"""Promemoria della giornata: cosa l'utente non ha ancora segnato oggi.

Pensati per non dare fastidio. Ricordano solo abitudini che l'utente ha già:
  - gli integratori, solo se ne ha dichiarati;
  - il diario, solo se lo ha usato di recente. A chi non conta le calorie
    non va ricordato ogni giorno di farlo;
  - l'allenamento, solo nei giorni scelti per la scheda e finché la sessione
    di oggi non è iniziata (avviata o con almeno una serie segnata).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    MealItem,
    MealLog,
    SessionSet,
    SupplementDeclaration,
    UserProfile,
    WorkoutPlan,
    WorkoutSession,
)
from app.services import supplement_intake

# Il diario conta come "in uso" se c'è almeno un pasto in questi giorni.
DIARY_RECENT_DAYS = 14


@dataclass
class DailyReminders:
    supplements: list[tuple[SupplementDeclaration, int]] = field(default_factory=list)
    meals_missing: bool = False
    # Schede con allenamento previsto oggi e non ancora iniziato.
    workouts_due: list[WorkoutPlan] = field(default_factory=list)


def _has_food(db: Session, profile: UserProfile, start: dt.date, end: dt.date) -> bool:
    """C'è almeno un alimento o un pasto libero registrato fra `start` ed `end`?"""
    return (
        db.scalar(
            select(MealLog.id)
            .outerjoin(MealItem, MealItem.meal_log_id == MealLog.id)
            .where(
                MealLog.profile_id == profile.id,
                MealLog.date >= start,
                MealLog.date <= end,
                MealLog.is_planned.is_(False),
                or_(MealItem.id.is_not(None), MealLog.kcal.is_not(None)),
            )
            .limit(1)
        )
        is not None
    )


def workouts_due(db: Session, profile: UserProfile, today: dt.date) -> list[WorkoutPlan]:
    """Schede attive che prevedono allenamento oggi, senza sessione iniziata."""
    previste = [
        p
        for p in db.scalars(
            select(WorkoutPlan).where(
                WorkoutPlan.profile_id == profile.id, WorkoutPlan.is_active.is_(True)
            )
        )
        if today.weekday() in p.training_weekdays
    ]
    if not previste:
        return []
    # Iniziata = avviata con il cronometro, oppure con almeno una serie.
    iniziate = set(
        db.scalars(
            select(WorkoutSession.workout_plan_id)
            .outerjoin(SessionSet, SessionSet.workout_session_id == WorkoutSession.id)
            .where(
                WorkoutSession.profile_id == profile.id,
                WorkoutSession.date == today,
                or_(WorkoutSession.started_at.is_not(None), SessionSet.id.is_not(None)),
            )
        )
    )
    return [p for p in previste if p.id not in iniziate]


def build(db: Session, profile: UserProfile, *, today: dt.date) -> DailyReminders:
    usa_il_diario = _has_food(
        db, profile, today - dt.timedelta(days=DIARY_RECENT_DAYS), today - dt.timedelta(days=1)
    )
    return DailyReminders(
        supplements=supplement_intake.pending(db, profile, today=today),
        meals_missing=usa_il_diario and not _has_food(db, profile, today, today),
        workouts_due=workouts_due(db, profile, today),
    )
