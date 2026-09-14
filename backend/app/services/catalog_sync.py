"""Popolamento delle tabelle di cache locali (esercizi e ingredienti).

Perché una cache invece di chiamare le API a ogni richiesta:

  - il catalogo esercizi wger cambia raramente ma pesa ~10 richieste
    paginate: rifarlo a ogni generazione di scheda sarebbe uno spreco;
  - una scheda deve poter essere generata anche se wger è momentaneamente
    irraggiungibile (i server pubblici sono volontari, non hanno SLA);
  - permette join e filtri SQL (per gruppo muscolare, attrezzatura) che
    sull'API si pagherebbero in round-trip.

Le funzioni sono **idempotenti**: rieseguirle aggiorna i record esistenti
invece di duplicarli.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Exercise, Ingredient, IngredientSource
from app.services import usda_client, wger_client
from app.services.usda_client import RawUsdaFood
from app.services.wger_client import RawIngredient

logger = logging.getLogger("catalog_sync")


@dataclass
class SyncResult:
    fetched: int
    created: int
    updated: int
    skipped_no_muscle: int

    @property
    def stored(self) -> int:
        return self.created + self.updated


def sync_exercises(db: Session, *, preferred_lang: int = wger_client.LANG_IT) -> SyncResult:
    """Scarica il catalogo esercizi wger e lo riversa in `exercises`.

    Gli esercizi **senza gruppo muscolare primario** vengono scartati: circa
    il 16% del catalogo ne è privo, e senza quel dato un esercizio non è
    utilizzabile per costruire una scheda mirata a un gruppo muscolare (che è
    tutto lo scopo del generatore).
    """
    raw_exercises = wger_client.fetch_exercises(preferred_lang=preferred_lang)

    existing = {
        ex.wger_id: ex
        for ex in db.scalars(select(Exercise).where(Exercise.wger_id.is_not(None)))
    }

    created = updated = skipped = 0
    for raw in raw_exercises:
        if not raw.primary_muscles:
            skipped += 1
            continue

        fields = dict(
            name=raw.name,
            primary_muscle=raw.primary_muscles[0],
            secondary_muscles=", ".join(raw.secondary_muscles) or None,
            equipment=", ".join(raw.equipment) or None,
            category=raw.category,
            description=raw.description,
            image_url=raw.image_url,
            is_compound=raw.is_compound,
        )

        current = existing.get(raw.wger_id)
        if current is None:
            db.add(Exercise(wger_id=raw.wger_id, **fields))
            created += 1
        else:
            for key, value in fields.items():
                setattr(current, key, value)
            updated += 1

    db.commit()
    logger.info(
        "Sync esercizi: %d scaricati, %d nuovi, %d aggiornati, %d scartati (senza muscolo)",
        len(raw_exercises), created, updated, skipped,
    )
    return SyncResult(
        fetched=len(raw_exercises),
        created=created,
        updated=updated,
        skipped_no_muscle=skipped,
    )


def _upsert_ingredient(
    db: Session, *, source: str, source_id: str, name: str, macros: dict, commit: bool = True
) -> Ingredient:
    """Inserisce o aggiorna un ingrediente, identificato da (fonte, id fonte).

    Gli ingredienti si importano **su richiesta** e non in blocco: wger conta
    oltre un milione di voci e USDA centinaia di migliaia. Si salva solo ciò
    che entra davvero in una ricetta o in un pasto registrato.

    Con `commit=False` si limita a un flush (serve l'id): chi importa molti
    ingredienti insieme fa un solo commit alla fine, invece di pagarne uno
    per voce sul database remoto.
    """
    existing = db.scalar(
        select(Ingredient).where(
            Ingredient.source == source, Ingredient.source_id == source_id
        )
    )

    fields = {"name": name, **macros}

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        if commit:
            db.commit()
        return existing

    ingredient = Ingredient(source=source, source_id=source_id, **fields)
    db.add(ingredient)
    if commit:
        db.commit()
        db.refresh(ingredient)
    else:
        db.flush()
    return ingredient


def upsert_wger_ingredient(db: Session, raw: RawIngredient, *, commit: bool = True) -> Ingredient:
    """Prodotto confezionato da wger/Open Food Facts."""
    return _upsert_ingredient(
        db,
        commit=commit,
        source=IngredientSource.WGER,
        source_id=str(raw.wger_id),
        # Il nome del prodotto è più utile con la marca, quando c'è.
        name=f"{raw.name} ({raw.brand})" if raw.brand else raw.name,
        macros=dict(
            kcal_100g=raw.kcal_100g,
            protein_100g=raw.protein_100g,
            carbs_100g=raw.carbs_100g,
            fat_100g=raw.fat_100g,
            sugars_100g=raw.sugars_100g,
            fiber_100g=raw.fiber_100g,
            saturated_fat_100g=raw.saturated_fat_100g,
        ),
    )


def upsert_usda_food(db: Session, raw: RawUsdaFood, *, commit: bool = True) -> Ingredient:
    """Alimento generico/grezzo da USDA FoodData Central."""
    return _upsert_ingredient(
        db,
        commit=commit,
        source=IngredientSource.USDA,
        source_id=str(raw.fdc_id),
        name=raw.name,
        macros=dict(
            kcal_100g=raw.kcal_100g,
            protein_100g=raw.protein_100g,
            carbs_100g=raw.carbs_100g,
            fat_100g=raw.fat_100g,
            sugars_100g=raw.sugars_100g,
            fiber_100g=raw.fiber_100g,
            saturated_fat_100g=raw.saturated_fat_100g,
        ),
    )


def search_and_cache_ingredients(
    db: Session,
    name: str,
    *,
    limit: int = 10,
    include_branded: bool = True,
    usda_query: str | None = None,
) -> list[Ingredient]:
    """Cerca un alimento su entrambe le fonti e ne mette in cache i risultati.

    USDA per primo: chi cerca "petto di pollo" mentre compone una ricetta
    vuole l'alimento generico, non uno specifico prodotto confezionato. I
    risultati wger (di marca) seguono, utili quando l'utente registra un
    prodotto preciso che ha in casa.

    `usda_query` permette di interrogare USDA in inglese mantenendo la
    ricerca originale per wger/Open Food Facts, che ha i prodotti italiani.
    """
    usda, wger = fetch_raw_ingredients(
        name, limit=limit, include_branded=include_branded, usda_query=usda_query
    )
    return store_raw_ingredients(db, usda, wger)


def fetch_raw_ingredients(
    name: str,
    *,
    limit: int = 10,
    include_branded: bool = True,
    usda_query: str | None = None,
) -> tuple[list[RawUsdaFood], list[RawIngredient]]:
    """Interroga USDA e wger **in parallelo**, senza toccare il database.

    Non usando la sessione, può girare in un thread: è ciò che permette di
    preparare tutti gli ingredienti di più ricette contemporaneamente.
    Gli errori di rete diventano liste vuote, come nella ricerca sequenziale.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _usda() -> list[RawUsdaFood]:
        if not get_settings().usda_configured:
            return []
        try:
            return usda_client.search_foods(usda_query or name, limit=limit)
        except usda_client.UsdaError as e:
            logger.warning("Ricerca USDA fallita per %r: %s", name, e)
            return []

    def _wger() -> list[RawIngredient]:
        if not include_branded:
            return []
        try:
            return wger_client.search_ingredients(name, limit=limit)
        except wger_client.WgerError as e:
            logger.warning("Ricerca wger fallita per %r: %s", name, e)
            return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        da_usda, da_wger = pool.submit(_usda), pool.submit(_wger)
        return da_usda.result(), da_wger.result()


def store_raw_ingredients(
    db: Session,
    usda: list[RawUsdaFood],
    wger: list[RawIngredient],
    *,
    commit: bool = True,
) -> list[Ingredient]:
    """Salva i risultati grezzi con un unico commit (USDA per primo)."""
    results = [upsert_usda_food(db, food, commit=False) for food in usda]
    results += [upsert_wger_ingredient(db, raw, commit=False) for raw in wger]
    if commit and results:
        # Senza questo, dopo il commit ogni ingrediente verrebbe riletto dal
        # database al primo accesso: decine di query per una sola ricerca.
        precedente = db.expire_on_commit
        db.expire_on_commit = False
        try:
            db.commit()
        finally:
            db.expire_on_commit = precedente
    return results
