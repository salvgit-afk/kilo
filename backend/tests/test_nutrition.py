"""Test del motore nutrizionale: target, analisi ricette, suggerimenti.

I valori attesi vengono dai file della knowledge base (EFSA per i
macronutrienti, ISSN per le proteine). Come per il generatore di schede, un
test che fallisce va letto chiedendosi se il risultato rispetti ancora le
fonti, non se "il numero è cambiato".
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import (
    ActivityLevel,
    DietType,
    ExperienceLevel,
    Goal,
    Ingredient,
    IngredientSource,
    NutritionPlan,
    Sex,
    UserProfile,
)
from app.services import meal_suggestions as ms
from app.services import nutrition_targets as nt
from app.services import recipe_analyzer as ra
from app.services.themealdb_client import RawRecipe, RawRecipeIngredient


def _profilo(**overrides) -> UserProfile:
    defaults = dict(
        display_name="test",
        birth_date=dt.date(1996, 5, 20),
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


# --- Target calorici e macro -------------------------------------------------


def test_proteine_calcolate_sul_peso_non_sulle_calorie():
    """`protein_intake.md` prescrive g/kg. Un calcolo percentuale ridurrebbe
    le proteine proprio in deficit, quando servono di più."""
    magro = nt.compute_targets(_profilo(weight_kg=60))
    pesante = nt.compute_targets(_profilo(weight_kg=90))

    assert magro.protein_g == pytest.approx(60 * magro.protein_g_per_kg, abs=1)
    assert pesante.protein_g == pytest.approx(90 * pesante.protein_g_per_kg, abs=1)


def test_deficit_alza_le_proteine_per_kg():
    """In deficit le proteine servono a preservare la massa magra: il target
    per kg deve salire, non scendere."""
    massa = nt.compute_targets(_profilo(goal=Goal.HYPERTROPHY))
    definizione = nt.compute_targets(_profilo(goal=Goal.FAT_LOSS))

    assert definizione.protein_g_per_kg > massa.protein_g_per_kg
    assert definizione.target_kcal < massa.target_kcal


def test_surplus_massa_si_riduce_con_l_esperienza():
    """`diets_body_composition.md` (ISSN): surplus più ampio per chi inizia,
    più contenuto per chi è già allenato, dentro il range +10/+15%."""
    surplus = [
        nt.compute_targets(_profilo(experience_level=livello)).calorie_adjustment_pct
        for livello in (ExperienceLevel.BEGINNER, ExperienceLevel.INTERMEDIATE, ExperienceLevel.ADVANCED)
    ]
    assert surplus[0] > surplus[1] > surplus[2]
    assert all(0.10 <= s <= 0.15 for s in surplus)


def test_surplus_legato_all_esperienza_solo_in_massa():
    """Gli altri obiettivi non cambiano con il livello di esperienza."""
    for obiettivo in (Goal.FAT_LOSS, Goal.MAINTENANCE, Goal.STRENGTH):
        valori = {
            nt.compute_targets(_profilo(goal=obiettivo, experience_level=livello)).calorie_adjustment_pct
            for livello in (ExperienceLevel.BEGINNER, ExperienceLevel.ADVANCED)
        }
        assert len(valori) == 1


def test_spiegazione_del_surplus_invita_ad_aggiustarlo():
    t = nt.compute_targets(_profilo(experience_level=ExperienceLevel.BEGINNER))
    assert "esperienza" in t.rationale and "aggiustato" in t.rationale


def test_proteine_dentro_il_range_issn():
    """Range ISSN per persone attive: 1,4-2,4 g/kg."""
    for obiettivo in (Goal.HYPERTROPHY, Goal.FAT_LOSS, Goal.MAINTENANCE, Goal.GENERAL_HEALTH):
        target = nt.compute_targets(_profilo(goal=obiettivo))
        assert 1.4 <= target.protein_g_per_kg <= 2.4


def test_grassi_dentro_il_range_efsa():
    minimo, massimo = nt.FAT_ENERGY_PCT_RANGE
    for obiettivo in (Goal.HYPERTROPHY, Goal.FAT_LOSS, Goal.MAINTENANCE):
        target = nt.compute_targets(_profilo(goal=obiettivo))
        assert minimo <= target.fat_pct <= massimo


def test_macro_sommano_alle_calorie_target():
    """Controllo di coerenza: i grammi devono ricostruire le calorie."""
    t = nt.compute_targets(_profilo())
    ricalcolate = (
        t.protein_g * nt.KCAL_PER_G_PROTEIN
        + t.carbs_g * nt.KCAL_PER_G_CARBS
        + t.fat_g * nt.KCAL_PER_G_FAT
    )
    assert ricalcolate == pytest.approx(t.target_kcal, rel=0.02)


def test_carboidrati_sotto_il_range_efsa_vengono_segnalati():
    """In deficit con proteine alte i carboidrati residui possono uscire dal
    range EFSA: è atteso e va dichiarato, non corretto abbassando le proteine."""
    t = nt.compute_targets(_profilo(goal=Goal.FAT_LOSS))

    minimo, _ = nt.CARBS_ENERGY_PCT_RANGE
    if t.carbs_pct < minimo:
        assert any("EFSA" in w for w in t.warnings)
        assert any("proteine" in w.lower() for w in t.warnings)


def test_dieta_vegana_non_scende_sotto_la_soglia_proteica():
    """`vegetarian_vegan_nutrition.md`: sotto 1,5 g/kg da fonti vegetali gli
    adattamenti muscolari risultano compromessi."""
    vegano = nt.compute_targets(
        _profilo(goal=Goal.GENERAL_HEALTH, diet_type=DietType.VEGAN)
    )
    assert vegano.protein_g_per_kg >= nt.PLANT_BASED_PROTEIN_FLOOR
    assert any("vegetale" in w.lower() for w in vegano.warnings)
    assert "vegano" in vegano.knowledge_tags


def test_vegano_carica_anche_i_micronutrienti():
    """B12, ferro, iodio e colina sono i punti critici di una dieta vegana."""
    vegano = nt.compute_targets(_profilo(diet_type=DietType.VEGAN))
    assert "micronutrienti" in vegano.knowledge_tags


def test_deficit_con_molti_allenamenti_avvisa_sul_recupero():
    """`energy_availability_reds.md`: è la combinazione a rischio."""
    t = nt.compute_targets(_profilo(goal=Goal.FAT_LOSS), training_days=6)
    assert any("deficit" in w.lower() and "allenamento" in w.lower() for w in t.warnings)
    assert "deficit_calorico" in t.knowledge_tags


def test_deficit_moderato_senza_allenamenti_intensi_non_allarma():
    t = nt.compute_targets(_profilo(goal=Goal.FAT_LOSS), training_days=3)
    assert not any("giorni di allenamento" in w for w in t.warnings)


def test_donna_riceve_target_idrico_efsa_diverso():
    uomo = nt.compute_targets(_profilo(sex=Sex.MALE))
    donna = nt.compute_targets(_profilo(sex=Sex.FEMALE))
    assert (uomo.water_l, donna.water_l) == (2.5, 2.0)


def test_zuccheri_liberi_al_dieci_percento_delle_calorie():
    t = nt.compute_targets(_profilo())
    atteso = t.target_kcal * nt.FREE_SUGARS_MAX_PCT / nt.KCAL_PER_G_CARBS
    assert t.free_sugars_max_g == pytest.approx(atteso, abs=1)


def test_persist_disattiva_il_piano_precedente(db):
    profilo = _profilo()
    db.add(profilo)
    db.commit()

    primo = nt.persist_plan(db, profilo, nt.compute_targets(profilo))
    secondo = nt.persist_plan(db, profilo, nt.compute_targets(profilo))

    db.refresh(primo)
    assert primo.is_active is False and primo.ended_at is not None
    assert secondo.is_active is True


# --- Conversione delle quantità ----------------------------------------------


@pytest.mark.parametrize(
    "misura,grammi_attesi",
    [
        ("900g", 900),
        ("1.2 kg", 1200),
        ("250 ml", 250),
        ("2 oz", 56.7),
        ("½ kg", 500),
    ],
)
def test_misure_esplicite_convertite_senza_llm(misura, grammi_attesi):
    """Le unità di peso non richiedono interpretazione: convertirle in locale
    rende il sistema utilizzabile anche senza chiave API."""
    assert ra.parse_measure_directly(misura) == pytest.approx(grammi_attesi, rel=0.01)


@pytest.mark.parametrize(
    "misura", ["¼ cup", "1 clove peeled crushed", "5 thinly sliced", "To taste", ""]
)
def test_misure_casalinghe_non_convertite_localmente(misura):
    """Servono conoscenza del mondo (quanto pesa uno spicchio d'aglio):
    vanno all'LLM, non a una tabella di unità."""
    assert ra.parse_measure_directly(misura) is None


# --- Abbinamento degli ingredienti -------------------------------------------


@pytest.mark.parametrize(
    "query,giusto,sbagliato",
    [
        # Casi reali osservati: USDA restituisce per primo il derivato.
        ("Tomatoes", "Tomato, roma", "Tomato powder"),
        ("Salt", "Salt, table", "Butter, salted"),
        ("Onion", "Onions, raw", "Onions, dehydrated flakes"),
        ("Chicken", "Chicken, breast, raw", "Chicken spread"),
    ],
)
def test_alimento_base_preferito_alla_forma_trasformata(query, giusto, sbagliato):
    """Una ricetta che dice "Tomatoes" intende i pomodori, non il pomodoro in
    polvere: 302 kcal/100 g invece di 22 gonfierebbero il totale di centinaia
    di calorie."""
    assert ra.score_match(query, giusto) > ra.score_match(query, sbagliato)


def test_marcatore_presente_nella_query_non_penalizza():
    """"oil" indica una forma trasformata, ma se l'utente cerca proprio
    "Vegetable oil" non va penalizzata: si penalizza lo scostamento dalla
    richiesta, non proprietà assolute."""
    assert ra.score_match("Vegetable oil", "Vegetable oil") > ra.score_match(
        "Vegetable oil", "Vegetable oil spread"
    )


def test_plurali_riconosciuti():
    assert ra.score_match("Tomatoes", "Tomato") > 0
    assert ra.score_match("Eggs", "Egg, whole, raw") > 0


# --- Analisi della ricetta ----------------------------------------------------


def _ricetta(*ingredienti: tuple[str, str]) -> RawRecipe:
    return RawRecipe(
        meal_id="1",
        name="Test",
        category="Chicken",
        area="Italian",
        instructions="Cuoci.",
        thumbnail_url=None,
        tags=[],
        ingredients=[RawRecipeIngredient(name=n, measure=m) for n, m in ingredienti],
    )


@pytest.fixture
def catalogo_alimenti(db, monkeypatch):
    """Alimenti noti, senza rete."""
    alimenti = {
        "Chicken": Ingredient(
            source=IngredientSource.USDA, source_id="1", name="Chicken, breast, raw",
            kcal_100g=110, protein_100g=23, carbs_100g=0, fat_100g=2, fiber_100g=0,
        ),
        "Rice": Ingredient(
            source=IngredientSource.USDA, source_id="2", name="Rice, white, raw",
            kcal_100g=360, protein_100g=7, carbs_100g=80, fat_100g=1, fiber_100g=1,
        ),
    }
    db.add_all(alimenti.values())
    db.commit()

    def _finta_ricerca(_db, nome, **kwargs):
        return [alimenti[nome]] if nome in alimenti else []

    monkeypatch.setattr(
        "app.services.catalog_sync.search_and_cache_ingredients", _finta_ricerca
    )
    return db


def test_macro_calcolati_dal_database_non_dallllm(catalogo_alimenti):
    """200 g di petto di pollo a 110 kcal/100 g fanno 220 kcal: l'aritmetica
    la fa il database, mai il modello."""
    analizzata = ra.analyze_recipe(
        catalogo_alimenti, _ricetta(("Chicken", "200g")), servings=1, use_llm=False
    )
    assert analizzata.total_kcal == pytest.approx(220)
    assert analizzata.ingredients[0].protein_g == pytest.approx(46)


def test_porzioni_dividono_i_totali(catalogo_alimenti):
    analizzata = ra.analyze_recipe(
        catalogo_alimenti, _ricetta(("Chicken", "400g")), servings=4, use_llm=False
    )
    assert analizzata.kcal_per_serving == pytest.approx(110)


def test_copertura_parziale_dichiarata(catalogo_alimenti):
    """Se metà degli ingredienti non è riconosciuta, il totale è incompleto:
    va dichiarato, non presentato come un dato preciso."""
    analizzata = ra.analyze_recipe(
        catalogo_alimenti,
        _ricetta(("Chicken", "200g"), ("Ingrediente ignoto", "100g")),
        servings=1,
        use_llm=False,
    )
    assert analizzata.coverage == pytest.approx(0.5)
    assert analizzata.is_reliable is False
    assert "Ingrediente ignoto" in analizzata.unresolved_names


def test_senza_llm_le_misure_casalinghe_restano_irrisolte(catalogo_alimenti):
    """Fallback onesto: meglio dichiarare l'ingrediente non risolto che
    inventarne il peso."""
    analizzata = ra.analyze_recipe(
        catalogo_alimenti, _ricetta(("Rice", "¼ cup")), servings=1, use_llm=False
    )
    assert analizzata.ingredients[0].grams is None
    assert analizzata.coverage == 0.0


def test_conversione_llm_scarta_valori_assurdi(catalogo_alimenti, monkeypatch):
    """Un peso negativo o di decine di chili indica un errore di
    interpretazione: va scartato, non usato."""
    from app.services import llm_client

    monkeypatch.setattr(
        llm_client,
        "generate_structured",
        lambda *a, **k: {"conversioni": [{"indice": 0, "grammi": -50}]},
    )
    analizzata = ra.analyze_recipe(
        catalogo_alimenti, _ricetta(("Rice", "¼ cup")), servings=1
    )
    assert analizzata.ingredients[0].grams is None


# --- Suggerimento dei pasti ---------------------------------------------------


def _analizzata(kcal: float, protein: float, fiber: float = 0.0) -> ra.AnalyzedRecipe:
    voce = ra.AnalyzedIngredient(
        name="x", measure="100g", grams=100,
        ingredient=Ingredient(
            source=IngredientSource.USDA, source_id="9", name="x",
            kcal_100g=kcal, protein_100g=protein, carbs_100g=0, fat_100g=0,
        ),
        kcal=kcal, protein_g=protein, fiber_g=fiber,
    )
    return ra.AnalyzedRecipe(recipe=_ricetta(("x", "100g")), servings=1, ingredients=[voce])


def test_ricetta_troppo_calorica_penalizzata():
    """Sforare il target è un problema quanto restarne troppo sotto."""
    giusta, _ = ms.score_fit(_analizzata(600, 35), kcal_needed=600, protein_needed=35)
    eccessiva, motivi = ms.score_fit(
        _analizzata(1400, 35), kcal_needed=600, protein_needed=35
    )
    assert giusta > eccessiva
    assert any("più di quanto ti resta" in m for m in motivi)


def test_finestra_proteica_per_pasto_premiata():
    """`protein_intake.md`: 20-40 g a pasto è la finestra utile."""
    dentro, motivi = ms.score_fit(_analizzata(600, 30), kcal_needed=600, protein_needed=30)
    sotto, _ = ms.score_fit(_analizzata(600, 8), kcal_needed=600, protein_needed=30)

    assert dentro > sotto
    assert any("sintesi proteica" in m for m in motivi)


def test_poche_proteine_suggerisce_di_integrare():
    _, motivi = ms.score_fit(_analizzata(600, 5), kcal_needed=600, protein_needed=40)
    assert any("fonte proteica" in m for m in motivi)


def test_target_gia_raggiunto_non_propone_altro():
    punteggio, motivi = ms.score_fit(_analizzata(500, 30), kcal_needed=0, protein_needed=0)
    assert punteggio == 0.0
    assert any("già raggiunto" in m for m in motivi)


def test_fibra_abbondante_premiata():
    con_fibra, motivi = ms.score_fit(
        _analizzata(600, 30, fiber=10), kcal_needed=600, protein_needed=30
    )
    senza, _ = ms.score_fit(_analizzata(600, 30), kcal_needed=600, protein_needed=30)
    assert con_fibra > senza
    assert any("fibra" in m for m in motivi)
