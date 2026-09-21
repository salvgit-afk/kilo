"""Storico dei carichi: cosa si è sollevato, sessione per sessione.

Lo schema c'era da tempo (`WorkoutSession` e `SessionSet`, una riga per ogni
serie eseguita), ma nessuna schermata lo riempiva. Questo modulo è la parte
di lettura: l'ultima volta che si è fatto un esercizio, lo storico completo
di un esercizio e la serie di punti per il grafico della progressione.

Un carico non si sovrascrive mai: ogni sessione ha le sue serie, e
correggerne una cambia solo quella serie. È ciò che rende leggibile la
progressione nel tempo.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Exercise, SessionSet, WorkoutSession


@dataclass
class SessionEntry:
    """Le serie di un esercizio in una sessione."""

    session: WorkoutSession
    sets: list[SessionSet] = field(default_factory=list)

    @property
    def top_weight_kg(self) -> float:
        return max((s.weight_kg for s in self.sets), default=0.0)

    @property
    def best_e1rm(self) -> float:
        """Massimale stimato della serie migliore (Epley), per confrontare
        sessioni con ripetizioni diverse."""
        return max((s.estimated_1rm for s in self.sets), default=0.0)

    @property
    def volume_kg(self) -> float:
        return round(sum(s.weight_kg * s.reps for s in self.sets), 1)


def exercise_history(
    db: Session,
    profile_id: int,
    exercise_id: int,
    *,
    since: dt.date | None = None,
    exclude_session_id: int | None = None,
    limit: int = 60,
) -> list[SessionEntry]:
    """Le sessioni in cui compare l'esercizio, dalla più recente."""
    query = (
        select(SessionSet, WorkoutSession)
        .join(WorkoutSession, SessionSet.workout_session_id == WorkoutSession.id)
        .where(WorkoutSession.profile_id == profile_id, SessionSet.exercise_id == exercise_id)
        .order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc(), SessionSet.set_number)
    )
    if since is not None:
        query = query.where(WorkoutSession.date >= since)
    if exclude_session_id is not None:
        query = query.where(WorkoutSession.id != exclude_session_id)

    per_sessione: dict[int, SessionEntry] = {}
    for serie, sessione in db.execute(query):
        voce = per_sessione.get(sessione.id)
        if voce is None:
            if len(per_sessione) >= limit:
                break
            voce = per_sessione[sessione.id] = SessionEntry(sessione)
        voce.sets.append(serie)
    return list(per_sessione.values())


def last_performance(
    db: Session,
    profile_id: int,
    exercise_ids: list[int],
    *,
    exclude_session_id: int | None = None,
) -> dict[int, SessionEntry]:
    """Per ogni esercizio, l'ultima sessione in cui è stato eseguito.

    È il riferimento che serve in palestra: "l'ultima volta 3×8 a 60 kg".
    """
    risultato: dict[int, SessionEntry] = {}
    for exercise_id in dict.fromkeys(exercise_ids):
        storia = exercise_history(
            db, profile_id, exercise_id, exclude_session_id=exclude_session_id, limit=1
        )
        if storia:
            risultato[exercise_id] = storia[0]
    return risultato


@dataclass
class LoggedExercise:
    exercise: Exercise
    sessions: int
    last_date: dt.date


def logged_exercises(
    db: Session, profile_id: int, *, since: dt.date | None = None
) -> list[LoggedExercise]:
    """Gli esercizi con almeno una sessione registrata, i più frequenti prima.

    Alimenta il selettore del grafico dei carichi nel resoconto.
    """
    query = (
        select(
            Exercise,
            func.count(func.distinct(WorkoutSession.id)),
            func.max(WorkoutSession.date),
        )
        .join(SessionSet, SessionSet.exercise_id == Exercise.id)
        .join(WorkoutSession, SessionSet.workout_session_id == WorkoutSession.id)
        .where(WorkoutSession.profile_id == profile_id)
        .group_by(Exercise.id)
    )
    if since is not None:
        query = query.where(WorkoutSession.date >= since)
    righe = [LoggedExercise(ex, n, ultima) for ex, n, ultima in db.execute(query)]
    righe.sort(key=lambda r: (-r.sessions, r.exercise.name))
    return righe


@dataclass
class SessionRecord:
    exercise: Exercise
    weight_kg: float
    previous_best_kg: float | None


@dataclass
class SessionSummary:
    session: WorkoutSession
    duration_seconds: int | None
    sets_count: int
    exercises_count: int
    volume_kg: float
    records: list[SessionRecord]


def summarize_session(db: Session, session: WorkoutSession) -> SessionSummary:
    """Il riepilogo di fine allenamento.

    Un record è un carico mai sollevato prima su quell'esercizio, in nessuna
    sessione precedente. Alla prima volta non c'è record: senza un termine
    di paragone non si è battuto niente.
    """
    durata = None
    if session.started_at and session.ended_at:
        durata = max(0, int((session.ended_at - session.started_at).total_seconds()))

    per_esercizio: dict[int, list[SessionSet]] = {}
    for s in session.sets:
        per_esercizio.setdefault(s.exercise_id, []).append(s)

    record: list[SessionRecord] = []
    for exercise_id, serie in per_esercizio.items():
        oggi = max(s.weight_kg for s in serie)
        precedente = db.scalar(
            select(func.max(SessionSet.weight_kg))
            .join(WorkoutSession, SessionSet.workout_session_id == WorkoutSession.id)
            .where(
                WorkoutSession.profile_id == session.profile_id,
                SessionSet.exercise_id == exercise_id,
                WorkoutSession.id != session.id,
                WorkoutSession.date <= session.date,
            )
        )
        if precedente is not None and oggi > precedente:
            record.append(SessionRecord(serie[0].exercise, oggi, precedente))

    return SessionSummary(
        session=session,
        duration_seconds=durata,
        sets_count=len(session.sets),
        exercises_count=len(per_esercizio),
        volume_kg=round(sum(s.weight_kg * s.reps for s in session.sets), 1),
        records=record,
    )
