"""Traduzioni in italiano, con cache nel database.

Le fonti di contenuto dell'app (free-exercise-db, TheMealDB) sono in
inglese. L'LLM qui **traduce testo che arriva da una fonte**, non ne produce
di nuovo: le regole del prompt vietano di aggiungere passaggi, carichi,
serie o quantità. È lo stesso principio di `evidence_conduct.md` applicato
alla lingua.

Ogni traduzione viene salvata. Si paga una chiamata la prima volta, poi la
risposta è istantanea e soprattutto **stabile**: lo stesso esercizio non
cambia nome da un giorno all'altro.

Se l'LLM non è disponibile nulla si rompe: si mostra il testo originale.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise, LlmCache

logger = logging.getLogger("translation")


# --- Cache ---------------------------------------------------------------------


def cache_get(db: Session, kind: str, key: str) -> dict | None:
    riga = db.scalar(select(LlmCache).where(LlmCache.kind == kind, LlmCache.key == key))
    return riga.payload if riga is not None else None


def cached_keys(db: Session, kind: str, keys: list[str]) -> set[str]:
    """Quali chiavi sono già in cache, con una sola query."""
    if not keys:
        return set()
    return set(
        db.scalars(select(LlmCache.key).where(LlmCache.kind == kind, LlmCache.key.in_(keys)))
    )


def cache_put(db: Session, kind: str, key: str, payload: dict) -> None:
    riga = db.scalar(select(LlmCache).where(LlmCache.kind == kind, LlmCache.key == key))
    if riga is None:
        db.add(LlmCache(kind=kind, key=key[:190], payload=payload))
    else:
        riga.payload = payload
    db.commit()


# --- Esercizi ------------------------------------------------------------------

_EXERCISE_SCHEMA = {
    "type": "object",
    "properties": {
        "esercizi": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "nome": {"type": "string"},
                    "esecuzione": {"type": "array", "items": {"type": "string"}},
                    "consigli": {"type": "array", "items": {"type": "string"}},
                    "focus": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "nome", "esecuzione", "consigli", "focus"],
            },
        }
    },
    "required": ["esercizi"],
}

# I soli termini inglesi ammessi nei nomi: nelle palestre italiane si dicono
# così. Tutto il resto va tradotto, e `english_leftovers` lo verifica.
ALLOWED_GYM_TERMS = (
    "lat machine", "leg press", "leg extension", "leg curl", "chest press",
    "shoulder press", "pectoral machine", "hack squat", "front squat", "squat",
    "french press", "arnold press", "military press", "jm press", "tate press",
    "good morning", "step up", "skull crusher", "spider curl", "zottman",
    "pushdown", "pulley", "t-bar", "crunch", "curl", "ez", "air bike", "sissy",
    "jefferson", "zercher", "zecher", "gironda", "butterfly", "multipower", "dip",
)

_EXERCISE_PROMPT = """Sei un istruttore di sala pesi italiano. Per ogni esercizio scrivi la scheda
in un italiano naturale e corretto, come la leggerebbe un utente italiano.

NOME ("nome")
- Tutto in italiano, breve (al massimo 6 parole), senza due punti né parentesi.
- Sono ammessi SOLO questi termini inglesi, perché nelle palestre italiane si
  dicono così: {termini}.
- Ogni altra parola va tradotta. Riferimenti: barbell = bilanciere,
  dumbbell = manubrio o manubri, cable = cavi, machine = macchina,
  smith machine = multipower, bench = panca, incline = inclinata,
  decline = declinata, lying = sdraiato, seated = seduto, standing = in piedi,
  grip = presa, wide = larga, close = stretta, reverse = inversa,
  raise = alzate, fly = croci, row = rematore, lunge = affondi,
  dead lift = stacco, shrug = scrollate, calf raise = polpacci,
  push up = piegamenti, hammer = a martello, preacher = panca Scott,
  concentration = di concentrazione, one arm = a un braccio,
  overhead = sopra la testa.
- Esempi: "Bench Press: Barbell" -> "Panca piana con bilanciere";
  "Bench Press: Dumbbell (Incline)" -> "Panca inclinata con manubri";
  "Pull Down: Wide Bar (Wide Grip)" -> "Lat machine presa larga";
  "Seated Cable Rows" -> "Pulley basso";
  "Lateral Dumbbell Raises" -> "Alzate laterali con manubri";
  "Butterfly Machine" -> "Pectoral machine";
  "Romanian Dead Lift" -> "Stacco rumeno";
  "Triceps Pushdown: Cable (Rope)" -> "Pushdown ai cavi con corda";
  "Standing Calf Raises using Machine" -> "Polpacci in piedi alla macchina".

