"""Registrazione, accesso e sessioni.

Scelte di sicurezza e perché:

  - **Argon2** per le password (via `pwdlib`): è l'algoritmo raccomandato da
    OWASP, ed evita il limite di 72 byte di bcrypt che tronca silenziosamente
    le password lunghe.
  - **La password non viene mai salvata né registrata nei log**, nemmeno in
    forma parziale: nel database finisce solo l'hash.
  - **Token JWT con scadenza**: firmati con una chiave del file `.env`. Se la
    chiave non è configurata, l'app si rifiuta di avviare l'autenticazione
    invece di usare un valore predefinito — una chiave nota renderebbe i
    token falsificabili da chiunque conosca il codice.
  - **L'errore di accesso non distingue** fra email inesistente e password
    sbagliata: dirlo permetterebbe di scoprire quali email sono registrate.
"""

from __future__ import annotations

import datetime as dt
import logging

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

logger = logging.getLogger("auth")

_password_hash = PasswordHash.recommended()

ALGORITHM = "HS256"
TOKEN_TTL_DAYS = 30


class AuthError(RuntimeError):
    """Credenziali non valide o token non utilizzabile."""


class AuthNotConfigured(RuntimeError):
    """Manca `SECRET_KEY` nel file .env."""


def _secret() -> str:
    secret = get_settings().secret_key
    if not secret or len(secret) < 32:
        raise AuthNotConfigured(
            "SECRET_KEY mancante o troppo corta nel file .env: servono almeno "
            "32 caratteri casuali. Generane una con "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
        )
    return secret


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def create_token(user: User) -> str:
    adesso = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(adesso.timestamp()),
            "exp": adesso + dt.timedelta(days=TOKEN_TTL_DAYS),
        },
        _secret(),
        algorithm=ALGORITHM,
    )


def _payload(token: str) -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise AuthError("Sessione scaduta: accedi di nuovo.") from e
    except (jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise AuthError("Sessione non valida.") from e


def decode_token(token: str) -> int:
    """Restituisce l'id utente contenuto nel token, se valido."""
    return int(_payload(token)["sub"])


def user_from_token(db: Session, token: str) -> User:
    """L'utente della sessione. Dopo un cambio password i token vecchi non valgono."""
    payload = _payload(token)
    user = get_user(db, int(payload["sub"]))
    cambio = user.password_changed_at
    if cambio is not None:
        if cambio.tzinfo is None:
            cambio = cambio.replace(tzinfo=dt.timezone.utc)
        # `iat` è in secondi interi: il token emesso nello stesso secondo del
        # cambio, cioè quello nuovo, resta valido.
        if int(payload.get("iat", 0)) < int(cambio.timestamp()):
            raise AuthError("Password cambiata: accedi di nuovo.")
    return user


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == normalize_email(email))) is not None


def register(db: Session, *, email: str, password: str, verified: bool = False) -> User:
    email = normalize_email(email)

    if email_taken(db, email):
        raise AuthError("Esiste già un account con questa email.")

    if len(password) < 8:
        raise AuthError("La password deve avere almeno 8 caratteri.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        email_verified_at=dt.datetime.now(dt.timezone.utc) if verified else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Nuovo account registrato (id=%s)", user.id)
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))

    # Messaggio identico nei due casi: distinguerli rivelerebbe quali email
    # sono registrate a chi prova a indovinare.
    credenziali_errate = AuthError("Email o password non corretti.")

    if user is None:
        # Si calcola comunque un hash, così il tempo di risposta non cambia
        # fra email esistente e inesistente.
        hash_password(password)
        raise credenziali_errate

    if not verify_password(password, user.password_hash):
        raise credenziali_errate

    return user


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AuthError("Account non più esistente.")
    return user


def reset_password(db: Session, *, email: str, password: str) -> User:
    """Nuova password, dopo il codice. Le sessioni aperte altrove si chiudono."""
    if len(password) < 8:
        raise AuthError("La password deve avere almeno 8 caratteri.")
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        raise AuthError("Il codice è scaduto o non è valido: chiedine uno nuovo.")
    adesso = dt.datetime.now(dt.timezone.utc)
    user.password_hash = hash_password(password)
    user.password_changed_at = adesso
    # Chi ha ricevuto il codice ha dimostrato che la casella è sua.
    user.email_verified_at = user.email_verified_at or adesso
    db.commit()
    db.refresh(user)
    logger.info("Password cambiata col codice (id=%s)", user.id)
    return user
