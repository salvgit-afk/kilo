"""Limiti di utilizzo: contro i tentativi a raffica e l'esaurimento della quota.

Due strumenti, per due problemi diversi:

  - **finestra in memoria** (`SlidingWindow`) per accesso e registrazione:
    blocca chi prova password a raffica o crea account in massa. Si azzera
    se il servizio si riavvia, ed è accettabile: chi attacca tiene il
    servizio sveglio, e il limite torna subito attivo;
  - **quota giornaliera nel database** (`consume_daily`) per le funzioni che
    chiamano l'LLM: su Render gratuito il servizio dorme e si riavvia spesso,
    e un contatore in memoria non reggerebbe un'intera giornata.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ApiUsage


class RateLimited(RuntimeError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class SlidingWindow:
    """Al massimo `limit` eventi per chiave negli ultimi `seconds` secondi."""

    def __init__(self, limit: int, seconds: int):
        self.limit = limit
        self.seconds = seconds
        self._eventi: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _pulisci(self, chiave: str, adesso: float) -> deque[float]:
        eventi = self._eventi[chiave]
        while eventi and adesso - eventi[0] >= self.seconds:
            eventi.popleft()
        return eventi

    def check(self, chiave: str) -> None:
        """Solleva `RateLimited` se la chiave ha esaurito i tentativi."""
        with self._lock:
            adesso = time.monotonic()
            eventi = self._pulisci(chiave, adesso)
            if len(eventi) >= self.limit:
                attesa = int(self.seconds - (adesso - eventi[0])) + 1
                raise RateLimited("Troppi tentativi: riprova fra qualche minuto.", attesa)

    def hit(self, chiave: str) -> None:
        with self._lock:
            adesso = time.monotonic()
            self._pulisci(chiave, adesso).append(adesso)

    def reset(self, chiave: str | None = None) -> None:
        with self._lock:
            if chiave is None:
                self._eventi.clear()
            else:
                self._eventi.pop(chiave, None)


# Tentativi di accesso falliti per email (contro chi prova le password di un
# account) e richieste per indirizzo IP (contro chi prova molte email).
LOGIN_FAILURES_PER_EMAIL = SlidingWindow(limit=8, seconds=15 * 60)
LOGIN_PER_IP = SlidingWindow(limit=40, seconds=15 * 60)
REGISTER_PER_IP = SlidingWindow(limit=10, seconds=60 * 60)

# Quote giornaliere per account.
DAILY_LIMITS = {
    "chat": 60,
    "food_names": 150,
    "plan_generation": 25,
}


def consume_daily(db: Session, user_id: int, kind: str, *, today: dt.date | None = None) -> None:
    """Conta un uso della funzione `kind`; oltre il limite solleva `RateLimited`."""
    limite = DAILY_LIMITS[kind]
    oggi = today or dt.date.today()
    riga = db.scalar(
        select(ApiUsage).where(ApiUsage.user_id == user_id, ApiUsage.day == oggi, ApiUsage.kind == kind)
    )
    if riga is None:
        riga = ApiUsage(user_id=user_id, day=oggi, kind=kind, count=0)
        db.add(riga)
        try:
            db.flush()
        except IntegrityError:
            # Due richieste contemporanee hanno creato la riga insieme.
            db.rollback()
            riga = db.scalar(
                select(ApiUsage).where(
                    ApiUsage.user_id == user_id, ApiUsage.day == oggi, ApiUsage.kind == kind
                )
            )
    if riga.count >= limite:
        secondi_a_mezzanotte = int(
            (dt.datetime.combine(oggi + dt.timedelta(days=1), dt.time()) - dt.datetime.now()).total_seconds()
        )
        raise RateLimited(
            "Hai raggiunto il limite giornaliero per questa funzione: riprova domani.",
            max(secondi_a_mezzanotte, 60),
        )
    riga.count += 1
    db.commit()
