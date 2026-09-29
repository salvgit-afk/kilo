"""Alimenti italiani dalle Tabelle di composizione del CREA.

Il CREA Centro di ricerca Alimenti e Nutrizione pubblica i valori di circa
900 alimenti consumati in Italia, con il nome italiano e la porzione tipica.
Rispetto a USDA e CIQUAL ha due vantaggi pratici: la ricerca in italiano
trova l'alimento direttamente ("prosciutto crudo", senza traduzione), e la
porzione standard diventa la quantità proposta nel diario.

I dati stanno in `app/data/crea_2019.json` (generato da
`scripts/build_crea.py` leggendo alimentinutrizione.it) e finiscono in
`ingredients` con `source = "crea"`. Condizioni del CREA: riproduzione e uso
consentiti citando la fonte, "CREA Centro di ricerca Alimenti e Nutrizione".
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientSource

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "crea_2019.json"
ATTRIBUTION = "CREA Centro di ricerca Alimenti e Nutrizione"


@lru_cache(maxsize=1)
def records() -> tuple[dict, ...]:
    return tuple(json.loads(DATA_FILE.read_text(encoding="utf-8"))["alimenti"])


def fields(voce: dict) -> dict:
    return dict(
        source=IngredientSource.CREA,
        source_id=voce["id"],
        name=voce["name"][:255],
        kcal_100g=voce["kcal"],
        protein_100g=voce["protein"],
        carbs_100g=voce["carbs"],
        fat_100g=voce["fat"],
        sugars_100g=voce.get("sugars"),
        fiber_100g=voce.get("fiber"),
        saturated_fat_100g=voce.get("saturated"),
        portion_g=voce.get("portion_g"),
    )


def sync(db: Session) -> int:
    """Inserisce o aggiorna tutti gli alimenti CREA. Restituisce quanti nuovi."""
    esistenti = {
        i.source_id: i
        for i in db.scalars(select(Ingredient).where(Ingredient.source == IngredientSource.CREA))
    }
    nuovi = 0
    for voce in records():
        campi = fields(voce)
        riga = esistenti.get(voce["id"])
        if riga is None:
            db.add(Ingredient(**campi))
            nuovi += 1
        else:
            for k, v in campi.items():
                setattr(riga, k, v)
    db.commit()
    return nuovi


# Articoli e preposizioni che non aiutano a trovare l'alimento.
_VUOTE = frozenset("di da del della dei delle al allo alla ai agli alle con in e il lo la i gli le un una".split())


def _parole(testo: str) -> list[str]:
    # Gli accenti si tolgono solo per decidere le parole: nel database i
    # nomi restano accentati, e si cerca con la radice senza l'ultima vocale
    # ("uova" trova "uovo", "mele" trova "mela").
    senza = unicodedata.normalize("NFKD", (testo or "").lower())
    senza = "".join(c for c in senza if not unicodedata.combining(c))
    parole = [p for p in re.findall(r"[a-z]+", senza) if p not in _VUOTE and len(p) > 1]
    return [p[:-1] if len(p) > 4 else p for p in parole]


def search(db: Session, query: str, *, limit: int = 20) -> list[Ingredient]:
    """Alimenti CREA il cui nome contiene tutte le parole della ricerca in
    italiano; se nessuno, si riprova togliendone una alla volta."""
    parole = _parole(query)
    if not parole:
        return []
    trovati = _con_tutte(db, parole, limit)
    if not trovati and len(parole) > 1:
        for tolta in range(len(parole)):
            trovati += _con_tutte(db, parole[:tolta] + parole[tolta + 1 :], limit)
        trovati = list({i.id: i for i in trovati}.values())
    return trovati


def _con_tutte(db: Session, parole: list[str], limit: int) -> list[Ingredient]:
    return list(
        db.scalars(
            select(Ingredient)
            .where(
                Ingredient.source == IngredientSource.CREA,
                and_(*[Ingredient.name.ilike(f"%{p}%") for p in parole]),
            )
            .order_by(Ingredient.name)
            .limit(limit * 3)
        )
    )
