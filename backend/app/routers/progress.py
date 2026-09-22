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
    ConsistencyOut,
    ConsistencyWeekOut,
    ExerciseProgressOut,
    LoggedExerciseOut,
    MuscleVolumeOut,
    NutritionStatsOut,
    NutritionWeekOut,
    OneRmPointOut,
    OneRmTrendOut,
    ProgressReportOut,
    SyncResultOut,
    VolumeStatsOut,
    WeightPointOut,
    WeightTrendOut,
)
from app.services import (
    catalog_sync,
    exercise_library,
    progress_report,
    progress_stats,
    training_log,
    translation,
)

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


@router.get("/progress/loads", response_model=list[LoggedExerciseOut])
def logged_exercises(
    weeks: int = Query(default=12, ge=1, le=260),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[LoggedExerciseOut]:
    """Esercizi con carichi registrati nel periodo, i più frequenti prima:
    il selettore del grafico della progressione dei carichi."""
    dal = dt.date.today() - dt.timedelta(weeks=weeks)
    righe = training_log.logged_exercises(db, profile.id, since=dal)
    translation.ensure_translated(db, [r.exercise for r in righe])
    return [
        LoggedExerciseOut(
            exercise_id=r.exercise.id,
            exercise_name=r.exercise.name_it or r.exercise.name,
            sessions=r.sessions,
            last_date=r.last_date,
        )
        for r in righe
    ]


@router.get("/progress/volume", response_model=VolumeStatsOut)
def volume_stats(
    weeks: int = Query(default=8, ge=1, le=52),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> VolumeStatsOut:
    """Serie settimanali per gruppo muscolare, confrontate con il range delle
    fonti per il livello dell'utente (`training_volume.md`).

    Il confronto è sulla media del periodo: una singola settimana può essere
    di scarico o saltata per un'influenza, e non dice se il volume abituale
    sia adeguato.
    """
    stats = progress_stats.volume_by_muscle(db, profile, weeks=weeks)
    return VolumeStatsOut(
        weeks=stats.weeks,
        muscles=[
            MuscleVolumeOut(
                muscle=m.muscle,
                sets_per_week=m.sets_per_week,
                average=round(m.average, 1),
                last=m.last,
                range_min=m.range_min,
                range_max=m.range_max,
                status=m.status,
            )
            for m in stats.muscles
        ],
    )


@router.get("/progress/one-rm/{exercise_id}", response_model=OneRmTrendOut)
def one_rm_stats(
    exercise_id: int,
    weeks: int = Query(default=26, ge=1, le=260),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> OneRmTrendOut:
    """Andamento del massimale stimato di un esercizio, una riga per sessione.

    Un esercizio mai registrato da questo profilo risponde 404 e non una
    risposta vuota: come per i profili altrui, non si distingue fra "non
    esiste" e "non è tuo"."""
    trend = progress_stats.one_rm_trend(db, profile, exercise_id, weeks=weeks)
    if trend is None:
        raise HTTPException(status_code=404, detail="Nessuna serie registrata per questo esercizio")

    return OneRmTrendOut(
        exercise_id=trend.exercise_id,
        exercise_name=trend.exercise_name,
        points=[
            OneRmPointOut(date=p.date, one_rm=p.one_rm, kg=p.kg, reps=p.reps)
            for p in trend.points
        ],
        delta_pct=round(trend.delta_pct, 3),
        high_rep_estimate=trend.high_rep_estimate,
    )


@router.get("/progress/consistency", response_model=ConsistencyOut)
def consistency_stats(
    weeks: int = Query(default=12, ge=1, le=104),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> ConsistencyOut:
    """Allenamenti svolti rispetto a quelli previsti dalle schede attive."""
    stats = progress_stats.consistency(db, profile, weeks=weeks)
    return ConsistencyOut(
        weeks=[
            ConsistencyWeekOut(start=s.start, done=s.done, planned=s.planned)
            for s in stats.weeks
        ],
        streak_weeks=stats.streak_weeks,
        best_streak_weeks=stats.best_streak_weeks,
        done_total=stats.done_total,
        planned_total=stats.planned_total,
    )


@router.get("/progress/weight-trend", response_model=WeightTrendOut)
def weight_trend_stats(
    weeks: int = Query(default=12, ge=1, le=104),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> WeightTrendOut:
    """Peso corporeo a media mobile di 7 giorni e ritmo settimanale."""
    stats = progress_stats.weight_trend(db, profile, weeks=weeks)
    return WeightTrendOut(
        points=[
            WeightPointOut(date=p.date, weight_kg=p.weight_kg, average_kg=p.average_kg)
            for p in stats.points
        ],
        weekly_rate_kg=stats.weekly_rate_kg,
        expected_min=stats.expected_min,
        expected_max=stats.expected_max,
        verdict=stats.verdict,
        note=stats.note,
    )


@router.get("/progress/nutrition", response_model=NutritionStatsOut)
def nutrition_stats(
    weeks: int = Query(default=8, ge=1, le=52),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> NutritionStatsOut:
    """Medie settimanali del diario rispetto ai target della giornata."""
    stats = progress_stats.nutrition_weeks(db, profile, weeks=weeks)
    return NutritionStatsOut(
        weeks=[
            NutritionWeekOut(
                start=s.start,
                kcal_avg=s.kcal_avg,
                protein_avg_g=s.protein_avg_g,
                days_logged=s.days_logged,
                days_in_kcal_target=s.days_in_kcal_target,
                days_in_protein_target=s.days_in_protein_target,
            )
            for s in stats.weeks
        ],
        kcal_target=stats.kcal_target,
        protein_target_g=stats.protein_target_g,
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
