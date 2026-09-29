"""Trasforma la tabella CIQUAL (Excel di ANSES) nel JSON compatto che usa Kilo.

    pip install openpyxl        # serve solo qui, non all'app
    python scripts/build_ciqual.py "Table Ciqual 2025_ENG_2025_11_03.xlsx"

Scarica il file da https://ciqual.anses.fr (versione in inglese, Excel).
Scrive `app/data/ciqual_2025.json`, che va nel repository: la Licence Ouverte
Etalab permette di ridistribuire i dati citando la fonte, e così il server
non deve né scaricare né leggere Excel.

Valori nel file: testo con la virgola decimale, "-" quando manca il dato,
"traces" per quantità minime (qui 0) e "< x" sotto il limite di
quantificazione (qui x/2, la convenzione più usata). Si tengono solo gli
alimenti con calorie, proteine, carboidrati e grassi: senza, una voce del
diario non si può contare.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "ciqual_2025.json"

# Colonne del foglio "food composition" (versione inglese 2025).
COL = {
    "code": 6, "name": 7, "group": 3, "subgroup": 4,
    "kcal": 10, "protein": 14, "carbs": 16, "fat": 17,
    "sugars": 18, "fiber": 26, "saturated": 31,
}


def numero(valore) -> float | None:
    if valore is None:
        return None
    testo = str(valore).strip().replace(",", ".")
    if testo in ("", "-"):
        return None
    if testo.lower() == "traces":
        return 0.0
    if testo.startswith("<"):
        try:
            return round(float(testo[1:].strip()) / 2, 3)
        except ValueError:
            return None
    try:
        return float(testo)
    except ValueError:
        return None


def main(path: str) -> int:
    ws = openpyxl.load_workbook(path, read_only=True)["food composition"]
    righe = ws.iter_rows(values_only=True)
    intestazione = next(righe)
    assert "alim_nom_eng" in str(intestazione[COL["name"]]), "colonne diverse da quelle attese"
    alimenti = []
    for r in righe:
        if not r or not r[COL["code"]] or str(r[COL["group"]]).strip() in ("-", ""):
            continue
        valori = {k: numero(r[COL[k]]) for k in ("kcal", "protein", "carbs", "fat", "sugars", "fiber", "saturated")}
        if any(valori[k] is None for k in ("kcal", "protein", "carbs", "fat")):
            continue
        alimenti.append({
            "id": str(r[COL["code"]]).strip(),
            "name": " ".join(str(r[COL["name"]]).split()),
            "group": str(r[COL["subgroup"]] or r[COL["group"]]).strip(),
            **{k: v for k, v in valori.items()},
        })
    OUT.write_text(json.dumps({
        "_fonte": "Anses. 2025. Table de composition nutritionnelle des aliments Ciqual. https://ciqual.anses.fr",
        "_licenza": "Licence Ouverte / Open Licence (Etalab) 2.0: riuso libero, citando la fonte",
        "alimenti": alimenti,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(alimenti)} alimenti scritti in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
