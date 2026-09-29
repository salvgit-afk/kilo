"""Pasti previsti, proteine in polvere segnate e "I miei prodotti".

- Nei giorni futuri si aggiunge solo come previsto, fino a 7 giorni avanti;
  oggi lo sceglie l'utente. I previsti non contano in nessun totale finché
  non si confermano, anche nei giorni passati.
- Le proteine in polvere contano nei giorni in cui sono segnate come prese,
  e il diario dice quante sono, per dividerle dal cibo.
- I prodotti con codice a barre restano sempre fra "I miei prodotti".
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import Ingredient, MealLog, SavedFood, SupplementDeclaration, SupplementKind
from app.services import clock, rate_limit

PASSWORD = "passwordlunga1"
OGGI = clock.today()
DOMANI = OGGI + dt.timedelta(days=1)
IERI = OGGI - dt.timedelta(days=1)


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
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    for finestra in (rate_limit.LOGIN_PER_IP, rate_limit.LOGIN_FAILURES_PER_EMAIL, rate_limit.REGISTER_PER_IP):
        finestra.reset()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _account(client, email="a@example.com"):
    r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    p = client.post("/profile", headers=h, json={
        "display_name": "x", "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    })
    return h, p.json()["id"]


def _prodotti(db):
    tonno = Ingredient(
        name="Tonno all'olio", source="off", barcode="8004030000000",
        kcal_100g=192, protein_100g=25, carbs_100g=0, fat_100g=10,
    )
    mela = Ingredient(name="Apple", source="usda", kcal_100g=52, protein_100g=0.3, carbs_100g=14, fat_100g=0.2)
    db.add_all([tonno, mela])
    db.commit()
    return tonno, mela


def _aggiungi(client, h, pid, ing, giorno, grammi=100, pasto="lunch", previsto=False):
    return client.post(
        f"/nutrition/diary/items?profile_id={pid}",
        headers=h,
        json={"ingredient_id": ing.id, "grams": grammi, "meal_type": pasto, "date": str(giorno), "planned": previsto},
    )


def _diario(client, h, pid, giorno):
    r = client.get(f"/nutrition/diary?profile_id={pid}&date={giorno}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# --- Pasti previsti -------------------------------------------------------------


def test_domani_e_sempre_previsto_e_non_conta(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, _ = _prodotti(db)
    r = _aggiungi(client, h, pid, tonno, DOMANI, grammi=80)
    assert r.status_code == 201, r.text

    domani = _diario(client, h, pid, DOMANI)
    assert domani["meals"] == []
    assert domani["totals"]["kcal"] == 0
    assert len(domani["planned_meals"]) == 1
    assert domani["planned_totals"]["kcal"] == pytest.approx(153.6)

    giorni = client.get(
        f"/nutrition/diary/days?profile_id={pid}&start={OGGI}&end={OGGI + dt.timedelta(days=6)}", headers=h
    ).json()["days"]
    assert giorni == [{"date": str(DOMANI), "kcal": 0, "planned_kcal": 153.6}]


def test_oltre_sette_giorni_rifiutato(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, _ = _prodotti(db)
    assert _aggiungi(client, h, pid, tonno, OGGI + dt.timedelta(days=7)).status_code == 201
    r = _aggiungi(client, h, pid, tonno, OGGI + dt.timedelta(days=8))
    assert r.status_code == 422 and "7 giorni" in r.json()["detail"]


def test_oggi_previsto_a_scelta_e_separato_dal_mangiato(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, mela = _prodotti(db)
    _aggiungi(client, h, pid, mela, OGGI, grammi=200, pasto="dinner")
    _aggiungi(client, h, pid, tonno, OGGI, grammi=100, pasto="dinner", previsto=True)

    oggi = _diario(client, h, pid, OGGI)
    assert [len(m["items"]) for m in oggi["meals"]] == [1]
    assert [len(m["items"]) for m in oggi["planned_meals"]] == [1]
    assert oggi["totals"]["kcal"] == pytest.approx(104)


def test_conferma_con_grammi_corretti(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, mela = _prodotti(db)
    _aggiungi(client, h, pid, mela, OGGI, grammi=100, previsto=True)
    voce = _aggiungi(client, h, pid, tonno, OGGI, grammi=100, previsto=True).json()

    r = client.post(f"/nutrition/diary/items/{voce['id']}/confirm?grams=50", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["quantity_g"] == 50

    oggi = _diario(client, h, pid, OGGI)
    assert oggi["totals"]["kcal"] == pytest.approx(96)
    assert [i["name"] for i in oggi["meals"][0]["items"]] == ["Tonno all'olio"]
    # La mela resta prevista.
    assert [i["name"] for i in oggi["planned_meals"][0]["items"]] == ["Apple"]


def test_conferma_tutto_il_pasto_e_il_previsto_sparisce(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, mela = _prodotti(db)
    _aggiungi(client, h, pid, tonno, IERI, previsto=True)
    _aggiungi(client, h, pid, mela, IERI, previsto=True)
    # Un previsto di un giorno passato non conta finché non si conferma.
    ieri = _diario(client, h, pid, IERI)
    assert ieri["totals"]["kcal"] == 0
    pasto = ieri["planned_meals"][0]["id"]

    r = client.post(f"/nutrition/diary/meals/{pasto}/confirm", headers=h)
    assert r.status_code == 200, r.text
    ieri = _diario(client, h, pid, IERI)
    assert ieri["planned_meals"] == []
    assert ieri["totals"]["kcal"] == pytest.approx(244)
    assert db.scalar(select(MealLog).where(MealLog.is_planned.is_(True))) is None


def test_domani_non_si_conferma(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, _ = _prodotti(db)
    voce = _aggiungi(client, h, pid, tonno, DOMANI).json()
    r = client.post(f"/nutrition/diary/items/{voce['id']}/confirm", headers=h)
    assert r.status_code == 422


def test_togliere_l_ultimo_previsto_cancella_il_pasto(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, _ = _prodotti(db)
    voce = _aggiungi(client, h, pid, tonno, DOMANI).json()
    assert client.delete(f"/nutrition/diary/items/{voce['id']}", headers=h).status_code == 204
    assert db.scalar(select(MealLog)) is None


def test_i_previsti_altrui_non_si_confermano(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    h_altro, _ = _account(client, "b@example.com")
    tonno, _ = _prodotti(db)
    voce = _aggiungi(client, h, pid, tonno, OGGI, previsto=True).json()
    assert client.post(f"/nutrition/diary/items/{voce['id']}/confirm", headers=h_altro).status_code == 404


def test_i_previsti_non_finiscono_nei_recenti(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    _, mela = _prodotti(db)
    _aggiungi(client, h, pid, mela, DOMANI)
    assert client.get(f"/nutrition/diary/recent?profile_id={pid}", headers=h).json() == []


# --- Proteine in polvere -------------------------------------------------------------


def test_polvere_conta_solo_se_segnata_e_si_vede_a_parte(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    polvere = SupplementDeclaration(
        profile_id=pid, kind=SupplementKind.PROTEIN_POWDER, protein_g_per_dose=25,
        doses_per_day=1, is_active=True,
    )
    db.add(polvere)
    db.commit()

    oggi = _diario(client, h, pid, OGGI)
    assert oggi["totals"]["protein_g"] == 0 and oggi["powder_protein_g"] == 0
    assert oggi["protein_powders"] == [
        {"supplement_id": polvere.id, "kind": "protein_powder", "product_name": None,
         "protein_g_per_dose": 25, "doses": 0}
    ]

    r = client.put(
        f"/supplements/{polvere.id}/intake?profile_id={pid}&today={OGGI}",
        headers=h, json={"date": str(OGGI), "doses": 1},
    )
    assert r.status_code == 200, r.text
    oggi = _diario(client, h, pid, OGGI)
    assert oggi["powder_protein_g"] == 25
    assert oggi["totals"]["protein_g"] == 25
    assert oggi["totals"]["kcal"] == 100
    assert oggi["protein_powders"][0]["doses"] == 1
    # Ieri non era segnata: niente.
    assert _diario(client, h, pid, IERI)["totals"]["protein_g"] == 0


# --- I miei prodotti ------------------------------------------------------------------


def test_prodotto_scansionato_resta_sempre_fra_i_miei(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, mela = _prodotti(db)
    _aggiungi(client, h, pid, tonno, OGGI, grammi=80)
    _aggiungi(client, h, pid, tonno, IERI, grammi=60)
    _aggiungi(client, h, pid, mela, OGGI, grammi=150)

    miei = client.get(f"/nutrition/diary/saved?profile_id={pid}", headers=h).json()
    # La mela è un generico: entra solo con la stella.
    assert [(m["name"], m["uses"], m["grams"]) for m in miei] == [("Tonno all'olio", 2, 60)]

    recenti = {r["name"]: r["saved"] for r in client.get(f"/nutrition/diary/recent?profile_id={pid}", headers=h).json()}
    assert recenti == {"Tonno all'olio": True, "Apple": False}


def test_stella_aggiunge_e_toglie_e_una_scansione_non_lo_rimette(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    tonno, mela = _prodotti(db)
    assert client.put(f"/nutrition/diary/saved/{mela.id}?profile_id={pid}&grams=150", headers=h).status_code == 204
    _aggiungi(client, h, pid, tonno, OGGI)
    miei = client.get(f"/nutrition/diary/saved?profile_id={pid}", headers=h).json()
    assert {m["name"] for m in miei} == {"Tonno all'olio", "Apple"}

    assert client.delete(f"/nutrition/diary/saved/{tonno.id}?profile_id={pid}", headers=h).status_code == 204
    _aggiungi(client, h, pid, tonno, OGGI)
    miei = client.get(f"/nutrition/diary/saved?profile_id={pid}", headers=h).json()
    assert [m["name"] for m in miei] == ["Apple"]
    # L'uso però è contato: se lo rimette, torna con la sua storia.
    riga = db.scalar(select(SavedFood).where(SavedFood.ingredient_id == tonno.id))
    assert riga.uses == 2 and riga.starred is False


def test_i_miei_prodotti_sono_miei(ambiente):
    client, db = ambiente
    h, pid = _account(client)
    h_altro, pid_altro = _account(client, "b@example.com")
    tonno, _ = _prodotti(db)
    _aggiungi(client, h, pid, tonno, OGGI)
    assert client.get(f"/nutrition/diary/saved?profile_id={pid_altro}", headers=h_altro).json() == []
    assert client.get(f"/nutrition/diary/saved?profile_id={pid}", headers=h_altro).status_code == 404
