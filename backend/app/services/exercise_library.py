"""Catalogo esercizi: tre fonti aperte unite, più gli esercizi scritti a mano.

Fonti (verificate direttamente, 09/2026):

  - **Everkinetic** (github.com/everkinetic/data, CC BY-SA 4.0): disegni al
    tratto nello stesso stile, posizione di partenza e di arrivo.
  - **RepDB** (github.com/RepDB/exercise-dataset, free tier): illustrazioni
    flat a colori, partenza e arrivo. La licenza chiede un'attribuzione
    visibile ("Exercise data by RepDB (repdb.co)") e vieta di ridistribuire il
    dataset: le voci stanno solo nel database dell'app, le immagini sono lette
    dal repository ufficiale.
  - **free-exercise-db** (github.com/yuhonas/free-exercise-db, pubblico
    dominio): foto reali, partenza e arrivo.
  - **Kilo** (`manual_exercises.py`): varianti che nessuna fonte contiene.

Nessuna fonte da sola copre tutte le varianti comuni in palestra, per questo
sono unite. Lo stesso esercizio compare spesso in più fonti con nomi diversi:
i doppioni verificati a mano stanno in `app/data/exercise_duplicates.json` e se
ne tiene uno solo, preferendo i disegni alle illustrazioni e queste alle foto
(`CATALOG_SOURCES`). I doppioni restano nel database, perché schede e
preferenze salvate li referenziano, ma escono dal catalogo.

Gli esercizi wger restano nel database per le schede più vecchie e non fanno
parte del catalogo.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx
from sqlalchemy import and_, case, exists, select
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

# Esercizi a tempo o a distanza (plank, tenute, camminate con carico, slitta):
# una prescrizione in serie e ripetizioni non ha senso. Gli affondi camminati
# restano, perché si contano in ripetizioni.
TIMED_EXERCISE_PATTERN = re.compile(
    r"\b(plank|planks|hold|wall sit|carry|farmer'?s walk|lateral walk|sumo walk|"
    r"monster walk|heel-to-toe walk|backward walk|sled|isometric|bosu)\b",
    re.IGNORECASE,
)

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

# Priorità di tutto ciò che non è fra gli esercizi di base: dopo di loro.
DEFAULT_PRIORITY = 100


# --- Everkinetic: disegni con un unico stile -------------------------------------
#
# Verificato il 13/09/2026 su github.com/everkinetic/data: licenza CC BY-SA
# 4.0, 289 esercizi con due disegni a tratto nello stesso stile (posizione di
# partenza e di arrivo) e i passaggi dell'esecuzione. Limite noto: il dataset
# non contiene l'hip thrust (arriva da RepDB).

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


# --- RepDB: illustrazioni flat a colori --------------------------------------------

SOURCE_REPDB = "repdb"
REPDB_DATASET_URL = "https://raw.githubusercontent.com/RepDB/exercise-dataset/main/exercises.json"
REPDB_IMAGE_BASE_URL = "https://raw.githubusercontent.com/RepDB/exercise-dataset/main/"
REPDB_ATTRIBUTION = "Exercise data by RepDB (repdb.co)"

# Muscoli anatomici del dataset -> gruppi della scheda. Romboidi nel dorso e i
# tre fasci del deltoide nelle spalle, come fanno gli altri cataloghi.
REPDB_MUSCLES = {
    "gluteus_maximus": "Glutes", "gluteus_medius": "Glutes", "abductors": "Glutes",
    "quadriceps": "Quads", "pectoralis_major": "Chest",
    "latissimus_dorsi": "Lats", "rhomboids": "Lats",
    "anterior_deltoid": "Shoulders", "lateral_deltoid": "Shoulders",
    "posterior_deltoid": "Shoulders", "supraspinatus": "Shoulders",
    "hamstrings": "Hamstrings",
    "rectus_abdominis": "Abs", "obliques": "Abs", "transverse_abdominis": "Abs",
    "triceps_brachii": "Triceps",
    "biceps_brachii": "Biceps", "brachialis": "Biceps", "brachioradialis": "Biceps",
    "trapezius": "Trapezius", "gastrocnemius": "Calves", "soleus": "Calves",
}
REPDB_SECONDARY_ONLY = {
    "erector_spinae": "Lower back", "quadratus_lumborum": "Lower back",
    "forearm_flexors": "Forearms", "forearm_extensors": "Forearms", "forearms": "Forearms",
    "adductors": "Adductors",
}

REPDB_EQUIPMENT = {
    "dumbbell": "dumbbell", "barbell": "barbell", "kettlebell": "kettlebell",
    "cable": "cable", "lat_pulldown_machine": "cable", "pull_up_bar": "pull-up bar",
    "ez_bar": "e-z curl bar", "smith_machine": "smith machine",
    "loop_band": "bands", "resistance_band": "bands",
    "suspension_trainer": "suspension trainer", "flat_bench": "bench",
    "stability_ball": "exercise ball", "rings": "rings", "plates": "weight plate",
    "dip_station": "parallel bars", "trap_bar": "trap bar", "ab_wheel": "ab wheel",
    "slam_ball": "medicine ball",
}
_REPDB_MACHINES = frozenset({
    "leg_press", "leg_curl", "hack_squat", "leg_extension", "pec_deck",
    "glute_ham_developer",
})


def _repdb_equipment(value: str | None) -> str:
    if not value:
        return BODYWEIGHT
    if value in REPDB_EQUIPMENT:
        return REPDB_EQUIPMENT[value]
    if value in _REPDB_MACHINES or value.endswith("_machine"):
        return "machine"
    return value.replace("_", " ")


# --- Esercizi di base dell'intero catalogo ----------------------------------------
#
# Non è una classifica di efficacia — `exercise_choice_and_focus.md` ricorda
# che a parità di muscolo allenato conta l'aderenza. Serve a proporre per primi
# gli esercizi che si trovano in qualsiasi palestra. Base Everkinetic, più
# quelli che mancano (macchine, cavi, hip thrust) dalle altre fonti. Gli id sono
# verificati sui dataset; il formato è "sorgente:id".

# Esercizi di base Everkinetic che nel dataset non hanno i disegni, e quindi non
# vengono importati: al loro posto, nella stessa posizione, l'equivalente RepDB.
_EVERKINETIC_WITHOUT_DRAWINGS = {
    "0084": "repdb:chest-press-machine",       # Incline Chest Press (macchina)
    "0047": "repdb:pec-deck",                  # Butterfly Machine
    "0097": "repdb:lat-pulldown",              # Pull Down: Wide Bar (Wide Grip)
    "0298": "repdb:barbell-row",               # Bent Over Row with Barbell
    "0089": "repdb:chin-ups",                  # Chin Ups
    "0012": "repdb:dumbbell-shoulder-press",   # Dumbbell Shoulder Press
    "0003": "repdb:machine-shoulder-press",    # Seated Shoulder Press Machine
    "0006": "repdb:arnold-press",              # Arnold Press
    "0283": "repdb:dumbbell-calf-raise",       # Standing Calf Raise with Dumbbell
}
_STAPLES_BEFORE = {
    # Everkinetic non ha l'hip thrust, che per i glutei è l'esercizio di base.
    "Glutes": ["repdb:hip-thrust"],
}
_STAPLES_AFTER = {
    "Chest": ["repdb:machine-chest-fly"],
    "Lats": [
        "free_exercise_db:Leverage_Iso_Row", "free_exercise_db:Leverage_High_Row",
        "repdb:chest-supported-smith-machine-row",
    ],
    "Shoulders": [
        "repdb:cable-lateral-raise", "repdb:face-pull", "free_exercise_db:Reverse_Machine_Flyes",
    ],
    "Triceps": ["free_exercise_db:Cable_Rope_Overhead_Triceps_Extension"],
    "Glutes": ["repdb:barbell-glute-bridge", "repdb:smith-machine-hip-thrust", "repdb:glute-kickback"],
    "Abs": ["repdb:cable-crunch", "repdb:hanging-leg-raise", "repdb:machine-seated-crunch"],
}
CATALOG_STAPLES: dict[str, list[str]] = {
    gruppo: _STAPLES_BEFORE.get(gruppo, [])
    + [_EVERKINETIC_WITHOUT_DRAWINGS.get(i, f"{SOURCE_EVERKINETIC}:{i}") for i in ids]
    + _STAPLES_AFTER.get(gruppo, [])
    for gruppo, ids in EVERKINETIC_STAPLES.items()
}
_CATALOG_RANK = {
    voce: rank for voci in CATALOG_STAPLES.values() for rank, voce in enumerate(voci)
}


def staple_priority(source: str, external_id: str) -> int:
    return _CATALOG_RANK.get(f"{source}:{external_id}", DEFAULT_PRIORITY)


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
        priority=staple_priority(SOURCE_EVERKINETIC, external_id),
    )


def parse_repdb_entry(raw: dict) -> dict | None:
    """Converte una voce di RepDB nei campi di `Exercise`.

    Restituisce `None` per ciò che non serve in una scheda da sala pesi:
    stretching, cardio e olimpici, esercizi a tempo, muscolo primario che non
    è un gruppo della scheda (avambracci, adduttori).
    """
    if raw.get("category") != "strength":
        return None
    nome = (raw.get("name_en") or "").strip()
    external_id = str(raw.get("id") or "")
    if not nome or not external_id or TIMED_EXERCISE_PATTERN.search(nome):
        return None

    primari = [REPDB_MUSCLES[m] for m in raw.get("primary_muscles") or [] if m in REPDB_MUSCLES]
    if not primari:
        return None
    primario = primari[0]

    secondari: list[str] = []
    for muscolo in [*(raw.get("primary_muscles") or [])[1:], *(raw.get("secondary_muscles") or [])]:
        gruppo = REPDB_MUSCLES.get(muscolo) or REPDB_SECONDARY_ONLY.get(muscolo)
        if gruppo and gruppo != primario and gruppo not in secondari:
            secondari.append(gruppo)

    pose = (raw.get("images") or {}).get("flat") or {}
    percorsi = [pose[k] for k in ("start", "peak") if pose.get(k)] or (
        [pose["main"]] if pose.get("main") else []
    )
    immagini = [f"{REPDB_IMAGE_BASE_URL}{p}" for p in percorsi]
    if not immagini:
        return None

    passi = [s.strip() for s in raw.get("instructions_en") or [] if s and s.strip()]
    consigli = [s.strip() for s in raw.get("tips_en") or [] if s and s.strip()]

    return dict(
        external_id=external_id,
        name=nome,
        primary_muscle=primario,
        secondary_muscles=", ".join(secondari) or None,
        equipment=_repdb_equipment(raw.get("equipment")),
        category="strength",
        description="\n".join(passi) or None,
        instructions=passi or None,
        tips=consigli or None,
        image_url=immagini[0],
        demo_images=immagini,
        # Come per Everkinetic, curl, polpacci, addominali e scrollate sono
        # isolamenti anche quando il dataset li marca "compound".
        is_compound=raw.get("mechanic") == "compound" and primario not in _SINGLE_JOINT_GROUPS,
        level=raw.get("difficulty"),
        priority=staple_priority(SOURCE_REPDB, external_id),
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
    # RepDB avvolge l'elenco in un oggetto con i metadati.
    if isinstance(data, dict) and isinstance(data.get("exercises"), list):
        data = data["exercises"]
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
    """Converte una voce di free-exercise-db nei campi di `Exercise`.

    Restituisce `None` per ciò che non è utilizzabile in una scheda: categoria
    fuori dalla sala pesi, esercizio a tempo, nessun fotogramma o muscolo
    primario non mappabile.
    """
    if raw.get("category") not in INCLUDED_CATEGORIES:
        return None
    if TIMED_EXERCISE_PATTERN.search(raw.get("name") or ""):
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
        priority=staple_priority(SOURCE, external_id),
    )


_SOURCES = {
    SOURCE: (DATASET_URL, parse_entry),
    SOURCE_EVERKINETIC: (EVERKINETIC_DATASET_URL, parse_everkinetic_entry),
    SOURCE_REPDB: (REPDB_DATASET_URL, parse_repdb_entry),
}

SOURCE_MANUAL = "kilo"

# Fonti del catalogo, dalla preferita alla meno preferita quando lo stesso
# esercizio compare in più di una: i disegni (e le schede già salvate, che li
# usano) prima, poi le illustrazioni, gli esercizi scritti a mano e per ultime
# le foto.
CATALOG_SOURCES = (SOURCE_EVERKINETIC, SOURCE_REPDB, SOURCE_MANUAL, SOURCE)
_SOURCE_RANK = {sorgente: i for i, sorgente in enumerate(CATALOG_SOURCES)}

DUPLICATES_FILE = Path(__file__).resolve().parent.parent / "data" / "exercise_duplicates.json"


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
        "Libreria esercizi %s: %d voci, %d nuove, %d aggiornate, %d scartate",
        source, len(dataset), created, updated, skipped,
    )
    return SyncResult(
        fetched=len(dataset), created=created, updated=updated, skipped_no_muscle=skipped
    )


def sync_manual(db: Session):
    """Importa gli esercizi scritti a mano, testi italiani compresi."""
    from app.services.catalog_sync import SyncResult
    from app.services.manual_exercises import MANUAL_EXERCISES

    existing = {
        ex.external_id: ex
        for ex in db.scalars(select(Exercise).where(Exercise.source == SOURCE_MANUAL))
    }
    created = updated = 0
    for voce in MANUAL_EXERCISES:
        campi = dict(
            voce,
            category="strength",
            description="\n".join(voce["instructions"]),
            image_url=None,
            demo_images=None,
            level=None,
            priority=staple_priority(SOURCE_MANUAL, voce["external_id"]),
        )
        corrente = existing.get(voce["external_id"])
        if corrente is None:
            db.add(Exercise(source=SOURCE_MANUAL, **campi))
            created += 1
        else:
            for chiave, valore in campi.items():
                setattr(corrente, chiave, valore)
            updated += 1
    db.commit()
    return SyncResult(
        fetched=len(MANUAL_EXERCISES), created=created, updated=updated, skipped_no_muscle=0
    )


def load_duplicate_groups(path: Path = DUPLICATES_FILE) -> list[list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))["gruppi"]


def apply_duplicates(db: Session, groups: list[list[str]] | None = None) -> int:
    """Segna i doppioni verificati e restituisce quanti esercizi escono dal catalogo.

    Per ogni gruppo resta visibile l'esercizio della fonte preferita
    (`CATALOG_SOURCES`), a parità di fonte quello di base, poi il più vecchio.
    Le voci del file non ancora importate (o escluse, come i plank) vengono
    ignorate. Riapplicarla è sicura: ricalcola tutto da capo.
    """
    groups = load_duplicate_groups() if groups is None else groups
    righe = list(
        db.scalars(select(Exercise).where(Exercise.source.in_(CATALOG_SOURCES)))
    )
    per_chiave = {f"{ex.source}:{ex.external_id}": ex for ex in righe}

    for ex in righe:
        ex.duplicate_of_id = None

    nascosti = 0
    for gruppo in groups:
        membri = [per_chiave[k] for k in gruppo if k in per_chiave]
        if len(membri) < 2:
            continue
        principale = min(
            membri,
            key=lambda ex: (_SOURCE_RANK.get(ex.source, 99), ex.priority, ex.id),
        )
        for ex in membri:
            if ex is not principale:
                ex.duplicate_of_id = principale.id
                nascosti += 1

    db.commit()
    logger.info("Catalogo esercizi: %d doppioni nascosti", nascosti)
    return nascosti


def sync_catalog(db: Session, datasets: dict[str, list[dict]] | None = None):
    """Importa tutte le fonti, gli esercizi scritti a mano e applica i doppioni.

    Se una fonte non è raggiungibile si prosegue con le altre: il catalogo già
    importato resta valido. Fallisce solo se non si scarica nessuna fonte.
    """
    from app.services.catalog_sync import SyncResult

    fetched = created = updated = skipped = 0
    errori: list[str] = []
    for sorgente in (SOURCE_EVERKINETIC, SOURCE_REPDB, SOURCE):
        try:
            esito = sync_library(
                db, dataset=(datasets or {}).get(sorgente) if datasets else None, source=sorgente
            )
        except LibraryError as e:
            logger.warning("%s", e)
            errori.append(str(e))
            continue
        fetched += esito.fetched
        created += esito.created
        updated += esito.updated
        skipped += esito.skipped_no_muscle

    if len(errori) == 3:
        raise LibraryError("; ".join(errori))

    manuali = sync_manual(db)
    apply_duplicates(db)
    return SyncResult(
        fetched=fetched + manuali.fetched,
        created=created + manuali.created,
        updated=updated + manuali.updated,
        skipped_no_muscle=skipped,
    )


def has_library(db: Session, source: str = SOURCE) -> bool:
    return bool(db.scalar(select(exists().where(Exercise.source == source))))


def has_catalog(db: Session) -> bool:
    return bool(db.scalar(select(exists().where(Exercise.source.in_(CATALOG_SOURCES)))))


def catalog_condition(db: Session):
    """Filtro SQL sul catalogo da cui scegliere gli esercizi.

    Tutte le fonti del catalogo, senza i doppioni. Gli esercizi non ancora
    tradotti restano visibili con il nome originale: la traduzione arriva in
    background. Senza nessuna fonte importata (per esempio nei test) tutto ciò
    che c'è nel database, sempre senza doppioni.
    """
    visibili = Exercise.duplicate_of_id.is_(None)
    if not has_catalog(db):
        return visibili
    return and_(Exercise.source.in_(CATALOG_SOURCES), visibili)


def catalog_order():
    """Ordinamento di "canonicità" condiviso da generatore, alternative e
    ricerca: prima gli esercizi di base, poi quelli con animazione, a parità i
    disegni e le illustrazioni prima delle foto, poi immagine e descrizione."""
    return (
        Exercise.priority,
        Exercise.demo_images.is_(None),
        case(_SOURCE_RANK, value=Exercise.source, else_=len(CATALOG_SOURCES)),
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
    #   python -m app.services.exercise_library [--no-translate]
    import sys

    from app.database import SessionLocal
    from app.services import translation

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with SessionLocal() as sessione:
        esito = sync_catalog(sessione)
        print(f"Catalogo: {esito.created} nuovi, {esito.updated} aggiornati, {esito.skipped_no_muscle} scartati")
    if "--no-translate" not in sys.argv:
        print(f"Tradotti in italiano: {translation.translate_library()}")
