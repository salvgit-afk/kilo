"""Promemoria sul telefono: iscrizione, invio all'ora giusta, pulizia.

Nessuna chiamata di rete: l'invio vero (`pywebpush`) è sostituito, tranne in
un test che controlla solo la cifratura del messaggio con chiavi reali.
"""

from __future__ import annotations

import base64
import datetime as dt

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import PushSubscription, SupplementDeclaration, WorkoutPlan
from app.services import push_notifications, rate_limit

PASSWORD = "passwordlunga1"
ROMA = push_notifications.FUSO


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _vapid():
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64(pub), _b64(k.private_numbers().private_value.to_bytes(32, "big"))


def _browser_keys():
    """Chiavi come quelle che genera un browser con PushManager.subscribe()."""
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"p256dh": _b64(pub), "auth": _b64(b"0123456789abcdef")}


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

    pub, priv = _vapid()
    s = get_settings()
    monkeypatch.setattr(s, "secret_key", "chiave-di-test-" + "x" * 40)
    monkeypatch.setattr(s, "gemini_api_key", "")
    monkeypatch.setattr(s, "vapid_public_key", pub)
    monkeypatch.setattr(s, "vapid_private_key", priv)
    monkeypatch.setattr(s, "push_cron_secret", "segreto-del-job")
    for finestra in (rate_limit.LOGIN_PER_IP, rate_limit.LOGIN_FAILURES_PER_EMAIL, rate_limit.REGISTER_PER_IP):
        finestra.reset()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _account(client, email, nome="Salvatore"):
    r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    p = client.post("/profile", headers=h, json={
        "display_name": nome, "birth_date": "1994-03-01", "sex": "male", "height_cm": 178,
        "weight_kg": 78, "goal": "hypertrophy", "training_days_per_week": 3,
    })
    return h, p.json()["id"]


def _iscrivi(client, h, endpoint="https://push.example/abc", ora=20):
    return client.post("/push/subscriptions", headers=h, json={
        "endpoint": endpoint, "keys": _browser_keys(), "reminder_hour": ora,
    })


def test_config_pubblica_senza_login(ambiente):
    client, _ = ambiente
    r = client.get("/push/config")
    assert r.status_code == 200
    assert r.json()["enabled"] is True and r.json()["public_key"]


def test_iscrizione_aggiornamento_e_rimozione(ambiente):
    client, db = ambiente
    h, _ = _account(client, "a@example.com")
    assert _iscrivi(client, h).json()["reminder_hour"] == 20
    assert _iscrivi(client, h, ora=21).json()["reminder_hour"] == 21
    assert len(client.get("/push/subscriptions", headers=h).json()) == 1

    assert client.post("/push/subscriptions/remove", headers=h, json={"endpoint": "https://push.example/abc"}).status_code == 204
    assert client.get("/push/subscriptions", headers=h).json() == []


def test_iscrizione_rifiuta_ora_notturna_e_endpoint_non_https(ambiente):
    client, _ = ambiente
    h, _ = _account(client, "a@example.com")
    assert _iscrivi(client, h, ora=3).status_code == 422
    assert _iscrivi(client, h, endpoint="http://push.example/x").status_code == 422


def test_stesso_telefono_passa_al_nuovo_account(ambiente):
    client, db = ambiente
    h1, _ = _account(client, "a@example.com")
    h2, _ = _account(client, "b@example.com")
    _iscrivi(client, h1)
    _iscrivi(client, h2)
    assert client.get("/push/subscriptions", headers=h1).json() == []
    assert len(client.get("/push/subscriptions", headers=h2).json()) == 1


def test_non_si_rimuove_l_iscrizione_di_un_altro(ambiente):
    client, db = ambiente
    h1, _ = _account(client, "a@example.com")
    h2, _ = _account(client, "b@example.com")
    _iscrivi(client, h1)
    client.post("/push/subscriptions/remove", headers=h2, json={"endpoint": "https://push.example/abc"})
    assert len(client.get("/push/subscriptions", headers=h1).json()) == 1


def test_dispatch_richiede_il_segreto(ambiente):
    client, _ = ambiente
    assert client.post("/push/dispatch").status_code == 403
    assert client.post("/push/dispatch", headers={"X-Cron-Secret": "sbagliato"}).status_code == 403


def _con_integratore(db, profile_id):
    db.add(SupplementDeclaration(profile_id=profile_id, kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1))
    db.commit()


