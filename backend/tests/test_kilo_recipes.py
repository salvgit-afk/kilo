"""Ricette Kilo: la raccolta curata e il suo posto nei suggerimenti.

Gli abbinamenti con USDA non si controllano qui (servirebbe la rete): li
verifica `scripts/check_kilo_recipes.py`, da rileggere quando si aggiungono
ricette. Qui si controllano i dati della raccolta e l'ordine delle fonti.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.data import kilo_recipes as k
from app.models import (
    ActivityLevel,
    DietType,
    ExperienceLevel,
    Goal,
    Ingredient,
    IngredientSource,
    Sex,
    UserProfile,
)
from app.services import meal_suggestions as ms
from app.services import nutrition_targets as nt
from app.services import recipe_analyzer, themealdb_client

CATEGORIE = {"Colazione", "Pollo e tacchino", "Pesce", "Carne rossa", "Legumi e vegetariane", "Spuntini"}

# Ingredienti che escludono una dieta: una ricetta "vegana" con il pollo
# sarebbe l'errore più grave che la raccolta può contenere.
ANIMALI = ("pollo", "tacchino", "manzo", "salmone", "tonno", "merluzzo", "gamberi")
DERIVATI = ("uov", "albume", "yogurt", "skyr", "latte", "ricotta", "feta", "mozzarella",
            "parmigiano", "grana", "miele", "fiocchi di latte")


def _profilo(**overrides) -> UserProfile:
    dati = dict(
        display_name="test", birth_date=dt.date(1996, 5, 20), sex=Sex.MALE,
        height_cm=178.0, weight_kg=76.0, goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=4,
    )
    dati.update(overrides)
    return UserProfile(**dati)


# --- La raccolta ---------------------------------------------------------------------


def test_almeno_trenta_ricette_con_id_unici():
    assert len(k.RECIPES) >= 30
    assert len(k.BY_ID) == len(k.RECIPES)


@pytest.mark.parametrize("ricetta", k.RECIPES, ids=lambda r: r.slug)
def test_ogni_ricetta_ha_dosi_in_grammi(ricetta):
    assert ricetta.category in CATEGORIE
    assert ricetta.diet in (k.OMNIVORE, k.VEGETARIAN, k.VEGAN)
    assert 1 <= ricetta.servings <= 6 and 0 < ricetta.minutes <= 120
    assert len(ricetta.ingredients) >= 2 and ricetta.steps.strip()
    for i in ricetta.ingredients:
        assert 0 < i.grams <= 1000, (ricetta.slug, i.it)
        assert i.it.strip() and i.en.strip()


@pytest.mark.parametrize("ricetta", k.RECIPES, ids=lambda r: r.slug)
def test_nomi_italiani_non_sono_termini_di_ricerca_usda(ricetta):
    """Il nome mostrato è italiano: "bananas raw" nella card era un errore."""
    for i in ricetta.ingredients:
        assert not any(w in i.it.split() for w in ("raw", "uncooked", "commercial", "cooked", "canned", "dry")), i.it


@pytest.mark.parametrize("ricetta", k.RECIPES, ids=lambda r: r.slug)
def test_dieta_dichiarata_coerente_con_gli_ingredienti(ricetta):
    testo = " ".join(i.it for i in ricetta.ingredients).lower()
    if ricetta.diet in (k.VEGETARIAN, k.VEGAN):
        assert not any(a in testo for a in ANIMALI), ricetta.slug
    if ricetta.diet == k.VEGAN:
        assert not any(d in testo for d in DERIVATI), ricetta.slug


def test_misure_lette_senza_modello():
    """Le dosi sono in grammi: l'analisi non deve mai chiedere una stima."""
    for ricetta in k.RECIPES:
        grezza = ms.kilo_raw_recipe(ricetta)
        for voce, ing in zip(grezza.ingredients, ricetta.ingredients):
            assert recipe_analyzer.parse_measure_directly(voce.measure) == pytest.approx(ing.grams)


# --- Ricerca -----------------------------------------------------------------------------


def test_ricerca_in_italiano_negli_ingredienti():
    trovate = ms.kilo_candidates(_profilo(), "pollo")
    assert trovate and all("pollo" in " ".join(i.it for i in r.ingredients) for r in trovate)
    # Né il tacchino della stessa categoria né la "cipolla", che contiene "poll".
    assert not {"polpette-tacchino", "pasta-ragu-magro"} & {r.slug for r in trovate}


