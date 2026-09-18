"""Diario alimentare: cerca un alimento, pesalo, aggiungilo al pasto.

È il flusso del contacalorie classico, ed è **la via precisa** del progetto:
l'utente conferma quale alimento è e quanti grammi ne mangia, quindi non
resta nessuna approssimazione da indovinare. I suggerimenti di ricette
(`meal_suggestions`) servono a un altro scopo — trovare idee — e portano con
sé una stima nutrizionale, non un conteggio.

Precisione dei dati sottostanti, misurata su valori di riferimento noti:
USDA restituisce valori esatti o entro l'1% per la maggior parte degli
alimenti generici. La qualità è quindi confrontabile con quella dei
contacalorie commerciali, che usano la stessa fonte.

Due accortezze che rendono affidabile il conteggio nel tempo:

  1. i valori nutrizionali vengono **copiati** nel pasto al momento della
     registrazione (vedi `MealItem`), così lo storico non cambia se il
     catalogo viene risincronizzato;
  2. la ricerca **non sceglie per l'utente**: restituisce i candidati con i
     loro valori in vista, perché una voce sbagliata si riconosce a colpo
     d'occhio dai numeri (un "petto di pollo" da 65 kcal e 3 g di proteine è
     palesemente un errore di chi l'ha inserita).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Ingredient, IngredientSource, MealItem, MealLog, UserProfile
from app.services import catalog_sync
from app.services.nutrition_targets import NutritionTargets

logger = logging.getLogger("food_diary")

# Porzione predefinita quando l'utente non indica i grammi.
DEFAULT_QUANTITY_G = 100.0


@dataclass
class FoodSearchResult:
    """Candidato da mostrare nella ricerca, con i valori già visibili."""

    ingredient: Ingredient
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float
    source_label: str

    @property
    def is_generic(self) -> bool:
        """Gli alimenti USDA sono generici e curati in laboratorio, tranne i
        prodotti di marca americani che USDA elenca con la marca in maiuscolo
        ("Kefir, lowfat, strawberry, LIFEWAY")."""
        return self.ingredient.source == IngredientSource.USDA and not usda_brand(
            self.ingredient.name
        )

    def macros_for(self, grams: float) -> dict[str, float]:
        fattore = grams / 100.0
        return {
            "kcal": self.kcal_100g * fattore,
            "protein_g": self.protein_100g * fattore,
            "carbs_g": self.carbs_100g * fattore,
            "fat_g": self.fat_100g * fattore,
        }


@dataclass
class DailyTotals:
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugars_g: float = 0.0

    def remaining_against(self, targets: NutritionTargets) -> dict[str, float]:
        """Quanto manca ai target di giornata (negativo = superato)."""
        return {
            "kcal": targets.target_kcal - self.kcal,
            "protein_g": targets.protein_g - self.protein_g,
            "carbs_g": targets.carbs_g - self.carbs_g,
            "fat_g": targets.fat_g - self.fat_g,
            "fiber_g": targets.fiber_g - self.fiber_g,
        }

    def progress_against(self, targets: NutritionTargets) -> dict[str, float]:
        """Quota di ciascun target già raggiunta (1.0 = target centrato)."""
        return {
            "kcal": self.kcal / targets.target_kcal if targets.target_kcal else 0.0,
            "protein_g": self.protein_g / targets.protein_g if targets.protein_g else 0.0,
            "carbs_g": self.carbs_g / targets.carbs_g if targets.carbs_g else 0.0,
            "fat_g": self.fat_g / targets.fat_g if targets.fat_g else 0.0,
        }


# Parole in maiuscolo che USDA usa senza che indichino una marca.
_NON_MARCHE = {"NFS", "UHT", "USDA", "NS", "RTE", "RTF"}


def usda_brand(name: str) -> bool:
    """Vero per le voci USDA che sono prodotti di marca americani.

    USDA elenca alcuni prodotti confezionati con la marca in maiuscolo in
    fondo al nome ("Kefir, lowfat, plain, LIFEWAY"). Non sono alimenti
    generici e non si trovano nei supermercati italiani.
    """
    return any(
        len(parola) >= 3 and parola not in _NON_MARCHE
        for parola in re.findall(r"\b[A-Z][A-Z'&]{2,}\b", name or "")
    )


# Quanti alimenti generici prima dei prodotti italiani.
MAX_GENERIC_FIRST = 5

OFF_SEARCH_CACHE = "off_search"
# I prodotti in vendita cambiano lentamente: una settimana tiene basso il
# numero di ricerche verso Open Food Facts senza mostrare dati vecchi.
OFF_SEARCH_TTL = dt.timedelta(days=7)


def _store_off_product(db: Session, prodotto, *, commit: bool = True) -> Ingredient:
    """Salva (o riusa) un prodotto Open Food Facts, identificato dal codice.

    La ricerca per nome e la scansione condividono le righe: un prodotto
    trovato cercando si scansiona poi all'istante, e viceversa.
    """
    esistente = db.scalar(
        select(Ingredient).where(
            Ingredient.barcode == prodotto.barcode, Ingredient.source == IngredientSource.OFF
        )
    )
    if esistente is not None:
        return esistente
    ingrediente = Ingredient(
        source=IngredientSource.OFF,
        source_id=prodotto.barcode,
        barcode=prodotto.barcode,
        name=prodotto.name,
        kcal_100g=prodotto.kcal_100g,
        protein_100g=prodotto.protein_100g,
        carbs_100g=prodotto.carbs_100g,
        fat_100g=prodotto.fat_100g,
        sugars_100g=prodotto.sugars_100g,
        fiber_100g=prodotto.fiber_100g,
        saturated_fat_100g=prodotto.saturated_fat_100g,
    )
    db.add(ingrediente)
    if commit:
        db.commit()
        db.refresh(ingrediente)
    else:
        db.flush()
    return ingrediente


def _italian_products(db: Session, query: str, *, limit: int) -> list[Ingredient] | None:
    """Prodotti venduti in Italia da Open Food Facts, con cache di 7 giorni.

    `None` quando Open Food Facts non è utilizzabile (rete, soglia al
    minuto): chi chiama ripiega su un'altra fonte.
    """
    from app.models import LlmCache
    from app.services import off_client

    chiave = " ".join(query.lower().split())[:200]
    riga = db.scalar(
        select(LlmCache).where(LlmCache.kind == OFF_SEARCH_CACHE, LlmCache.key == chiave)
    )
    if riga is not None:
        creata = riga.created_at
        if creata is not None and creata.tzinfo is None:
            creata = creata.replace(tzinfo=dt.timezone.utc)
        if creata is None or dt.datetime.now(dt.timezone.utc) - creata < OFF_SEARCH_TTL:
            ids = riga.payload.get("ids") or []
            trovati = {i.id: i for i in db.scalars(select(Ingredient).where(Ingredient.id.in_(ids)))}
            return [trovati[i] for i in ids if i in trovati][:limit]

    try:
        prodotti = off_client.search_products(query, limit=limit)
    except off_client.OffError as e:
        logger.info("Ricerca Open Food Facts non disponibile per %r: %s", query, e)
        return None

    ingredienti = [_store_off_product(db, p, commit=False) for p in prodotti]
    if riga is not None:
        db.delete(riga)
        db.flush()
    db.add(LlmCache(kind=OFF_SEARCH_CACHE, key=chiave, payload={"ids": [i.id for i in ingredienti]}))
    db.commit()
    return ingredienti


# Parole che indicano già uno stato o una cottura: non si aggiunge "raw".
_STATE_WORDS = {"raw", "cooked", "boiled", "dry", "fried", "roasted", "grilled", "canned", "frozen"}

# Parole della ricerca inglese che non identificano l'alimento.
_FILLER_EN = {"of", "with", "and", "the", "raw", "fresh", "whole"}


def _radice_en(parola: str) -> str:
    """"oats" trova "Oat bran", "tomatoes" trova "Tomato"."""
    parola = parola.lower()
    if len(parola) > 4 and parola.endswith("oes"):
        return parola[:-2]
    if len(parola) > 3 and parola.endswith("s") and not parola.endswith("ss"):
        return parola[:-1]
    return parola


def pertinente(inglese: str, nome: str) -> bool:
    """Tutte le parole cercate compaiono nel nome, a inizio parola.

    Toglie i risultati che USDA aggiunge per somiglianza ("Candies,
    confectioner's coating, yogurt" cercando "greek yogurt").
    """
    parole = [_radice_en(p) for p in re.findall(r"[a-z]+", inglese.lower()) if p not in _FILLER_EN]
    testo = (nome or "").lower()
    return all(re.search(rf"\b{re.escape(p)}", testo) for p in parole)


def _usda_and_fallback(
    db: Session, query: str, inglese: str, *, limit: int, with_fallback: bool
) -> tuple[list[Ingredient], list[Ingredient]]:
    """Alimenti USDA e, se richiesto, i prodotti wger di riserva."""
    from app.services import usda_client

    usda_grezzi, wger_grezzi = catalog_sync.fetch_raw_ingredients(
        query,
        limit=limit,
        include_branded=with_fallback,
        usda_query=inglese if inglese != query.lower() else None,
    )
    # Con una parola sola USDA mette in cima i derivati: per "rice" cracker,
    # farina e crusca, e il riso vero non compare. La stessa ricerca con
    # "raw" porta l'alimento base; i risultati estranei che si porta dietro
    # ("Apricots, raw") li toglie poi il filtro sulle parole cercate.
    parole = inglese.split()
    if len(parole) == 1 and parole[0] not in _STATE_WORDS and get_settings().usda_configured:
        try:
            usda_grezzi = usda_client.search_foods(f"{parole[0]} raw", limit=10) + usda_grezzi
        except usda_client.UsdaError as e:
            logger.info("Ricerca USDA aggiuntiva fallita per %r: %s", inglese, e)
    visti: set[str] = set()
    usda_grezzi = [f for f in usda_grezzi if not (f.name in visti or visti.add(f.name))]
    usda = catalog_sync.store_raw_ingredients(db, usda_grezzi, [])
    riserva = catalog_sync.store_raw_ingredients(db, [], wger_grezzi) if wger_grezzi else []
    return usda, riserva


def search_foods(db: Session, query: str, *, limit: int = 15) -> list[FoodSearchResult]:
    """Cerca un alimento e restituisce i candidati da scegliere, in tre gruppi.

    1. **Alimenti generici USDA** ("petto di pollo crudo"): valori di
       laboratorio, i più affidabili per un alimento non confezionato.
    2. **Prodotti venduti in Italia** da Open Food Facts, i più scansionati
       per primi, con marca e formato nel nome ("Kefir · Milbona (464 ml)").
    3. **Prodotti di marca americani** che USDA elenca insieme ai generici:
       in fondo, perché difficilmente sono quelli che si hanno in casa.

    Le voci con lo stesso nome e le stesse calorie compaiono una volta sola.
    Deliberatamente **non** seleziona il risultato migliore: la scelta spetta
    all'utente, con i valori nutrizionali visibili accanto a ogni voce.
    """
    query = (query or "").strip()
    if not query:
        return []

    from app.services import translation
    from app.services.recipe_analyzer import score_match

    # USDA non capisce l'italiano: "petto di pollo" diventa "chicken breast"
    # solo per USDA; Open Food Facts riceve la ricerca originale.
    inglese = translation.query_to_english(db, query, allow_llm=False) or query
    italiani = _italian_products(db, query, limit=limit) if len(query) >= 3 else []
    # wger (vecchia copia mondiale di Open Food Facts, senza marche nel nome)
    # solo se la ricerca italiana non ha risposto.
    usda, riserva = _usda_and_fallback(
        db, query, inglese, limit=max(limit, 20), with_fallback=italiani is None
    )

    generici = sorted(
        (i for i in usda if not usda_brand(i.name) and pertinente(inglese, i.name)),
        key=lambda i: -score_match(inglese, i.name),
    )
    americani = [i for i in usda if usda_brand(i.name) and pertinente(inglese, i.name)]
    # I generici più pertinenti in cima, poi i prodotti in vendita in Italia,
    # poi il resto dei generici: una lista di varianti USDA non deve spingere
    # i prodotti di casa fuori dallo schermo.
    ordinati = (
        generici[:MAX_GENERIC_FIRST] + (italiani or []) + generici[MAX_GENERIC_FIRST:]
        + riserva + americani
    )

    risultati: list[FoodSearchResult] = []
    visti: set[tuple[str, int]] = set()
    for ing in ordinati:
        firma = (" ".join((ing.name or "").lower().split()), round(ing.kcal_100g or 0))
        if firma in visti:
            continue
        visti.add(firma)
        risultati.append(
            FoodSearchResult(
                ingredient=ing,
                kcal_100g=ing.kcal_100g or 0.0,
                protein_100g=ing.protein_100g or 0.0,
                carbs_100g=ing.carbs_100g or 0.0,
                fat_100g=ing.fat_100g or 0.0,
                source_label=source_label(ing),
            )
        )
    return risultati


# --- Codice a barre --------------------------------------------------------------


@dataclass
class BarcodeLookup:
    ingredient: Ingredient
    cached: bool  # True = trovato in cache, nessuna chiamata a Open Food Facts


def lookup_barcode(db: Session, raw_barcode: str, *, user_id: int) -> BarcodeLookup:
    """Prodotto dal codice a barre: prima la cache, poi Open Food Facts.

    Ordine: il prodotto che l'utente stesso ha inserito a mano (è la sua
    etichetta), poi quello già letto da Open Food Facts, poi la chiamata.
    Solleva `ValueError` (codice non valido), `off_client.ProductNotFound`,
    `off_client.IncompleteProduct` o `off_client.OffError`.
    """
    from app.services import off_client

    codice = off_client.normalize_barcode(raw_barcode)
    proprio = db.scalar(
        select(Ingredient).where(
            Ingredient.barcode == codice,
            Ingredient.source == IngredientSource.MANUAL,
            Ingredient.created_by_user_id == user_id,
        ).order_by(Ingredient.id.desc())
    )
    if proprio is not None:
        return BarcodeLookup(proprio, cached=True)

    in_cache = db.scalar(
        select(Ingredient).where(
            Ingredient.barcode == codice, Ingredient.source == IngredientSource.OFF
        )
    )
    if in_cache is not None:
        return BarcodeLookup(in_cache, cached=True)

    prodotto = off_client.get_product(codice)
    ingrediente = _store_off_product(db, prodotto)
    return BarcodeLookup(ingrediente, cached=False)


def create_manual_product(
    db: Session,
    *,
    user_id: int,
    name: str,
    kcal_100g: float,
    protein_100g: float,
    carbs_100g: float,
    fat_100g: float,
    barcode: str | None = None,
) -> Ingredient:
    """Prodotto inserito dall'etichetta, visibile solo a chi lo inserisce."""
    from app.services import off_client

    codice = off_client.normalize_barcode(barcode) if barcode else None
    if protein_100g + carbs_100g + fat_100g > 100.5:
        raise ValueError("Proteine, carboidrati e grassi insieme non possono superare 100 g su 100 g.")
    ingrediente = Ingredient(
        source=IngredientSource.MANUAL,
        source_id=codice,
        barcode=codice,
        name=name.strip()[:255],
        kcal_100g=kcal_100g,
        protein_100g=protein_100g,
        carbs_100g=carbs_100g,
        fat_100g=fat_100g,
        created_by_user_id=user_id,
    )
    db.add(ingrediente)
    db.commit()
    db.refresh(ingrediente)
    return ingrediente


