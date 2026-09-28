"""Cancellazione dei dati di una persona, tutta o in parte.

Due usi:

- `reset_everything`: il pulsante "Azzera dati" del Profilo. Cancella i
  profili dell'utente con tutto quello che contengono; restano l'account
  (email e password), i dispositivi iscritti alle notifiche e i prodotti
  inseriti a mano. Al prossimo accesso si riparte dall'onboarding.
- `reset_tracking`: scheda con allenamenti, integratori e diario, tenendo
  al massimo un giorno del diario. Lo usa `scripts/reset_dati.py`.

Le righe figlie si cancellano esplicitamente, seguendo le chiavi esterne del
modello, invece di affidarsi al `ON DELETE CASCADE` del database: SQLite (i
test) non lo applica se non glielo si chiede, e così si può anche fare una
copia di tutto quello che sparisce prima di cancellarlo.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import ColumnElement, Table, delete, select, update
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    AgentRecommendationLog,
    MealLog,
    NotificationLog,
    NotificationSettings,
    SupplementDeclaration,
    TrainingFeedback,
    User,
    UserProfile,
    WorkoutPlan,
    WorkoutSession,
)

# Tabella -> righe cancellate, così come erano: la copia di sicurezza.
Backup = dict[str, list[dict[str, Any]]]


def _delete(db: Session, table: Table, where: ColumnElement[bool], backup: Backup) -> None:
    """Cancella le righe di `table` che soddisfano `where`, figlie comprese."""
    ids = select(table.c.id).where(where)
    for figlia in Base.metadata.sorted_tables:
        for fk in figlia.foreign_keys:
            if fk.column is not table.c.id:
                continue
            if (fk.ondelete or "").upper() == "CASCADE":
                _delete(db, figlia, fk.parent.in_(ids), backup)
            elif (fk.ondelete or "").upper() == "SET NULL":
                db.execute(update(figlia).where(fk.parent.in_(ids)).values({fk.parent.name: None}))
    righe = [dict(r) for r in db.execute(select(table).where(where)).mappings()]
    if righe:
        backup.setdefault(table.name, []).extend(righe)
        db.execute(delete(table).where(where))


def reset_tracking(db: Session, profile: UserProfile, *, keep_diary_day: dt.date | None = None) -> Backup:
    """Scheda e allenamenti, integratori, diario (tranne `keep_diary_day`).

    Non tocca i dati del profilo, le pesate, le ricette salvate né le
    preferenze sugli esercizi. Non fa commit: decide chi chiama.
    """
    backup: Backup = {}
    diario = MealLog.profile_id == profile.id
    if keep_diary_day is not None:
        diario = diario & (MealLog.date != keep_diary_day)
    for model, where in (
        (WorkoutSession, WorkoutSession.profile_id == profile.id),
        (TrainingFeedback, TrainingFeedback.profile_id == profile.id),
        (AgentRecommendationLog, AgentRecommendationLog.profile_id == profile.id),
        (WorkoutPlan, WorkoutPlan.profile_id == profile.id),
        (SupplementDeclaration, SupplementDeclaration.profile_id == profile.id),
        (MealLog, diario),
    ):
        _delete(db, model.__table__, where, backup)
    return backup


def reset_everything(db: Session, user: User) -> Backup:
    """Tutti i profili dell'utente e le sue notifiche già mandate. Fa commit."""
    backup: Backup = {}
    _delete(db, UserProfile.__table__, UserProfile.user_id == user.id, backup)
    _delete(db, NotificationLog.__table__, NotificationLog.user_id == user.id, backup)
    _delete(db, NotificationSettings.__table__, NotificationSettings.user_id == user.id, backup)
    db.commit()
    db.expire_all()
    return backup


def counts(backup: Backup) -> dict[str, int]:
    return {tabella: len(righe) for tabella, righe in sorted(backup.items())}
