"""Test dell'autoregolazione del volume e della sostituzione esercizi.

La matrice decisionale viene da `doms_and_autoregulation.md`. Un errore di
segno qui sarebbe grave e silenzioso: consiglierebbe di **aumentare** il
volume proprio a chi è già in deficit di recupero, cioè l'esatto contrario
di quello che serve.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models import (
    ActivityLevel,
    AgentRecommendationLog,
    Exercise,
    ExercisePreference,
    ExperienceLevel,
    Goal,
    ProgressPerception,
    RecommendationType,
    RecoveryQuality,
    Sex,
    TrainingFeedback,
    UserProfile,
    VolumeAdjustment,
    WorkoutPlanExercise,
)
from app.services import autoregulation as ar
from app.services import exercise_swap as sw
from app.services import workout_generator as wg


@pytest.fixture
def scenario(db):
    """Profilo intermedio con una scheda attiva da 8 settimane."""
    for muscle in set(
        wg.PUSH_MUSCLES + wg.PULL_MUSCLES + wg.LEG_MUSCLES + wg.CORE_MUSCLES + wg.FULL_BODY_MUSCLES
    ):
        db.add_all(
            [
                Exercise(
                    wger_id=abs(hash((muscle, i))) % 100000,
                    name=f"{muscle} {tipo}",
                    primary_muscle=muscle,
                    equipment="Barbell",
                    is_compound=tipo.startswith("compound"),
                )
                for i, tipo in enumerate(("compound", "compound2", "isolation", "isolation2"))
            ]
        )
    profilo = UserProfile(
        display_name="test",
        birth_date=dt.date(1995, 1, 1),
        sex=Sex.MALE,
        height_cm=178.0,
        weight_kg=76.0,
        goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
        training_days_per_week=4,
    )
    db.add(profilo)
    db.commit()

    plan = wg.persist_plan(
        db,
        profilo,
        wg.generate_plan(db, profilo),
        started_at=dt.date.today() - dt.timedelta(weeks=8),
    )
    return db, profilo, plan


def _feedback(profilo, plan, **overrides) -> TrainingFeedback:
    defaults = dict(
        profile_id=profilo.id,
        workout_plan_id=plan.id,
        date=dt.date.today(),
        progress_perception=ProgressPerception.GOOD,
        recovery_quality=RecoveryQuality.GOOD,
        doms_duration_hours=24,
        affects_performance=False,
    )
    defaults.update(overrides)
    return TrainingFeedback(**defaults)


# --- Matrice decisionale ----------------------------------------------------


def test_nessun_progresso_con_doms_prolungato_riduce_il_volume(scenario):
    """Lo scenario centrale: il collo di bottiglia è il recupero, non lo
    stimolo. Aumentare il volume qui peggiorerebbe il problema."""
    db, profilo, plan = scenario
    feedback = _feedback(
        profilo,
        plan,
        progress_perception=ProgressPerception.NONE,
        recovery_quality=RecoveryQuality.POOR,
        doms_duration_hours=96,
        affects_performance=True,
    )

    rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)

    assert rec.adjustment == VolumeAdjustment.DECREASE
    assert rec.suggested_weekly_sets < rec.current_weekly_sets


def test_nessun_progresso_con_buon_recupero_aumenta_il_volume(scenario):
    """Stesso «non vedo progressi», conclusione opposta: senza segnali di
    recupero insufficiente c'è margine per aumentare lo stimolo."""
    db, profilo, plan = scenario
    feedback = _feedback(profilo, plan, progress_perception=ProgressPerception.NONE)

    rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)

    assert rec.adjustment == VolumeAdjustment.INCREASE
    assert rec.suggested_weekly_sets > rec.current_weekly_sets


def test_progressi_con_recupero_al_limite_mantiene(scenario):
    db, profilo, plan = scenario
    feedback = _feedback(
        profilo, plan, progress_perception=ProgressPerception.GOOD,
        recovery_quality=RecoveryQuality.POOR,
    )

    rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)
    assert rec.adjustment == VolumeAdjustment.MAINTAIN


