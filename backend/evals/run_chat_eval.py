"""Valutazione della chat con Gemini reale sul set di prova.

Da lanciare a mano, soprattutto prima e dopo aver cambiato prompt, modello o
documenti della knowledge base:

    cd backend
    .venv/bin/python -m evals.run_chat_eval                  # tutti i casi
    .venv/bin/python -m evals.run_chat_eval --only creatina-dose,tribulus
    .venv/bin/python -m evals.run_chat_eval --save-baseline  # nuovo riferimento

**Consuma quota Gemini**: una richiesta per caso (circa 40), con una pausa fra
le chiamate per restare sotto il limite al minuto del piano gratuito. Usa un
database temporaneo in memoria con profili di prova: nessun dato reale.

Ogni risposta viene controllata in modo deterministico (vedi
`chat_golden_set.json`): dati attesi presenti, frasi vietate assenti, nessuna
azione verso gli integratori se non se ne è parlato, lunghezza contenuta. Il
risultato viene salvato in `evals/results/` e confrontato con
`evals/baseline.json`: i casi che prima passavano e ora falliscono sono
regressioni, e lo script esce con codice 1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import SupplementDeclaration, UserProfile
from app.services import chat_agent, llm_client

DIR = Path(__file__).resolve().parent
GOLDEN = DIR / "chat_golden_set.json"
BASELINE = DIR / "baseline.json"
RESULTS = DIR / "results"
MAX_WORDS = 230


def normalize(text: str) -> str:
    """Minuscole, trattini uniformi e senza spazi attorno, virgola decimale → punto."""
    t = text.lower().replace("–", "-").replace("—", "-")
    t = re.sub(r"\s*-\s*", "-", t)
    return re.sub(r"(\d),(\d)", r"\1.\2", t)


def check(case: dict, reply: chat_agent.ChatReply) -> list[str]:
    """Problemi trovati nella risposta; lista vuota = superato."""
    problemi = []
    testo = normalize(reply.answer)

    attese = case.get("answer_any") or []
    if attese and not any(normalize(a) in testo for a in attese):
        problemi.append(f"manca uno fra {attese}")
    for vietata in case.get("answer_none") or []:
        if normalize(vietata) in testo:
            problemi.append(f"contiene «{vietata}»")
    if not case.get("supplement_action") and any(
        a.get("section") == "integratori" for a in reply.actions
    ):
        problemi.append("azione verso Integratori senza che se ne sia parlato")
    parole = len(reply.answer.split())
    if parole > MAX_WORDS:
        problemi.append(f"troppo lunga ({parole} parole)")
    return problemi


def build_profiles(db, profili: dict) -> dict[str, UserProfile]:
    creati = {}
    for nome, dati in profili.items():
        dati = dict(dati)
        integratori = dati.pop("supplements", [])
        dati["birth_date"] = dt.date.fromisoformat(dati["birth_date"])
        p = UserProfile(display_name=f"prova-{nome}", **dati)
        db.add(p)
        db.flush()
        for i in integratori:
            db.add(SupplementDeclaration(profile_id=p.id, **i))
        creati[nome] = p
    db.commit()
    return creati


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="id dei casi da eseguire, separati da virgola")
    parser.add_argument("--pause", type=float, default=4.5, help="secondi fra una chiamata e l'altra")
    parser.add_argument("--save-baseline", action="store_true", help="salva questo risultato come riferimento")
    args = parser.parse_args()

    if not llm_client.is_configured():
        print("GEMINI_API_KEY non configurata: niente da valutare.")
        return 2

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    casi = golden["casi"]
    if args.only:
        scelti = set(args.only.split(","))
        casi = [c for c in casi if c["id"] in scelti]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    profili = build_profiles(db, golden["profili"])

    esiti = {}
    for n, caso in enumerate(casi, 1):
        if n > 1:
            time.sleep(args.pause)
        reply = chat_agent.answer(db, profili[caso["profilo"]], caso["question"], history=caso.get("history"))
        if not reply.used_llm:
            stato, problemi = "non valutato", [reply.answer[:120]]
        else:
            problemi = check(caso, reply)
            stato = "ok" if not problemi else "fallito"
        esiti[caso["id"]] = {
            "stato": stato,
            "categoria": caso["categoria"],
            "problemi": problemi,
            "risposta": reply.answer,
            "azioni": reply.actions,
        }
        segno = {"ok": "✓", "fallito": "✗", "non valutato": "?"}[stato]
        print(f"{segno} {caso['id']:28} {'; '.join(problemi)[:110]}")

    valutati = [e for e in esiti.values() if e["stato"] != "non valutato"]
    superati = sum(e["stato"] == "ok" for e in valutati)
    print(f"\nSuperati {superati}/{len(valutati)} ({len(esiti) - len(valutati)} non valutati)")
    per_categoria = Counter(e["categoria"] for e in valutati if e["stato"] == "ok")
    totali = Counter(e["categoria"] for e in valutati)
    for categoria in sorted(totali):
        print(f"  {categoria:14} {per_categoria[categoria]}/{totali[categoria]}")

    risultato = {
        "data": dt.datetime.now().isoformat(timespec="seconds"),
        "modello": llm_client.get_settings().gemini_model,
        "superati": superati,
        "valutati": len(valutati),
        "casi": esiti,
    }
    RESULTS.mkdir(exist_ok=True)
    percorso = RESULTS / f"{dt.datetime.now():%Y-%m-%d-%H%M}.json"
    percorso.write_text(json.dumps(risultato, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Risultato salvato in {percorso.relative_to(DIR.parent)}")

    regressioni = []
    if BASELINE.exists():
        riferimento = json.loads(BASELINE.read_text(encoding="utf-8"))["casi"]
        regressioni = [
            cid for cid, e in esiti.items()
            if e["stato"] == "fallito" and riferimento.get(cid, {}).get("stato") == "ok"
        ]
        if regressioni:
            print(f"REGRESSIONI rispetto al riferimento: {', '.join(regressioni)}")

    if args.save_baseline:
        BASELINE.write_text(json.dumps(risultato, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Salvato come nuovo riferimento (evals/baseline.json)")

    return 1 if regressioni else 0


if __name__ == "__main__":
    sys.exit(main())
