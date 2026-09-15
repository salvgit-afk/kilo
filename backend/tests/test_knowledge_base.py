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


@pytest.mark.parametrize(
    "tag, attesi",
    [
        ("ipertrofia", ["~10 serie per muscolo a settimana", "**2 minuti** per i multi-articolari"]),
        ("progressione", ["≥80% 1RM", "≥10 serie/settimana", "2-10%"]),
        ("composizione_corporea", ["2,3-3,1 g/kg di massa magra", "0,5-1,0% del peso"]),
        ("categorie_integratori", ["Evidenza forte di efficacia", "tribulus terrestris"]),
        ("creatina", ["3-5 g/giorno", "5-10 g/giorno", "4-6"]),
        ("timing_pasti", ["20-40 g", "0,25-0,40 g/kg", "30-40 g di caseina"]),
        ("biomeccanica", ["2-8 secondi", "+14% contro +9%", "sopra la testa"]),
        ("volume_allenamento", ["0,5", "trascurabile"]),
    ],
)
def test_documenti_da_testo_integrale_contengono_i_parametri_della_fonte(tag, attesi):
    """I documenti letti sul testo integrale devono riportare i numeri chiave
    della fonte: se un'edizione futura li perde, l'agente risponderebbe senza."""
    contesto = kb.build_context([tag])
    mancanti = [a for a in attesi if a not in contesto]
    assert not mancanti, f"{tag}: mancano {mancanti}"


def test_cifre_non_presenti_nelle_fonti_restano_fuori():
    """Due cifre attribuite per errore alle fonti ISSN nella versione
    precedente: non devono tornare come raccomandazioni."""
    assert "0,03 g/kg/giorno" not in kb.build_context(["creatina"]).split("```")[2]
    timing = kb.build_context(["timing_pasti"]).split("```")[2]
    assert "entro 1-4 ore" not in timing


def test_chat_collega_le_domande_ai_nuovi_documenti():
    from app.services.chat_agent import _tags_for

    assert "ipertrofia" in _tags_for("Quante ripetizioni per l'ipertrofia?")
    assert "tipi_dieta" in _tags_for("La dieta chetogenica fa dimagrire di più?")
    assert "categorie_integratori" in _tags_for("Il tribulus serve a qualcosa?")
    assert "surplus_calorico" in _tags_for("Voglio mettere massa")
    assert "ampiezza_movimento" in _tags_for("Conviene il leg curl da seduto per l'allungamento?")


def test_documento_inesistente_solleva_errore_esplicito():
    with pytest.raises(kb.KnowledgeBaseError):
        kb.load_document("non_esiste.md")
