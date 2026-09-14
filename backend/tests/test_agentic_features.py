"""Test delle funzioni introdotte per la libreria esercizi, le traduzioni e
le proposte dell'agente.

Nessun test tocca la rete: le chiamate LLM sono sostituite, e dove non lo
sono si verifica che il codice non le faccia (dizionario, validazioni).
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import (
    ActivityLevel,
    DietType,
    Exercise,
    ExperienceLevel,
    Goal,
    Ingredient,
    IngredientSource,
    Sex,
    UserProfile,
)
from app.services import chat_agent, exercise_library, gap_filler, translation
from app.services import workout_generator as wg


# --- Libreria esercizi (free-exercise-db) ------------------------------------------

VOCE_PANCA = {
    "id": "Barbell_Bench_Press_-_Medium_Grip",
    "name": "Barbell Bench Press - Medium Grip",
    "category": "strength",
    "mechanic": "compound",
    "equipment": "barbell",
    "level": "beginner",
    "primaryMuscles": ["chest"],
    "secondaryMuscles": ["shoulders", "triceps", "chest"],
    "instructions": ["Lie back on a flat bench.", "Lower the bar to your chest."],
    "images": ["Barbell_Bench_Press_-_Medium_Grip/0.jpg", "Barbell_Bench_Press_-_Medium_Grip/1.jpg"],
}


def test_parse_entry_mappa_muscoli_fotogrammi_e_priorita():
    campi = exercise_library.parse_entry(VOCE_PANCA)
    assert campi["primary_muscle"] == "Chest"
    # Il primario non si ripete fra i secondari.
    assert campi["secondary_muscles"] == "Shoulders, Triceps"
    assert len(campi["demo_images"]) == 2
    assert campi["demo_images"][0].startswith(exercise_library.IMAGE_BASE_URL)
    assert campi["is_compound"] is True
    assert campi["priority"] == 0  # primo fra gli esercizi di base del petto


@pytest.mark.parametrize(
    "modifica",
    [
        {"category": "stretching"},
        {"images": []},
        {"primaryMuscles": ["neck"]},
    ],
)
def test_parse_entry_scarta_voci_non_utilizzabili(modifica):
    assert exercise_library.parse_entry({**VOCE_PANCA, **modifica}) is None


def test_corpo_libero_usa_la_stessa_etichetta_di_wger():
    campi = exercise_library.parse_entry({**VOCE_PANCA, "equipment": "body only"})
    assert campi["equipment"] == wg.BODYWEIGHT


def test_con_la_libreria_il_generatore_non_mescola_le_fonti(db):
    """Importata la libreria, la stessa panca non deve comparire due volte
    con due nomi diversi (una da wger, una da free-exercise-db)."""
    for muscolo in wg.FULL_BODY_MUSCLES:
        db.add(Exercise(name=f"wger {muscolo}", primary_muscle=muscolo, is_compound=True))
    dataset = [
        {**VOCE_PANCA, "id": f"X_{m}", "name": f"lib {m}", "primaryMuscles": [m]}
        for m in ("chest", "lats", "quadriceps", "glutes", "shoulders", "abdominals")
    ]
    exercise_library.sync_library(db, dataset=dataset)

    profilo = UserProfile(
        display_name="t", birth_date=dt.date(1995, 1, 1), sex=Sex.MALE,
        height_cm=178, weight_kg=76, goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    plan = wg.generate_plan(db, profilo)
    assert plan.exercises
    assert all(i.exercise.source == exercise_library.SOURCE for i in plan.exercises)


def test_sync_library_non_cancella_le_traduzioni(db):
    exercise_library.sync_library(db, dataset=[VOCE_PANCA])
    ex = db.query(Exercise).one()
    ex.name_it = "Panca piana con bilanciere"
    db.commit()

    exercise_library.sync_library(db, dataset=[VOCE_PANCA])
    assert db.query(Exercise).one().name_it == "Panca piana con bilanciere"


def test_traduzione_esercizi_scarta_passaggi_riassunti(db, monkeypatch):
    exercise_library.sync_library(db, dataset=[{**VOCE_PANCA, "instructions": ["a", "b", "c", "d", "e", "f"]}])
    ex = db.query(Exercise).one()
    monkeypatch.setattr(
        "app.services.llm_client.generate_structured",
        lambda *a, **k: {
            "esercizi": [
                {"id": ex.id, "nome": "Panca piana", "esecuzione": ["unico passo"], "focus": ["petto"]}
            ]
        },
    )
    assert translation.translate_exercises(db, [ex]) == 1
    assert ex.name_it == "Panca piana"
    # 1 passaggio contro 6 originali: il modello ha riassunto, si tiene l'originale.
    assert ex.instructions_it is None


# --- Ricerche in italiano ------------------------------------------------------------


def test_query_dizionario_senza_llm(db, monkeypatch):
    def _vietato(*a, **k):
        raise AssertionError("non doveva chiamare l'LLM")

    monkeypatch.setattr("app.services.llm_client.generate_structured", _vietato)
    assert translation.query_to_english(db, "pollo") == "chicken"
    assert translation.query_to_english(db, "petto di pollo") == "chicken breast"
    # Nel diario le parole sconosciute restano come sono.
    assert translation.query_to_english(db, "riso basmati", allow_llm=False) == "rice basmati"
    assert translation.query_to_english(db, "chicken breast", allow_llm=False) == "chicken breast"


# --- «Cosa mi manca oggi» -------------------------------------------------------------


def _ing(nome, kcal, p, c, g, source=IngredientSource.USDA):
    return Ingredient(
        name=nome, source=source, source_id=nome, kcal_100g=kcal,
        protein_100g=p, carbs_100g=c, fat_100g=g,
    )


def test_atwater_scarta_valori_incoerenti():
    assert gap_filler.is_plausible(_ing("petto", 120, 23, 0, 2.6))
    assert not gap_filler.is_plausible(_ing("banana crowdsourced", 0, 1, 23, 0))
    assert not gap_filler.is_plausible(_ing("petto sbagliato", 65, 23, 0, 2.6))


def test_porzione_limitata_dalle_calorie_rimaste():
    petto = _ing("petto", 120, 23, 0, 2.6)
    assert gap_filler.portion_for(petto, protein_left_g=30, kcal_left=1000) == 130
    assert gap_filler.portion_for(petto, protein_left_g=30, kcal_left=60) == 50
    assert gap_filler.portion_for(petto, protein_left_g=30, kcal_left=20) is None


def test_dieta_vegana_esclude_carne_e_latticini():
    assert not gap_filler.compatible_with_diet("Chicken breast, raw", DietType.VEGAN)
    assert not gap_filler.compatible_with_diet("Cheese, ricotta", DietType.VEGAN)
    assert gap_filler.compatible_with_diet("Tofu, firm", DietType.VEGAN)
    assert gap_filler.compatible_with_diet("Cheese, ricotta", DietType.VEGETARIAN)


# --- Azioni proposte dalla chat -----------------------------------------------------


def test_azioni_valide_passano_e_quelle_malformate_no():
    azioni = chat_agent._clean_actions(
        [
            {"tipo": "apri_sezione", "etichetta": "Apri il diario", "valore": "diario"},
            {"tipo": "apri_sezione", "etichetta": "Boh", "valore": "sezione_inventata"},
            {"tipo": "registra_peso", "etichetta": "Registra", "valore": "72,5 kg"},
            {"tipo": "registra_peso", "etichetta": "Registra", "valore": "7250"},
        ],
        "quanto devo mangiare?",
    )
    assert [a["type"] for a in azioni] == ["open_section", "log_weight"]
    assert azioni[1]["value"] == "72.5"


def test_risposta_che_dichiara_eseguita_un_azione_viene_corretta():
    corretta = chat_agent.disclaim_claimed_actions("Ho registrato il tuo peso di 64,5 kg.", has_actions=True)
    assert "non ho ancora fatto nulla" in corretta
    invariata = "Se vuoi lo registro: conferma con il pulsante qui sotto."
    assert chat_agent.disclaim_claimed_actions(invariata, has_actions=True) == invariata


def test_multiarticolari_fuori_dagli_esercizi_di_base_non_scavalcano_i_curl(db):
    """Un "Drag Curl" classificato multi-articolare non deve prendere il posto
    del curl con bilanciere, che è fra gli esercizi di base."""
    db.add_all(
        [
            Exercise(name="Drag Curl", primary_muscle="Biceps", is_compound=True, priority=100,
                     source=exercise_library.SOURCE),
            Exercise(name="Barbell Curl", primary_muscle="Biceps", is_compound=False, priority=0,
                     source=exercise_library.SOURCE),
            Exercise(name="Hammer Curls", primary_muscle="Biceps", is_compound=False, priority=2,
                     source=exercise_library.SOURCE),
        ]
    )
    db.commit()
    assert [e.name for e in wg._pick_exercises(db, "Biceps", None, wanted=1)] == ["Barbell Curl"]
    assert [e.name for e in wg._pick_exercises(db, "Biceps", None, wanted=2)] == ["Barbell Curl", "Hammer Curls"]


def test_porzioni_da_un_pasto_senza_doppioni_ne_trasformati(db):
    profilo = UserProfile(
        display_name="t", birth_date=dt.date(1995, 1, 1), sex=Sex.MALE, height_cm=178,
        weight_kg=76, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add_all(
        [
            profilo,
            _ing("Chicken, breast, skinless, raw", 120, 23, 0, 2.6),
            _ing("Chicken, breast, meat and skin, raw", 172, 21, 0, 9.3),
            _ing("Egg, white, dried", 382, 81, 7.8, 0.3),
            _ing("Fish, tuna, light, canned in water", 90, 20, 0, 1),
        ]
    )
    db.commit()
    esito = gap_filler.suggest(db, profilo, protein_left_g=120, kcal_left=2000)
    nomi = [f.ingredient.name for f in esito.foods]
    assert not any("dried" in n for n in nomi)
    assert sum(n.startswith("Chicken") for n in nomi) == 1
    # Porzioni da circa 40 g di proteine, non l'intero fabbisogno in un colpo.
    assert all(f.protein_g <= gap_filler.PROTEIN_PER_PORTION_G + 1 for f in esito.foods)


def test_nessuna_azione_sugli_integratori_se_non_se_ne_parla():
    proposta = [{"tipo": "apri_sezione", "etichetta": "Integratori", "valore": "integratori"}]
    assert chat_agent._clean_actions(proposta, "come recupero meglio?") == []
    assert chat_agent._clean_actions(proposta, "la creatina serve?")
