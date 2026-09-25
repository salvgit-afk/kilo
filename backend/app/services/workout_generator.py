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

# Serie settimanali per gruppo muscolare: (minimo, partenza, massimo).
#
# La partenza è il volume della scheda nuova; il minimo è il pavimento sotto
# cui l'autoregolazione non scende, il massimo il tetto oltre cui non si
# aggiungono serie.
#
# Obiettivi diversi dalla massa muscolare: range di `training_volume.md`,
# partendo dalla parte bassa.
WEEKLY_SETS_DEFAULT = {
    ExperienceLevel.BEGINNER: (4, 5, 8),
    ExperienceLevel.INTERMEDIATE: (8, 10, 14),
    ExperienceLevel.ADVANCED: (12, 14, 20),
}

# Obiettivo massa muscolare: `hypertrophy_prescription.md` (IUSCA, ~10 serie a
# settimana come minimo per ottimizzare) e `resistance_training_acsm.md`
# (ACSM 2026, ≥10 serie, rendimenti decrescenti oltre ~18-20). Nessun livello
# parte sotto 10. Il massimo sta a circa due aumenti del 20% dalla partenza
# (il limite IUSCA per ciclo) e per gli avanzati coincide con la soglia dei
# rendimenti decrescenti. Il minimo resta sotto 10 perché IUSCA riconosce
# risposte buone anche a volumi più bassi: serve quando il recupero non regge.
WEEKLY_SETS_HYPERTROPHY = {
    ExperienceLevel.BEGINNER: (6, 10, 14),
    ExperienceLevel.INTERMEDIATE: (8, 12, 16),
    ExperienceLevel.ADVANCED: (10, 14, 20),
}

# `hypertrophy_prescription.md` (IUSCA): oltre ~10 serie per muscolo nella
# stessa seduta conviene distribuire il volume su più giorni.
MAX_SETS_PER_MUSCLE_PER_SESSION = 10


def weekly_sets_range(profile: UserProfile) -> tuple[int, int, int]:
    """(minimo, partenza, massimo) di serie settimanali per gruppo muscolare."""
    table = WEEKLY_SETS_HYPERTROPHY if profile.goal == Goal.HYPERTROPHY else WEEKLY_SETS_DEFAULT
    return table.get(profile.experience_level, table[ExperienceLevel.BEGINNER])


# Oltre il massimo della tabella non c'è un muro: `training_dose_response.md`
# (Pelland 2026) non trova nessun punto in cui i guadagni si fermano. Ma
# nemmeno via libera: 24 serie settimanali è la dose più alta provata in uno
# studio controllato su allenati (Aube 2022), dove non ha dato più ipertrofia
# delle 12 o 18 e la forza andava peggio. Da lì in poi non esistono prove
# controllate di un vantaggio, quindi è il nostro limite di sicurezza.
DOCUMENTED_CEILING_SETS = 24
# Quanto si può salire sopra il massimo del proprio livello: sei serie, cioè
# circa due aumenti del 20%, per non passare da "consigliato" a "mai provato"
# in un colpo solo.
CEILING_MARGIN_SETS = 6


def safety_ceiling_sets(profile: UserProfile) -> int:
    """Massimo assoluto di serie settimanali per gruppo muscolare.

    Si raggiunge solo con l'autoregolazione, un aumento per volta e a patto
    che l'utente dichiari di recuperare bene: è il territorio oltre il range
    consigliato, dove le prove si fanno rade.
    """
    _, _, massimo = weekly_sets_range(profile)
    if profile.goal != Goal.HYPERTROPHY:
        # Per forza, dimagrimento e mantenimento il range resta quello: il
        # volume alto non è la leva principale di quegli obiettivi.
        return massimo
    return min(massimo + CEILING_MARGIN_SETS, DOCUMENTED_CEILING_SETS)

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
    split_type: str | None = None


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
    return SPLIT_BUILDERS[resolve_split_type(days_per_week, split_type)](days_per_week)


def resolve_split_type(days_per_week: int, split_type: str | None = SplitType.AUTO) -> str:
    """La divisione effettiva: quella scelta, oppure quella di `auto`."""
    if split_type in SPLIT_BUILDERS:
        return split_type
    if days_per_week <= 3:
        return SplitType.FULL_BODY
    if days_per_week == 4:
        return SplitType.UPPER_LOWER
    return SplitType.PUSH_PULL_LEGS