ESECUZIONE ("esecuzione")
- Riscrivi i passaggi della fonte in italiano chiaro e scorrevole, con il tu e
  l'imperativo: posizione di partenza, movimento, ritorno. Frasi complete e
  terminologia corretta da sala pesi, non una traduzione parola per parola.
- Da 3 a 8 voci: puoi unire o dividere i passaggi per chiarezza, ma NON
  aggiungere nulla che la fonte non dica (niente carichi, serie, ripetizioni,
  tempi, respirazione o avvertenze inventate).

CONSIGLI ("consigli")
- Traduci i consigli della fonte, se presenti; altrimenti lista vuota.

FOCUS ("focus")
- 2 o 3 indicazioni brevi (massimo 14 parole) su dove concentrare l'attenzione
  per sentire lavorare il muscolo principale, ricavate dal movimento descritto
  e dai muscoli indicati. Niente numeri, promesse di risultati o indicazioni
  mediche.

Se una voce contiene "da_correggere", correggi esattamente quei problemi.
Restituisci lo stesso "id" ricevuto per ogni esercizio.

ESERCIZI
{esercizi}
"""

_ENGLISH_WORDS = frozenset(
    """
    with and the on using one two arm arms leg legs barbell barbells dumbbell
    dumbbells cable cables machine bench incline decline lying seated standing
    raise raises fly flys flyes row rows grip wide close narrow reverse press
    extension extensions pull pulls down up ups lunge lunges calf calves shrug
    shrugs kickback body weight ball band bands bent over rear front lateral
    side squats dead lift lifts hammer preacher concentration drag triceps
    biceps chest shoulder shoulders back hip thigh crossover pullover rotation
    upright plate stance single alternating overhead behind head floor knees
    """.split()
)

_ENGLISH_STOPWORDS = frozenset("the your you and with until of to while keep slowly".split())


def english_leftovers(name: str) -> list[str]:
    """Parole inglesi rimaste in un nome, esclusi i termini da palestra ammessi."""
    testo = (name or "").lower()
    for termine in sorted(ALLOWED_GYM_TERMS, key=len, reverse=True):
        testo = re.sub(rf"(?<![a-z]){re.escape(termine)}(?![a-z])", " ", testo)
    return [w for w in re.findall(r"[a-z]+", testo) if w in _ENGLISH_WORDS]


def _looks_english(frasi: list[str]) -> bool:
    parole = re.findall(r"[a-z]+", " ".join(frasi).lower())
    return sum(1 for w in parole if w in _ENGLISH_STOPWORDS) >= 3

# Nomi dei gruppi muscolari passati al prompt, perché il focus parli di
# "petto" e non di "Chest".
_MUSCOLI_IT = {
    "Chest": "petto", "Lats": "dorso", "Shoulders": "spalle", "Biceps": "bicipiti",
    "Triceps": "tricipiti", "Quads": "quadricipiti", "Hamstrings": "femorali",
    "Glutes": "glutei", "Calves": "polpacci", "Abs": "addominali",
    "Trapezius": "trapezio", "Forearms": "avambracci", "Lower back": "zona lombare",
    "Adductors": "adduttori", "Neck": "collo",
}

# Blocchi piccoli: con testi riscritti (non tradotti riga per riga) il modello
# lavora meglio su pochi esercizi alla volta.
EXERCISE_BATCH_SIZE = 6


def _muscoli(testo: str | None) -> str:
    return ", ".join(
        _MUSCOLI_IT.get(m.strip(), m.strip()) for m in (testo or "").split(",") if m.strip()
    )


def _clean_list(values, *, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()][:limit]


def _exercise_payload(ex: Exercise, da_correggere: list[str] | None) -> dict:
    voce = {
        "id": ex.id,
        "nome_originale": ex.name,
        "muscolo_principale": _muscoli(ex.primary_muscle),
        "muscoli_secondari": _muscoli(ex.secondary_muscles),
        "attrezzatura": ex.equipment,
        "passaggi": ex.instructions or [],
        "consigli": ex.tips or [],
    }
    if da_correggere:
        voce["da_correggere"] = da_correggere
    return voce


def _check_translation(voce: dict) -> tuple[dict, list[str]]:
    """Pulisce una traduzione e dice cosa non va."""
    dati = {
        "nome": str(voce.get("nome") or "").strip().rstrip("."),
        "esecuzione": _clean_list(voce.get("esecuzione"), limit=10),
        "consigli": _clean_list(voce.get("consigli"), limit=6),
        "focus": _clean_list(voce.get("focus"), limit=3),
    }
    problemi: list[str] = []
    if not dati["nome"]:
        problemi.append("nome mancante")
    inglesi = english_leftovers(dati["nome"])
    if inglesi:
        problemi.append("nel nome restano parole inglesi da tradurre: " + ", ".join(inglesi))
    if len(dati["esecuzione"]) < 2:
        problemi.append("esecuzione mancante o troppo breve")
    elif _looks_english(dati["esecuzione"] + dati["consigli"]):
        problemi.append("esecuzione o consigli ancora in inglese")
    return dati, problemi


def translate_exercises(db: Session, exercises: list[Exercise]) -> int:
    """Traduce gli esercizi ancora senza nome italiano. Restituisce quanti.

    Ogni blocco ha due tentativi: il secondo solo per le voci che non passano
    i controlli (parole inglesi nel nome, esecuzione assente o in inglese), con
    l'indicazione precisa di cosa correggere. Se anche il secondo fallisce, un
    testo non valido non viene salvato: si mostra l'originale.

    Si ferma al primo errore dell'LLM (quota, rete): gli esercizi rimasti
    verranno tradotti alla prossima occasione.
    """
    from app.config import get_settings
    from app.services import llm_client

    modello = get_settings().gemini_translation_model
    da_tradurre = [ex for ex in exercises if not ex.name_it]
    tradotti = 0

    for inizio in range(0, len(da_tradurre), EXERCISE_BATCH_SIZE):
        blocco = da_tradurre[inizio : inizio + EXERCISE_BATCH_SIZE]
        per_id = {ex.id: ex for ex in blocco}
        risultati: dict[int, dict] = {}
        correzioni: dict[int, list[str]] = {}

        for tentativo in range(2):
            mancanti = [ex for ex in blocco if ex.id not in risultati]
            if not mancanti:
                break
            payload = [_exercise_payload(ex, correzioni.get(ex.id)) for ex in mancanti]
            try:
                risposta = llm_client.generate_structured(
                    _EXERCISE_PROMPT.format(
                        termini=", ".join(ALLOWED_GYM_TERMS),
                        esercizi=json.dumps(payload, ensure_ascii=False),
                    ),
                    _EXERCISE_SCHEMA,
                    temperature=0.2,
                    timeout=150.0,
                    model=modello,
                    purpose="translate_exercises",
                )
            except (llm_client.LLMNotConfigured, llm_client.LLMError) as e:
                logger.info("Traduzione esercizi interrotta (%s)", e)
                return tradotti

            ultimo = tentativo == 1
            for voce in risposta.get("esercizi") or []:
                if not isinstance(voce, dict):
                    continue
                ex = per_id.get(voce.get("id"))
                if ex is None or ex.id in risultati:
                    continue
                dati, problemi = _check_translation(voce)
                if problemi and not ultimo:
                    correzioni[ex.id] = problemi
                    continue
                if problemi:
                    logger.warning("Traduzione imperfetta per %r: %s", ex.name, "; ".join(problemi))
                    if any("esecuzione" in p for p in problemi):
                        dati["esecuzione"], dati["consigli"] = [], []
                if dati["nome"]:
                    risultati[ex.id] = dati

        for ex_id, dati in risultati.items():
            ex = per_id[ex_id]
            ex.name_it = dati["nome"][:255]
            ex.instructions_it = dati["esecuzione"] or None
            ex.tips_it = dati["consigli"] or None
            ex.focus_it = dati["focus"] or None
            tradotti += 1
        db.commit()

    return tradotti


def translate_library(
    *, source: str | None = None, max_failures: int = 4, pause_seconds: float = 4.0
) -> int:
    """Traduce la libreria esercizi, un blocco alla volta.

    Senza `source` traduce tutto il catalogo visibile (fonti del catalogo,
    senza doppioni), prima gli esercizi di base. Pensata per girare in
    background o da riga di comando: apre una propria sessione, fa una pausa
    fra i blocchi per restare nei limiti del piano gratuito di Gemini e si
    ferma dopo alcuni errori consecutivi (quota esaurita): rieseguendola
    riprende da dove si era interrotta.
    """
    import time

    from app.database import SessionLocal
    from app.services.exercise_library import CATALOG_SOURCES

    filtro_fonte = (
        Exercise.source == source
        if source
        else Exercise.source.in_(CATALOG_SOURCES)
        & Exercise.duplicate_of_id.is_(None)
        & Exercise.in_catalog.is_(True)
    )
    totale = fallimenti = 0
    with SessionLocal() as db:
        while True:
            blocco = list(
                db.scalars(
                    select(Exercise)
                    .where(filtro_fonte, Exercise.name_it.is_(None))
                    .order_by(Exercise.priority, Exercise.id)
                    .limit(EXERCISE_BATCH_SIZE)
                )
            )
            if not blocco:
                break
            fatti = translate_exercises(db, blocco)
            if fatti == 0:
                fallimenti += 1
                if fallimenti >= max_failures:
                    logger.warning("Traduzione libreria sospesa dopo %d errori", fallimenti)
                    break
                time.sleep(pause_seconds * 5 * fallimenti)
                continue
            fallimenti = 0
            totale += fatti
            logger.info("Tradotti %d esercizi finora", totale)
            time.sleep(pause_seconds)
    return totale


def ensure_translated(db: Session, exercises: list[Exercise]) -> None:
    """Traduce al volo ciò che manca, senza mai far fallire la richiesta."""
    mancanti = [ex for ex in exercises if ex is not None and not ex.name_it and ex.instructions]
    if not mancanti:
        return
    try:
        translate_exercises(db, mancanti)
    except Exception as e:  # la traduzione non deve mai bloccare la scheda
        logger.warning("Traduzione esercizi non riuscita: %s", e)
        db.rollback()


# --- Ricette -------------------------------------------------------------------

_RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "nome": {"type": "string"},
        "ingredienti": {"type": "array", "items": {"type": "string"}},
        "preparazione": {"type": "string"},
        "categoria": {"type": "string"},
        "cucina": {"type": "string"},
    },
    "required": ["nome", "ingredienti", "preparazione"],
}

_RECIPE_PROMPT = """Traduci in italiano questa ricetta.

