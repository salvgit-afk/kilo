"""Statistiche della pagina Progressi: volume, massimale, costanza, peso, dieta.

Quello che conta qui non è il numero in sé ma il confronto: il volume contro
il range delle fonti, gli allenamenti contro la scheda, il peso contro il
ritmo atteso, il diario contro i target. E, come per ogni altra rotta, le
statistiche di un altro profilo non si leggono.

Le date sono sempre calcolate a partire dal lunedì della settimana corrente:
i test devono passare qualunque giorno della settimana si esegua la suite.
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
from app.models import (
    Exercise,
    MealItem,
    MealLog,
    SessionSet,
    SupplementDeclaration,
    SupplementKind,
    WeightLog,
    WorkoutPlan,
    WorkoutSession,
)
from app.services import rate_limit
from app.services.progress_stats import week_start

PASSWORD = "passwordlunga1"

OGGI = dt.date.today()
LUNEDI = week_start(OGGI)


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
    for finestra in (
        rate_limit.LOGIN_PER_IP,
        rate_limit.LOGIN_FAILURES_PER_EMAIL,
        rate_limit.REGISTER_PER_IP,
    ):
        finestra.reset()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _account(client, email, **profilo):
    r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    dati = {
        "display_name": "x", "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "experience_level": "beginner",
        "training_days_per_week": 3,
    }
    dati.update(profilo)
    p = client.post("/profile", headers=h, json=dati)
    return h, p.json()["id"]


def _esercizi(db):
    panca = Exercise(name="Bench Press", name_it="Panca piana", primary_muscle="Chest")
    squat = Exercise(name="Squat", name_it="Squat", primary_muscle="Quads")
    db.add_all([panca, squat])
    db.commit()
    return panca, squat


def _sessione(db, profile_id, giorno, *, esercizio=None, serie=0, kg=60.0, reps=8, avviata=False):
    """Una sessione con le sue serie, scritta direttamente a database."""
    sessione = WorkoutSession(
        profile_id=profile_id,
        date=giorno,
        started_at=dt.datetime.now() if avviata else None,
    )
    db.add(sessione)
    db.flush()
    for n in range(serie):
        db.add(
            SessionSet(
                workout_session_id=sessione.id,
                exercise_id=esercizio.id,
                set_number=n + 1,
                reps=reps,
                weight_kg=kg,
            )
        )
    db.commit()
    return sessione


# --- Volume per gruppo muscolare ----------------------------------------------------


def test_volume_muscolo_sotto_e_sopra_il_range(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    panca, squat = _esercizi(db)

    # Principiante con obiettivo massa: range 6-14 serie a settimana.
    _sessione(db, pid, LUNEDI, esercizio=panca, serie=3)
    _sessione(db, pid, LUNEDI, esercizio=squat, serie=20)

    r = client.get(f"/progress/volume?profile_id={pid}&weeks=1", headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["weeks"] == [LUNEDI.isoformat()]

    per_muscolo = {m["muscle"]: m for m in corpo["muscles"]}
    # Il volume più alto va in cima.
    assert [m["muscle"] for m in corpo["muscles"]] == ["Quads", "Chest"]
    assert per_muscolo["Chest"]["sets_per_week"] == [3]
    assert per_muscolo["Chest"]["status"] == "sotto"
    assert (per_muscolo["Chest"]["range_min"], per_muscolo["Chest"]["range_max"]) == (6, 14)
    assert per_muscolo["Quads"]["status"] == "sopra"
    assert per_muscolo["Quads"]["last"] == 20


def test_volume_una_riga_per_settimana_anche_senza_allenamenti(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    panca, _ = _esercizi(db)
    _sessione(db, pid, LUNEDI - dt.timedelta(days=14), esercizio=panca, serie=4)

    r = client.get(f"/progress/volume?profile_id={pid}&weeks=4", headers=h)
    corpo = r.json()
    assert corpo["weeks"] == [
        (LUNEDI - dt.timedelta(weeks=n)).isoformat() for n in (3, 2, 1, 0)
    ]
    chest = corpo["muscles"][0]
    assert chest["sets_per_week"] == [0, 4, 0, 0]
    assert chest["average"] == 1.0
    assert chest["status"] == "sotto"


def test_volume_senza_dati(ambiente):
    client, _ = ambiente
    h, pid = _account(client, "a@example.com")
    r = client.get(f"/progress/volume?profile_id={pid}", headers=h)
    assert r.status_code == 200
    assert r.json()["muscles"] == []
    assert len(r.json()["weeks"]) == 8


# --- Massimale stimato ---------------------------------------------------------------


def test_one_rm_un_punto_per_sessione(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    panca, _ = _esercizi(db)

    _sessione(db, pid, LUNEDI - dt.timedelta(days=14), esercizio=panca, serie=2, kg=60, reps=8)
    # Nella stessa sessione vale la serie migliore per massimale stimato,
    # non il carico più alto.
    ultima = _sessione(db, pid, LUNEDI, esercizio=panca, serie=1, kg=70, reps=8)
    db.add(
        SessionSet(
            workout_session_id=ultima.id, exercise_id=panca.id, set_number=2,
            reps=1, weight_kg=85,
        )
    )
    db.commit()

    r = client.get(f"/progress/one-rm/{panca.id}?profile_id={pid}&weeks=8", headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["exercise_name"] == "Panca piana"
    assert [p["one_rm"] for p in corpo["points"]] == [76.0, 88.7]
    assert corpo["points"][-1]["kg"] == 70 and corpo["points"][-1]["reps"] == 8
    assert corpo["delta_pct"] == pytest.approx((88.7 - 76.0) / 76.0, abs=0.001)
    assert corpo["high_rep_estimate"] is False


def test_one_rm_avvisa_sulle_serie_lunghe(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    panca, _ = _esercizi(db)
    _sessione(db, pid, LUNEDI, esercizio=panca, serie=1, kg=40, reps=15)

    r = client.get(f"/progress/one-rm/{panca.id}?profile_id={pid}", headers=h)
    assert r.json()["high_rep_estimate"] is True
    # Un solo punto: nessun confronto possibile.
    assert r.json()["delta_pct"] == 0.0


def test_one_rm_esercizio_mai_registrato(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _, squat = _esercizi(db)
    assert client.get(f"/progress/one-rm/{squat.id}?profile_id={pid}", headers=h).status_code == 404
    assert client.get(f"/progress/one-rm/9999?profile_id={pid}", headers=h).status_code == 404


# --- Costanza ------------------------------------------------------------------------


def _piano(db, profile_id, *, inizio):
    piano = WorkoutPlan(
        profile_id=profile_id, name="Full body", goal="hypertrophy", days_per_week=3,
        started_at=inizio, training_weekdays_raw="0,2,4",
    )
    db.add(piano)
    db.commit()
    return piano


def test_consistency_settimana_saltata_spezza_la_serie(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    panca, _ = _esercizi(db)
    _piano(db, pid, inizio=LUNEDI - dt.timedelta(weeks=3))

    for settimane_fa, allenamenti in ((3, 3), (2, 3), (1, 1)):
        lunedi = LUNEDI - dt.timedelta(weeks=settimane_fa)
        for giorno in range(allenamenti):
            _sessione(db, pid, lunedi + dt.timedelta(days=giorno), esercizio=panca, serie=3)
    # Settimana in corso: solo il lunedì, che è sempre passato o è oggi.
    _sessione(db, pid, LUNEDI, avviata=True)

    r = client.get(f"/progress/consistency?profile_id={pid}&weeks=4", headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [(s["done"], s["planned"]) for s in corpo["weeks"]] == [(3, 3), (3, 3), (1, 3), (1, 3)]
    # La settimana scorsa (1 su 3) ha spezzato la serie; quella in corso non
    # è ancora finita e quindi non conta né a favore né contro.
    assert corpo["streak_weeks"] == 0
    assert corpo["best_streak_weeks"] == 2
    assert (corpo["done_total"], corpo["planned_total"]) == (8, 12)


def test_consistency_piu_schede_attive_non_si_sommano(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _piano(db, pid, inizio=LUNEDI)
    _piano(db, pid, inizio=LUNEDI)

    r = client.get(f"/progress/consistency?profile_id={pid}&weeks=1", headers=h)
    assert r.json()["weeks"][0]["planned"] == 3


def test_consistency_senza_dati(ambiente):
    client, _ = ambiente
    h, pid = _account(client, "a@example.com")
    r = client.get(f"/progress/consistency?profile_id={pid}&weeks=6", headers=h)
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["weeks"]) == 6
    assert all((s["done"], s["planned"]) == (0, 0) for s in corpo["weeks"])
    assert (corpo["streak_weeks"], corpo["best_streak_weeks"]) == (0, 0)
    assert (corpo["done_total"], corpo["planned_total"]) == (0, 0)


# --- Peso --------------------------------------------------------------------------


def test_weight_trend_ritmo_dentro_il_range_del_dimagrimento(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com", goal="fat_loss", weight_kg=80)

    for giorni_fa in range(28, -1, -1):
        db.add(
            WeightLog(
                profile_id=pid,
                date=OGGI - dt.timedelta(days=giorni_fa),
                weight_kg=80.0 - 0.08 * (28 - giorni_fa),
            )
        )
    db.commit()

    r = client.get(f"/progress/weight-trend?profile_id={pid}&weeks=8", headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["points"]) == 29
    # La media mobile smussa: il primo punto non coincide con la pesata.
    assert corpo["points"][0]["weight_kg"] == 80.0
    assert corpo["points"][-1]["average_kg"] < corpo["points"][0]["average_kg"]
    assert corpo["weekly_rate_kg"] < 0
    # 0,5-1,0% del peso a settimana (`diets_body_composition.md`).
    assert corpo["expected_min"] < corpo["weekly_rate_kg"] < corpo["expected_max"] < 0
    assert corpo["verdict"] == "in_linea"


def test_weight_trend_pochi_dati(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com", goal="fat_loss")
    for giorni_fa in (3, 0):
        db.add(
            WeightLog(profile_id=pid, date=OGGI - dt.timedelta(days=giorni_fa), weight_kg=78.0)
        )
    db.commit()

    r = client.get(f"/progress/weight-trend?profile_id={pid}", headers=h)
    corpo = r.json()
    assert corpo["verdict"] == "pochi_dati"
    assert len(corpo["points"]) == 2
    assert "due settimane" in corpo["note"]


def test_weight_trend_senza_pesate(ambiente):
    client, _ = ambiente
    h, pid = _account(client, "a@example.com")
    r = client.get(f"/progress/weight-trend?profile_id={pid}", headers=h)
    assert r.status_code == 200
    assert r.json()["points"] == []
    assert r.json()["verdict"] == "pochi_dati"
    assert r.json()["weekly_rate_kg"] is None


def test_weight_trend_senza_ritmo_nelle_fonti(ambiente):
    """Per l'aumento di massa le fonti non danno un ritmo in kg a settimana:
    la risposta lo dichiara invece di inventare un range."""
    client, db = ambiente
    h, pid = _account(client, "a@example.com", goal="hypertrophy")
    for giorni_fa in range(21, -1, -1):
        db.add(
            WeightLog(
                profile_id=pid,
                date=OGGI - dt.timedelta(days=giorni_fa),
                weight_kg=78.0 + 0.03 * (21 - giorni_fa),
            )
        )
    db.commit()

    corpo = client.get(f"/progress/weight-trend?profile_id={pid}", headers=h).json()
    assert corpo["expected_min"] is None and corpo["expected_max"] is None
    assert corpo["verdict"] == "non_valutabile"
    assert "non indicano un ritmo" in corpo["note"]


# --- Dieta -------------------------------------------------------------------------


def _pasto(db, profile_id, giorno, *, kcal, proteine):
    pasto = MealLog(profile_id=profile_id, date=giorno, meal_type="lunch", is_planned=False)
    db.add(pasto)
    db.flush()
    db.add(
        MealItem(
            meal_log_id=pasto.id, name="Riso e pollo", quantity_g=400,
            kcal=kcal, protein_g=proteine, carbs_g=80, fat_g=10,
        )
    )
    db.commit()


def test_nutrition_medie_settimanali_con_le_proteine_dell_integratore(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")

    # Settimana scorsa: due giorni interamente passati, qualunque sia oggi.
    scorsa = LUNEDI - dt.timedelta(weeks=1)
    _pasto(db, pid, scorsa, kcal=2000, proteine=100)
    _pasto(db, pid, scorsa + dt.timedelta(days=1), kcal=2400, proteine=120)
    db.add(
        SupplementDeclaration(
            profile_id=pid, kind=SupplementKind.PROTEIN_POWDER, doses_per_day=2,
            protein_g_per_dose=25, is_active=True,
        )
    )
    db.commit()

    r = client.get(f"/progress/nutrition?profile_id={pid}&weeks=2", headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [s["start"] for s in corpo["weeks"]] == [scorsa.isoformat(), LUNEDI.isoformat()]

    registrata = corpo["weeks"][0]
    assert registrata["days_logged"] == 2
    # Le 50 g dell'integratore si sommano al totale, con le loro 200 kcal.
    assert registrata["protein_avg_g"] == 160  # (100 + 120) / 2 + 50
    assert registrata["kcal_avg"] == 2400      # (2000 + 2400) / 2 + 50 * 4
    assert corpo["kcal_target"] and corpo["protein_target_g"]
    # Settimana in corso senza niente nel diario: resta nell'elenco con zero
    # giorni, così il grafico non salta una colonna.
    assert corpo["weeks"][1]["days_logged"] == 0


def test_nutrition_giorni_in_target(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    target = client.get(f"/nutrition/targets?profile_id={pid}", headers=h).json()

    _pasto(db, pid, LUNEDI, kcal=target["target_kcal"], proteine=target["protein_g"])

    settimana = client.get(
        f"/progress/nutrition?profile_id={pid}&weeks=1", headers=h
    ).json()["weeks"][0]
    assert (settimana["days_in_kcal_target"], settimana["days_in_protein_target"]) == (1, 1)


def test_nutrition_senza_diario(ambiente):
    client, _ = ambiente
    h, pid = _account(client, "a@example.com")
    r = client.get(f"/progress/nutrition?profile_id={pid}", headers=h)
    assert r.status_code == 200
    assert r.json()["weeks"] == []
    assert r.json()["kcal_target"] > 0


# --- Proprietà ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "rotta",
    ["/progress/volume", "/progress/consistency", "/progress/weight-trend", "/progress/nutrition"],
)
def test_statistiche_di_un_altro_profilo_non_si_leggono(ambiente, rotta):
    client, db = ambiente
    _, mio = _account(client, "a@example.com")
    altrui_h, _ = _account(client, "b@example.com")

    r = client.get(f"{rotta}?profile_id={mio}", headers=altrui_h)
    assert r.status_code == 404


def test_massimale_di_un_altro_profilo_non_si_legge(ambiente):
    client, db = ambiente
    h, mio = _account(client, "a@example.com")
    altrui_h, _ = _account(client, "b@example.com")
    panca, _ = _esercizi(db)
    _sessione(db, mio, LUNEDI, esercizio=panca, serie=3)

    assert client.get(
        f"/progress/one-rm/{panca.id}?profile_id={mio}", headers=altrui_h
    ).status_code == 404
    # Stesso esercizio, ma nessuna serie registrata dall'altro profilo.
    r = client.get(f"/progress/one-rm/{panca.id}?profile_id={mio}", headers=h)
    assert r.status_code == 200 and r.json()["points"]
