"""Iscrizione ai promemoria sul telefono e invio (vedi `push_notifications`)."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import PushSubscription, User, UserProfile
from app.routers.auth import current_user
from app.services import notification_rules, push_notifications, rate_limit

router = APIRouter(prefix="/push", tags=["notifiche"])


class PushConfigOut(BaseModel):
    enabled: bool
    public_key: str | None


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1024, pattern=r"^https://")
    keys: PushKeys
    reminder_hour: int = Field(default=20, ge=min(push_notifications.ORE_CONSENTITE), le=max(push_notifications.ORE_CONSENTITE))


class SubscriptionOut(BaseModel):
    endpoint: str
    reminder_hour: int


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1024)


class SettingsIn(BaseModel):
    """Quali notifiche si vogliono ricevere, per account."""

    training: bool = True
    supplements: bool = True
    diary: bool = True
    recipes: bool = True
    progress: bool = True
    meal_prep: bool = False
    # None = l'ora dell'allenamento la ricava Kilo dalle sessioni passate.
    gym_hour: int | None = Field(default=None, ge=5, le=23)


class SettingsOut(SettingsIn):
    # L'ora effettiva del promemoria dell'allenamento: quella scelta a mano,
    # o quella ricavata dagli avvii delle ultime sessioni.
    effective_gym_hour: int


class DispatchOut(BaseModel):
    due: int
    sent: int
    removed: int
    failed: int


def _require_configured() -> None:
    if not get_settings().push_configured:
        raise HTTPException(status_code=503, detail="Le notifiche non sono configurate sul server.")


@router.get("/config", response_model=PushConfigOut)
def config() -> PushConfigOut:
    """Chiave pubblica VAPID per `PushManager.subscribe()`. Non è un segreto."""
    s = get_settings()
    return PushConfigOut(enabled=s.push_configured, public_key=s.vapid_public_key or None)


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()


@router.post("/subscriptions", response_model=SubscriptionOut)
def subscribe(
    payload: SubscriptionIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> PushSubscription:
    """Iscrive questo dispositivo, o aggiorna l'ora se è già iscritto.

    Se lo stesso browser era iscritto con un altro account (cambio di
    account sullo stesso telefono), l'iscrizione passa a chi è entrato ora:
    i promemoria di un altro non devono arrivare qui.
    """
    _require_configured()
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=payload.endpoint, user_id=user.id)
        db.add(sub)
    elif sub.user_id != user.id:
        sub.user_id = user.id
    sub.p256dh = payload.keys.p256dh
    sub.auth = payload.keys.auth
    sub.reminder_hour = payload.reminder_hour
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/subscriptions/remove", status_code=204, response_model=None)
def unsubscribe(payload: EndpointIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id
        )
    )
    if sub is not None:
        db.delete(sub)
        db.commit()


@router.post("/test", status_code=204, response_model=None)
def test(payload: EndpointIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    """Notifica di prova su questo dispositivo, per controllare che arrivi."""
    _require_configured()
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id
        )
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="Questo dispositivo non è iscritto ai promemoria.")
    try:
        rate_limit.consume_daily(db, user.id, "push_test")
    except rate_limit.RateLimited as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)}) from e
    db.commit()
    try:
        push_notifications.send(
            sub,
            push_notifications.Message(
                title="Kilo", body="Le notifiche funzionano: ti scrivo solo se oggi manca qualcosa.", section="profilo"
            ),
        )
    except push_notifications.Gone as e:
        db.delete(sub)
        db.commit()
        raise HTTPException(status_code=410, detail="Iscrizione scaduta: riattiva i promemoria.") from e
    except push_notifications.PushFailed as e:
        push_notifications.log.warning("Notifica di prova rifiutata: %s", e.reason)
        raise HTTPException(
            status_code=502, detail=f"Il servizio di notifiche ha rifiutato l'invio ({e.reason})."
        ) from e


def _settings_out(db: Session, user: User) -> SettingsOut:
    s = notification_rules.settings_for(db, user.id)
    profilo = db.scalars(select(UserProfile).where(UserProfile.user_id == user.id)).first()
    ora = (
        notification_rules.gym_hour(
            db, profilo, fuso=push_notifications.FUSO, override=s.gym_hour
        )
        if profilo is not None
        else (s.gym_hour or notification_rules.DEFAULT_GYM_HOUR)
    )
    return SettingsOut(
        training=s.training,
        supplements=s.supplements,
        diary=s.diary,
        recipes=s.recipes,
        progress=s.progress,
        meal_prep=s.meal_prep,
        gym_hour=s.gym_hour,
        effective_gym_hour=ora,
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db), user: User = Depends(current_user)) -> SettingsOut:
    out = _settings_out(db, user)
    db.commit()
    return out


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    payload: SettingsIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> SettingsOut:
    s = notification_rules.settings_for(db, user.id)
    for campo, valore in payload.model_dump().items():
        setattr(s, campo, valore)
    out = _settings_out(db, user)
    db.commit()
    return out


@router.post("/dispatch", response_model=DispatchOut)
def dispatch(
    x_cron_secret: str | None = Header(default=None), db: Session = Depends(get_db)
) -> DispatchOut:
    """Chiamato ogni ora dal job esterno, con il segreto `PUSH_CRON_SECRET`."""
    s = get_settings()
    if not s.push_cron_secret or not s.push_configured:
        raise HTTPException(status_code=503, detail="Invio dei promemoria non configurato.")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, s.push_cron_secret):
        raise HTTPException(status_code=403, detail="Non autorizzato.")
    r = push_notifications.dispatch(db)
    return DispatchOut(due=r.due, sent=r.sent, removed=r.removed, failed=r.failed)
