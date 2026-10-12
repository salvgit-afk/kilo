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
SERA = dt.datetime.combine(OGGI, dt.time(19), tzinfo=ROMA)


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
                # In UTC, come le salva l'app: SQLite scarta il fuso.
                started_at=dt.datetime.combine(
                    OGGI - dt.timedelta(days=i), dt.time(19), tzinfo=ROMA
                ).astimezone(dt.timezone.utc),
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
    # Consigli solo per ciò che è dichiarato: qui solo creatina, niente proteine.
    assert "creatina con un pasto" in allenamento.body
    assert "proteine" not in allenamento.body and "mezz'ora" not in allenamento.body


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
    # Prima di cena mancano quasi sempre: non si dice niente.
    assert not [n for n in _note(db, u) if n.key.startswith("proteine-basse:")]
    db.add(MealLog(profile_id=p.id, date=OGGI, meal_type="dinner", kcal=600, protein_g=25))
    db.commit()
    nota = next(n for n in _note(db, u) if n.key.startswith("proteine-basse:"))
    assert nota.section == "ricette" and nota.hours == (20, 22)


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
    assert push_notifications.after_session(db, p, now=SERA, sender=lambda sub, m: inviate.append(m)) is True
    # Le fonti dicono fino a 2 ore dopo, non "entro mezz'ora".
    assert "un paio d'ore" in inviate[0].body and "mezz'ora" not in inviate[0].body
    # Una sola volta, anche chiudendo due sessioni nello stesso giorno.
    assert push_notifications.after_session(db, p, now=SERA, sender=lambda sub, m: inviate.append(m)) is False
    # E una volta in tutta la giornata: niente "Integratori di oggi" né nel promemoria della sera.
    assert not [n for n in _note(db, u) if n.key.startswith("integratori:")]
    sera = notification_rules.evening_summary(db, p, OGGI, 20)
    assert not sera or "proteine in polvere" not in sera[0].body


def test_integratori_gia_ricordati_a_meta_giornata_non_si_ripetono(db: Session):
    from app.models import NotificationLog

    u, p = _utente(db)
    db.add(SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1))
    db.add(NotificationLog(user_id=u.id, key=f"integratori:{OGGI}", sent_on=OGGI))
    db.commit()
    assert push_notifications.after_session(db, p, now=SERA, sender=lambda sub, m: None) is False


def test_niente_promemoria_se_gli_integratori_sono_gia_segnati(db: Session):
    u, p = _utente(db)
    d = SupplementDeclaration(profile_id=p.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1)
    db.add(d)
    db.flush()
    db.add(SupplementIntake(supplement_id=d.id, date=OGGI, doses=1))
    db.commit()
    assert push_notifications.after_session(db, p, now=dt.datetime.combine(OGGI, dt.time(19), tzinfo=ROMA)) is False


# --- La scheda in uso decide i giorni di allenamento ----------------------------------


def test_promemoria_dalla_scheda_in_uso_non_da_tutte_le_attive(db: Session):
    """Una scheda da 3 giorni (lun, mer, ven) e una da 4 (lun, mar, gio, ven):
    con quella da 4 scelta, il mercoledì è riposo."""
    from app.services import daily_reminders

    _, p = _utente(db)
    tre = _scheda(db, p, giorni=[0, 2, 4], inizio=OGGI - dt.timedelta(days=30))
    quattro = _scheda(db, p, giorni=[0, 1, 3, 4], inizio=OGGI - dt.timedelta(days=30))
    mercoledi = OGGI + dt.timedelta(days=1)

    training_schedule.set_current_plan(db, quattro)
    db.commit()
    assert daily_reminders.workouts_due(db, p, mercoledi) == []
    assert daily_reminders.workouts_due(db, p, OGGI) == [quattro]  # martedì

    training_schedule.set_current_plan(db, tre)
    db.commit()
    assert daily_reminders.workouts_due(db, p, mercoledi) == [tre]
    assert daily_reminders.workouts_due(db, p, OGGI) == []
    assert not quattro.is_current, "al più una scheda in uso"


def test_senza_scelta_vale_la_scheda_piu_recente(db: Session):
    _, p = _utente(db)
    _scheda(db, p, giorni=[0, 2, 4], inizio=OGGI - dt.timedelta(days=30))
    recente = _scheda(db, p, giorni=[1, 3], inizio=OGGI - dt.timedelta(days=3))
    db.commit()
    assert training_schedule.current_plan(db, p.id) == recente


def test_allenamento_iniziato_con_l_altra_scheda_spegne_il_promemoria(db: Session):
    from app.services import daily_reminders

    _, p = _utente(db)
    tre = _scheda(db, p, giorni=[1], inizio=OGGI - dt.timedelta(days=30))
    quattro = _scheda(db, p, giorni=[1], inizio=OGGI - dt.timedelta(days=30))
    training_schedule.set_current_plan(db, quattro)
    db.add(WorkoutSession(
        profile_id=p.id, workout_plan_id=tre.id, date=OGGI,
        started_at=dt.datetime.combine(OGGI, dt.time(18), tzinfo=dt.timezone.utc),
    ))
    db.commit()
    assert daily_reminders.workouts_due(db, p, OGGI) == []


def test_un_utente_in_errore_non_ferma_gli_altri(db: Session, monkeypatch):
    """Ogni persona a sé: un errore su una non blocca le altre, e quello già
    mandato resta registrato (il giro dopo non lo rimanda)."""
    from app.models import NotificationLog

    u1, p1 = _utente(db)
    u2 = User(email="b@example.com", password_hash="x")
    db.add(u2)
    db.flush()
    p2 = UserProfile(user_id=u2.id, display_name="Bea", birth_date=dt.date(1996, 1, 1), sex="female",
                     height_cm=165, weight_kg=60, goal="hypertrophy", training_days_per_week=3)
    db.add(p2)
    db.add(PushSubscription(user_id=u2.id, endpoint="https://push.example/b", p256dh="k", auth="a"))
    db.flush()
    db.add(SupplementDeclaration(profile_id=p2.id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1))
    db.commit()
    originale = notification_rules.build

    def build(db_, utente, **kw):
        if utente.id == u1.id:
            raise RuntimeError("dati strani")
        return originale(db_, utente, **kw)

    monkeypatch.setattr(notification_rules, "build", build)
    inviate, r = _invia(db, ora=20)
    assert inviate and r.failed == 1
    registrate = {k for (k,) in db.query(NotificationLog.key).filter(NotificationLog.user_id == u2.id)}
    assert registrate
    assert _invia(db, ora=20)[0] == [], "il giro dopo non rimanda le stesse"
