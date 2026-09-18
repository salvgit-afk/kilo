"""Calcolo dei valori nutrizionali reali di una ricetta.

Il problema da risolvere: TheMealDB descrive le quantità come le scriverebbe
una persona — "1.2 kg", "¼ cup", "1 clove peeled crushed", "5 thinly sliced"
— e non fornisce alcun dato nutrizionale. Per sapere quante proteine ha un
piatto servono i **grammi**.

La divisione dei compiti segue `knowledge_base/evidence_conduct.md`:

  - **l'LLM interpreta il linguaggio**: "¼ cup di riso" → circa 45 g. È un
    compito linguistico e di conoscenza del mondo, quello in cui i modelli
    sono affidabili;
  - **il database fa l'aritmetica**: i macro si sommano dai valori per 100 g
    di USDA/wger. Ai modelli i calcoli non si affidano, perché sbagliano in
    modo silenzioso e plausibile.

Un valore nutrizionale non viene mai chiesto all'LLM: solo la quantità.

Onestà sul risultato: se alcuni ingredienti non trovano corrispondenza nel
database, il totale è **incompleto**. In quel caso si dichiara la copertura
invece di presentare un numero che sembra preciso e non lo è.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientSource
from app.services import catalog_sync
from app.services.themealdb_client import RawRecipe, RawRecipeIngredient

logger = logging.getLogger("recipe_analyzer")

# Sotto questa quota di ingredienti riconosciuti il totale non è
# abbastanza affidabile da essere mostrato come un dato.
MIN_COVERAGE_FOR_RELIABLE = 0.75

# Conversioni dirette, senza scomodare l'LLM: coprono i casi più frequenti e
# rendono il sistema utilizzabile anche senza chiave API.
_DIRECT_UNITS_TO_GRAMS = {
    "g": 1.0, "gr": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0,
    "ml": 1.0,           # approssimazione per liquidi a base acquosa
    "l": 1000.0,
    "litre": 1000.0, "liter": 1000.0,
    "oz": 28.35,
    "lb": 453.6, "lbs": 453.6,
}

_FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}

_NUMBER_UNIT_RE = re.compile(
    r"^\s*(?P<qty>\d+(?:[.,]\d+)?|[¼½¾⅓⅔⅛])\s*(?P<unit>[a-zA-Z]+)?\b"
)


@dataclass
class AnalyzedIngredient:
    name: str
    measure: str
    grams: float | None
    ingredient: Ingredient | None
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugars_g: float = 0.0
    conversion_source: str = "non riconosciuto"  # "diretta", "llm", "non riconosciuto"

    @property
    def resolved(self) -> bool:
        return self.ingredient is not None and self.grams is not None


@dataclass
class AnalyzedRecipe:
    recipe: RawRecipe
    servings: int
    ingredients: list[AnalyzedIngredient]
    knowledge_tags: list[str] = field(default_factory=lambda: ["macronutrienti"])

    @property
    def resolved_count(self) -> int:
        return sum(1 for i in self.ingredients if i.resolved)

    @property
    def coverage(self) -> float:
        """Quota di ingredienti con quantità e valori nutrizionali noti."""
        if not self.ingredients:
            return 0.0
        return self.resolved_count / len(self.ingredients)

    @property
    def is_reliable(self) -> bool:
        return self.coverage >= MIN_COVERAGE_FOR_RELIABLE

    def _total(self, attr: str) -> float:
        return sum(getattr(i, attr) for i in self.ingredients)

    @property
    def total_kcal(self) -> float:
        return self._total("kcal")

    @property
    def kcal_per_serving(self) -> float:
        return self.total_kcal / self.servings

    @property
    def protein_per_serving(self) -> float:
        return self._total("protein_g") / self.servings

    @property
    def carbs_per_serving(self) -> float:
        return self._total("carbs_g") / self.servings

    @property
    def fat_per_serving(self) -> float:
        return self._total("fat_g") / self.servings

    @property
    def fiber_per_serving(self) -> float:
        return self._total("fiber_g") / self.servings

    @property
    def sugars_per_serving(self) -> float:
        return self._total("sugars_g") / self.servings

    @property
    def unresolved_names(self) -> list[str]:
        return [i.name for i in self.ingredients if not i.resolved]


def parse_measure_directly(measure: str) -> float | None:
    """Converte le misure che non richiedono interpretazione ("900g", "1.2 kg").

    Restituisce `None` quando l'unità è casalinga o assente ("¼ cup",
    "1 clove peeled crushed"): quei casi vanno all'LLM, che sa quanto pesa
    uno spicchio d'aglio.
    """
    if not measure:
        return None

    match = _NUMBER_UNIT_RE.match(measure.strip())
    if not match:
        return None

    raw_qty = match.group("qty")
    quantity = _FRACTIONS.get(raw_qty)
    if quantity is None:
        try:
            quantity = float(raw_qty.replace(",", "."))
        except ValueError:
            return None

    unit = (match.group("unit") or "").lower()
    factor = _DIRECT_UNITS_TO_GRAMS.get(unit)
    if factor is None:
        return None

    return quantity * factor


_CONVERSION_SCHEMA = {
    "type": "object",
    "properties": {
        "conversioni": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indice": {"type": "integer"},
                    "grammi": {"type": "number"},
                },
                "required": ["indice", "grammi"],
            },
        }
    },
    "required": ["conversioni"],
}

_CONVERSION_PROMPT = """Converti in grammi le quantità di ingredienti scritte
in linguaggio comune.

