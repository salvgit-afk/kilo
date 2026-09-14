"""Client per TheMealDB (struttura delle ricette).

Gratuito, senza registrazione: la chiave "1" è quella pubblica di test,
inclusa nell'URL base configurato.

**Limite importante di questa fonte** (verificato direttamente sull'API):
le quantità degli ingredienti sono **testo libero pensato per un essere
umano** — "1.2 kg", "¼ cup", "5 thinly sliced", "8 cloves chopped" — non
grammi. Quindi da TheMealDB si prende la *struttura* della ricetta
(quali ingredienti, in che ordine, con che procedimento), mai i valori
nutrizionali, che non fornisce affatto.

La conversione "misura casalinga → grammi" e il calcolo dei macro avvengono
altrove, incrociando gli ingredienti con wger/USDA. È coerente con
`knowledge_base/evidence_conduct.md`: l'LLM può interpretare il linguaggio
("¼ cup di riso" → grammi), ma la somma dei macro la fa il database, perché
i modelli sbagliano l'aritmetica.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger("themealdb_client")

# L'API espone 20 slot fissi strIngredient1..20 / strMeasure1..20.
_MAX_INGREDIENT_SLOTS = 20


class MealDbError(RuntimeError):
    """Chiamata a TheMealDB fallita (rete, timeout, risposta inattesa)."""


@dataclass
class RawRecipeIngredient:
    name: str
    # Quantità come la scrive un umano: va interpretata, non usata com'è.
    measure: str


@dataclass
class RawRecipe:
    meal_id: str
    name: str
    category: str | None
    area: str | None
    instructions: str | None
    thumbnail_url: str | None
    tags: list[str]
    ingredients: list[RawRecipeIngredient]
    youtube_url: str | None = None
    source_url: str | None = None


def _get(path: str, params: dict | None = None, *, timeout: float = 25.0) -> dict:
    base = get_settings().themealdb_base_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/{path.lstrip('/')}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json() or {}
    except Exception as e:
        raise MealDbError(f"Richiesta a TheMealDB fallita ({path}): {e}") from e


def _parse_recipe(meal: dict) -> RawRecipe:
    ingredients: list[RawRecipeIngredient] = []
    for i in range(1, _MAX_INGREDIENT_SLOTS + 1):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if not name:
            continue  # gli slot inutilizzati arrivano vuoti o null
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        ingredients.append(RawRecipeIngredient(name=name, measure=measure))

    raw_tags = (meal.get("strTags") or "").strip()
    return RawRecipe(
        meal_id=str(meal.get("idMeal")),
        name=(meal.get("strMeal") or "").strip(),
        category=(meal.get("strCategory") or "").strip() or None,
        area=(meal.get("strArea") or "").strip() or None,
        instructions=(meal.get("strInstructions") or "").strip() or None,
        thumbnail_url=(meal.get("strMealThumb") or "").strip() or None,
        tags=[t.strip() for t in raw_tags.split(",") if t.strip()],
        ingredients=ingredients,
        youtube_url=(meal.get("strYoutube") or "").strip() or None,
        source_url=(meal.get("strSource") or "").strip() or None,
    )


def _parse_meals(data: dict) -> list[RawRecipe]:
    # L'API restituisce {"meals": null} quando non trova nulla, non una lista vuota.
    return [_parse_recipe(m) for m in (data.get("meals") or [])]


def search_by_name(name: str) -> list[RawRecipe]:
    """Ricette che contengono `name` nel titolo, complete di ingredienti."""
    name = (name or "").strip()
    if not name:
        return []
    return _parse_meals(_get("search.php", {"s": name}))


def lookup(meal_id: str | int) -> RawRecipe | None:
    """Ricetta completa a partire dall'id."""
    recipes = _parse_meals(_get("lookup.php", {"i": str(meal_id)}))
    return recipes[0] if recipes else None


def filter_by_main_ingredient(ingredient: str) -> list[tuple[str, str]]:
    """Ricette che usano un dato ingrediente principale.

    Restituisce solo `(meal_id, nome)`: questo endpoint di TheMealDB non
    include ingredienti né procedimento, serve una `lookup()` per ciascuna.
    """
    ingredient = (ingredient or "").strip()
    if not ingredient:
        return []
    data = _get("filter.php", {"i": ingredient})
    return [
        (str(m.get("idMeal")), (m.get("strMeal") or "").strip())
        for m in (data.get("meals") or [])
    ]


def filter_by_category(category: str) -> list[tuple[str, str]]:
    """Come `filter_by_main_ingredient`, ma per categoria (es. "Chicken",
    "Vegetarian", "Seafood"). Stessa limitazione: serve la lookup."""
    category = (category or "").strip()
    if not category:
        return []
    data = _get("filter.php", {"c": category})
    return [
        (str(m.get("idMeal")), (m.get("strMeal") or "").strip())
        for m in (data.get("meals") or [])
    ]


def list_categories() -> list[str]:
    data = _get("list.php", {"c": "list"})
    return [
        (m.get("strCategory") or "").strip()
        for m in (data.get("meals") or [])
        if (m.get("strCategory") or "").strip()
    ]
