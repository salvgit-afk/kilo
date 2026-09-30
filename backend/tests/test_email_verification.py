"""Verifica dell'email e password dimenticata.

Le email non partono davvero: `mailer.send` è sostituito da una funzione
che le raccoglie, e il DNS da una risposta fissa.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import EmailCode, User
from app.services import auth, email_verification, mailer, rate_limit

PASSWORD = "passwordlunga1"
EMAIL = "salvo.rossi@gmail.com"


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

    impostazioni = get_settings()
    monkeypatch.setattr(impostazioni, "secret_key", "chiave-di-test-" + "x" * 40)
    monkeypatch.setattr(impostazioni, "gemini_api_key", "")
    monkeypatch.setattr(impostazioni, "brevo_api_key", "chiave-finta")
    monkeypatch.setattr(impostazioni, "mail_from", "kilo.app@gmail.com")
    for finestra in (
        rate_limit.LOGIN_PER_IP,
        rate_limit.LOGIN_FAILURES_PER_EMAIL,
        rate_limit.REGISTER_PER_IP,
        rate_limit.EMAIL_CODE_PER_IP,
    ):
        finestra.reset()

    inviate: list[dict] = []
    monkeypatch.setattr(
        mailer, "send", lambda to, subject, html, text: inviate.append({"to": to, "subject": subject, "text": text})
    )
    monkeypatch.setattr(email_verification, "domain_receives_email", lambda d: d != "nessunaposta.it")

    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db, inviate
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _codice(inviate) -> str:
    return re.search(r"\b(\d{6})\b", inviate[-1]["subject"]).group(1)


def _chiedi(client, email=EMAIL, purpose="register"):
    return client.post("/auth/email-code", json={"email": email, "purpose": purpose})


def _indietro(db, email=EMAIL, purpose="register", secondi=61):
    """Sposta indietro l'invio, come se fosse passato del tempo."""
    riga = db.scalar(select(EmailCode).where(EmailCode.email == email, EmailCode.purpose == purpose))
    riga.sent_at = riga.sent_at - dt.timedelta(seconds=secondi)
    riga.expires_at = riga.expires_at - dt.timedelta(seconds=secondi)
    db.commit()


# --- Indirizzi --------------------------------------------------------------------


@pytest.mark.parametrize(
    "email",
    ["email@gmail.com", "test123@gmail.com", "mario@example.com", "x@mailinator.com", "senza-chiocciola", "a@b"],
)
def test_indirizzi_finti_rifiutati(email):
    assert email_verification.address_problem(email) is not None


def test_indirizzo_vero_accettato():
    assert email_verification.address_problem("Salvo.Rossi@Gmail.com ") is None


def test_dominio_senza_posta_rifiutato(ambiente):
    client, _, inviate = ambiente
    r = _chiedi(client, "mario@nessunaposta.it")
    assert r.status_code == 422 and "non può ricevere" in r.json()["detail"]
    assert inviate == []


# --- Registrazione -------------------------------------------------------------


def test_registrazione_col_codice(ambiente):
    client, db, inviate = ambiente
    r = _chiedi(client)
    assert r.status_code == 200, r.text
    assert r.json() == {"sent": True, "required": True, "expires_in_minutes": 10, "resend_after_seconds": 60}
    assert inviate[0]["to"] == EMAIL

    riga = db.scalar(select(EmailCode))
    assert _codice(inviate) not in riga.code_hash  # solo l'impronta

    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": _codice(inviate)})
    assert r.status_code == 201, r.text
    utente = db.scalar(select(User))
    assert utente.email_verified_at is not None
    # Il codice si usa una volta sola.
    assert db.scalar(select(EmailCode)) is None


def test_registrazione_senza_codice_o_sbagliato(ambiente):
    client, db, inviate = ambiente
    _chiedi(client)
    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 400
    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": "000000"})
    assert r.status_code == 400 and "Ancora 4 tentativi" in r.json()["detail"]
    assert db.scalar(select(User)) is None


def test_troppi_tentativi_serve_un_codice_nuovo(ambiente):
    client, _, inviate = ambiente
    _chiedi(client)
    giusto = _codice(inviate)
    sbagliato = "111111" if giusto != "111111" else "222222"
    for _ in range(email_verification.MAX_ATTEMPTS):
        client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": sbagliato})
    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": giusto})
    assert r.status_code == 400 and "nuovo codice" in r.json()["detail"]


