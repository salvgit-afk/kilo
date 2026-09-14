"""Test del meccanismo di retrieval della knowledge base.

Verifica che il collegamento fra tag e documenti regga: se si rompe,
l'agente genererebbe consigli senza le fonti che dovrebbero vincolarlo — il
tipo di guasto che non dà errori ma degrada silenziosamente la qualità.
"""

from __future__ import annotations

import pytest

from app.services import knowledge_base as kb


def test_ogni_tag_punta_a_un_file_esistente():
    """Un tag che punta a un file inesistente farebbe generare consigli
    senza la fonte che dovrebbe vincolarli."""
    mancanti = [
        f"{tag} -> {filename}"
        for tag, filename in kb.TAG_TO_FILE.items()
        if not (kb.KB_DIR / filename).is_file()
    ]
    assert not mancanti, f"documenti mancanti: {mancanti}"


def test_documento_di_condotta_presente():
    assert (kb.KB_DIR / kb.ALWAYS_INCLUDED).is_file()


def test_contesto_include_sempre_le_regole_di_condotta():
    """`evidence_conduct.md` definisce come pesare l'evidenza e cosa fare
    sugli argomenti non coperti: va in ogni prompt, non solo quando richiesto."""
    contesto = kb.build_context(["volume_allenamento"])
    assert kb.ALWAYS_INCLUDED in contesto
    assert "training_volume.md" in contesto


def test_tag_multipli_non_duplicano_lo_stesso_file():
    """"recupero" e "intensità" puntano entrambi a rest_periods_and_rir.md."""
    assert kb.resolve_tags(["recupero", "intensità"]) == ["rest_periods_and_rir.md"]


def test_tag_sconosciuto_ignorato_senza_errore():
    """Meglio un consiglio con un documento in meno che una richiesta fallita."""
    assert kb.resolve_tags(["volume_allenamento", "inesistente"]) == [
        "training_volume.md"
    ]


def test_contesto_contiene_i_parametri_numerici_attesi():
    """Controllo di sostanza: il documento sul volume deve contenere davvero
    i range che il generatore applica."""
    contesto = kb.build_context(["volume_allenamento"])
    assert "4-8" in contesto and "8-14" in contesto and "12-20" in contesto


def test_documento_inesistente_solleva_errore_esplicito():
    with pytest.raises(kb.KnowledgeBaseError):
        kb.load_document("non_esiste.md")
