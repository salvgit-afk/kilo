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
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

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
        """Gli alimenti USDA sono generici e curati in laboratorio; quelli
        wger sono prodotti di marca inseriti dagli utenti."""
        return self.ingredient.source == IngredientSource.USDA

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


def search_foods(db: Session, query: str, *, limit: int = 15) -> list[FoodSearchResult]:
    """Cerca un alimento su USDA e wger, restituendo i candidati da scegliere.

    Deliberatamente **non** seleziona il risultato migliore: la scelta spetta
    all'utente. È la differenza fra un conteggio e una stima — e protegge
    anche dal problema noto dei dati crowd-sourced, dove voci con lo stesso
    nome hanno valori molto diversi.
    """
    query = (query or "").strip()
    if not query:
        return []

    from app.services import translation

    # USDA non capisce l'italiano: "petto di pollo" diventa "chicken breast"
    # solo per USDA; Open Food Facts riceve la ricerca originale.
    inglese = translation.query_to_english(db, query, allow_llm=False) or query
    trovati = catalog_sync.search_and_cache_ingredients(
        db, query, limit=max(limit, 20), usda_query=inglese if inglese != query.lower() else None
    )

    risultati = [
        FoodSearchResult(
            ingredient=ing,
            kcal_100g=ing.kcal_100g or 0.0,
            protein_100g=ing.protein_100g or 0.0,
            carbs_100g=ing.carbs_100g or 0.0,
            fat_100g=ing.fat_100g or 0.0,
            source_label=(
                "generico (USDA)"
                if ing.source == IngredientSource.USDA
                else "prodotto di marca"
            ),
        )
        for ing in trovati
    ]

    # L'ordine è: **prima la fonte, poi la pertinenza**.
    #
    # Ordinare per sola pertinenza sembra più intelligente ma peggiora il
    # risultato: le voci crowd-sourced hanno nomi identici alla ricerca
    # ("banana") e battono i nomi descrittivi di USDA ("Bananas, raw"),
    # portando in cima proprio le voci meno affidabili — nei dati reali
    # compaiono una "banana" da 0 kcal e un "olive oil" da 0 kcal.
    #
    # Dentro il gruppo degli alimenti generici il punteggio serve invece a
    # evitare l'altro difetto: cercando "chicken breast", USDA propone per
    # primo "Chicken breast tenders, breaded" anziché il petto semplice.
    from app.services.recipe_analyzer import score_match

    risultati.sort(
        key=lambda r: (
            not r.is_generic,
            -score_match(inglese if r.is_generic else query, r.ingredient.name),
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
    ingrediente = Ingredient(
        source=IngredientSource.OFF,
        source_id=codice,
        barcode=codice,
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
    db.commit()
    db.refresh(ingrediente)
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
    return {
        IngredientSource.USDA: "generico (USDA)",
        IngredientSource.OFF: "codice a barre · Open Food Facts",
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
