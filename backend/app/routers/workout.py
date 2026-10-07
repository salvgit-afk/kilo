"""Schede di allenamento, sessioni svolte, alternative e autoregolazione."""

from __future__ import annotations

import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Exercise,
    ExercisePreference,
    ScreeningRecord,
    SessionSet,
    TrainingFeedback,
    User,
    UserProfile,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
)
from app.routers.auth import current_user
from app.routers.profile import ensure_owner, owned_profile
from app.schemas import (
    AlternativeOut,
    ChatActionOut,
    ChatIn,
    ChatOut,
    ExerciseGuidanceOut,
    ExerciseHistoryOut,
    ExerciseOut,
    ExerciseSessionOut,
    FeedbackIn,
    ManualSetsIn,
    PlanExerciseAddIn,
    PlanExerciseUpdate,
    PlanGenerationOut,
    PlanOrderIn,
    PlanScheduleIn,
    PlanVolumeOut,
    PreferenceIn,
    PreferenceOut,
    ExerciseNoteIn,
    ExerciseNoteOut,
    SessionFinishIn,
    SessionIn,
    SessionOut,
    SessionRecordOut,
    SessionSetIn,
    SessionSetOut,
    SessionSetUpdate,
    SessionSummaryOut,
    SessionUpdate,
    SwapIn,
    VolumeRecommendationOut,
    WorkoutPlanOut,
)
from app.services import (
    autoregulation,
    chat_agent,
    clock,
    exercise_guidance,
    exercise_library,
    exercise_notes,
    exercise_swap,
    plan_editing,
    push_notifications,
    rate_limit,
    training_log,
    training_schedule,
    translation,
    workout_generator,
)

# Ogni rotta richiede l'accesso, anche il catalogo esercizi: i dati di un
# profilo passano da `owned_profile`, che controlla che sia di chi chiama.
router = APIRouter(
    prefix="/workout", tags=["allenamento"], dependencies=[Depends(current_user)]
)


def _limit(db: Session, user: User, kind: str) -> None:
    try:
        rate_limit.consume_daily(db, user.id, kind)
    except rate_limit.RateLimited as e:
        raise HTTPException(
            status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)}
        ) from e


def _plan_row(db: Session, profile: UserProfile, plan_exercise_id: int) -> WorkoutPlanExercise:
    """Una riga di scheda, solo se la scheda è del profilo."""
    riga = db.get(WorkoutPlanExercise, plan_exercise_id)
    if riga is None or riga.plan is None or riga.plan.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Esercizio non presente in scheda")
    return riga


def _latest_screening(db: Session, profile_id: int) -> ScreeningRecord | None:
    return db.scalar(
        select(ScreeningRecord)
        .where(ScreeningRecord.profile_id == profile_id)
        .order_by(ScreeningRecord.created_at.desc())
    )


def _active_plan(db: Session, profile_id: int) -> WorkoutPlan | None:
    """La scheda in uso fra quelle attive (possono essercene più d'una)."""
    return training_schedule.current_plan(db, profile_id)


def _plan_for(db: Session, profile_id: int, plan_id: int | None) -> WorkoutPlan | None:
    """La scheda indicata, se è del profilo; senza indicazione quella in uso."""
    if plan_id is None:
        return _active_plan(db, profile_id)
    piano = db.get(WorkoutPlan, plan_id)
    if piano is None or piano.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    return piano


