"""Promemoria sul telefono con Web Push.

Il flusso:
  1. il browser si iscrive (`PushManager.subscribe`) con la chiave pubblica
     VAPID e ci consegna indirizzo e chiavi dell'iscrizione;
  2. un job esterno e gratuito (GitHub Actions, ogni ora) chiama
     `/push/dispatch`: Render gratuito si addormenta e non può tenere un
     timer suo;
  3. per ogni iscrizione arrivata alla sua ora si calcolano i promemoria di
     `daily_reminders` e, se manca qualcosa, parte una notifica sola.

Il testo lo costruisce questo modulo, non l'LLM: dice solo cosa manca oggi.
Se non manca niente non parte nulla, così la notifica non diventa rumore.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PushSubscription, UserProfile
from app.services import daily_reminders

log = logging.getLogger(__name__)

# Gli utenti sono in Italia: l'ora del promemoria è quella di Roma, anche se
# il server gira in UTC.
FUSO = ZoneInfo("Europe/Rome")
ORE_CONSENTITE = range(7, 23)
# Un promemoria della sera che arriva il giorno dopo non serve più.
TTL_SECONDI = 4 * 3600

SUPPLEMENT_NAMES = {
    "protein_powder": "proteine in polvere",
    "creatine": "creatina",
    "caffeine": "caffeina",
    "beta_alanine": "beta-alanina",
    "hmb": "HMB",
    "bcaa": "BCAA",
    "glutamine": "glutammina",
    "citrulline": "citrullina",
    "vitamin_d": "vitamina D",
    "omega_3": "omega-3",
    "ashwagandha": "ashwagandha",
    "moringa": "moringa",
}


@dataclass
class Message:
    title: str
    body: str
    # Sezione dell'app da aprire al tocco.
    section: str


class Gone(Exception):
    """L'iscrizione non esiste più (app disinstallata, permesso tolto)."""


class PushFailed(Exception):
    """Il servizio push ha rifiutato il messaggio: `reason` dice perché."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _reason(e: Exception) -> str:
    """Motivo leggibile dalla risposta del servizio push (Apple, Google, Mozilla).

    Apple risponde per esempio 403 {"reason": "BadJwtToken"}: quasi sempre
    un VAPID_SUBJECT non valido o chiavi incollate male.
    """
    risposta = getattr(e, "response", None)
    if risposta is None:
        return str(e)[:200]
    testo = (getattr(risposta, "text", "") or "").strip()
    try:
        testo = json.loads(testo).get("reason", testo)
    except (ValueError, AttributeError):
        pass
    return f"{risposta.status_code} {testo}".strip()[:200]


def now_local() -> dt.datetime:
    return dt.datetime.now(FUSO)


def build_message(reminders: daily_reminders.DailyReminders, *, name: str | None = None) -> Message | None:
    """Una frase con tutto ciò che manca oggi; None se non manca niente."""
    parti: list[str] = []
    sezione = "oggi"
    if reminders.workouts_due:
        nomi = ", ".join(p.name for p in reminders.workouts_due)
        parti.append(f"l'allenamento ({nomi})")
        sezione = "scheda"
    if reminders.supplements:
        nomi = ", ".join(
            d.product_name or SUPPLEMENT_NAMES.get(d.kind, d.kind) for d, _ in reminders.supplements
        )
        parti.append(nomi)
        if sezione == "oggi":
            sezione = "integratori"
    if reminders.meals_missing:
        parti.append("i pasti nel diario")
        if sezione == "oggi":
            sezione = "diario"
    if not parti:
        return None
    if len(parti) > 1:
        # Con più cose da ricordare si apre la pagina Oggi, che le riassume.
        sezione = "oggi"
    elenco = parti[0] if len(parti) == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]
    saluto = f"{name}, oggi" if name else "Oggi"
    return Message(title="Kilo", body=f"{saluto} non hai ancora segnato {elenco}.", section=sezione)


def send(sub: PushSubscription, message: Message) -> None:
    """Invia una notifica. Solleva `Gone` se l'iscrizione va cancellata."""
    from pywebpush import WebPushException, webpush

    settings = get_settings()
    payload = json.dumps(
        {"title": message.title, "body": message.body, "section": message.section},
        ensure_ascii=False,
    )
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=TTL_SECONDI,
            timeout=10,
        )
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            raise Gone() from e
        raise PushFailed(_reason(e)) from e
    except Exception as e:  # chiave o subject non validi, rete
        raise PushFailed(f"{type(e).__name__}: {str(e)[:160]}") from e


def _message_for_user(db: Session, user_id: int, today: dt.date) -> Message | None:
    profili = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).all()
    for profilo in profili:
        msg = build_message(daily_reminders.build(db, profilo, today=today), name=profilo.display_name)
        if msg:
            return msg
    return None


@dataclass
class DispatchResult:
    due: int = 0
    sent: int = 0
    removed: int = 0
    failed: int = 0


def dispatch(db: Session, *, now: dt.datetime | None = None, sender=send) -> DispatchResult:
    """Manda i promemoria arrivati alla loro ora e non ancora mandati oggi.

    «Arrivati» e non «esattamente a quest'ora»: i job gratuiti possono
    partire in ritardo o saltare un giro, e il promemoria delle 20 deve
    arrivare anche se il job parte alle 21.
    """
    adesso = now or now_local()
    oggi = adesso.date()
    risultato = DispatchResult()
    if adesso.hour not in ORE_CONSENTITE:
        return risultato
    iscrizioni = db.scalars(
        select(PushSubscription).where(PushSubscription.reminder_hour <= adesso.hour)
    ).all()
    messaggi: dict[int, Message | None] = {}
    for sub in iscrizioni:
        if sub.last_sent_on == oggi:
            continue
        risultato.due += 1
        if sub.user_id not in messaggi:
            messaggi[sub.user_id] = _message_for_user(db, sub.user_id, oggi)
        msg = messaggi[sub.user_id]
        # Segnato anche se non c'era niente da dire: si guarda una volta al giorno.
        sub.last_sent_on = oggi
        if msg is None:
            continue
        try:
            sender(sub, msg)
            risultato.sent += 1
        except Gone:
            db.delete(sub)
            risultato.removed += 1
        except Exception as e:  # noqa: BLE001 — un telefono irraggiungibile non ferma gli altri
            log.warning("Invio push non riuscito (iscrizione %s): %s", sub.id, e)
            risultato.failed += 1
    db.commit()
    return risultato
