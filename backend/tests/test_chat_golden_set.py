"""Set di prova della chat, parte deterministica (senza rete né quota).

Per ogni domanda di `evals/chat_golden_set.json` verifica che:
  - vengano richiamati i documenti giusti;
  - nel testo mandato a Gemini ci siano davvero le frasi con i dati per
    rispondere (se il dato non arriva, nessun modello può rispondere bene).

La parte che interroga Gemini sta in `evals/run_chat_eval.py` e si lancia a
mano, perché consuma quota.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import chat_agent, knowledge_base

GOLDEN = json.loads(
    (Path(__file__).resolve().parent.parent / "evals" / "chat_golden_set.json").read_text(encoding="utf-8")
)
CASI = GOLDEN["casi"]


def test_set_di_prova_ben_formato():
    ids = [c["id"] for c in CASI]
    assert len(ids) == len(set(ids)), "id duplicati"
    assert len(CASI) >= 40
    for c in CASI:
        assert c["profilo"] in GOLDEN["profili"], c["id"]
        for tag in c["tags"]:
            assert tag in knowledge_base.TAG_TO_FILE, (c["id"], tag)


@pytest.mark.parametrize("caso", CASI, ids=[c["id"] for c in CASI])
def test_la_domanda_richiama_i_documenti_giusti(caso):
    trovati = chat_agent._tags_for(caso["question"])
    mancanti = [t for t in caso["tags"] if t not in trovati]
    assert not mancanti, f"tag mancanti {mancanti}, trovati {trovati}"


@pytest.mark.parametrize("caso", CASI, ids=[c["id"] for c in CASI])
def test_i_dati_per_rispondere_arrivano_nel_prompt(caso):
    contesto = chat_agent.sources_for(caso["question"])
    mancanti = [a for a in caso["anchors"] if a not in contesto]
    assert not mancanti, f"frasi non inviate al modello: {mancanti}"
