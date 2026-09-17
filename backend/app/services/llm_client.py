"""Client LLM (Google Gemini, piano gratuito) con output JSON strutturato.

Estratto dal progetto precedente, dove serviva a normalizzare i nomi dei
merchant: la parte utile è il pattern di chiamata (schema JSON vincolato,
timeout, nessun crash se la chiave manca o l'API fallisce).

**Ruolo dell'LLM in questo progetto**: personalizzare e spiegare, mai
inventare parametri. I numeri (serie, g/kg di proteine, dosaggi) arrivano
dai file in `app/knowledge_base/` e vengono passati nel prompt come vincoli.
Vedi `knowledge_base/evidence_conduct.md`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("llm_client")

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class LLMNotConfigured(RuntimeError):
    """La chiave Gemini non è configurata nel file .env."""


class LLMError(RuntimeError):
    """Chiamata all'LLM fallita (rete, quota, risposta non parsabile)."""


class LLMQuotaExceeded(LLMError):
    """Limite di richieste del piano raggiunto (HTTP 429)."""


def fallback_model(model: str) -> str:
    """Alias "latest" della stessa famiglia, usato se il modello fissato
    viene ritirato: meglio una versione diversa che nessuna risposta."""
    return "gemini-flash-lite-latest" if "lite" in model else "gemini-flash-latest"


def is_configured() -> bool:
    return get_settings().gemini_configured


def generate_structured(
    prompt: str,
    response_schema: dict[str, Any],
    *,
    temperature: float = 0.2,
    timeout: float = 30.0,
    model: str | None = None,
) -> dict[str, Any]:
    """Chiede a Gemini una risposta JSON conforme a `response_schema`.

    Solleva `LLMNotConfigured` / `LLMError`: sta al chiamante decidere il
    fallback (di norma: generare comunque l'output in modo deterministico dai
    parametri della knowledge base, senza il testo esplicativo dell'LLM).
    """
    settings = get_settings()
    if not settings.gemini_configured:
        raise LLMNotConfigured("GEMINI_API_KEY non configurata nel file .env")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }

    modello = model or settings.gemini_model
    try:
        # La chiave va nell'header e non nell'URL: gli URL finiscono nei log
        # (httpx li registra a livello INFO), gli header no.
        resp = _post(modello, payload, settings.gemini_api_key, timeout)
        if resp.status_code == 404 and modello != fallback_model(modello):
            # Versione fissata ritirata da Google.
            logger.warning(
                "Modello %s non disponibile: uso %s", modello, fallback_model(modello)
            )
            resp = _post(fallback_model(modello), payload, settings.gemini_api_key, timeout)
        if resp.status_code == 429:
            raise LLMQuotaExceeded("Limite di richieste Gemini raggiunto")
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except LLMQuotaExceeded:
        logger.warning("Quota Gemini esaurita (%s)", modello)
        raise
    except Exception as e:
        logger.warning("Chiamata LLM fallita: %s", e)
        raise LLMError(str(e)) from e


def _post(model: str, payload: dict[str, Any], api_key: str, timeout: float) -> httpx.Response:
    return httpx.post(
        _GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": api_key},
        json=payload,
        timeout=timeout,
    )
