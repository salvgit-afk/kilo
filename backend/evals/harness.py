"""Parti comuni delle valutazioni (chat, importazione ricette, schede).

Non è un modulo di test: qui non c'è nessuna asserzione e niente viene
eseguito all'import. Contiene solo quello che tutte le suite fanno allo
stesso modo — normalizzare il testo prima di confrontarlo, scegliere i casi
da eseguire, stampare il riassunto, salvare il risultato in `results/` e
confrontarlo con un riferimento — perché tre copie della stessa funzione di
confronto finiscono sempre per divergere.

Le funzioni di confronto (`normalizza`, `una_fra`, `regressioni`) non
toccano rete né database: sono quelle coperte da
`tests/test_evals_harness.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

DIR = Path(__file__).resolve().parent
RESULTS = DIR / "results"

OK = "ok"
FALLITO = "fallito"
NON_VALUTATO = "non valutato"

SEGNI = {OK: "✓", FALLITO: "✗", NON_VALUTATO: "?"}


def normalizza(testo: str) -> str:
    """Minuscole, trattini uniformi e senza spazi attorno, virgola decimale → punto.

    Serve a confrontare quello che conta (il dato) e non come è scritto: un
    modello che risponde «8 – 16 serie» sta dicendo la stessa cosa di «8-16».
    """
    t = (testo or "").lower().replace("–", "-").replace("—", "-")
    t = re.sub(r"\s*-\s*", "-", t)
    return re.sub(r"(\d),(\d)", r"\1.\2", t)


def contiene(testo: str, frase: str) -> bool:
    """La frase compare nel testo, a meno di come è scritta."""
    return normalizza(frase) in normalizza(testo)


def una_fra(testo: str, frasi: list[str] | None) -> bool:
    """Almeno una delle frasi compare nel testo. Elenco vuoto = nessun vincolo."""
    if not frasi:
        return True
    normalizzato = normalizza(testo)
    return any(normalizza(f) in normalizzato for f in frasi)


def nessuna_fra(testo: str, frasi: list[str] | None) -> list[str]:
    """Le frasi vietate che invece compaiono nel testo."""
    normalizzato = normalizza(testo)
    return [f for f in (frasi or []) if normalizza(f) in normalizzato]


def carica_golden(percorso: Path) -> dict:
    return json.loads(percorso.read_text(encoding="utf-8"))


def seleziona(casi: list[dict], only: str | None) -> list[dict]:
    """Filtra i casi con `--only id1,id2`; senza filtro li restituisce tutti."""
    if not only:
        return casi
    scelti = {i.strip() for i in only.split(",") if i.strip()}
    return [c for c in casi if c["id"] in scelti]


def stato_di(problemi: list[str]) -> str:
    return OK if not problemi else FALLITO


def stampa_esito(caso_id: str, stato: str, problemi: list[str]) -> None:
    print(f"{SEGNI[stato]} {caso_id:28} {'; '.join(problemi)[:110]}")


def riassunto(esiti: dict[str, dict]) -> tuple[int, int]:
    """Stampa superati/valutati e il dettaglio per categoria. Restituisce i conteggi."""
    valutati = [e for e in esiti.values() if e["stato"] != NON_VALUTATO]
    superati = sum(e["stato"] == OK for e in valutati)
    print(f"\nSuperati {superati}/{len(valutati)} ({len(esiti) - len(valutati)} non valutati)")
    per_categoria = Counter(e["categoria"] for e in valutati if e["stato"] == OK)
    totali = Counter(e["categoria"] for e in valutati)
    for categoria in sorted(totali):
        print(f"  {categoria:14} {per_categoria[categoria]}/{totali[categoria]}")
    return superati, len(valutati)


def salva_risultato(risultato: dict, *, prefisso: str = "") -> Path:
    """Scrive il risultato in `results/` con la data nel nome."""
    RESULTS.mkdir(exist_ok=True)
    percorso = RESULTS / f"{prefisso}{dt.datetime.now():%Y-%m-%d-%H%M}.json"
    percorso.write_text(json.dumps(risultato, ensure_ascii=False, indent=2), encoding="utf-8")
    return percorso


def regressioni(esiti: dict[str, dict], riferimento: dict[str, dict]) -> list[str]:
    """Casi che nel riferimento passavano e adesso falliscono.

    Solo questi contano come regressione: un caso già fallito prima è un
    problema noto, e un caso nuovo non ha un «prima» con cui confrontarsi.
    """
    return [
        cid
        for cid, esito in esiti.items()
        if esito["stato"] == FALLITO and riferimento.get(cid, {}).get("stato") == OK
    ]


def finalizza(
    esiti: dict[str, dict],
    *,
    baseline: Path,
    prefisso: str = "",
    intestazione: dict | None = None,
    salva_baseline: bool = False,
) -> int:
    """Riassunto, salvataggio, confronto con il riferimento, codice di uscita.

    Restituisce 1 se c'è almeno una regressione: è così che una suite può
    essere lanciata da uno script senza leggerne l'output.
    """
    superati, valutati = riassunto(esiti)

    risultato = {
        "data": dt.datetime.now().isoformat(timespec="seconds"),
        **(intestazione or {}),
        "superati": superati,
        "valutati": valutati,
        "casi": esiti,
    }
    percorso = salva_risultato(risultato, prefisso=prefisso)
    try:
        mostrato = percorso.relative_to(DIR.parent)
    except ValueError:  # cartella dei risultati spostata (succede nei test)
        mostrato = percorso
    print(f"Risultato salvato in {mostrato}")

    perse = []
    if baseline.exists():
        riferimento = json.loads(baseline.read_text(encoding="utf-8"))["casi"]
        perse = regressioni(esiti, riferimento)
        if perse:
            print(f"REGRESSIONI rispetto al riferimento: {', '.join(perse)}")

    if salva_baseline:
        baseline.write_text(json.dumps(risultato, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Salvato come nuovo riferimento (evals/{baseline.name})")

    return 1 if perse else 0


def argomenti_comuni(parser) -> None:
    """Opzioni che tutte le suite hanno, con gli stessi nomi."""
    parser.add_argument("--only", help="id dei casi da eseguire, separati da virgola")
    parser.add_argument("--save-baseline", action="store_true", help="salva questo risultato come riferimento")
