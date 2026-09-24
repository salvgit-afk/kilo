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

import base64
import json
import logging
import random
import time
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


# Errori temporanei del server: vale la pena riprovare. Il 429 no: sul piano
# gratuito di solito è la quota esaurita, e riprovare subito non serve.
RETRY_STATUSES = {500, 502, 503, 504}
RETRY_BACKOFF_SECONDS = (1.0, 3.0)


def generate_structured(
    prompt: str,
    response_schema: dict[str, Any],
    *,
    system: str | None = None,
    temperature: float = 0.2,
    timeout: float = 30.0,
    model: str | None = None,
    max_output_tokens: int | None = None,
    purpose: str = "generico",
    image: tuple[bytes, str] | None = None,
) -> dict[str, Any]:
    """Chiede a Gemini una risposta JSON conforme a `response_schema`.

    - `system` va nel `systemInstruction` di Gemini: regole e dati fidati
      separati dal testo dell'utente, che resiste meglio a chi prova a
      scavalcarle;
    - `timeout` è il tempo **complessivo**, nuovi tentativi compresi;
    - `purpose` etichetta la chiamata nei log dei token consumati;
    - `image` è una coppia (byte, tipo MIME) inviata insieme al testo: serve
      per leggere un'etichetta nutrizionale o riconoscere un piatto. L'immagine
      va in fondo alle parti, dopo le istruzioni: è un dato da guardare, non
      una fonte di ordini.

    Solleva `LLMNotConfigured` / `LLMError`: sta al chiamante decidere il
    fallback (di norma: generare comunque l'output in modo deterministico dai
    parametri della knowledge base, senza il testo esplicativo dell'LLM).
    """
    settings = get_settings()
    if not settings.gemini_configured:
        raise LLMNotConfigured("GEMINI_API_KEY non configurata nel file .env")

    config: dict[str, Any] = {
        "temperature": temperature,
        "responseMimeType": "application/json",
        "responseSchema": response_schema,
    }
    if max_output_tokens:
        config["maxOutputTokens"] = max_output_tokens
    parti: list[dict[str, Any]] = [{"text": prompt}]
    if image is not None:
        dati_immagine, tipo = image
        parti.append(
            {"inlineData": {"mimeType": tipo, "data": base64.b64encode(dati_immagine).decode()}}
        )
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parti}],
        "generationConfig": config,
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    modello = model or settings.gemini_model
    scadenza = time.monotonic() + timeout
    try:
        # La chiave va nell'header e non nell'URL: gli URL finiscono nei log
        # (httpx li registra a livello INFO), gli header no.
        resp = _send(modello, payload, settings.gemini_api_key, scadenza)
        if resp.status_code == 404 and modello != fallback_model(modello):
            # Versione fissata ritirata da Google.
            logger.warning(
                "Modello %s non disponibile: uso %s", modello, fallback_model(modello)
            )
            modello = fallback_model(modello)
            resp = _send(modello, payload, settings.gemini_api_key, scadenza)
        if resp.status_code == 429:
            raise LLMQuotaExceeded("Limite di richieste Gemini raggiunto")
        resp.raise_for_status()

        dati = resp.json()
        _log_usage(purpose, modello, dati.get("usageMetadata") or {})
        candidato = dati["candidates"][0]
        if candidato.get("finishReason") == "MAX_TOKENS":
            raise LLMError(f"Risposta troncata dal limite di {max_output_tokens} token")
        return json.loads(candidato["content"]["parts"][0]["text"])
    except LLMQuotaExceeded:
        logger.warning("Quota Gemini esaurita (%s, %s)", modello, purpose)
        raise
    except LLMError:
        raise
    except Exception as e:
        logger.warning("Chiamata LLM fallita (%s): %s", purpose, e)
        raise LLMError(str(e)) from e


def _send(
    model: str, payload: dict[str, Any], api_key: str, deadline: float
) -> httpx.Response:
    """Una chiamata, con nuovi tentativi sugli errori temporanei finché resta tempo."""
    for tentativo in range(len(RETRY_BACKOFF_SECONDS) + 1):
        rimasto = deadline - time.monotonic()
        if rimasto <= 0:
            raise LLMError("Tempo massimo per la risposta esaurito")
        try:
            resp = _post(model, payload, api_key, rimasto)
            if resp.status_code not in RETRY_STATUSES:
                return resp
            motivo = f"HTTP {resp.status_code}"
        except (httpx.TimeoutException, httpx.TransportError) as e:
            resp = None
            motivo = type(e).__name__

        if tentativo == len(RETRY_BACKOFF_SECONDS):
            break
        attesa = RETRY_BACKOFF_SECONDS[tentativo] + random.uniform(0, 0.5)
        # Un nuovo tentativo ha senso solo se c'è tempo per la risposta.
        if deadline - time.monotonic() < attesa + 2:
            break
        logger.info("Gemini %s: %s, nuovo tentativo fra %.1f s", model, motivo, attesa)
        time.sleep(attesa)

    if resp is None:
        raise LLMError(f"Gemini non raggiungibile ({motivo})")
    return resp


