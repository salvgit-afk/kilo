"""I dati segnati dall'utente non si toccano.

Le modifiche al catalogo (doppioni rivisti, adduttori, nomi), la scheda in
uso, l'allenamento senza rete, le note e il filtro per attrezzatura
aggiungono dati o cambiano come si leggono, ma non devono cancellare né
modificare quello che l'utente ha già segnato: schede, allenamenti, serie,
diario, pesate, integratori, preferenze.

Il test popola un database, fotografa ogni riga di quelle tabelle, esegue
tutto ciò che è cambiato e controlla che ogni riga di prima sia identica
(le righe nuove sono ammesse: una scheda generata, una sessione nuova).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import (
    Exercise,
    ExerciseNote,
    ExercisePreference,
    MealItem,
    MealLog,
    SessionSet,
    SupplementDeclaration,
    SupplementIntake,
    WeightLog,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
)
from app.services import exercise_library as lib
from app.services import rate_limit

PASSWORD = "passwordlunga1"
OGGI = dt.date.today()
IERI = OGGI - dt.timedelta(days=1)

# Le tabelle con i dati dell'utente e le colonne che una funzione può cambiare
# senza toccare quei dati (la scheda in uso è una scelta, non un dato segnato).
TABELLE = {
    WorkoutPlan: {"is_current"},
    WorkoutPlanExercise: set(),
    WorkoutSession: set(),
    SessionSet: set(),
    ExercisePreference: set(),
    ExerciseNote: set(),
    MealLog: set(),
    MealItem: set(),
    WeightLog: set(),
    SupplementDeclaration: set(),
    SupplementIntake: set(),
}


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
        "display_name": "Salvo", "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    })
    return h, p.json()["id"]


def _catalogo(db):
    """Esercizi come nel catalogo vero, compresi quelli toccati dalle modifiche."""
    voci = [
        # pushdown a un braccio e estensione sopra la testa: prima nello stesso gruppo
        (lib.SOURCE_EVERKINETIC, "0166", "One Arm Tricep Extension with Cable", "Triceps", False, "cable"),
        (lib.SOURCE_EVERKINETIC, "0199", "Triceps Extension: Cable (One Arm, Low-Pulley)", "Triceps", False, "cable"),
        (lib.SOURCE_MANUAL, "single-arm-overhead-cable-triceps-extension", "Single-Arm Overhead Cable Triceps Extension",
         "Triceps", False, "cable"),
        # abductor machine, ora con il doppione RepDB
        (lib.SOURCE_EVERKINETIC, "0156", "Thigh Abductor", "Glutes", False, "machine"),
        (lib.SOURCE_REPDB, "hip-abduction", "Machine Hip Abduction", "Glutes", False, "machine"),
        # esercizi base per generare una scheda
        (lib.SOURCE_EVERKINETIC, "Q", "Leg Press", "Quads", True, "machine"),
        (lib.SOURCE_EVERKINETIC, "C", "Chest Press", "Chest", True, "machine"),
        (lib.SOURCE_EVERKINETIC, "S", "Shoulder Press", "Shoulders", True, "machine"),
        (lib.SOURCE_EVERKINETIC, "L", "Lat Pulldown", "Lats", True, "cable"),
        (lib.SOURCE_EVERKINETIC, "H", "Romanian Dead Lift", "Hamstrings", True, "barbell"),
        (lib.SOURCE_EVERKINETIC, "B", "Biceps Curl: Cable", "Biceps", False, "cable"),
        (lib.SOURCE_EVERKINETIC, "K", "Standing Calf Raise", "Calves", False, "machine"),
        (lib.SOURCE_EVERKINETIC, "A", "Cable Crunch", "Abs", False, "cable"),
    ]
    esercizi = {}
    for sorgente, eid, nome, muscolo, multi, attrezzo in voci:
        e = Exercise(source=sorgente, external_id=eid, name=nome, primary_muscle=muscolo, is_compound=multi,
                     equipment=attrezzo, in_catalog=True,
                     name_it="French press monolaterale al cavo" if eid.startswith("single-arm") else None)
        db.add(e)
        esercizi[eid] = e
    db.flush()
    return esercizi


def _riempi(db, pid, ex):
    """Due schede, allenamenti con serie (anche su esercizi che diventano doppioni),
    preferenze, note, diario, pesata e integratori."""
    tre = WorkoutPlan(profile_id=pid, name="Full body — 3 giorni", goal="hypertrophy", days_per_week=3,
                      started_at=OGGI - dt.timedelta(days=20), training_weekdays_raw="0,2,4")
    quattro = WorkoutPlan(profile_id=pid, name="Push/Pull — 4 giorni", goal="hypertrophy", days_per_week=4,
                          started_at=OGGI - dt.timedelta(days=2), training_weekdays_raw="0,1,3,4")
    db.add_all([tre, quattro])
    db.flush()
    for piano, chiavi in ((tre, ["single-arm-overhead-cable-triceps-extension", "hip-abduction", "Q"]),
                          (quattro, ["C", "L", "0166"])):
        for i, k in enumerate(chiavi):
            db.add(WorkoutPlanExercise(workout_plan_id=piano.id, exercise_id=ex[k].id, day_label="A",
                                       order_index=i, target_sets=2, target_reps_min=8, target_reps_max=10,
                                       target_rir=3, rest_seconds=90))
    sessione = WorkoutSession(profile_id=pid, workout_plan_id=tre.id, date=IERI, day_label="A",
                              started_at=dt.datetime.combine(IERI, dt.time(18), tzinfo=dt.timezone.utc),
                              ended_at=dt.datetime.combine(IERI, dt.time(19), tzinfo=dt.timezone.utc))
    db.add(sessione)
    db.flush()
    for n, (k, kg, rip) in enumerate([("single-arm-overhead-cable-triceps-extension", 10, 8),
                                      ("single-arm-overhead-cable-triceps-extension", 10, 8),
                                      ("hip-abduction", 40, 12), ("Q", 120, 10)], start=1):
        db.add(SessionSet(workout_session_id=sessione.id, exercise_id=ex[k].id, set_number=n, reps=rip,
                          weight_kg=kg, rir=2))
    db.add(ExercisePreference(profile_id=pid, exercise_id=ex["hip-abduction"].id, is_preferred=True, note="scelto"))
    db.add(ExerciseNote(profile_id=pid, exercise_id=ex["single-arm-overhead-cable-triceps-extension"].id,
                        text="Cavo alla tacca 3"))
    pasto = MealLog(profile_id=pid, date=IERI, meal_type="lunch")
    db.add(pasto)
    db.flush()
    db.add(MealItem(meal_log_id=pasto.id, name="Riso", quantity_g=80, kcal=280, protein_g=6, carbs_g=62, fat_g=1))
    db.add(WeightLog(profile_id=pid, date=IERI, weight_kg=78.4))
    creatina = SupplementDeclaration(profile_id=pid, kind="creatine")
    db.add(creatina)
    db.flush()
    db.add(SupplementIntake(supplement_id=creatina.id, date=IERI))
    db.commit()
    return tre, quattro


def _fotografia(db) -> dict[str, dict[int, dict]]:
    foto = {}
    for modello, ignorate in TABELLE.items():
        tabella = modello.__table__
        righe = db.execute(select(tabella)).mappings().all()
        foto[tabella.name] = {r["id"]: {k: v for k, v in r.items() if k not in ignorate} for r in righe}
    return foto


def test_nessun_dato_dell_utente_cancellato_o_modificato(ambiente):
    client, db = ambiente
    h, pid = _account(client, "intatti@example.com")
    ex = _catalogo(db)
    tre, quattro = _riempi(db, pid, ex)
    prima = _fotografia(db)
    assert all(prima.values()), "ogni tabella deve avere righe, o il controllo non vale"
    q = f"profile_id={pid}"

    # Catalogo: esercizi scritti a mano (nomi nuovi), doppioni rivisti, nomi scelti a mano.
    lib.sync_manual(db)
    lib.apply_duplicates(db)
    lib.apply_name_overrides(db)
    assert ex["single-arm-overhead-cable-triceps-extension"].duplicate_of_id == ex["0199"].id

    # Scheda in uso, letture, storico unito fra doppioni, note, filtro attrezzatura.
    assert client.put(f"/workout/plans/{tre.id}/current?{q}", headers=h).status_code == 200
    assert client.get(f"/workout/plans/active?{q}", headers=h).json()["id"] == tre.id
    assert client.get(f"/workout/plans?{q}&active_only=true", headers=h).status_code == 200
    ultima = client.get(f"/workout/last-performance?{q}&exercise_ids={ex['0199'].id}", headers=h).json()
    assert len(ultima[str(ex["0199"].id)]["sets"]) == 2, "i carichi seguono la versione con i disegni"
    assert client.get(f"/workout/exercises/{ex['0199'].id}/history?{q}", headers=h).status_code == 200
    note = client.get(f"/workout/exercise-notes?{q}&exercise_ids={ex['0199'].id}", headers=h).json()
    assert note == {str(ex["0199"].id): "Cavo alla tacca 3"}
    riga = next(r for r in tre.exercises if r.exercise_id == ex["Q"].id)
    assert client.get(f"/workout/plan-exercises/{riga.id}/alternatives?{q}&equipment=macchine", headers=h).status_code == 200
    assert client.get(f"/workout/plans/{tre.id}/candidates?{q}&muscle=Adductors", headers=h).status_code == 200
    assert client.get(f"/profile/{pid}/reminders?today={OGGI}", headers=h).status_code in (200, 404)

    # Allenamento senza rete: sessione e serie mandate due volte.
    corpo = {"day_label": "A", "workout_plan_id": quattro.id, "date": str(OGGI), "start": True,
             "client_id": "44444444-aaaa-4bbb-8ccc-000000000001"}
    s = client.post(f"/workout/sessions?{q}", headers=h, json=corpo).json()
    assert client.post(f"/workout/sessions?{q}", headers=h, json=corpo).json()["id"] == s["id"]
    serie = {"exercise_id": ex["C"].id, "set_number": 1, "reps": 8, "weight_kg": 50,
             "client_id": "44444444-aaaa-4bbb-8ccc-000000000002"}
    client.post(f"/workout/sessions/{s['id']}/sets", headers=h, json=serie)
    client.post(f"/workout/sessions/{s['id']}/sets", headers=h, json=serie)
    client.post(f"/workout/sessions/{s['id']}/finish", headers=h, json={})

    # Una scheda nuova generata accanto alle altre.
    r = client.post(f"/workout/plans/generate?{q}&split_type=push_pull&explain=false"
                    "&weekdays=0&weekdays=1&weekdays=3&weekdays=4", headers=h)
    assert r.status_code == 201, r.text

    db.expire_all()
    dopo = _fotografia(db)
    for tabella, righe in prima.items():
        for id_, valori in righe.items():
            assert dopo[tabella].get(id_) == valori, f"{tabella} riga {id_} cambiata o cancellata"
    # Le righe nuove sono solo quelle create qui: una sessione, una serie, una scheda.
    assert len(dopo["session_sets"]) == len(prima["session_sets"]) + 1
    assert len(dopo["workout_sessions"]) == len(prima["workout_sessions"]) + 1
    assert len(dopo["workout_plans"]) == len(prima["workout_plans"]) + 1


def test_le_migrazioni_nuove_aggiungono_soltanto():
    """Le migrazioni di questo lavoro aggiungono colonne, vincoli e tabelle:
    nessun UPDATE, DELETE, DROP o ALTER sui dati esistenti in upgrade()."""
    cartella = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    for nome in ("d2b7e4a9c1f3_current_workout_plan.py", "e8c1f5a3b7d2_offline_ids_and_exercise_notes.py"):
        testo = (cartella / nome).read_text(encoding="utf-8")
        upgrade = testo.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
        for vietato in ("op.execute", "drop_", "alter_column", "bulk_", "UPDATE", "DELETE"):
            assert vietato not in upgrade, f"{nome}: {vietato} in upgrade()"
