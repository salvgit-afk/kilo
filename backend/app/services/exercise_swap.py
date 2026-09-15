"""Alternative agli esercizi di una scheda.

La ragione è l'**aderenza**, non la fisiologia: a parità di gruppo muscolare
stimolato, un esercizio che l'utente ha scelto e che gli piace vale più di
uno "ottimale" che evita, perché una scheda abbandonata non produce
risultati. Vedi `knowledge_base/exercise_choice_and_focus.md`.

Vincolo che la sostituzione deve rispettare: stesso **gruppo muscolare
primario** e, quando possibile, stessa tipologia (multi-articolare o
isolamento), perché da quella dipende il recupero assegnato
(`rest_periods_and_rir.md`). Cambiare esercizio non deve cambiare lo
stimolo previsto dalla scheda.

Nota su un'idea diffusa e priva di supporto: **non** serve cambiare esercizi
di continuo "per confondere il muscolo". Cambiare troppo spesso impedisce
anche di misurare i progressi sullo stesso movimento.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentRecommendationLog,
    Exercise,
    ExercisePreference,
    RecommendationType,
    UserProfile,
    WorkoutPlanExercise,
)
from app.services import exercise_library
from app.services.workout_generator import _is_usable, _available_equipment_filter

logger = logging.getLogger("exercise_swap")


class SwapError(RuntimeError):
    """Sostituzione non possibile (esercizio inesistente o nessuna alternativa)."""


@dataclass
class Alternative:
    exercise: Exercise
    same_type: bool          # stessa tipologia multi-articolare/isolamento
    already_preferred: bool  # già segnato come gradito dall'utente

    @property
    def preserves_stimulus(self) -> bool:
        """Se la tipologia coincide, la sostituzione non altera nemmeno il
        tempo di recupero previsto dalla scheda."""
        return self.same_type


def find_alternatives(
    db: Session,
    profile: UserProfile,
    exercise: Exercise,
    *,
    limit: int = 5,
) -> list[Alternative]:
    """Alternative per lo stesso gruppo muscolare primario.

    Ordinamento: prima quelle già gradite dall'utente, poi quelle che
    preservano la tipologia (e quindi il recupero), infine gli esercizi con
    immagine e descrizione, che in wger sono i più curati.
    """
    if not exercise.primary_muscle:
        raise SwapError(
            f"L'esercizio «{exercise.name}» non ha un gruppo muscolare primario: "
            "impossibile trovare un'alternativa equivalente."
        )

    allowed = _available_equipment_filter(profile)

    preferenze = {
        p.exercise_id: p.is_preferred
        for p in db.scalars(
            select(ExercisePreference).where(
                ExercisePreference.profile_id == profile.id
            )
        )
    }

    candidati = db.scalars(
        select(Exercise)
        .where(
            Exercise.primary_muscle == exercise.primary_muscle,
            Exercise.id != exercise.id,
            exercise_library.catalog_condition(db),
        )
        .order_by(*exercise_library.catalog_order())
    )

    alternative = [
        Alternative(
            exercise=candidato,
            same_type=candidato.is_compound == exercise.is_compound,
            already_preferred=preferenze.get(candidato.id, False),
        )
        for candidato in candidati
        # Gli esercizi che l'utente ha esplicitamente segnato come sgraditi
        # non vanno riproposti: sarebbe il contrario dello scopo.
        if preferenze.get(candidato.id, True) is not False
        and _is_usable(candidato, allowed)
    ]

    alternative.sort(
        key=lambda a: (
            not a.already_preferred,
            not a.same_type,
            # A parità di tipologia, prima le varianti in allungamento
            # (`biomechanics_technique.md`).
            exercise_library.lengthened_rank(a.exercise),
            a.exercise.priority if a.exercise.priority is not None else 100,
            a.exercise.name,
        )
    )
    return alternative[:limit]


def set_preference(
    db: Session, profile: UserProfile, exercise: Exercise, *, preferred: bool, note: str | None = None
) -> ExercisePreference:
    """Registra se un esercizio piace o no, per le schede successive."""
    existing = db.scalar(
        select(ExercisePreference).where(
            ExercisePreference.profile_id == profile.id,
            ExercisePreference.exercise_id == exercise.id,
        )
    )
    if existing is not None:
        existing.is_preferred = preferred
        existing.note = note
        db.commit()
        return existing

    preference = ExercisePreference(
        profile_id=profile.id,
        exercise_id=exercise.id,
        is_preferred=preferred,
        note=note,
    )
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


def swap_in_plan(
    db: Session,
    profile: UserProfile,
    plan_exercise: WorkoutPlanExercise,
    replacement: Exercise,
    *,
    mark_old_as_disliked: bool = False,
) -> WorkoutPlanExercise:
    """Sostituisce un esercizio nella scheda, mantenendone i parametri.

    Serie, ripetizioni e RIR restano invariati perché dipendono dal volume
    programmato, non dal singolo movimento. Il recupero viene ricalcolato
    solo se cambia la tipologia dell'esercizio: è l'unico parametro legato
    al tipo di movimento (`rest_periods_and_rir.md`).
    """
    from app.services.workout_generator import (
        REST_COMPOUND_SECONDS,
        REST_ISOLATION_SECONDS,
        REST_STRENGTH_SECONDS,
    )

    if replacement.primary_muscle != plan_exercise.exercise.primary_muscle:
        raise SwapError(
            f"«{replacement.name}» allena {replacement.primary_muscle}, mentre "
            f"«{plan_exercise.exercise.name}» allena "
            f"{plan_exercise.exercise.primary_muscle}: la sostituzione "
            "cambierebbe lo stimolo previsto dalla scheda."
        )

    vecchio = plan_exercise.exercise

    # Il recupero da forza (esercizi con carichi alti e poche ripetizioni) non
    # va ricalcolato sulla tipologia: dipende dall'obiettivo, non dal movimento.
    if plan_exercise.rest_seconds != REST_STRENGTH_SECONDS:
        plan_exercise.rest_seconds = (
            REST_COMPOUND_SECONDS if replacement.is_compound else REST_ISOLATION_SECONDS
        )

    plan_exercise.exercise_id = replacement.id

    if mark_old_as_disliked:
        set_preference(db, profile, vecchio, preferred=False, note="sostituito nella scheda")
    set_preference(db, profile, replacement, preferred=True, note="scelto dall'utente")

    db.add(
        AgentRecommendationLog(
            profile_id=profile.id,
            recommendation_type=RecommendationType.EXERCISE_SWAPPED,
            reference_id=plan_exercise.workout_plan_id,
            summary=(
                f"«{vecchio.name}» sostituito con «{replacement.name}» "
                f"({replacement.primary_muscle}). Serie, ripetizioni e RIR "
                f"invariati; recupero {plan_exercise.rest_seconds}s."
            ),
            knowledge_source_tags="scelta_esercizi,recupero",
            used_llm=False,
        )
    )

    db.commit()
    db.refresh(plan_exercise)
    return plan_exercise