def source_label(ingredient: Ingredient) -> str:
    if ingredient.source == IngredientSource.USDA and usda_brand(ingredient.name):
        return "prodotto USA (USDA)"
    return {
        IngredientSource.USDA: "generico (USDA)",
        IngredientSource.OFF: "prodotto di marca · Open Food Facts",
        IngredientSource.MANUAL: "inserito da te",
    }.get(ingredient.source, "prodotto di marca")


def get_or_create_meal(
    db: Session,
    profile: UserProfile,
    *,
    date: dt.date | None = None,
    meal_type: str = "lunch",
) -> MealLog:
    """Recupera il pasto del giorno, creandolo se non esiste."""
    date = date or dt.date.today()
    meal = db.scalar(
        select(MealLog).where(
            MealLog.profile_id == profile.id,
            MealLog.date == date,
            MealLog.meal_type == meal_type,
        )
    )
    if meal is not None:
        return meal

    meal = MealLog(
        profile_id=profile.id, date=date, meal_type=meal_type, servings=1.0
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal


def add_food(
    db: Session, meal: MealLog, ingredient: Ingredient, *, grams: float = DEFAULT_QUANTITY_G
) -> MealItem:
    """Aggiunge un alimento pesato al pasto.

    I valori nutrizionali vengono calcolati qui e **salvati nella riga**: il
    conteggio di oggi non deve cambiare se domani il catalogo viene
    risincronizzato.
    """
    if grams <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")

    fattore = grams / 100.0
    item = MealItem(
        meal_log_id=meal.id,
        ingredient_id=ingredient.id,
        name=ingredient.name,
        quantity_g=grams,
        kcal=(ingredient.kcal_100g or 0.0) * fattore,
        protein_g=(ingredient.protein_100g or 0.0) * fattore,
        carbs_g=(ingredient.carbs_100g or 0.0) * fattore,
        fat_g=(ingredient.fat_100g or 0.0) * fattore,
        fiber_g=(ingredient.fiber_100g or 0.0) * fattore if ingredient.fiber_100g else None,
        sugars_g=(ingredient.sugars_100g or 0.0) * fattore if ingredient.sugars_100g else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_quantity(db: Session, item: MealItem, grams: float) -> MealItem:
    """Corregge la quantità, riscalando i valori già salvati.

    Si riparte dai valori memorizzati nella riga, non dal catalogo: se
    l'alimento nel frattempo è cambiato, correggere i grammi non deve
    cambiare anche i valori nutrizionali di ciò che è già stato mangiato.
    """
    if grams <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")

    fattore = grams / item.quantity_g
    item.quantity_g = grams
    item.kcal *= fattore
    item.protein_g *= fattore
    item.carbs_g *= fattore
    item.fat_g *= fattore
    if item.fiber_g is not None:
        item.fiber_g *= fattore
    if item.sugars_g is not None:
        item.sugars_g *= fattore

    db.commit()
    db.refresh(item)
    return item


def remove_food(db: Session, item: MealItem) -> None:
    db.delete(item)
    db.commit()


def meal_totals(meal: MealLog) -> DailyTotals:
    """Somma degli alimenti di un pasto."""
    totali = DailyTotals()
    for item in meal.items:
        totali.kcal += item.kcal
        totali.protein_g += item.protein_g
        totali.carbs_g += item.carbs_g
        totali.fat_g += item.fat_g
        totali.fiber_g += item.fiber_g or 0.0
        totali.sugars_g += item.sugars_g or 0.0
    return totali


def daily_totals(
    db: Session, profile: UserProfile, *, date: dt.date | None = None
) -> DailyTotals:
    """Somma di tutti i pasti di una giornata.

    Include sia gli alimenti pesati sia i pasti liberi con macro inseriti a
    mano, così il totale resta corretto anche per chi non modella tutto.
    """
    date = date or dt.date.today()
    pasti = db.scalars(
        select(MealLog).where(
            MealLog.profile_id == profile.id,
            MealLog.date == date,
            MealLog.is_planned.is_(False),
        )
    ).all()

    totali = DailyTotals()
    for pasto in pasti:
        parziale = meal_totals(pasto)
        totali.kcal += parziale.kcal
        totali.protein_g += parziale.protein_g
        totali.carbs_g += parziale.carbs_g
        totali.fat_g += parziale.fat_g
        totali.fiber_g += parziale.fiber_g
        totali.sugars_g += parziale.sugars_g

        # Pasto libero: macro dichiarati direttamente, senza alimenti pesati.
        if not pasto.items and pasto.kcal is not None:
            porzioni = pasto.servings or 1.0
            totali.kcal += pasto.kcal * porzioni
            totali.protein_g += (pasto.protein_g or 0.0) * porzioni
            totali.carbs_g += (pasto.carbs_g or 0.0) * porzioni
            totali.fat_g += (pasto.fat_g or 0.0) * porzioni

    return totali
