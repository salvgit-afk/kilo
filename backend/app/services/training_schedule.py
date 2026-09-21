"""Giorni della settimana in cui ci si allena.

Una scheda dice *cosa* fare (giorno A, B, Push…); questo modulo dice
*quando*. I giorni sono numeri da 0 (lunedì) a 6 (domenica), salvati nella
scheda come testo "0,2,4".

Le proposte di partenza distanziano gli allenamenti: con 3 giorni lunedì,
mercoledì e venerdì lasciano sempre un giorno di recupero in mezzo. Restano
proposte: l'utente sceglie i giorni che gli servono.
"""

from __future__ import annotations

DEFAULT_WEEKDAYS: dict[int, tuple[int, ...]] = {
    1: (0,),
    2: (0, 3),
    3: (0, 2, 4),
    4: (0, 1, 3, 4),
    5: (0, 1, 2, 3, 4),
    6: (0, 1, 2, 3, 4, 5),
    7: (0, 1, 2, 3, 4, 5, 6),
}


class ScheduleError(ValueError):
    """Giorni non validi."""


def default_for(days_per_week: int) -> list[int]:
    return list(DEFAULT_WEEKDAYS.get(min(max(days_per_week, 1), 7), DEFAULT_WEEKDAYS[3]))


def normalize(weekdays: list[int]) -> list[int]:
    """Giorni ordinati e senza doppioni; almeno uno, al massimo sette."""
    giorni = sorted(set(weekdays))
    if not giorni:
        raise ScheduleError("Scegli almeno un giorno di allenamento.")
    if any(g < 0 or g > 6 for g in giorni):
        raise ScheduleError("I giorni vanno da lunedì (0) a domenica (6).")
    return giorni


def parse(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    try:
        return normalize([int(x) for x in raw.split(",") if x.strip()])
    except (ValueError, ScheduleError):
        return None


def serialize(weekdays: list[int]) -> str:
    return ",".join(str(g) for g in normalize(weekdays))
