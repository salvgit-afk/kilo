"""Test del diario alimentare (la via precisa del conteggio).

A differenza dei suggerimenti di ricette, qui non c'è nulla da stimare:
l'utente sceglie l'alimento e ne indica i grammi. I test verificano che il
conteggio resti corretto e, soprattutto, che **non cambi da solo** nel tempo.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models import (
    ActivityLevel,
    ExperienceLevel,
    Goal,
    Ingredient,
    IngredientSource,
    MealItem,
    Sex,
    UserProfile,
)
from app.services import food_diary as fd
from app.services import nutrition_targets as nt


@pytest.fixture
def diario(db, monkeypatch):
    profilo = UserProfile(
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
    pollo = Ingredient(
        source=IngredientSource.USDA, source_id="1",
        name="Chicken, breast, boneless, skinless, raw",
        kcal_100g=106, protein_100g=22.5, carbs_100g=0, fat_100g=1.9, fiber_100g=0,
    )
    riso = Ingredient(
        source=IngredientSource.USDA, source_id="2", name="Rice, white, raw",
        kcal_100g=360, protein_100g=7, carbs_100g=80, fat_100g=1, fiber_100g=1.3,
    )
    marca = Ingredient(
        source=IngredientSource.WGER, source_id="3", name="chicken breast (Marca)",
        kcal_100g=98, protein_100g=22.3, carbs_100g=0, fat_100g=1.5,
    )
    db.add_all([profilo, pollo, riso, marca])
    db.commit()

    def _trova(nome, *ingredienti):
        return [i for i in ingredienti if nome.lower().split()[0] in i.name.lower()]

    monkeypatch.setattr(
        fd, "_usda_and_fallback", lambda _db, nome, _en, **kw: (_trova(nome, pollo, riso), [])
    )
    monkeypatch.setattr(fd, "_italian_products", lambda _db, nome, **kw: _trova(nome, marca))
    return db, profilo, pollo, riso, marca


# --- Ricerca ------------------------------------------------------------------


def test_ricerca_non_sceglie_per_lutente(diario):
    """La lista completa con i valori in vista è ciò che distingue un
    conteggio da una stima: un valore anomalo si riconosce a colpo d'occhio."""
    db, _, _, _, _ = diario
    risultati = fd.search_foods(db, "chicken")

    assert len(risultati) >= 2
    assert all(r.kcal_100g > 0 for r in risultati)


def test_alimenti_generici_prima_dei_prodotti_di_marca(diario):
    """I dati USDA sono curati in laboratorio, quelli di marca inseriti dagli
    utenti: cercando "chicken" per un pasto serve il primo tipo."""
    db, _, _, _, _ = diario
    risultati = fd.search_foods(db, "chicken")
    assert risultati[0].is_generic is True


def test_macro_per_quantita_calcolati_correttamente(diario):
    db, _, pollo, _, _ = diario
    risultato = fd.search_foods(db, "chicken")[0]
    macro = risultato.macros_for(200)

    assert macro["kcal"] == pytest.approx(212)
    assert macro["protein_g"] == pytest.approx(45)


# --- Registrazione dei pasti --------------------------------------------------


def test_alimento_pesato_produce_i_macro_giusti(diario):
    db, profilo, pollo, _, _ = diario
    pasto = fd.get_or_create_meal(db, profilo, meal_type="lunch")
    item = fd.add_food(db, pasto, pollo, grams=200)

    assert item.kcal == pytest.approx(212)
    assert item.protein_g == pytest.approx(45)
    assert item.quantity_g == 200


def test_totale_pasto_somma_gli_alimenti(diario):
    db, profilo, pollo, riso, _ = diario
    pasto = fd.get_or_create_meal(db, profilo)
    fd.add_food(db, pasto, pollo, grams=200)
    fd.add_food(db, pasto, riso, grams=100)

    db.refresh(pasto)
    totali = fd.meal_totals(pasto)
    assert totali.kcal == pytest.approx(212 + 360)
    assert totali.protein_g == pytest.approx(45 + 7)


def test_quantita_non_positiva_rifiutata(diario):
    db, profilo, pollo, _, _ = diario
    pasto = fd.get_or_create_meal(db, profilo)
    with pytest.raises(ValueError):
        fd.add_food(db, pasto, pollo, grams=0)


def test_stesso_pasto_riutilizzato_nella_stessa_giornata(diario):
    db, profilo, _, _, _ = diario
    primo = fd.get_or_create_meal(db, profilo, meal_type="lunch")
    secondo = fd.get_or_create_meal(db, profilo, meal_type="lunch")
    assert primo.id == secondo.id

    cena = fd.get_or_create_meal(db, profilo, meal_type="dinner")
    assert cena.id != primo.id


# --- Il punto che conta: lo storico non deve cambiare da solo ----------------


def test_valori_congelati_al_momento_della_registrazione(diario):
    """Il catalogo viene risincronizzato e i dati di Open Food Facts vengono
    corretti dagli utenti: senza la copia, un pasto di mesi fa cambierebbe i
    propri valori da solo, falsando lo storico e i report."""
    db, profilo, pollo, _, _ = diario
    pasto = fd.get_or_create_meal(db, profilo)
    item = fd.add_food(db, pasto, pollo, grams=100)
    kcal_registrate = item.kcal

    # L'alimento viene aggiornato nel catalogo, come dopo un nuovo sync.
    pollo.kcal_100g = 500
    db.commit()
    db.refresh(item)

    assert item.kcal == pytest.approx(kcal_registrate)


