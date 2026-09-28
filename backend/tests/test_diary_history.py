"""Storico del diario: si legge e si scrive un giorno passato, e la striscia
della settimana ha le calorie giuste di ogni giorno."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import MealItem, MealLog
from app.services import clock, rate_limit

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


def _pasto(db, profile_id, giorno, kcal):
    pasto = MealLog(profile_id=profile_id, date=giorno, meal_type="lunch")
    db.add(pasto)
    db.flush()
    db.add(MealItem(meal_log_id=pasto.id, name="Riso", quantity_g=100, kcal=kcal, protein_g=7, carbs_g=78, fat_g=1))
    db.commit()


def test_giorni_con_le_calorie(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _pasto(db, pid, IERI, 350)
    _pasto(db, pid, IERI, 150)
    _pasto(db, pid, OGGI - dt.timedelta(days=3), 800)
    _pasto(db, pid, OGGI - dt.timedelta(days=30), 999)  # fuori dall'intervallo

    r = client.get(
        f"/nutrition/diary/days?profile_id={pid}&start={OGGI - dt.timedelta(days=6)}&end={OGGI}", headers=h
    )
    assert r.status_code == 200, r.text
    giorni = {g["date"]: g["kcal"] for g in r.json()["days"]}
    assert giorni == {str(IERI): 500, str(OGGI - dt.timedelta(days=3)): 800}
    assert r.json()["target_kcal"] > 0


def test_intervallo_troppo_lungo_rifiutato(ambiente):
    client, _ = ambiente
    h, pid = _account(client, "a@example.com")
    r = client.get(f"/nutrition/diary/days?profile_id={pid}&start=2026-01-01&end=2026-06-01", headers=h)
    assert r.status_code == 422


def test_diario_di_ieri(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _pasto(db, pid, IERI, 420)
    ieri = client.get(f"/nutrition/diary?profile_id={pid}&date={IERI}", headers=h).json()
    oggi = client.get(f"/nutrition/diary?profile_id={pid}&date={OGGI}", headers=h).json()
    assert ieri["totals"]["kcal"] == 420 and len(ieri["meals"]) == 1
    assert oggi["meals"] == []


def test_lo_storico_altrui_non_si_legge(ambiente):
    client, db = ambiente
    _, pid = _account(client, "a@example.com")
    h_altro, _ = _account(client, "b@example.com")
    r = client.get(f"/nutrition/diary/days?profile_id={pid}&start={IERI}&end={OGGI}", headers=h_altro)
    assert r.status_code == 404
