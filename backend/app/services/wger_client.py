"""Client per l'API di wger (esercizi e ingredienti).

wger è un progetto open source (AGPL): gli endpoint pubblici usati qui
**non richiedono autenticazione**. Se un giorno servisse più capacità, è
auto-ospitabile — nessun rischio di essere tagliati fuori da un cambio di
policy commerciale (a differenza delle API proprietarie).

Cosa fornisce:
  - `exerciseinfo` : ~950 esercizi con gruppo muscolare primario/secondario,
                     attrezzatura, categoria, descrizione e immagini.
  - `ingredient`   : oltre un milione di alimenti, re-import di Open Food
                     Facts (il campo `source_name` lo dichiara esplicitamente).

Due dettagli dell'API verificati direttamente, non dedotti:
  1. I valori nutrizionali arrivano come **stringhe** ("26.700"), non numeri:
     vanno convertiti, altrimenti i calcoli sui macro falliscono in silenzio.
  2. Gli esercizi hanno traduzioni separate per lingua (it=13, en=2). Non
     tutti sono tradotti in italiano: si ripiega sull'inglese.

Tutti gli errori di rete sono incapsulati in `WgerError`, così i router
possono rispondere con un 4xx/5xx pulito invece di far crashare l'app.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger("wger_client")

LANG_IT = 13
LANG_EN = 2

# Attrezzatura che indica un esercizio a corpo libero, per il filtro
# "cosa posso fare con quello che ho".
BODYWEIGHT_EQUIPMENT = "none (bodyweight exercise)"


class WgerError(RuntimeError):
    """Chiamata a wger fallita (rete, timeout, risposta inattesa)."""


@dataclass
class RawExercise:
    wger_id: int
    name: str
    category: str | None
    primary_muscles: list[str]
    secondary_muscles: list[str]
    equipment: list[str]
    description: str | None
    image_url: str | None

    @property
    def is_compound(self) -> bool:
        """Euristica dichiarata: un esercizio che coinvolge anche muscoli
        secondari è trattato come multi-articolare.

        Non è una classificazione biomeccanica rigorosa — serve solo a
        differenziare i tempi di recupero (vedi `rest_periods_and_rir.md`:
        90-120 s per i multi-articolari, 60-90 s per gli isolamenti).
        """
        return bool(self.secondary_muscles)


@dataclass
class RawIngredient:
    wger_id: int
    name: str
    brand: str | None
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float
    sugars_100g: float | None = None
    fiber_100g: float | None = None
    saturated_fat_100g: float | None = None
    barcode: str | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    source_name: str | None = None


@dataclass
class MuscleRef:
    """Riferimento muscolare: `name` è anatomico (Quadriceps femoris),
    `common_name` è quello d'uso comune (Quads)."""

    id: int
    name: str
    common_name: str | None
    is_front: bool = True


@dataclass
class EquipmentRef:
    id: int
    name: str


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# I tag rimossi lasciano spazi spuri prima della punteggiatura ("Stand up .").
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?])")


def _strip_html(text: str | None) -> str | None:
    """Le descrizioni degli esercizi arrivano in HTML."""
    if not text:
        return None
    cleaned = _WS_RE.sub(" ", _TAG_RE.sub(" ", text))
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned).strip()
    return cleaned or None