def test_tutto_bene_non_cambia_nulla(scenario):
    db, profilo, plan = scenario
    rec = ar.evaluate_feedback(db, profilo, _feedback(profilo, plan), plan=plan)

    assert rec.adjustment == VolumeAdjustment.MAINTAIN
    assert rec.suggested_weekly_sets == rec.current_weekly_sets


@pytest.mark.parametrize(
    "campo,valore",
    [
        ("recovery_quality", RecoveryQuality.POOR),
        ("doms_duration_hours", 96),
        ("affects_performance", True),
    ],
)
def test_ogni_segnale_di_recupero_insufficiente_basta_da_solo(scenario, campo, valore):
    """I tre segnali sono alternativi, non cumulativi: chi riferisce che i
    dolori gli rovinano le sessioni non deve anche dichiarare il recupero
    scarso perché venga ascoltato."""
    db, profilo, plan = scenario
    feedback = _feedback(
        profilo, plan, progress_perception=ProgressPerception.NONE, **{campo: valore}
    )

    rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)
    assert rec.adjustment == VolumeAdjustment.DECREASE


# --- Limiti e prudenza -------------------------------------------------------


def test_volume_non_scende_sotto_il_minimo_del_livello(scenario):
    """Il range di `training_volume.md` resta il vincolo: sotto il minimo non
    si va, si guarda altrove (alimentazione, sonno)."""
    db, profilo, plan = scenario
    minimo, _ = wg.WEEKLY_SETS_BY_EXPERIENCE[ExperienceLevel.INTERMEDIATE]

    for _ in range(5):
        feedback = _feedback(
            profilo, plan,
            progress_perception=ProgressPerception.NONE,
            recovery_quality=RecoveryQuality.POOR,
        )
        rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)
        ar.apply_volume_change(db, plan, rec)
        assert rec.suggested_weekly_sets >= minimo


def test_volume_non_supera_il_massimo_del_livello(scenario):
    db, profilo, plan = scenario
    _, massimo = wg.WEEKLY_SETS_BY_EXPERIENCE[ExperienceLevel.INTERMEDIATE]

    for _ in range(5):
        feedback = _feedback(profilo, plan, progress_perception=ProgressPerception.NONE)
        rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)
        ar.apply_volume_change(db, plan, rec)
        assert rec.suggested_weekly_sets <= massimo


def test_al_massimo_del_range_suggerisce_di_guardare_altrove(scenario):
    """Arrivati al tetto, continuare ad aggiungere serie non è la risposta."""
    db, profilo, plan = scenario
    for _ in range(6):
        feedback = _feedback(profilo, plan, progress_perception=ProgressPerception.NONE)
        rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)
        ar.apply_volume_change(db, plan, rec)

    assert rec.adjustment == VolumeAdjustment.MAINTAIN
    assert any("alimentazione" in c.lower() or "proteico" in c.lower() for c in rec.caveats)


def test_scheda_troppo_recente_produce_un_avviso_di_prudenza(scenario):
    """Sotto le 4-6 settimane è presto per concludere che non funzioni."""
    db, profilo, plan = scenario
    plan.started_at = dt.date.today() - dt.timedelta(weeks=1)
    db.commit()

    rec = ar.evaluate_feedback(
        db, profilo, _feedback(profilo, plan, progress_perception=ProgressPerception.NONE), plan=plan
    )
    assert any("settimane" in c for c in rec.caveats)


def test_ricorda_che_il_volume_non_e_lunica_causa(scenario):
    db, profilo, plan = scenario
    rec = ar.evaluate_feedback(
        db, profilo, _feedback(profilo, plan, progress_perception=ProgressPerception.NONE), plan=plan
    )
    assert any("proteine" in c.lower() or "calorie" in c.lower() for c in rec.caveats)


def test_modifica_applicata_alle_righe_della_scheda(scenario):
    db, profilo, plan = scenario
    prima = {r.id: r.target_sets for r in db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    )}

    feedback = _feedback(
        profilo, plan,
        progress_perception=ProgressPerception.NONE,
        recovery_quality=RecoveryQuality.POOR,
    )
    rec = ar.evaluate_feedback(db, profilo, feedback, plan=plan)
    modificate = ar.apply_volume_change(db, plan, rec)

    dopo = {r.id: r.target_sets for r in db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    )}
    assert modificate > 0
    assert all(dopo[i] <= prima[i] for i in prima)
    assert all(v >= 1 for v in dopo.values()), "nessuna riga deve scendere a zero serie"


