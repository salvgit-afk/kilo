"""Ricerca alimenti: generici, prodotti venduti in Italia, prodotti americani.

Il caso che l'ha motivata: cercando "kefir" comparivano due kefir americani
LIFEWAY etichettati "generico" e poi una sfilza di voci chiamate solo
"kefir", senza marca, con calorie diverse — una vecchia copia mondiale di
Open Food Facts. Nessuna rete: le fonti sono sostituite.
"""

from __future__ import annotations

import httpx
import pytest

from app.models import Ingredient, IngredientSource, LlmCache
from app.services import food_diary as fd
from app.services import off_client

# --- Prodotti americani dentro USDA -------------------------------------------------


@pytest.mark.parametrize("nome", ["Kefir, lowfat, strawberry, LIFEWAY", "Cereals, KELLOGG'S, corn flakes"])
def test_marca_americana_riconosciuta(nome):
    assert fd.usda_brand(nome)


@pytest.mark.parametrize("nome", ["Kefir, NFS", "Milk, UHT, whole", "Chicken, breast, raw"])
def test_alimento_generico_non_scambiato_per_marca(nome):
    assert not fd.usda_brand(nome)


# --- Ordine dei risultati -------------------------------------------------------------------


def _ing(db, nome, fonte, kcal, codice=None):
    ing = Ingredient(
        name=nome, source=fonte, kcal_100g=kcal, protein_100g=3.4,
        carbs_100g=4.0, fat_100g=1.5, barcode=codice,
    )
    db.add(ing)
    db.commit()
    return ing


def test_generici_poi_italiani_poi_americani_senza_doppioni(db, monkeypatch):
    generico = _ing(db, "Kefir, plain, NFS", IngredientSource.USDA, 52)
    lifeway = _ing(db, "Kefir, lowfat, plain, LIFEWAY", IngredientSource.USDA, 41)
    granarolo = _ing(db, "Kefir · Granarolo (500 g)", IngredientSource.OFF, 67, "8002670013030")
    milbona = _ing(db, "Kefir · Milbona (464 ml)", IngredientSource.OFF, 44, "4056489246435")
    doppione = _ing(db, "kefir  · milbona (464 ml)", IngredientSource.OFF, 44, "4056489246436")

    monkeypatch.setattr(fd, "_usda_and_fallback", lambda *_a, **_k: ([lifeway, generico], []))
    monkeypatch.setattr(fd, "_italian_products", lambda *_a, **_k: [milbona, doppione, granarolo])

    risultati = fd.search_foods(db, "kefir")
    nomi = [r.ingredient.name for r in risultati]

    assert nomi == [generico.name, milbona.name, granarolo.name, lifeway.name]
    assert risultati[0].is_generic and not risultati[-1].is_generic
    assert risultati[-1].source_label == "prodotto USA (USDA)"
    assert risultati[1].source_label == "prodotto di marca · Open Food Facts"


def test_riserva_wger_solo_se_la_ricerca_italiana_non_risponde(db, monkeypatch):
    chiamate = {}

    def fonti(_db, _q, _en, *, limit, with_fallback):
        chiamate["riserva"] = with_fallback
        return [], []

    monkeypatch.setattr(fd, "_usda_and_fallback", fonti)
    monkeypatch.setattr(fd, "_italian_products", lambda *_a, **_k: None)
    fd.search_foods(db, "kefir")
    assert chiamate["riserva"] is True

    monkeypatch.setattr(fd, "_italian_products", lambda *_a, **_k: [])
    fd.search_foods(db, "kefir")
    assert chiamate["riserva"] is False


# --- Ricerca su Open Food Facts --------------------------------------------------------------


def _hit(codice, nome, marche, kcal, p=3.4, c=4.0, g=1.5, quantita="480 g"):
    return {
        "code": codice, "product_name": nome, "brands": marche, "quantity": quantita,
        "nutriments": {"energy-kcal_100g": kcal, "proteins_100g": p, "carbohydrates_100g": c, "fat_100g": g},
    }


class _Risposta:
    status_code = 200

    def __init__(self, hits):
        self._hits = hits

    def json(self):
        return {"hits": self._hits}


@pytest.fixture(autouse=True)
def _nessun_limite(monkeypatch):
    monkeypatch.setattr(off_client, "_ricerche_recenti", [])