def test_codice_scaduto(ambiente):
    client, db, inviate = ambiente
    _chiedi(client)
    _indietro(db, secondi=11 * 60)
    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": _codice(inviate)})
    assert r.status_code == 400 and "scaduto" in r.json()["detail"]


def test_nuovo_codice_solo_dopo_un_minuto_e_vale_l_ultimo(ambiente):
    client, db, inviate = ambiente
    _chiedi(client)
    primo = _codice(inviate)
    r = _chiedi(client)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) <= 61
    _indietro(db)
    assert _chiedi(client).status_code == 200
    secondo = _codice(inviate)
    if primo != secondo:
        r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": primo})
        assert r.status_code == 400
    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "code": secondo})
    assert r.status_code == 201


def test_email_gia_registrata(ambiente):
    client, db, _ = ambiente
    db.add(User(email=EMAIL, password_hash=auth.hash_password(PASSWORD)))
    db.commit()
    r = _chiedi(client)
    assert r.status_code == 409 and "accedi" in r.json()["detail"]


def test_invio_non_riuscito(ambiente, monkeypatch):
    client, db, _ = ambiente

    def _rotto(*_a):
        raise mailer.MailError("giù")

    monkeypatch.setattr(mailer, "send", _rotto)
    r = _chiedi(client)
    assert r.status_code == 503
    assert db.scalar(select(EmailCode)) is None


def test_email_spenta_registrazione_come_prima(ambiente, monkeypatch):
    client, db, inviate = ambiente
    monkeypatch.setattr(get_settings(), "brevo_api_key", "")
    assert _chiedi(client).json() == {"sent": False, "required": False, "expires_in_minutes": 0, "resend_after_seconds": 0}
    r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 201
    assert db.scalar(select(User)).email_verified_at is None
    assert inviate == []
    assert _chiedi(client, purpose="reset").status_code == 503


# --- Password dimenticata ------------------------------------------------------------


def test_password_dimenticata(ambiente):
    client, db, inviate = ambiente
    db.add(User(email=EMAIL, password_hash=auth.hash_password(PASSWORD)))
    db.commit()
    vecchio = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {vecchio}"}).status_code == 200

    assert _chiedi(client, purpose="reset").status_code == 200
    assert "password" in inviate[0]["text"].lower()
    r = client.post(
        "/auth/reset-password", json={"email": EMAIL, "code": _codice(inviate), "password": "nuovapassword9"}
    )
    assert r.status_code == 200, r.text
    nuovo = r.json()["token"]

    assert client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": EMAIL, "password": "nuovapassword9"}).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {nuovo}"}).status_code == 200


def test_sessioni_vecchie_chiuse_dopo_il_cambio(ambiente):
    client, db, inviate = ambiente
    utente = User(email=EMAIL, password_hash=auth.hash_password(PASSWORD))
    db.add(utente)
    db.commit()
    vecchio = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["token"]
    # Il cambio arriva dopo: lo si simula spostando indietro il token di un minuto.
    utente.password_changed_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
    db.commit()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {vecchio}"})
    assert r.status_code == 401 and "Password cambiata" in r.json()["detail"]


def test_reset_per_email_sconosciuta_non_la_rivela(ambiente):
    client, _, inviate = ambiente
    r = _chiedi(client, "nessuno.qui@gmail.com", purpose="reset")
    # Stessa risposta di un account vero, ma nessuna email e nessun codice valido.
    assert r.status_code == 200 and r.json()["sent"] is True
    assert inviate == []
    r = client.post(
        "/auth/reset-password", json={"email": "nessuno.qui@gmail.com", "code": "123456", "password": "nuovapassword9"}
    )
    assert r.status_code == 400


def test_codice_di_registrazione_non_vale_per_la_password(ambiente):
    client, db, inviate = ambiente
    db.add(User(email=EMAIL, password_hash=auth.hash_password(PASSWORD)))
    db.commit()
    _chiedi(client, purpose="reset")
    codice = _codice(inviate)
    r = client.post("/auth/register", json={"email": "altro.utente@gmail.com", "password": PASSWORD, "code": codice})
    assert r.status_code == 400
