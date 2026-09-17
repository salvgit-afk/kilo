"""Report di progressione e stato del catalogo."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Exercise, Ingredient, UserProfile
from app.routers.auth import current_user, require_admin
from app.routers.profile import owned_profile
from app.schemas import (
    CatalogStatusOut,
    ExerciseProgressOut,
    ProgressReportOut,
    SyncResultOut,
)
from app.services import catalog_sync, exercise_library, progress_report, translation

router = APIRouter(tags=["progressione"], dependencies=[Depends(current_user)])


@router.get("/progress/report", response_model=ProgressReportOut)
def read_report(
    weeks: int = Query(default=12, ge=1, le=104),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> ProgressReportOut:
    """Report del periodo richiesto.

    Il peso corporeo è confrontato a medie mobili e non a pesate singole: le
    oscillazioni giornaliere di 1-2 kg da acqua e glicogeno renderebbero il
    confronto fra due misurazioni soprattutto rumore. Quando le pesate sono
    troppo poche, la risposta lo dichiara in `weight_smoothed`.
    """
    fine = dt.date.today()
    report = progress_report.build_report(
        db, profile, since=fine - dt.timedelta(weeks=weeks), until=fine
    )

    return ProgressReportOut(
        period_start=report.period_start,
        period_end=report.period_end,
        weeks=round(report.weeks, 1),
        too_early=report.too_early,
        weight_first_average=(
            round(report.weight.first_average, 1)
            if report.weight.first_average is not None
            else None
        ),
        weight_last_average=(
            round(report.weight.last_average, 1)
            if report.weight.last_average is not None
            else None
        ),
        weight_delta_kg=(
            round(report.weight.delta_kg, 1)
            if report.weight.delta_kg is not None
            else None
        ),
        weight_weekly_rate_kg=(
            round(report.weight.weekly_rate_kg, 2)
            if report.weight.weekly_rate_kg is not None
            else None
        ),
        weight_measurements=report.weight.measurements,
        weight_smoothed=report.weight.smoothed,
        sessions_done=report.adherence.sessions_done,
        sessions_per_week=round(report.adherence.actual_per_week, 1),
        planned_per_week=report.adherence.planned_per_week,
        exercises=[
            ExerciseProgressOut(
                exercise_name=e.exercise_name,
                first_best_set=e.first_best_set,
                last_best_set=e.last_best_set,
                first_best_1rm=round(e.first_best_1rm, 1),
                last_best_1rm=round(e.last_best_1rm, 1),
                delta_kg=round(e.delta_kg, 1),
                delta_pct=round(e.delta_pct, 3),
                sessions=e.sessions,
                high_rep_estimate=e.high_rep_estimate,
            )
            for e in report.exercises
        ],
        notes=report.notes,
        plateau_advice=progress_report.explain_plateau(db, profile, report),
    )


@router.get("/catalog/status", response_model=CatalogStatusOut)
def catalog_status(db: Session = Depends(get_db)) -> CatalogStatusOut:
    muscoli = db.scalars(
        select(Exercise.primary_muscle)
        .where(Exercise.primary_muscle.is_not(None))
        .distinct()
        .order_by(Exercise.primary_muscle)
    ).all()

    return CatalogStatusOut(
        # Solo il catalogo visibile: i doppioni restano nel database ma non
        # sono esercizi in più fra cui scegliere.
        exercises_cached=db.scalar(
            select(func.count()).select_from(Exercise).where(exercise_library.catalog_condition(db))
        ) or 0,
        ingredients_cached=db.scalar(select(func.count()).select_from(Ingredient)) or 0,
        muscles=list(muscoli),
    )


@router.post(
    "/catalog/sync-exercises",
    response_model=SyncResultOut,
    # Scarica le fonti e avvia centinaia di chiamate all'LLM: solo chi è in
    # ADMIN_EMAILS può lanciarla.
    dependencies=[Depends(require_admin)],
)
def sync_exercises(
    background: BackgroundTasks, include_wger: bool = False, db: Session = Depends(get_db)
) -> SyncResultOut:
    """Importa il catalogo esercizi: Everkinetic, RepDB, free-exercise-db e
    gli esercizi scritti a mano, senza doppioni.

    La traduzione in italiano parte in background: richiede molte chiamate
    all'LLM e non ha senso far aspettare la risposta. Gli esercizi non ancora
    tradotti mostrano intanto il nome originale.
    """
    try:
        risultato = exercise_library.sync_catalog(db)
    except exercise_library.LibraryError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    if include_wger:
        catalog_sync.sync_exercises(db)
    background.add_task(translation.translate_library)
    return SyncResultOut(**vars(risultato))
