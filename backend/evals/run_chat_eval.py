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
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import SupplementDeclaration, UserProfile
from app.services import chat_agent, llm_client
from evals import harness

DIR = Path(__file__).resolve().parent
GOLDEN = DIR / "chat_golden_set.json"
BASELINE = DIR / "baseline.json"
MAX_WORDS = 230


def check(case: dict, reply: chat_agent.ChatReply) -> list[str]:
    """Problemi trovati nella risposta; lista vuota = superato."""
    problemi = []

    attese = case.get("answer_any") or []
    if not harness.una_fra(reply.answer, attese):
        problemi.append(f"manca uno fra {attese}")
    for vietata in harness.nessuna_fra(reply.answer, case.get("answer_none")):
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
    harness.argomenti_comuni(parser)
    parser.add_argument("--pause", type=float, default=4.5, help="secondi fra una chiamata e l'altra")
    args = parser.parse_args()

    if not llm_client.is_configured():
        print("GEMINI_API_KEY non configurata: niente da valutare.")
        return 2

    golden = harness.carica_golden(GOLDEN)
    casi = harness.seleziona(golden["casi"], args.only)

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
            stato, problemi = harness.NON_VALUTATO, [reply.answer[:120]]
        else:
            problemi = check(caso, reply)
            stato = harness.stato_di(problemi)
        esiti[caso["id"]] = {
            "stato": stato,
            "categoria": caso["categoria"],
            "problemi": problemi,
            "risposta": reply.answer,
            "azioni": reply.actions,
        }
        harness.stampa_esito(caso["id"], stato, problemi)

    return harness.finalizza(
        esiti,
        baseline=BASELINE,
        intestazione={"modello": llm_client.get_settings().gemini_model},
        salva_baseline=args.save_baseline,
    )


if __name__ == "__main__":
    sys.exit(main())