def test_ricerca_solo_italia_marca_nel_nome_incompleti_scartati(monkeypatch):
    richieste = {}

    def finto_get(url, params, headers, timeout):
        richieste.update(params)
        return _Risposta([
            _hit("8034066307072", "Kefir", ["alplì", " NÖM"], 44),
            {"code": "4740125321050", "product_name": "Kefir", "brands": ["Valio"], "nutriments": {}},
            _hit("1234567890123", "Kefir sbagliato", ["X"], 44, p=90, c=40),  # macro > 100 g
            _hit("8001120000000", "Biscotti", ["Kefir Srl"], 450, p=7, c=70, g=15),  # solo la marca
        ])

    monkeypatch.setattr(off_client.httpx, "get", finto_get)
    prodotti = off_client.search_products('kefir" OR countries_tags:*')

    assert [p.name for p in prodotti] == ["Kefir · alplì (480 g)"]
    assert 'countries_tags:"en:italy"' in richieste["q"]
    # Il testo dell'utente non può aggiungere filtri alla ricerca.
    assert richieste["q"].count(":") == 2  # solo quelli del filtro "en:italy"
    assert " OR " not in richieste["q"]
    # Pertinenza del motore: la popolarità portava biscotti cercando "petto di pollo".
    assert "sort_by" not in richieste


def test_bibita_zero_non_scartata_come_implausibile():
    zero = off_client.OffProduct("5449000131805", "Coca-Cola Zero", 0.3, 0, 0, 0, 0, None, None)
    assert off_client.plausible(zero)


def test_calorie_incoerenti_con_i_macro_scartate():
    sbagliato = off_client.OffProduct("1", "Kefir", 400, 3.4, 4.0, 1.5, None, None, None)
    assert not off_client.plausible(sbagliato)


def test_soglia_di_ricerche_al_minuto():
    for i in range(off_client.SEARCHES_PER_MINUTE):
        off_client._consuma_ricerca(now=100.0 + i)
    with pytest.raises(off_client.SearchRateLimited):
        off_client._consuma_ricerca(now=110.0)
    off_client._consuma_ricerca(now=170.0)  # passato il minuto si riparte


def test_rete_giu_diventa_errore_gestito(monkeypatch):
    def giu(*_a, **_k):
        raise httpx.ConnectError("no")

    monkeypatch.setattr(off_client.httpx, "get", giu)
    with pytest.raises(off_client.OffError):
        off_client.search_products("kefir")


# --- Cache delle ricerche ---------------------------------------------------------------------


def test_seconda_ricerca_dalla_cache_e_scansione_istantanea(db, monkeypatch):
    chiamate = []

    def finta(query, *, limit):
        chiamate.append(query)
        return [off_client.OffProduct("8002670013030", "Kefir · Granarolo", 67, 2.9, 4.0, 3.5, None, None, None)]

    monkeypatch.setattr(off_client, "search_products", finta)
    prima = fd._italian_products(db, "Kefir", limit=10)
    seconda = fd._italian_products(db, "  kefir ", limit=10)

    assert [i.id for i in prima] == [i.id for i in seconda]
    assert chiamate == ["Kefir"]
    assert db.query(LlmCache).filter_by(kind=fd.OFF_SEARCH_CACHE).count() == 1

    # Il prodotto trovato cercando è lo stesso che si trova scansionando.
    monkeypatch.setattr(off_client, "get_product", lambda _c: pytest.fail("doveva venire dalla cache"))
    trovato = fd.lookup_barcode(db, "8002670013030", user_id=1)
    assert trovato.cached and trovato.ingredient.id == prima[0].id


def test_open_food_facts_giu_restituisce_none(db, monkeypatch):
    def giu(query, *, limit):
        raise off_client.SearchRateLimited("troppe")

    monkeypatch.setattr(off_client, "search_products", giu)
    assert fd._italian_products(db, "kefir", limit=10) is None


@pytest.mark.parametrize("nome", [
    "Yogurt, Greek, plain, nonfat", "Rice, white, long-grain, raw", "Oat bran, raw",
])
def test_generico_pertinente(nome):
    inglese = {"Y": "yogurt greek", "R": "rice", "O": "oats"}[nome[0]]
    assert fd.pertinente(inglese, nome)


@pytest.mark.parametrize("inglese,nome", [
    ("yogurt greek", "Candies, confectioner's coating, yogurt"),
    ("kefir", "Apricots, raw"),
    ("rice", "Abiyuch, raw"),
])
def test_generico_estraneo_scartato(inglese, nome):
    assert not fd.pertinente(inglese, nome)
