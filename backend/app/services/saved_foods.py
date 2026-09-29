"""I miei prodotti: gli alimenti che l'utente ritrova sempre, senza scadenza.

I "recenti" del diario sono una finestra che scorre: servono a ripetere in un
tocco quello che si mangia spesso, ma un prodotto scansionato settimane fa
finisce fuori dalla lista. Chi scansiona una confezione invece la vuole
ritrovare anche quando la confezione non ce l'ha in mano (il pranzo fuori
casa): qui resta finché non la toglie lui.

Entrano da soli i prodotti con codice a barre e quelli inseriti a mano dalla
tabella nutrizionale; gli alimenti generici (mela, riso) solo con la stella.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientSource, SavedFood, UserProfile


def is_own_product(ingredient: Ingredient) -> bool:
    """Prodotto confezionato scansionato o copiato dall'etichetta."""
    return bool(ingredient.barcode) or ingredient.source == IngredientSource.MANUAL


def _riga(db: Session, profile: UserProfile, ingredient: Ingredient) -> SavedFood | None:
    return db.scalar(
        select(SavedFood).where(
            SavedFood.profile_id == profile.id, SavedFood.ingredient_id == ingredient.id
        )
    )


def record_use(db: Session, profile: UserProfile, ingredient: Ingredient, grams: float) -> None:
    """Conta un uso dell'alimento. Non fa commit: decide chi chiama.

    Un prodotto proprio entra in lista al primo uso; un generico viene
    contato solo se l'utente l'ha già salvato con la stella.
    """
    riga = _riga(db, profile, ingredient)
    if riga is None:
        if not is_own_product(ingredient):
            return
        riga = SavedFood(profile_id=profile.id, ingredient_id=ingredient.id, starred=True, uses=0)
        db.add(riga)
    riga.uses = (riga.uses or 0) + 1
    riga.last_grams = grams
    riga.last_used_at = dt.datetime.now(dt.timezone.utc)


def set_starred(
    db: Session, profile: UserProfile, ingredient: Ingredient, starred: bool, *, grams: float | None = None
) -> SavedFood:
    """Aggiunge o toglie un alimento dalla lista, per scelta dell'utente."""
    riga = _riga(db, profile, ingredient)
    if riga is None:
        riga = SavedFood(profile_id=profile.id, ingredient_id=ingredient.id, uses=0, last_grams=grams)
        db.add(riga)
    riga.starred = starred
    if grams and not riga.last_grams:
        riga.last_grams = grams
    db.commit()
    db.refresh(riga)
    return riga


def list_saved(db: Session, profile: UserProfile) -> list[SavedFood]:
    """La lista, dal più usato; a parità, dal più recente."""
    righe = db.scalars(
        select(SavedFood)
        .where(SavedFood.profile_id == profile.id, SavedFood.starred.is_(True))
        .order_by(SavedFood.uses.desc(), SavedFood.last_used_at.desc(), SavedFood.id.desc())
    ).all()
    # `NULLS LAST` non esiste su tutti i database: chi non è mai stato usato
    # ha zero usi e finisce comunque in fondo.
    return list(righe)
