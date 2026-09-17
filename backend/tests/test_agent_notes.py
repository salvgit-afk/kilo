"""Test delle note di Kilo.

Le note sono regole sulle fonti: si verifica che compaiano quando la soglia
del documento è raggiunta, che non compaiano prima, e che una nota chiusa
non ritorni.
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
    RecoveryQuality,
    ProgressPerception,
    Sex,
    SupplementDeclaration,
    SupplementKind,
    TrainingFeedback,
    UserProfile,
    WeightLog,
    WorkoutPlan,
)
from app.services import agent_notes, supplement_intake

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
        weight_kg=80.0,
        goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
        training_days_per_week=4,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _integratore(db, profilo, giorni_presi: int, **kwargs) -> SupplementDeclaration:
    kwargs.setdefault("kind", SupplementKind.CREATINE)
    kwargs.setdefault("dose_amount", 5)
    kwargs.setdefault("dose_unit", "g")
    d = SupplementDeclaration(profile_id=profilo.id, **kwargs)
    db.add(d)
    db.commit()
    d.created_at = dt.datetime.combine(giorni_fa(max(giorni_presi - 1, 0)), dt.time(9))
    db.commit()
    for n in range(giorni_presi):
        supplement_intake.set_doses(db, d, giorni_fa(n), supplement_intake.required_doses(d))
    return d


def _chiavi(db, profilo, sezione=None) -> list[str]:
    return [
        n.key.split(":")[0]
        for n in agent_notes.build(db, profilo, today=OGGI)
        if sezione is None or n.section == sezione
    ]


def test_nessun_dato_nessuna_nota(db, profilo):
    assert agent_notes.build(db, profilo, today=OGGI) == []


# --- Integratori -------------------------------------------------------------------


def test_creatina_scorte_piene_solo_dopo_28_giorni(db, profilo):
    d = _integratore(db, profilo, 27)
    assert "creatina-scorte-piene" not in _chiavi(db, profilo)

    supplement_intake.set_doses(db, d, giorni_fa(27), 1)
    note = agent_notes.build(db, profilo, today=OGGI)
    piena = next(n for n in note if n.key.startswith("creatina-scorte-piene"))
    assert "Non serve fare pause" in piena.text
    assert piena.knowledge_tags == ["creatina"]
    assert piena.section == "integratori"


def test_fase_di_carico_finita_dopo_7_giorni(db, profilo):
    _integratore(db, profilo, 6, doses_per_day=4)
    assert "creatina-carico-finito" not in _chiavi(db, profilo)

    profilo2 = profilo
    d = db.query(SupplementDeclaration).one()
    supplement_intake.set_doses(db, d, giorni_fa(6), 4)
    chiavi = _chiavi(db, profilo2)
    assert "creatina-carico-finito" in chiavi
    # In carico non ha senso parlare di saturazione "in 3-4 settimane".
    assert "creatina-scorte-piene" not in chiavi


def test_giorni_saltati_rassicurano(db, profilo):
    d = _integratore(db, profilo, 20)
    for n in (2, 5, 9):
        supplement_intake.set_doses(db, d, giorni_fa(n), 0)
    nota = next(
        n for n in agent_notes.build(db, profilo, today=OGGI)
        if n.key.startswith("creatina-giorni-saltati")
    )
    assert "3 giorni saltati" in nota.title
    assert "4-6 settimane" in nota.text


def test_beta_alanina_dichiara_i_limiti_della_fonte(db, profilo):
    _integratore(db, profilo, 28, kind=SupplementKind.BETA_ALANINE)
    nota = agent_notes.build(db, profilo, today=OGGI)[0]
    assert nota.key.startswith("beta-alanina-4-settimane")
    assert "non dà indicazioni" in nota.text


def test_nessuna_nota_su_integratori_non_dichiarati(db, profilo):
    """Kilo non propone integratori: senza dichiarazioni, nessuna nota."""
    assert not [n for n in agent_notes.build(db, profilo, today=OGGI) if n.section == "integratori"]


# --- Chiusura -------------------------------------------------------------------------


def test_nota_chiusa_non_ritorna(db, profilo):
    _integratore(db, profilo, 30)
    nota = agent_notes.build(db, profilo, today=OGGI)[0]
    agent_notes.dismiss(db, profilo, nota.key)
    agent_notes.dismiss(db, profilo, nota.key)  # due volte: nessun errore
    assert nota.key not in [n.key for n in agent_notes.build(db, profilo, today=OGGI)]


def test_nota_settimanale_torna_la_settimana_dopo(db, profilo):
    d = _integratore(db, profilo, 20)
    for n in (2, 5, 9):
        supplement_intake.set_doses(db, d, giorni_fa(n), 0)
    chiave = next(
        n.key for n in agent_notes.build(db, profilo, today=OGGI)
        if n.key.startswith("creatina-giorni-saltati")
    )
    agent_notes.dismiss(db, profilo, chiave)
    dopo = agent_notes.build(db, profilo, today=OGGI + dt.timedelta(days=7))
    assert any(n.key.startswith("creatina-giorni-saltati") and n.key != chiave for n in dopo)


# --- Scheda ---------------------------------------------------------------------------


def _scheda(db, profilo, giorni: int) -> WorkoutPlan:
    piano = WorkoutPlan(
        profile_id=profilo.id, name="Full body", goal=profilo.goal,
        days_per_week=3, started_at=giorni_fa(giorni),
    )
    db.add(piano)
    db.commit()
    return piano


def test_scheda_fai_il_punto_dopo_4_settimane(db, profilo):
    _scheda(db, profilo, 27)
    assert "scheda-fai-il-punto" not in _chiavi(db, profilo)

    db.query(WorkoutPlan).one().started_at = giorni_fa(28)
    db.commit()
    nota = next(n for n in agent_notes.build(db, profilo, today=OGGI) if n.section == "scheda")
    assert nota.action == "feedback"
    assert "20-25%" in nota.text


def test_feedback_recente_toglie_la_nota(db, profilo):
    piano = _scheda(db, profilo, 40)
    db.add(TrainingFeedback(
        profile_id=profilo.id, workout_plan_id=piano.id, date=giorni_fa(3),
        progress_perception=ProgressPerception.GOOD, recovery_quality=RecoveryQuality.GOOD,
    ))
    db.commit()
    assert "scheda-fai-il-punto" not in _chiavi(db, profilo)


# --- Peso e alimentazione --------------------------------------------------------------


def _pesate(db, profilo, inizio: float, fine: float, giorni: int = 35) -> None:
    for n in range(giorni + 1):
        peso = inizio + (fine - inizio) * n / giorni
        db.add(WeightLog(profile_id=profilo.id, date=giorni_fa(giorni - n), weight_kg=peso))
    db.commit()


def test_calo_troppo_rapido_in_definizione(db, profilo):
    profilo.goal = Goal.FAT_LOSS
    db.commit()
    _pesate(db, profilo, 80.0, 73.0)  # ~1,4 kg a settimana
    nota = next(n for n in agent_notes.build(db, profilo, today=OGGI) if n.section == "progressi")
    assert nota.key.startswith("calo-troppo-rapido")
    assert nota.knowledge_tags == ["composizione_corporea"]


def test_calo_moderato_nessuna_nota(db, profilo):
    profilo.goal = Goal.FAT_LOSS
    db.commit()
    _pesate(db, profilo, 80.0, 78.0)  # ~0,4 kg a settimana
    assert "calo-troppo-rapido" not in _chiavi(db, profilo)


def test_massa_con_peso_in_calo(db, profilo):
    _pesate(db, profilo, 80.0, 79.0)
    assert "massa-peso-in-calo" in _chiavi(db, profilo)


def test_troppe_poche_pesate_nessuna_conclusione(db, profilo):
    profilo.goal = Goal.FAT_LOSS
    db.commit()
    _pesate(db, profilo, 80.0, 77.0, giorni=10)
    assert _chiavi(db, profilo, "progressi") == []


def _giornata(db, profilo, giorno: dt.date, proteine: float) -> None:
    pasto = MealLog(profile_id=profilo.id, date=giorno, meal_type="lunch")
    db.add(pasto)
    db.flush()
    db.add(MealItem(
        meal_log_id=pasto.id, name="x", quantity_g=100,
        kcal=2000, protein_g=proteine, carbs_g=200, fat_g=60,
    ))
    db.commit()


def test_proteine_sotto_target_in_media(db, profilo):
    for n in (1, 2, 3):
        _giornata(db, profilo, giorni_fa(n), proteine=60)
    nota = next(n for n in agent_notes.build(db, profilo, today=OGGI) if n.section == "diario")
    assert nota.knowledge_tags == ["proteine"]


def test_proteine_serve_una_media_di_almeno_3_giorni(db, profilo):
    for n in (1, 2):
        _giornata(db, profilo, giorni_fa(n), proteine=40)
    assert _chiavi(db, profilo, "diario") == []


def test_proteine_coperte_nessuna_nota(db, profilo):
    for n in (1, 2, 3):
        _giornata(db, profilo, giorni_fa(n), proteine=170)
    assert _chiavi(db, profilo, "diario") == []


def test_la_chat_conosce_le_note_mostrate(db, profilo):
    from app.services import chat_agent

    _integratore(db, profilo, 30)
    contesto = chat_agent._user_context(db, profilo)
    assert "Note di Kilo mostrate" in contesto
    assert "Creatina: scorte piene" in contesto
