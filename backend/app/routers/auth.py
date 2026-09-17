"""Registrazione, accesso e recupero della sessione."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserProfile
from app.schemas import AuthOut, CredentialsIn, ProfileOut, UserOut
from app.services import auth, rate_limit

router = APIRouter(prefix="/auth", tags=["account"])


def client_ip(request: Request) -> str:
    """Indirizzo di chi si collega.

    Si usa l'**ultimo** valore di `X-Forwarded-For`, quello aggiunto dal
    proxy di Render: i precedenti li scrive il client e si possono inventare.
    """
    inoltro = request.headers.get("x-forwarded-for", "")
    if inoltro:
        return inoltro.split(",")[-1].strip()
    return request.client.host if request.client else "sconosciuto"


def _too_many(e: rate_limit.RateLimited) -> HTTPException:
    return HTTPException(
        status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)}
    )


def is_admin(user: User) -> bool:
    return user.email.lower() in get_settings().admin_email_set


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dipendenza per gli endpoint che richiedono un accesso valido."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Accesso richiesto")

    try:
        user_id = auth.decode_token(header.split(" ", 1)[1].strip())
        return auth.get_user(db, user_id)
    except auth.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except auth.AuthNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def require_admin(user: User = Depends(current_user)) -> User:
    """Solo per gli account indicati in `ADMIN_EMAILS`."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Operazione riservata all'amministratore")
    return user


def _session(db: Session, user: User) -> AuthOut:
    profilo = db.scalar(
        select(UserProfile)
        .where(UserProfile.user_id == user.id)
        .order_by(UserProfile.id.desc())
    )
    return AuthOut(
        token=auth.create_token(user),
        user=UserOut(id=user.id, email=user.email, is_admin=is_admin(user)),
        profile=ProfileOut.model_validate(profilo) if profilo else None,
    )


@router.post("/register", response_model=AuthOut, status_code=201)
def register(payload: CredentialsIn, request: Request, db: Session = Depends(get_db)) -> AuthOut:
    ip = client_ip(request)
    try:
        rate_limit.REGISTER_PER_IP.check(ip)
    except rate_limit.RateLimited as e:
        raise _too_many(e) from e
    rate_limit.REGISTER_PER_IP.hit(ip)
    try:
        user = auth.register(db, email=payload.email, password=payload.password)
    except auth.AuthError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except auth.AuthNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return _session(db, user)


@router.post("/login", response_model=AuthOut)
def login(payload: CredentialsIn, request: Request, db: Session = Depends(get_db)) -> AuthOut:
    ip = client_ip(request)
    email = auth.normalize_email(payload.email)
    try:
        rate_limit.LOGIN_PER_IP.check(ip)
        rate_limit.LOGIN_FAILURES_PER_EMAIL.check(email)
    except rate_limit.RateLimited as e:
        raise _too_many(e) from e
    rate_limit.LOGIN_PER_IP.hit(ip)

    try:
        user = auth.authenticate(db, email=payload.email, password=payload.password)
    except auth.AuthError as e:
        # Contano solo i tentativi falliti: chi entra al primo colpo non
        # consuma nulla del proprio margine.
        rate_limit.LOGIN_FAILURES_PER_EMAIL.hit(email)
        raise HTTPException(status_code=401, detail=str(e)) from e
    except auth.AuthNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return _session(db, user)


@router.get("/me", response_model=AuthOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> AuthOut:
    """Ripristina la sessione a partire dal token salvato dal browser."""
    return _session(db, user)
