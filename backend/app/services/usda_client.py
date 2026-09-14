"""Client per USDA FoodData Central (alimenti generici e grezzi).

Chiave gratuita self-service, 1000 richieste/ora. Copre il punto debole di
wger/Open Food Facts: gli **alimenti generici non confezionati** ("petto di
pollo crudo", "mela", "lenticchie secche"), dove i dati crowd-sourced di OFF
sono irregolari mentre quelli USDA sono curati in laboratorio.

Divisione dei compiti fra le due fonti:
  - wger/OFF -> prodotti di marca con codice a barre (la pasta X, lo yogurt Y)
  - USDA     -> ingredienti base di una ricetta

Due dettagli dell'API verificati direttamente, entrambi facili da sbagliare:

  1. **L'id del nutriente "energia" cambia per dataset.** Gli alimenti
     `Foundation` (i più recenti e curati) non hanno l'id classico 1008: usano
     2047 (fattori di Atwater generali) e 2048 (specifici). Senza fallback,
     metà degli alimenti risulterebbe a zero calorie — un errore che passerebbe
     inosservato fino a produrre piani alimentari sbagliati.

  2. **La qualità della ricerca dipende dal dataset.** Cercando "apple raw" in
     `SR Legacy` il primo risultato è "Rose-apples" (un altro frutto), mentre
     in `Foundation` è "Apples, fuji, with skin, raw". Per questo si
     interrogano in ordine di affidabilità, non tutti insieme.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger("usda_client")

# Dataset in ordine di preferenza per gli alimenti generici.
# "Branded" è escluso di proposito: sono prodotti confezionati, terreno di
# wger/Open Food Facts.
GENERIC_DATA_TYPES = ("Foundation", "SR Legacy")

# Id dei nutrienti (numerazione FoodData Central).
_NUTRIENT_PROTEIN = 1003
_NUTRIENT_FAT = 1004
_NUTRIENT_CARBS = 1005
_NUTRIENT_FIBER = 1079
_NUTRIENT_SUGARS = 2000
_NUTRIENT_SUGARS_NLEA = 1063
_NUTRIENT_SATURATED_FAT = 1258

# Energia, in ordine di preferenza:
#   1008 -> "Energy", presente in SR Legacy e Branded
#   2047 -> "Energy (Atwater General Factors)", fattori standard 4/4/9
#   2048 -> "Energy (Atwater Specific Factors)", fattori specifici per alimento
# Si preferiscono i fattori generali perché coerenti con l'aritmetica 4/4/9
# con cui i macro vengono mostrati all'utente.
_ENERGY_IDS = (1008, 2047, 2048)


class UsdaNotConfigured(RuntimeError):
    """USDA_API_KEY non configurata nel file .env."""


class UsdaError(RuntimeError):
    """Chiamata a USDA fallita (rete, quota, risposta inattesa)."""


@dataclass
class RawUsdaFood:
    fdc_id: int
    name: str
    data_type: str | None
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float
    sugars_100g: float | None = None
    fiber_100g: float | None = None
    saturated_fat_100g: float | None = None
    food_category: str | None = None


def _get(path: str, params: dict, *, timeout: float = 30.0) -> dict:
    settings = get_settings()
    if not settings.usda_configured:
        raise UsdaNotConfigured("USDA_API_KEY non configurata nel file .env")

    base = settings.usda_base_url.rstrip("/")
    try:
        # Chiave nell'header (supportato da api.data.gov) e non nei parametri:
        # gli URL finiscono nei log, gli header no.
        resp = httpx.get(
            f"{base}/{path.lstrip('/')}",
            params=params,
            headers={"X-Api-Key": settings.usda_api_key},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise UsdaError(f"Richiesta a USDA fallita ({path}): {e}") from e


def _nutrient_map(food: dict) -> dict[int, float]:
    """Appiattisce `foodNutrients` in {id_nutriente: valore}.

    La struttura differisce fra ricerca e dettaglio: nella ricerca l'id è in
    `nutrientId`, nel dettaglio è annidato in `nutrient.id`.
    """
    values: dict[int, float] = {}
    for entry in food.get("foodNutrients") or []:
        nutrient_id = entry.get("nutrientId")
        if nutrient_id is None:
            nutrient_id = (entry.get("nutrient") or {}).get("id")
        value = entry.get("value")
        if value is None:
            value = entry.get("amount")
        if nutrient_id is not None and value is not None:
            values[int(nutrient_id)] = float(value)
    return values


def _first_available(values: dict[int, float], ids: tuple[int, ...]) -> float | None:
    for nutrient_id in ids:
        if nutrient_id in values:
            return values[nutrient_id]
    return None


def _clamp_non_negative(value: float | None) -> float | None:
    """USDA ricava i carboidrati "per differenza" (100 meno acqua, proteine,
    grassi e ceneri): il rumore di misura può produrre valori leggermente
    negativi, es. -0,4 g per il petto di pollo con pelle.

    Lasciarli passare significherebbe *sottrarre* carboidrati dal totale
    giornaliero di un piano alimentare, con un errore invisibile.
    """
    if value is None:
        return None
    return max(value, 0.0)


def _parse_food(food: dict) -> RawUsdaFood | None:
    values = _nutrient_map(food)

    kcal = _first_available(values, _ENERGY_IDS)
    protein = values.get(_NUTRIENT_PROTEIN)
    carbs = values.get(_NUTRIENT_CARBS)
    fat = values.get(_NUTRIENT_FAT)

    # Senza i macro di base l'alimento non è utilizzabile per i calcoli:
    # meglio scartarlo che salvarlo con degli zeri finti.
    if None in (kcal, protein, carbs, fat):
        return None

    return RawUsdaFood(
        fdc_id=int(food["fdcId"]),
        name=(food.get("description") or "").strip(),
        data_type=food.get("dataType"),
        kcal_100g=_clamp_non_negative(kcal),
        protein_100g=_clamp_non_negative(protein),
        carbs_100g=_clamp_non_negative(carbs),
        fat_100g=_clamp_non_negative(fat),
        sugars_100g=_clamp_non_negative(
            _first_available(values, (_NUTRIENT_SUGARS, _NUTRIENT_SUGARS_NLEA))
        ),
        fiber_100g=_clamp_non_negative(values.get(_NUTRIENT_FIBER)),
        saturated_fat_100g=_clamp_non_negative(values.get(_NUTRIENT_SATURATED_FAT)),
        food_category=food.get("foodCategory"),
    )


def search_foods(
    query: str,
    *,
    limit: int = 10,
    data_types: tuple[str, ...] = GENERIC_DATA_TYPES,
) -> list[RawUsdaFood]:
    """Cerca alimenti generici, dai dataset più curati.

    I valori nutrizionali di USDA sono espressi **per 100 g**, coerenti con
    il resto del modello dati.
    """
    query = (query or "").strip()
    if not query:
        return []

    data = _get(
        "foods/search",
        {
            "query": query,
            "pageSize": limit,
            # L'API accetta più dataType separati da virgola, in ordine di
            # preferenza per il ranking dei risultati.
            "dataType": ",".join(data_types),
        },
    )

    parsed = (_parse_food(food) for food in data.get("foods") or [])
    return [food for food in parsed if food is not None]


def get_food(fdc_id: int) -> RawUsdaFood | None:
    """Dettaglio completo di un alimento a partire dal suo FDC id."""
    return _parse_food(_get(f"food/{fdc_id}", {}))
