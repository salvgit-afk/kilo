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
from app.services import rate_limit
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


# --- Giorni della settimana ------------------------------------------------------------


def test_scheda_senza_giorni_salvati_riceve_la_proposta(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _scheda(db, pid)  # 3 giorni a settimana, creata prima di questa funzione
    piani = client.get(f"/workout/plans?profile_id={pid}", headers=h).json()
    assert piani[0]["training_weekdays"] == [0, 2, 4]  # lunedì, mercoledì, venerdì


def test_giorni_modificabili_e_frequenza_allineata(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, _, _ = _scheda(db, pid)

    r = client.put(f"/workout/plans/{piano.id}/schedule?profile_id={pid}", headers=h,
                   json={"weekdays": [6, 0, 2, 4, 2]})
    assert r.status_code == 200, r.text
    assert r.json()["training_weekdays"] == [0, 2, 4, 6]  # ordinati, senza doppioni
    assert r.json()["days_per_week"] == 4
    profilo = client.get(f"/profile/{pid}", headers=h).json()
    assert profilo["training_days_per_week"] == 4


@pytest.mark.parametrize("giorni", [[], [7], [-1, 2]])
def test_giorni_non_validi_rifiutati(ambiente, giorni):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, _, _ = _scheda(db, pid)
    r = client.put(f"/workout/plans/{piano.id}/schedule?profile_id={pid}", headers=h, json={"weekdays": giorni})
    assert r.status_code == 422


def test_giorni_della_scheda_di_un_altro_non_modificabili(ambiente):
    client, db = ambiente
    _, pid_v = _account(client, "v@example.com")
    attaccante, pid_a = _account(client, "a@example.com")
    piano, _, _, _ = _scheda(db, pid_v)
    r = client.put(f"/workout/plans/{piano.id}/schedule?profile_id={pid_a}", headers=attaccante,
                   json={"weekdays": [1]})
    assert r.status_code == 404


# --- Avvio, in corso, fine ----------------------------------------------------------------


def test_allenamento_avviato_resta_in_corso_fino_alla_fine(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, _ = _scheda(db, pid)
    oggi = str(dt.date.today())

    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h,
                    json={"day_label": "A", "workout_plan_id": piano.id, "date": oggi, "start": True}).json()
    assert s["started_at"] and s["ended_at"] is None

    attivo = client.get(f"/workout/sessions/active?profile_id={pid}&today={oggi}", headers=h).json()
    assert attivo["id"] == s["id"]

    client.post(f"/workout/sessions/{s['id']}/sets", headers=h,
                json={"exercise_id": panca.id, "set_number": 1, "reps": 8, "weight_kg": 60})
    r = client.post(f"/workout/sessions/{s['id']}/finish", headers=h)
    assert r.status_code == 200, r.text
    riepilogo = r.json()
    assert riepilogo["duration_seconds"] is not None and riepilogo["duration_seconds"] >= 0
    assert (riepilogo["sets_count"], riepilogo["exercises_count"], riepilogo["volume_kg"]) == (1, 1, 480)
    assert riepilogo["records"] == []  # prima volta: nessun termine di paragone

    assert client.get(f"/workout/sessions/active?profile_id={pid}&today={oggi}", headers=h).json() is None


def test_record_solo_se_mai_sollevato_prima(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, squat = _scheda(db, pid)
    prima = str(dt.date.today() - dt.timedelta(days=3))
    client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "day_label": "A", "date": prima,
        "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 8, "weight_kg": 60},
                 {"exercise_id": squat.id, "set_number": 1, "reps": 5, "weight_kg": 100}],
    })
    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "day_label": "A", "start": True,
        "sets": [{"exercise_id": panca.id, "set_number": 1, "reps": 6, "weight_kg": 62.5},
                 {"exercise_id": squat.id, "set_number": 1, "reps": 5, "weight_kg": 100}],
    }).json()
    record = client.post(f"/workout/sessions/{s['id']}/finish", headers=h).json()["records"]
    assert [(x["exercise_name"], x["weight_kg"], x["previous_best_kg"]) for x in record] == [("Panca piana", 62.5, 60)]


def test_sessione_riaperta_torna_in_corso(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _scheda(db, pid)
    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={"day_label": "A", "start": True}).json()
    client.post(f"/workout/sessions/{s['id']}/finish", headers=h)
    riaperta = client.post(f"/workout/sessions/{s['id']}/start", headers=h).json()
    assert riaperta["ended_at"] is None and riaperta["started_at"] == s["started_at"]


def test_la_data_la_decide_il_telefono(ambiente):
    """Fra mezzanotte e le due il server in UTC ha ancora la data di ieri."""
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    domani = str(dt.date.today() + dt.timedelta(days=1))
    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h,
                    json={"day_label": "A", "date": domani, "start": True}).json()
    assert s["date"] == domani
    corrente = client.get(f"/workout/sessions/current?profile_id={pid}&day_label=A&today={domani}", headers=h).json()
    assert corrente["id"] == s["id"]


