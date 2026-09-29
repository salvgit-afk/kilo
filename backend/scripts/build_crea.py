"""Legge le Tabelle di composizione degli alimenti del CREA e scrive il JSON che usa Kilo.

    python scripts/build_crea.py --cache /tmp/crea-pagine

Il CREA pubblica le tabelle solo come pagine web (alimentinutrizione.it, una
per alimento). Le condizioni d'uso permettono di riprodurre e usare i dati,
anche a fini commerciali, **citando la fonte**: "CREA Centro di ricerca
Alimenti e Nutrizione". Lo script legge l'elenco e poi ogni pagina, **una
volta sola e piano** (una richiesta ogni 1,5 secondi, circa mezz'ora per 908
alimenti); con `--cache` tiene una copia di ogni pagina, così rilanciarlo non
riscarica niente. Scrive `app/data/crea_2019.json`.

Valori: "tr" (tracce) diventa 0, una cella vuota "dato mancante". I grassi
saturi il CREA li dà in percentuale sugli acidi grassi, non in grammi:
convertirli richiederebbe un fattore stimato, quindi restano vuoti. Se mancano
solo i carboidrati e le calorie tornano con proteine e grassi, i carboidrati
sono 0 (carne, pesce, uova); altrimenti l'alimento si scarta.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://www.alimentinutrizione.it"
ELENCO = f"{BASE}/tabelle-nutrizionali/ricerca-per-alimento"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "crea_2019.json"
PAUSA_S = 1.5
UA = "Mozilla/5.0 (compatible; Kilo/1.0; app personale, dati citati come fonte CREA)"

NUTRIENTI = {
    "kcal": "Energia (kcal)",
    "protein": "Proteine (g)",
    "fat": "Lipidi (g)",
    "carbs": "Carboidrati disponibili (g)",
    "sugars": "Zuccheri solubili (g)",
    "fiber": "Fibra totale (g)",
}


def celle(pagina: str) -> list[list[str]]:
    righe = re.findall(r"<tr[^>]*>(.*?)</tr>", pagina, re.S)
    return [
        [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
         for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        for r in righe
    ]


def numero(testo: str | None) -> float | None:
    t = (testo or "").strip().replace(",", ".")
    if not t or t == "-":
        return None
    if t.lower() in ("tr", "tracce"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return None


def leggi(codice: str, pagina: str) -> dict | None:
    titolo = re.search(r"<title>\s*AlimentiNUTrizione\s*-\s*(.*?)\s*</title>", pagina, re.S)
    if not titolo:
        return None
    info: dict[str, str] = {}
    valori: dict[str, float | None] = {}
    for c in celle(pagina):
        if len(c) == 2:
            info[c[0]] = c[1]
        elif len(c) >= 3:
            for chiave, etichetta in NUTRIENTI.items():
                if chiave not in valori and c[0].startswith(etichetta):
                    valori[chiave] = numero(c[2])
    kcal, p, f, cho = (valori.get(k) for k in ("kcal", "protein", "fat", "carbs"))
    if kcal is None or p is None or f is None:
        return None
    if cho is None:
        if abs(kcal - (4 * p + 9 * f)) > 5:
            return None
        cho = 0.0
    porzione = re.search(r"(\d+(?:[.,]\d+)?)\s*g", info.get("Porzione", ""))
    return {
        "id": codice,
        "name": html.unescape(titolo.group(1)).strip(),
        "en": info.get("English Name") or None,
        "category": info.get("Categoria") or None,
        "portion_g": float(porzione.group(1).replace(",", ".")) if porzione else None,
        "kcal": kcal, "protein": p, "carbs": cho, "fat": f,
        "sugars": valori.get("sugars"), "fiber": valori.get("fiber"),
        "saturated": valori.get("saturated"),
    }


def scarica(client: httpx.Client, url: str, cache: Path | None, nome: str) -> str:
    if cache and (cache / nome).exists():
        return (cache / nome).read_text(encoding="utf-8")
    for tentativo in range(3):
        try:
            r = client.get(url)
            r.raise_for_status()
            if cache:
                (cache / nome).write_text(r.text, encoding="utf-8")
            time.sleep(PAUSA_S)
            return r.text
        except httpx.HTTPError:
            time.sleep(10 * (tentativo + 1))
    raise RuntimeError(f"pagina non raggiungibile: {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=None)
    args = parser.parse_args()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, headers={"User-Agent": UA}) as client:
        elenco = scarica(client, ELENCO, args.cache, "elenco.html")
        codici = list(dict.fromkeys(re.findall(r'href="/tabelle-nutrizionali/(\d{6})"', elenco)))
        print(f"{len(codici)} alimenti nell'elenco")
        alimenti, scartati = [], []
        for n, codice in enumerate(codici, 1):
            voce = leggi(codice, scarica(client, f"{BASE}/tabelle-nutrizionali/{codice}", args.cache, f"{codice}.html"))
            (alimenti if voce else scartati).append(voce or codice)
            if n % 50 == 0:
                print(f"  {n}/{len(codici)}", flush=True)
    OUT.write_text(json.dumps({
        "_fonte": "CREA Centro di ricerca Alimenti e Nutrizione - Tabelle di composizione degli alimenti (aggiornamento 2019). https://www.alimentinutrizione.it",
        "_condizioni": "Riproduzione e uso consentiti citando la fonte originale",
        "alimenti": alimenti,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(alimenti)} alimenti scritti in {OUT}; scartati senza macro: {len(scartati)} {scartati[:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
