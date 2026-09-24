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


# --- Nuovi tentativi, prompt di sistema, consumo token ------------------------


def test_errore_temporaneo_riprovato(monkeypatch):
    risposte = [_risposta(503), _risposta(200)]
    monkeypatch.setattr(llm_client, "_post", lambda *a: risposte.pop(0))
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    assert llm_client.generate_structured("x", {}) == {"ok": True}
    assert risposte == []


def test_timeout_riprovato(monkeypatch):
    chiamate = []

    def finto_post(*a):
        chiamate.append(1)
        if len(chiamate) == 1:
            raise httpx.ReadTimeout("lento", request=_REQ)
        return _risposta(200)

    monkeypatch.setattr(llm_client, "_post", finto_post)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    assert llm_client.generate_structured("x", {}, timeout=60) == {"ok": True}
    assert len(chiamate) == 2


def test_quota_esaurita_non_riprovata(monkeypatch):
    chiamate = []
    monkeypatch.setattr(llm_client, "_post", lambda *a: chiamate.append(1) or _risposta(429))
    with pytest.raises(llm_client.LLMQuotaExceeded):
        llm_client.generate_structured("x", {})
    assert len(chiamate) == 1


def test_tentativi_limitati(monkeypatch):
    chiamate = []
    monkeypatch.setattr(llm_client, "_post", lambda *a: chiamate.append(1) or _risposta(503))
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    with pytest.raises(llm_client.LLMError):
        llm_client.generate_structured("x", {}, timeout=120)
    assert len(chiamate) == len(llm_client.RETRY_BACKOFF_SECONDS) + 1


def test_nessun_nuovo_tentativo_senza_tempo(monkeypatch):
    """Con il tempo quasi finito si risponde subito, invece di attendere."""
    chiamate = []
    monkeypatch.setattr(llm_client, "_post", lambda *a: chiamate.append(1) or _risposta(503))
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    with pytest.raises(llm_client.LLMError):
        llm_client.generate_structured("x", {}, timeout=2)
    assert len(chiamate) == 1


def test_istruzioni_nel_system_prompt_e_limite_di_uscita(monkeypatch):
    inviati = []
    monkeypatch.setattr(llm_client, "_post", lambda m, payload, k, t: inviati.append(payload) or _risposta(200))
    llm_client.generate_structured("domanda", {}, system="regole", max_output_tokens=500)
    payload = inviati[0]
    assert payload["systemInstruction"]["parts"][0]["text"] == "regole"
    assert payload["contents"][0]["parts"][0]["text"] == "domanda"
    assert payload["generationConfig"]["maxOutputTokens"] == 500


def test_risposta_troncata_segnalata(monkeypatch):
    corpo = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"ok"'}]}}]}
    monkeypatch.setattr(llm_client, "_post", lambda *a: httpx.Response(200, json=corpo, request=_REQ))
    with pytest.raises(llm_client.LLMError, match="troncata"):
        llm_client.generate_structured("x", {}, max_output_tokens=10)


def test_token_consumati_nei_log(monkeypatch, caplog):
    corpo = {
        "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
        "usageMetadata": {"promptTokenCount": 812, "candidatesTokenCount": 95},
    }
    monkeypatch.setattr(llm_client, "_post", lambda *a: httpx.Response(200, json=corpo, request=_REQ))
    with caplog.at_level("INFO", logger="llm_client"):
        llm_client.generate_structured("x", {}, purpose="chat")
    assert "[chat]" in caplog.text and "812" in caplog.text and "95" in caplog.text