La ricetta è per {porzioni} porzioni: le quantità sono per la ricetta intera.

REGOLE:
- Rispondi solo con la quantità in grammi, stimata in modo ragionevole per un
  ingrediente di dimensioni medie.
- Considera l'ingrediente: "1 clove" di aglio pesa circa 3 g, "1" cipolla
  circa 150 g, un cucchiaio da tavola di olio 9 g, un cucchiaino di olio 5 g.
- Se la quantità NON è indicata, usa la porzione standard italiana per una
  persona moltiplicata per {porzioni}:
{porzioni_standard}
- Se la quantità è indicata come "to taste", "q.b.", "a piacere", "for
  garnish" o simili, usa una quantità simbolica piccola (1-2 g per le spezie).
- Non inventare valori nutrizionali: ti serve solo il peso.
- Usa l'indice numerico fornito per ogni riga.

INGREDIENTI DA CONVERTIRE:
{righe}
"""

# Porzioni standard per persona (SINU, LARN V revisione 2024; il dettaglio è
# in `knowledge_base/standard_portions.md`). Servono quando una ricetta
# elenca gli ingredienti senza quantità: meglio partire da un riferimento
# ufficiale che da un numero a sensazione.
_PORZIONI_STANDARD = """  pasta, riso e cereali 80 g (crudi); pane 50 g; una piadina o tortilla
  circa 100 g; carne rossa o bianca 100 g; pesce fresco 150 g; pesce in
  scatola 50 g; uova 50 g ciascuno; legumi in scatola 150 g, secchi 50 g;
  formaggi freschi 100 g; altri formaggi 50 g; latte e yogurt 125 g;
  verdure 200 g; insalata 80 g; frutta 150 g; frutta secca 30 g;
  olio 9 g; burro 10 g; patate 200 g."""


def _convert_with_llm(
    pending: list[tuple[int, RawRecipeIngredient]], servings: int = 4
) -> dict[int, float]:
    """Chiede all'LLM il peso in grammi delle misure casalinghe.

    Una sola chiamata per ricetta. Se l'LLM non è disponibile, gli
    ingredienti restano non risolti e la ricetta lo dichiara: meglio una
    copertura parziale e onesta che un peso inventato.
    """
    from app.services import llm_client

    righe = "\n".join(
        f"{indice}. {ing.measure or '(quantità non indicata)'} di {ing.name}"
        for indice, ing in pending
    )

    try:
        risposta = llm_client.generate_structured(
            _CONVERSION_PROMPT.format(
                righe=righe, porzioni=max(1, servings), porzioni_standard=_PORZIONI_STANDARD
            ),
            _CONVERSION_SCHEMA,
            # Una ricetta può avere 15-20 ingredienti da convertire in una
            # sola chiamata: il timeout predefinito di 30s non basta.
            timeout=75.0,
            purpose="recipe_quantities",
        )
    except (llm_client.LLMNotConfigured, llm_client.LLMError) as e:
        logger.info("Conversione in grammi non disponibile (%s)", e)
        return {}

    converted: dict[int, float] = {}
    for voce in risposta.get("conversioni") or []:
        try:
            indice = int(voce["indice"])
            grammi = float(voce["grammi"])
        except (KeyError, TypeError, ValueError):
            continue
        # Un peso negativo o assurdo indica un errore di interpretazione:
        # meglio scartarlo e dichiarare l'ingrediente non risolto.
        if 0 < grammi <= 5000:
            converted[indice] = grammi

    return converted


# Forme trasformate di un alimento. Una ricetta che dice "Tomatoes" intende
# i pomodori, non il pomodoro in polvere: senza questa penalizzazione USDA
# restituisce come primo risultato "Tomato powder" (302 kcal/100 g invece di
# 22) e il totale della ricetta risulta gonfiato di centinaia di calorie.
_PROCESSED_MARKERS = (
    "powder", "dehydrated", "dried", "spread", "paste", "canned", "sauce",
    "fried", "rings", "juice", "concentrate", "extract", "flakes", "soup",
    "smoked", "breaded", "battered", "candied", "syrup", "salted", "sweetened",
    "roll", "patty", "nuggets", "meatless", "substitute", "imitation",
)

# Indicano l'alimento nella forma in cui una ricetta lo elenca.
_FRESH_MARKERS = ("raw", "fresh", "whole")

# Parole che non aggiungono identità all'alimento: non vanno contate nel
# calcolo della copertura, altrimenti "Oil, olive, salad or cooking" verrebbe
# penalizzato per parole che non cambiano di che alimento si tratta.
_FILLER_WORDS = frozenset(
    {"raw", "fresh", "whole", "or", "and", "with", "without", "all", "type",
     "types", "commercial", "commercially", "prepared", "unprepared", "nfs"}
)


def _normalize(text: str) -> str:
    """Minuscole senza punteggiatura, con i plurali più banali ridotti."""
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    parole = []
    for parola in text.split():
        if len(parola) > 3 and parola.endswith("es"):
            parola = parola[:-2]
        elif len(parola) > 3 and parola.endswith("s"):
            parola = parola[:-1]
        parole.append(parola)
    return " ".join(parole)


def score_match(query: str, candidate_name: str) -> float:
    """Quanto un alimento del catalogo corrisponde all'ingrediente cercato.

    Il principio è penalizzare lo **scostamento dalla richiesta**, non
    proprietà assolute: "oil" è una forma trasformata, ma se l'utente cerca
    proprio "Vegetable oil" non va penalizzata. Per questo i marcatori
    contano solo quando compaiono nel nome del candidato e **non** nella
    query.
    """
    q = _normalize(query)
    name = _normalize(candidate_name)
    if not q or not name:
        return 0.0

    score = 0.0

    parole_query = set(q.split())
    parole_nome = name.split()

    # L'alimento base ha il termine cercato in testa ("Tomato, roma"),
    # i derivati lo hanno più avanti o come aggettivo ("Butter, salted").
    if name == q:
        score += 20
    elif name.startswith(q):
        score += 12
    elif f" {q}" in f" {name}":
        score += 4

    # USDA nomina gli alimenti mettendo per prima l'identità del cibo:
    # "Oil, olive, salad or cooking" è un olio, "Mayonnaise, ... with olive
    # oil" è una maionese. Senza questo criterio la maionese vince, perché
    # contiene la ricerca per intero e in ordine.
    if parole_nome and parole_nome[0] in parole_query:
        score += 10

    # Tutte le parole cercate presenti, anche in ordine diverso: "Oil, olive"
    # corrisponde a "olive oil" quanto "Olive oil".
    if parole_query and parole_query.issubset(set(parole_nome)):
        score += 6

    for marker in _PROCESSED_MARKERS:
        if marker in name and marker not in q:
            score -= 6

    if any(marker in name for marker in _FRESH_MARKERS):
        score += 5

    # Quanta parte del nome candidato è coperta dalla ricerca. Distingue
    # l'alimento vero da un prodotto che semplicemente lo contiene: cercando
    # "olive oil", "Oil, olive" è coperto quasi del tutto, mentre
    # "Mayonnaise, reduced fat, with olive oil" ha molte parole in più.
    # È un criterio strutturale, che non richiede di elencare all'infinito
    # le parole da penalizzare ("crackers", "snacks", "mayonnaise"...).
    parole_significative = [p for p in parole_nome if p not in _FILLER_WORDS]
    if parole_significative:
        copertura = sum(1 for p in parole_significative if p in parole_query) / len(
            parole_significative
        )
        score += 8 * copertura

    # A parità di tutto, il nome più breve è il meno qualificato, quindi il
    # più generico: "Onions, raw" batte "Onions, dehydrated flakes".
    score -= len(name) / 40.0

    return score


_MATCH_CACHE = "ingredient_match"


def _match_key(name: str) -> str:
    return " ".join((name or "").lower().split())[:190]


def _match_ingredient(db: Session, name: str) -> Ingredient | None:
    """Cerca l'ingrediente nel catalogo e sceglie il candidato migliore.

    Non si prende il primo risultato: il ranking di rilevanza di USDA per i
    nomi generici è debole (cercando "Salt" propone "Butter, salted" prima di
    "Salt, table"). La risposta corretta è quasi sempre fra i primi
    risultati, ma va scelta.

    La scelta viene ricordata: "Chicken" compare in decine di ricette, e
    rifare ogni volta due ricerche di rete per lo stesso nome era la parte
    più lenta dei suggerimenti.
    """
    from app.services import translation

    chiave = _match_key(name)
    cached = translation.cache_get(db, _MATCH_CACHE, chiave)
    if cached and cached.get("id"):
        ingrediente = db.get(Ingredient, cached["id"])
        if ingrediente is not None:
            return ingrediente

    try:
        risultati = catalog_sync.search_and_cache_ingredients(db, name, limit=6)
    except Exception as e:  # rete assente o fonte non raggiungibile
        logger.warning("Ricerca ingrediente %r fallita: %s", name, e)
        return None

    migliore = _choose_ingredient(name, risultati)
    if migliore is not None:
        translation.cache_put(db, _MATCH_CACHE, chiave, {"id": migliore.id})
    return migliore


def _choose_ingredient(name: str, risultati: list[Ingredient]) -> Ingredient | None:
    if not risultati:
        return None

    def _punteggio(ing: Ingredient) -> tuple[float, float]:
        punteggio = score_match(name, ing.name)
        # Spareggio sulla fonte: per un ingrediente di ricetta serve
        # l'alimento generico, e i dati USDA sono curati in laboratorio
        # mentre quelli wger/Open Food Facts sono inseriti dagli utenti.
        # Senza questo criterio, fra tre voci "Onion" con lo stesso nome si
        # sceglierebbe a caso fra 56, 289 e 47 kcal/100 g.
        if ing.source == IngredientSource.USDA:
            punteggio += 3
        # A parità di punteggio si preferisce il nome più corto, cioè il meno
        # qualificato e quindi il più generico. Deliberatamente **non** si usa
        # il valore calorico come spareggio: fra voci omonime sceglierebbe
        # sempre la meno calorica, sottostimando in modo sistematico — per un
        # piano alimentare è la direzione d'errore più dannosa, perché fa
        # credere di mangiare meno di quanto si mangia.
        return punteggio, -len(ing.name)

    migliore = max(risultati, key=_punteggio)
    logger.debug("Ingrediente %r -> %r", name, migliore.name)
    return migliore


_CONVERSION_CACHE = "recipe_grams"


def _pending_measures(recipe: RawRecipe) -> list[tuple[int, RawRecipeIngredient]]:
    return [
        (indice, ing)
        for indice, ing in enumerate(recipe.ingredients)
        if parse_measure_directly(ing.measure) is None
    ]


def _conversions_for(
    db: Session,
    recipe: RawRecipe,
    pending: list[tuple[int, RawRecipeIngredient]],
    servings: int = 4,
) -> dict[int, float]:
    """Conversioni in grammi, dalla cache se la ricetta è già stata vista.

    La stessa ricetta cercata due volte deve dare gli stessi numeri: rifare la
    conversione produrrebbe stime leggermente diverse a ogni ricerca.
    """
    from app.services import translation

    cached = translation.cache_get(db, _CONVERSION_CACHE, recipe.meal_id)
    if cached is not None:
        return {int(k): float(v) for k, v in cached.items()}

    conversioni = _convert_with_llm(pending, servings=servings)
    if conversioni:
        translation.cache_put(
            db, _CONVERSION_CACHE, recipe.meal_id, {str(k): v for k, v in conversioni.items()}
        )
    return conversioni


def prefetch_recipe_data(db: Session, recipes: list[RawRecipe]) -> None:
    """Prepara in parallelo tutto ciò che serve ad analizzare più ricette.

    In sequenza, sei ricette da una dozzina di ingredienti costavano sei
    chiamate LLM e oltre cento ricerche di rete una dopo l'altra, più un
    commit sul database remoto per ogni risultato: la richiesta superava i
    quattro minuti. Qui il lavoro di rete — conversioni in grammi e ricerche
    degli ingredienti — parte tutto insieme; le scritture avvengono dopo, in
    questo thread (la sessione non si condivide fra thread), con un solo
    commit.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.models import LlmCache
    from app.services import translation

    conversioni = [
        (r, pending)
        for r in recipes
        if (pending := _pending_measures(r))
        and translation.cache_get(db, _CONVERSION_CACHE, r.meal_id) is None
    ]

    nomi: dict[str, str] = {}
    for ricetta in recipes:
        for ing in ricetta.ingredients:
            nomi.setdefault(_match_key(ing.name), ing.name)
    noti = translation.cached_keys(db, _MATCH_CACHE, list(nomi))
    da_cercare = [(chiave, nome) for chiave, nome in nomi.items() if chiave not in noti]

    if not conversioni and not da_cercare:
        return

    with ThreadPoolExecutor(max_workers=10) as pool:
        futuri_conv = [pool.submit(_convert_with_llm, pending) for _, pending in conversioni]
        futuri_ing = [
            pool.submit(catalog_sync.fetch_raw_ingredients, nome, limit=6)
            for _, nome in da_cercare
        ]
        risultati_conv = [f.result() for f in futuri_conv]
        risultati_ing = [f.result() for f in futuri_ing]

    for (ricetta, _), conv in zip(conversioni, risultati_conv):
        if conv:
            db.add(
                LlmCache(
                    kind=_CONVERSION_CACHE,
                    key=ricetta.meal_id,
                    payload={str(k): v for k, v in conv.items()},
                )
            )
    for (chiave, nome), (usda, wger) in zip(da_cercare, risultati_ing):
        trovati = catalog_sync.store_raw_ingredients(db, usda, wger, commit=False)
        migliore = _choose_ingredient(nome, trovati)
        if migliore is not None:
            db.add(LlmCache(kind=_MATCH_CACHE, key=chiave, payload={"id": migliore.id}))

    try:
        db.commit()
    except Exception as e:  # es. la stessa ricetta preparata da una richiesta concorrente
        logger.warning("Salvataggio dei dati delle ricette non riuscito: %s", e)
        db.rollback()


