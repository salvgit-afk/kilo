"""Quando aumentare il carico: la doppia progressione, con il RIR.

Regola delle fonti (`resistance_training_acsm.md`): quando si superano le
ripetizioni previste, aumentare il carico del 2-10%. Per l'ipertrofia si
lavora a 1-3 ripetizioni dal cedimento (`rest_periods_and_rir.md`), e il
RIR segnato serie per serie dice se le ripetizioni sono arrivate con il
margine previsto o "tirate".

Si guarda l'ultima sessione dell'esercizio, le serie al carico più alto:

- tutte al massimo del range, con un margine non più di un'unità sotto il
  RIR previsto (o senza RIR segnato): si sale di carico;
- tutte al massimo del range ma al cedimento o quasi (RIR di 2 o più sotto
  il previsto): si resta, il carico è già impegnativo;
- tutte sotto il minimo del range: il carico è troppo alto, si scende;
- altrimenti: stesso carico, una ripetizione in più.

Il passo è il 5% del carico per i multi-articolari (almeno 2,5 kg, il disco
più piccolo di solito), e un passo piccolo per gli esercizi d'isolamento,
dove il 5% di un manubrio leggero non esiste: 1 kg sotto i 10 kg, 2 kg fino
a 20, poi 2,5.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import SessionSet


@dataclass
class Suggestion:
    # "carico" (sali), "ripetizioni" (una in più), "mantieni", "scendi"
    kind: str
    weight_kg: float | None
    reps: int
    text: str
    reason: str


def _kg(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def step(weight_kg: float, is_compound: bool) -> float:
    if weight_kg <= 0:
        return 0.0
    if is_compound:
        return max(2.5, round(weight_kg * 0.05 / 2.5) * 2.5)
    if weight_kg < 10:
        return 1.0
    return 2.0 if weight_kg < 20 else 2.5


def suggest(
    sets: list[SessionSet],
    *,
    reps_min: int,
    reps_max: int,
    target_rir: int,
    is_compound: bool,
) -> Suggestion | None:
    """Cosa fare la prossima volta, dalle serie dell'ultima sessione."""
    valide = [s for s in sets if s.reps and s.reps > 0]
    if not valide:
        return None
    carico = max(s.weight_kg or 0.0 for s in valide)
    serie = [s for s in valide if (s.weight_kg or 0.0) == carico]
    ripetizioni = [s.reps for s in serie]
    rir = [s.rir for s in serie if s.rir is not None]
    margine_minimo = min(rir) if rir else None

    if all(r >= reps_max for r in ripetizioni):
        tirate = margine_minimo is not None and margine_minimo <= target_rir - 2
        # Oltre il range di 2 ripetizioni si sale comunque (ACSM: +1-2 ripetizioni).
        if tirate and not all(r >= reps_max + 2 for r in ripetizioni):
            return Suggestion(
                kind="mantieni",
                weight_kg=carico or None,
                reps=reps_max,
                text=f"Resta a {_kg(carico)} kg" if carico else f"Resta a {reps_max} ripetizioni",
                reason=(
                    f"Hai chiuso il range, ma a RIR {margine_minimo} invece di {target_rir}: "
                    "ripetilo con più margine, poi sali."
                ),
            )
        if carico <= 0:
            return Suggestion(
                kind="carico",
                weight_kg=None,
                reps=reps_min,
                text="Aggiungi un po' di carico",
                reason=f"Tutte le serie a {reps_max} ripetizioni a corpo libero: è il momento di zavorrarle.",
            )
        nuovo = round(carico + step(carico, is_compound), 2)
        return Suggestion(
            kind="carico",
            weight_kg=nuovo,
            reps=reps_min,
            text=f"Prova {_kg(nuovo)} kg",
            reason=(
                f"L'ultima volta tutte le serie a {reps_max} ripetizioni con {_kg(carico)} kg: "
                f"sali e riparti da {reps_min}. Se il salto è troppo, usa il più piccolo che hai."
            ),
        )

    if all(r < reps_min for r in ripetizioni) and carico > 0:
        nuovo = max(0.0, round(carico - step(carico, is_compound), 2))
        return Suggestion(
            kind="scendi",
            weight_kg=nuovo,
            reps=reps_min,
            text=f"Scendi a {_kg(nuovo)} kg",
            reason=(
                f"L'ultima volta sotto le {reps_min} ripetizioni in tutte le serie: con un carico "
                "più leggero resti nel range previsto."
            ),
        )

    obiettivo = min(reps_max, min(ripetizioni) + 1)
    return Suggestion(
        kind="ripetizioni",
        weight_kg=carico or None,
        reps=obiettivo,
        text=f"{_kg(carico)} kg × {obiettivo}" if carico else f"{obiettivo} ripetizioni",
        reason=f"Stesso carico, una ripetizione in più: quando arrivi a {reps_max} in tutte le serie, sali.",
    )
