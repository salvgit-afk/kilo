"""Schede di allenamento, sessioni svolte, alternative e autoregolazione."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
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
from app.routers.profile import owned_profile
from app.schemas import (
    AlternativeOut,
    ChatActionOut,
    ChatIn,
    ChatOut,
    ExerciseOut,
    PreferenceIn,
    PreferenceOut,
    FeedbackIn,
    PlanGenerationOut,
    SessionIn,
    SessionOut,
    SwapIn,
    VolumeRecommendationOut,
    WorkoutPlanOut,
)
from app.services import (
    autoregulation,
    chat_agent,
    exercise_library,
    exercise_swap,
    rate_limit,
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
    """La scheda attiva più recente (possono essercene più d'una)."""
    return db.scalar(
        select(WorkoutPlan)
        .where(WorkoutPlan.profile_id == profile_id, WorkoutPlan.is_active.is_(True))
        .order_by(WorkoutPlan.started_at.desc(), WorkoutPlan.id.desc())
        .limit(1)
    )


def _plan_for(db: Session, profile_id: int, plan_id: int | None) -> WorkoutPlan | None:
    """La scheda indicata, se è del profilo; senza indicazione la più recente."""
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
    translation.ensure_translated(db, [riga.exercise for riga in plan.exercises])

    return PlanGenerationOut(
        plan=WorkoutPlanOut.model_validate(plan),
        weekly_sets_per_muscle=generated.weekly_sets_per_muscle,
        warnings=generated.warnings,
        knowledge_tags=generated.knowledge_tags,
    )


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
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[AlternativeOut]:
    """Alternative per lo stesso gruppo muscolare, filtrabili per nome.

    Serve all'aderenza: un esercizio scelto e gradito viene eseguito, uno
    imposto e noioso viene saltato.
    """
    limit = max(1, min(limit, 40))
    riga = _plan_row(db, profile, plan_exercise_id)

    try:
        alternative = exercise_swap.find_alternatives(
            db, profile, riga.exercise, limit=limit, q=q
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
    piano = _active_plan(db, profile.id)

    sessione = WorkoutSession(
        profile_id=profile.id,
        workout_plan_id=piano.id if piano else None,
        date=payload.date or dt.date.today(),
        day_label=payload.day_label,
        perceived_fatigue=payload.perceived_fatigue,
        note=payload.note,
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
        date=dt.date.today(),
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
def read_exercise(exercise_id: int, db: Session = Depends(get_db)) -> Exercise:
    """Dettaglio di un esercizio, per l'overlay con l'esecuzione."""
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Esercizio non trovato")
    translation.ensure_translated(db, [exercise])
    return exercise


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
    if q:
        # Si cerca sia nel nome italiano sia nell'originale: "panca" e
        # "bench" devono trovare lo stesso esercizio.
        termine = f"%{q.strip()}%"
        query = query.where(or_(Exercise.name_it.ilike(termine), Exercise.name.ilike(termine)))
    query = query.order_by(*exercise_library.catalog_order()).limit(max(1, min(limit, 100)))
    return list(db.scalars(query))


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
