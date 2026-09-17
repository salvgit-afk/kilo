"""Codice a barre: lettura da Open Food Facts, cache e prodotti inseriti a mano."""

from __future__ import annotations

import pytest

from app.models import Ingredient, IngredientSource, User
from app.services import food_diary, off_client

NUTELLA = {
    "code": "3017620422003",
    "status": 1,
    "product": {
        "product_name": "Nutella",
        "brands": "Nutella, Ferrero",
        "quantity": "400 g e",
        "nutriments": {
            "energy-kcal_100g": 539, "proteins_100g": 6.3, "carbohydrates_100g": 57.5,
            "fat_100g": 30.9, "sugars_100g": 56.3, "fiber_100g": 0, "saturated-fat_100g": 10.6,
        },
    },
}


# --- Interpretazione della risposta -------------------------------------------------


def test_prodotto_letto_con_valori_per_100g():
    p = off_client.parse_product("3017620422003", NUTELLA)
    assert (p.kcal_100g, p.protein_100g, p.carbs_100g, p.fat_100g) == (539, 6.3, 57.5, 30.9)
    assert p.name == "Nutella (400 g)"  # la marca coincide col nome: non si ripete


def test_codice_sconosciuto_con_http_200_e_status_0():
    """Il caso da non confondere con un prodotto valido ma vuoto."""
    with pytest.raises(off_client.ProductNotFound):
        off_client.parse_product("8002580005059", {"code": "8002580005059", "status": 0, "status_verbose": "product not found"})


def test_valori_mancanti_non_diventano_zeri():
    dati = {"status": 1, "product": {"product_name": "Kefir", "nutriments": {"energy-kcal_100g": 60}}}
    with pytest.raises(off_client.IncompleteProduct) as e:
        off_client.parse_product("12345678", dati)
    assert "proteine" in str(e.value) and e.value.name == "Kefir"


def test_calorie_ricavate_dai_kilojoule():
    dati = {"status": 1, "product": {"product_name": "Kefir magro", "brands": "Latteria", "nutriments": {
        "energy_100g": 184, "proteins_100g": 3.5, "carbohydrates_100g": 4, "fat_100g": 0.5}}}
    p = off_client.parse_product("12345678", dati)
    assert p.kcal_100g == 44.0
    assert p.name == "Kefir magro · Latteria"


@pytest.mark.parametrize("grezzo,atteso", [("3017620422003", "3017620422003"), (" 8 002580-005059 ", "8002580005059")])
def test_codice_normalizzato(grezzo, atteso):
    assert off_client.normalize_barcode(grezzo) == atteso


@pytest.mark.parametrize("grezzo", ["123", "abc", "123456789012345"])
def test_codice_non_valido(grezzo):
    with pytest.raises(ValueError):
        off_client.normalize_barcode(grezzo)


# --- Cache e prodotti manuali ----------------------------------------------------------


@pytest.fixture
def utenti(db):
    a = User(email="a@example.com", password_hash="x")
    b = User(email="b@example.com", password_hash="x")
    db.add_all([a, b])
    db.commit()
    return a, b


def test_seconda_scansione_dalla_cache(db, utenti, monkeypatch):
    chiamate = []

    def finto(codice):
        chiamate.append(codice)
        return off_client.parse_product(codice, NUTELLA)

    monkeypatch.setattr(off_client, "get_product", finto)
    prima = food_diary.lookup_barcode(db, "3017620422003", user_id=utenti[0].id)
    seconda = food_diary.lookup_barcode(db, "3017620422003", user_id=utenti[1].id)

    assert prima.cached is False and seconda.cached is True
    assert prima.ingredient.id == seconda.ingredient.id
    assert prima.ingredient.source == IngredientSource.OFF
    assert chiamate == ["3017620422003"]


def test_codice_sconosciuto_non_salvato(db, utenti, monkeypatch):
    def finto(codice):
        raise off_client.ProductNotFound("no")

    monkeypatch.setattr(off_client, "get_product", finto)
    with pytest.raises(off_client.ProductNotFound):
        food_diary.lookup_barcode(db, "8002580005059", user_id=utenti[0].id)
    assert db.query(Ingredient).count() == 0


def test_prodotto_manuale_visibile_solo_a_chi_lo_inserisce(db, utenti, monkeypatch):
    a, b = utenti
    food_diary.create_manual_product(
        db, user_id=a.id, name="Kefir magro Latteria X", barcode="8002580005059",
        kcal_100g=44, protein_100g=3.5, carbs_100g=4, fat_100g=0.5,
    )
    assert food_diary.lookup_barcode(db, "8002580005059", user_id=a.id).ingredient.name == "Kefir magro Latteria X"

    def non_trovato(codice):
        raise off_client.ProductNotFound("no")

    monkeypatch.setattr(off_client, "get_product", non_trovato)
    with pytest.raises(off_client.ProductNotFound):
        food_diary.lookup_barcode(db, "8002580005059", user_id=b.id)


def test_macro_manuali_impossibili_rifiutati(db, utenti):
    with pytest.raises(ValueError):
        food_diary.create_manual_product(
            db, user_id=utenti[0].id, name="Sbagliato", kcal_100g=500,
            protein_100g=60, carbs_100g=60, fat_100g=10,
        )