def test_correzione_quantita_non_riprende_i_valori_dal_catalogo(diario):
    """Correggere i grammi deve riscalare ciò che è stato registrato, non
    ricalcolare da un catalogo nel frattempo cambiato."""
    db, profilo, pollo, _, _ = diario
    pasto = fd.get_or_create_meal(db, profilo)
    item = fd.add_food(db, pasto, pollo, grams=100)

    pollo.kcal_100g = 500  # il catalogo cambia
    db.commit()

    fd.update_quantity(db, item, 200)
    assert item.kcal == pytest.approx(212)  # 106 x 2, non 500 x 2


def test_alimento_rimosso_dal_catalogo_lascia_leggibile_lo_storico(diario):
    """Il nome è copiato nella riga: il pasto resta comprensibile anche se
    l'alimento sparisce dal catalogo."""
    db, profilo, pollo, _, _ = diario
    pasto = fd.get_or_create_meal(db, profilo)
    item = fd.add_food(db, pasto, pollo, grams=100)
    nome = item.name

    db.delete(pollo)
    db.commit()
    db.refresh(item)

    assert item.name == nome
    assert item.kcal == pytest.approx(106)
    assert item.ingredient_id is None


def test_rimozione_alimento_dal_pasto(diario):
    db, profilo, pollo, riso, _ = diario
    pasto = fd.get_or_create_meal(db, profilo)
    item = fd.add_food(db, pasto, pollo, grams=100)
    fd.add_food(db, pasto, riso, grams=100)

    fd.remove_food(db, item)
    db.refresh(pasto)
    assert len(pasto.items) == 1


# --- Totali giornalieri e confronto con i target -----------------------------


def test_totale_giornaliero_somma_tutti_i_pasti(diario):
    db, profilo, pollo, riso, _ = diario
    pranzo = fd.get_or_create_meal(db, profilo, meal_type="lunch")
    fd.add_food(db, pranzo, pollo, grams=100)
    cena = fd.get_or_create_meal(db, profilo, meal_type="dinner")
    fd.add_food(db, cena, riso, grams=100)

    totali = fd.daily_totals(db, profilo)
    assert totali.kcal == pytest.approx(106 + 360)


def test_pasto_libero_incluso_nei_totali(diario):
    """Chi non vuole pesare tutto deve poter inserire un pasto a mano senza
    che il totale del giorno diventi sbagliato."""
    db, profilo, pollo, _, _ = diario
    pranzo = fd.get_or_create_meal(db, profilo, meal_type="lunch")
    fd.add_food(db, pranzo, pollo, grams=100)

    libero = fd.get_or_create_meal(db, profilo, meal_type="snack")
    libero.kcal = 300
    libero.protein_g = 20
    db.commit()

    totali = fd.daily_totals(db, profilo)
    assert totali.kcal == pytest.approx(406)
    assert totali.protein_g == pytest.approx(22.5 + 20)


def test_pasti_pianificati_esclusi_dai_totali(diario):
    """Un pasto pianificato ma non ancora consumato non deve contare come
    mangiato."""
    db, profilo, pollo, _, _ = diario
    pianificato = fd.get_or_create_meal(db, profilo, meal_type="dinner")
    fd.add_food(db, pianificato, pollo, grams=100)
    pianificato.is_planned = True
    db.commit()

    assert fd.daily_totals(db, profilo).kcal == pytest.approx(0)


def test_quanto_manca_ai_target(diario):
    db, profilo, pollo, _, _ = diario
    target = nt.compute_targets(profilo)
    pasto = fd.get_or_create_meal(db, profilo)
    fd.add_food(db, pasto, pollo, grams=200)

    manca = fd.daily_totals(db, profilo).remaining_against(target)
    assert manca["kcal"] == pytest.approx(target.target_kcal - 212)
    assert manca["protein_g"] == pytest.approx(target.protein_g - 45)


def test_superamento_del_target_dato_come_valore_negativo(diario):
    """Serve a mostrare di quanto si è sforato, non a fermarsi a zero."""
    db, profilo, pollo, _, _ = diario
    target = nt.compute_targets(profilo)
    pasto = fd.get_or_create_meal(db, profilo)
    fd.add_food(db, pasto, pollo, grams=6000)

    assert fd.daily_totals(db, profilo).remaining_against(target)["kcal"] < 0


def test_progressione_percentuale_sui_target(diario):
    db, profilo, pollo, _, _ = diario
    target = nt.compute_targets(profilo)
    pasto = fd.get_or_create_meal(db, profilo)
    fd.add_food(db, pasto, pollo, grams=100)

    progresso = fd.daily_totals(db, profilo).progress_against(target)
    assert progresso["kcal"] == pytest.approx(106 / target.target_kcal)


def test_giornata_senza_pasti_ha_totali_a_zero(diario):
    db, profilo, _, _, _ = diario
    totali = fd.daily_totals(db, profilo, date=dt.date(2020, 1, 1))
    assert totali.kcal == 0 and totali.protein_g == 0
