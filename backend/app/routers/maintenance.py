"""Manutenzione chiamata dal job orario di GitHub Actions.

Render gratuito non può tenere un timer suo (si spegne dopo 15 minuti): il
job dei promemoria, dopo l'invio, chiama anche questa rotta con lo stesso
segreto (`PUSH_CRON_SECRET`). Fa due cose, entrambe leggere se non c'è
niente da fare:

1. completa la traduzione del catalogo esercizi, se un deploy o lo
   spegnimento di Render ha interrotto quella partita da "Aggiorna catalogo":
   chi apre l'app deve trovare tutto in italiano, non un misto;
2. pulisce le righe che non servono più e fanno crescere il database verso
   il limite gratuito di Neon (0,5 GB).
"""

from __future__ import annotations

import datetime as dt
import hmac
import logging
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ApiUsage, EmailCode, NotificationLog
from app.services import clock, translation

logger = logging.getLogger("maintenance")
router = APIRouter(prefix="/maintenance", tags=["manutenzione"])

# Tempo massimo di traduzione per giro: il job orario aspetta al più qualche
# minuto, e il resto lo riprende il giro dopo.
TRANSLATION_BUDGET_SECONDS = 180
NOTIFICATION_LOG_DAYS = 60
API_USAGE_DAYS = 30
# Le notifiche di un giorno preciso finiscono con la data ("integratori:2026-10-12"):
# quelle si possono dimenticare. Le altre ("scheda-vecchia:3", "ricetta-salvata:9")
# restano: è il registro a impedire che vengano rimandate.
_CHIAVE_CON_DATA = re.compile(r"\d{4}-\d{2}-\d{2}$")


def prune(db: Session, *, today: dt.date | None = None) -> dict[str, int]:
    """Cancella i registri vecchi che non servono più. Mai dati dell'utente."""
    today = today or clock.today()
    limite = today - dt.timedelta(days=NOTIFICATION_LOG_DAYS)
    vecchie = [
        id_
        for id_, chiave in db.execute(
            select(NotificationLog.id, NotificationLog.key).where(NotificationLog.sent_on < limite)
        )
        if _CHIAVE_CON_DATA.search(chiave)
    ]
    if vecchie:
        db.execute(delete(NotificationLog).where(NotificationLog.id.in_(vecchie)))
    quote = db.execute(
        delete(ApiUsage).where(ApiUsage.day < today - dt.timedelta(days=API_USAGE_DAYS))
    ).rowcount
    codici = db.execute(
        delete(EmailCode).where(
            EmailCode.expires_at < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        )
    ).rowcount
    db.commit()
    return {"notification_log": len(vecchie), "api_usage": quote or 0, "email_codes": codici or 0}


def _check_secret(x_cron_secret: str | None) -> None:
    segreto = get_settings().push_cron_secret
    if not segreto:
        raise HTTPException(status_code=503, detail="Manutenzione non configurata (PUSH_CRON_SECRET).")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, segreto):
        raise HTTPException(status_code=403, detail="Non autorizzato.")


@router.post("/run")
def run(x_cron_secret: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    _check_secret(x_cron_secret)
    pulite = prune(db)
    tradotti = 0
    if get_settings().gemini_api_key and translation.pending_count(db) > 0:
        tradotti = translation.translate_library(budget_seconds=TRANSLATION_BUDGET_SECONDS)
    risultato = {"pruned": pulite, "translated": tradotti, "pending": translation.pending_count(db)}
    logger.info("Manutenzione: %s", risultato)
    return risultato
