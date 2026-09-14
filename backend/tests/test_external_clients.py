"""Test dei client esterni e della cache locale.

Nessuna chiamata di rete: i dati di esempio sono copiati dalle risposte
reali delle API, così i test restano veloci e deterministici ma continuano
a descrivere il formato vero (comprese le sue stranezze, come i nutrienti
restituiti da wger sotto forma di stringa).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Exercise, Ingredient, IngredientSource
from app.services import catalog_sync, themealdb_client, usda_client, wger_client
from app.services.wger_client import RawExercise, RawIngredient

# --- Campioni presi da risposte reali dell'API ------------------------------

WGER_EXERCISE = {
    "id": 43,
    "category": {"id": 9, "name": "Legs"},
    "muscles": [{"id": 10, "name": "Quadriceps femoris", "name_en": "Quads"}],
    "muscles_secondary": [
        {"id": 11, "name": "Biceps femoris", "name_en": "Hamstrings"},
        {"id": 8, "name": "Gluteus maximus", "name_en": "Glutes"},
    ],
    "equipment": [{"id": 1, "name": "Barbell"}],
    "images": [],
    "translations": [
        {"language": 2, "name": "Barbell Hack Squats", "description": "<p>Stand <b>up</b>.</p>"},
        {"language": 4, "name": "Sentadilla Hack con Barra", "description": "<p>De pie.</p>"},
    ],
}

WGER_INGREDIENT = {
    "id": 2483247,
    "name": "chicken",
    "brand": "Tewco",
    "code": "5059697724916",
    "source_name": "Open Food Facts",
    # wger restituisce i nutrienti come stringhe, tranne energy.
    "energy": 175,
    "protein": "26.700",
    "carbohydrates": "0.100",
    "carbohydrates_sugar": "0.100",
    "fat": "7.500",
    "fat_saturated": "1.800",
    "fiber": "0.100",
}

# Alimento USDA "Foundation": NON ha l'id energia classico (1008), usa i
# fattori di Atwater (2047 generali, 2048 specifici).
USDA_FOUNDATION_FOOD = {
    "fdcId": 2646170,
    "description": "Chicken, breast, boneless, skinless, raw",
    "dataType": "Foundation",
    "foodNutrients": [
        {"nutrientId": 1003, "nutrientName": "Protein", "value": 22.5},
        {"nutrientId": 1004, "nutrientName": "Total lipid (fat)", "value": 1.93},
        {"nutrientId": 1005, "nutrientName": "Carbohydrate, by difference", "value": 0.0},
        {"nutrientId": 1258, "nutrientName": "Fatty acids, total saturated", "value": 0.349},
        {"nutrientId": 2047, "nutrientName": "Energy (Atwater General Factors)", "value": 106},
        {"nutrientId": 2048, "nutrientName": "Energy (Atwater Specific Factors)", "value": 112},
    ],
}

# Alimento "SR Legacy": usa l'id energia classico.
USDA_SR_LEGACY_FOOD = {
    "fdcId": 171077,
    "description": "Chicken, broilers or fryers, breast, meat only, raw",
    "dataType": "SR Legacy",
    "foodNutrients": [
        {"nutrientId": 1008, "nutrientName": "Energy", "value": 172},
        {"nutrientId": 1003, "nutrientName": "Protein", "value": 20.8},
        {"nutrientId": 1004, "nutrientName": "Total lipid (fat)", "value": 9.25},
        {"nutrientId": 1005, "nutrientName": "Carbohydrate, by difference", "value": 0.0},
    ],
}


# --- wger: parsing esercizi -------------------------------------------------


def test_esercizio_usa_il_nome_comune_del_muscolo():
    """Serve "Quads", non "Quadriceps femoris": è quello che l'utente
    riconosce nell'interfaccia."""
    ex = wger_client._parse_exercise(WGER_EXERCISE, wger_client.LANG_IT)
    assert ex.primary_muscles == ["Quads"]
    assert ex.secondary_muscles == ["Hamstrings", "Glutes"]


def test_traduzione_ripiega_sullinglese_se_manca_litaliano():
    """L'esempio non ha traduzione italiana (lingua 13): deve usare l'inglese
    invece di scartare l'esercizio."""
    ex = wger_client._parse_exercise(WGER_EXERCISE, wger_client.LANG_IT)
    assert ex.name == "Barbell Hack Squats"


def test_traduzione_preferita_viene_usata_quando_esiste():
    italiano = dict(WGER_EXERCISE)
    italiano["translations"] = [
        *WGER_EXERCISE["translations"],
        {"language": 13, "name": "Hack Squat con Bilanciere", "description": "<p>In piedi.</p>"},
    ]
    ex = wger_client._parse_exercise(italiano, wger_client.LANG_IT)
    assert ex.name == "Hack Squat con Bilanciere"


