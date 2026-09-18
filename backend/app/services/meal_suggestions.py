"""Suggerimento di ricette in base ai target nutrizionali.

Il criterio non è "la ricetta più proteica" ma **quanto avvicina l'utente ai
target che gli restano per la giornata**. Una ricetta da 60 g di proteine è
ottima a pranzo se ne mancano 70, pessima se ne mancano 20 e sfonderebbe le
calorie.

Le ricette arrivano da due fonti, in quest'ordine:

1. **Ricette Kilo** (`app/data/kilo_recipes.py`): italiane, con ogni dose in
   grammi, quindi macro calcolati senza stime e senza chiamate al modello;
2. **TheMealDB**, solo se le Ricette Kilo non bastano a riempire i
   suggerimenti: quantità in linguaggio comune, convertite e dichiarate
   come stima.

Entrambe passano da `recipe_analyzer` per ottenere i macro reali. Le ricette
con copertura insufficiente degli ingredienti vengono scartate: meglio
proporne poche e affidabili che molte con numeri inventati.

Filtro dietetico: TheMealDB ha categorie native "Vegan" e "Vegetarian", che
vengono usate direttamente quando il profilo lo richiede.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.data import kilo_recipes
from app.models import DietType, UserProfile
from app.services import recipe_analyzer, themealdb_client, translation
from app.services.nutrition_targets import NutritionTargets
from app.services.recipe_analyzer import AnalyzedRecipe

logger = logging.getLogger("meal_suggestions")


class RecipeSourceUnavailable(RuntimeError):
    """La fonte delle ricette non risponde: va detto, non trasformato in un
    errore 500 incomprensibile né in un "nessun risultato" falso."""

# Quota dei target giornalieri che un singolo pasto dovrebbe coprire.
DEFAULT_MEAL_SHARE = 0.33

# `protein_intake.md`: 20-40 g di proteine a pasto è la finestra utile per
# la sintesi proteica.
PROTEIN_PER_MEAL_RANGE = (20.0, 40.0)

# Categorie TheMealDB compatibili con le diete vegetali.
VEGAN_CATEGORY = "Vegan"
VEGETARIAN_CATEGORIES = ("Vegetarian", "Vegan")


@dataclass
class MealSuggestion:
    analyzed: AnalyzedRecipe
    fit_score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.analyzed.recipe.name


def _remaining(target: float, consumed: float) -> float:
    return max(0.0, target - consumed)


def score_fit(
    analyzed: AnalyzedRecipe,
    *,
    kcal_needed: float,
    protein_needed: float,
) -> tuple[float, list[str]]:
    """Quanto una ricetta si avvicina a ciò che manca, per una porzione.

    Penalizza sia lo scarso apporto sia lo sforamento: superare il target
    calorico è un problema quanto restare troppo sotto quello proteico.
    """
    reasons: list[str] = []
    kcal = analyzed.kcal_per_serving
    protein = analyzed.protein_per_serving

    if kcal_needed <= 0:
        return 0.0, ["Hai già raggiunto il target calorico di oggi."]

    # 1.0 = copre esattamente il fabbisogno rimasto per questo pasto.
    kcal_ratio = kcal / kcal_needed
    protein_ratio = protein / protein_needed if protein_needed > 0 else 1.0

    # Scostamento dall'ideale, con lo sforamento calorico pesato di più.
    kcal_penalty = abs(1 - kcal_ratio) * (1.4 if kcal_ratio > 1 else 1.0)
    protein_penalty = abs(1 - min(protein_ratio, 1.5))

    score = max(0.0, 10 - kcal_penalty * 5 - protein_penalty * 4)

    minimo, massimo = PROTEIN_PER_MEAL_RANGE
    if minimo <= protein <= massimo:
        score += 1.5
        reasons.append(
            f"{protein:.0f} g di proteine per porzione, dentro la finestra "
            f"20-40 g utile alla sintesi proteica."
        )
    elif protein < minimo:
        reasons.append(
            f"Solo {protein:.0f} g di proteine: valuta di affiancarci una fonte "
            "proteica."
        )

    if kcal_ratio > 1.25:
        reasons.append(
            f"{kcal:.0f} kcal a porzione: più di quanto ti resta per questo pasto "
            f"({kcal_needed:.0f} kcal). Riduci la porzione o tienila per un altro giorno."
        )
    elif 0.75 <= kcal_ratio <= 1.25:
        reasons.append(f"{kcal:.0f} kcal a porzione, in linea con il tuo target.")

    if analyzed.fiber_per_serving >= 7:
        score += 0.5
        reasons.append(f"Buon apporto di fibra ({analyzed.fiber_per_serving:.0f} g).")

    return score, reasons


def _search_query(query: str, limit: int) -> list[themealdb_client.RawRecipe]:
    """Cerca per titolo e, se non basta, per ingrediente principale.

    TheMealDB cerca solo nel titolo: "chicken" trova i piatti che hanno
    "chicken" nel nome, ma non un curry di pollo chiamato "Butter Chicken" se
    si cerca "chicken breast". La ricerca per ingrediente completa i risultati.
    """
    ricette = themealdb_client.search_by_name(query)
    visti = {r.meal_id for r in ricette}

    termini = [query] + sorted(set(query.split()) - {query}, key=len, reverse=True)
    for termine in termini:
        if len(ricette) >= limit:
            break
        for meal_id, _ in themealdb_client.filter_by_main_ingredient(termine.replace(" ", "_")):
            if len(ricette) >= limit:
                break
            if meal_id in visti:
                continue
            completa = themealdb_client.lookup(meal_id)
            if completa is not None:
                ricette.append(completa)
                visti.add(meal_id)
    return ricette


def _candidate_recipes(
    db: Session, profile: UserProfile, query: str | None, limit: int
) -> list[themealdb_client.RawRecipe]:
    """Recupera le ricette candidate, rispettando la dieta dichiarata."""
    if profile.diet_type == DietType.VEGAN:
        categorie = [VEGAN_CATEGORY]
    elif profile.diet_type == DietType.VEGETARIAN:
        categorie = list(VEGETARIAN_CATEGORIES)
    else:
        categorie = []

    if query:
        # TheMealDB conosce solo l'inglese: "pollo" trovava soltanto tre piatti
        # spagnoli con "Pollo" nel titolo.
        inglese = translation.query_to_english(db, query) or query
        ricette = _search_query(inglese, limit * 2 if categorie else limit)
        if categorie:
            ricette = [r for r in ricette if r.category in categorie]
        return ricette[:limit]

    if categorie:
        # `filter_by_category` non include ingredienti né procedimento:
        # serve una lookup per ciascuna ricetta.
        riferimenti: list[tuple[str, str]] = []
        for categoria in categorie:
            riferimenti.extend(themealdb_client.filter_by_category(categoria))

        ricette = []
        for meal_id, _ in riferimenti[:limit]:
            completa = themealdb_client.lookup(meal_id)
            if completa is not None:
                ricette.append(completa)
        return ricette

    # Nessun filtro: si parte da una ricerca generica su fonti proteiche.
    return themealdb_client.search_by_name("chicken")[:limit]


# --- Ricette Kilo ---------------------------------------------------------------------


def kilo_raw_recipe(ricetta: kilo_recipes.KiloRecipe) -> themealdb_client.RawRecipe:
    """Una Ricetta Kilo nella forma che `recipe_analyzer` sa analizzare.

    Le misure sono già in grammi ("150 g"): l'analisi le legge direttamente
    e non passa mai dal modello.
    """
    return themealdb_client.RawRecipe(
        meal_id=ricetta.meal_id,
        name=ricetta.name,
        category=ricetta.category,
        area="Italian",
        instructions=ricetta.steps,
        thumbnail_url=None,
        tags=list(ricetta.keywords),
        ingredients=[
            themealdb_client.RawRecipeIngredient(name=i.en, measure=f"{i.grams:g} g")
            for i in ricetta.ingredients
        ],
    )


def _dieta_compatibile(profile: UserProfile, ricetta: kilo_recipes.KiloRecipe) -> bool:
    if profile.diet_type == DietType.VEGAN:
        return ricetta.diet == kilo_recipes.VEGAN
    if profile.diet_type == DietType.VEGETARIAN:
        return ricetta.diet in (kilo_recipes.VEGETARIAN, kilo_recipes.VEGAN)
    return True


# Termini con cui si trova un'intera categoria. Non il nome della categoria:
# "Pollo e tacchino" farebbe uscire le polpette di tacchino cercando "pollo".
CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "Colazione": ("colazione",),
    "Pollo e tacchino": ("carne bianca",),
    "Pesce": ("pesce",),
    "Carne rossa": ("carne rossa",),
    "Legumi e vegetariane": ("vegetariano", "vegetariana"),
    "Spuntini": ("spuntino", "merenda"),
}


def _radice(parola: str) -> str:
    """Toglie la vocale finale: "uova" trova "uovo", "lenticchia" "lenticchie"."""
    return parola[:-1] if len(parola) >= 4 and parola[-1] in "aeiou" else parola


def kilo_candidates(profile: UserProfile, query: str | None) -> list[kilo_recipes.KiloRecipe]:
    """Le Ricette Kilo compatibili con la dieta e, se c'è, con la ricerca.

    La ricerca è in italiano, come le ricette: ogni parola deve comparire nel
    nome, nella categoria, nelle parole chiave o negli ingredienti.
    """
    ricette = [r for r in kilo_recipes.RECIPES if _dieta_compatibile(profile, r)]
    parole = [_radice(p) for p in re.findall(r"[a-zàèéìòù]+", (query or "").lower()) if len(p) >= 3]
    if not parole:
        return ricette

    def testo(r: kilo_recipes.KiloRecipe) -> str:
        return " ".join(
            [r.name, *CATEGORY_TERMS.get(r.category, ()), *r.keywords, *(i.it for i in r.ingredients)]
        ).lower()

    # A inizio parola: la radice "poll" non deve trovare la "cipolla".
    schemi = [re.compile(rf"\b{re.escape(p)}") for p in parole]
    return [r for r in ricette if all(schema.search(testo(r)) for schema in schemi)]


def is_kilo(meal_id: str | None) -> bool:
    return kilo_recipes.get(meal_id) is not None


def suggest_meals(
    db: Session,
    profile: UserProfile,
    targets: NutritionTargets,
    *,
    query: str | None = None,
    consumed_kcal: float = 0.0,
    consumed_protein_g: float = 0.0,
    meal_share: float = DEFAULT_MEAL_SHARE,
    candidates: int = 6,
    top: int = 3,
) -> list[MealSuggestion]:
    """Propone le ricette che meglio avvicinano ai target rimasti.

    `consumed_*` permette di suggerire in corso di giornata: a cena si tiene
    conto di quanto già mangiato, non del target pieno.
    """
    kcal_rimaste = _remaining(targets.target_kcal, consumed_kcal)
    protein_rimaste = _remaining(targets.protein_g, consumed_protein_g)

    kcal_pasto = kcal_rimaste * meal_share if consumed_kcal == 0 else kcal_rimaste
    protein_pasto = (
        protein_rimaste * meal_share if consumed_protein_g == 0 else protein_rimaste
    )

    kilo = kilo_candidates(profile, query)
    porzioni = {r.meal_id: r.servings for r in kilo}
    ricette = [kilo_raw_recipe(r) for r in kilo]

    # TheMealDB serve solo quando le Ricette Kilo non bastano: è più lento
    # (quantità da convertire con il modello) e i suoi valori sono stime.
    if len(kilo) < top:
        try:
            ricette += _candidate_recipes(db, profile, query, candidates)
        except themealdb_client.MealDbError as e:
            logger.warning("TheMealDB non disponibile: %s", e)
            if not kilo:
                raise RecipeSourceUnavailable(
                    "Il servizio delle ricette (TheMealDB) non risponde in questo momento. "
                    "Riprova tra qualche minuto: diario e target funzionano comunque."
                ) from e
    if not ricette:
        return []

    # Conversioni in grammi e ricerche degli ingredienti sono indipendenti fra
    # loro: si preparano tutte in parallelo prima dell'analisi.
    recipe_analyzer.prefetch_recipe_data(db, ricette)

    suggerimenti: list[MealSuggestion] = []
    for ricetta in ricette:
        analizzata = recipe_analyzer.analyze_recipe(
            db, ricetta, servings=porzioni.get(ricetta.meal_id, 4)
        )

        # Una ricetta di cui non si conoscono metà degli ingredienti produce
        # un totale che sembra un dato e non lo è: meglio non proporla.
        if not analizzata.is_reliable:
            logger.info(
                "Ricetta %r scartata: copertura ingredienti %.0f%%",
                ricetta.name, analizzata.coverage * 100,
            )
            continue

        punteggio, motivi = score_fit(
            analizzata, kcal_needed=kcal_pasto, protein_needed=protein_pasto
        )
        suggerimenti.append(
            MealSuggestion(analyzed=analizzata, fit_score=punteggio, reasons=motivi)
        )

    # Prima le Ricette Kilo (dosi esatte), poi le altre; dentro ciascun
    # gruppo, quelle che avvicinano di più ai target.
    suggerimenti.sort(key=lambda s: (is_kilo(s.analyzed.recipe.meal_id), s.fit_score), reverse=True)
    return suggerimenti[:top]