@router.post("/plans/generate", response_model=PlanGenerationOut, status_code=201)
def generate_plan(
    explain: bool = True,
    split_type: str | None = None,
    replace_plan_id: int | None = None,
    sets_per_exercise: int | None = Query(default=None, ge=1, le=10),
    reps_min: int | None = Query(default=None, ge=1, le=50),
    reps_max: int | None = Query(default=None, ge=1, le=50),
    weekdays: list[int] = Query(default=[], max_length=7),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
    user: User = Depends(current_user),
) -> PlanGenerationOut:
    """Genera una scheda e la aggiunge a quelle attive.

    I parametri (serie, ripetizioni, RIR, recuperi) sono calcolati dai file
    della knowledge base. Con `explain=true` la motivazione viene riscritta
    in linguaggio naturale dall'LLM, che però non può modificare alcun
    numero: se non è disponibile resta la spiegazione deterministica.

    `replace_plan_id` sostituisce una scheda esistente («Rigenera») invece di
    affiancarla. `sets_per_exercise` e `reps_min`/`reps_max` sono una scelta
    manuale dell'utente e la scheda dichiara che non seguono le fonti.
    """
    screening = _latest_screening(db, profile.id)

    giorni: list[int] | None = None
    if weekdays:
        try:
            giorni = training_schedule.normalize(weekdays)
        except training_schedule.ScheduleError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    if (reps_min is None) != (reps_max is None):
        raise HTTPException(status_code=422, detail="Indica sia le ripetizioni minime sia le massime")
    if reps_min is not None and reps_max is not None and reps_min > reps_max:
        raise HTTPException(
            status_code=422, detail="Le ripetizioni minime non possono superare le massime"
        )
    # Ogni generazione può chiamare l'LLM per la spiegazione.
    _limit(db, user, "plan_generation")
    if replace_plan_id is not None:
        da_sostituire = _plan_for(db, profile.id, replace_plan_id)
        if da_sostituire is None or not da_sostituire.is_active:
            raise HTTPException(status_code=404, detail="Scheda da sostituire non trovata")

    try:
        # La scelta esplicita dell'utente ha la precedenza su quella salvata
        # nel profilo, così si può provare uno split diverso senza modificarlo.
        if split_type:
            profile.split_type = split_type
            db.commit()
        # I giorni scelti decidono la frequenza con cui si costruisce la scheda.
        if giorni:
            profile.training_days_per_week = len(giorni)
            db.commit()
        generated = workout_generator.generate_plan(
            db, profile, screening=screening, split_type=split_type
        )
    except workout_generator.GenerationError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    workout_generator.apply_manual_targets(
        generated,
        sets=sets_per_exercise,
        reps=(reps_min, reps_max) if reps_min is not None and reps_max is not None else None,
    )

    used_llm = False
    if explain:
        spiegazione = workout_generator.explain_plan(generated, profile)
        used_llm = spiegazione != generated.rationale
        generated.rationale = spiegazione

    plan = workout_generator.persist_plan(
        db, profile, generated, used_llm=used_llm, replace_plan_id=replace_plan_id
    )
    if giorni:
        plan.training_weekdays_raw = training_schedule.serialize(giorni)
        db.commit()
    translation.ensure_translated(db, [riga.exercise for riga in plan.exercises])

    return PlanGenerationOut(
        plan=WorkoutPlanOut.model_validate(plan),
        weekly_sets_per_muscle=generated.weekly_sets_per_muscle,
        weekly_sets_equivalent=generated.weekly_sets_equivalent,
        warnings=generated.warnings,
        knowledge_tags=generated.knowledge_tags,
    )


@router.put("/plans/{plan_id}/current", response_model=WorkoutPlanOut)
def choose_current_plan(
    plan_id: int, db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
) -> WorkoutPlan:
    """La scheda scelta nel menu diventa quella in uso: i suoi giorni decidono
    promemoria, notifiche e pagina Oggi."""
    piano = _plan_for(db, profile.id, plan_id)
    if piano is None or not piano.is_active:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    training_schedule.set_current_plan(db, piano)
    db.commit()
    db.refresh(piano)
    return piano


@router.get("/plans/active", response_model=WorkoutPlanOut | None)
def read_active_plan(
    db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
):
    return _active_plan(db, profile.id)