def test_allenamento_di_un_altro_non_si_chiude(ambiente):
    client, db = ambiente
    vittima, pid_v = _account(client, "v@example.com")
    attaccante, _ = _account(client, "a@example.com")
    s = client.post(f"/workout/sessions?profile_id={pid_v}", headers=vittima, json={"day_label": "A", "start": True}).json()
    assert client.post(f"/workout/sessions/{s['id']}/finish", headers=attaccante).status_code == 404
    assert client.post(f"/workout/sessions/{s['id']}/start", headers=attaccante).status_code == 404


# --- Carichi segnati fuori dall'allenamento ---------------------------------------------


def test_carichi_segnati_fuori_dall_allenamento(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, _ = _scheda(db, pid)
    ieri = str(dt.date.today() - dt.timedelta(days=1))
    corpo = {"date": ieri, "workout_plan_id": piano.id, "day_label": "A",
             "sets": [{"weight_kg": 60, "reps": 8, "rir": 2}, {"weight_kg": 62.5, "reps": 6}]}

    r = client.post(f"/workout/exercises/{panca.id}/manual-sets?profile_id={pid}", headers=h, json=corpo)
    assert r.status_code == 201, r.text
    sessioni = r.json()["sessions"]
    assert len(sessioni) == 1 and sessioni[0]["date"] == ieri
    assert [(s["weight_kg"], s["reps"], s["set_number"]) for s in sessioni[0]["sets"]] == [(60, 8, 1), (62.5, 6, 2)]
    sessione = db.get(WorkoutSession, sessioni[0]["session_id"])
    assert sessione.started_at is None and "fuori" in (sessione.note or "")

    # Stesso giorno: le serie si aggiungono in coda, nella stessa sessione.
    r = client.post(f"/workout/exercises/{panca.id}/manual-sets?profile_id={pid}", headers=h,
                    json={**corpo, "sets": [{"weight_kg": 65, "reps": 5}]})
    assert [s["set_number"] for s in r.json()["sessions"][0]["sets"]] == [1, 2, 3]
    assert len(r.json()["sessions"]) == 1


def test_carichi_a_mano_non_per_il_futuro_ne_su_schede_altrui(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    h_altro, pid_altro = _account(client, "b@example.com")
    piano, _, panca, _ = _scheda(db, pid)
    fra_tre = str(dt.date.today() + dt.timedelta(days=3))
    serie = [{"weight_kg": 60, "reps": 8}]
    assert client.post(f"/workout/exercises/{panca.id}/manual-sets?profile_id={pid}", headers=h,
                       json={"date": fra_tre, "sets": serie}).status_code == 422
    assert client.post(f"/workout/exercises/{panca.id}/manual-sets?profile_id={pid_altro}", headers=h_altro,
                       json={"date": str(dt.date.today()), "workout_plan_id": piano.id, "sets": serie}).status_code == 404


# --- La scheda in uso ---------------------------------------------------------------


def test_scheda_in_uso_scelta_dal_menu(ambiente):
    client, db = ambiente
    h, pid = _account(client, "uso@example.com")
    tre, *_ = _scheda(db, pid)
    quattro = WorkoutPlan(
        profile_id=pid, name="Push/Pull", goal="hypertrophy", days_per_week=4,
        started_at=dt.date.today() - dt.timedelta(days=10),
    )
    db.add(quattro)
    db.commit()

    # Senza scelta vale la più recente (la full body, iniziata oggi).
    assert client.get(f"/workout/plans/active?profile_id={pid}", headers=h).json()["id"] == tre.id

    r = client.put(f"/workout/plans/{quattro.id}/current?profile_id={pid}", headers=h)
    assert r.status_code == 200 and r.json()["is_current"] is True
    assert client.get(f"/workout/plans/active?profile_id={pid}", headers=h).json()["id"] == quattro.id
    elenco = client.get(f"/workout/plans?profile_id={pid}&active_only=true", headers=h).json()
    assert {p["id"]: p["is_current"] for p in elenco} == {tre.id: False, quattro.id: True}

    # Eliminata quella in uso, torna la più recente fra le altre.
    client.delete(f"/workout/plans/{quattro.id}?profile_id={pid}", headers=h)
    assert client.get(f"/workout/plans/active?profile_id={pid}", headers=h).json()["id"] == tre.id
    # Una scheda archiviata non si sceglie.
    assert client.put(f"/workout/plans/{quattro.id}/current?profile_id={pid}", headers=h).status_code == 404


def test_scheda_di_un_altro_non_si_sceglie(ambiente):
    client, db = ambiente
    h1, pid1 = _account(client, "uno@example.com")
    _, pid2 = _account(client, "due@example.com")
    altrui, *_ = _scheda(db, pid2)
    r = client.put(f"/workout/plans/{altrui.id}/current?profile_id={pid1}", headers=h1)
    assert r.status_code == 404
    db.refresh(altrui)
    assert altrui.is_current is False


# --- Allenamento senza rete: invii ripetuti e orari del telefono ---------------------


def test_sessione_e_serie_inviate_due_volte_restano_una(ambiente):
    """La risposta si perde, il telefono rimanda: niente doppioni."""
    client, db = ambiente
    h, pid = _account(client, "offline@example.com")
    piano, riga, panca, _ = _scheda(db, pid)
    corpo = {"day_label": "A", "workout_plan_id": piano.id, "date": str(dt.date.today()),
             "start": True, "client_id": "11111111-aaaa-4bbb-8ccc-000000000001"}
    s1 = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json=corpo).json()
    s2 = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json=corpo).json()
    assert s1["id"] == s2["id"]
    assert db.query(WorkoutSession).filter_by(profile_id=pid).count() == 1

    serie = {"exercise_id": panca.id, "set_number": 1, "reps": 8, "weight_kg": 60,
             "client_id": "11111111-aaaa-4bbb-8ccc-000000000002"}
    a = client.post(f"/workout/sessions/{s1['id']}/sets", headers=h, json=serie)
    b = client.post(f"/workout/sessions/{s1['id']}/sets", headers=h, json=serie)
    assert a.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert len(client.get(f"/workout/sessions/current?profile_id={pid}&day_label=A&plan_id={piano.id}&today={dt.date.today()}", headers=h).json()["sets"]) == 1