def _log_usage(purpose: str, model: str, usage: dict[str, Any]) -> None:
    """Token consumati per chiamata: è così che la quota si tiene d'occhio
    sui numeri reali (nei log di Render), non a stima."""
    logger.info(
        "Gemini [%s] %s: %s token in ingresso, %s in uscita, %s di ragionamento",
        purpose,
        model,
        usage.get("promptTokenCount", "?"),
        usage.get("candidatesTokenCount", 0),
        usage.get("thoughtsTokenCount", 0),
    )


def _post(model: str, payload: dict[str, Any], api_key: str, timeout: float) -> httpx.Response:
    return httpx.post(
        _GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": api_key},
        json=payload,
        timeout=timeout,
    )


def stream_structured(
    prompt: str,
    response_schema: dict[str, Any],
    *,
    system: str | None = None,
    temperature: float = 0.2,
    timeout: float = 60.0,
    model: str | None = None,
    max_output_tokens: int | None = None,
    purpose: str = "generico",
):
    """Come `generate_structured`, ma restituisce il JSON un pezzo alla volta.

    Gemini in streaming manda il testo della risposta in frammenti (SSE):
    qui si riemettono man mano, così l'applicazione può mostrare la risposta
    mentre si scrive. Lo schema resta, quindi il risultato finale è lo stesso
    JSON vincolato; chi chiama accumula i frammenti e li interpreta con
    `partial_string` finché non arriva quello completo.

    Genera stringhe (i frammenti grezzi). Se lo streaming fallisce prima del
    primo frammento solleva `LLMError` come la versione non in streaming.
    """
    settings = get_settings()
    if not settings.gemini_configured:
        raise LLMNotConfigured("GEMINI_API_KEY non configurata nel file .env")

    config: dict[str, Any] = {
        "temperature": temperature,
        "responseMimeType": "application/json",
        "responseSchema": response_schema,
    }
    if max_output_tokens:
        config["maxOutputTokens"] = max_output_tokens
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": config,
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    modello = model or settings.gemini_model
    url = _GEMINI_URL.format(model=modello).replace(":generateContent", ":streamGenerateContent")
    try:
        with httpx.stream(
            "POST",
            url,
            params={"alt": "sse"},
            headers={"x-goog-api-key": settings.gemini_api_key},
            json=payload,
            timeout=timeout,
        ) as risposta:
            if risposta.status_code == 429:
                raise LLMQuotaExceeded("Limite di richieste Gemini raggiunto")
            if risposta.status_code >= 400:
                risposta.read()
                raise LLMError(f"HTTP {risposta.status_code}")
            for riga in risposta.iter_lines():
                if not riga.startswith("data:"):
                    continue
                dati = riga[5:].strip()
                if not dati or dati == "[DONE]":
                    continue
                try:
                    blocco = json.loads(dati)
                except ValueError:
                    continue
                if "usageMetadata" in blocco:
                    _log_usage(purpose, modello, blocco["usageMetadata"])
                for candidato in blocco.get("candidates") or []:
                    for parte in (candidato.get("content") or {}).get("parts") or []:
                        testo = parte.get("text")
                        if testo:
                            yield testo
    except LLMError:
        raise
    except Exception as e:
        logger.warning("Streaming LLM fallito (%s): %s", purpose, e)
        raise LLMError(str(e)) from e


def partial_string(raw: str, key: str) -> str:
    """Valore (anche incompleto) di una chiave stringa dentro un JSON a metà.

    Serve a mostrare la risposta mentre arriva: il JSON completo non c'è
    ancora, ma la parte già scritta di `"risposta": "..."` sì. Si fermano le
    sequenze di escape spezzate a metà, che altrimenti comparirebbero a
    schermo come caratteri strani.
    """
    ancora = f'"{key}"'
    inizio = raw.find(ancora)
    if inizio < 0:
        return ""
    i = raw.find('"', inizio + len(ancora) + 1)
    if i < 0:
        return ""
    fuori = []
    i += 1
    while i < len(raw):
        c = raw[i]
        if c == '"':
            break
        if c == "\\":
            sequenza = raw[i : i + 6] if raw[i + 1 : i + 2] == "u" else raw[i : i + 2]
            if len(sequenza) < (6 if raw[i + 1 : i + 2] == "u" else 2):
                break  # escape spezzato dal frammento: si aspetta il resto
            try:
                fuori.append(json.loads(f'"{sequenza}"'))
            except ValueError:
                break
            i += len(sequenza)
            continue
        fuori.append(c)
        i += 1
    return "".join(fuori)
