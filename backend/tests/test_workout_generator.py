"""Test del generatore di schede.

I valori attesi qui vengono dai file della knowledge base. Se un test
fallisce dopo una modifica, la domanda da porsi è se il piano generato
rispetti ancora i parametri delle fonti citate — non se "il numero è
cambiato".
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models import (
    ActivityLevel,
    AgentRecommendationLog,
    Exercise,
    ExperienceLevel,
    Goal,
    RecommendationType,
    ScreeningRecord,
    Sex,
    UserProfile,
    WorkoutPlan,
    WorkoutPlanExercise,
)
from app.services import workout_generator as wg

TUTTI_I_MUSCOLI = (
    wg.PUSH_MUSCLES + wg.PULL_MUSCLES + wg.LEG_MUSCLES + wg.CORE_MUSCLES
)


@pytest.fixture
def catalogo(db):
    """Catalogo minimo ma realistico: per ogni gruppo muscolare un esercizio
    multi-articolare con bilanciere, uno di isolamento con manubri e uno a
    corpo libero."""
    for muscle in set(TUTTI_I_MUSCOLI + wg.FULL_BODY_MUSCLES):
        db.add_all(
            [
                Exercise(
                    wger_id=hash((muscle, "c")) % 100000,
                    name=f"{muscle} compound",
                    primary_muscle=muscle,
                    secondary_muscles="Glutes",
                    equipment="Barbell, Bench",
                    is_compound=True,
                ),
                Exercise(
                    wger_id=hash((muscle, "i")) % 100000,
                    name=f"{muscle} isolation",
                    primary_muscle=muscle,
                    equipment="Dumbbell",
                    is_compound=False,
                ),
                Exercise(
                    wger_id=hash((muscle, "b")) % 100000,
                    name=f"{muscle} bodyweight",
                    primary_muscle=muscle,
                    equipment=wg.BODYWEIGHT,
                    is_compound=False,
                ),
            ]
        )
    db.commit()
    return db


def _profilo(**overrides) -> UserProfile:
    defaults = dict(
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
    defaults.update(overrides)
    return UserProfile(**defaults)


# --- Volume settimanale (training_volume.md) --------------------------------


@pytest.mark.parametrize("livello", list(wg.WEEKLY_SETS_BY_EXPERIENCE))
def test_volume_settimanale_dentro_il_range_della_fonte(catalogo, livello):
    """Il totale settimanale per gruppo muscolare deve cadere nel range
    indicato da `training_volume.md` per quel livello di esperienza."""
    profilo = _profilo(experience_level=livello)
    plan = wg.generate_plan(catalogo, profilo)

    minimo, massimo = wg.WEEKLY_SETS_BY_EXPERIENCE[livello]
    for muscolo, serie in plan.weekly_sets_per_muscle.items():
        assert minimo <= serie <= massimo, f"{muscolo}: {serie} fuori da {minimo}-{massimo}"


def test_volume_non_si_moltiplica_con_la_frequenza(catalogo):
    """Allenare un muscolo più volte a settimana deve *dividere* il volume
    fra le sessioni, non ripeterlo per intero: è l'errore che triplicherebbe
    il carico reale rispetto a quello prescritto."""
    tre = wg.generate_plan(catalogo, _profilo(training_days_per_week=3))
    sei = wg.generate_plan(catalogo, _profilo(training_days_per_week=6))

    minimo, massimo = wg.WEEKLY_SETS_BY_EXPERIENCE[ExperienceLevel.INTERMEDIATE]
    for plan in (tre, sei):
        assert all(minimo <= v <= massimo for v in plan.weekly_sets_per_muscle.values())


# --- Recuperi e RIR (rest_periods_and_rir.md) -------------------------------


def test_recuperi_distinti_per_multiarticolari_e_isolamenti(catalogo):
    plan = wg.generate_plan(catalogo, _profilo())

    for item in plan.exercises:
        atteso = (
            wg.REST_COMPOUND_SECONDS
            if item.exercise.is_compound
            else wg.REST_ISOLATION_SECONDS
        )
        assert item.rest_seconds == atteso


def test_obiettivo_forza_usa_recuperi_lunghi_e_poche_ripetizioni(catalogo):
    plan = wg.generate_plan(catalogo, _profilo(goal=Goal.STRENGTH))

    assert all(i.rest_seconds == wg.REST_STRENGTH_SECONDS for i in plan.exercises)
    for i in plan.exercises:
        atteso = (3, 5) if i.exercise.is_compound else (6, 8)
        assert (i.reps_min, i.reps_max) == atteso


@pytest.mark.parametrize("goal", list(wg.REP_RANGES))
def test_range_di_ripetizioni_stretti(catalogo, goal):
    """Niente range generici come 6-12: al massimo 2-3 ripetizioni di
    ampiezza, così è chiaro quando aumentare il carico."""
    plan = wg.generate_plan(catalogo, _profilo(goal=goal))
    for i in plan.exercises:
        assert i.reps_max - i.reps_min <= 2
        assert (i.reps_min, i.reps_max) == wg.rep_range(goal, i.exercise.is_compound)


def test_serie_per_esercizio_restano_2_3_quando_il_tetto_lo_consente(catalogo):
    """Intermedio, per gruppo muscolare: il volume si divide su più esercizi
    invece di accumularsi su uno solo."""
    # Il catalogo base ha tre esercizi per muscolo: per dividere 10 serie in
    # blocchi da 2-3 ne servono quattro.
    catalogo.add_all(
        [
            Exercise(name="Chest compound 2", primary_muscle="Chest", equipment="Machine", is_compound=True),
            Exercise(name="Chest isolation 2", primary_muscle="Chest", equipment="Cable", is_compound=False),
        ]
    )
    catalogo.commit()
    plan = wg.generate_plan(
        catalogo,
        _profilo(training_days_per_week=3, split_type="muscle_group"),
        split_type="muscle_group",
    )
    petto = [i for i in plan.exercises if i.exercise.primary_muscle == "Chest"]
    assert len(petto) >= 2
    assert all(i.sets <= wg.TARGET_SETS_PER_EXERCISE for i in petto)


def test_slot_esercizi_distribuiti_a_turno():
    assert wg._allocate_exercise_slots([4, 4], 8) == [4, 4]
    assert wg._allocate_exercise_slots([4, 4, 4, 4], 8) == [2, 2, 2, 2]
    assert wg._allocate_exercise_slots([1, 3, 1], 8) == [1, 3, 1]


@pytest.mark.parametrize(
    "livello,rir_atteso",
    [
        (ExperienceLevel.BEGINNER, 3),
        (ExperienceLevel.INTERMEDIATE, 2),
        (ExperienceLevel.ADVANCED, 1),
    ],
)
def test_rir_piu_conservativo_per_i_principianti(catalogo, livello, rir_atteso):
    """Ai principianti si lascia più margine dal cedimento: la tecnica è
    ancora in costruzione e il cedimento la degrada."""
    plan = wg.generate_plan(catalogo, _profilo(experience_level=livello))
    assert all(i.rir == rir_atteso for i in plan.exercises)


# --- Qualità della selezione -------------------------------------------------


def test_giornate_a_e_b_non_sono_identiche(catalogo):
    """Due sessioni Upper con gli stessi esercizi rendono inutile lo split:
    la rotazione deve pescare esercizi diversi dal pool disponibile."""
    plan = wg.generate_plan(catalogo, _profilo(training_days_per_week=4))

    upper_a = {i.exercise.name for i in plan.exercises if i.day_label == "Upper A"}
    upper_b = {i.exercise.name for i in plan.exercises if i.day_label == "Upper B"}

    assert upper_a and upper_b
    assert upper_a != upper_b


def test_due_esercizi_per_muscolo_abbinano_multiarticolare_e_isolamento(catalogo):
    """Pescando entrambi dallo stesso ordinamento si otterrebbero due
    multi-articolari (in wger sono la maggioranza), lasciando la scheda senza
    isolamento e con tutti i recuperi identici."""
    plan = wg.generate_plan(
        catalogo, _profilo(experience_level=ExperienceLevel.ADVANCED, training_days_per_week=4)
    )

    per_muscolo: dict[tuple[str, str], list[bool]] = {}
    for item in plan.exercises:
        chiave = (item.day_label, item.exercise.primary_muscle)
        per_muscolo.setdefault(chiave, []).append(item.exercise.is_compound)

    coppie = [tipi for tipi in per_muscolo.values() if len(tipi) == 2]
    assert coppie, "nessun gruppo muscolare ha ricevuto due esercizi"
    assert all(sorted(tipi) == [False, True] for tipi in coppie)


def test_recuperi_differenziati_nella_stessa_scheda(catalogo):
    """Conseguenza pratica dell'abbinamento: una scheda deve contenere sia
    recuperi da multi-articolare sia da isolamento."""
    plan = wg.generate_plan(
        catalogo, _profilo(experience_level=ExperienceLevel.ADVANCED, training_days_per_week=4)
    )
    recuperi = {i.rest_seconds for i in plan.exercises}
    assert recuperi == {wg.REST_COMPOUND_SECONDS, wg.REST_ISOLATION_SECONDS}


# --- Gate di sicurezza (screening_and_red_flags.md) -------------------------


def test_screening_positivo_riduce_il_volume_al_minimo(catalogo):
    profilo = _profilo(experience_level=ExperienceLevel.ADVANCED)
    screening = ScreeningRecord(heart_condition=True)

    con_gate = wg.generate_plan(catalogo, profilo, screening=screening)
    senza_gate = wg.generate_plan(catalogo, profilo)

    minimo, _ = wg.WEEKLY_SETS_BY_EXPERIENCE[ExperienceLevel.ADVANCED]
    assert all(v <= minimo for v in con_gate.weekly_sets_per_muscle.values())
    assert max(con_gate.weekly_sets_per_muscle.values()) < max(
        senza_gate.weekly_sets_per_muscle.values()
    )


def test_screening_positivo_produce_un_avviso_esplicito(catalogo):
    plan = wg.generate_plan(
        catalogo, _profilo(), screening=ScreeningRecord(bone_joint_problem=True)
    )
    assert any("medico" in w.lower() for w in plan.warnings)
    assert "screening" in plan.knowledge_tags


def test_screening_negativo_non_limita_nulla(catalogo):
    senza_si = wg.generate_plan(catalogo, _profilo(), screening=ScreeningRecord())
    normale = wg.generate_plan(catalogo, _profilo())
    assert senza_si.weekly_sets_per_muscle == normale.weekly_sets_per_muscle
    # Lo screening negativo non aggiunge avvertenze rispetto al piano normale
    # (che può averne di proprie, per esempio sulla distribuzione delle serie).
    assert senza_si.warnings == normale.warnings
    assert not any("screening" in w for w in senza_si.warnings)


# --- Linee guida per età (who_physical_activity.md) -------------------------


def test_over_65_riceve_lavoro_su_equilibrio(catalogo):
    anziano = _profilo(birth_date=dt.date(dt.date.today().year - 70, 1, 1))
    plan = wg.generate_plan(catalogo, anziano)

    assert any("equilibrio" in w.lower() for w in plan.warnings)
    assert "attivita_generale" in plan.knowledge_tags


def test_under_65_non_riceve_lavvertenza_equilibrio(catalogo):
    plan = wg.generate_plan(catalogo, _profilo())
    assert not any("equilibrio" in w.lower() for w in plan.warnings)


# --- Attrezzatura disponibile ------------------------------------------------


def test_attrezzatura_limitata_esclude_gli_esercizi_non_eseguibili(catalogo):
    plan = wg.generate_plan(catalogo, _profilo(available_equipment="dumbbell"))

    for item in plan.exercises:
        equip = (item.exercise.equipment or "").lower()
        assert "barbell" not in equip


def test_corpo_libero_sempre_disponibile(catalogo):
    """Senza attrezzatura la scheda deve comunque esistere, usando gli
    esercizi a corpo libero."""
    plan = wg.generate_plan(catalogo, _profilo(available_equipment="tappetino"))

    assert plan.exercises
    assert all(
        wg.BODYWEIGHT in (i.exercise.equipment or "").lower() for i in plan.exercises
    )


def test_nessun_esercizio_disponibile_solleva_errore(db):
    """Catalogo vuoto: meglio un errore esplicito che una scheda vuota."""
    with pytest.raises(wg.GenerationError):
        wg.generate_plan(db, _profilo())


# --- Struttura degli split ---------------------------------------------------


@pytest.mark.parametrize(
    "giorni,etichette_attese",
    [
        (2, ["Giorno A", "Giorno B"]),
        (3, ["Giorno A", "Giorno B", "Giorno C"]),
        (4, ["Upper A", "Lower A", "Upper B", "Lower B"]),
        (6, ["Push A", "Pull A", "Gambe A", "Push B", "Pull B", "Gambe B"]),
    ],
)
def test_split_per_giorni_disponibili(giorni, etichette_attese):
    assert [g for g, _ in wg.build_split(giorni)] == etichette_attese


def test_full_body_non_include_i_gruppi_minori():
    """Brachialis, Soleus e simili hanno pochi esercizi in catalogo e vengono
    allenati come secondari: dedicargli slot gonfierebbe la sessione."""
    _, muscoli = wg.build_split(3)[0]
    assert "Brachialis" not in muscoli and "Soleus" not in muscoli


def test_tetto_di_esercizi_per_sessione_rispettato(catalogo):
    """Senza tetto, una giornata Upper produrrebbe 12 esercizi: oltre due ore
    di seduta, che nessuno completa come prescritto."""
    for giorni in (3, 4, 6):
        plan = wg.generate_plan(
            catalogo,
            _profilo(training_days_per_week=giorni, experience_level=ExperienceLevel.ADVANCED),
        )
        per_giorno: dict[str, int] = {}
        for item in plan.exercises:
            per_giorno[item.day_label] = per_giorno.get(item.day_label, 0) + 1

        assert max(per_giorno.values()) <= wg.MAX_EXERCISES_PER_SESSION


# --- Persistenza -------------------------------------------------------------


def test_persist_disattiva_la_scheda_precedente(catalogo):
    profilo = _profilo()
    catalogo.add(profilo)
    catalogo.commit()

    prima = wg.persist_plan(catalogo, profilo, wg.generate_plan(catalogo, profilo))
    seconda = wg.persist_plan(catalogo, profilo, wg.generate_plan(catalogo, profilo))

    catalogo.refresh(prima)
    assert prima.is_active is False and prima.ended_at is not None
    assert seconda.is_active is True

    # La vecchia resta nello storico: serve ai report di progressione.
    assert len(list(catalogo.scalars(select(WorkoutPlan)))) == 2


def test_persist_registra_le_fonti_usate(catalogo):
    """Deve essere sempre possibile ricostruire su quali documenti si basa
    una scheda: è il requisito di `evidence_conduct.md`."""
    profilo = _profilo()
    catalogo.add(profilo)
    catalogo.commit()

    generata = wg.generate_plan(catalogo, profilo, screening=ScreeningRecord())
    plan = wg.persist_plan(catalogo, profilo, generata)

    log = catalogo.scalars(select(AgentRecommendationLog)).one()
    assert log.reference_id == plan.id
    assert log.recommendation_type == RecommendationType.WORKOUT_PLAN_GENERATED
    assert "volume_allenamento" in log.knowledge_source_tags
    assert log.used_llm is False


# --- Spiegazione in linguaggio naturale --------------------------------------


def test_spiegazione_ripiega_su_quella_deterministica_senza_llm(catalogo, monkeypatch):
    """Senza chiave LLM la scheda resta pienamente utilizzabile: perde solo il
    testo discorsivo. Nessun parametro dipende da quella chiamata."""
    from app.services import llm_client

    def _non_configurato(*args, **kwargs):
        raise llm_client.LLMNotConfigured("chiave assente")

    monkeypatch.setattr(llm_client, "generate_structured", _non_configurato)

    profilo = _profilo()
    generata = wg.generate_plan(catalogo, profilo)
    assert wg.explain_plan(generata, profilo) == generata.rationale


def test_spiegazione_ripiega_anche_se_llm_risponde_vuoto(catalogo, monkeypatch):
    from app.services import llm_client

    monkeypatch.setattr(
        llm_client, "generate_structured", lambda *a, **k: {"spiegazione": "   "}
    )

    profilo = _profilo()
    generata = wg.generate_plan(catalogo, profilo)
    assert wg.explain_plan(generata, profilo) == generata.rationale


def test_prompt_llm_contiene_i_parametri_gia_decisi(catalogo, monkeypatch):
    """L'LLM deve ricevere i numeri già calcolati, non doverli dedurre: è
    ciò che gli impedisce di inventarli."""
    from app.services import llm_client

    catturato = {}

    def _cattura(prompt, schema, **kwargs):
        catturato["prompt"] = prompt
        return {"spiegazione": "ok"}

    monkeypatch.setattr(llm_client, "generate_structured", _cattura)

    profilo = _profilo()
    generata = wg.generate_plan(catalogo, profilo)
    wg.explain_plan(generata, profilo)

    prompt = catturato["prompt"]
    assert "non modificabili" in prompt
    assert "RIR 2" in prompt
    # Le fonti devono essere allegate, incluse le regole di condotta.
    assert "training_volume.md" in prompt and "evidence_conduct.md" in prompt


def test_persist_salva_tutti_i_parametri_degli_esercizi(catalogo):
    profilo = _profilo()
    catalogo.add(profilo)
    catalogo.commit()

    generata = wg.generate_plan(catalogo, profilo)
    plan = wg.persist_plan(catalogo, profilo, generata)

    righe = list(
        catalogo.scalars(
            select(WorkoutPlanExercise).where(
                WorkoutPlanExercise.workout_plan_id == plan.id
            )
        )
    )
    assert len(righe) == len(generata.exercises)
    assert all(r.target_rir == 2 and r.rest_seconds in (90, 120) for r in righe)
