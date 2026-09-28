"""Azzeramento dei dati: tutto (pulsante del Profilo) o in parte (script).

Conta soprattutto che sparisca solo quello che deve: la colazione di oggi
resta, le pesate restano, e i dati di un'altra persona non si toccano mai.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import (
    Exercise,
    MealItem,
    MealLog,
    SessionSet,
    SupplementDeclaration,
    SupplementIntake,
    UserProfile,
    WeightLog,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
)
from app.services import clock, data_reset, rate_limit

PASSWORD = "passwordlunga1"
OGGI = clock.today()
IERI = OGGI - dt.timedelta(days=1)


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    def _db():
        yield db

    monkeypatch.setattr(get_settings(), "secret_key", "chiave-di-test-" + "x" * 40)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    for finestra in (rate_limit.LOGIN_PER_IP, rate_limit.LOGIN_FAILURES_PER_EMAIL, rate_limit.REGISTER_PER_IP):
        finestra.reset()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _account(client, email):
    r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    p = client.post("/profile", headers=h, json={
        "display_name": "x", "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    })
    return h, p.json()["id"]


def _riempi(db, profile_id, esercizio):
    """Una scheda con una sessione, un integratore con un'assunzione, due giorni di diario, una pesata."""
    piano = WorkoutPlan(profile_id=profile_id, name="Full body", goal="hypertrophy", days_per_week=3, started_at=IERI)
    db.add(piano)
    db.flush()
    db.add(WorkoutPlanExercise(
        workout_plan_id=piano.id, exercise_id=esercizio.id, day_label="A", target_sets=3,
        target_reps_min=6, target_reps_max=8, target_rir=2, rest_seconds=90,
    ))
    sessione = WorkoutSession(profile_id=profile_id, workout_plan_id=piano.id, date=IERI, day_label="A")
    db.add(sessione)
    db.flush()
    db.add(SessionSet(workout_session_id=sessione.id, exercise_id=esercizio.id, set_number=1, reps=8, weight_kg=60))
    creatina = SupplementDeclaration(profile_id=profile_id, kind="creatine")
    db.add(creatina)
    db.flush()
    db.add(SupplementIntake(supplement_id=creatina.id, date=IERI))
    for giorno in (IERI, OGGI):
        pasto = MealLog(profile_id=profile_id, date=giorno, meal_type="breakfast")
        db.add(pasto)
        db.flush()
        db.add(MealItem(meal_log_id=pasto.id, name="Avena", quantity_g=50, kcal=190, protein_g=6, carbs_g=30, fat_g=3))
    db.add(WeightLog(profile_id=profile_id, date=IERI, weight_kg=78))
    db.commit()


def _conta(db, model, **filtri):
    q = select(func.count()).select_from(model)
    for k, v in filtri.items():
        q = q.where(getattr(model, k) == v)
    return db.scalar(q)


def test_reset_parziale_tiene_il_diario_di_oggi(ambiente):
    client, db = ambiente
    _, pid = _account(client, "a@example.com")
    _, altro = _account(client, "b@example.com")
    panca = Exercise(name="Bench Press", name_it="Panca piana", primary_muscle="Chest", is_compound=True)
    db.add(panca)
    db.flush()
    _riempi(db, pid, panca)
    _riempi(db, altro, panca)

    backup = data_reset.reset_tracking(db, db.get(UserProfile, pid), keep_diary_day=OGGI)
    db.commit()

    assert _conta(db, WorkoutPlan, profile_id=pid) == 0
    assert _conta(db, WorkoutSession, profile_id=pid) == 0
    assert _conta(db, SupplementDeclaration, profile_id=pid) == 0
    assert _conta(db, MealLog, profile_id=pid, date=IERI) == 0
    assert _conta(db, MealLog, profile_id=pid, date=OGGI) == 1
    assert _conta(db, WeightLog, profile_id=pid) == 1
    # Le figlie spariscono con i genitori e finiscono nella copia.
    assert _conta(db, SessionSet) == 1 and _conta(db, SupplementIntake) == 1 and _conta(db, MealItem) == 3
    assert data_reset.counts(backup) == {
        "meal_items": 1, "meal_logs": 1, "session_sets": 1, "supplement_declarations": 1,
        "supplement_intakes": 1, "workout_plan_exercises": 1, "workout_plans": 1, "workout_sessions": 1,
    }
    # L'altra persona non perde niente.
    assert _conta(db, WorkoutPlan, profile_id=altro) == 1
    assert _conta(db, MealLog, profile_id=altro) == 2


def test_azzera_dati_riporta_all_onboarding(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _, altro = _account(client, "b@example.com")
    panca = Exercise(name="Bench Press", name_it="Panca piana", primary_muscle="Chest", is_compound=True)
    db.add(panca)
    db.flush()
    _riempi(db, pid, panca)
    _riempi(db, altro, panca)

    r = client.post(f"/profile/{pid}/reset", headers=h, json={"confirm": "azzera"})
    assert r.status_code == 204, r.text

    assert client.get("/auth/me", headers=h).json()["profile"] is None
    assert _conta(db, UserProfile, id=pid) == 0
    assert _conta(db, WeightLog, profile_id=pid) == 0
    assert _conta(db, MealLog, profile_id=pid) == 0
    assert _conta(db, MealLog, profile_id=altro) == 2
    # Con lo stesso account si rifà l'onboarding.
    assert client.post("/profile", headers=h, json={
        "display_name": "x", "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    }).status_code == 201


def test_azzera_dati_vuole_la_conferma_scritta(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    assert client.post(f"/profile/{pid}/reset", headers=h, json={"confirm": "si"}).status_code == 422
    assert _conta(db, UserProfile, id=pid) == 1


def test_azzera_dati_non_si_fa_sul_profilo_altrui(ambiente):
    client, db = ambiente
    _, pid = _account(client, "a@example.com")
    h_altro, _ = _account(client, "b@example.com")
    assert client.post(f"/profile/{pid}/reset", headers=h_altro, json={"confirm": "AZZERA"}).status_code == 404
    assert _conta(db, UserProfile, id=pid) == 1
