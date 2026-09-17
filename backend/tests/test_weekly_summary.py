"""Test del riepilogo settimanale."""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import (
    ActivityLevel,
    ExperienceLevel,
    Goal,
    MealItem,
    MealLog,
    Sex,
    SupplementDeclaration,
    SupplementKind,
    UserProfile,
    WeightLog,
    WorkoutPlan,
    WorkoutSession,
)
from app.services import supplement_intake, weekly_summary as ws

GIOVEDI = dt.date(2026, 9, 17)
LUNEDI_SCORSO = dt.date(2026, 9, 7)


@pytest.fixture
def profilo(db) -> UserProfile:
    p = UserProfile(
        display_name="test", birth_date=dt.date(1996, 5, 20), sex=Sex.MALE,
        height_cm=178.0, weight_kg=80.0, goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=4,
    )
    db.add(p)
    db.commit()
    return p


def giorno(n: int) -> dt.date:
    """n-esimo giorno della settimana scorsa (0 = lunedì)."""
    return LUNEDI_SCORSO + dt.timedelta(days=n)


def test_settimana_conclusa_da_lunedi_a_domenica():
    assert ws.last_week(GIOVEDI) == (dt.date(2026, 9, 7), dt.date(2026, 9, 13))
    # Anche di lunedì la settimana "conclusa" è quella prima.
    assert ws.last_week(dt.date(2026, 9, 14)) == (dt.date(2026, 9, 7), dt.date(2026, 9, 13))


def test_senza_dati_nessun_obiettivo(db, profilo):
    r = ws.build(db, profilo, today=GIOVEDI)
    assert r.has_data is False
    assert r.focus is None


def test_allenamenti_mancanti_sono_la_priorita(db, profilo):
    db.add(WorkoutPlan(profile_id=profilo.id, name="x", goal="hypertrophy", days_per_week=4,
                       started_at=giorno(-20)))
    for n in (0, 2):
        db.add(WorkoutSession(profile_id=profilo.id, date=giorno(n)))
    # Fuori settimana: non conta.
    db.add(WorkoutSession(profile_id=profilo.id, date=GIOVEDI))
    db.commit()
    r = ws.build(db, profilo, today=GIOVEDI)
    assert (r.sessions_done, r.sessions_planned) == (2, 4)
    assert r.focus.startswith("Allenamenti: 2 su 4")


def test_peso_confrontato_con_la_settimana_prima(db, profilo):
    for n, peso in ((-6, 80.0), (-3, 80.4), (1, 80.6), (4, 81.0)):
        db.add(WeightLog(profile_id=profilo.id, date=giorno(n), weight_kg=peso))
    db.commit()
    r = ws.build(db, profilo, today=GIOVEDI)
    assert r.weight_average == 80.8
    assert r.weight_delta_kg == pytest.approx(0.6)
    assert r.weigh_ins == 2


def test_proteine_media_dei_giorni_registrati(db, profilo):
    for n in (0, 1, 2):
        pasto = MealLog(profile_id=profilo.id, date=giorno(n), meal_type="lunch")
        db.add(pasto)
        db.flush()
        db.add(MealItem(meal_log_id=pasto.id, name="x", quantity_g=100,
                        kcal=2500, protein_g=90, carbs_g=300, fat_g=70))
    db.commit()
    r = ws.build(db, profilo, today=GIOVEDI)
    assert r.logged_days == 3
    assert r.protein_average_g == 90
    assert r.focus.startswith("Proteine")


def test_costanza_integratori_dal_giorno_di_inizio(db, profilo):
    d = SupplementDeclaration(profile_id=profilo.id, kind=SupplementKind.CREATINE, dose_amount=5)
    db.add(d)
    db.commit()
    d.created_at = dt.datetime.combine(giorno(3), dt.time(9))  # iniziata giovedì
    db.commit()
    for n in (3, 4, 6):
        supplement_intake.set_doses(db, d, giorno(n), 1)
    r = ws.build(db, profilo, today=GIOVEDI)
    assert [(i.days_taken, i.days_expected) for i in r.supplements] == [(3, 4)]


def test_settimana_completa(db, profilo):
    db.add(WorkoutPlan(profile_id=profilo.id, name="x", goal="hypertrophy", days_per_week=2,
                       started_at=giorno(-20)))
    for n in (0, 3):
        db.add(WorkoutSession(profile_id=profilo.id, date=giorno(n)))
    for n in (1, 5):
        db.add(WeightLog(profile_id=profilo.id, date=giorno(n), weight_kg=80))
    db.commit()
    assert ws.build(db, profilo, today=GIOVEDI).focus.startswith("Settimana solida")
