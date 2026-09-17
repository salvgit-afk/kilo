"""Test del client Gemini: versione ritirata e quota esaurita.

Nessuna chiamata di rete: `_post` viene sostituito con risposte finte.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.services import chat_agent, llm_client

_REQ = httpx.Request("POST", "https://example.test")


def _risposta(status: int, testo: str = '{"ok": true}') -> httpx.Response:
    corpo = {"candidates": [{"content": {"parts": [{"text": testo}]}}]}
    return httpx.Response(status, json=corpo, request=_REQ)


@pytest.fixture(autouse=True)
def chiave(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "finta")


def test_versione_fissa_come_default():
    assert "latest" not in get_settings().gemini_model


def test_modello_ritirato_ripiega_sull_alias(monkeypatch):
    chiamati = []

    def finto_post(model, payload, api_key, timeout):
        chiamati.append(model)
        return _risposta(404) if model == "gemini-3.5-flash-lite" else _risposta(200)

    monkeypatch.setattr(llm_client, "_post", finto_post)
    assert llm_client.generate_structured("x", {}, model="gemini-3.5-flash-lite") == {"ok": True}
    assert chiamati == ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"]


def test_alias_della_stessa_famiglia():
    assert llm_client.fallback_model("gemini-3.5-flash-lite") == "gemini-flash-lite-latest"
    assert llm_client.fallback_model("gemini-3.5-flash") == "gemini-flash-latest"


def test_quota_esaurita_riconosciuta(monkeypatch):
    monkeypatch.setattr(llm_client, "_post", lambda *a: _risposta(429))
    with pytest.raises(llm_client.LLMQuotaExceeded):
        llm_client.generate_structured("x", {})


def test_quota_esaurita_non_blocca_le_traduzioni_per_sempre():
    """Chi intercetta `LLMError` (traduzioni) gestisce anche la quota."""
    assert issubclass(llm_client.LLMQuotaExceeded, llm_client.LLMError)


def test_chat_spiega_la_quota_esaurita(monkeypatch, db):
    import datetime as dt

    from app.models import ActivityLevel, ExperienceLevel, Goal, Sex, UserProfile

    p = UserProfile(
        display_name="t", birth_date=dt.date(1996, 1, 1), sex=Sex.MALE, height_cm=178,
        weight_kg=76, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add(p)
    db.commit()

    def esaurita(*a, **k):
        raise llm_client.LLMQuotaExceeded("429")

    monkeypatch.setattr(llm_client, "generate_structured", esaurita)
    risposta = chat_agent.answer(db, p, "quante serie devo fare?")
    assert "domani" in risposta.answer
    assert risposta.used_llm is False
