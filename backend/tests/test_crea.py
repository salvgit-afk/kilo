"""CREA: i dati letti dal sito, la ricerca in italiano, nome e porzione."""

from __future__ import annotations

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Ingredient, IngredientSource
from app.services import crea, food_diary, translation


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessione = sessionmaker(bind=engine)()
    yield sessione
    sessione.close()


def test_il_file_ha_gli_alimenti_con_i_macro():
    voci = crea.records()
    assert len(voci) > 700
    assert all(v["kcal"] is not None and v["protein"] is not None and v["fat"] is not None for v in voci)
    assert len({v["id"] for v in voci}) == len(voci)
    assert sum(1 for v in voci if v.get("portion_g")) > len(voci) / 2


def test_sync_idempotente(db):
    assert crea.sync(db) == len(crea.records())
    assert crea.sync(db) == 0


def test_ricerca_in_italiano_senza_traduzione(db):
    crea.sync(db)
    nomi = [i.name.lower() for i in crea.search(db, "prosciutto crudo")]
    assert nomi and all("prosciutto" in n and "crudo" in n for n in nomi)
    # Singolare e plurale, con e senza accenti.
    assert crea.search(db, "uova") and crea.search(db, "mele")
    assert crea.search(db, "") == []


def test_nome_italiano_senza_llm_e_porzione(db):
    crea.sync(db)
    ing = crea.search(db, "farro")[0]
    assert translation.cached_food_names(db, [ing.id]) == {ing.id: ing.name}
    assert food_diary.source_label(ing) == "generico (CREA)"
    assert db.query(Ingredient).filter_by(source=IngredientSource.CREA).filter(Ingredient.portion_g.isnot(None)).count() > 0