def test_decisione_tracciata_con_le_fonti(scenario):
    db, profilo, plan = scenario
    rec = ar.evaluate_feedback(db, profilo, _feedback(profilo, plan), plan=plan)
    log = ar.record_recommendation(db, profilo, rec, plan=plan)

    assert log.recommendation_type == RecommendationType.VOLUME_ADJUSTED
    assert "doms" in log.knowledge_source_tags


# --- Sostituzione degli esercizi ---------------------------------------------


def test_alternative_stesso_gruppo_muscolare(scenario):
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()

    alternative = sw.find_alternatives(db, profilo, riga.exercise)

    assert alternative
    assert all(
        a.exercise.primary_muscle == riga.exercise.primary_muscle for a in alternative
    )
    assert all(a.exercise.id != riga.exercise.id for a in alternative)


def test_alternative_preferiscono_la_stessa_tipologia(scenario):
    """Mantenere multi-articolare o isolamento preserva anche il recupero
    assegnato dalla scheda."""
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()

    alternative = sw.find_alternatives(db, profilo, riga.exercise)
    assert alternative[0].preserves_stimulus


def test_esercizi_sgraditi_non_vengono_riproposti(scenario):
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()

    scartato = sw.find_alternatives(db, profilo, riga.exercise)[0].exercise
    sw.set_preference(db, profilo, scartato, preferred=False)

    ancora = sw.find_alternatives(db, profilo, riga.exercise)
    assert scartato.id not in [a.exercise.id for a in ancora]


def test_esercizi_graditi_proposti_per_primi(scenario):
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()

    alternative = sw.find_alternatives(db, profilo, riga.exercise)
    gradito = alternative[-1].exercise
    sw.set_preference(db, profilo, gradito, preferred=True)

    assert sw.find_alternatives(db, profilo, riga.exercise)[0].exercise.id == gradito.id


def test_sostituzione_mantiene_serie_ripetizioni_e_rir(scenario):
    """Cambiare esercizio non deve cambiare il volume programmato: serie e
    ripetizioni dipendono dal piano, non dal singolo movimento."""
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()
    prima = (riga.target_sets, riga.target_reps_min, riga.target_reps_max, riga.target_rir)

    sostituto = sw.find_alternatives(db, profilo, riga.exercise)[0].exercise
    sw.swap_in_plan(db, profilo, riga, sostituto)

    assert riga.exercise_id == sostituto.id
    assert (riga.target_sets, riga.target_reps_min, riga.target_reps_max, riga.target_rir) == prima


def test_sostituzione_con_muscolo_diverso_rifiutata(scenario):
    """Sostituire con un esercizio per un altro gruppo cambierebbe lo stimolo
    previsto: va impedito, non corretto in silenzio."""
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()

    altro_muscolo = db.scalars(
        select(Exercise).where(Exercise.primary_muscle != riga.exercise.primary_muscle)
    ).first()

    with pytest.raises(sw.SwapError):
        sw.swap_in_plan(db, profilo, riga, altro_muscolo)


def test_sostituzione_registra_la_preferenza_e_il_log(scenario):
    db, profilo, plan = scenario
    riga = db.scalars(
        select(WorkoutPlanExercise).where(WorkoutPlanExercise.workout_plan_id == plan.id)
    ).first()
    vecchio_id = riga.exercise_id

    sostituto = sw.find_alternatives(db, profilo, riga.exercise)[0].exercise
    sw.swap_in_plan(db, profilo, riga, sostituto, mark_old_as_disliked=True)

    preferenze = {
        p.exercise_id: p.is_preferred
        for p in db.scalars(select(ExercisePreference))
    }
    assert preferenze[vecchio_id] is False
    assert preferenze[sostituto.id] is True

    log = db.scalars(
        select(AgentRecommendationLog).where(
            AgentRecommendationLog.recommendation_type == RecommendationType.EXERCISE_SWAPPED
        )
    ).one()
    assert "scelta_esercizi" in log.knowledge_source_tags
