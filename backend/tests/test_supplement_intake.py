"""Test del diario delle assunzioni e dei promemoria della giornata.

Il diario deve dire tre cose senza ambiguità: da quanti giorni l'utente
assume l'integratore, se ne ha saltato qualcuno e la serie in corso. I
promemoria devono ricordare solo abitudini che l'utente ha già.
"""

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
    SupplementIntake,
    SupplementKind,
    UserProfile,
)
from app.services import daily_reminders, supplement_intake as intake

OGGI = dt.date(2026, 9, 17)


def giorni_fa(n: int) -> dt.date:
    return OGGI - dt.timedelta(days=n)


@pytest.fixture
def profilo(db) -> UserProfile:
    p = UserProfile(
        display_name="test",
        birth_date=dt.date(1996, 5, 20),
        sex=Sex.MALE,
        height_cm=178.0,
        weight_kg=76.0,
        goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
        training_days_per_week=4,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _dichiara(db, profilo, *, giorni: int = 30, **kwargs) -> SupplementDeclaration:
    kwargs.setdefault("kind", SupplementKind.CREATINE)
    d = SupplementDeclaration(profile_id=profilo.id, **kwargs)
    db.add(d)
    db.commit()
    # Dichiarato `giorni` fa: la data di inizio conta per i giorni saltati.
    d.created_at = dt.datetime.combine(giorni_fa(giorni), dt.time(9))
    db.commit()
    db.refresh(d)
    return d


def _segna(db, d, *giorni: int, dosi: int = 1) -> None:
    for n in giorni:
        intake.set_doses(db, d, giorni_fa(n), dosi)


# --- Conteggi -----------------------------------------------------------------


def test_nessuna_assunzione_segnata(db, profilo):
    d = _dichiara(db, profilo, giorni=0)
    r = intake.summarize(db, d, today=OGGI)

    assert (r.days_taken, r.current_streak, r.missed_days) == (0, 0, 0)
    assert r.since == OGGI


def test_giorni_totali_e_serie(db, profilo):
    """14 giorni di fila fino a oggi: 14 in tutto, serie di 14, nessuno saltato."""
    d = _dichiara(db, profilo, giorni=13)
    _segna(db, d, *range(14))
    r = intake.summarize(db, d, today=OGGI)

    assert r.days_taken == 14
    assert r.current_streak == 14
    assert r.missed_days == 0


def test_oggi_non_ancora_segnato_non_interrompe_la_serie(db, profilo):
    d = _dichiara(db, profilo, giorni=5)
    _segna(db, d, 1, 2, 3)
    r = intake.summarize(db, d, today=OGGI)

    assert r.current_streak == 3
    # Oggi non è ancora finito: non conta come saltato.
    assert r.missed_days == 2  # 4 e 5 giorni fa


def test_giorno_saltato_azzera_la_serie_ma_non_il_totale(db, profilo):
    d = _dichiara(db, profilo, giorni=6)
    _segna(db, d, 0, 1, 3, 4, 5, 6)
    r = intake.summarize(db, d, today=OGGI)

    assert r.days_taken == 6
    assert r.current_streak == 2
    assert r.missed_days == 1


def test_giorni_segnati_prima_della_dichiarazione_spostano_l_inizio(db, profilo):
    d = _dichiara(db, profilo, giorni=0)
    _segna(db, d, 10)
    r = intake.summarize(db, d, today=OGGI)

    assert r.since == giorni_fa(10)
    assert r.missed_days == 9


def test_giorni_saltati_contati_solo_nella_finestra(db, profilo):
    d = _dichiara(db, profilo, giorni=100)
    r = intake.summarize(db, d, today=OGGI)

    assert r.missed_days == intake.HISTORY_DAYS - 1
    assert r.history == {}


def test_assunzioni_future_rispetto_a_oggi_ignorate(db, profilo):
    d = _dichiara(db, profilo, giorni=2)
    intake.set_doses(db, d, OGGI + dt.timedelta(days=1), 1)
    assert intake.summarize(db, d, today=OGGI).days_taken == 0


# --- Dosi multiple -------------------------------------------------------------


def test_fase_di_carico_richiede_piu_dosi(db, profilo):
    d = _dichiara(db, profilo, doses_per_day=4)
    assert intake.required_doses(d) == 4

    intake.set_doses(db, d, OGGI, 2)
    assert intake.pending(db, profilo, today=OGGI) == [(d, 2)]

    intake.set_doses(db, d, OGGI, 4)
    assert intake.pending(db, profilo, today=OGGI) == []


def test_dose_parziale_conta_come_giorno_di_assunzione(db, profilo):
    d = _dichiara(db, profilo, giorni=1, doses_per_day=4)
    _segna(db, d, 1, dosi=1)
    assert intake.summarize(db, d, today=OGGI).days_taken == 1


def test_zero_dosi_cancella_il_giorno(db, profilo):
    d = _dichiara(db, profilo)
    intake.set_doses(db, d, OGGI, 1)
    intake.set_doses(db, d, OGGI, 0)
    assert db.query(SupplementIntake).count() == 0


def test_dosi_fuori_limite_rifiutate(db, profilo):
    d = _dichiara(db, profilo)
    with pytest.raises(ValueError):
        intake.set_doses(db, d, OGGI, -1)
    with pytest.raises(ValueError):
        intake.set_doses(db, d, OGGI, intake.MAX_DOSES_PER_DAY + 1)


def test_rimuovere_l_integratore_cancella_lo_storico(db, profilo):
    d = _dichiara(db, profilo)
    _segna(db, d, 0, 1)
    db.delete(d)
    db.commit()
    assert db.query(SupplementIntake).count() == 0


# --- Traguardi dalle fonti -------------------------------------------------------


def test_traguardo_solo_dove_la_fonte_indica_una_durata(db, profilo):
    creatina = _dichiara(db, profilo, kind=SupplementKind.CREATINE)
    caffeina = _dichiara(db, profilo, kind=SupplementKind.CAFFEINE)

    traguardo = intake.summarize(db, creatina, today=OGGI).milestone
    assert traguardo is not None and traguardo.days == 28
    assert traguardo.knowledge_tag == "creatina"
    assert intake.summarize(db, caffeina, today=OGGI).milestone is None


# --- Promemoria ------------------------------------------------------------------


def _pasto(db, profilo, giorno: dt.date) -> None:
    pasto = MealLog(profile_id=profilo.id, date=giorno, meal_type="lunch")
    db.add(pasto)
    db.flush()
    db.add(
        MealItem(
            meal_log_id=pasto.id, name="riso", quantity_g=100,
            kcal=130, protein_g=3, carbs_g=28, fat_g=0.3,
        )
    )
    db.commit()


def test_nessun_promemoria_senza_integratori_ne_diario(db, profilo):
    promemoria = daily_reminders.build(db, profilo, today=OGGI)
    assert promemoria.supplements == []
    assert promemoria.meals_missing is False


def test_promemoria_integratore_non_segnato(db, profilo):
    d = _dichiara(db, profilo)
    assert daily_reminders.build(db, profilo, today=OGGI).supplements == [(d, 0)]

    intake.set_doses(db, d, OGGI, 1)
    assert daily_reminders.build(db, profilo, today=OGGI).supplements == []


def test_integratore_disattivato_non_ricordato(db, profilo):
    _dichiara(db, profilo, is_active=False)
    assert daily_reminders.build(db, profilo, today=OGGI).supplements == []


def test_diario_ricordato_solo_a_chi_lo_usa(db, profilo):
    """Chi non conta le calorie non deve sentirselo ricordare ogni giorno."""
    assert daily_reminders.build(db, profilo, today=OGGI).meals_missing is False

    _pasto(db, profilo, giorni_fa(3))
    assert daily_reminders.build(db, profilo, today=OGGI).meals_missing is True

    _pasto(db, profilo, OGGI)
    assert daily_reminders.build(db, profilo, today=OGGI).meals_missing is False


def test_diario_abbandonato_da_tempo_non_ricordato(db, profilo):
    _pasto(db, profilo, giorni_fa(daily_reminders.DIARY_RECENT_DAYS + 1))
    assert daily_reminders.build(db, profilo, today=OGGI).meals_missing is False


def test_pasto_vuoto_non_conta_come_registrato(db, profilo):
    _pasto(db, profilo, giorni_fa(2))
    db.add(MealLog(profile_id=profilo.id, date=OGGI, meal_type="dinner"))
    db.commit()
    assert daily_reminders.build(db, profilo, today=OGGI).meals_missing is True


# --- "16 su 18 giorni": il periodo reale, non una finestra fissa ------------------------


def test_giorni_tracciati_dal_primo_segnato(db, profilo):
    d = _dichiara(db, profilo, giorni=40)
    _segna(db, d, *[n for n in range(1, 19) if n not in (5, 11)])
    r = intake.summarize(db, d, today=OGGI)
    # Dal primo giorno segnato (18 giorni fa) a ieri: oggi non è ancora finito.
    assert (r.days_taken, r.tracked_days) == (16, 18)


def test_oggi_segnato_entra_nel_periodo(db, profilo):
    d = _dichiara(db, profilo, giorni=3)
    _segna(db, d, 0, 1, 2)
    assert intake.summarize(db, d, today=OGGI).tracked_days == 3


def test_niente_segnato_niente_periodo(db, profilo):
    d = _dichiara(db, profilo, giorni=10)
    assert intake.summarize(db, d, today=OGGI).tracked_days == 0


def test_fase_con_nome_e_spiegazione():
    for giorni, nome, nota, completata, _, _ in intake.MILESTONES.values():
        assert giorni > 0 and nome and completata
    creatina = intake.MILESTONES[intake.SupplementKind.CREATINE]
    assert creatina[1] == "Fase di saturazione"
    # Il 28 non deve sembrare la fine dell'assunzione.
    assert "mantenimento" in creatina[2] and "non la fine" in creatina[2]
