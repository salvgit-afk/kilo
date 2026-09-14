"""Suggerimento di ricette in base ai target nutrizionali.

Il criterio non è "la ricetta più proteica" ma **quanto avvicina l'utente ai
target che gli restano per la giornata**. Una ricetta da 60 g di proteine è
ottima a pranzo se ne mancano 70, pessima se ne mancano 20 e sfonderebbe le
calorie.

Le ricette arrivano da TheMealDB (struttura e procedimento) e vengono
analizzate da `recipe_analyzer` per ottenere i macro reali. Le ricette con
copertura insufficiente degli ingredienti vengono scartate: meglio
proporne poche e affidabili che molte con numeri inventati.

Filtro dietetico: TheMealDB ha categorie native "Vegan" e "Vegetarian", che
vengono usate direttamente quando il profilo lo richiede.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

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

    try:
        ricette = _candidate_recipes(db, profile, query, candidates)
    except themealdb_client.MealDbError as e:
        logger.warning("TheMealDB non disponibile: %s", e)
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
        analizzata = recipe_analyzer.analyze_recipe(db, ricetta)

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

    suggerimenti.sort(key=lambda s: s.fit_score, reverse=True)
    return suggerimenti[:top]
