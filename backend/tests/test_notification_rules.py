"""Regole delle notifiche: cosa arriva, quando, e quanto poco.

Tutto è deterministico: nessuna rete, nessun LLM. L'invio è sostituito da
una lista, così i test guardano *quali* notifiche partono e in che ordine.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import (
    Exercise,
    MealLog,
    NotificationLog,
    PushSubscription,
    SavedRecipe,
    SessionSet,
    SupplementDeclaration,
    SupplementIntake,
    User,
    UserProfile,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
)
from app.services import notification_rules, push_notifications, training_schedule

ROMA = push_notifications.FUSO
OGGI = dt.date(2026, 9, 22)  # martedì


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://", future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _utente(db: Session) -> tuple[User, UserProfile]:
    u = User(email="a@example.com", password_hash="x")
    db.add(u)
    db.flush()
    p = UserProfile(
        user_id=u.id, display_name="Salvatore", birth_date=dt.date(1994, 3, 1), sex="male",
        height_cm=178, weight_kg=80, goal="hypertrophy", training_days_per_week=3,
    )
    db.add(p)
    db.add(PushSubscription(user_id=u.id, endpoint="https://push.example/a", p256dh="k", auth="a"))
    db.flush()
    return u, p


def _scheda(db: Session, profile: UserProfile, *, giorni: list[int], inizio: dt.date) -> WorkoutPlan:
    piano = WorkoutPlan(
        profile_id=profile.id, name="Upper / Lower", goal="hypertrophy", days_per_week=3,
        started_at=inizio, training_weekdays_raw=training_schedule.serialize(giorni),
    )
    db.add(piano)
    db.flush()
    return piano


def _note(db: Session, user: User, *, today: dt.date = OGGI, evening_hour: int = 20) -> list[notification_rules.Notification]:
    s = notification_rules.settings_for(db, user.id)
    return notification_rules.build(db, user, today=today, fuso=ROMA, settings=s, evening_hour=evening_hour)


def _invia(db: Session, *, ora: int, giorno: dt.date = OGGI) -> tuple[list, push_notifications.DispatchResult]:
    inviate = []
    r = push_notifications.dispatch(
        db,
        now=dt.datetime.combine(giorno, dt.time(ora), tzinfo=ROMA),
        sender=lambda sub, msg: inviate.append(msg),
    )
    return inviate, r


def test_promemoria_allenamento_all_ora_abituale(db: Session):
    u, p = _utente(db)
    _scheda(db, p, giorni=[OGGI.weekday()], inizio=OGGI - dt.timedelta(days=7))
    # Tre sessioni avviate alle 19 italiane: l'ora si ricava da qui.
    for i in (7, 14, 21):
        db.add(
            WorkoutSession(
                profile_id=p.id, date=OGGI - dt.timedelta(days=i),
                started_at=dt.datetime.combine(OGGI - dt.timedelta(days=i), dt.time(19), tzinfo=ROMA),
            )
        )
    db.commit()

    assert notification_rules.gym_hour(db, p, fuso=ROMA) == 19
    chiavi = {n.key: n for n in _note(db, u)}
    allenamento = next(n for k, n in chiavi.items() if k.startswith("allenamento:"))
    assert allenamento.hours[0] == 19 and allenamento.section == "scheda"

    assert _invia(db, ora=18)[0] == []
    inviate, _ = _invia(db, ora=19)
    assert any("Upper / Lower" in m.body for m in inviate)


def test_ora_palestra_scelta_a_mano_vince(db: Session):
    u, p = _utente(db)
    _scheda(db, p, giorni=[OGGI.weekday()], inizio=OGGI)
    s = notification_rules.settings_for(db, u.id)
    s.gym_hour = 7
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("allenamento:"))
    assert nota.hours[0] == 7


def test_progressione_dei_carichi(db: Session):
    u, p = _utente(db)
    piano = _scheda(db, p, giorni=[0], inizio=OGGI - dt.timedelta(days=7))
    panca = Exercise(name="Bench Press", name_it="Panca piana", primary_muscle="Chest", is_compound=True)
    db.add(panca)
    db.flush()
    db.add(WorkoutPlanExercise(
        workout_plan_id=piano.id, exercise_id=panca.id, day_label="A", order_index=0,
        target_sets=3, target_reps_min=6, target_reps_max=8, target_rir=2, rest_seconds=150,
    ))
    for giorni_fa in (7, 3):
        sessione = WorkoutSession(profile_id=p.id, workout_plan_id=piano.id, date=OGGI - dt.timedelta(days=giorni_fa))
        db.add(sessione)
        db.flush()
        for n in range(3):
            db.add(SessionSet(
                workout_session_id=sessione.id, exercise_id=panca.id, set_number=n + 1,
                weight_kg=60, reps=8, rir=1,
            ))
    db.commit()

    nota = next(n for n in _note(db, u) if n.key.startswith("carichi:"))
    assert "Panca piana" in nota.body and "62,5" in nota.body.replace(".", ",")


def test_niente_progressione_se_non_chiude_il_range(db: Session):
    u, p = _utente(db)
    piano = _scheda(db, p, giorni=[0], inizio=OGGI)
    squat = Exercise(name="Squat", name_it="Squat", primary_muscle="Quads", is_compound=True)
    db.add(squat)
    db.flush()
    db.add(WorkoutPlanExercise(
        workout_plan_id=piano.id, exercise_id=squat.id, day_label="A", order_index=0,
        target_sets=3, target_reps_min=6, target_reps_max=8, target_rir=2, rest_seconds=150,
    ))
    for giorni_fa in (7, 3):
        sessione = WorkoutSession(profile_id=p.id, workout_plan_id=piano.id, date=OGGI - dt.timedelta(days=giorni_fa))
        db.add(sessione)
        db.flush()
        db.add(SessionSet(workout_session_id=sessione.id, exercise_id=squat.id, set_number=1, weight_kg=80, reps=6))
    db.commit()
    assert not [n for n in _note(db, u) if n.key.startswith("carichi:")]


def test_scheda_vecchia_dopo_sei_settimane(db: Session):
    u, p = _utente(db)
    _scheda(db, p, giorni=[0], inizio=OGGI - dt.timedelta(weeks=7))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("scheda-vecchia:"))
    assert "7 settimane" in nota.body


def test_integratori_giorno_di_riposo_e_di_allenamento(db: Session):
    u, p = _utente(db)
    db.add(SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1))
    db.commit()
    riposo = next(n for n in _note(db, u) if n.key.startswith("integratori:"))
    assert "riposo" in riposo.body and riposo.hours == (13, 14)

    _scheda(db, p, giorni=[OGGI.weekday()], inizio=OGGI)
    db.commit()
    allenamento = next(n for n in _note(db, u) if n.key.startswith("integratori:"))
    assert "mezz'ora" in allenamento.body and "250-300 ml" in allenamento.body


def test_tappa_della_creatina_al_ventottesimo_giorno(db: Session):
    u, p = _utente(db)
    d = SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1)
    db.add(d)
    db.flush()
    for i in range(28):
        db.add(SupplementIntake(supplement_id=d.id, date=OGGI - dt.timedelta(days=i), doses=1))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("tappa:"))
    assert "mantenimento" in nota.body


def test_diario_fermo_da_due_giorni(db: Session):
    u, p = _utente(db)
    db.add(MealLog(profile_id=p.id, date=OGGI - dt.timedelta(days=3), meal_type="lunch", kcal=600, protein_g=40))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("diario-fermo:"))
    assert "3 giorni" in nota.body


def test_proteine_oltre_il_necessario(db: Session):
    u, p = _utente(db)
    db.add(MealLog(profile_id=p.id, date=OGGI, meal_type="dinner", kcal=1200, protein_g=210))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("proteine-alte:"))
    assert "2,4" in nota.body


def test_proteine_basse_propone_una_ricetta(db: Session):
    u, p = _utente(db)
    db.add(MealLog(profile_id=p.id, date=OGGI, meal_type="lunch", kcal=500, protein_g=20))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("proteine-basse:"))
    assert nota.section == "ricette"


def test_ricetta_salvata_e_mai_provata(db: Session):
    u, p = _utente(db)
    db.add(SavedRecipe(
        profile_id=p.id, source="kilo", external_id="pollo", data={"name": "Pollo al limone"},
        created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=12),
    ))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("ricetta-salvata:"))
    assert "Pollo al limone" in nota.body


def test_riepilogo_solo_di_lunedi(db: Session):
    u, p = _utente(db)
    _scheda(db, p, giorni=[0, 2, 4], inizio=OGGI - dt.timedelta(days=30))
    for i in range(1, 8):
        giorno = OGGI + dt.timedelta(days=7 - OGGI.weekday()) - dt.timedelta(days=i)
        if giorno.weekday() in (0, 2, 4):
            s = WorkoutSession(profile_id=p.id, date=giorno, started_at=dt.datetime.combine(giorno, dt.time(19), tzinfo=ROMA))
            db.add(s)
    db.commit()
    lunedi = OGGI + dt.timedelta(days=7 - OGGI.weekday())
    assert not [n for n in _note(db, u) if n.key.startswith("riepilogo:")]
    assert [n for n in _note(db, u, today=lunedi) if n.key.startswith("riepilogo:")]


def test_categoria_spenta_non_produce_notifiche(db: Session):
    u, p = _utente(db)
    db.add(SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1))
    s = notification_rules.settings_for(db, u.id)
    s.supplements = False
    db.commit()
    assert not [n for n in _note(db, u) if n.key.startswith("integratori:")]


def test_al_massimo_tre_al_giorno_e_mai_due_volte(db: Session):
    u, p = _utente(db)
    _scheda(db, p, giorni=[OGGI.weekday()], inizio=OGGI - dt.timedelta(weeks=8))
    db.add(SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1))
    db.add(MealLog(profile_id=p.id, date=OGGI - dt.timedelta(days=4), meal_type="lunch", kcal=500, protein_g=20))
    db.add(SavedRecipe(
        profile_id=p.id, source="kilo", external_id="x", data={"name": "Pollo"},
        created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30),
    ))
    db.commit()

    inviate, _ = _invia(db, ora=20)
    assert len(inviate) == push_notifications.MAX_PER_DAY
    # Riprovando subito dopo non parte più nulla: né ripetizioni né sforamenti.
    assert _invia(db, ora=21)[0] == []
    assert db.scalar(select(NotificationLog.key).where(NotificationLog.user_id == u.id)) is not None


def test_promemoria_integratori_a_fine_allenamento(db: Session):
    u, p = _utente(db)
    db.add(SupplementDeclaration(profile_id=p.id, kind="protein_powder", dose_amount=30, dose_unit="g", doses_per_day=1))
    db.commit()
    inviate = []
    assert push_notifications.after_session(db, p, sender=lambda sub, m: inviate.append(m)) is True
    assert "mezz'ora" in inviate[0].body
    # Una sola volta, anche chiudendo due sessioni nello stesso giorno.
    assert push_notifications.after_session(db, p, sender=lambda sub, m: inviate.append(m)) is False


def test_niente_promemoria_se_gli_integratori_sono_gia_segnati(db: Session):
    u, p = _utente(db)
    d = SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1)
    db.add(d)
    db.flush()
    db.add(SupplementIntake(supplement_id=d.id, date=OGGI, doses=1))
    db.commit()
    assert push_notifications.after_session(db, p, now=dt.datetime.combine(OGGI, dt.time(19), tzinfo=ROMA)) is False
