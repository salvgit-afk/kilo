"""Importazione di una ricetta incollata e travaso nel diario.

Il modello non viene mai chiamato davvero: si sostituisce la sua risposta,
perché quello che va verificato non è come legge il testo ma che i numeri
arrivino dal catalogo alimenti e non da lui.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import Ingredient, IngredientSource
from app.services import recipe_analyzer, recipe_import

PASSWORD = "passwordlunga1"

TESTO = """Porridge proteico
Per 2 persone
- 80 g di fiocchi d'avena
- 300 g di albume
- 1 cucchiaio di burro d'arachidi
Mescola tutto e cuoci 5 minuti."""

RISPOSTA_MODELLO = {
    "nome": "Porridge proteico",
    "porzioni": 2,
    "preparazione": "Mescola tutto e cuoci 5 minuti.",
    "ingredienti": [
        {"nome": "fiocchi d'avena", "nome_en": "oats", "quantita": "80 g"},
        {"nome": "albume", "nome_en": "egg white", "quantita": "300 g"},
        {"nome": "burro d'arachidi", "nome_en": "peanut butter", "quantita": "1 cucchiaio"},
    ],
}

# kcal, proteine, carboidrati, grassi per 100 g
CATALOGO = {
    "oats": ("Oats, raw", 389, 16.9, 66.3, 6.9),
    "egg white": ("Egg, white, raw", 52, 10.9, 0.7, 0.2),
    "peanut butter": ("Peanut butter, smooth", 588, 22.5, 22.3, 50.4),
}


@pytest.fixture
def catalogo(db, monkeypatch):
    """Il catalogo alimenti locale, senza chiamate a USDA."""
    per_nome: dict[str, Ingredient] = {}
    for chiave, (nome, kcal, pro, carb, gra) in CATALOGO.items():
        ing = Ingredient(
            name=nome, source=IngredientSource.USDA, kcal_100g=kcal,
            protein_100g=pro, carbs_100g=carb, fat_100g=gra, fiber_100g=0.0,
        )
        db.add(ing)
        per_nome[chiave] = ing
    db.commit()

    monkeypatch.setattr(
        recipe_analyzer, "_match_ingredient", lambda _db, nome: per_nome.get(nome.lower())
    )
    return per_nome


@pytest.fixture
def modello(monkeypatch):
    """Risposta del modello alla lettura del testo, e conversione in grammi."""
    monkeypatch.setattr(recipe_import, "_parse_text", lambda _testo: RISPOSTA_MODELLO)
    # "1 cucchiaio" non ha un'unità diretta: normalmente lo converte il modello.
    monkeypatch.setattr(recipe_analyzer, "_convert_with_llm", lambda pending, **_: {2: 16.0})


# --- Lettura del testo -----------------------------------------------------------------


def test_ricetta_letta_con_macro_dal_catalogo(db, catalogo, modello):
    r = recipe_import.import_from_text(db, TESTO)

    assert r.name == "Porridge proteico"
    assert r.servings == 2
    assert [i.name for i in r.ingredients] == ["fiocchi d'avena", "albume", "burro d'arachidi"]
    # I grammi delle quantità già esplicite non passano dal modello.
    assert [i.grams for i in r.ingredients] == [80.0, 300.0, 16.0]
    assert all(i.resolved for i in r.ingredients)
    assert not r.warnings

    avena = r.ingredients[0]
    assert avena.matched_name == "Oats, raw"
    assert avena.protein_100g == 16.9


def test_grammi_stimati_segnati_come_tali(db, catalogo, modello):
    r = recipe_import.import_from_text(db, TESTO)
    # "80 g" e "300 g" vengono dal testo, "1 cucchiaio" dalla stima.
    assert [i.estimated for i in r.ingredients] == [False, False, True]
    # Una misura casalinga non è una dose mancante: nessun avviso.
    assert not r.warnings


def test_dosi_mancanti_stimate_con_avviso(db, catalogo, monkeypatch):
    """Il caso dei tacos: nessuna quantità nel testo."""
    senza = {**RISPOSTA_MODELLO, "porzioni": 1, "ingredienti": [
        {**v, "quantita": ""} for v in RISPOSTA_MODELLO["ingredienti"]
    ]}
    monkeypatch.setattr(recipe_import, "_parse_text", lambda _t: senza)
    ricevute = {}

    def stima(pending, servings=4):
        ricevute["porzioni"] = servings
        return {i: 50.0 for i, _ in pending}

    monkeypatch.setattr(recipe_analyzer, "_convert_with_llm", stima)
    r = recipe_import.import_from_text(db, TESTO)

    assert ricevute["porzioni"] == 1  # la stima sa per quante persone è
    assert all(i.estimated for i in r.ingredients)
    assert "LARN" in r.warnings[0] and "1 persona" in r.warnings[0]


def test_ingrediente_non_trovato_dichiarato_non_inventato(db, catalogo, modello, monkeypatch):
    monkeypatch.setattr(
        recipe_import,
        "_parse_text",
        lambda _t: {**RISPOSTA_MODELLO, "ingredienti": RISPOSTA_MODELLO["ingredienti"]
                    + [{"nome": "polvere di stelle", "nome_en": "star dust", "quantita": "10 g"}]},
    )
    r = recipe_import.import_from_text(db, TESTO)

    ultimo = r.ingredients[-1]
    assert ultimo.ingredient_id is None
    assert ultimo.kcal_100g is None  # non si riempie con zeri: il dato manca
    assert r.unresolved == ["polvere di stelle"]
    assert "polvere di stelle" in r.warnings[0]


def test_testo_senza_ingredienti_rifiutato(db, monkeypatch):
    monkeypatch.setattr(
        recipe_import, "_parse_text", lambda _t: {"nome": "", "porzioni": 1, "ingredienti": []}
    )
    with pytest.raises(recipe_import.RecipeImportError):
        recipe_import.import_from_text(db, "Oggi ho corso dieci chilometri sotto la pioggia.")


def test_testo_troppo_corto_non_arriva_al_modello(db, monkeypatch):
    def mai(_t):
        raise AssertionError("il modello non va chiamato")

    monkeypatch.setattr(recipe_import, "_parse_text", mai)
    with pytest.raises(recipe_import.RecipeImportError):
        recipe_import.import_from_text(db, "pasta")


def test_stesso_testo_stesso_identificativo():
    """La cache delle conversioni si appoggia a questo: deve essere stabile."""
    assert recipe_import._draft_id("ciao") == recipe_import._draft_id("ciao")
    assert recipe_import._draft_id("ciao") != recipe_import._draft_id("ciao!")


def test_porzioni_assurde_riportate_nei_limiti(db, catalogo, modello, monkeypatch):
    monkeypatch.setattr(
        recipe_import, "_parse_text", lambda _t: {**RISPOSTA_MODELLO, "porzioni": 9999}
    )
    assert recipe_import.import_from_text(db, TESTO).servings == recipe_import.MAX_SERVINGS


# --- Dal piatto al diario ---------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Sessione = sessionmaker(bind=engine)
    sessione = Sessione()

    def _db():
        yield sessione

    monkeypatch.setattr(get_settings(), "secret_key", "chiave-di-test-" + "x" * 40)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), sessione
    app.dependency_overrides.clear()
    sessione.close()
    engine.dispose()


def _account(client) -> tuple[dict, int]:
    r = client.post("/auth/register", json={"email": "cuoco@example.com", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    p = client.post("/profile", headers=headers, json={
        "display_name": "Cuoco", "birth_date": "1994-03-01", "sex": "male",
        "height_cm": 178, "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    })
    return headers, p.json()["id"]


def _ingrediente(db, nome: str) -> int:
    dati = CATALOGO[nome]
    ing = Ingredient(
        name=dati[0], source=IngredientSource.USDA, kcal_100g=dati[1],
        protein_100g=dati[2], carbs_100g=dati[3], fat_100g=dati[4], fiber_100g=0.0,
    )
    db.add(ing)
    db.commit()
    return ing.id


def test_ricetta_versata_nel_diario_in_una_volta(client):
    cl, db = client
    headers, pid = _account(cl)
    avena, albume = _ingrediente(db, "oats"), _ingrediente(db, "egg white")

    r = cl.post(f"/nutrition/diary/recipe?profile_id={pid}", headers=headers, json={
        "items": [
            {"name": "fiocchi d'avena", "grams": 80, "ingredient_id": avena},
            {"name": "albume", "grams": 300, "ingredient_id": albume},
        ],
        "meal_type": "breakfast",
        "servings": 2,
        "eaten_servings": 1,
    })
    assert r.status_code == 201, r.text
    voci = r.json()
    # Ricetta per 2, mangiata 1 porzione: metà delle quantità.
    assert [v["quantity_g"] for v in voci] == [40.0, 150.0]
    assert voci[0]["kcal"] == pytest.approx(389 * 0.4, rel=0.01)


def test_ingredienti_senza_catalogo_saltati_non_stimati(client):
    cl, db = client
    headers, pid = _account(cl)
    avena = _ingrediente(db, "oats")

    r = cl.post(f"/nutrition/diary/recipe?profile_id={pid}", headers=headers, json={
        "items": [
            {"name": "fiocchi d'avena", "grams": 80, "ingredient_id": avena},
            {"name": "polvere di stelle", "grams": 10, "ingredient_id": None},
            {"name": "sale", "grams": 0.4, "ingredient_id": avena},  # sotto il grammo
        ],
    })
    assert r.status_code == 201, r.text
    assert len(r.json()) == 1


def test_ricetta_tutta_da_abbinare_rifiutata(client):
    cl, _ = client
    headers, pid = _account(cl)
    r = cl.post(f"/nutrition/diary/recipe?profile_id={pid}", headers=headers, json={
        "items": [{"name": "polvere di stelle", "grams": 10, "ingredient_id": None}],
    })
    assert r.status_code == 422


def test_diario_di_un_altro_profilo_non_accessibile(client):
    cl, db = client
    headers, _ = _account(cl)
    avena = _ingrediente(db, "oats")
    r = cl.post("/nutrition/diary/recipe?profile_id=999", headers=headers, json={
        "items": [{"name": "avena", "grams": 80, "ingredient_id": avena}],
    })
    assert r.status_code == 404
