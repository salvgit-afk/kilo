"""Test delle funzioni condivise dalle valutazioni (`evals/harness.py`).

Le valutazioni vere non girano qui: sono script da lanciare a mano e
consumano quota Gemini. Quello che si può e si deve testare senza rete e
senza chiave è il **metro di misura**: se il confronto con le risposte attese
o quello con il riferimento sono sbagliati, tutte le suite mentono insieme,
e mentono in silenzio.
"""

from __future__ import annotations

import json

from evals import harness


def test_normalizza_ignora_come_e_scritto_il_numero():
    # Il dato è lo stesso, la forma no: «8 – 16» e «8-16» devono coincidere.
    assert harness.normalizza("Serie 8 – 16") == harness.normalizza("serie 8-16")
    # Virgola decimale italiana e punto sono la stessa quantità.
    assert harness.normalizza("1,6 g/kg") == "1.6 g/kg"
    assert harness.normalizza("") == ""


def test_contiene_confronta_dopo_la_normalizzazione():
    assert harness.contiene("Tra le 8 — 16 serie", "8-16")
    assert not harness.contiene("12 serie", "8-16")


def test_una_fra_basta_una_alternativa():
    assert harness.una_fra("recupera 90 secondi", ["60", "90"])
    assert not harness.una_fra("recupera 120 secondi", ["60", "90"])


def test_una_fra_senza_attese_non_vincola():
    # Un caso senza `answer_any` non deve fallire per assenza di vincoli.
    assert harness.una_fra("qualunque cosa", [])
    assert harness.una_fra("qualunque cosa", None)


def test_nessuna_fra_elenca_solo_le_frasi_trovate():
    trovate = harness.nessuna_fra("prendi creatina e BCAA", ["creatina", "bcaa", "caffeina"])
    assert trovate == ["creatina", "bcaa"]
    assert harness.nessuna_fra("testo", None) == []


def test_seleziona_filtra_per_id_e_ignora_gli_spazi():
    casi = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert harness.seleziona(casi, "a, c") == [{"id": "a"}, {"id": "c"}]
    assert harness.seleziona(casi, None) == casi


def test_stato_di():
    assert harness.stato_di([]) == harness.OK
    assert harness.stato_di(["qualcosa non va"]) == harness.FALLITO


def test_regressione_solo_se_prima_passava():
    esiti = {
        "peggiorato": {"stato": harness.FALLITO},
        "gia-rotto": {"stato": harness.FALLITO},
        "nuovo": {"stato": harness.FALLITO},
        "migliorato": {"stato": harness.OK},
    }
    riferimento = {
        "peggiorato": {"stato": harness.OK},
        "gia-rotto": {"stato": harness.FALLITO},
        "migliorato": {"stato": harness.FALLITO},
    }
    # Un caso nuovo non ha un «prima» con cui confrontarsi, e un caso già
    # fallito è un problema noto: né l'uno né l'altro sono regressioni.
    assert harness.regressioni(esiti, riferimento) == ["peggiorato"]


def test_regressione_ignora_i_casi_non_valutati():
    esiti = {"saltato": {"stato": harness.NON_VALUTATO}}
    assert harness.regressioni(esiti, {"saltato": {"stato": harness.OK}}) == []


def test_riassunto_conta_solo_i_casi_valutati(capsys):
    esiti = {
        "uno": {"stato": harness.OK, "categoria": "lettura"},
        "due": {"stato": harness.FALLITO, "categoria": "lettura"},
        "tre": {"stato": harness.NON_VALUTATO, "categoria": "lettura"},
    }
    assert harness.riassunto(esiti) == (1, 2)
    assert "Superati 1/2 (1 non valutati)" in capsys.readouterr().out


def test_finalizza_salva_il_risultato_e_segnala_la_regressione(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(harness, "RESULTS", tmp_path / "results")
    baseline = tmp_path / "prova_baseline.json"
    baseline.write_text(
        json.dumps({"casi": {"caso": {"stato": harness.OK}}}), encoding="utf-8"
    )

    esiti = {"caso": {"stato": harness.FALLITO, "categoria": "prova", "problemi": ["rotto"]}}
    assert harness.finalizza(esiti, baseline=baseline, prefisso="prova-") == 1
    assert "REGRESSIONI" in capsys.readouterr().out

    salvati = list((tmp_path / "results").glob("prova-*.json"))
    assert len(salvati) == 1
    risultato = json.loads(salvati[0].read_text(encoding="utf-8"))
    assert risultato["superati"] == 0 and risultato["valutati"] == 1
    assert risultato["casi"] == esiti


def test_finalizza_senza_riferimento_esce_con_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RESULTS", tmp_path / "results")
    esiti = {"caso": {"stato": harness.FALLITO, "categoria": "prova", "problemi": ["rotto"]}}
    # Nessun riferimento: un fallimento non è ancora una regressione, e sta
    # alla suite decidere se è comunque un difetto (le schede lo fanno).
    assert harness.finalizza(esiti, baseline=tmp_path / "manca.json") == 0


def test_save_baseline_scrive_il_nuovo_riferimento(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RESULTS", tmp_path / "results")
    baseline = tmp_path / "prova_baseline.json"
    esiti = {"caso": {"stato": harness.OK, "categoria": "prova", "problemi": []}}
    harness.finalizza(esiti, baseline=baseline, salva_baseline=True)
    assert json.loads(baseline.read_text(encoding="utf-8"))["casi"] == esiti