def _to_float(value: object) -> float | None:
    """wger restituisce i nutrienti come stringhe ("26.700") o null."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(path: str, params: dict | None = None, *, timeout: float = 25.0) -> dict:
    base = get_settings().wger_base_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/{path.lstrip('/')}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise WgerError(f"Richiesta a wger fallita ({path}): {e}") from e


# --- Tabelle di riferimento (piccole: 15 muscoli, 12 attrezzi) --------------


def fetch_muscles() -> list[MuscleRef]:
    data = _get("muscle/", {"limit": 100})
    return [
        MuscleRef(
            id=m["id"],
            name=m["name"],
            common_name=m.get("name_en") or None,
            is_front=bool(m.get("is_front", True)),
        )
        for m in data.get("results", [])
    ]


def fetch_equipment() -> list[EquipmentRef]:
    data = _get("equipment/", {"limit": 100})
    return [EquipmentRef(id=e["id"], name=e["name"]) for e in data.get("results", [])]


# --- Esercizi ---------------------------------------------------------------


def _pick_translation(translations: list[dict], preferred_lang: int) -> dict | None:
    """Preferisce la lingua richiesta, ripiega sull'inglese, poi su qualsiasi
    traduzione con un nome valido."""
    by_lang = {t.get("language"): t for t in translations if (t.get("name") or "").strip()}
    for lang in (preferred_lang, LANG_EN):
        if lang in by_lang:
            return by_lang[lang]
    return next(iter(by_lang.values()), None)


def _parse_exercise(item: dict, preferred_lang: int) -> RawExercise | None:
    translation = _pick_translation(item.get("translations") or [], preferred_lang)
    if translation is None:
        return None  # esercizio senza alcun nome utilizzabile: si scarta

    images = item.get("images") or []
    return RawExercise(
        wger_id=item["id"],
        name=(translation.get("name") or "").strip(),
        category=(item.get("category") or {}).get("name"),
        # `name_en` è il nome comune (Quads); si ripiega sull'anatomico.
        primary_muscles=[
            m.get("name_en") or m.get("name") for m in item.get("muscles") or []
        ],
        secondary_muscles=[
            m.get("name_en") or m.get("name") for m in item.get("muscles_secondary") or []
        ],
        equipment=[e.get("name") for e in item.get("equipment") or []],
        description=_strip_html(translation.get("description")),
        image_url=images[0].get("image") if images else None,
    )


def fetch_exercises(
    *,
    preferred_lang: int = LANG_IT,
    limit: int | None = None,
    page_size: int = 100,
) -> list[RawExercise]:
    """Scarica il catalogo esercizi, gestendo la paginazione.

    `limit=None` scarica tutto (~950 esercizi, una decina di richieste). Il
    catalogo cambia raramente: va scaricato una volta e messo in cache nella
    tabella `exercises`, non a ogni generazione di scheda.
    """
    collected: list[RawExercise] = []
    offset = 0

    while True:
        data = _get("exerciseinfo/", {"limit": page_size, "offset": offset})
        results = data.get("results", [])
        if not results:
            break

        for item in results:
            parsed = _parse_exercise(item, preferred_lang)
            if parsed is not None:
                collected.append(parsed)
                if limit is not None and len(collected) >= limit:
                    return collected

        if not data.get("next"):
            break
        offset += page_size

    return collected


# --- Ingredienti ------------------------------------------------------------


def _parse_ingredient(item: dict) -> RawIngredient | None:
    kcal = _to_float(item.get("energy"))
    protein = _to_float(item.get("protein"))
    carbs = _to_float(item.get("carbohydrates"))
    fat = _to_float(item.get("fat"))

    # Senza i macro di base l'ingrediente è inutilizzabile per i calcoli:
    # meglio scartarlo che inserirlo con degli zeri finti.
    if None in (kcal, protein, carbs, fat):
        return None

    return RawIngredient(
        wger_id=item["id"],
        name=(item.get("name") or "").strip(),
        brand=(item.get("brand") or "").strip() or None,
        kcal_100g=kcal,
        protein_100g=protein,
        carbs_100g=carbs,
        fat_100g=fat,
        sugars_100g=_to_float(item.get("carbohydrates_sugar")),
        fiber_100g=_to_float(item.get("fiber")),
        saturated_fat_100g=_to_float(item.get("fat_saturated")),
        barcode=(item.get("code") or "").strip() or None,
        is_vegan=item.get("is_vegan"),
        is_vegetarian=item.get("is_vegetarian"),
        source_name=item.get("source_name"),
    )


def search_ingredients(name: str, *, limit: int = 20) -> list[RawIngredient]:
    """Cerca alimenti per nome.

    Due limiti noti di questa fonte, entrambi verificati sui dati reali:

    1. È forte sui **prodotti confezionati di marca** e debole sugli
       **alimenti generici** ("petto di pollo crudo"). Per quelli si usa USDA.

    2. I dati sono **crowd-sourced e talvolta sbagliati**. Esempio reale
       trovato durante lo sviluppo: una voce "petto di pollo" dichiara 65 kcal
       e 3,2 g di proteine per 100 g (i valori corretti sono ~100 kcal e
       ~22 g). Un controllo di coerenza calorie/macro **non** intercetta
       questo caso, perché la voce è internamente coerente: è proprio il dato
       di partenza a essere errato.

       Conseguenza per il resto dell'app: la scelta dell'ingrediente non va
       automatizzata prendendo il primo risultato. L'interfaccia deve
       mostrare i valori nutrizionali accanto a ogni risultato, così un
       valore anomalo salta all'occhio prima di finire in un piano
       alimentare.

    Nota sulla lingua: wger è l'**unica** delle due fonti che risponde a
    ricerche in italiano ("petto di pollo"); USDA è solo in inglese.
    """
    name = (name or "").strip()
    if not name:
        return []

    data = _get("ingredient/", {"name": name, "limit": limit})
    parsed = (_parse_ingredient(item) for item in data.get("results", []))
    return [ing for ing in parsed if ing is not None]


def get_ingredient(wger_id: int) -> RawIngredient | None:
    item = _get(f"ingredient/{wger_id}/")
    return _parse_ingredient(item)