REGOLE VINCOLANTI
- Traduci fedelmente. Non aggiungere, togliere o modificare ingredienti,
  quantità, tempi o temperature. Le quantità restano quelle scritte
  (puoi tradurre l'unità: "cup" -> "tazza", "tbsp" -> "cucchiaio").
- "ingredienti": una voce per ogni riga ricevuta, nello stesso ordine.
- "nome": il nome del piatto in italiano; se è un nome proprio straniero
  (es. "Pollo en Salsa") lascialo com'è.
- "preparazione": i passaggi, separati da un a capo.
- "categoria": traduci la categoria indicata (es. "Chicken" -> "Pollo").
- "cucina": l'aggettivo italiano della cucina indicata, minuscolo
  (es. "French" o "France" -> "francese"); vuoto se non è indicata.

RICETTA
Nome: {nome}
Categoria: {categoria}
Cucina: {cucina}
Ingredienti:
{ingredienti}
Preparazione:
{preparazione}
"""


def _translate_recipe_call(recipe: dict) -> dict | None:
    from app.services import llm_client

    try:
        risposta = llm_client.generate_structured(
            _RECIPE_PROMPT.format(
                nome=recipe["name"],
                categoria=recipe.get("category") or "",
                cucina=recipe.get("area") or "",
                ingredienti="\n".join(recipe["ingredients"]),
                preparazione=recipe.get("instructions") or "",
            ),
            _RECIPE_SCHEMA,
            temperature=0.1,
            timeout=60.0,
            purpose="translate_recipes",
        )
    except (llm_client.LLMNotConfigured, llm_client.LLMError) as e:
        logger.info("Traduzione ricetta non disponibile (%s)", e)
        return None

    ingredienti = _clean_list(risposta.get("ingredienti"), limit=40)
    if len(ingredienti) != len(recipe["ingredients"]):
        # Righe perse o aggiunte: gli ingredienti tradotti non sono affidabili.
        ingredienti = list(recipe["ingredients"])
    return {
        "name": (risposta.get("nome") or recipe["name"]).strip(),
        "category": (risposta.get("categoria") or recipe.get("category") or "").strip() or None,
        "area": (risposta.get("cucina") or "").strip().lower() or None,
        "ingredients": ingredienti,
        "instructions": (risposta.get("preparazione") or recipe.get("instructions") or "").strip(),
    }


def translate_recipes(db: Session, recipes: list[dict]) -> list[dict]:
    """Traduce più ricette in parallelo, usando la cache per `meal_id`.

    Ogni dizionario ha `meal_id`, `name`, `category`, `ingredients`,
    `instructions`; ne viene restituita la versione italiana (o l'originale
    se la traduzione non è disponibile).
    """
    risultati: dict[str, dict] = {}
    mancanti: list[dict] = []
    for r in recipes:
        cached = cache_get(db, "recipe_it", r["meal_id"])
        if cached:
            risultati[r["meal_id"]] = cached
        else:
            mancanti.append(r)

    if mancanti:
        with ThreadPoolExecutor(max_workers=4) as pool:
            tradotte = list(pool.map(_translate_recipe_call, mancanti))
        for originale, tradotta in zip(mancanti, tradotte):
            if tradotta:
                cache_put(db, "recipe_it", originale["meal_id"], tradotta)
                risultati[originale["meal_id"]] = tradotta

    return [{**r, **risultati.get(r["meal_id"], {})} for r in recipes]


# --- Nomi degli alimenti ---------------------------------------------------------

_FOOD_KIND = "food_it"

_FOOD_SCHEMA = {
    "type": "object",
    "properties": {
        "alimenti": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "nome": {"type": "string"}},
                "required": ["id", "nome"],
            },
        }
    },
    "required": ["alimenti"],
}

_FOOD_PROMPT = """Traduci in italiano i nomi di questi alimenti, presi da un
database nutrizionale.

REGOLE VINCOLANTI
- Mantieni ogni informazione che distingue l'alimento: crudo o cotto, parte
  (petto, coscia), con o senza pelle, percentuale di grassi, marca.
- Puoi togliere le specificazioni tecniche irrilevanti per chi mangia
  ("broilers or fryers", "NFS"). Esempio:
  "Chicken, broilers or fryers, breast, skinless, boneless, meat only, raw"
  -> "Petto di pollo senza pelle, crudo".
- Nomi già in italiano e nomi di marchi restano invariati.
- Restituisci lo stesso "id" ricevuto.

ALIMENTI
{alimenti}
"""


def cached_food_names(db: Session, ingredient_ids: list[int]) -> dict[int, str]:
    """Nomi italiani già salvati, con una sola query."""
    if not ingredient_ids:
        return {}
    righe = db.scalars(
        select(LlmCache).where(
            LlmCache.kind == _FOOD_KIND,
            LlmCache.key.in_([str(i) for i in ingredient_ids]),
        )
    )
    return {int(r.key): r.payload.get("nome") for r in righe if r.payload.get("nome")}


def translate_food_names(db: Session, ingredients: list) -> dict[int, str]:
    """Nomi italiani degli alimenti, traducendo in un'unica chiamata quelli
    non ancora in cache. In caso di errore restituisce ciò che ha."""
    from app.services import llm_client

    ingredients = [i for i in ingredients if i is not None]
    nomi = cached_food_names(db, [i.id for i in ingredients])
    mancanti = [i for i in ingredients if i.id not in nomi][:25]
    if not mancanti:
        return nomi

    payload = [{"id": i.id, "nome": i.name} for i in mancanti]
    try:
        risposta = llm_client.generate_structured(
            _FOOD_PROMPT.format(alimenti=json.dumps(payload, ensure_ascii=False)),
            _FOOD_SCHEMA,
            temperature=0.0,
            timeout=30.0,
            purpose="translate_food_names",
        )
    except (llm_client.LLMNotConfigured, llm_client.LLMError) as e:
        logger.info("Traduzione nomi alimenti non disponibile (%s)", e)
        return nomi

    validi = {i.id for i in mancanti}
    for voce in risposta.get("alimenti") or []:
        if not isinstance(voce, dict):
            continue
        nome = str(voce.get("nome") or "").strip()[:300]
        if voce.get("id") in validi and nome:
            nomi[voce["id"]] = nome
            db.add(LlmCache(kind=_FOOD_KIND, key=str(voce["id"]), payload={"nome": nome}))
            validi.discard(voce["id"])
    try:
        db.commit()
    except Exception:  # una traduzione concorrente dello stesso alimento
        db.rollback()
    return nomi


# --- Ricerca: dall'italiano all'inglese ------------------------------------------

# Le fonti di ricette cercano in inglese. I termini più comuni si traducono
# senza LLM: la ricerca è istantanea e non dipende dalla quota.
FOOD_TERMS_IT_EN = {
    "pollo": "chicken", "petto": "breast", "tacchino": "turkey", "manzo": "beef",
    "vitello": "veal", "maiale": "pork", "agnello": "lamb", "salmone": "salmon",
    "tonno": "tuna", "merluzzo": "cod", "pesce": "fish", "gamberi": "prawns",
    "gamberetti": "shrimp", "uova": "egg", "uovo": "egg", "riso": "rice",
    "pasta": "pasta", "spaghetti": "spaghetti", "patate": "potato", "patata": "potato",
    "funghi": "mushroom", "lenticchie": "lentil", "ceci": "chickpea",
    "fagioli": "beans", "tofu": "tofu", "avena": "oat", "formaggio": "cheese",
    "zuppa": "soup", "insalata": "salad", "verdure": "vegetable", "spinaci": "spinach",
    "broccoli": "broccoli", "zucchine": "zucchini", "melanzane": "aubergine",
    "pomodoro": "tomato", "pomodori": "tomato", "torta": "cake", "pane": "bread",
    "curry": "curry", "pizza": "pizza", "lasagne": "lasagne", "salsiccia": "sausage",
    "prosciutto": "ham", "anatra": "duck", "cozze": "mussels", "vegano": "vegan",
    "vegetariano": "vegetarian", "dolce": "dessert", "colazione": "breakfast",
}

_STOPWORDS_IT = {"di", "con", "al", "alla", "allo", "ai", "e", "il", "la", "le", "lo", "i", "gli", "in"}

_QUERY_SCHEMA = {
    "type": "object",
    "properties": {"inglese": {"type": "string"}},
    "required": ["inglese"],
}


def query_to_english(db: Session, query: str, *, allow_llm: bool = True) -> str:
    """Traduce una ricerca di cibo in inglese, per le fonti che non capiscono
    l'italiano. Restituisce la query originale se non riesce a tradurla.

    Con `allow_llm=False` usa solo il dizionario, lasciando invariate le
    parole che non conosce: è la modalità della ricerca nel diario, che deve
    restare istantanea (e "chicken breast" deve restare "chicken breast").
    """
    from app.services import llm_client

    testo = (query or "").strip().lower()
    if not testo:
        return ""
    parole = [p for p in re.findall(r"[a-zàèéìòù]+", testo) if p not in _STOPWORDS_IT]
    conosciute = [p in FOOD_TERMS_IT_EN for p in parole]
    if parole and (all(conosciute) or (not allow_llm and any(conosciute))):
        tradotte = [FOOD_TERMS_IT_EN.get(p, p) for p in parole]
        # "petto di pollo" -> "chicken breast": il nome dell'alimento va prima.
        if tradotte[0] == "breast" and len(tradotte) > 1:
            tradotte = tradotte[1:] + ["breast"]
        return " ".join(dict.fromkeys(tradotte))
    if not allow_llm:
        return testo

    cached = cache_get(db, "query_en", testo)
    if cached:
        return cached.get("inglese") or testo

    try:
        risposta = llm_client.generate_structured(
            "Traduci in inglese questa ricerca di cibo o di un piatto, con le "
            "parole che userebbe un database di ricette in inglese. Solo la "
            f"traduzione, niente altro.\nRicerca: {testo}",
            _QUERY_SCHEMA,
            temperature=0.0,
            timeout=20.0,
            purpose="query_to_english",
        )
    except (llm_client.LLMNotConfigured, llm_client.LLMError):
        return testo

    inglese = (risposta.get("inglese") or "").strip().lower()[:80]
    if not inglese:
        return testo
    cache_put(db, "query_en", testo, {"inglese": inglese})
    return inglese
