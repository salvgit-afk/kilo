"""Foto di etichette e piatti: cosa si accetta, cosa si dichiara stimato.

Nessuna chiamata di rete: la lettura del modello è sostituita. Quello che si
verifica è il contorno, che è la parte che protegge l'utente: formati,
dimensioni, valori implausibili, stime dichiarate come tali.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import Ingredient
from app.services import food_photo, rate_limit, recipe_analyzer

PASSWORD = "passwordlunga1"
FOTO = b"\xff\xd8\xff\xe0" + b"0" * 2048  # byte qualsiasi: non viene mai decodificata


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    def _db():
        yield db

    monkeypatch.setattr(get_settings(), "secret_key", "chiave-di-test-" + "x" * 40)
    for finestra in (rate_limit.LOGIN_PER_IP, rate_limit.LOGIN_FAILURES_PER_EMAIL, rate_limit.REGISTER_PER_IP):
        finestra.reset()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db, monkeypatch
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _account(client):
    r = client.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    p = client.post("/profile", headers=h, json={
        "display_name": "x", "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    })
    return h, p.json()["id"]


def _invia(client, h, pid, percorso, *, nome="foto.jpg", tipo="image/jpeg", dati=FOTO):
    return client.post(
        f"/nutrition/diary/photo/{percorso}?profile_id={pid}",
        headers=h,
        files={"photo": (nome, io.BytesIO(dati), tipo)},
    )


def _risposta(monkeypatch, dati: dict):
    monkeypatch.setattr(food_photo, "_ask", lambda *a, **k: dati)


# --- Etichetta ---------------------------------------------------------------


ETICHETTA = {
    "nome": "Fiocchi d'avena", "marca": "Marca", "valori_per": "100g", "leggibile": True,
    "kcal": 370, "proteine_g": 13, "carboidrati_g": 60, "grassi_g": 7, "fibre_g": 10,
}


def test_etichetta_letta(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    _risposta(monkeypatch, ETICHETTA)
    r = _invia(client, h, pid, "label")
    assert r.status_code == 200
    dati = r.json()
    assert dati["name"] == "Fiocchi d'avena" and dati["kcal_100g"] == 370
    assert dati["warnings"] == []


def test_valori_per_porzione_segnalati(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    _risposta(monkeypatch, {**ETICHETTA, "valori_per": "porzione", "porzione_g": 40})
    dati = _invia(client, h, pid, "label").json()
    assert dati["per_serving"] is True
    assert any("porzione" in a for a in dati["warnings"])


def test_valori_che_non_tornano_segnalati(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    # 13 p + 60 c + 7 g fanno circa 355 kcal, non 900: la regola 4-4-9 lo vede.
    _risposta(monkeypatch, {**ETICHETTA, "kcal": 900})
    dati = _invia(client, h, pid, "label").json()
    assert any("non tornano" in a for a in dati["warnings"])


def test_foto_senza_tabella_rifiutata(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    _risposta(monkeypatch, {"nome": "", "leggibile": False, "valori_per": "sconosciuto"})
    r = _invia(client, h, pid, "label")
    assert r.status_code == 422 and "codice a barre" in r.json()["detail"]


def test_pdf_rifiutato_senza_chiamare_il_modello(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)

    def mai(*_a, **_k):
        raise AssertionError("il modello non deve essere chiamato")

    monkeypatch.setattr(food_photo, "_ask", mai)
    r = _invia(client, h, pid, "label", nome="documento.pdf", tipo="application/pdf")
    assert r.status_code == 422 and "Formato" in r.json()["detail"]


def test_foto_troppo_grande_rifiutata(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    monkeypatch.setattr(food_photo, "_ask", lambda *a, **k: ETICHETTA)
    grande = b"x" * (food_photo.MAX_IMAGE_BYTES + 10)
    r = _invia(client, h, pid, "label", dati=grande)
    assert r.status_code == 422 and "troppo grande" in r.json()["detail"]


# --- Piatto ------------------------------------------------------------------


PIATTO = {
    "nome": "Pollo con riso",
    "porzioni": 1,
    "ingredienti": [
        {"nome": "petto di pollo", "nome_en": "chicken breast", "quantita": "150 g", "sicurezza": "alta"},
        {"nome": "riso bianco", "nome_en": "white rice", "quantita": "200 g", "sicurezza": "bassa"},
    ],
}


@pytest.fixture
def catalogo(ambiente):
    _, db, _ = ambiente
    db.add_all([
        Ingredient(name="chicken breast", kcal_100g=165, protein_100g=31,
                   carbs_100g=0, fat_100g=3.6, source="usda"),
        Ingredient(name="white rice", kcal_100g=130, protein_100g=2.7,
                   carbs_100g=28, fat_100g=0.3, source="usda"),
    ])
    db.commit()


def test_piatto_riconosciuto_con_quantita_stimate(ambiente, catalogo):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    _risposta(monkeypatch, PIATTO)
    monkeypatch.setattr(recipe_analyzer, "_convert_with_llm", lambda pending, **_: {})
    r = _invia(client, h, pid, "meal")
    assert r.status_code == 200
    dati = r.json()
    assert dati["servings"] == 1 and len(dati["items"]) == 2
    # Dalla foto nessuno ha pesato niente: ogni riga è una stima.
    assert all(i["estimated"] for i in dati["items"])
    assert "stimate dalla foto" in dati["warnings"][0]
    assert any("riso bianco" in a for a in dati["warnings"])  # riconoscimento incerto


def test_foto_senza_cibo_rifiutata(ambiente):
    client, _, monkeypatch = ambiente
    h, pid = _account(client)
    _risposta(monkeypatch, {"nome": "Pasto", "porzioni": 1, "ingredienti": []})
    r = _invia(client, h, pid, "meal")
    assert r.status_code == 422 and "non riconosco cibo" in r.json()["detail"].lower()


def test_foto_di_un_altro_profilo_non_accessibile(ambiente, catalogo):
    client, _, monkeypatch = ambiente
    h, _ = _account(client)
    altro = client.post("/auth/register", json={"email": "b@example.com", "password": PASSWORD})
    h2 = {"Authorization": f"Bearer {altro.json()['token']}"}
    p2 = client.post("/profile", headers=h2, json={
        "display_name": "y", "birth_date": "1994-03-01", "sex": "female", "height_cm": 165,
        "weight_kg": 60, "goal": "fat_loss", "training_days_per_week": 3,
    }).json()["id"]
    _risposta(monkeypatch, PIATTO)
    assert _invia(client, h, p2, "meal").status_code == 404


def test_quota_giornaliera_delle_foto(ambiente):
    client, db, monkeypatch = ambiente
    h, pid = _account(client)
    _risposta(monkeypatch, ETICHETTA)
    monkeypatch.setitem(rate_limit.DAILY_LIMITS, "photo_scan", 2)
    assert _invia(client, h, pid, "label").status_code == 200
    assert _invia(client, h, pid, "label").status_code == 200
    r = _invia(client, h, pid, "label")
    assert r.status_code == 429 and r.headers["Retry-After"]
