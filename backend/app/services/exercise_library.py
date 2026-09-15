"""Catalogo esercizi da free-exercise-db, con animazione dell'esecuzione.

Perché questa fonte si affianca a wger (verificato direttamente, 09/2026):

  - **free-exercise-db** (github.com/yuhonas/free-exercise-db) contiene 873
    esercizi, e 873 di questi hanno **due fotogrammi** — posizione iniziale e
    finale — più le istruzioni passo passo, il muscolo primario, i secondari,
    l'attrezzatura e la meccanica (multi-articolare/isolamento). Licenza
    *The Unlicense*: pubblico dominio, riutilizzabile senza vincoli.
  - **wger** espone 78 video in tutto, in formato HEVC da 30-50 MB: Chrome
    non li riproduce, quindi non sono utilizzabili in un'interfaccia web. Le
    descrizioni e le immagini mancano per buona parte del catalogo.

Alternando i due fotogrammi si ottiene un'animazione del movimento: non è un
video, ma mostra da dove si parte e dove si arriva, che è ciò che serve per
capire l'esecuzione. L'interfaccia lo dichiara come tale.

Gli esercizi wger restano nel database: le schede già salvate li
referenziano. Quando questa libreria è importata, però, generatore,
alternative e preferenze attingono solo da qui, per non proporre lo stesso
esercizio due volte con due nomi diversi.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import and_, exists, select, true
from sqlalchemy.orm import Session

from app.models import Exercise

logger = logging.getLogger("exercise_library")

SOURCE = "free_exercise_db"
DATASET_URL = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
)
IMAGE_BASE_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"

# Solo le categorie da sala pesi. Stretching, pliometria, cardio, strongman e
# sollevamento olimpico non servono a costruire una scheda di ipertrofia o
# forza, e i movimenti olimpici richiedono una tecnica da apprendere con un
# allenatore, non da un'animazione.
INCLUDED_CATEGORIES = frozenset({"strength", "powerlifting"})

# Muscoli del dataset -> gruppi usati dal generatore (gli stessi nomi di wger).
# "middle back" confluisce nel dorso: rematori e pulley allenano gli stessi
# distretti che l'utente chiama "dorso".
MUSCLE_MAP = {
    "abdominals": "Abs",
    "abductors": "Glutes",
    "biceps": "Biceps",
    "calves": "Calves",
    "chest": "Chest",
    "glutes": "Glutes",
    "hamstrings": "Hamstrings",
    "lats": "Lats",
    "middle back": "Lats",
    "quadriceps": "Quads",
    "shoulders": "Shoulders",
    "traps": "Trapezius",
    "triceps": "Triceps",
}

# Muscoli che compaiono solo come secondari: si mostrano, ma non sono gruppi
# per cui il generatore programma esercizi dedicati.
SECONDARY_ONLY = {
    "forearms": "Forearms",
    "lower back": "Lower back",
    "adductors": "Adductors",
    "neck": "Neck",
}

# Stesso valore usato da wger e dal generatore per il corpo libero.
BODYWEIGHT = "none (bodyweight exercise)"

# Gli esercizi "di base" di ogni distretto, in ordine di priorità.
#
# Non è una classifica di efficacia — `exercise_choice_and_focus.md` ricorda
# che a parità di muscolo allenato conta l'aderenza. Serve a evitare il
# problema già visto con wger: senza un criterio, il generatore sceglieva
# esercizi marginali ("Alternating Renegade Row") al posto di quelli che si
# trovano in qualsiasi palestra. Gli id sono verificati sul dataset.
STAPLES: dict[str, list[str]] = {
    "Chest": [
        "Barbell_Bench_Press_-_Medium_Grip", "Leverage_Chest_Press",
        "Dumbbell_Bench_Press", "Incline_Dumbbell_Press", "Butterfly",
        "Cable_Crossover", "Machine_Bench_Press",
        "Barbell_Incline_Bench_Press_-_Medium_Grip", "Dumbbell_Flyes",
        "Incline_Cable_Flye", "Dips_-_Chest_Version", "Pushups",
    ],
    "Lats": [
        "Wide-Grip_Lat_Pulldown", "Seated_Cable_Rows", "Pullups",
        "One-Arm_Dumbbell_Row", "Bent_Over_Barbell_Row", "Straight-Arm_Pulldown",
        "Close-Grip_Front_Lat_Pulldown", "T-Bar_Row_with_Handle", "Leverage_High_Row",
        "Chin-Up", "V-Bar_Pulldown", "Bent_Over_Two-Dumbbell_Row",
    ],
    "Shoulders": [
        "Dumbbell_Shoulder_Press", "Side_Lateral_Raise", "Leverage_Shoulder_Press",
        "Cable_Seated_Lateral_Raise", "Reverse_Machine_Flyes", "Face_Pull",
        "Machine_Shoulder_Military_Press", "Standing_Military_Press",
        "Seated_Bent-Over_Rear_Delt_Raise", "Arnold_Dumbbell_Press",
    ],
    "Biceps": [
        "Barbell_Curl", "Alternate_Incline_Dumbbell_Curl", "Hammer_Curls",
        "Preacher_Curl", "Dumbbell_Bicep_Curl", "Standing_Biceps_Cable_Curl",
        "EZ-Bar_Curl", "Machine_Bicep_Curl", "Cable_Preacher_Curl",
        "Concentration_Curls",
    ],
    "Triceps": [
        "Triceps_Pushdown_-_Rope_Attachment", "Close-Grip_Barbell_Bench_Press",
        "Cable_Rope_Overhead_Triceps_Extension", "Triceps_Pushdown",
        "EZ-Bar_Skullcrusher", "Dips_-_Triceps_Version", "Machine_Triceps_Extension",
        "Dumbbell_One-Arm_Triceps_Extension",
    ],
    "Quads": [
        "Barbell_Squat", "Leg_Press", "Leg_Extensions", "Hack_Squat",
        "Split_Squat_with_Dumbbells", "Goblet_Squat", "Smith_Machine_Squat",
        "Dumbbell_Lunges", "Front_Barbell_Squat",
    ],
    "Hamstrings": [
        "Romanian_Deadlift", "Lying_Leg_Curls", "Seated_Leg_Curl",
        "Stiff-Legged_Dumbbell_Deadlift", "Standing_Leg_Curl", "Glute_Ham_Raise",
    ],
    "Glutes": [
        "Barbell_Hip_Thrust", "Barbell_Glute_Bridge", "One-Legged_Cable_Kickback",
        "Thigh_Abductor", "Glute_Kickback", "Single_Leg_Glute_Bridge",
    ],
    "Calves": [
        "Standing_Calf_Raises", "Seated_Calf_Raise",
        "Calf_Press_On_The_Leg_Press_Machine", "Smith_Machine_Calf_Raise",
        "Standing_Barbell_Calf_Raise",
    ],
    # Senza l'ab roller, che è l'unico "multi-articolare" del gruppo e come
    # tale veniva scelto per primo anche per chi inizia, e senza il plank:
    # è un esercizio a tempo, e una prescrizione in ripetizioni non ha senso.
    "Abs": [
        "Cable_Crunch", "Hanging_Leg_Raise", "Ab_Crunch_Machine",
        "Crunches", "Flat_Bench_Lying_Leg_Raise",
    ],
    "Trapezius": ["Dumbbell_Shrug", "Barbell_Shrug", "Leverage_Shrug", "Cable_Shrugs"],
}

# Priorità di tutto ciò che non è fra gli esercizi di base: dopo di loro.
DEFAULT_PRIORITY = 100

_STAPLE_RANK = {
    external_id: rank for ids in STAPLES.values() for rank, external_id in enumerate(ids)
}


# --- Everkinetic: disegni con un unico stile -------------------------------------
#
# Verificato il 13/09/2026 su github.com/everkinetic/data: licenza CC BY-SA
# 4.0, 289 esercizi con due disegni a tratto nello stesso stile (posizione di
# partenza e di arrivo) e i passaggi dell'esecuzione. È la fonte scelta per la
# coerenza visiva: free-exercise-db ha foto reali, wger mescola foto e disegni
# di stili diversi. Limite noto: il dataset non contiene l'hip thrust.

SOURCE_EVERKINETIC = "everkinetic"
EVERKINETIC_DATASET_URL = (
    "https://raw.githubusercontent.com/everkinetic/data/master/dist/exercises.json"
)
EVERKINETIC_IMAGE_BASE_URL = "https://raw.githubusercontent.com/everkinetic/data/master/dist/"

EVERKINETIC_MUSCLES = {
    "pectoralis major": "Chest",
    "latissimus dorsi": "Lats",
    "deltoid": "Shoulders",
    "biceps brachii": "Biceps",
    "triceps brachii": "Triceps",
    "quadriceps": "Quads",
    "ischiocrural muscles": "Hamstrings",
    "glutaeus maximus": "Glutes",
    "gastrocnemius": "Calves",
    "soleus": "Calves",
    "abdominals": "Abs",
    "obliques": "Abs",
    "trapezius": "Trapezius",
    "erector spinae": "Lower back",
}

# Dove il muscolo principale del dataset è impreciso o poco utile alla scheda.
EVERKINETIC_PRIMARY_OVERRIDE = {
    "0049": "Triceps",                                   # panca presa stretta
    "0086": "Lats",                                      # rematore a corpo libero
    "0090": "Lats", "0091": "Lats",                      # trazioni presa stretta/larga
    "0094": "Shoulders",                                 # tirate con elastico
    "0041": "Trapezius",                                 # scrollate al multipower
    "0114": "Quads", "0115": "Quads", "0121": "Quads",   # affondi
    "0156": "Glutes",                                    # abductor machine
    "0135": "Adductors", "0157": "Adductors",            # adductor: fuori scheda
    "0099": "Hamstrings", "0100": "Hamstrings", "0107": "Hamstrings",  # stacchi
    "0101": "Hamstrings", "0102": "Hamstrings",          # good morning
}

# Esclusi: esercizi a tempo (plank, isometrie del collo), mobilità, equilibrio
# su attrezzi instabili e combinazioni di due esercizi in uno ("curl in
# affondo"), che non servono a una scheda da sala pesi.
EVERKINETIC_EXCLUDED = frozenset({
    "0001", "0002", "0019", "0027", "0069", "0072", "0076", "0098", "0113",
    "0116", "0140", "0148", "0150", "0208", "0255", "0256", "0258", "0259",
    "0260", "0262", "0263", "0264", "0265", "0266", "0267", "0268", "0269",
    "0270", "0271", "0277", "0290", "0295", "0296",
})

# Attrezzatura del dataset -> nomi usati nel resto dell'app. `None` = non è un
# attrezzo a sé (corpo libero, accessori dei cavi).
EVERKINETIC_EQUIPMENT = {
    "body": None, "wide bar": None, "v-bar": None,
    "dumbbells": "dumbbell", "dumbbell": "dumbbell", "barbell": "barbell",
    "cable": "cable", "machine": "machine", "machine: butterfly": "machine",
    "machine: bench press": "machine", "chest machine": "machine",
    "machine: chest": "machine", "flat bench": "bench", "bench": "bench",
    "bench: hyperextension": "bench", "bench: incline": "incline bench",
    "bench: decline": "decline bench", "smith machine": "smith machine",
    "exercise band": "bands", "bar": "pull-up bar", "pull-up bar": "pull-up bar",
    "exercise ball": "exercise ball", "stability ball": "exercise ball",
    "swiss ball": "exercise ball", "weight plate": "weight plate",
    "weight": "weight plate", "t-bar machine": "t-bar machine",
    "parallel bars": "parallel bars", "towel": "towel",
}

# Esercizi di base per gruppo, in ordine di priorità (id del dataset).
EVERKINETIC_STAPLES: dict[str, list[str]] = {
    "Chest": ["0042", "0084", "0055", "0061", "0047", "0048", "0043", "0066", "0056", "0060", "0054", "0077"],
    "Lats": ["0097", "0025", "0087", "0298", "0029", "0096", "0092", "0089", "0093", "0026"],
    "Shoulders": ["0012", "0018", "0003", "0035", "0004", "0006", "0033", "0032", "0015"],
    "Biceps": ["0211", "0214", "0227", "0239", "0224", "0212", "0226", "0236", "0216", "0220"],
    "Triceps": ["0206", "0049", "0205", "0183", "0172", "0210", "0198", "0204", "0201"],
    "Quads": ["0122", "0127", "0142", "0123", "0115", "0137", "0124", "0138"],
    "Hamstrings": ["0118", "0117", "0119", "0099", "0120", "0101", "0107"],
    "Glutes": ["0109", "0112", "0156"],
    "Calves": ["0282", "0279", "0273", "0281", "0283"],
    "Abs": ["0288", "0291", "0021", "0292", "0287", "0284"],
    "Trapezius": ["0005", "0030", "0009", "0041"],
}

_EK_RANK = {
    external_id: rank
    for ids in EVERKINETIC_STAPLES.values()
    for rank, external_id in enumerate(ids)
}

# Gruppi per cui il generatore programma esercizi.
_PLAN_GROUPS = frozenset(MUSCLE_MAP.values())

# Il campo "type" del dataset è inaffidabile (trazioni e distensioni sono
# marcate "isolation"), e da questa classificazione dipendono recuperi e
# range di ripetizioni: si ricava dal nome del movimento.
_COMPOUND_WORDS = (
    "press", "squat", "row", "pull up", "pull ups", "chin", "pull down", "dip",
    "lunge", "dead lift", "step up", "push up", "good morning",
)
_ISOLATION_WORDS = (
    "fly", "raise", "pullover", "rotation", "extension", "curl", "kickback",
    "shrug", "crossover",
)
_SINGLE_JOINT_GROUPS = frozenset({"Biceps", "Calves", "Abs", "Trapezius"})


def everkinetic_is_compound(title: str, primary: str) -> bool:
    t = title.lower()
    if primary in _SINGLE_JOINT_GROUPS:
        return False
    if primary == "Triceps":
        return (
            t.startswith("bench press") or t.startswith("jm press")
            or "dips" in t or "pushup" in t or "push up" in t
        )
    if any(w in t for w in _ISOLATION_WORDS):
        return False
    return any(w in t for w in _COMPOUND_WORDS)


def parse_everkinetic_entry(raw: dict) -> dict | None:
    """Converte una voce di Everkinetic nei campi di `Exercise`."""
    external_id = str(raw.get("id") or "")
    if not external_id or external_id in EVERKINETIC_EXCLUDED or raw.get("type") == "isometric":
        return None
    immagini = [f"{EVERKINETIC_IMAGE_BASE_URL}{path}" for path in raw.get("svg") or []]
    if len(immagini) < 2:
        return None

    primari = raw.get("primary") or []
    primario = EVERKINETIC_PRIMARY_OVERRIDE.get(external_id) or (
        EVERKINETIC_MUSCLES.get(primari[0]) if primari else None
    )
    if primario not in _PLAN_GROUPS:
        return None

    secondari: list[str] = []
    for nome in [*primari[1:], *(raw.get("secondary") or [])]:
        muscolo = EVERKINETIC_MUSCLES.get(nome)
        if muscolo and muscolo != primario and muscolo not in secondari:
            secondari.append(muscolo)

    attrezzi: list[str] = []
    for voce in raw.get("equipment") or []:
        chiave = voce.strip().lower()
        valore = EVERKINETIC_EQUIPMENT.get(chiave, chiave)
        if valore and valore not in attrezzi:
            attrezzi.append(valore)

    passi = [s.strip() for s in raw.get("steps") or [] if s and s.strip()]
    consigli = [s.strip() for s in raw.get("tips") or [] if s and s.strip()]
    titolo = (raw.get("title") or raw.get("name") or external_id).strip()

    return dict(
        external_id=external_id,
        name=titolo,
        primary_muscle=primario,
        secondary_muscles=", ".join(secondari) or None,
        equipment=", ".join(attrezzi) or BODYWEIGHT,
        category="strength",
        description="\n".join(passi) or None,
        instructions=passi or None,
        tips=consigli or None,
        image_url=immagini[0],
        demo_images=immagini,
        is_compound=everkinetic_is_compound(titolo, primario),
        level=None,
        priority=_EK_RANK.get(external_id, DEFAULT_PRIORITY),
    )


class LibraryError(RuntimeError):
    """Download o lettura del dataset non riusciti."""


def fetch_dataset(url: str = DATASET_URL, *, timeout: float = 60.0) -> list[dict]:
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise LibraryError(f"Download del catalogo esercizi non riuscito ({url}): {e}") from e
    if not isinstance(data, list):
        raise LibraryError(f"Formato inatteso del catalogo esercizi ({url})")
    return data


def _map_muscles(names: list[str] | None) -> list[str]:
    risultato: list[str] = []
    for nome in names or []:
        mappato = MUSCLE_MAP.get(nome) or SECONDARY_ONLY.get(nome)
        if mappato and mappato not in risultato:
            risultato.append(mappato)
    return risultato


def parse_entry(raw: dict) -> dict | None:
    """Converte una voce del dataset nei campi di `Exercise`.

    Restituisce `None` per ciò che non è utilizzabile in una scheda: categoria
    fuori dalla sala pesi, nessun fotogramma o muscolo primario non mappabile.
    """
    if raw.get("category") not in INCLUDED_CATEGORIES:
        return None
    immagini = [f"{IMAGE_BASE_URL}{path}" for path in raw.get("images") or []]
    if not immagini:
        return None
    primari = [MUSCLE_MAP[m] for m in raw.get("primaryMuscles") or [] if m in MUSCLE_MAP]
    if not primari:
        return None

    secondari = [m for m in _map_muscles(raw.get("secondaryMuscles")) if m != primari[0]]
    istruzioni = [s.strip() for s in raw.get("instructions") or [] if s and s.strip()]
    external_id = str(raw.get("id"))
    equipment = raw.get("equipment")

    return dict(
        external_id=external_id,
        name=(raw.get("name") or external_id).strip(),
        primary_muscle=primari[0],
        secondary_muscles=", ".join(secondari) or None,
        equipment=BODYWEIGHT if equipment in (None, "body only") else equipment,
        category=raw.get("category"),
        description="\n".join(istruzioni) or None,
        instructions=istruzioni or None,
        image_url=immagini[0],
        demo_images=immagini,
        is_compound=raw.get("mechanic") == "compound",
        level=raw.get("level"),
        priority=_STAPLE_RANK.get(external_id, DEFAULT_PRIORITY),
    )


_SOURCES = {
    SOURCE: (DATASET_URL, parse_entry),
    SOURCE_EVERKINETIC: (EVERKINETIC_DATASET_URL, parse_everkinetic_entry),
}


def sync_library(db: Session, dataset: list[dict] | None = None, *, source: str = SOURCE):
    """Importa o aggiorna il catalogo di una fonte. Idempotente.

    Le traduzioni già salvate (`name_it`, `instructions_it`, `focus_it`,
    `tips_it`) non vengono toccate: rieseguire l'import non deve costare nuove
    chiamate LLM.
    """
    from app.services.catalog_sync import SyncResult

    url, parser = _SOURCES[source]
    dataset = fetch_dataset(url) if dataset is None else dataset
    existing = {
        ex.external_id: ex
        for ex in db.scalars(select(Exercise).where(Exercise.source == source))
    }

    created = updated = skipped = 0
    for raw in dataset:
        campi = parser(raw)
        if campi is None:
            skipped += 1
            continue
        corrente = existing.get(campi["external_id"])
        if corrente is None:
            db.add(Exercise(source=source, **campi))
            created += 1
        else:
            for chiave, valore in campi.items():
                setattr(corrente, chiave, valore)
            updated += 1

    db.commit()
    logger.info(
        "Libreria esercizi: %d voci, %d nuove, %d aggiornate, %d scartate",
        len(dataset), created, updated, skipped,
    )
    return SyncResult(
        fetched=len(dataset), created=created, updated=updated, skipped_no_muscle=skipped
    )


def has_library(db: Session, source: str = SOURCE) -> bool:
    return bool(db.scalar(select(exists().where(Exercise.source == source))))


# Dalla fonte preferita alla meno preferita: i disegni coerenti prima delle foto.
SOURCE_PRECEDENCE = (SOURCE_EVERKINETIC, SOURCE)


def active_source(db: Session) -> str | None:
    for sorgente in SOURCE_PRECEDENCE:
        if has_library(db, sorgente):
            return sorgente
    return None


def catalog_condition(db: Session):
    """Filtro SQL sul catalogo da cui scegliere gli esercizi.

    Si usa una sola fonte, la preferita fra quelle importate, così immagini e
    nomi restano coerenti in tutta la scheda; senza librerie importate (per
    esempio nei test) tutto il catalogo disponibile.
    """
    sorgente = active_source(db)
    if not sorgente:
        return true()
    # Finché la traduzione non è completa (la quota gratuita di Gemini è
    # giornaliera), gli esercizi ancora in inglese restano fuori: nella scheda
    # e nelle alternative non deve comparire un nome non tradotto.
    tradotti = db.scalar(
        select(exists().where(Exercise.source == sorgente, Exercise.name_it.is_not(None)))
    )
    if tradotti:
        return and_(Exercise.source == sorgente, Exercise.name_it.is_not(None))
    return Exercise.source == sorgente


def catalog_order():
    """Ordinamento di "canonicità" condiviso da generatore, alternative e
    ricerca: prima gli esercizi di base, poi quelli con animazione,
    immagine e descrizione."""
    return (
        Exercise.priority,
        Exercise.demo_images.is_(None),
        Exercise.image_url.is_(None),
        Exercise.description.is_(None),
        Exercise.name,
    )


# Varianti che allenano il muscolo in allungamento, preferite a parità di
# gradimento, gruppo muscolare e tipologia (`biomechanics_technique.md`).
# Solo dove un confronto diretto fra esercizi lo sostiene: leg curl da seduti
# contro da sdraiati (Maeo 2021) ed estensioni dei tricipiti sopra la testa
# contro il braccio lungo il corpo (Maeo 2023). Per petto, dorsali e spalle
# mancano confronti diretti, quindi nessuna preferenza.
LENGTHENED_VARIANTS: dict[str, tuple[str, ...]] = {
    "Hamstrings": ("seated leg curl", "sitting leg curl", "seated hamstring curl"),
    "Triceps": ("overhead",),
}

# Everkinetic: il nome non sempre dice "overhead". Id verificati sui passaggi
# del dataset: busto eretto (in piedi o seduti) e braccia sopra la testa, come
# nello studio. Esclusi di proposito gli esercizi da sdraiati o su panca
# inclinata che portano il peso "dietro la testa": la spalla è a circa 90°,
# una posizione intermedia che lo studio non ha confrontato.
LENGTHENED_EVERKINETIC_IDS = frozenset({
    "0119",                                   # Seated Leg Curl
    "0173",                                   # Triceps Extension: Dumbbell (One Arm)
    "0193", "0194",                           # estensioni seduti sopra la testa
    "0198", "0200", "0201",                   # estensioni in piedi sopra la testa
})


def lengthened_rank(exercise: Exercise) -> int:
    """0 per le varianti in allungamento del muscolo primario, 1 per le altre."""
    parole = LENGTHENED_VARIANTS.get(exercise.primary_muscle or "")
    if not parole:
        return 1
    if exercise.source == SOURCE_EVERKINETIC and exercise.external_id in LENGTHENED_EVERKINETIC_IDS:
        return 0
    nome = (exercise.name or "").lower().replace("-", " ").replace("_", " ")
    return 0 if any(parola in nome for parola in parole) else 1


if __name__ == "__main__":
    # Import completo da riga di comando:
    #   python -m app.services.exercise_library
    import sys

    from app.database import SessionLocal
    from app.services import translation

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Predefinita Everkinetic; `--fedb` per il vecchio catalogo con le foto.
    sorgente = SOURCE if "--fedb" in sys.argv else SOURCE_EVERKINETIC
    with SessionLocal() as sessione:
        esito = sync_library(sessione, source=sorgente)
        print(f"Import {sorgente}: {esito.created} nuovi, {esito.updated} aggiornati, {esito.skipped_no_muscle} scartati")
    if "--no-translate" not in sys.argv:
        print(f"Tradotti in italiano: {translation.translate_library(source=sorgente)}")
