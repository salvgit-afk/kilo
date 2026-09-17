"""Open Food Facts: lettura di un prodotto dal codice a barre.

`GET https://world.openfoodfacts.org/api/v2/product/{barcode}.json`, gratuito
e senza chiave. Due particolarità gestite qui, perché nessun chiamante debba
ricordarsele:

  - **un codice sconosciuto risponde comunque HTTP 200**, con `status: 0` nel
    corpo: va trattato come "non trovato", non come un prodotto vuoto;
  - i valori sono inseriti dagli utenti e a volte mancano: un prodotto senza
    calorie o macronutrienti per 100 g non è utilizzabile per un conteggio,
    e viene segnalato come incompleto invece di essere salvato a zero.

Open Food Facts chiede di identificare l'app con uno User-Agent dedicato.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger("off_client")

PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
USER_AGENT = "Kilo/1.0 (app di allenamento e nutrizione; github.com/salvgit-afk/kilo)"
FIELDS = "code,product_name,product_name_it,generic_name_it,brands,quantity,nutriments"
KJ_PER_KCAL = 4.184


class OffError(RuntimeError):
    """Open Food Facts non raggiungibile o risposta non valida."""


class ProductNotFound(OffError):
    """Il codice non è nel database (HTTP 200 con `status: 0`)."""


class IncompleteProduct(OffError):
    """Il prodotto esiste ma mancano calorie o macronutrienti per 100 g."""

    def __init__(self, message: str, name: str | None):
        super().__init__(message)
        self.name = name


@dataclass
class OffProduct:
    barcode: str
    name: str
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float
    sugars_100g: float | None
    fiber_100g: float | None
    saturated_fat_100g: float | None


def normalize_barcode(raw: str) -> str:
    """Solo cifre, 8-14 (EAN-8, UPC-A, EAN-13, GTIN-14); altrimenti ValueError."""
    codice = re.sub(r"\D", "", raw or "")
    if not 8 <= len(codice) <= 14:
        raise ValueError("Il codice a barre deve avere da 8 a 14 cifre.")
    return codice


def _number(nutriments: dict, key: str) -> float | None:
    valore = nutriments.get(key)
    try:
        return float(valore) if valore is not None and valore != "" else None
    except (TypeError, ValueError):
        return None


def parse_product(barcode: str, data: dict) -> OffProduct:
    """Interpreta la risposta; solleva `ProductNotFound` o `IncompleteProduct`."""
    if data.get("status") != 1 or not isinstance(data.get("product"), dict):
        raise ProductNotFound(f"Prodotto {barcode} non trovato su Open Food Facts")

    prodotto = data["product"]
    nome = (
        prodotto.get("product_name_it")
        or prodotto.get("product_name")
        or prodotto.get("generic_name_it")
        or ""
    ).strip()
    marca = (prodotto.get("brands") or "").split(",")[0].strip()
    if marca and marca.lower() not in nome.lower():
        nome = f"{nome} · {marca}" if nome else marca
    # "400 g e": la "e" è il simbolo ℮ (quantità stimata) delle confezioni.
    quantita = re.sub(r"\s*(℮|\be)$", "", (prodotto.get("quantity") or "").strip())
    if nome and quantita:
        nome = f"{nome} ({quantita})"

    n = prodotto.get("nutriments") or {}
    kcal = _number(n, "energy-kcal_100g")
    if kcal is None:
        kj = _number(n, "energy-kj_100g") or _number(n, "energy_100g")
        kcal = kj / KJ_PER_KCAL if kj is not None else None
    proteine = _number(n, "proteins_100g")
    carboidrati = _number(n, "carbohydrates_100g")
    grassi = _number(n, "fat_100g")

    mancanti = [
        etichetta
        for etichetta, valore in (
            ("calorie", kcal), ("proteine", proteine), ("carboidrati", carboidrati), ("grassi", grassi)
        )
        if valore is None
    ]
    if mancanti or not nome:
        raise IncompleteProduct(
            "Su Open Food Facts il prodotto non ha " + (", ".join(mancanti) or "un nome") + " per 100 g.",
            nome or None,
        )

    return OffProduct(
        barcode=barcode,
        name=nome[:255],
        kcal_100g=round(kcal, 1),
        protein_100g=proteine,
        carbs_100g=carboidrati,
        fat_100g=grassi,
        sugars_100g=_number(n, "sugars_100g"),
        fiber_100g=_number(n, "fiber_100g"),
        saturated_fat_100g=_number(n, "saturated-fat_100g"),
    )


def get_product(barcode: str, *, timeout: float = 15.0) -> OffProduct:
    try:
        resp = httpx.get(
            PRODUCT_URL.format(barcode=barcode),
            params={"fields": FIELDS},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise OffError(f"Open Food Facts non raggiungibile: {e}") from e
    if resp.status_code == 404:
        raise ProductNotFound(f"Prodotto {barcode} non trovato su Open Food Facts")
    if resp.status_code != 200:
        raise OffError(f"Open Food Facts ha risposto {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as e:
        raise OffError("Risposta di Open Food Facts non valida") from e
    return parse_product(barcode, data)