def test_descrizione_ripulita_dallhtml():
    """I tag vanno via senza lasciare spazi spuri prima della punteggiatura,
    perché questo testo finisce nell'interfaccia."""
    ex = wger_client._parse_exercise(WGER_EXERCISE, wger_client.LANG_EN)
    assert ex.description == "Stand up."


def test_esercizio_senza_traduzioni_viene_scartato():
    senza = dict(WGER_EXERCISE, translations=[])
    assert wger_client._parse_exercise(senza, wger_client.LANG_IT) is None


def test_multiarticolare_se_ha_muscoli_secondari():
    ex = wger_client._parse_exercise(WGER_EXERCISE, wger_client.LANG_EN)
    assert ex.is_compound is True

    isolamento = dict(WGER_EXERCISE, muscles_secondary=[])
    assert wger_client._parse_exercise(isolamento, wger_client.LANG_EN).is_compound is False


# --- wger: parsing ingredienti ----------------------------------------------


def test_nutrienti_stringa_convertiti_in_numeri():
    """Se questa conversione salta, i calcoli sui macro fallirebbero in
    silenzio sommando stringhe."""
    ing = wger_client._parse_ingredient(WGER_INGREDIENT)
    assert ing.protein_100g == pytest.approx(26.7)
    assert ing.fat_100g == pytest.approx(7.5)
    assert isinstance(ing.kcal_100g, float)


def test_ingrediente_senza_macro_di_base_viene_scartato():
    """Meglio nessun dato che zeri finti: un ingrediente con macro a zero
    falserebbe silenziosamente il totale di una ricetta."""
    incompleto = dict(WGER_INGREDIENT, protein=None)
    assert wger_client._parse_ingredient(incompleto) is None


def test_campi_nutrizionali_opzionali_possono_mancare():
    senza_fibra = dict(WGER_INGREDIENT, fiber=None)
    ing = wger_client._parse_ingredient(senza_fibra)
    assert ing is not None and ing.fiber_100g is None


# --- TheMealDB --------------------------------------------------------------


def test_slot_ingredienti_vuoti_ignorati():
    """L'API espone sempre 20 slot: quelli inutilizzati arrivano vuoti o null."""
    meal = {
        "idMeal": "52795",
        "strMeal": "Chicken Handi",
        "strCategory": "Chicken",
        "strArea": "Indian",
        "strInstructions": "Cuoci.",
        "strTags": "Curry,Spicy",
        **{f"strIngredient{i}": "" for i in range(1, 21)},
        **{f"strMeasure{i}": "" for i in range(1, 21)},
    }
    meal["strIngredient1"], meal["strMeasure1"] = "Chicken", "1.2 kg"
    meal["strIngredient2"], meal["strMeasure2"] = "Onion", "5 thinly sliced"
    meal["strIngredient5"] = None  # l'API usa sia "" sia null

    recipe = themealdb_client._parse_recipe(meal)
    assert [i.name for i in recipe.ingredients] == ["Chicken", "Onion"]
    assert recipe.tags == ["Curry", "Spicy"]


def test_quantita_restano_testo_libero():
    """Promemoria esplicito del limite della fonte: la conversione in grammi
    è un problema separato, non risolto dal client."""
    meal = {
        "idMeal": "1",
        "strMeal": "Test",
        **{f"strIngredient{i}": "" for i in range(1, 21)},
        **{f"strMeasure{i}": "" for i in range(1, 21)},
    }
    meal["strIngredient1"], meal["strMeasure1"] = "Rice", "¼ cup"
    recipe = themealdb_client._parse_recipe(meal)
    assert recipe.ingredients[0].measure == "¼ cup"


def test_nessun_risultato_restituisce_lista_vuota():
    """TheMealDB risponde {"meals": null}, non con una lista vuota."""
    assert themealdb_client._parse_meals({"meals": None}) == []


# --- USDA -------------------------------------------------------------------


def test_energia_letta_dai_fattori_atwater_quando_manca_id_1008():
    """Gli alimenti Foundation non hanno l'id energia classico: senza questo
    fallback risulterebbero a **zero calorie**, un errore che non darebbe
    alcun segnale e falserebbe ogni piano alimentare."""
    food = usda_client._parse_food(USDA_FOUNDATION_FOOD)
    assert food is not None
    assert food.kcal_100g == pytest.approx(106)  # 2047, non 2048


def test_energia_preferisce_id_classico_quando_presente():
    food = usda_client._parse_food(USDA_SR_LEGACY_FOOD)
    assert food.kcal_100g == pytest.approx(172)


def test_alimento_senza_macro_di_base_scartato():
    senza_proteine = dict(
        USDA_FOUNDATION_FOOD,
        foodNutrients=[
            n for n in USDA_FOUNDATION_FOOD["foodNutrients"] if n["nutrientId"] != 1003
        ],
    )
    assert usda_client._parse_food(senza_proteine) is None