def test_categoria_trovata_con_il_suo_termine():
    pesce = ms.kilo_candidates(_profilo(), "pesce")
    assert {r.category for r in pesce} == {"Pesce"}
    assert len(pesce) == sum(r.category == "Pesce" for r in k.RECIPES)


def test_ricerca_tollera_singolare_e_plurale():
    uova = {r.slug for r in ms.kilo_candidates(_profilo(), "uova")}
    uovo = {r.slug for r in ms.kilo_candidates(_profilo(), "uovo")}
    assert uova == uovo and "polpette-tacchino" in uova


def test_dieta_vegana_solo_ricette_vegane():
    ricette = ms.kilo_candidates(_profilo(diet_type=DietType.VEGAN), None)
    assert ricette and all(r.diet == k.VEGAN for r in ricette)


def test_dieta_vegetariana_include_le_vegane():
    diete = {r.diet for r in ms.kilo_candidates(_profilo(diet_type=DietType.VEGETARIAN), None)}
    assert diete == {k.VEGETARIAN, k.VEGAN}


# --- Posto nei suggerimenti -------------------------------------------------------------


@pytest.fixture
def catalogo_finto(db, monkeypatch):
    """Ogni alimento trova un ingrediente generico: niente rete."""
    ing = Ingredient(
        name="Alimento generico", source=IngredientSource.USDA, kcal_100g=150,
        protein_100g=12, carbs_100g=15, fat_100g=5, fiber_100g=1,
    )
    db.add(ing)
    db.commit()
    monkeypatch.setattr(recipe_analyzer, "_match_ingredient", lambda _db, _nome: ing)
    monkeypatch.setattr(recipe_analyzer, "prefetch_recipe_data", lambda _db, _r: None)


def _themealdb_mai_chiamato(*_a, **_k):
    raise AssertionError("TheMealDB non andava interpellato")


def test_ricette_kilo_bastano_theMealDB_non_interpellato(db, catalogo_finto, monkeypatch):
    monkeypatch.setattr(ms, "_candidate_recipes", _themealdb_mai_chiamato)
    profilo = _profilo()
    risultati = ms.suggest_meals(db, profilo, nt.compute_targets(profilo), query="pollo", top=3)
    assert len(risultati) == 3
    assert all(ms.is_kilo(s.analyzed.recipe.meal_id) for s in risultati)


def test_ricette_kilo_prima_di_quelle_esterne(db, catalogo_finto, monkeypatch):
    esterna = themealdb_client.RawRecipe(
        meal_id="52772", name="Teriyaki Chicken", category="Chicken", area="Japanese",
        instructions="...", thumbnail_url=None, tags=[],
        ingredients=[themealdb_client.RawRecipeIngredient("chicken", "500 g")],
    )
    monkeypatch.setattr(ms, "_candidate_recipes", lambda *_a, **_k: [esterna])
    profilo = _profilo()
    risultati = ms.suggest_meals(db, profilo, nt.compute_targets(profilo), query="salmone", top=4)

    fonti = [ms.is_kilo(s.analyzed.recipe.meal_id) for s in risultati]
    assert fonti[0] is True and fonti[-1] is False
    assert fonti == sorted(fonti, reverse=True)


def test_theMealDB_giu_non_blocca_le_ricette_kilo(db, catalogo_finto, monkeypatch):
    def giu(*_a, **_k):
        raise themealdb_client.MealDbError("timeout")

    monkeypatch.setattr(ms, "_candidate_recipes", giu)
    profilo = _profilo()
    risultati = ms.suggest_meals(db, profilo, nt.compute_targets(profilo), query="salmone", top=4)
    assert risultati and all(ms.is_kilo(s.analyzed.recipe.meal_id) for s in risultati)


def test_porzioni_della_ricetta_usate_nell_analisi(db, catalogo_finto, monkeypatch):
    monkeypatch.setattr(ms, "_candidate_recipes", _themealdb_mai_chiamato)
    profilo = _profilo()
    risultati = ms.suggest_meals(db, profilo, nt.compute_targets(profilo), query="ragù", top=1)
    assert risultati[0].analyzed.servings == k.get("kilo:pasta-ragu-magro").servings
