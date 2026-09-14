"""Test delle formule codificate nei modelli.

Questi valori non sono arbitrari: vengono dai file in `app/knowledge_base/`.
Se un test qui fallisce dopo una modifica, la domanda giusta è "ho cambiato
la formula per sbaglio?" — un errore qui produrrebbe schede e piani
alimentari sbagliati senza alcun segnale visibile all'utente.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import (
    ActivityLevel,
    Ingredient,
    Recipe,
    RecipeIngredient,
    ScreeningRecord,
    SessionSet,
    Sex,
    UserProfile,
)


def _profile(**overrides) -> UserProfile:
    """Profilo di riferimento: uomo di 30 anni, 80 kg, 180 cm."""
    defaults = dict(
        display_name="test",
        birth_date=dt.date(dt.date.today().year - 30, 1, 1),
        sex=Sex.MALE,
        height_cm=180.0,
        weight_kg=80.0,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


# --- Mifflin-St Jeor (calorie_and_1rm_formulas.md) --------------------------


def test_bmr_uomo():
    # 10*80 + 6.25*180 - 5*30 + 5
    assert _profile().bmr == pytest.approx(1780.0)


def test_bmr_donna_differisce_di_166_kcal():
    """Le due varianti della formula differiscono solo per la costante
    (+5 uomini, -161 donne): a parità di taglia lo scarto è sempre 166."""
    uomo = _profile().bmr
    donna = _profile(sex=Sex.FEMALE).bmr
    assert uomo - donna == pytest.approx(166.0)


@pytest.mark.parametrize(
    "level,factor",
    [
        (ActivityLevel.SEDENTARY, 1.2),
        (ActivityLevel.LIGHTLY_ACTIVE, 1.375),
        (ActivityLevel.MODERATELY_ACTIVE, 1.55),
        (ActivityLevel.VERY_ACTIVE, 1.725),
        (ActivityLevel.EXTREMELY_ACTIVE, 1.9),
    ],
)
def test_tdee_usa_il_moltiplicatore_corretto(level, factor):
    p = _profile(activity_level=level)
    assert p.tdee == pytest.approx(round(p.bmr * factor, 1))


def test_eta_non_conta_il_compleanno_non_ancora_arrivato():
    domani = dt.date.today() + dt.timedelta(days=1)
    p = _profile(birth_date=dt.date(domani.year - 30, domani.month, domani.day))
    assert p.age == 29


# --- Epley (calorie_and_1rm_formulas.md) ------------------------------------


def test_stima_1rm_epley():
    # 100 kg x 5 ripetizioni -> 100 * (1 + 5/30)
    assert SessionSet(set_number=1, reps=5, weight_kg=100.0).estimated_1rm == pytest.approx(116.7)


def test_stima_1rm_con_una_ripetizione_e_il_carico_stesso():
    """Con 1 ripetizione la stima deve avvicinarsi al carico sollevato."""
    assert SessionSet(set_number=1, reps=1, weight_kg=100.0).estimated_1rm == pytest.approx(103.3)


# --- Gate di sicurezza (screening_and_red_flags.md) -------------------------


def test_screening_senza_si_non_richiede_valutazione_medica():
    assert ScreeningRecord().requires_medical_clearance is False


@pytest.mark.parametrize(
    "campo",
    [
        "heart_condition",
        "chest_pain",
        "dizziness_loss_consciousness",
        "chronic_condition",
        "blood_pressure_heart_medication",
        "bone_joint_problem",
        "pregnant_or_postpartum",
        "eating_disorder_history",
    ],
)
def test_un_solo_si_attiva_il_gate(campo):
    """Basta una risposta affermativa: il gate non pesa le domande fra loro."""
    assert ScreeningRecord(**{campo: True}).requires_medical_clearance is True


# --- Macro delle ricette calcolati, non dichiarati ---------------------------


def _ingrediente(nome: str, kcal: float, prot: float, carb: float, fat: float) -> Ingredient:
    return Ingredient(
        source="manual",
        name=nome,
        kcal_100g=kcal,
        protein_100g=prot,
        carbs_100g=carb,
        fat_100g=fat,
    )


def test_macro_ricetta_sommati_dagli_ingredienti():
    """200 g di petto di pollo + 100 g di riso, una porzione."""
    pollo = _ingrediente("Petto di pollo", 165, 31, 0, 3.6)
    riso = _ingrediente("Riso bianco cotto", 130, 2.7, 28, 0.3)

    r = Recipe(name="Pollo e riso", servings=1)
    r.ingredients = [
        RecipeIngredient(ingredient=pollo, quantity_g=200),
        RecipeIngredient(ingredient=riso, quantity_g=100),
    ]

    assert r.kcal_per_serving == pytest.approx(165 * 2 + 130)
    assert r.protein_per_serving == pytest.approx(31 * 2 + 2.7)
    assert r.carbs_per_serving == pytest.approx(28.0)
    assert r.fat_per_serving == pytest.approx(3.6 * 2 + 0.3)


def test_macro_divisi_per_le_porzioni():
    pollo = _ingrediente("Petto di pollo", 165, 31, 0, 3.6)
    r = Recipe(name="Doppia porzione", servings=2)
    r.ingredients = [RecipeIngredient(ingredient=pollo, quantity_g=200)]

    assert r.protein_per_serving == pytest.approx(31.0)  # 62 g totali / 2


def test_macro_mancante_non_rompe_il_calcolo():
    """Open Food Facts ha spesso campi vuoti (zuccheri, fibra): il totale
    deve restare calcolabile invece di sollevare un errore."""
    ing = _ingrediente("Senza dati zuccheri", 100, 10, 10, 1)
    r = Recipe(name="Test", servings=1)
    r.ingredients = [RecipeIngredient(ingredient=ing, quantity_g=100)]

    assert r.sugars_per_serving == pytest.approx(0.0)
    assert r.kcal_per_serving == pytest.approx(100.0)
