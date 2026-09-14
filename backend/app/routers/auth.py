"""Registrazione, accesso e recupero della sessione."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserProfile
from app.schemas import AuthOut, CredentialsIn, ProfileOut, UserOut
from app.services import auth

router = APIRouter(prefix="/auth", tags=["account"])


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


def _session(db: Session, user: User) -> AuthOut:
    profilo = db.scalar(
        select(UserProfile)
        .where(UserProfile.user_id == user.id)
        .order_by(UserProfile.id.desc())
    )
    return AuthOut(
        token=auth.create_token(user),
        user=UserOut.model_validate(user),
        profile=ProfileOut.model_validate(profilo) if profilo else None,
    )


@router.post("/register", response_model=AuthOut, status_code=201)
def register(payload: CredentialsIn, db: Session = Depends(get_db)) -> AuthOut:
    try:
        user = auth.register(db, email=payload.email, password=payload.password)
    except auth.AuthError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except auth.AuthNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return _session(db, user)


@router.post("/login", response_model=AuthOut)
def login(payload: CredentialsIn, db: Session = Depends(get_db)) -> AuthOut:
    try:
        user = auth.authenticate(db, email=payload.email, password=payload.password)
    except auth.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except auth.AuthNotConfigured as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return _session(db, user)


@router.get("/me", response_model=AuthOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> AuthOut:
    """Ripristina la sessione a partire dal token salvato dal browser."""
    return _session(db, user)