def test_identificativo_di_un_altro_rifiutato(ambiente):
    client, db = ambiente
    h1, pid1 = _account(client, "primo@example.com")
    h2, pid2 = _account(client, "secondo@example.com")
    corpo = {"date": str(dt.date.today()), "client_id": "22222222-aaaa-4bbb-8ccc-000000000001"}
    assert client.post(f"/workout/sessions?profile_id={pid1}", headers=h1, json=corpo).status_code == 201
    r = client.post(f"/workout/sessions?profile_id={pid2}", headers=h2, json=corpo)
    assert r.status_code == 409


def test_orari_dell_allenamento_fatto_senza_rete(ambiente):
    """Avvio e fine sono quelli veri, non l'ora in cui torna la rete."""
    client, db = ambiente
    h, pid = _account(client, "orari@example.com")
    piano, *_ = _scheda(db, pid)
    adesso = dt.datetime.now(dt.timezone.utc)
    inizio = adesso - dt.timedelta(hours=2)
    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "workout_plan_id": piano.id, "date": str(dt.date.today()), "start": True,
        "started_at": inizio.isoformat(), "client_id": "33333333-aaaa-4bbb-8ccc-000000000001",
    }).json()
    fine = inizio + dt.timedelta(minutes=65)
    r = client.post(f"/workout/sessions/{s['id']}/finish", headers=h, json={"ended_at": fine.isoformat()})
    assert r.status_code == 200
    assert abs(r.json()["duration_seconds"] - 65 * 60) <= 1


def test_orari_impossibili_diventano_adesso(ambiente):
    client, db = ambiente
    h, pid = _account(client, "futuro@example.com")
    domani = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    s = client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "date": str(dt.date.today()), "start": True, "started_at": domani.isoformat(),
    }).json()
    avvio = dt.datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
    if avvio.tzinfo is None:
        avvio = avvio.replace(tzinfo=dt.timezone.utc)
    assert avvio < dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
    # Fine prima dell'avvio: si usa adesso, la durata non è negativa.
    r = client.post(f"/workout/sessions/{s['id']}/finish", headers=h,
                    json={"ended_at": (avvio - dt.timedelta(hours=1)).isoformat()})
    assert r.json()["duration_seconds"] >= 0


# --- Note sugli esercizi ---------------------------------------------------------------


def test_note_sugli_esercizi(ambiente):
    client, db = ambiente
    h, pid = _account(client, "note@example.com")
    _, _, panca, squat = _scheda(db, pid)
    r = client.put(f"/workout/exercises/{panca.id}/note?profile_id={pid}", headers=h,
                   json={"text": "  Sedile 4, schienale 2  "})
    assert r.status_code == 200 and r.json()["text"] == "Sedile 4, schienale 2"
    note = client.get(f"/workout/exercise-notes?profile_id={pid}&exercise_ids={panca.id}&exercise_ids={squat.id}",
                      headers=h).json()
    assert note == {str(panca.id): "Sedile 4, schienale 2"}
    # Un altro utente non vede le note.
    h2, pid2 = _account(client, "altro-note@example.com")
    assert client.get(f"/workout/exercise-notes?profile_id={pid2}&exercise_ids={panca.id}", headers=h2).json() == {}
    assert client.get(f"/workout/exercise-notes?profile_id={pid}&exercise_ids={panca.id}", headers=h2).status_code in (403, 404)
    # Vuota = cancellata.
    client.put(f"/workout/exercises/{panca.id}/note?profile_id={pid}", headers=h, json={"text": ""})
    assert client.get(f"/workout/exercise-notes?profile_id={pid}&exercise_ids={panca.id}", headers=h).json() == {}