def test_carboidrati_negativi_azzerati():
    """USDA calcola i carboidrati "per differenza": il rumore di misura può
    dare valori sotto zero (es. -0,4 g per il pollo con pelle). Lasciarli
    passare significherebbe sottrarre carboidrati dal totale giornaliero."""
    con_negativi = dict(
        USDA_FOUNDATION_FOOD,
        foodNutrients=[
            {"nutrientId": 1003, "value": 21.4},
            {"nutrientId": 1004, "value": 4.8},
            {"nutrientId": 1005, "value": -0.4},
            {"nutrientId": 2047, "value": 127},
        ],
    )
    assert usda_client._parse_food(con_negativi).carbs_100g == 0.0


def test_struttura_nutrienti_annidata_del_dettaglio():
    """L'endpoint di dettaglio annida l'id in `nutrient.id` e il valore in
    `amount`, invece di `nutrientId`/`value` come nella ricerca."""
    dettaglio = {
        "fdcId": 1,
        "description": "Test",
        "dataType": "Foundation",
        "foodNutrients": [
            {"nutrient": {"id": 1003}, "amount": 10.0},
            {"nutrient": {"id": 1004}, "amount": 2.0},
            {"nutrient": {"id": 1005}, "amount": 5.0},
            {"nutrient": {"id": 2047}, "amount": 80.0},
        ],
    }
    food = usda_client._parse_food(dettaglio)
    assert food.protein_100g == pytest.approx(10.0)
    assert food.kcal_100g == pytest.approx(80.0)


# --- Cache locale -----------------------------------------------------------


def _raw_exercise(wger_id: int, name: str, muscles: list[str]) -> RawExercise:
    return RawExercise(
        wger_id=wger_id,
        name=name,
        category="Legs",
        primary_muscles=muscles,
        secondary_muscles=["Glutes"] if muscles else [],
        equipment=["Barbell"],
        description="descrizione",
        image_url=None,
    )


def test_sync_scarta_esercizi_senza_gruppo_muscolare(db, monkeypatch):
    """Il 16% del catalogo wger non ha muscolo primario: senza quel dato un
    esercizio non serve a costruire una scheda mirata."""
    monkeypatch.setattr(
        wger_client,
        "fetch_exercises",
        lambda **_: [
            _raw_exercise(1, "Squat", ["Quads"]),
            _raw_exercise(2, "Axe Hold", []),
        ],
    )

    result = catalog_sync.sync_exercises(db)

    assert result.fetched == 2
    assert result.created == 1
    assert result.skipped_no_muscle == 1
    assert db.scalar(select(Exercise).where(Exercise.wger_id == 2)) is None


def test_sync_e_idempotente(db, monkeypatch):
    """Rieseguire il sync deve aggiornare, non duplicare."""
    monkeypatch.setattr(
        wger_client, "fetch_exercises", lambda **_: [_raw_exercise(1, "Squat", ["Quads"])]
    )
    catalog_sync.sync_exercises(db)

    monkeypatch.setattr(
        wger_client,
        "fetch_exercises",
        lambda **_: [_raw_exercise(1, "Squat con bilanciere", ["Quads"])],
    )
    result = catalog_sync.sync_exercises(db)

    assert result.created == 0 and result.updated == 1
    exercises = list(db.scalars(select(Exercise)))
    assert len(exercises) == 1
    assert exercises[0].name == "Squat con bilanciere"


def test_upsert_ingrediente_include_la_marca_nel_nome(db):
    raw = wger_client._parse_ingredient(WGER_INGREDIENT)
    ing = catalog_sync.upsert_wger_ingredient(db, raw)

    assert ing.name == "chicken (Tewco)"
    assert ing.source == IngredientSource.WGER
    assert ing.protein_100g == pytest.approx(26.7)


def test_upsert_ingrediente_non_duplica(db):
    raw = wger_client._parse_ingredient(WGER_INGREDIENT)
    catalog_sync.upsert_wger_ingredient(db, raw)

    aggiornato = RawIngredient(**{**raw.__dict__, "protein_100g": 30.0})
    catalog_sync.upsert_wger_ingredient(db, aggiornato)

    righe = list(db.scalars(select(Ingredient)))
    assert len(righe) == 1
    assert righe[0].protein_100g == pytest.approx(30.0)


def test_stesso_alimento_da_fonti_diverse_resta_separato(db):
    """Un prodotto di marca (wger) e un alimento generico (USDA) con lo stesso
    nome sono voci distinte: hanno valori nutrizionali diversi e servono a
    scopi diversi."""
    catalog_sync.upsert_wger_ingredient(db, wger_client._parse_ingredient(WGER_INGREDIENT))
    catalog_sync.upsert_usda_food(db, usda_client._parse_food(USDA_FOUNDATION_FOOD))

    fonti = {i.source for i in db.scalars(select(Ingredient))}
    assert fonti == {IngredientSource.WGER, IngredientSource.USDA}
