"""Composizione della scheda: aggiungere e togliere esercizi, volume ricalcolato."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.services import rate_limit
from app.models import Exercise, WorkoutPlan, WorkoutPlanExercise
from app.services import workout_generator as wg

PASSWORD = "passwordlunga1"


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    def _db():
        yield db

    monkeypatch.setattr(get_settings(), "secret_key", "chiave-di-test-" + "x" * 40)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    # I limiti per indirizzo sono in memoria e condivisi fra i test: senza
    # azzerarli, le registrazioni dei test precedenti ricevono un 429.
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


def _scheda(db, profile_id):
    panca = Exercise(name="Bench Press", name_it="Panca piana", primary_muscle="Chest", is_compound=True)
    squat = Exercise(name="Squat", name_it="Squat", primary_muscle="Quads", is_compound=True)
    db.add_all([panca, squat])
    db.flush()
    piano = WorkoutPlan(
        profile_id=profile_id, name="Full body", goal="hypertrophy", days_per_week=3,
        started_at=dt.date.today(),
    )
    db.add(piano)
    db.flush()
    riga = WorkoutPlanExercise(
        workout_plan_id=piano.id, exercise_id=panca.id, day_label="A", target_sets=3,
        target_reps_min=6, target_reps_max=8, target_rir=2, rest_seconds=150,
    )
    db.add(riga)
    db.commit()
    return piano, riga, panca, squat



def _scheda_due_esercizi(db, pid):
    piano, riga, panca, squat = _scheda(db, pid)
    db.add(WorkoutPlanExercise(
        workout_plan_id=piano.id, exercise_id=squat.id, day_label="A", target_sets=3,
        target_reps_min=6, target_reps_max=8, target_rir=2, rest_seconds=150,
    ))
    curl = Exercise(name="Barbell Curl", name_it="Curl con bilanciere", primary_muscle="Biceps", is_compound=False)
    db.add(curl)
    db.commit()
    return piano, curl


def test_aggiungere_un_esercizio_oltre_il_tetto_del_generatore(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, curl = _scheda_due_esercizi(db, pid)
    altri = [Exercise(name=f"Fly {i}", primary_muscle="Chest", is_compound=False) for i in range(8)]
    db.add_all(altri)
    db.commit()

    for ex in [curl, *altri]:
        r = client.post(f"/workout/plans/{piano.id}/exercises?profile_id={pid}", headers=h,
                        json={"exercise_id": ex.id, "day_label": "A"})
        assert r.status_code == 201, r.text
    giorno = [e for e in r.json()["exercises"] if e["day_label"] == "A"]
    assert len(giorno) == 11 > wg.MAX_EXERCISES_PER_SESSION
    nuovo = next(e for e in giorno if e["exercise"]["id"] == curl.id)
    # Parametri delle fonti per un isolamento: 3 serie, 8-10, recupero da isolamento.
    assert (nuovo["target_sets"], nuovo["target_reps_min"], nuovo["target_reps_max"]) == (3, 8, 10)
    assert nuovo["rest_seconds"] == wg.REST_ISOLATION_SECONDS


def test_aggiungere_a_un_giorno_che_non_esiste(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, curl = _scheda_due_esercizi(db, pid)
    r = client.post(f"/workout/plans/{piano.id}/exercises?profile_id={pid}", headers=h,
                    json={"exercise_id": curl.id, "day_label": "Z"})
    assert r.status_code == 422


def test_togliere_un_esercizio_ma_non_l_ultimo_del_giorno(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _ = _scheda_due_esercizi(db, pid)
    righe = [e["id"] for e in client.get(f"/workout/plans?profile_id={pid}", headers=h).json()[0]["exercises"]]

    r = client.delete(f"/workout/plan-exercises/{righe[0]}?profile_id={pid}", headers=h)
    assert r.status_code == 200, r.text
    assert [e["id"] for e in r.json()["exercises"]] == righe[1:]
    r = client.delete(f"/workout/plan-exercises/{righe[1]}?profile_id={pid}", headers=h)
    assert r.status_code == 409


def test_la_scheda_di_un_altro_non_si_modifica(ambiente):
    client, db = ambiente
    _, pid = _account(client, "a@example.com")
    h_altro, pid_altro = _account(client, "b@example.com")
    piano, curl = _scheda_due_esercizi(db, pid)
    riga = piano.exercises[0].id
    assert client.post(f"/workout/plans/{piano.id}/exercises?profile_id={pid_altro}", headers=h_altro,
                       json={"exercise_id": curl.id, "day_label": "A"}).status_code == 404
    assert client.delete(f"/workout/plan-exercises/{riga}?profile_id={pid_altro}", headers=h_altro).status_code == 404


def test_volume_ricalcolato_con_gli_avvisi(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _ = _scheda_due_esercizi(db, pid)
    r = client.get(f"/workout/plans/{piano.id}/volume?profile_id={pid}", headers=h)
    assert r.status_code == 200, r.text
    dati = r.json()
    assert dati["weekly_sets_equivalent"]["Chest"] == 3
    assert "Hamstrings" not in dati["weekly_sets_equivalent"]
    assert any("petto 3" in a for a in dati["warnings"])


def test_candidati_da_aggiungere_senza_quelli_gia_in_scheda(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _ = _scheda_due_esercizi(db, pid)
    db.add(Exercise(name="Dumbbell Fly", primary_muscle="Chest", is_compound=False))
    db.commit()
    r = client.get(f"/workout/plans/{piano.id}/candidates?profile_id={pid}&muscle=Chest", headers=h)
    assert r.status_code == 200, r.text
    assert [c["exercise"]["name"] for c in r.json()] == ["Dumbbell Fly"]


def test_riordinare_gli_esercizi_di_un_giorno(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, curl = _scheda_due_esercizi(db, pid)
    r = client.post(f"/workout/plans/{piano.id}/exercises?profile_id={pid}", headers=h,
                    json={"exercise_id": curl.id, "day_label": "A"})
    prima = [e["id"] for e in r.json()["exercises"]]

    nuovo_ordine = list(reversed(prima))
    r = client.put(f"/workout/plans/{piano.id}/order?profile_id={pid}", headers=h,
                   json={"day_label": "A", "plan_exercise_ids": nuovo_ordine})
    assert r.status_code == 200, r.text
    assert [e["id"] for e in r.json()["exercises"]] == nuovo_ordine
    # L'ordine resta anche rileggendo la scheda.
    assert [e["id"] for e in client.get(f"/workout/plans?profile_id={pid}", headers=h).json()[0]["exercises"]] == nuovo_ordine

    # Un elenco che non corrisponde al giorno viene rifiutato.
    r = client.put(f"/workout/plans/{piano.id}/order?profile_id={pid}", headers=h,
                   json={"day_label": "A", "plan_exercise_ids": nuovo_ordine[:-1]})
    assert r.status_code == 409


def test_i_giorni_restano_in_ordine_dopo_un_riordino(ambiente):
    """Gli esercizi arrivano ordinati per posizione nel giorno: un esercizio
    aggiunto ad A e portato in cima non deve far passare B e C davanti."""
    from app.services import plan_editing

    client, db = ambiente
    _, profile_id = _account(client, "ordine@example.com")
    piano = WorkoutPlan(
        profile_id=profile_id, name="Full body", goal="hypertrophy", days_per_week=3,
        started_at=dt.date.today(),
    )
    db.add(piano)
    db.flush()
    esercizi = [Exercise(name=f"Ex {i}", primary_muscle="Chest", is_compound=True) for i in range(4)]
    db.add_all(esercizi)
    db.flush()
    for giorno, ex in zip(("A", "B", "C", "A"), esercizi):
        db.add(WorkoutPlanExercise(
            workout_plan_id=piano.id, exercise_id=ex.id, day_label=giorno,
            order_index=1 if ex is esercizi[3] else 0,
            target_sets=3, target_reps_min=6, target_reps_max=8, target_rir=2, rest_seconds=150,
        ))
    db.commit()
    db.refresh(piano)
    giorno_a = [e.id for e in piano.exercises if e.day_label == "A"]
    plan_editing.reorder_day(db, piano, "A", list(reversed(giorno_a)))

    assert piano.exercises[0].day_label != "A"  # l'ordine grezzo mette B davanti
    assert plan_editing.day_labels(piano) == ["A", "B", "C"]
