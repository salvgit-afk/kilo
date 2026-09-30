"""Verifica dell'email con un codice di 6 cifre.

Serve a due cose: registrarsi con un indirizzo vero, e rientrare con la
password dimenticata. Prima di mandare il codice si fermano gli indirizzi
finti più comuni (nomi segnaposto come `email@`, domini di prova o usa-e-
getta, domini senza server di posta): che la casella esista davvero lo
dimostra solo il codice ricevuto.

Il codice vale 10 minuti, se ne chiede uno nuovo dopo un minuto e dopo 5
tentativi sbagliati va richiesto da capo. Nel database finisce solo la sua
impronta (HMAC con la chiave del server), non il codice.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import re
import secrets

import dns.exception
import dns.resolver
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailCode
from app.services import mailer

logger = logging.getLogger("email_verification")

VALIDITY = dt.timedelta(minutes=10)
RESEND_AFTER = dt.timedelta(seconds=60)
MAX_ATTEMPTS = 5
DNS_TIMEOUT_SECONDS = 3.0

REGISTER = "register"
RESET = "reset"

# Parti prima della @ che non sono una persona né un'azienda.
PLACEHOLDER_NAMES = {
    "email", "e-mail", "mail", "test", "testing", "prova", "prove", "esempio", "example",
    "user", "utente", "nome", "name", "cognome", "nomecognome", "nome.cognome", "tuonome",
    "tuaemail", "asd", "asdf", "qwerty", "abc", "xxx", "aaa", "foo", "bar", "noreply",
    "no-reply", "fake", "finto",
}

# Domini riservati agli esempi o usa-e-getta.
BLOCKED_DOMAINS = {
    "example.com", "example.org", "example.net", "example.it", "esempio.it", "test.com",
    "test.it", "prova.it", "email.com", "mail.test", "localhost", "mailinator.com",
    "yopmail.com", "guerrillamail.com", "sharklasers.com", "10minutemail.com",
    "temp-mail.org", "tempmail.com", "trashmail.com", "getnada.com", "dispostable.com",
    "maildrop.cc", "throwawaymail.com",
}

_FORMA = re.compile(r"^[a-z0-9._%+-]+@([a-z0-9-]+\.)+[a-z]{2,}$")


class VerificationError(ValueError):
    """Indirizzo non accettato o codice sbagliato: il messaggio è per l'utente."""


class TooSoon(VerificationError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


def normalize(email: str) -> str:
    return (email or "").strip().lower()


def address_problem(email: str) -> str | None:
    """None se l'indirizzo può ricevere il codice, altrimenti il motivo."""
    e = normalize(email)
    if not _FORMA.match(e):
        return "Scrivi un indirizzo email valido."
    locale, dominio = e.split("@")
    if locale in PLACEHOLDER_NAMES or locale.rstrip("0123456789") in PLACEHOLDER_NAMES:
        return "Usa il tuo indirizzo email reale: ti mandiamo un codice per confermarlo."
    if dominio in BLOCKED_DOMAINS:
        return "Questo dominio non è accettato: usa il tuo indirizzo email personale."
    return None


def domain_receives_email(domain: str) -> bool:
    """Il dominio ha un server di posta (record MX).

    Se il DNS è lento o irraggiungibile non si blocca nessuno: decide il
    codice. Solo un dominio inesistente o senza posta viene fermato.
    """
    try:
        risposta = dns.resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT_SECONDS)
        # "Null MX" (RFC 7505, un solo record verso "."): il dominio dichiara
        # di non ricevere posta, come example.com.
        return any(str(r.exchange) not in (".", "") for r in risposta)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False
    except dns.exception.DNSException:
        return True


def _hash(email: str, purpose: str, code: str) -> str:
    chiave = get_settings().secret_key.encode()
    return hmac.new(chiave, f"{purpose}:{email}:{code}".encode(), hashlib.sha256).hexdigest()


def _aware(momento: dt.datetime) -> dt.datetime:
    # SQLite restituisce date senza fuso: sono comunque in UTC.
    return momento if momento.tzinfo else momento.replace(tzinfo=dt.timezone.utc)