def test_dispatch_manda_solo_all_ora_giusta_e_una_volta(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _con_integratore(db, pid)
    _iscrivi(client, h, ora=20)
    inviati = []
    sender = lambda sub, msg: inviati.append(msg)  # noqa: E731

    push_notifications.dispatch(db, now=dt.datetime(2026, 9, 22, 19, 5, tzinfo=ROMA), sender=sender)
    assert inviati == []

    # Il job è in ritardo: alle 21 il promemoria delle 20 parte lo stesso.
    r = push_notifications.dispatch(db, now=dt.datetime(2026, 9, 22, 21, 10, tzinfo=ROMA), sender=sender)
    assert r.sent == 1
    assert "creatina" in inviati[0].body and inviati[0].section == "integratori"

    push_notifications.dispatch(db, now=dt.datetime(2026, 9, 22, 22, 0, tzinfo=ROMA), sender=sender)
    assert len(inviati) == 1

    # Il giorno dopo si ricomincia.
    push_notifications.dispatch(db, now=dt.datetime(2026, 9, 23, 20, 0, tzinfo=ROMA), sender=sender)
    assert len(inviati) == 2


def test_niente_notifica_se_non_manca_niente(ambiente):
    client, db = ambiente
    h, _ = _account(client, "a@example.com")
    _iscrivi(client, h)
    inviati = []
    r = push_notifications.dispatch(
        db, now=dt.datetime(2026, 9, 22, 20, 0, tzinfo=ROMA), sender=lambda s, m: inviati.append(m)
    )
    assert inviati == [] and r.due == 1 and r.sent == 0


def test_iscrizione_scaduta_viene_cancellata(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _con_integratore(db, pid)
    _iscrivi(client, h)

    def scaduta(sub, msg):
        raise push_notifications.Gone()

    r = push_notifications.dispatch(db, now=dt.datetime(2026, 9, 22, 20, 0, tzinfo=ROMA), sender=scaduta)
    assert r.removed == 1
    assert db.scalars(select(PushSubscription)).all() == []


def test_messaggio_con_piu_cose_apre_oggi(ambiente):
    _, db = ambiente
    piano = WorkoutPlan(name="Push A", goal="hypertrophy", days_per_week=3)
    decl = SupplementDeclaration(kind="creatine", dose_amount=5, dose_unit="g", doses_per_day=1)
    from app.services.daily_reminders import DailyReminders

    msg = push_notifications.build_message(
        DailyReminders(supplements=[(decl, 0)], meals_missing=True, workouts_due=[piano]), name="Sara"
    )
    assert msg.section == "oggi"
    assert msg.body == "Sara, oggi non hai ancora segnato l'allenamento (Push A), creatina e i pasti nel diario."


def test_invio_vero_cifra_il_messaggio(ambiente, monkeypatch):
    """Con chiavi reali pywebpush cifra e firma: si ferma solo la richiesta HTTP."""
    client, db = ambiente
    h, _ = _account(client, "a@example.com")
    _iscrivi(client, h)
    sub = db.scalars(select(PushSubscription)).one()
    chiamate = {}

    class Risposta:
        status_code = 201
        text = ""
        headers = {}

    def finto_post(url, data=None, headers=None, timeout=None, **_):
        chiamate.update(url=url, data=data, headers=headers)
        return Risposta()

    monkeypatch.setattr("requests.post", finto_post)
    push_notifications.send(sub, push_notifications.Message(title="Kilo", body="ciao", section="oggi"))
    assert chiamate["url"] == "https://push.example/abc"
    assert chiamate["headers"]["Content-Encoding"] == "aes128gcm"
    assert chiamate["headers"]["Authorization"].startswith("vapid ")
    assert b"ciao" not in chiamate["data"]


@pytest.mark.parametrize("scritto, atteso", [
    ("mailto:me@example.it", "mailto:me@example.it"),
    ("mailto: me@example.it ", "mailto:me@example.it"),
    ("<me@example.it>", "mailto:me@example.it"),
    ("me@example.it", "mailto:me@example.it"),
    ('"mailto:me@example.it"', "mailto:me@example.it"),
    ("https://kilo.example.it", "https://kilo.example.it"),
])
def test_subject_vapid_normalizzato(scritto, atteso):
    from app.config import Settings

    assert Settings(vapid_subject=scritto).vapid_subject == atteso


def test_chiavi_incollate_con_spazi_e_virgolette():
    from app.config import Settings

    s = Settings(vapid_private_key='  "abc_DEF-123"\n', push_cron_secret=" segreto ")
    assert s.vapid_private_key == "abc_DEF-123" and s.push_cron_secret == "segreto"


def test_prova_rifiutata_mostra_il_motivo(ambiente, monkeypatch):
    client, db = ambiente
    h, _ = _account(client, "a@example.com")
    _iscrivi(client, h)

    class Risposta:
        status_code = 403
        reason = "Forbidden"
        text = '{"reason":"BadJwtToken"}'
        headers = {}

    monkeypatch.setattr("requests.post", lambda *a, **k: Risposta())
    r = client.post("/push/test", headers=h, json={"endpoint": "https://push.example/abc"})
    assert r.status_code == 502
    assert "403 BadJwtToken" in r.json()["detail"]
