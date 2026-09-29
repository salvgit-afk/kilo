"""Alimenti generici dalla tabella CIQUAL di ANSES (Francia).

Perché accanto a USDA: USDA descrive bene gli alimenti di base, ma pensa
alla dieta americana. CIQUAL ha la cucina europea: formaggi stagionati,
salumi, pane, piatti pronti, con valori di laboratorio di un ente pubblico.

I dati stanno in `app/data/ciqual_2025.json` (generato da
`scripts/build_ciqual.py`) e finiscono nella tabella `ingredients` con
`source = "ciqual"`: la migrazione li carica al deploy, `sync` li aggiorna.
Il nome è quello inglese della tabella; il nome italiano arriva con la stessa
traduzione in cache degli alimenti USDA.

Licenza: Licence Ouverte Etalab 2.0, riuso libero citando la fonte:
"Anses. 2025. Table de composition nutritionnelle des aliments Ciqual".
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientSource

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "ciqual_2025.json"
ATTRIBUTION = "Anses. 2025. Table de composition nutritionnelle des aliments Ciqual"


@lru_cache(maxsize=1)
def records() -> tuple[dict, ...]:
    return tuple(json.loads(DATA_FILE.read_text(encoding="utf-8"))["alimenti"])


def fields(voce: dict) -> dict:
    """Dal record del JSON alle colonne di `ingredients`."""
    return dict(
        source=IngredientSource.CIQUAL,
        source_id=voce["id"],
        name=voce["name"][:255],
        kcal_100g=voce["kcal"],
        protein_100g=voce["protein"],
        carbs_100g=voce["carbs"],
        fat_100g=voce["fat"],
        sugars_100g=voce.get("sugars"),
        fiber_100g=voce.get("fiber"),
        saturated_fat_100g=voce.get("saturated"),
    )


def sync(db: Session) -> int:
    """Inserisce o aggiorna tutti gli alimenti CIQUAL. Restituisce quanti nuovi."""
    esistenti = {
        i.source_id: i
        for i in db.scalars(select(Ingredient).where(Ingredient.source == IngredientSource.CIQUAL))
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


# Parole che non aiutano a trovare l'alimento giusto.
_VUOTE = frozenset("a an and of the with in raw cooked fresh".split())


def search(db: Session, english_query: str, *, limit: int = 20) -> list[Ingredient]:
    """Alimenti CIQUAL il cui nome contiene tutte le parole della ricerca.

    La ricerca arriva già in inglese (come per USDA), tradotta a dizionario:
    una parola italiana che il dizionario non conosce ("prosciutto crudo" ->
    "ham crudo") resta com'è. Se con tutte le parole non si trova niente, si
    riprova togliendone una alla volta. Le parole si cercano anche senza la
    "s" finale: "eggs" trova "egg".
    """
    parole = [
        p.rstrip("s") if len(p) > 3 else p
        for p in re.findall(r"[a-z]+", (english_query or "").lower())
        if p not in _VUOTE and len(p) > 1
    ]
    # CIQUAL scrive "wholemeal", USDA e il dizionario "whole wheat".
    if "whole" in parole and "wheat" in parole:
        parole = [p for p in parole if p != "wheat"]
    if not parole:
        return []
    trovati = _con_tutte(db, parole, limit)
    if not trovati and len(parole) > 1:
        for tolta in range(len(parole)):
            trovati += _con_tutte(db, parole[:tolta] + parole[tolta + 1 :], limit)
        trovati = list({i.id: i for i in trovati}.values())
    return trovati


def _con_tutte(db: Session, parole: list[str], limit: int) -> list[Ingredient]:
    condizioni = [Ingredient.name.ilike(f"%{p}%") for p in parole]
    return list(
        db.scalars(
            select(Ingredient)
            .where(Ingredient.source == IngredientSource.CIQUAL, and_(*condizioni))
            .order_by(Ingredient.name)
            .limit(limit * 3)
        )
    )