def test_la_chat_non_invia_il_nome(db, monkeypatch):
    import datetime as dt

    from app.models import ActivityLevel, ExperienceLevel, Goal, Sex, UserProfile

    p = UserProfile(
        display_name="Mariarosa", birth_date=dt.date(1996, 1, 1), sex=Sex.FEMALE, height_cm=165,
        weight_kg=60, goal=Goal.FAT_LOSS, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add(p)
    db.commit()
    visti = {}

    def finto(prompt, schema, **kwargs):
        visti.update(kwargs, prompt=prompt)
        return {"risposta": "ok", "azioni": []}

    monkeypatch.setattr(llm_client, "generate_structured", finto)
    chat_agent.answer(db, p, "quante proteine mi servono?")
    assert "Mariarosa" not in visti["prompt"] + visti["system"]
    assert "REGOLE VINCOLANTI" in visti["system"]
    assert visti["prompt"].startswith("<domanda>")


# --- Streaming ---------------------------------------------------------------


@pytest.mark.parametrize(
    "grezzo, atteso",
    [
        ('{"risposta": "Ciao, come', "Ciao, come"),
        ('{"risposta": "Riga\\nDue", "azioni": []}', "Riga\nDue"),
        ('{"risposta": "perch\\u00e9', "perché"),
        # Escape spezzato a metà dal frammento: si aspetta il pezzo mancante
        # invece di mostrare caratteri strani.
        ('{"risposta": "perch\\u00', "perch"),
        ('{"azioni": []}', ""),
        ("", ""),
    ],
)
def test_risposta_parziale_mentre_arriva(grezzo, atteso):
    assert llm_client.partial_string(grezzo, "risposta") == atteso


class _FintoStream:
    """Risposta SSE finta, nella forma in cui la manda Gemini."""

    def __init__(self, righe, status_code=200):
        self.righe = righe
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def iter_lines(self):
        return iter(self.righe)

    def read(self):
        return b""


def test_streaming_restituisce_i_frammenti(monkeypatch):
    righe = [
        'data: {"candidates":[{"content":{"parts":[{"text":"{\\"risposta\\": \\"Cia"}]}}]}',
        "",
        'data: {"candidates":[{"content":{"parts":[{"text":"o\\"}"}]}}],"usageMetadata":{"promptTokenCount":10}}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(llm_client.httpx, "stream", lambda *a, **k: _FintoStream(righe))
    pezzi = list(llm_client.stream_structured("domanda", {"type": "object"}))
    assert "".join(pezzi) == '{"risposta": "Ciao"}'
    assert llm_client.partial_string(pezzi[0], "risposta") == "Cia"


def test_streaming_quota_esaurita(monkeypatch):
    monkeypatch.setattr(llm_client.httpx, "stream", lambda *a, **k: _FintoStream([], status_code=429))
    with pytest.raises(llm_client.LLMQuotaExceeded):
        list(llm_client.stream_structured("domanda", {"type": "object"}))


def test_streaming_errore_di_rete_diventa_LLMError(monkeypatch):
    def esplode(*_a, **_k):
        raise llm_client.httpx.ConnectError("rete assente")

    monkeypatch.setattr(llm_client.httpx, "stream", esplode)
    with pytest.raises(llm_client.LLMError):
        list(llm_client.stream_structured("domanda", {"type": "object"}))


def test_chat_in_streaming_manda_pezzi_e_poi_le_azioni(db, monkeypatch):
    """La risposta arriva a pezzi; azioni e fonti solo alla fine."""
    import datetime as dt

    from app.models import ActivityLevel, ExperienceLevel, Goal, Sex, UserProfile

    p = UserProfile(
        display_name="Luca", birth_date=dt.date(1996, 1, 1), sex=Sex.MALE, height_cm=180,
        weight_kg=80, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add(p)
    db.commit()

    pezzi = [
        '{"risposta": "Per la massa ',
        'servono 1,6-2,2 g/kg.", "azioni": [',
        '{"tipo": "apri_sezione", "etichetta": "Apri il diario", "valore": "diario"}]}',
    ]
    monkeypatch.setattr(llm_client, "stream_structured", lambda *a, **k: iter(pezzi))

    eventi = list(chat_agent.answer_stream(db, p, "quante proteine per la massa?"))
    testo = "".join(v for t, v in eventi if t == "delta")
    tipo, finale = eventi[-1]
    assert testo == "Per la massa servono 1,6-2,2 g/kg."
    assert tipo == "done" and finale.answer == testo
    assert finale.actions and finale.actions[0]["section"] == "diario"
    assert "proteine" in finale.knowledge_tags


def test_chat_in_streaming_risposta_troncata_non_perde_il_testo(db, monkeypatch):
    import datetime as dt

    from app.models import ActivityLevel, ExperienceLevel, Goal, Sex, UserProfile

    p = UserProfile(
        display_name="Luca", birth_date=dt.date(1996, 1, 1), sex=Sex.MALE, height_cm=180,
        weight_kg=80, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add(p)
    db.commit()
    monkeypatch.setattr(
        llm_client, "stream_structured", lambda *a, **k: iter(['{"risposta": "Ti sp'])
    )
    _, finale = list(chat_agent.answer_stream(db, p, "dimmi qualcosa"))[-1]
    assert finale.answer == "Ti sp" and finale.actions == []


def test_chat_in_streaming_quota_esaurita(db, monkeypatch):
    import datetime as dt

    from app.models import ActivityLevel, ExperienceLevel, Goal, Sex, UserProfile

    p = UserProfile(
        display_name="Luca", birth_date=dt.date(1996, 1, 1), sex=Sex.MALE, height_cm=180,
        weight_kg=80, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add(p)
    db.commit()

    def esaurita(*_a, **_k):
        raise llm_client.LLMQuotaExceeded("quota")
        yield  # pragma: no cover

    monkeypatch.setattr(llm_client, "stream_structured", esaurita)
    eventi = list(chat_agent.answer_stream(db, p, "ciao"))
    assert len(eventi) == 1 and "esaurito i messaggi" in eventi[0][1].answer


def test_la_chat_normale_e_quella_in_streaming_usano_lo_stesso_prompt(db, monkeypatch):
    """Se le due strade divergessero, le evals coprirebbero solo una delle due."""
    import datetime as dt

    from app.models import ActivityLevel, ExperienceLevel, Goal, Sex, UserProfile

    p = UserProfile(
        display_name="Luca", birth_date=dt.date(1996, 1, 1), sex=Sex.MALE, height_cm=180,
        weight_kg=80, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.BEGINNER,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=3,
    )
    db.add(p)
    db.commit()
    visti = {}

    def finto(prompt, schema, **kwargs):
        visti["normale"] = (prompt, kwargs.get("system"))
        return {"risposta": "ok", "azioni": []}

    def finto_stream(prompt, schema, **kwargs):
        visti["stream"] = (prompt, kwargs.get("system"))
        return iter(['{"risposta": "ok"}'])

    monkeypatch.setattr(llm_client, "generate_structured", finto)
    monkeypatch.setattr(llm_client, "stream_structured", finto_stream)
    chat_agent.answer(db, p, "quante serie a settimana?")
    list(chat_agent.answer_stream(db, p, "quante serie a settimana?"))
    assert visti["normale"] == visti["stream"]
