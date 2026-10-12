"""Un lavoro alla volta: invio dei promemoria, traduzione del catalogo.

Il job orario può essere ritentato mentre il primo giro è ancora in corso
(curl che scade su un Render lento), e la traduzione del catalogo può partire
sia dal pulsante "Aggiorna catalogo" sia dal job: due giri insieme mandano
due volte la stessa notifica o pagano due volte la stessa traduzione.

`exclusive` non aspetta: se il lavoro è già in corso restituisce False e chi
chiama rinuncia. Dentro lo stesso processo basta un lucchetto in memoria
(Render gratuito è un'istanza sola); su Postgres si prende anche un advisory
lock, che vale fra processi diversi (un deploy che si sovrappone).
"""

from __future__ import annotations

import threading
import zlib
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text

from app.database import engine

_locali: dict[str, threading.Lock] = {}
_guardia = threading.Lock()


def _lucchetto(nome: str) -> threading.Lock:
    with _guardia:
        return _locali.setdefault(nome, threading.Lock())


@contextmanager
def exclusive(nome: str, bind=None) -> Iterator[bool]:
    """`with exclusive("dispatch") as mio:` — `mio` è False se è già in corso.

    `bind` è il motore del database da usare (quello della sessione di chi
    chiama); senza, quello dell'app.
    """
    motore = bind if bind is not None else engine
    locale = _lucchetto(nome)
    if not locale.acquire(blocking=False):
        yield False
        return
    try:
        if motore.dialect.name != "postgresql":
            yield True
            return
        chiave = zlib.crc32(f"kilo:{nome}".encode())
        with motore.connect() as conn:
            preso = bool(conn.execute(text("select pg_try_advisory_lock(:k)"), {"k": chiave}).scalar())
            try:
                yield preso
            finally:
                if preso:
                    conn.execute(text("select pg_advisory_unlock(:k)"), {"k": chiave})
                    conn.commit()
    finally:
        locale.release()