# Nomi leggibili delle divisioni: distinguono le schede quando ce n'è più d'una.
SPLIT_NAMES = {
    SplitType.FULL_BODY: "Full body",
    SplitType.UPPER_LOWER: "Upper/Lower",
    SplitType.PUSH_PULL_LEGS: "Push/Pull/Gambe",
    SplitType.MUSCLE_GROUP: "Per gruppo muscolare",
}


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
    # Fra gli isolamenti, a parità di gradimento, prima le varianti che
    # allenano il muscolo in allungamento (`biomechanics_technique.md`).
    isolation.sort(
        key=lambda ex: (preferences.get(ex.id) is not True, exercise_library.lengthened_rank(ex))
    )

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
    low, target, _ = weekly_sets_range(profile)

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
    resolved_split = resolve_split_type(
        profile.training_days_per_week,
        split_type or getattr(profile, "split_type", None) or SplitType.AUTO,
    )
    split = build_split(profile.training_days_per_week, resolved_split)
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
    # Muscoli che in una seduta superano il tetto IUSCA per seduta: come per
    # le giornate affollate, si segnala invece di tagliare il volume.
    overloaded_muscles: list[str] = []

    for day_label, muscles in split:
        order = 0
        sets_by_muscle = {
            m: max(1, round(weekly_target / frequency[m])) for m in muscles
        }
        for muscle, sets in sets_by_muscle.items():
            if sets > MAX_SETS_PER_MUSCLE_PER_SESSION and muscle not in overloaded_muscles:
                overloaded_muscles.append(muscle)
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

    if overloaded_muscles:
        warnings.append(
            f"Con questo split {', '.join(overloaded_muscles)} ricevono più di "
            f"{MAX_SETS_PER_MUSCLE_PER_SESSION} serie nella stessa seduta. Le "
            "raccomandazioni IUSCA suggeriscono di non superare circa "
            f"{MAX_SETS_PER_MUSCLE_PER_SESSION} serie per muscolo a seduta e di "
            "distribuire il resto: valuta uno split che alleni ogni muscolo "
            "almeno due volte a settimana."
        )

    knowledge_tags = ["volume_allenamento", "recupero", "intensità", "progressione"]
    if profile.goal == Goal.HYPERTROPHY:
        knowledge_tags.append("ipertrofia")
    elif profile.goal == Goal.STRENGTH:
        knowledge_tags.append("forza")
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
        name=f"{GOAL_NAMES.get(profile.goal, 'Scheda')} · {SPLIT_NAMES[resolved_split]} — "
             f"{profile.training_days_per_week} giorni",
        split_type=resolved_split,
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
    low, _, high = weekly_sets_range(profile)
    c_min, c_max = rep_range(profile.goal, True)
    i_min, i_max = rep_range(profile.goal, False)
    if profile.goal == Goal.HYPERTROPHY:
        volume = (
            f"Volume di {weekly_target} serie settimanali per gruppo muscolare: "
            f"le position stand IUSCA e ACSM indicano circa 10 serie a settimana "
            f"come soglia per ottimizzare la crescita muscolare. Per un livello "
            f"«{profile.experience_level}» il range va da {low} a {high}: si sale "
            f"al massimo del 20% per volta, in base a come rispondi. "
        )
    else:
        volume = (
            f"Volume di {weekly_target} serie settimanali per gruppo muscolare, "
            f"nella parte bassa del range {low}-{high} indicato per un livello "
            f"«{profile.experience_level}»: si parte prudenti e si sale in base a "
            f"come rispondi. "
        )
    return (
        volume
        + f"Intensità espressa in RIR {rir} (ripetizioni che ti "
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
- **Massimo 110 parole**: due paragrafi brevi, niente introduzioni né
  riepiloghi finali, nessuna frase che riassume quello che hai appena detto.
  Chi legge vuole sapere perché la scheda è così, non un tema.
- Cita almeno una volta, con i numeri esatti: serie e ripetizioni, il RIR e
  i recuperi. Sono la parte che l'utente vede nella scheda.
- Niente elenchi dentro la spiegazione: i punti chiave hanno un campo loro.

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
        risposta = llm_client.generate_structured(
            prompt, _EXPLANATION_SCHEMA, purpose="explain_plan"
        )
    except (llm_client.LLMNotConfigured, llm_client.LLMError) as e:
        logger.info("Spiegazione LLM non disponibile (%s): uso quella deterministica", e)
        return generated.rationale

    spiegazione = _accorcia(risposta.get("spiegazione") or "")
    if not spiegazione:
        return generated.rationale

    punti = risposta.get("punti_chiave") or []
    if punti:
        spiegazione += "\n\n" + "\n".join(f"• {p}" for p in punti)
    return spiegazione


# Tetto rigido della spiegazione: il prompt ne chiede 110, ma il modello a
# volte dilaga e un muro di testo non lo legge nessuno. Non conta i punti
# chiave, che sono elenchi brevi e si leggono a colpo d'occhio.
MAX_EXPLANATION_WORDS = 140


def _accorcia(testo: str, limite: int = MAX_EXPLANATION_WORDS) -> str:
    """Taglia la spiegazione troppo lunga all'ultima frase intera."""
    testo = (testo or "").strip()
    parole = testo.split()
    if len(parole) <= limite:
        return testo
    troncato = " ".join(parole[:limite])
    fine = max(troncato.rfind(". "), troncato.rfind("! "), troncato.rfind("? "))
    return (troncato[: fine + 1] if fine > 0 else troncato.rstrip(",;:") + ".").strip()


# --- Persistenza -------------------------------------------------------------


def apply_manual_targets(
    generated: GeneratedPlan,
    *,
    sets: int | None = None,
    reps: tuple[int, int] | None = None,
) -> None:
    """Serie e/o ripetizioni scelte dall'utente al posto di quelle calcolate.

    Valgono per tutti gli esercizi. RIR e recuperi restano quelli delle fonti,
    e la scheda lo dichiara: da qui in poi i numeri non vengono più dalla
    knowledge base, e l'utente deve saperlo.
    """
    if sets is None and reps is None:
        return

    for item in generated.exercises:
        if sets is not None:
            item.sets = sets
        if reps is not None:
            item.reps_min, item.reps_max = reps

    if sets is not None:
        settimanali: dict[str, int] = {}
        for item in generated.exercises:
            muscolo = item.exercise.primary_muscle or "?"
            settimanali[muscolo] = settimanali.get(muscolo, 0) + item.sets
        generated.weekly_sets_per_muscle = settimanali

    parti = []
    if sets is not None:
        parti.append(f"{sets} serie per esercizio")
    if reps is not None:
        parti.append(f"{reps[0]}-{reps[1]} ripetizioni")
    scelta = " e ".join(parti)
    generated.warnings.append(
        f"Hai scelto tu {scelta} per tutti gli esercizi: questi valori non seguono "
        "i parametri delle fonti. RIR e recuperi restano quelli calcolati."
    )
    generated.rationale += f"\n\nModifica manuale dell'utente: {scelta} per tutti gli esercizi."


def archive_plan(db: Session, profile: UserProfile, plan_id: int) -> WorkoutPlan | None:
    """Toglie una scheda da quelle attive senza cancellarla.

    Resta nello storico per i report di progressione. Restituisce `None` se
    la scheda non esiste, non è del profilo o è già archiviata.
    """
    import datetime as dt

    plan = db.get(WorkoutPlan, plan_id)
    if plan is None or plan.profile_id != profile.id or not plan.is_active:
        return None
    plan.is_active = False
    plan.ended_at = dt.date.today()
    db.commit()
    return plan


def persist_plan(
    db: Session,
    profile: UserProfile,
    generated: GeneratedPlan,
    *,
    started_at=None,
    used_llm: bool = False,
    replace_plan_id: int | None = None,
) -> WorkoutPlan:
    """Salva la scheda accanto a quelle già attive.

    Con `replace_plan_id` (il pulsante «Rigenera») la scheda indicata viene
    archiviata al posto di essere affiancata. Le schede vecchie non vengono
    cancellate: servono ai report per confrontare inizio e fine di un percorso.

    Registra anche la raccomandazione in `agent_recommendation_log`, con i
    tag della knowledge base che l'hanno prodotta: deve essere sempre
    possibile rispondere a "perché mi ha proposto questo, e in base a cosa".
    """
    import datetime as dt

    if replace_plan_id is not None:
        previous = db.get(WorkoutPlan, replace_plan_id)
        if previous is not None and previous.profile_id == profile.id and previous.is_active:
            previous.is_active = False
            previous.ended_at = dt.date.today()

    plan = WorkoutPlan(
        profile_id=profile.id,
        name=generated.name,
        goal=generated.goal,
        days_per_week=generated.days_per_week,
        split_type=generated.split_type,
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
