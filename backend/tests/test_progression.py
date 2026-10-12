"""Doppia progressione con il RIR: quando salire, restare o scendere."""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import SessionSet
from app.services import progression
from tests.test_training_log import _account, _scheda, ambiente  # noqa: F401


def _serie(*valori):
    """(kg, ripetizioni, rir) -> serie."""
    return [SessionSet(set_number=i + 1, weight_kg=kg, reps=r, rir=rir) for i, (kg, r, rir) in enumerate(valori)]


def _consiglio(serie, *, compound=True, rir=2):
    return progression.suggest(serie, reps_min=6, reps_max=8, target_rir=rir, is_compound=compound)


def test_tutte_al_massimo_con_il_margine_previsto_si_sale():
    c = _consiglio(_serie((100, 8, 2), (100, 8, 2), (100, 8, 3)))
    assert c.kind == "carico" and c.weight_kg == 105 and c.reps == 6
    # Un'unità sotto il RIR previsto va ancora bene; senza RIR segnato anche.
    assert _consiglio(_serie((60, 8, 1), (60, 8, 1))).weight_kg == 62.5
    assert _consiglio(_serie((60, 8, None), (60, 8, None))).kind == "carico"


def test_al_massimo_ma_al_cedimento_si_resta():
    c = _consiglio(_serie((100, 8, 0), (100, 8, 1)))
    assert c.kind == "mantieni" and c.weight_kg == 100
    assert "RIR 0" in c.reason
    # Oltre il range di due ripetizioni si sale comunque.
    assert _consiglio(_serie((100, 10, 0), (100, 10, 0))).kind == "carico"


def test_una_ripetizione_in_piu_finche_non_si_chiude_il_range():
    c = _consiglio(_serie((100, 8, 2), (100, 7, 2), (100, 6, 1)))
    assert c.kind == "ripetizioni" and c.weight_kg == 100 and c.reps == 7


def test_sotto_il_range_si_scende():
    c = _consiglio(_serie((100, 5, 0), (100, 4, 0)))
    assert c.kind == "scendi" and c.weight_kg == 95


def test_conta_il_carico_piu_alto_non_le_serie_di_avvicinamento():
    c = _consiglio(_serie((60, 12, 5), (100, 8, 2), (100, 8, 2)))
    assert c.kind == "carico" and c.weight_kg == 105


@pytest.mark.parametrize("carico,passo", [(8, 1.0), (14, 2.0), (30, 2.5)])
def test_passo_piccolo_per_gli_esercizi_di_isolamento(carico, passo):
    c = progression.suggest(_serie((carico, 12, 2), (carico, 12, 2)), reps_min=10, reps_max=12,
                            target_rir=2, is_compound=False)
    assert c.weight_kg == carico + passo


def test_corpo_libero_si_aggiunge_carico():
    c = _consiglio(_serie((0, 8, 2), (0, 8, 2)))
    assert c.kind == "carico" and c.weight_kg is None


def test_ultima_volta_con_la_scheda_porta_il_consiglio(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    piano, _, panca, _squat = _scheda(db, pid)
    client.post(f"/workout/sessions?profile_id={pid}", headers=h, json={
        "day_label": "A", "date": str(dt.date.today() - dt.timedelta(days=3)),
        "sets": [{"exercise_id": panca.id, "set_number": n, "reps": 8, "weight_kg": 60, "rir": 2} for n in (1, 2, 3)],
    })
    base = f"/workout/last-performance?profile_id={pid}&exercise_ids={panca.id}"
    senza = client.get(base, headers=h).json()[str(panca.id)]
    assert senza["suggestion"] is None
    con = client.get(f"{base}&plan_id={piano.id}", headers=h).json()[str(panca.id)]
    assert con["suggestion"]["kind"] == "carico" and con["suggestion"]["weight_kg"] == 62.5
    assert con["suggestion"]["text"] == "Prova 62,5 kg"


def test_il_coach_riceve_scheda_carichi_volume_e_peso(db):
    """"Analizza i miei progressi" deve partire dai dati veri, non da nome
    della scheda e numero di esercizi."""
    from app.models import Exercise, User, UserProfile, WeightLog, WorkoutPlan, WorkoutPlanExercise, WorkoutSession
    from app.services import chat_agent, clock

    oggi = clock.today()
    u = User(email="a@example.com", password_hash="x")
    db.add(u)
    db.flush()
    p = UserProfile(user_id=u.id, display_name="S", birth_date=dt.date(1994, 3, 1), sex="male", height_cm=178,
                    weight_kg=80, goal="hypertrophy", training_days_per_week=4)
    panca = Exercise(name="Chest Press", name_it="Chest press", primary_muscle="Chest",
                     secondary_muscles="Triceps", is_compound=True)
    db.add_all([p, panca])
    db.flush()
    piano = WorkoutPlan(profile_id=p.id, name="Push/Pull", goal="hypertrophy", days_per_week=4,
                        started_at=oggi - dt.timedelta(weeks=3))
    db.add(piano)
    db.flush()
    db.add(WorkoutPlanExercise(workout_plan_id=piano.id, exercise_id=panca.id, day_label="Push A", order_index=0,
                               target_sets=3, target_reps_min=8, target_reps_max=10, target_rir=2, rest_seconds=120))
    for giorni_fa, kg in ((10, 60), (3, 62.5)):
        s = WorkoutSession(profile_id=p.id, workout_plan_id=piano.id, date=oggi - dt.timedelta(days=giorni_fa),
                           day_label="Push A")
        db.add(s)
        db.flush()
        db.add_all([SessionSet(workout_session_id=s.id, exercise_id=panca.id, set_number=n, weight_kg=kg,
                               reps=10, rir=2) for n in (1, 2, 3)])
    for giorni_fa in (6, 4, 2):
        db.add(WeightLog(profile_id=p.id, date=oggi - dt.timedelta(days=giorni_fa), weight_kg=80.4))
    db.commit()

    contesto = chat_agent._user_context(db, p)
    assert "Push A: Chest press 3×8-10 RIR 2, recupero 120s" in contesto
    assert "pronti a salire: Chest press (prova 65 kg)" in contesto
    assert "Massimale stimato (8 settimane): Chest press" in contesto
    assert "Serie nell'ultima settimana conclusa" in contesto
    assert "Peso: media mobile 80,4 kg" in contesto
