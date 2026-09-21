"""Storico dei carichi: sessioni, serie e parametri della scheda modificabili.

Il percorso vero: si apre il giorno della scheda, si segnano le serie una a
una, si corregge un carico settimane dopo, si guarda la progressione. E
nessuno deve poter leggere o toccare le serie di un altro.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import Exercise, WorkoutPlan, WorkoutPlanExercise, WorkoutSession

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


# --- Parametri della scheda ----------------------------------------------------------


def test_parametri_della_scheda_modificabili(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _, riga, _, _ = _scheda(db, pid)

    r = client.patch(f"/workout/plan-exercises/{riga.id}?profile_id={pid}", headers=h, json={
        "target_sets": 4, "target_reps_min": 8, "target_reps_max": 10, "target_rir": 1, "rest_seconds": 120,
    })
    assert r.status_code == 200, r.text
    ex = r.json()["exercises"][0]
    assert (ex["target_sets"], ex["target_reps_min"], ex["target_reps_max"], ex["target_rir"], ex["rest_seconds"]) == (4, 8, 10, 1, 120)


def test_ripetizioni_minime_oltre_le_massime_rifiutate(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _, riga, _, _ = _scheda(db, pid)
    r = client.patch(f"/workout/plan-exercises/{riga.id}?profile_id={pid}", headers=h, json={"target_reps_min": 12})
    assert r.status_code == 422


# --- Una sessione, serie dopo serie ---------------------------------------------------


def test_sessione_serie_per_serie_e_ripresa(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, _ = _scheda(db, pid)

    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h,
                    json={"day_label": "A", "workout_plan_id": piano.id})
    assert s.status_code == 201 and s.json()["sets"] == []
    sid = s.json()["id"]

    for n, kg in ((1, 60), (2, 62.5)):
        r = client.post(f"/workout/sessions/{sid}/sets", headers=h,
                        json={"exercise_id": panca.id, "set_number": n, "reps": 8, "weight_kg": kg, "rir": 2})
        assert r.status_code == 201, r.text

    # Riaprendo la pagina a metà allenamento si ritrova la sessione.
    ripresa = client.get(f"/workout/sessions/current?profile_id={pid}&day_label=A&plan_id={piano.id}", headers=h)
    assert ripresa.json()["id"] == sid
    assert [x["weight_kg"] for x in ripresa.json()["sets"]] == [60, 62.5]


def test_carico_corretto_dopo_senza_toccare_le_altre_sessioni(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, _ = _scheda(db, pid)

    ids = []
    for giorni_fa, kg in ((14, 55), (7, 60)):
        s = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
            "day_label": "A", "workout_plan_id": piano.id,
            "date": str(dt.date.today() - dt.timedelta(days=giorni_fa)),
            "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 8, "weight_kg": kg}],
        })
        ids.append(s.json()["sets"][0]["id"])

    client.patch(f"/workout/sets/{ids[0]}", headers=h, json={"weight_kg": 57.5})

    storia = client.get(f"/workout/exercises/{panca.id}/history?profile_id={pid}", headers=h).json()
    assert storia["exercise_name"] == "Panca piana"
    # Dalla più recente; la correzione ha cambiato solo la sessione vecchia.
    assert [x["top_weight_kg"] for x in storia["sessions"]] == [60, 57.5]
    assert storia["sessions"][0]["best_e1rm"] == pytest.approx(76.0)


def test_ultima_volta_esclude_la_sessione_in_corso(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, squat = _scheda(db, pid)

    client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "day_label": "A", "date": str(dt.date.today() - dt.timedelta(days=3)),
        "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 8, "weight_kg": 60}],
    })
    oggi = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "day_label": "A", "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 8, "weight_kg": 65}],
    }).json()["id"]

    r = client.get(
        f"/workout/last-performance?profile_id={pid}&exercise_ids={panca.id}&exercise_ids={squat.id}"
        f"&exclude_session_id={oggi}", headers=h,
    ).json()
    assert r[str(panca.id)]["top_weight_kg"] == 60
    assert str(squat.id) not in r  # mai eseguito


def test_elenco_esercizi_con_carichi(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _, _, panca, squat = _scheda(db, pid)
    for es in (panca, panca, squat):
        client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
            "day_label": "A", "sets": [{"exercise_id": es.id, "set_number": 1, "reps": 5, "weight_kg": 80}],
        })
    righe = client.get(f"/progress/loads?profile_id={pid}", headers=h).json()
    assert [(r["exercise_name"], r["sessions"]) for r in righe] == [("Panca piana", 2), ("Squat", 1)]


def test_eliminare_una_sessione_toglie_le_sue_serie(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _, _, panca, _ = _scheda(db, pid)
    sid = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "day_label": "A", "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 5, "weight_kg": 80}],
    }).json()["id"]
    assert client.delete(f"/workout/sessions/{sid}", headers=h).status_code == 204
    assert client.get(f"/workout/exercises/{panca.id}/history?profile_id={pid}", headers=h).json()["sessions"] == []


# --- Proprietà ----------------------------------------------------------------------------


def test_serie_e_sessioni_di_un_altro_non_accessibili(ambiente):
    client, db = ambiente
    vittima, pid_v = _account(client, "v@example.com")
    attaccante, pid_a = _account(client, "a@example.com")
    piano, riga, panca, _ = _scheda(db, pid_v)

    s = client.post(f"/workout/sessions?profile_id={pid_v}", headers=vittima, json={
        "day_label": "A", "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 5, "weight_kg": 80}],
    }).json()
    sid, set_id = s["id"], s["sets"][0]["id"]

    assert client.patch(f"/workout/sets/{set_id}", headers=attaccante, json={"weight_kg": 1}).status_code == 404
    assert client.delete(f"/workout/sets/{set_id}", headers=attaccante).status_code == 404
    assert client.post(f"/workout/sessions/{sid}/sets", headers=attaccante,
                       json={"exercise_id": panca.id, "set_number": 2, "reps": 1, "weight_kg": 1}).status_code == 404
    assert client.patch(f"/workout/sessions/{sid}", headers=attaccante, json={"note": "x"}).status_code == 404
    assert client.delete(f"/workout/sessions/{sid}", headers=attaccante).status_code == 404
    assert client.patch(f"/workout/plan-exercises/{riga.id}?profile_id={pid_a}", headers=attaccante,
                        json={"target_sets": 9}).status_code == 404
    # Una sessione non si aggancia alla scheda di un altro.
    assert client.post(f"/workout/sessions?profile_id={pid_a}", headers=attaccante,
                       json={"day_label": "A", "workout_plan_id": piano.id}).status_code == 404
    # Lo storico dell'attaccante non contiene le serie della vittima.
    storia = client.get(f"/workout/exercises/{panca.id}/history?profile_id={pid_a}", headers=attaccante).json()
    assert storia["sessions"] == []
    assert db.get(WorkoutSession, sid).sets[0].weight_kg == 80