def analyze_recipe(
    db: Session, recipe: RawRecipe, *, servings: int = 4, use_llm: bool = True
) -> AnalyzedRecipe:
    """Calcola i valori nutrizionali reali di una ricetta.

    `servings` non è fornito da TheMealDB: si assume 4 porzioni salvo
    indicazione diversa. È un'assunzione dichiarata, non un dato.
    """
    servings = max(1, servings)
    analyzed: list[AnalyzedIngredient] = []
    pending: list[tuple[int, RawRecipeIngredient]] = []

    for indice, ing in enumerate(recipe.ingredients):
        grams = parse_measure_directly(ing.measure)
        voce = AnalyzedIngredient(
            name=ing.name,
            measure=ing.measure,
            grams=grams,
            ingredient=None,
            conversion_source="diretta" if grams is not None else "non riconosciuto",
        )
        analyzed.append(voce)
        if grams is None:
            pending.append((indice, ing))

    if pending and use_llm:
        for indice, grammi in _conversions_for(db, recipe, pending, servings).items():
            if 0 <= indice < len(analyzed):
                analyzed[indice].grams = grammi
                analyzed[indice].conversion_source = "llm"

    # I macro li calcola il database, non il modello.
    for voce in analyzed:
        if voce.grams is None:
            continue
        ingrediente = _match_ingredient(db, voce.name)
        if ingrediente is None:
            continue

        voce.ingredient = ingrediente
        fattore = voce.grams / 100.0
        voce.kcal = (ingrediente.kcal_100g or 0.0) * fattore
        voce.protein_g = (ingrediente.protein_100g or 0.0) * fattore
        voce.carbs_g = (ingrediente.carbs_100g or 0.0) * fattore
        voce.fat_g = (ingrediente.fat_100g or 0.0) * fattore
        voce.fiber_g = (ingrediente.fiber_100g or 0.0) * fattore
        voce.sugars_g = (ingrediente.sugars_100g or 0.0) * fattore

    return AnalyzedRecipe(recipe=recipe, servings=servings, ingredients=analyzed)