def _message(purpose: str, code: str) -> tuple[str, str, str]:
    if purpose == RESET:
        titolo = "Cambia la password"
        frase = "Per scegliere una nuova password di Kilo inserisci questo codice nell'app:"
        coda = "Se non l'hai chiesto tu, ignora questa email: la password resta quella di prima."
    else:
        titolo = "Conferma la tua email"
        frase = "Per completare la registrazione a Kilo inserisci questo codice nell'app:"
        coda = "Se non hai chiesto tu di registrarti, ignora questa email: senza il codice l'account non viene creato."
    oggetto = f"{code} è il tuo codice Kilo"
    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e6e7ea">
  <div style="background:#07080d;padding:26px 24px;text-align:center">
    <div style="font-size:26px;font-weight:700;color:#aed44a;letter-spacing:.5px">Kilo</div>
    <div style="font-size:18px;font-weight:700;color:#ffffff;margin-top:8px">{titolo}</div>
  </div>
  <div style="padding:24px;color:#2b2f3a;font-size:15px;line-height:1.5">
    <p style="margin:0">{frase}</p>
    <p style="font-family:'Courier New',monospace;font-size:34px;font-weight:700;letter-spacing:10px;text-align:center;color:#6f8f1f;margin:22px 0">{code}</p>
    <p style="margin:0;color:#6b7080;font-size:13px">Vale 10 minuti. {coda}</p>
  </div>
</div>"""
    testo = f"{titolo}\n\n{frase}\n\n{code}\n\nVale 10 minuti. {coda}\n"
    return oggetto, html, testo


def send_code(db: Session, email: str, purpose: str, *, deliver: bool = True) -> None:
    """Crea un codice nuovo e lo manda. L'indirizzo va già controllato.

    Con `deliver` falso il codice si registra ma non parte: serve alla
    password dimenticata per un indirizzo senza account, così la risposta
    non rivela quali email sono registrate.
    """
    e = normalize(email)
    adesso = dt.datetime.now(dt.timezone.utc)
    riga = db.scalar(select(EmailCode).where(EmailCode.email == e, EmailCode.purpose == purpose))
    if riga is not None and adesso - _aware(riga.sent_at) < RESEND_AFTER:
        attesa = int((RESEND_AFTER - (adesso - _aware(riga.sent_at))).total_seconds()) + 1
        raise TooSoon("Ti abbiamo appena mandato un codice: aspetta un minuto prima di chiederne un altro.", attesa)

    codice = f"{secrets.randbelow(1_000_000):06d}"
    if deliver:
        oggetto, html, testo = _message(purpose, codice)
        mailer.send(e, oggetto, html, testo)
    if riga is None:
        riga = EmailCode(email=e, purpose=purpose)
        db.add(riga)
    riga.code_hash = _hash(e, purpose, codice) if deliver else ""
    riga.sent_at = adesso
    riga.expires_at = adesso + VALIDITY
    riga.attempts = 0
    db.commit()


def check_code(db: Session, email: str, purpose: str, code: str | None) -> None:
    """Lancia `VerificationError` se il codice non è quello mandato. Usato una volta sola."""
    e = normalize(email)
    if not code or not code.strip():
        raise VerificationError("Scrivi il codice che ti abbiamo mandato per email.")
    riga = db.scalar(select(EmailCode).where(EmailCode.email == e, EmailCode.purpose == purpose))
    if riga is None or not riga.code_hash or dt.datetime.now(dt.timezone.utc) > _aware(riga.expires_at):
        if riga is not None:
            db.delete(riga)
            db.commit()
        raise VerificationError("Il codice è scaduto o non è valido: chiedine uno nuovo.")
    if riga.attempts >= MAX_ATTEMPTS:
        db.delete(riga)
        db.commit()
        raise VerificationError("Troppi tentativi sbagliati: chiedi un nuovo codice.")
    if not hmac.compare_digest(riga.code_hash, _hash(e, purpose, code.strip())):
        riga.attempts += 1
        db.commit()
        rimasti = MAX_ATTEMPTS - riga.attempts
        raise VerificationError(
            "Codice non corretto." + (f" Ancora {rimasti} tentativi." if rimasti else " Chiedine uno nuovo.")
        )
    db.delete(riga)
    db.commit()
