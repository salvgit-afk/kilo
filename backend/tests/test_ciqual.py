"""CIQUAL: i dati caricati, la ricerca per parole, la fonte nei risultati."""

from __future__ import annotations

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Ingredient, IngredientSource
from app.services import ciqual, food_diary


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessione = sessionmaker(bind=engine)()
    yield sessione
    sessione.close()


def test_il_file_ha_gli_alimenti_con_i_macro():
    voci = ciqual.records()
    assert len(voci) > 3000
    assert all(v["kcal"] is not None and v["protein"] is not None for v in voci)
    assert len({v["id"] for v in voci}) == len(voci)


def test_sync_idempotente(db):
    assert ciqual.sync(db) == len(ciqual.records())
    assert ciqual.sync(db) == 0
    assert db.query(Ingredient).filter_by(source=IngredientSource.CIQUAL).count() == len(ciqual.records())


def test_ricerca_con_tutte_le_parole_e_ripiego(db):
    ciqual.sync(db)
    nomi = [i.name for i in ciqual.search(db, "yogurt greek")]
    assert nomi and all("yogurt" in n.lower() and "greek" in n.lower() for n in nomi)
    # "crudo" non è inglese: si riprova senza, e il prosciutto si trova lo stesso.
    assert any("ham" in i.name.lower() for i in ciqual.search(db, "ham crudo"))
    assert ciqual.search(db, "") == []


def test_generico_ciqual_etichettato(db):
    ciqual.sync(db)
    ing = ciqual.search(db, "parmesan")[0]
    assert food_diary.source_label(ing) == "generico (CIQUAL, Anses)"
    risultato = food_diary.FoodSearchResult(
        ingredient=ing, kcal_100g=ing.kcal_100g, protein_100g=ing.protein_100g,
        carbs_100g=ing.carbs_100g, fat_100g=ing.fat_100g, source_label="",
    )
    assert risultato.is_generic
