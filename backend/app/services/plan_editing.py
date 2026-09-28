"""Composizione della scheda da parte dell'utente: aggiungere e togliere esercizi.

Il generatore si ferma a `MAX_EXERCISES_PER_SESSION` esercizi a seduta perché
propone una scheda che si riesce a completare. Chi la modifica a mano invece
decide lui: niente tetto, ma il volume della scheda viene ricalcolato a ogni
modifica e Kilo dice quando un muscolo scende sotto il minimo delle fonti o
una seduta diventa molto lunga.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Exercise, Goal, UserProfile, WorkoutPlan, WorkoutPlanExercise
from app.services import exercise_swap
from app.services import workout_generator as wg

# Muscoli su cui si segnala il volume basso: quelli che le schede allenano.
_MAIN_MUSCLES = set(wg.PUSH_MUSCLES + wg.PULL_MUSCLES + wg.LEG_MUSCLES + wg.CORE_MUSCLES)


class EditError(ValueError):
    """Modifica non possibile (giorno inesistente, ultimo esercizio del giorno)."""


def _days(plan: WorkoutPlan) -> list[str]:
    return list(dict.fromkeys(e.day_label for e in plan.exercises))


def add_exercise(
    db: Session, profile: UserProfile, plan: WorkoutPlan, exercise: Exercise, day_label: str
) -> WorkoutPlanExercise:
    """Aggiunge un esercizio in fondo al giorno, con i parametri delle fonti.

    Serie, ripetizioni, RIR e recupero sono quelli che il generatore darebbe
    allo stesso tipo di esercizio: l'utente li cambia poi come gli altri.
    """
    if day_label not in _days(plan):
        raise EditError(f"La scheda non ha un giorno «{day_label}».")
    reps_min, reps_max = wg.rep_range(plan.goal, exercise.is_compound)
    riga = WorkoutPlanExercise(
        workout_plan_id=plan.id,
        exercise_id=exercise.id,
        day_label=day_label,
        order_index=1 + max((e.order_index for e in plan.exercises if e.day_label == day_label), default=-1),
        target_sets=wg.TARGET_SETS_PER_EXERCISE,
        target_reps_min=reps_min,
        target_reps_max=reps_max,
        target_rir=wg.RIR_BY_EXPERIENCE.get(profile.experience_level, 2),
        rest_seconds=(
            wg.REST_STRENGTH_SECONDS
            if plan.goal == Goal.STRENGTH
            else wg.REST_COMPOUND_SECONDS
            if exercise.is_compound
            else wg.REST_ISOLATION_SECONDS
        ),
    )
    db.add(riga)
    # Sceglierlo è un modo di dire che piace: le prossime schede lo propongono.
    exercise_swap.set_preference(db, profile, exercise, preferred=True, note="aggiunto alla scheda")
    db.commit()
    db.refresh(plan)
    return riga


def remove_exercise(db: Session, plan_exercise: WorkoutPlanExercise) -> None:
    """Toglie un esercizio dalla scheda. Le serie già registrate restano."""
    stesso_giorno = [
        e for e in plan_exercise.plan.exercises if e.day_label == plan_exercise.day_label
    ]
    if len(stesso_giorno) <= 1:
        raise EditError(
            "È l'unico esercizio del giorno: senza, il giorno sparirebbe dalla scheda. "
            "Cambialo invece di toglierlo."
        )
    db.delete(plan_exercise)
    db.commit()


@dataclass
class PlanVolume:
    weekly_sets_equivalent: dict[str, float]
    warnings: list[str] = field(default_factory=list)


def _target_muscle(exercise: Exercise) -> str | None:
    primario, parole = wg.PSEUDO_MUSCLES["Rear delts"]
    nome = (exercise.name or "").lower().replace("-", " ")
    if exercise.primary_muscle == primario and any(p in nome for p in parole):
        return "Rear delts"
    return None


def plan_volume(plan: WorkoutPlan, profile: UserProfile) -> PlanVolume:
    """Volume settimanale della scheda così com'è, con gli avvisi."""
    voci = [
        wg.PlannedExercise(
            exercise=e.exercise,
            day_label=e.day_label,
            order_index=e.order_index,
            sets=e.target_sets,
            reps_min=e.target_reps_min,
            reps_max=e.target_reps_max,
            rir=e.target_rir,
            rest_seconds=e.rest_seconds,
            target_muscle=_target_muscle(e.exercise),
        )
        for e in plan.exercises
    ]
    equivalenti = wg.equivalent_weekly_sets(voci)
    avvisi: list[str] = []

    minimo, _, _ = wg.weekly_sets_range(profile)
    bassi = sorted(
        (m, v) for m, v in equivalenti.items() if m in _MAIN_MUSCLES and v < minimo
    )
    if bassi:
        avvisi.append(
            "Sotto le "
            f"{minimo} serie settimanali consigliate per il tuo livello: "
            + ", ".join(f"{wg.muscle_name_it(m)} {_numero(v)}" for m, v in bassi)
            + ". Contano anche le serie indirette, a metà."
        )

    lunghe = []
    for giorno in _days(plan):
        serie = sum(e.target_sets for e in plan.exercises if e.day_label == giorno)
        if serie > wg.LONG_SESSION_SETS:
            lunghe.append(f"{giorno} ha {serie} serie")
    if lunghe:
        avvisi.append(
            "Sedute lunghe: "
            + ", ".join(lunghe)
            + ", oltre un'ora e un quarto. Con un giorno in più lo stesso volume "
            "si distribuisce in meno serie per seduta."
        )
    return PlanVolume(weekly_sets_equivalent=equivalenti, warnings=avvisi)


def _numero(v: float) -> str:
    return f"{v:g}".replace(".", ",")
