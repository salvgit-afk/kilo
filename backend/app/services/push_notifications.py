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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import NotificationLog, PushSubscription, User, UserProfile
from app.services import daily_reminders, notification_rules

log = logging.getLogger(__name__)

# Gli utenti sono in Italia: l'ora del promemoria è quella di Roma, anche se
# il server gira in UTC.
FUSO = ZoneInfo("Europe/Rome")
ORE_CONSENTITE = range(7, 23)
# Un promemoria della sera che arriva il giorno dopo non serve più.
TTL_SECONDI = 4 * 3600
# Tetto giornaliero per persona: oltre, le notifiche smettono di essere
# promemoria e diventano rumore che si impara a ignorare.
MAX_PER_DAY = 3

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


@dataclass
class DispatchResult:
    due: int = 0
    sent: int = 0
    removed: int = 0
    failed: int = 0


def _subscriptions_by_user(db: Session) -> dict[int, list[PushSubscription]]:
    gruppi: dict[int, list[PushSubscription]] = {}
    for sub in db.scalars(select(PushSubscription)):
        gruppi.setdefault(sub.user_id, []).append(sub)
    return gruppi


def _deliver(
    db: Session,
    subs: list[PushSubscription],
    nota: notification_rules.Notification,
    result: DispatchResult,
    sender,
) -> bool:
    """Manda una notifica a tutti i dispositivi dell'account.

    Torna True se almeno uno l'ha ricevuta: solo allora la notifica viene
    registrata come mandata, altrimenti si riprova al giro dopo.
    """
    recapitata = False
    for sub in list(subs):
        try:
            sender(sub, Message(title=nota.title, body=nota.body, section=nota.section))
            result.sent += 1
            recapitata = True
        except Gone:
            db.delete(sub)
            subs.remove(sub)
            result.removed += 1
        except Exception as e:  # noqa: BLE001 — un telefono irraggiungibile non ferma gli altri
            log.warning("Invio push non riuscito (iscrizione %s): %s", sub.id, e)
            result.failed += 1
    return recapitata


def _already_sent(db: Session, user_id: int) -> set[str]:
    return set(db.scalars(select(NotificationLog.key).where(NotificationLog.user_id == user_id)))


def _sent_today(db: Session, user_id: int, today: dt.date) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(NotificationLog)
            .where(NotificationLog.user_id == user_id, NotificationLog.sent_on == today)
        )
        or 0
    )


def _record(db: Session, user_id: int, key: str, today: dt.date) -> None:
    db.add(NotificationLog(user_id=user_id, key=key, sent_on=today))
    db.flush()


def dispatch(db: Session, *, now: dt.datetime | None = None, sender=send) -> DispatchResult:
    """Manda le notifiche dovute adesso, al massimo `MAX_PER_DAY` per persona.

    Il job orario può partire in ritardo o saltare un giro: ogni regola
    dichiara una finestra di ore, e dentro quella la notifica parte comunque,
    una volta sola (`NotificationLog`).
    """
    adesso = now or now_local()
    oggi = adesso.date()
    result = DispatchResult()
    if adesso.hour not in ORE_CONSENTITE:
        return result

    for user_id, subs in _subscriptions_by_user(db).items():
        utente = db.get(User, user_id)
        if utente is None:
            continue
        impostazioni = notification_rules.settings_for(db, user_id)
        ora_sera = min(s.reminder_hour for s in subs)
        candidate = notification_rules.build(
            db, utente, today=oggi, fuso=FUSO, settings=impostazioni, evening_hour=ora_sera
        )
        gia_mandate = _already_sent(db, user_id)
        restanti = MAX_PER_DAY - _sent_today(db, user_id, oggi)
        for nota in candidate:
            if restanti <= 0:
                break
            if nota.key in gia_mandate or not nota.hours[0] <= adesso.hour <= nota.hours[1]:
                continue
            result.due += 1
            if _deliver(db, subs, nota, result, sender):
                _record(db, user_id, nota.key, oggi)
                restanti -= 1
    db.commit()
    return result


def after_session(db: Session, profile: UserProfile, *, now: dt.datetime | None = None, sender=send) -> bool:
    """Promemoria degli integratori appena finito l'allenamento.

    Arriva subito e non al giro d'ora successivo: le fonti indicano le
    proteine da subito e fino a due ore dopo, e mezz'ora è il momento in cui
    lo shaker si prepara davvero. Se non c'è niente da prendere, tace.
    """
    adesso = now or now_local()
    oggi = adesso.date()
    if profile.user_id is None:
        return False
    subs = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == profile.user_id)
    ).all()
    if not subs:
        return False
    impostazioni = notification_rules.settings_for(db, profile.user_id)
    if not impostazioni.supplements:
        return False
    da_prendere = notification_rules.supplement_intake.pending(db, profile, today=oggi)
    if not da_prendere:
        return False
    chiave = f"post-allenamento:{profile.id}:{oggi}"
    if chiave in _already_sent(db, profile.user_id):
        return False
    if _sent_today(db, profile.user_id, oggi) >= MAX_PER_DAY:
        return False
    elenco = ", ".join(notification_rules._nome(d) for d, _ in da_prendere)
    nota = notification_rules.Notification(
        key=chiave,
        title="Allenamento chiuso",
        body=(
            f"Entro mezz'ora: {elenco}. Le proteine in 250-300 ml d'acqua, o come "
            "indica la confezione."
        ),
        section="integratori",
        category="supplements",
        priority=1,
        hours=(0, 23),
    )
    risultato = DispatchResult()
    if _deliver(db, list(subs), nota, risultato, sender):
        _record(db, profile.user_id, chiave, oggi)
        db.commit()
        return True
    db.commit()
    return False
