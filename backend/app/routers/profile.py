"""Profilo utente, screening di sicurezza e peso corporeo."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScreeningRecord, User, UserProfile, WeightLog
from app.routers.auth import current_user
from app.schemas import (
    ProfileIn,
    ProfileOut,
    ProfileUpdate,
    ScreeningIn,
    ScreeningOut,
    WeightLogIn,
    WeightLogOut,
)

router = APIRouter(prefix="/profile", tags=["profilo"])


def get_profile(profile_id: int, db: Session, user: User | None = None) -> UserProfile:
    """Recupera un profilo, verificando che appartenga a chi lo richiede.

    Il controllo di proprietà risponde 404 e non 403: dire "esiste ma non è
    tuo" rivelerebbe quali id sono in uso.
    """
    profile = db.get(UserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profilo non trovato")
    if user is not None and profile.user_id not in (None, user.id):
        raise HTTPException(status_code=404, detail="Profilo non trovato")
    return profile


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(
    payload: ProfileIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UserProfile:
    profile = UserProfile(user_id=user.id, **payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("", response_model=list[ProfileOut])
def list_profiles(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[UserProfile]:
    """Solo i profili dell'account che ha effettuato l'accesso."""
    return list(
        db.scalars(
            select(UserProfile)
            .where(UserProfile.user_id == user.id)
            .order_by(UserProfile.id)
        )
    )


@router.get("/{profile_id}", response_model=ProfileOut)
def read_profile(
    profile_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> UserProfile:
    return get_profile(profile_id, db, user)


@router.patch("/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UserProfile:
    profile = get_profile(profile_id, db, user)
    for campo, valore in payload.model_dump(exclude_unset=True).items():
        setattr(profile, campo, valore)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/{profile_id}/screening", response_model=ScreeningOut, status_code=201)
def add_screening(
    profile_id: int, payload: ScreeningIn, db: Session = Depends(get_db)
) -> ScreeningRecord:
    """Registra un questionario PAR-Q+.

    I questionari non vengono sovrascritti ma accumulati: la situazione di
    salute cambia nel tempo, e serve sapere quale risposta era valida quando
    un certo piano è stato generato.
    """
    profile = get_profile(profile_id, db)
    screening = ScreeningRecord(profile_id=profile.id, **payload.model_dump())
    db.add(screening)
    db.commit()
    db.refresh(screening)
    return screening


@router.get("/{profile_id}/screening", response_model=ScreeningOut | None)
def latest_screening(
    profile_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    profile = get_profile(profile_id, db, user)
    return db.scalar(
        select(ScreeningRecord)
        .where(ScreeningRecord.profile_id == profile.id)
        .order_by(ScreeningRecord.created_at.desc())
    )


@router.post("/{profile_id}/weight", response_model=WeightLogOut, status_code=201)
def log_weight(
    profile_id: int,
    payload: WeightLogIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WeightLog:
    profile = get_profile(profile_id, db, user)
    log = WeightLog(
        profile_id=profile.id,
        date=payload.date or dt.date.today(),
        weight_kg=payload.weight_kg,
        body_fat_pct=payload.body_fat_pct,
        note=payload.note,
    )
    db.add(log)

    # Il peso del profilo segue l'ultima misurazione: da lì dipendono TDEE e
    # target proteico, che altrimenti resterebbero fermi al dato iniziale.
    profile.weight_kg = payload.weight_kg

    db.commit()
    db.refresh(log)
    return log


@router.get("/{profile_id}/weight", response_model=list[WeightLogOut])
def list_weights(
    profile_id: int,
    limit: int = 90,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[WeightLog]:
    profile = get_profile(profile_id, db, user)
    return list(
        db.scalars(
            select(WeightLog)
            .where(WeightLog.profile_id == profile.id)
            .order_by(WeightLog.date.desc())
            .limit(limit)
        )
    )