@router.get("/plans", response_model=list[WorkoutPlanOut])
def list_plans(
    active_only: bool = False,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[WorkoutPlan]:
    query = select(WorkoutPlan).where(WorkoutPlan.profile_id == profile.id)
    if active_only:
        query = query.where(WorkoutPlan.is_active.is_(True))
    return list(db.scalars(query.order_by(WorkoutPlan.started_at.desc(), WorkoutPlan.id.desc())))


@router.delete("/plans/{plan_id}", status_code=204, response_model=None)
def delete_plan(
    plan_id: int, db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
) -> None:
    """Toglie la scheda da quelle attive.

    Non la cancella dal database: sessioni e report di progressione continuano
    a riferirsi a ciò che era in programma in quel periodo.
    """
    if workout_generator.archive_plan(db, profile, plan_id) is None:
        raise HTTPException(status_code=404, detail="Scheda non trovata")


@router.get(
    "/plan-exercises/{plan_exercise_id}/alternatives",
    response_model=list[AlternativeOut],
)
def list_alternatives(
    plan_exercise_id: int,
    limit: int = 6,
    q: str | None = None,
    muscle: str | None = None,
    equipment: str | None = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[AlternativeOut]:
    """Alternative per lo stesso gruppo muscolare, filtrabili per nome.

    Serve all'aderenza: un esercizio scelto e gradito viene eseguito, uno
    imposto e noioso viene saltato.
    """
    limit = max(1, min(limit, 200))
    riga = _plan_row(db, profile, plan_exercise_id)

    try:
        alternative = exercise_swap.find_alternatives(
            db, profile, riga.exercise, limit=limit, q=q, muscle=muscle, equipment=equipment
        )
    except exercise_swap.SwapError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    translation.ensure_translated(db, [a.exercise for a in alternative])
    return [
        AlternativeOut(
            exercise=a.exercise,
            preserves_stimulus=a.preserves_stimulus,
            already_preferred=a.already_preferred,
        )
        for a in alternative
    ]


@router.post("/plan-exercises/{plan_exercise_id}/swap", response_model=WorkoutPlanOut)
def swap_exercise(
    plan_exercise_id: int,
    payload: SwapIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutPlan:
    riga = _plan_row(db, profile, plan_exercise_id)

    sostituto = db.get(Exercise, payload.replacement_exercise_id)
    if sostituto is None:
        raise HTTPException(status_code=404, detail="Esercizio sostitutivo non trovato")

    try:
        exercise_swap.swap_in_plan(
            db, profile, riga, sostituto,
            mark_old_as_disliked=payload.mark_old_as_disliked,
            allow_muscle_change=payload.allow_muscle_change,
        )
    except exercise_swap.SwapError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    return db.get(WorkoutPlan, riga.workout_plan_id)


@router.post("/sessions", response_model=SessionOut, status_code=201)
def log_session(
    payload: SessionIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutSession:
    """Registra una sessione svolta con le serie effettive.

    Sono questi i dati su cui si basano i report di progressione, e non
    dipendono da nessuna API esterna.
    """
    # Già arrivata (inviata di nuovo dopo una risposta persa): la stessa.
    if payload.client_id:
        esistente = db.scalar(select(WorkoutSession).where(WorkoutSession.client_id == payload.client_id))
        if esistente is not None:
            if esistente.profile_id != profile.id:
                raise HTTPException(status_code=409, detail="Identificativo già usato")
            return esistente

    piano = _plan_for(db, profile.id, payload.workout_plan_id)

    sessione = WorkoutSession(
        profile_id=profile.id,
        workout_plan_id=piano.id if piano else None,
        # La data la manda il telefono: il server è in UTC e fra mezzanotte e
        # le due, in Italia, avrebbe ancora quella di ieri.
        date=payload.date or clock.today(),
        day_label=payload.day_label,
        perceived_fatigue=payload.perceived_fatigue,
        note=payload.note,
        started_at=_client_time(payload.started_at) if payload.start else None,
        client_id=payload.client_id,
    )
    db.add(sessione)
    db.flush()

    for serie in payload.sets:
        if db.get(Exercise, serie.exercise_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Esercizio {serie.exercise_id} non trovato"
            )
        db.add(SessionSet(workout_session_id=sessione.id, **serie.model_dump()))

    db.commit()
    db.refresh(sessione)
    return sessione


@router.put("/plans/{plan_id}/schedule", response_model=WorkoutPlanOut)
def update_schedule(
    plan_id: int,
    payload: PlanScheduleIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutPlan:
    """Giorni della settimana in cui ci si allena con questa scheda.

    La frequenza diventa il numero di giorni scelti, anche nel profilo: è
    quella che usano i target nutrizionali e il riepilogo della settimana.
    Se i giorni sono più di quelli diversi della scheda (3 allenamenti con
    una A/B), gli allenamenti si alternano.
    """
    piano = _plan_for(db, profile.id, plan_id)
    try:
        giorni = training_schedule.normalize(payload.weekdays)
    except training_schedule.ScheduleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    piano.training_weekdays_raw = training_schedule.serialize(giorni)
    piano.days_per_week = len(giorni)
    profile.training_days_per_week = len(giorni)
    db.commit()
    db.refresh(piano)
    return piano


# --- Parametri della scheda -------------------------------------------------------


@router.patch("/plan-exercises/{plan_exercise_id}", response_model=WorkoutPlanOut)
def update_plan_exercise(
    plan_exercise_id: int,
    payload: PlanExerciseUpdate,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutPlan:
    """Serie, ripetizioni, RIR e recupero di un esercizio della scheda.

    I valori generati vengono dalle fonti; da qui in poi sono una scelta
    dell'utente, che li conosce meglio di un generatore dopo qualche settimana.
    """
    riga = _plan_row(db, profile, plan_exercise_id)
    cambi = payload.model_dump(exclude_unset=True, exclude_none=True)
    minimo = cambi.get("target_reps_min", riga.target_reps_min)
    massimo = cambi.get("target_reps_max", riga.target_reps_max)
    if minimo > massimo:
        raise HTTPException(
            status_code=422,
            detail="Le ripetizioni minime non possono superare le massime.",
        )
    for campo, valore in cambi.items():
        setattr(riga, campo, valore)
    db.commit()
    return db.get(WorkoutPlan, riga.workout_plan_id)


@router.get("/plans/{plan_id}/candidates", response_model=list[AlternativeOut])
def list_candidates(
    plan_id: int,
    muscle: str,
    q: str | None = None,
    limit: int = 24,
    equipment: str | None = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[AlternativeOut]:
    """Esercizi da aggiungere alla scheda per un gruppo muscolare."""
    piano = _plan_for(db, profile.id, plan_id)
    candidati = exercise_swap.find_candidates(
        db, profile, muscle, limit=max(1, min(limit, 200)), q=q, equipment=equipment,
        exclude_ids={e.exercise_id for e in piano.exercises},
    )
    translation.ensure_translated(db, [c.exercise for c in candidati])
    return [
        AlternativeOut(exercise=c.exercise, preserves_stimulus=False, already_preferred=c.already_preferred)
        for c in candidati
    ]


@router.post("/plans/{plan_id}/exercises", response_model=WorkoutPlanOut, status_code=201)
def add_plan_exercise(
    plan_id: int,
    payload: PlanExerciseAddIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutPlan:
    """Aggiunge un esercizio a un giorno della scheda, senza tetto di esercizi."""
    piano = _plan_for(db, profile.id, plan_id)
    esercizio = db.get(Exercise, payload.exercise_id)
    if esercizio is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    try:
        plan_editing.add_exercise(db, profile, piano, esercizio, payload.day_label)
    except plan_editing.EditError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return piano


@router.delete("/plan-exercises/{plan_exercise_id}", response_model=WorkoutPlanOut)
def remove_plan_exercise(
    plan_exercise_id: int,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutPlan:
    """Toglie un esercizio dalla scheda; le serie già registrate restano."""
    riga = _plan_row(db, profile, plan_exercise_id)
    piano_id = riga.workout_plan_id
    try:
        plan_editing.remove_exercise(db, riga)
    except plan_editing.EditError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    piano = db.get(WorkoutPlan, piano_id)
    db.refresh(piano)
    return piano


@router.put("/plans/{plan_id}/order", response_model=WorkoutPlanOut)
def reorder_plan_day(
    plan_id: int,
    payload: PlanOrderIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutPlan:
    """L'ordine degli esercizi di un giorno, scelto trascinandoli."""
    piano = _plan_for(db, profile.id, plan_id)
    try:
        plan_editing.reorder_day(db, piano, payload.day_label, payload.plan_exercise_ids)
    except plan_editing.EditError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return piano


@router.get("/plans/{plan_id}/volume", response_model=PlanVolumeOut)
def read_plan_volume(
    plan_id: int, db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
) -> PlanVolumeOut:
    """Serie settimanali per gruppo e avvisi, ricalcolati sulla scheda attuale."""
    risultato = plan_editing.plan_volume(_plan_for(db, profile.id, plan_id), profile)
    return PlanVolumeOut(weekly_sets_equivalent=risultato.weekly_sets_equivalent, warnings=risultato.warnings)


# --- Sessioni e serie ----------------------------------------------------------------


def _owned_session(db: Session, session_id: int, user: User) -> WorkoutSession:
    sessione = db.get(WorkoutSession, session_id)
    if sessione is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata")
    ensure_owner(db, sessione.profile_id, user, "Sessione non trovata")
    return sessione


# Quanto indietro può arrivare un orario mandato dal telefono: un allenamento
# fatto senza rete e inviato al rientro, anche il giorno dopo.
CLIENT_TIME_MAX_AGE = dt.timedelta(days=2)


def _client_time(
    valore: dt.datetime | None, *, not_before: dt.datetime | None = None
) -> dt.datetime:
    """L'orario mandato dal telefono, se plausibile; altrimenti adesso.

    Plausibile = né nel futuro (oltre qualche minuto di orologio sfasato) né
    più vecchio di due giorni, e non prima dell'avvio. Un orario strano non
    fa fallire il salvataggio: si usa l'ora del server.
    """
    adesso = dt.datetime.now(dt.timezone.utc)
    if valore is None:
        return adesso
    if valore.tzinfo is None:
        valore = valore.replace(tzinfo=dt.timezone.utc)
    inizio = not_before
    if inizio is not None and inizio.tzinfo is None:
        inizio = inizio.replace(tzinfo=dt.timezone.utc)
    if valore > adesso + dt.timedelta(minutes=5) or valore < adesso - CLIENT_TIME_MAX_AGE:
        return adesso
    if inizio is not None and valore < inizio:
        return adesso
    return valore


def _owned_set(db: Session, set_id: int, user: User) -> SessionSet:
    serie = db.get(SessionSet, set_id)
    if serie is None:
        raise HTTPException(status_code=404, detail="Serie non trovata")
    ensure_owner(db, serie.session.profile_id, user, "Serie non trovata")
    return serie


@router.get("/sessions/current", response_model=SessionOut | None)
def current_session(
    day_label: str = Query(max_length=32),
    plan_id: int | None = None,
    today: dt.date | None = None,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutSession | None:
    """La sessione di oggi per quel giorno della scheda, se è già iniziata.

    Riaprendo la pagina a metà allenamento si ritrovano le serie già segnate.
    """
    piano = _plan_for(db, profile.id, plan_id)
    query = select(WorkoutSession).where(
        WorkoutSession.profile_id == profile.id,
        WorkoutSession.date == (today or clock.today()),
        WorkoutSession.day_label == day_label,
    )
    if piano is not None:
        query = query.where(WorkoutSession.workout_plan_id == piano.id)
    return db.scalar(query.order_by(WorkoutSession.id.desc()).limit(1))


@router.get("/sessions/active", response_model=SessionOut | None)
def active_session(
    today: dt.date | None = None,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WorkoutSession | None:
    """L'allenamento avviato e non ancora terminato, se c'è.

    È ciò che trasforma "Inizia allenamento" in "Allenamento in corso" con il
    cronometro, anche dopo aver chiuso il pannello o ricaricato la pagina.
    Solo quelli di oggi: uno dimenticato aperto ieri non resta in corso.
    """
    return db.scalar(
        select(WorkoutSession)
        .where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.date == (today or clock.today()),
            WorkoutSession.started_at.is_not(None),
            WorkoutSession.ended_at.is_(None),
        )
        .order_by(WorkoutSession.started_at.desc())
        .limit(1)
    )


def _summary_out(r: training_log.SessionSummary) -> SessionSummaryOut:
    return SessionSummaryOut(
        session=SessionOut.model_validate(r.session),
        duration_seconds=r.duration_seconds,
        sets_count=r.sets_count,
        exercises_count=r.exercises_count,
        volume_kg=r.volume_kg,
        records=[
            SessionRecordOut(
                exercise_id=x.exercise.id,
                exercise_name=x.exercise.name_it or x.exercise.name,
                weight_kg=x.weight_kg,
                previous_best_kg=x.previous_best_kg,
            )
            for x in r.records
        ],
    )


@router.post("/sessions/{session_id}/start", response_model=SessionOut)
def start_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> WorkoutSession:
    """Avvia (o riapre) un allenamento: riparte il cronometro se era chiuso."""
    sessione = _owned_session(db, session_id, user)
    if sessione.started_at is None:
        sessione.started_at = dt.datetime.now(dt.timezone.utc)
    sessione.ended_at = None
    db.commit()
    db.refresh(sessione)
    return sessione


@router.post("/sessions/{session_id}/finish", response_model=SessionSummaryOut)
def finish_session(
    session_id: int,
    payload: SessionFinishIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SessionSummaryOut:
    """Termina l'allenamento e restituisce il riepilogo: durata, serie,
    chili sollevati e i carichi mai raggiunti prima.

    Terminato senza rete, il telefono manda l'ora vera della fine: la durata
    non deve includere il tempo passato ad aspettare la connessione."""
    sessione = _owned_session(db, session_id, user)
    adesso = _client_time(payload.ended_at if payload else None, not_before=sessione.started_at)
    if sessione.started_at is None:
        sessione.started_at = adesso
    sessione.ended_at = adesso
    db.commit()
    db.refresh(sessione)
    translation.ensure_translated(db, list({s.exercise for s in sessione.sets if s.exercise}))
    # Promemoria degli integratori subito, non al giro d'ora successivo: è
    # adesso che si prepara lo shaker. Se l'invio fallisce, l'allenamento
    # resta comunque chiuso.
    try:
        push_notifications.after_session(db, sessione.profile)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("Promemoria post-allenamento non inviato", exc_info=True)
    return _summary_out(training_log.summarize_session(db, sessione))


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WorkoutSession:
    sessione = _owned_session(db, session_id, user)
    for campo, valore in payload.model_dump(exclude_unset=True).items():
        if campo == "date" and valore is None:
            continue
        setattr(sessione, campo, valore)
    db.commit()
    db.refresh(sessione)
    return sessione


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
def delete_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    sessione = _owned_session(db, session_id, user)
    db.delete(sessione)
    db.commit()


@router.post("/sessions/{session_id}/sets", response_model=SessionSetOut, status_code=201)
def add_set(
    session_id: int,
    payload: SessionSetIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SessionSet:
    """Una serie appena eseguita: si salva subito, non a fine allenamento,
    così niente va perso se il telefono si blocca a metà."""
    sessione = _owned_session(db, session_id, user)
    # Già arrivata (inviata di nuovo dopo una risposta persa): la stessa serie.
    if payload.client_id:
        esistente = db.scalar(select(SessionSet).where(SessionSet.client_id == payload.client_id))
        if esistente is not None:
            if esistente.workout_session_id != sessione.id:
                raise HTTPException(status_code=409, detail="Identificativo già usato")
            return esistente
    if db.get(Exercise, payload.exercise_id) is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    serie = SessionSet(workout_session_id=sessione.id, **payload.model_dump())
    db.add(serie)
    db.commit()
    db.refresh(serie)
    return serie


@router.patch("/sets/{set_id}", response_model=SessionSetOut)
def update_set(
    set_id: int,
    payload: SessionSetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SessionSet:
    """Corregge una serie, anche settimane dopo: cambia solo quella serie,
    lo storico delle altre sessioni resta com'è."""
    serie = _owned_set(db, set_id, user)
    for campo, valore in payload.model_dump(exclude_unset=True).items():
        if campo in ("reps", "weight_kg") and valore is None:
            continue
        setattr(serie, campo, valore)
    db.commit()
    db.refresh(serie)
    return serie


@router.delete("/sets/{set_id}", status_code=204, response_model=None)
def delete_set(
    set_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    serie = _owned_set(db, set_id, user)
    db.delete(serie)
    db.commit()


def _history_out(voce: training_log.SessionEntry) -> ExerciseSessionOut:
    return ExerciseSessionOut(
        session_id=voce.session.id,
        date=voce.session.date,
        day_label=voce.session.day_label,
        sets=[SessionSetOut.model_validate(s) for s in voce.sets],
        top_weight_kg=voce.top_weight_kg,
        best_e1rm=voce.best_e1rm,
        volume_kg=voce.volume_kg,
    )


@router.post("/exercises/{exercise_id}/manual-sets", response_model=ExerciseHistoryOut, status_code=201)
def add_manual_sets(
    exercise_id: int,
    payload: ManualSetsIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> ExerciseHistoryOut:
    """Carichi segnati fuori dall'allenamento. Restituisce lo storico aggiornato."""
    esercizio = db.get(Exercise, exercise_id)
    if esercizio is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    # Il telefono manda la sua data: un giorno di margine per i fusi orari.
    if payload.date > clock.today() + dt.timedelta(days=1):
        raise HTTPException(status_code=422, detail="Non si possono segnare carichi per un giorno futuro.")
    piano = _plan_for(db, profile.id, payload.workout_plan_id) if payload.workout_plan_id else None
    training_log.add_manual_sets(
        db,
        profile.id,
        esercizio,
        date=payload.date,
        sets=[(s.weight_kg, s.reps, s.rir) for s in payload.sets],
        plan_id=piano.id if piano else None,
        day_label=payload.day_label,
    )
    return exercise_history(exercise_id=exercise_id, weeks=None, db=db, profile=profile)


@router.get("/exercises/{exercise_id}/history", response_model=ExerciseHistoryOut)
def exercise_history(
    exercise_id: int,
    weeks: int | None = Query(default=None, ge=1, le=260),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> ExerciseHistoryOut:
    """Tutte le sessioni di un esercizio, dalla più recente: la base del
    grafico dei carichi e dello storico modificabile."""
    esercizio = db.get(Exercise, exercise_id)
    if esercizio is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    translation.ensure_translated(db, [esercizio])
    dal = clock.today() - dt.timedelta(weeks=weeks) if weeks else None
    storia = training_log.exercise_history(db, profile.id, exercise_id, since=dal)
    return ExerciseHistoryOut(
        exercise_id=esercizio.id,
        exercise_name=esercizio.name_it or esercizio.name,
        sessions=[_history_out(v) for v in storia],
    )


@router.get("/last-performance", response_model=dict[int, ExerciseSessionOut])
def last_performance(
    exercise_ids: list[int] = Query(default=[], max_length=40),
    exclude_session_id: int | None = None,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> dict[int, ExerciseSessionOut]:
    """L'ultima volta di ciascun esercizio: il riferimento durante la sessione."""
    ultime = training_log.last_performance(
        db, profile.id, exercise_ids, exclude_session_id=exclude_session_id
    )
    return {k: _history_out(v) for k, v in ultime.items()}


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    limit: int = 50,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[WorkoutSession]:
    return list(
        db.scalars(
            select(WorkoutSession)
            .where(WorkoutSession.profile_id == profile.id)
            .order_by(WorkoutSession.date.desc())
            .limit(limit)
        )
    )


@router.post("/feedback", response_model=VolumeRecommendationOut, status_code=201)
def submit_feedback(
    payload: FeedbackIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> VolumeRecommendationOut:
    """Registra come sta rispondendo l'utente e restituisce la raccomandazione.

    È qui che «non vedo progressi e i DOMS durano troppo» diventa una
    riduzione del volume, invece dell'istinto opposto di allenarsi di più.
    Con `apply_to_plan=true` la modifica viene applicata alla scheda indicata
    in `plan_id`, oppure alla più recente.
    """
    piano = _plan_for(db, profile.id, payload.plan_id)

    feedback = TrainingFeedback(
        profile_id=profile.id,
        workout_plan_id=piano.id if piano else None,
        date=clock.today(),
        progress_perception=payload.progress_perception,
        recovery_quality=payload.recovery_quality,
        doms_duration_hours=payload.doms_duration_hours,
        affects_performance=payload.affects_performance,
        sleep_quality=payload.sleep_quality,
        note=payload.note,
    )
    db.add(feedback)
    db.commit()

    raccomandazione = autoregulation.evaluate_feedback(db, profile, feedback, plan=piano)

    applicata = False
    if payload.apply_to_plan and piano is not None and raccomandazione.changes_volume:
        autoregulation.apply_volume_change(db, piano, raccomandazione)
        applicata = True

    autoregulation.record_recommendation(db, profile, raccomandazione, plan=piano)

    return VolumeRecommendationOut(
        adjustment=raccomandazione.adjustment,
        current_weekly_sets=raccomandazione.current_weekly_sets,
        suggested_weekly_sets=raccomandazione.suggested_weekly_sets,
        reason=raccomandazione.reason,
        caveats=raccomandazione.caveats,
        knowledge_tags=raccomandazione.knowledge_tags,
        applied=applicata,
    )


@router.get("/exercises/{exercise_id}", response_model=ExerciseOut)
def read_exercise(exercise_id: int, db: Session = Depends(get_db)) -> ExerciseOut:
    """Dettaglio di un esercizio, per l'overlay con l'esecuzione.

    Include la biomeccanica (articolazioni, piano, indicazioni di forma) e il
    suggerimento sul focus coerente con il muscolo principale.
    """
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    translation.ensure_translated(db, [exercise])
    risposta = ExerciseOut.model_validate(exercise)
    risposta.guidance = ExerciseGuidanceOut(**exercise_guidance.build(exercise).as_dict())
    return risposta


@router.get("/exercise-notes", response_model=dict[int, str])
def list_exercise_notes(
    exercise_ids: list[int] = Query(default=[], max_length=60),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> dict[int, str]:
    """Le note dell'utente per gli esercizi indicati (regolazioni, presa…)."""
    return exercise_notes.notes_for(db, profile.id, exercise_ids)


@router.put("/exercises/{exercise_id}/note", response_model=ExerciseNoteOut)
def save_exercise_note(
    exercise_id: int,
    payload: ExerciseNoteIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> ExerciseNoteOut:
    """Salva la nota dell'utente su un esercizio; un testo vuoto la toglie."""
    if db.get(Exercise, exercise_id) is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    testo = exercise_notes.set_note(db, profile.id, exercise_id, payload.text)
    return ExerciseNoteOut(exercise_id=exercise_id, text=testo)


@router.get("/exercises", response_model=list[ExerciseOut])
def list_exercises(
    muscle: str | None = None,
    q: str | None = None,
    limit: int = 40,
    db: Session = Depends(get_db),
) -> list[Exercise]:
    """Catalogo filtrabile: serve a scegliere l'esercizio preferito per un
    gruppo muscolare prima ancora di generare la scheda."""
    query = select(Exercise).where(
        Exercise.primary_muscle.is_not(None), exercise_library.catalog_condition(db)
    )
    if muscle:
        query = query.where(Exercise.primary_muscle == muscle)
    limit = max(1, min(limit, 200))
    query = query.order_by(*exercise_library.catalog_order())
    if not q:
        return list(db.scalars(query.limit(limit)))
    # Nome italiano e originale: "panca" e "bench" trovano lo stesso
    # esercizio, anche se non è ancora tradotto.
    query = query.where(exercise_library.search_condition(q, every_word=False))
    return exercise_library.rank_search(db.scalars(query), q)[:limit]


@router.get("/preferences", response_model=list[PreferenceOut])
def list_preferences(
    db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
) -> list[PreferenceOut]:
    righe = db.scalars(
        select(ExercisePreference).where(ExercisePreference.profile_id == profile.id)
    ).all()
    return [
        PreferenceOut(
            exercise_id=p.exercise_id,
            is_preferred=p.is_preferred,
            exercise=ExerciseOut.model_validate(p.exercise),
        )
        for p in righe
    ]


@router.post("/preferences", response_model=PreferenceOut, status_code=201)
def set_preference(
    payload: PreferenceIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> PreferenceOut:
    """Segna un esercizio come preferito o da evitare.

    Le preferenze pesano già sulla **generazione** della scheda successiva,
    non solo sulla sostituzione a posteriori: se preferisci la chest press
    alla panca piana, la prossima scheda nasce così.
    """
    exercise = db.get(Exercise, payload.exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")

    preferenza = exercise_swap.set_preference(
        db, profile, exercise, preferred=payload.is_preferred
    )
    return PreferenceOut(
        exercise_id=preferenza.exercise_id,
        is_preferred=preferenza.is_preferred,
        exercise=ExerciseOut.model_validate(exercise),
    )


@router.delete("/preferences/{exercise_id}", status_code=204, response_model=None)
def clear_preference(
    exercise_id: int,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> None:
    preferenza = db.scalar(
        select(ExercisePreference).where(
            ExercisePreference.profile_id == profile.id,
            ExercisePreference.exercise_id == exercise_id,
        )
    )
    if preferenza is not None:
        db.delete(preferenza)
        db.commit()


@router.post("/chat/stream")
def chat_stream(
    payload: ChatIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
    user: User = Depends(current_user),
) -> StreamingResponse:
    """La stessa risposta di `/chat`, ma che arriva mentre viene scritta.

    Il formato è quello degli Server-Sent Events: una riga `data:` per
    evento, `delta` per ogni pezzo di testo e `done` alla fine con la
    risposta definitiva, le fonti e le azioni proposte. Se lo streaming non
    è disponibile, il client può sempre ricadere su `/chat`.
    """
    _limit(db, user, "chat")

    def eventi():
        for tipo, valore in chat_agent.answer_stream(
            db, profile, payload.message,
            history=[m.model_dump() for m in payload.history],
            context=payload.context,
        ):
            if tipo == "delta":
                corpo = {"type": "delta", "text": valore}
            else:
                corpo = {
                    "type": "done",
                    "answer": valore.answer,
                    "knowledge_tags": valore.knowledge_tags,
                    "used_llm": valore.used_llm,
                    "actions": valore.actions,
                }
            yield f"data: {json.dumps(corpo, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        eventi(),
        media_type="text/event-stream",
        # Senza questa intestazione alcuni proxy accumulano la risposta e la
        # consegnano tutta insieme, vanificando lo streaming.
        headers={
            # `no-transform` dice ai proxy di non comprimere: con gzip la
            # risposta verrebbe accumulata e consegnata tutta insieme, che è
            # esattamente quello che lo streaming deve evitare.
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=ChatOut)
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
    user: User = Depends(current_user),
) -> ChatOut:
    """Assistente conversazionale.

    Riceve i dati reali del profilo e i documenti pertinenti, e **non può
    modificare nulla**: le modifiche restano azioni esplicite dell'utente.
    """
    _limit(db, user, "chat")
    risposta = chat_agent.answer(
        db, profile, payload.message,
        history=[m.model_dump() for m in payload.history],
        context=payload.context,
    )
    return ChatOut(
        answer=risposta.answer,
        knowledge_tags=risposta.knowledge_tags,
        used_llm=risposta.used_llm,
        actions=[ChatActionOut(**a) for a in risposta.actions],
    )
