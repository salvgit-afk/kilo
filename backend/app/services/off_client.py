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


# --- Ricerca per nome ----------------------------------------------------------

# Il motore di ricerca di Open Food Facts: risponde in meno di mezzo secondo e
# accetta filtri. Si cercano solo i prodotti **venduti in Italia**, non una
# sfilza di omonimi da mezzo mondo.
#
# Ordine: quello di pertinenza del motore. L'ordinamento per numero di
# scansioni sembrava migliore con "kefir", ma con due parole ("petto di
# pollo") portava in cima biscotti e creme spalmabili, i prodotti più
# scansionati d'Italia.
SEARCH_URL = "https://search.openfoodfacts.org/search"
SEARCH_FIELDS = FIELDS + ",unique_scans_n"

# Open Food Facts limita le ricerche per indirizzo IP, e dal server tutti gli
# utenti escono con lo stesso. Tenersi sotto il limite qui evita di farsi
# bloccare; oltre la soglia chi chiama usa la cache o un'altra fonte.
SEARCHES_PER_MINUTE = 8


class SearchRateLimited(OffError):
    """Soglia di ricerche al minuto raggiunta: riprovare dopo."""


_ricerche_recenti: list[float] = []


def _consuma_ricerca(now: float | None = None) -> None:
    import time

    adesso = time.monotonic() if now is None else now
    while _ricerche_recenti and adesso - _ricerche_recenti[0] > 60:
        _ricerche_recenti.pop(0)
    if len(_ricerche_recenti) >= SEARCHES_PER_MINUTE:
        raise SearchRateLimited("Troppe ricerche su Open Food Facts in questo minuto")
    _ricerche_recenti.append(adesso)


def plausible(p: OffProduct) -> bool:
    """Scarta i valori impossibili, frequenti nei dati inseriti a mano.

    Due controlli: i macronutrienti non possono superare i 100 g per 100 g, e
    le calorie dichiarate devono essere coerenti con quelle ricavate dai macro
    (4-4-9 kcal/g). Sotto le 20 kcal (acqua, bibite zero) la differenza
    relativa non vuol dire niente e non si controlla.
    """
    if p.protein_100g + p.carbs_100g + p.fat_100g > 101:
        return False
    stimate = 4 * p.protein_100g + 4 * p.carbs_100g + 9 * p.fat_100g
    if max(p.kcal_100g, stimate) < 20:
        return True
    return abs(p.kcal_100g - stimate) / max(p.kcal_100g, stimate) <= 0.35


def _query_sicura(testo: str) -> str:
    """Solo lettere, cifre e spazi, in minuscolo: la ricerca accetta una
    sintassi con virgolette, due punti e operatori in maiuscolo (AND, OR,
    NOT), e il testo dell'utente non deve poterla usare."""
    return " ".join(re.findall(r"[\wÀ-ÿ']+", (testo or "").lower()))[:80]


def search_products(query: str, *, limit: int = 12, timeout: float = 8.0) -> list[OffProduct]:
    """Prodotti venduti in Italia che corrispondono alla ricerca.

    Restituisce solo prodotti con calorie e macro completi e plausibili: gli
    altri non sono utilizzabili per un conteggio. Solleva `OffError` se il
    servizio non risponde e `SearchRateLimited` oltre la soglia al minuto.
    """
    testo = _query_sicura(query)
    if len(testo) < 2:
        return []
    _consuma_ricerca()
    try:
        resp = httpx.get(
            SEARCH_URL,
            params={
                "q": f'{testo} countries_tags:"en:italy"',
                "page_size": limit * 2,  # una parte viene scartata perché incompleta
                "fields": SEARCH_FIELDS,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise OffError(f"Ricerca Open Food Facts non raggiungibile: {e}") from e
    if resp.status_code != 200:
        raise OffError(f"La ricerca di Open Food Facts ha risposto {resp.status_code}")
    try:
        hits = resp.json().get("hits") or []
    except ValueError as e:
        raise OffError("Risposta della ricerca Open Food Facts non valida") from e

    # Radici delle parole significative: "uova" trova "uovo".
    parole = [
        p[:-1] if len(p) >= 4 and p[-1] in "aeiou" else p
        for p in testo.split()
        if len(p) >= 3 and p not in {"con", "per", "alla", "allo", "agli", "dei", "del", "della"}
    ]
    prodotti: list[OffProduct] = []
    for hit in hits:
        codice = str(hit.get("code") or "")
        marche = hit.get("brands")
        if isinstance(marche, list):  # la ricerca le restituisce come lista
            hit = {**hit, "brands": ",".join(m.strip() for m in marche if m)}
        # Almeno una parola cercata nel nome del prodotto, marca esclusa:
        # "Oat Original · Riso Scotti" non è un riso.
        nome_proprio = (hit.get("product_name_it") or hit.get("product_name") or "").lower()
        if parole and not any(re.search(rf"\b{re.escape(p)}", nome_proprio) for p in parole):
            continue
        try:
            prodotto = parse_product(normalize_barcode(codice), {"status": 1, "product": hit})
        except (ValueError, ProductNotFound, IncompleteProduct):
            continue
        if plausible(prodotto):
            prodotti.append(prodotto)
        if len(prodotti) >= limit:
            break
    return prodotti
