"""Generazione delle schede di allenamento.

Principio architetturale (da `knowledge_base/evidence_conduct.md`): **i
numeri non li decide l'LLM**. Serie, ripetizioni, RIR e recuperi vengono
calcolati qui, in modo deterministico, dai parametri dei file della
knowledge base. L'LLM interviene solo dopo, per spiegare la scheda in
linguaggio naturale — e se non è disponibile, la scheda resta valida, perde
solo il testo discorsivo.

Fonti dei parametri usati, con il file da cui provengono:

  - volume settimanale per gruppo muscolare  -> `training_volume.md`
  - recuperi e RIR                           -> `rest_periods_and_rir.md`
  - gate di sicurezza                        -> `screening_and_red_flags.md`
  - lavoro su equilibrio per gli over 65     -> `who_physical_activity.md`

Sulle ripetizioni, una precisazione che vale la pena tenere a mente leggendo
il codice: la letteratura (Schoenfeld et al. 2017/2021) mostra ipertrofia
**simile fra circa 5 e 35 ripetizioni**, purché le serie siano portate vicino
al cedimento. I range qui sotto sono quindi una scelta pratica e sostenibile,
non l'unico intervallo che "funziona" — l'idea che esista una sola finestra
magica di ripetizioni è proprio la nozione datata da evitare.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentRecommendationLog,
    Exercise,
    ExercisePreference,
    ExperienceLevel,
    Goal,
    RecommendationType,
    ScreeningRecord,
    SplitType,
    UserProfile,
    WorkoutPlan,
    WorkoutPlanExercise,
)
from app.services import exercise_library

logger = logging.getLogger("workout_generator")

# --- Parametri dalla knowledge base -----------------------------------------

# `training_volume.md`: serie settimanali per gruppo muscolare.
WEEKLY_SETS_BY_EXPERIENCE = {
    ExperienceLevel.BEGINNER: (4, 8),
    ExperienceLevel.INTERMEDIATE: (8, 14),
    ExperienceLevel.ADVANCED: (12, 20),
}

# `rest_periods_and_rir.md`: nessun beneficio ipertrofico oltre i 90 secondi,
# ma i multi-articolari ne richiedono di più per mantenere il carico.
REST_COMPOUND_SECONDS = 120
REST_ISOLATION_SECONDS = 90
REST_STRENGTH_SECONDS = 240

# `rest_periods_and_rir.md`: per ipertrofia si lavora tipicamente a 1-3 RIR,
# non sempre al cedimento. Ai principianti si lascia più margine, perché la
# tecnica è ancora in costruzione e il cedimento la degrada.
RIR_BY_EXPERIENCE = {
    ExperienceLevel.BEGINNER: 3,
    ExperienceLevel.INTERMEDIATE: 2,
    ExperienceLevel.ADVANCED: 1,
}

# Nomi leggibili degli obiettivi: finiscono nel titolo della scheda, che
# l'utente legge.
GOAL_NAMES = {
    Goal.HYPERTROPHY: "Scheda massa muscolare",
    Goal.STRENGTH: "Scheda forza",
    Goal.FAT_LOSS: "Scheda definizione",
    Goal.MAINTENANCE: "Scheda mantenimento",
    Goal.GENERAL_HEALTH: "Scheda salute generale",
}

# Range di ripetizioni **stretti**, distinti fra multi-articolari e isolamenti.
#
# Come ricordato in testa al modulo, ogni range fra circa 5 e 35 ripetizioni
# produce ipertrofia se le serie sono vicine al cedimento: la scelta di un
# 6-8 invece di un 6-12 non è fisiologica ma pratica. Un bersaglio stretto
# dice senza ambiguità quando aumentare il carico — arrivi in cima al range
# con il RIR previsto, e alla sessione dopo sali di peso — mentre un range
# largo lascia spazio per restare fermi a lungo senza accorgersene.
# Gli isolamenti stanno un gradino sopra: su una sola articolazione i carichi
# molto alti rendono più difficile controllare il movimento.
REP_RANGES = {
    Goal.HYPERTROPHY: {"compound": (6, 8), "isolation": (8, 10)},
    Goal.STRENGTH: {"compound": (3, 5), "isolation": (6, 8)},
    Goal.FAT_LOSS: {"compound": (6, 8), "isolation": (10, 12)},
    Goal.MAINTENANCE: {"compound": (6, 8), "isolation": (8, 10)},
    Goal.GENERAL_HEALTH: {"compound": (8, 10), "isolation": (10, 12)},
}

# Serie per singolo esercizio. Con 2-3 serie ognuna può essere portata
# davvero vicino al cedimento; quando il volume della giornata è maggiore, si
# aggiunge un esercizio invece di allungare lo stesso.
TARGET_SETS_PER_EXERCISE = 3


def rep_range(goal: str, is_compound: bool) -> tuple[int, int]:
    ranges = REP_RANGES.get(goal, REP_RANGES[Goal.HYPERTROPHY])
    return ranges["compound" if is_compound else "isolation"]

# Gruppi muscolari wger raccolti per distretto, con i nomi che l'API
# restituisce (`name_en`, il nome comune).
#
# Sono deliberatamente esclusi i gruppi minori che wger espone separatamente
# (Brachialis, Serratus anterior, Soleus, Obliquus externus abdominis): hanno
# pochi esercizi in catalogo e vengono comunque allenati come secondari dai
# multi-articolari. Dedicargli esercizi propri gonfierebbe la sessione senza
# beneficio.
PUSH_MUSCLES = ("Chest", "Shoulders", "Triceps")
PULL_MUSCLES = ("Lats", "Trapezius", "Biceps")
LEG_MUSCLES = ("Quads", "Hamstrings", "Glutes", "Calves")
CORE_MUSCLES = ("Abs",)

# Full body: si allenano i distretti principali a ogni sessione, coprendo i
# pattern fondamentali (spinta, trazione, gambe, core). I muscoli piccoli
# arrivano come secondari dei multi-articolari. Iterare su tutti i gruppi
# produrrebbe sessioni da 15+ esercizi, inapplicabili.
FULL_BODY_MUSCLES = ("Chest", "Lats", "Quads", "Glutes", "Shoulders", "Abs")

# Attrezzatura che non richiede nulla: sempre disponibile.
BODYWEIGHT = "none (bodyweight exercise)"

# `who_physical_activity.md`: sopra i 65 anni serve lavoro su equilibrio e
# forza funzionale almeno 3 giorni a settimana, in aggiunta al resto.
BALANCE_WORK_AGE_THRESHOLD = 65

# Tetto pratico di esercizi per sessione. Non viene da una fonte scientifica:
# è un vincolo di realizzabilità. Senza, una giornata Upper con 6 gruppi
# muscolari e due esercizi ciascuno produrrebbe 12 esercizi, cioè una seduta
# da oltre due ore che nessuno completa come prescritto — e una scheda non
# eseguita non allena nessuno.
MAX_EXERCISES_PER_SESSION = 8


@dataclass
class PlannedExercise:
    exercise: Exercise
    day_label: str
    order_index: int
    sets: int
    reps_min: int
    reps_max: int
    rir: int
    rest_seconds: int
    note: str | None = None


@dataclass
class GeneratedPlan:
    name: str
    goal: str
    days_per_week: int
    exercises: list[PlannedExercise]
    weekly_sets_per_muscle: dict[str, int]
    rationale: str
    warnings: list[str] = field(default_factory=list)
    knowledge_tags: list[str] = field(default_factory=list)


class GenerationError(RuntimeError):
    """Impossibile generare una scheda (es. catalogo esercizi vuoto)."""


# --- Split settimanali ------------------------------------------------------


def _full_body(days_per_week: int) -> list[tuple[str, tuple[str, ...]]]:
    return [(f"Giorno {chr(65 + i)}", FULL_BODY_MUSCLES) for i in range(days_per_week)]


def _upper_lower(days_per_week: int) -> list[tuple[str, tuple[str, ...]]]:
    upper = PUSH_MUSCLES + PULL_MUSCLES
    lower = LEG_MUSCLES + CORE_MUSCLES
    giorni = []
    for i in range(days_per_week):
        nome, muscoli = ("Upper", upper) if i % 2 == 0 else ("Lower", lower)
        giorni.append((f"{nome} {'A' if i < 2 else 'B'}", muscoli))
    return giorni


def _push_pull_legs(days_per_week: int) -> list[tuple[str, tuple[str, ...]]]:
    ciclo = (
        ("Push", PUSH_MUSCLES),
        ("Pull", PULL_MUSCLES),
        ("Gambe", LEG_MUSCLES + CORE_MUSCLES),
    )
    giorni = []
    for i in range(days_per_week):
        nome, muscoli = ciclo[i % 3]
        giorni.append((f"{nome} {'A' if i < 3 else 'B'}", muscoli))
    return giorni


def _muscle_group_split(days_per_week: int) -> list[tuple[str, tuple[str, ...]]]:
    """Divisione per gruppi muscolari, nel modo classico da palestra.

    Gli abbinamenti non sono casuali: si accoppiano muscoli che collaborano
    già nei movimenti (petto e tricipiti spingono insieme, dorso e bicipiti
    tirano insieme), così i secondari vengono allenati quando sono già
    coinvolti invece che il giorno dopo, quando dovrebbero recuperare.
    """
    blocchi = [
        ("Petto e bicipiti", ("Chest", "Biceps")),
        ("Gambe e dorso", ("Quads", "Hamstrings", "Glutes", "Lats")),
        ("Spalle e tricipiti", ("Shoulders", "Triceps", "Abs")),
        ("Petto e dorso", ("Chest", "Lats", "Trapezius")),
        ("Gambe e polpacci", ("Quads", "Hamstrings", "Glutes", "Calves")),
        ("Braccia e spalle", ("Biceps", "Triceps", "Shoulders")),
        ("Core e polpacci", ("Abs", "Calves")),
    ]
    return [
        (nome, muscoli) for nome, muscoli in blocchi[: max(1, min(days_per_week, 7))]
    ]


SPLIT_BUILDERS = {
    SplitType.FULL_BODY: _full_body,
    SplitType.UPPER_LOWER: _upper_lower,
    SplitType.PUSH_PULL_LEGS: _push_pull_legs,
    SplitType.MUSCLE_GROUP: _muscle_group_split,
}


def build_split(
    days_per_week: int, split_type: str = SplitType.AUTO
) -> list[tuple[str, tuple[str, ...]]]:
    """Distribuisce i gruppi muscolari sui giorni disponibili.

    Con `auto` la scelta segue i giorni disponibili: con pochi giorni il full
    body permette di stimolare ogni muscolo più volte a settimana, il che
    rende più facile raggiungere il volume settimanale senza sessioni
    interminabili. Con più giorni si può separare i distretti.

    Gli altri valori rispettano la scelta esplicita dell'utente, anche quando
    non sarebbe la mia: la scheda che si esegue volentieri vale più di quella
    teoricamente ottimale (`exercise_choice_and_focus.md`).
    """
    days_per_week = max(days_per_week, 1)

    if split_type != SplitType.AUTO:
        builder = SPLIT_BUILDERS.get(split_type)
        if builder is not None:
            return builder(days_per_week)

    if days_per_week <= 3:
        return _full_body(days_per_week)
    if days_per_week == 4:
        return _upper_lower(days_per_week)
    return _push_pull_legs(days_per_week)


# --- Selezione degli esercizi ------------------------------------------------


def _available_equipment_filter(profile: UserProfile) -> set[str] | None:
    """Interpreta l'attrezzatura dichiarata dall'utente (testo libero).

    `None` significa "nessun filtro": si assume una palestra attrezzata.
    """
    raw = (profile.available_equipment or "").strip().lower()
    if not raw:
        return None
    return {token.strip() for token in raw.replace(";", ",").split(",") if token.strip()}


def _is_usable(exercise: Exercise, allowed: set[str] | None) -> bool:
    if allowed is None:
        return True

    equipment = (exercise.equipment or "").lower()
    if not equipment or BODYWEIGHT in equipment:
        return True  # a corpo libero: sempre fattibile

    # Ogni attrezzo richiesto dall'esercizio deve essere fra quelli
    # dichiarati: basta che ne manchi uno e l'esercizio non è eseguibile.
    required = [e.strip() for e in equipment.split(",") if e.strip()]
    return all(any(token in req or req in token for token in allowed) for req in required)


def _preference_map(db: Session, profile_id: int | None) -> dict[int, bool]:
    """Esercizi che l'utente ha segnato come graditi o da evitare.

    Le preferenze pesano sulla generazione, non solo sulla sostituzione a
    posteriori: se hai già detto che preferisci la chest press alla panca
    piana, la scheda successiva deve nascere così, senza fartelo ripetere.
    """
    if profile_id is None:
        return {}
    return {
        p.exercise_id: p.is_preferred
        for p in db.scalars(
            select(ExercisePreference).where(
                ExercisePreference.profile_id == profile_id
            )
        )
    }


def _pick_exercises(
    db: Session,
    muscle: str,
    allowed: set[str] | None,
    *,
    wanted: int,
    rotation: int = 0,
    preferences: dict[int, bool] | None = None,
) -> list[Exercise]:
    """Sceglie gli esercizi per un gruppo muscolare.

    L'ordinamento non è alfabetico di proposito: con le traduzioni italiane
    l'alfabeto produce scelte arbitrarie (il primo esercizio per le spalle
    risultava "Allenamento al sacco"). Si ordina invece per indizi di
    "canonicità" presenti nel catalogo:

      1. multi-articolari prima — coinvolgono più massa per serie;
      2. con immagine — in wger le hanno soprattutto gli esercizi noti e
         curati, non quelli marginali aggiunti dagli utenti;
      3. con descrizione — stesso ragionamento.

    `rotation` fa scorrere la finestra di selezione: serve a rendere davvero
    diverse le giornate A e B di uno stesso distretto, invece di ripetere gli
    stessi esercizi due volte a settimana.
    """
    candidates = list(
        db.scalars(
            select(Exercise)
            .where(Exercise.primary_muscle == muscle, exercise_library.catalog_condition(db))
            .order_by(*exercise_library.catalog_order())
        )
    )
    preferences = preferences or {}
    # Gli esercizi esplicitamente sgraditi non vengono riproposti: sarebbe il
    # contrario dello scopo delle preferenze.
    usable = [
        ex
        for ex in candidates
        if _is_usable(ex, allowed) and preferences.get(ex.id, True) is not False
    ]
    if not usable:
        return []

    # I graditi vanno in testa, mantenendo l'ordinamento fra loro.
    graditi = [ex for ex in usable if preferences.get(ex.id) is True]
    if graditi:
        usable = graditi + [ex for ex in usable if ex not in graditi]

    def _slice(pool: list[Exercise], quantity: int, offset: int) -> list[Exercise]:
        if not pool or quantity <= 0:
            return []
        start = (offset * quantity) % len(pool)
        return (pool + pool)[start : start + quantity][: min(quantity, len(pool))]

    compound = [ex for ex in usable if ex.is_compound]
    # Nella libreria con gli esercizi di base la preferenza per i
    # multi-articolari vale solo per quelli di base. La fonte classifica come
    # multi-articolari anche movimenti come il "Drag Curl": senza questo
    # filtro scavalcavano il curl con bilanciere nella scheda dei bicipiti.
    if any((ex.priority if ex.priority is not None else 100) < exercise_library.DEFAULT_PRIORITY for ex in usable):
        compound = [ex for ex in compound if ex.priority < exercise_library.DEFAULT_PRIORITY]
    isolation = [ex for ex in usable if ex not in compound]

    if wanted <= 1:
        # Un solo esercizio: si preferisce il multi-articolare, che copre più
        # massa muscolare per serie.
        return _slice(compound or usable, 1, rotation)

    # Più esercizi: metà (arrotondata per eccesso) multi-articolari e il resto
    # di isolamento, nell'ordine classico. Prenderli tutti dallo stesso
    # ordinamento significherebbe ottenere solo multi-articolari (in wger sono
    # la maggioranza), lasciando la scheda senza isolamenti e con tutti i
    # recuperi uguali.
    n_compound = min((wanted + 1) // 2, len(compound))
    selezione = _slice(compound, n_compound, rotation) + _slice(
        isolation, wanted - n_compound, rotation
    )
    if len(selezione) < wanted:
        # Un gruppo muscolare può non avere entrambe le tipologie: si completa
        # con quello che c'è, senza duplicare.
        resto = [ex for ex in _slice(usable, wanted, rotation) if ex not in selezione]
        selezione += resto[: wanted - len(selezione)]
    return selezione


# --- Generazione -------------------------------------------------------------


def _weekly_sets_target(
    profile: UserProfile, screening: ScreeningRecord | None
) -> tuple[int, list[str]]:
    """Serie settimanali per gruppo muscolare, con i correttivi di sicurezza."""
    warnings: list[str] = []
    low, high = WEEKLY_SETS_BY_EXPERIENCE.get(
        profile.experience_level, WEEKLY_SETS_BY_EXPERIENCE[ExperienceLevel.BEGINNER]
    )

    # Punto di partenza nella parte bassa del range: `training_volume.md`
    # ricorda che si può sempre salire in base al recupero, mentre partire
    # troppo alto accumula fatica senza benefici aggiuntivi.
    target = low + (high - low) // 3

    if screening is not None and screening.requires_medical_clearance:
        target = low
        warnings.append(
            "Volume impostato al minimo del range per la tua esperienza: hai "
            "risposto «sì» ad almeno una domanda dello screening di sicurezza. "
            "Fai valutare il piano da un medico prima di aumentarlo."
        )

    return target, warnings


def generate_plan(
    db: Session,
    profile: UserProfile,
    *,
    screening: ScreeningRecord | None = None,
    split_type: str | None = None,
) -> GeneratedPlan:
    """Costruisce una scheda a partire dal profilo, in modo deterministico."""
    split = build_split(
        profile.training_days_per_week,
        split_type or getattr(profile, "split_type", SplitType.AUTO),
    )
    if not split:
        raise GenerationError("Nessun giorno di allenamento configurato")

    allowed = _available_equipment_filter(profile)
    weekly_target, warnings = _weekly_sets_target(profile, screening)
    rir = RIR_BY_EXPERIENCE.get(profile.experience_level, 2)
    is_strength = profile.goal == Goal.STRENGTH

    # Quante volte a settimana ogni muscolo viene allenato: serve a dividere
    # il volume settimanale fra le sessioni, invece di ripeterlo per intero
    # ogni giorno (errore che triplicherebbe il volume reale).
    frequency: dict[str, int] = {}
    for _, muscles in split:
        for muscle in muscles:
            frequency[muscle] = frequency.get(muscle, 0) + 1

    preferences = _preference_map(db, profile.id)
    planned: list[PlannedExercise] = []
    weekly_sets: dict[str, int] = {}
    muscles_without_exercises: set[str] = set()
    # Quante volte un muscolo è già stato programmato: usato per ruotare gli
    # esercizi fra le sessioni (Upper A e Upper B non devono essere identiche).
    times_programmed: dict[str, int] = {}

    # Giornate in cui il volume non sta in serie da 2-3 entro il tetto di
    # esercizi: lo si dichiara invece di tagliare in silenzio il volume.
    crowded_days: list[str] = []

    for day_label, muscles in split:
        order = 0
        sets_by_muscle = {
            m: max(1, round(weekly_target / frequency[m])) for m in muscles
        }
        slots = _allocate_exercise_slots(
            [math.ceil(sets_by_muscle[m] / TARGET_SETS_PER_EXERCISE) for m in muscles],
            MAX_EXERCISES_PER_SESSION,
        )

        for muscle, exercise_count in zip(muscles, slots):
            sets_today = sets_by_muscle[muscle]
            rotation = times_programmed.get(muscle, 0)
            exercises = _pick_exercises(
                db, muscle, allowed, wanted=exercise_count, rotation=rotation,
                preferences=preferences,
            )
            times_programmed[muscle] = rotation + 1

            if not exercises:
                muscles_without_exercises.add(muscle)
                continue

            # Il resto va sui primi esercizi, altrimenti la divisione intera
            # perderebbe serie per strada (5 serie su 2 esercizi -> 2+2=4).
            base, remainder = divmod(sets_today, len(exercises))
            for idx, exercise in enumerate(exercises):
                sets_for_exercise = max(1, base + (1 if idx < remainder else 0))
                if sets_for_exercise > TARGET_SETS_PER_EXERCISE and day_label not in crowded_days:
                    crowded_days.append(day_label)
                reps_min, reps_max = rep_range(profile.goal, exercise.is_compound)
                planned.append(
                    PlannedExercise(
                        exercise=exercise,
                        day_label=day_label,
                        order_index=order,
                        sets=sets_for_exercise,
                        reps_min=reps_min,
                        reps_max=reps_max,
                        rir=rir,
                        rest_seconds=(
                            REST_STRENGTH_SECONDS
                            if is_strength
                            else REST_COMPOUND_SECONDS
                            if exercise.is_compound
                            else REST_ISOLATION_SECONDS
                        ),
                    )
                )
                weekly_sets[muscle] = weekly_sets.get(muscle, 0) + sets_for_exercise
                order += 1

    if not planned:
        raise GenerationError(
            "Nessun esercizio disponibile con l'attrezzatura indicata. "
            "Verifica di aver sincronizzato il catalogo esercizi."
        )

    if muscles_without_exercises:
        warnings.append(
            "Nessun esercizio disponibile con la tua attrezzatura per: "
            + ", ".join(sorted(muscles_without_exercises))
        )

    if crowded_days:
        warnings.append(
            f"In {', '.join(crowded_days)} alcuni esercizi superano le "
            f"{TARGET_SETS_PER_EXERCISE} serie: il volume previsto non sta in "
            f"{MAX_EXERCISES_PER_SESSION} esercizi a sessione. Se preferisci serie "
            "da 2-3, aggiungi un giorno di allenamento o scegli uno split che "
            "alleni ogni muscolo più volte a settimana."
        )

    knowledge_tags = ["volume_allenamento", "recupero", "intensità"]
    if screening is not None:
        knowledge_tags.append("screening")

    if profile.age >= BALANCE_WORK_AGE_THRESHOLD:
        warnings.append(
            "Sopra i 65 anni le linee guida WHO raccomandano anche attività "
            "di equilibrio e forza funzionale almeno 3 giorni a settimana, "
            "in aggiunta a questa scheda."
        )
        knowledge_tags.append("attivita_generale")

    return GeneratedPlan(
        name=f"{GOAL_NAMES.get(profile.goal, 'Scheda')} — "
             f"{profile.training_days_per_week} giorni",
        goal=profile.goal,
        days_per_week=profile.training_days_per_week,
        exercises=planned,
        weekly_sets_per_muscle=weekly_sets,
        rationale=_deterministic_rationale(profile, weekly_target, rir),
        warnings=warnings,
        knowledge_tags=knowledge_tags,
    )


def _allocate_exercise_slots(needs: list[int], budget: int) -> list[int]:
    """Quanti esercizi assegnare a ogni gruppo muscolare della giornata.

    Ognuno ne riceve almeno uno. Il margine residuo del tetto di sessione va
    **a turno** a chi ne ha ancora bisogno, partendo dai distretti maggiori
    (primi nelle tuple): dandolo tutto al primo, il petto prenderebbe quattro
    esercizi e i bicipiti resterebbero con uno solo da sei serie.
    """
    slots = [1] * len(needs)
    spare = max(0, budget - len(needs))
    while spare > 0:
        assegnato = False
        for i, need in enumerate(needs):
            if spare == 0:
                break
            if slots[i] < need:
                slots[i] += 1
                spare -= 1
                assegnato = True
        if not assegnato:
            break
    return slots


def _deterministic_rationale(profile: UserProfile, weekly_target: int, rir: int) -> str:
    """Spiegazione generata senza LLM: sempre disponibile, sempre coerente
    con i parametri effettivamente applicati."""
    low, high = WEEKLY_SETS_BY_EXPERIENCE.get(
        profile.experience_level, WEEKLY_SETS_BY_EXPERIENCE[ExperienceLevel.BEGINNER]
    )
    c_min, c_max = rep_range(profile.goal, True)
    i_min, i_max = rep_range(profile.goal, False)
    return (
        f"Volume di {weekly_target} serie settimanali per gruppo muscolare, "
        f"nella parte bassa del range {low}-{high} indicato per un livello "
        f"«{profile.experience_level}»: si parte prudenti e si sale in base a "
        f"come rispondi. Intensità espressa in RIR {rir} (ripetizioni che ti "
        f"restano prima del cedimento) invece che in percentuale del massimale, "
        f"perché si adatta da sola a stanchezza, sonno e stress del giorno. "
        f"Ripetizioni {c_min}-{c_max} sui multi-articolari e {i_min}-{i_max} "
        f"sugli isolamenti, in 2-3 serie per esercizio: un range stretto ti dice "
        f"chiaramente quando aumentare il carico (arrivi in cima con il RIR "
        f"previsto → la volta dopo sali di peso). La ricerca mostra ipertrofia "
        f"simile fra circa 5 e 35 ripetizioni vicino al cedimento, quindi è una "
        f"scelta pratica, non l'unica che funziona. Recuperi di "
        f"{REST_COMPOUND_SECONDS} secondi sui multi-articolari e "
        f"{REST_ISOLATION_SECONDS} sugli isolamenti."
    )


# --- Spiegazione in linguaggio naturale (opzionale) --------------------------

_EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
        "spiegazione": {"type": "string"},
        "punti_chiave": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["spiegazione"],
}

_EXPLANATION_PROMPT = """Sei un assistente che spiega una scheda di allenamento
già costruita. Il tuo compito è **spiegare**, non progettare.

