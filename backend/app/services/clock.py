"""Il giorno di "oggi" per Kilo: quello italiano, non quello del server.

Render gira in UTC: fra mezzanotte e le 2 (l'una d'inverno) per il server è
ancora ieri, e un alimento segnato a quell'ora finiva nel giorno prima. Tutto
il backend chiede la data qui, così il confine del giorno è uno solo.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")


def now() -> dt.datetime:
    return dt.datetime.now(FUSO)


def today() -> dt.date:
    return now().date()
