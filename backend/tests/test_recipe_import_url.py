"""Importazione di una ricetta da un link: lettura della pagina e protezioni."""

from __future__ import annotations

import socket

import pytest

from app.services import recipe_import as ri

PAGINA = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Recipe", "name": "Pasta al pomodoro",
 "recipeYield": "2 servings",
 "recipeIngredient": ["Spaghetti 160 g", "Passata di pomodoro 200 g", "Olio extravergine 10 g"],
 "recipeInstructions": [{"@type": "HowToStep", "text": "Cuoci la pasta."},
                        {"@type": "HowToStep", "text": "Condisci con il sugo."}]}
</script></head><body>Pubblicità, commenti e altro testo.</body></html>"""


def test_riconosce_un_link():
    assert ri.looks_like_url("https://ricette.giallozafferano.it/Carbonara.html")
    assert ri.looks_like_url("  http://esempio.it/ricetta  ")
    assert not ri.looks_like_url("80 g di avena\nhttps://sito.it")


def test_dalla_pagina_al_testo_della_ricetta():
    testo = ri.scraped_text(PAGINA, "https://esempio.it/pasta")
    assert testo.splitlines()[0] == "Pasta al pomodoro"
    assert "Porzioni: 2" in testo
    assert "- Spaghetti 160 g" in testo and "- Olio extravergine 10 g" in testo
    assert "Cuoci la pasta." in testo
    assert "Pubblicità" not in testo


def test_pagina_senza_ricetta():
    with pytest.raises(ri.RecipeImportError):
        ri.scraped_text("<html><body>Nessuna ricetta qui</body></html>", "https://esempio.it/x")


@pytest.mark.parametrize("indirizzo", ["127.0.0.1", "10.1.2.3", "192.168.1.10", "169.254.169.254", "::1"])
def test_link_verso_la_rete_interna_rifiutati(monkeypatch, indirizzo):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (indirizzo, 0))])
    with pytest.raises(ri.RecipeImportError):
        ri._check_host("http://sembra-pubblico.it/ricetta")


def test_solo_http_e_https():
    with pytest.raises(ri.RecipeImportError):
        ri._check_host("file:///etc/passwd")


def test_import_da_link_passa_dal_testo(monkeypatch):
    letto = {}
    monkeypatch.setattr(ri, "_fetch_page", lambda url: PAGINA)
    monkeypatch.setattr(ri, "import_from_text", lambda db, testo: letto.setdefault("testo", testo))
    ri.import_from_url(None, "https://esempio.it/pasta")
    assert letto["testo"].startswith("Pasta al pomodoro")