REGOLE VINCOLANTI:
- Non inventare, modificare o aggiungere numeri. Serie, ripetizioni, RIR e
  recuperi sono già stati decisi e te li fornisco: usa esattamente quelli.
- Se citi un principio, deve essere sostenuto dalle FONTI qui sotto.
- Non usare toni assoluti ("devi", "è obbligatorio") dove le fonti stesse
  esprimono cautela o range.
- Scrivi in italiano, dando del tu, in modo diretto e concreto.
- Massimo 150 parole per la spiegazione.

PROFILO UTENTE
- Età: {eta} anni, obiettivo dichiarato: {obiettivo}
- Livello di esperienza: {esperienza}
- Giorni di allenamento a settimana: {giorni}

SCHEDA GIÀ GENERATA (parametri non modificabili)
- Volume settimanale per gruppo muscolare: {volume}
- Intensità: RIR {rir}
- Range di ripetizioni: {reps}
- Recuperi: {recuperi}
- Struttura: {struttura}

{avvertenze}

FONTI DA CUI PUOI ATTINGERE (non citarne altre):

{contesto}
"""


def explain_plan(generated: GeneratedPlan, profile: UserProfile) -> str:
    """Riscrive la motivazione della scheda in linguaggio naturale.

    Se l'LLM non è configurato o fallisce, restituisce la spiegazione
    deterministica: la scheda resta pienamente utilizzabile, perde solo il
    testo discorsivo. Nessun parametro dipende da questa chiamata.
    """
    from app.services import knowledge_base, llm_client

    volume = ", ".join(
        f"{muscolo} {serie}" for muscolo, serie in sorted(generated.weekly_sets_per_muscle.items())
    )
    recuperi = sorted({item.rest_seconds for item in generated.exercises})
    struttura = ", ".join(dict.fromkeys(item.day_label for item in generated.exercises))
    reps = "; ".join(
        dict.fromkeys(
            f"{i.reps_min}-{i.reps_max} ({'multi-articolari' if i.exercise.is_compound else 'isolamenti'})"
            for i in generated.exercises
        )
    ) or "n/d"
    rir = next((str(i.rir) for i in generated.exercises), "n/d")

    prompt = _EXPLANATION_PROMPT.format(
        eta=profile.age,
        obiettivo=profile.goal,
        esperienza=profile.experience_level,
        giorni=generated.days_per_week,
        volume=volume,
        rir=rir,
        reps=reps,
        recuperi=", ".join(f"{r}s" for r in recuperi),
        struttura=struttura,
        avvertenze=(
            "AVVERTENZE DA RIPORTARE:\n- " + "\n- ".join(generated.warnings)
            if generated.warnings
            else ""
        ),
        contesto=knowledge_base.build_context(generated.knowledge_tags),
    )

    try:
        risposta = llm_client.generate_structured(prompt, _EXPLANATION_SCHEMA)
    except (llm_client.LLMNotConfigured, llm_client.LLMError) as e:
        logger.info("Spiegazione LLM non disponibile (%s): uso quella deterministica", e)
        return generated.rationale

    spiegazione = (risposta.get("spiegazione") or "").strip()
    if not spiegazione:
        return generated.rationale

    punti = risposta.get("punti_chiave") or []
    if punti:
        spiegazione += "\n\n" + "\n".join(f"• {p}" for p in punti)
    return spiegazione


# --- Persistenza -------------------------------------------------------------


def persist_plan(
    db: Session,
    profile: UserProfile,
    generated: GeneratedPlan,
    *,
    started_at=None,
    used_llm: bool = False,
) -> WorkoutPlan:
    """Salva la scheda, disattivando quella precedente.

    Le schede vecchie non vengono cancellate: servono ai report per
    confrontare inizio e fine di un percorso.

    Registra anche la raccomandazione in `agent_recommendation_log`, con i
    tag della knowledge base che l'hanno prodotta: deve essere sempre
    possibile rispondere a "perché mi ha proposto questo, e in base a cosa".
    """
    import datetime as dt

    for previous in db.scalars(
        select(WorkoutPlan).where(
            WorkoutPlan.profile_id == profile.id, WorkoutPlan.is_active.is_(True)
        )
    ):
        previous.is_active = False
        previous.ended_at = dt.date.today()

    plan = WorkoutPlan(
        profile_id=profile.id,
        name=generated.name,
        goal=generated.goal,
        days_per_week=generated.days_per_week,
        rationale=generated.rationale,
        is_active=True,
        started_at=started_at or dt.date.today(),
    )
    db.add(plan)
    db.flush()  # serve l'id per le righe collegate

    for item in generated.exercises:
        db.add(
            WorkoutPlanExercise(
                workout_plan_id=plan.id,
                exercise_id=item.exercise.id,
                day_label=item.day_label,
                order_index=item.order_index,
                target_sets=item.sets,
                target_reps_min=item.reps_min,
                target_reps_max=item.reps_max,
                target_rir=item.rir,
                rest_seconds=item.rest_seconds,
                notes=item.note,
            )
        )

    riepilogo = (
        f"Scheda {generated.days_per_week} giorni, obiettivo {generated.goal}. "
        f"Volume settimanale: "
        + ", ".join(f"{m} {s}" for m, s in sorted(generated.weekly_sets_per_muscle.items()))
    )
    if generated.warnings:
        riepilogo += " | Avvertenze: " + " ".join(generated.warnings)

    db.add(
        AgentRecommendationLog(
            profile_id=profile.id,
            recommendation_type=RecommendationType.WORKOUT_PLAN_GENERATED,
            reference_id=plan.id,
            summary=riepilogo,
            knowledge_source_tags=",".join(generated.knowledge_tags),
            used_llm=used_llm,
        )
    )

    db.commit()
    db.refresh(plan)
    return plan
