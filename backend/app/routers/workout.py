"""Schede di allenamento, sessioni svolte, alternative e autoregolazione."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Exercise,
    ExercisePreference,
    ScreeningRecord,
    SessionSet,
    TrainingFeedback,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
)
from app.routers.profile import get_profile
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
    translation,
    workout_generator,
)

router = APIRouter(prefix="/workout", tags=["allenamento"])


def _latest_screening(db: Session, profile_id: int) -> ScreeningRecord | None:
    return db.scalar(
        select(ScreeningRecord)
        .where(ScreeningRecord.profile_id == profile_id)
        .order_by(ScreeningRecord.created_at.desc())
    )


def _active_plan(db: Session, profile_id: int) -> WorkoutPlan | None:
    return db.scalar(
        select(WorkoutPlan).where(
            WorkoutPlan.profile_id == profile_id, WorkoutPlan.is_active.is_(True)
        )
    )


@router.post("/plans/generate", response_model=PlanGenerationOut, status_code=201)
def generate_plan(
    profile_id: int,
    explain: bool = True,
    split_type: str | None = None,
    db: Session = Depends(get_db),
) -> PlanGenerationOut:
    """Genera una scheda e la rende attiva.

    I parametri (serie, ripetizioni, RIR, recuperi) sono calcolati dai file
    della knowledge base. Con `explain=true` la motivazione viene riscritta
    in linguaggio naturale dall'LLM, che però non può modificare alcun
    numero: se non è disponibile resta la spiegazione deterministica.
    """
    profile = get_profile(profile_id, db)
    screening = _latest_screening(db, profile.id)

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

    used_llm = False
    if explain:
        spiegazione = workout_generator.explain_plan(generated, profile)
        used_llm = spiegazione != generated.rationale
        generated.rationale = spiegazione

    plan = workout_generator.persist_plan(db, profile, generated, used_llm=used_llm)
    translation.ensure_translated(db, [riga.exercise for riga in plan.exercises])

    return PlanGenerationOut(
        plan=WorkoutPlanOut.model_validate(plan),
        weekly_sets_per_muscle=generated.weekly_sets_per_muscle,
        warnings=generated.warnings,
        knowledge_tags=generated.knowledge_tags,
    )


@router.get("/plans/active", response_model=WorkoutPlanOut | None)
def read_active_plan(profile_id: int, db: Session = Depends(get_db)):
    get_profile(profile_id, db)
    return _active_plan(db, profile_id)


@router.get("/plans", response_model=list[WorkoutPlanOut])
def list_plans(profile_id: int, db: Session = Depends(get_db)) -> list[WorkoutPlan]:
    get_profile(profile_id, db)
    return list(
        db.scalars(
            select(WorkoutPlan)
            .where(WorkoutPlan.profile_id == profile_id)
            .order_by(WorkoutPlan.started_at.desc())
        )
    )


@router.get(
    "/plan-exercises/{plan_exercise_id}/alternatives",
    response_model=list[AlternativeOut],
)
def list_alternatives(
    plan_exercise_id: int, profile_id: int, limit: int = 6, db: Session = Depends(get_db)
) -> list[AlternativeOut]:
    """Alternative per lo stesso gruppo muscolare.

    Serve all'aderenza: un esercizio scelto e gradito viene eseguito, uno
    imposto e noioso viene saltato.
    """
    profile = get_profile(profile_id, db)
    riga = db.get(WorkoutPlanExercise, plan_exercise_id)
    if riga is None:
        raise HTTPException(status_code=404, detail="Esercizio non presente in scheda")

    try:
        alternative = exercise_swap.find_alternatives(
            db, profile, riga.exercise, limit=limit
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
    profile_id: int,
    payload: SwapIn,
    db: Session = Depends(get_db),
) -> WorkoutPlan:
    profile = get_profile(profile_id, db)
    riga = db.get(WorkoutPlanExercise, plan_exercise_id)
    if riga is None:
        raise HTTPException(status_code=404, detail="Esercizio non presente in scheda")

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
    profile_id: int, payload: SessionIn, db: Session = Depends(get_db)
) -> WorkoutSession:
    """Registra una sessione svolta con le serie effettive.

    Sono questi i dati su cui si basano i report di progressione, e non
    dipendono da nessuna API esterna.
    """
    profile = get_profile(profile_id, db)
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
    profile_id: int, limit: int = 50, db: Session = Depends(get_db)
) -> list[WorkoutSession]:
    get_profile(profile_id, db)
    return list(
        db.scalars(
            select(WorkoutSession)
            .where(WorkoutSession.profile_id == profile_id)
            .order_by(WorkoutSession.date.desc())
            .limit(limit)
        )
    )


@router.post("/feedback", response_model=VolumeRecommendationOut, status_code=201)
def submit_feedback(
    profile_id: int, payload: FeedbackIn, db: Session = Depends(get_db)
) -> VolumeRecommendationOut:
    """Registra come sta rispondendo l'utente e restituisce la raccomandazione.

    È qui che «non vedo progressi e i DOMS durano troppo» diventa una
    riduzione del volume, invece dell'istinto opposto di allenarsi di più.
    Con `apply_to_plan=true` la modifica viene applicata alla scheda attiva.
    """
    profile = get_profile(profile_id, db)
    piano = _active_plan(db, profile.id)

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
    query = query.order_by(*exercise_library.catalog_order()).limit(limit)
    return list(db.scalars(query))


@router.get("/preferences", response_model=list[PreferenceOut])
def list_preferences(profile_id: int, db: Session = Depends(get_db)) -> list[PreferenceOut]:
    profile = get_profile(profile_id, db)
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
    profile_id: int, payload: PreferenceIn, db: Session = Depends(get_db)
) -> PreferenceOut:
    """Segna un esercizio come preferito o da evitare.

    Le preferenze pesano già sulla **generazione** della scheda successiva,
    non solo sulla sostituzione a posteriori: se preferisci la chest press
    alla panca piana, la prossima scheda nasce così.
    """
    profile = get_profile(profile_id, db)
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
    profile_id: int, exercise_id: int, db: Session = Depends(get_db)
) -> None:
    profile = get_profile(profile_id, db)
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
    profile_id: int, payload: ChatIn, db: Session = Depends(get_db)
) -> ChatOut:
    """Assistente conversazionale.

    Riceve i dati reali del profilo e i documenti pertinenti, e **non può
    modificare nulla**: le modifiche restano azioni esplicite dell'utente.
    """
    profile = get_profile(profile_id, db)
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
