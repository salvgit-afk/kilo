"""Valutazione dell'importazione ricette sul set di prova.

Da lanciare a mano, dopo aver cambiato il prompt di lettura, lo schema JSON
o il modello:

    cd backend
    .venv/bin/python -m evals.run_recipe_eval                  # tutti i casi
    .venv/bin/python -m evals.run_recipe_eval --only pasta-al-tonno
    .venv/bin/python -m evals.run_recipe_eval --save-baseline  # nuovo riferimento

**Non è un test pytest**: è uno script, e i casi «lettura» e «manipolazione»
consumano quota Gemini (fino a due richieste per caso — una per strutturare
il testo, una per convertire in grammi le misure casalinghe — con una pausa
fra le chiamate).

Cosa viene valutato, e con quale modello di responsabilità:

  - il **modello** legge il testo: titolo, porzioni, righe che sono
    ingredienti e con quale quantità. Qui si controllano numero di
    ingredienti riconosciuti, presenza di quelli attesi, porzioni lette
    correttamente e assenza di ingredienti inventati;
  - la **conversione in grammi** passa prima da `parse_measure_directly`
    (deterministica: "80 g", "1,2 kg") e solo per le misure casalinghe
    ("2 cucchiai", "1 spicchio") dal modello. Le attese sono intervalli
    larghi: quello che conta è che la stima sia plausibile;
  - i **valori nutrizionali** non sono in gioco: non vengono mai chiesti al
    modello, li calcola il catalogo alimenti. Per questo qui non si passa da
    `import_from_text` completa, che cercherebbe ogni ingrediente su USDA
    via rete, ma dalle due funzioni che il modello usa davvero.

I casi di categoria «manipolazione» sono prompt injection indiretta: il
testo della ricetta contiene righe che sembrano ordini. L'attesa non è che
il modello le commenti, ma che le legga come testo — ricetta strutturata
normalmente e nessuna traccia di quelle righe nei campi.

I controlli di categoria «deterministico» non toccano il modello e girano
sempre, anche senza chiave: in quel caso il resto risulta «non valutato» e
lo script esce con codice 0.

Codice di uscita: 1 se un controllo deterministico fallisce o se c'è una
regressione rispetto a `evals/recipe_baseline.json`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base
from app.services import llm_client, prompt_safety, recipe_analyzer, recipe_import
from app.services.themealdb_client import RawRecipeIngredient
from evals import harness

DIR = Path(__file__).resolve().parent
GOLDEN = DIR / "recipe_golden_set.json"
BASELINE = DIR / "recipe_baseline.json"


# --- lettura del testo -------------------------------------------------------


def _campi(dati: dict) -> str:
    """Tutto il testo dei campi della ricetta, per cercarci le frasi vietate."""
    pezzi = [str(dati.get("nome") or ""), str(dati.get("preparazione") or "")]
    for voce in dati.get("ingredienti") or []:
        if isinstance(voce, dict):
            pezzi += [str(voce.get(c) or "") for c in ("nome", "nome_en", "quantita")]
    return "\n".join(pezzi)


def _nomi(voce: dict) -> str:
    return f"{voce.get('nome') or ''} {voce.get('nome_en') or ''}"


def calcola_grammi(voci: list[dict], porzioni: int) -> dict[int, tuple[float | None, str]]:
    """Grammi di ogni ingrediente, come li calcolerebbe `recipe_analyzer`.

    Prima la conversione diretta (nessuna chiamata), poi una sola chiamata al
    modello per tutte le misure casalinghe rimaste. Restituisce, per indice,
    i grammi e da dove arrivano ("diretta", "llm", "non riconosciuto").
    """
    esito: dict[int, tuple[float | None, str]] = {}
    da_stimare: list[tuple[int, RawRecipeIngredient]] = []
    for indice, voce in enumerate(voci):
        misura = str(voce.get("quantita") or "")
        grammi = recipe_analyzer.parse_measure_directly(misura)
        if grammi is None:
            da_stimare.append(
                (indice, RawRecipeIngredient(name=str(voce.get("nome_en") or voce.get("nome") or ""), measure=misura))
            )
            esito[indice] = (None, "non riconosciuto")
        else:
            esito[indice] = (grammi, "diretta")

    if da_stimare:
        for indice, grammi in recipe_analyzer._convert_with_llm(da_stimare, porzioni).items():
            esito[indice] = (grammi, "llm")
    return esito


def controlla_lettura(caso: dict, dati: dict, grammi: dict[int, tuple[float | None, str]]) -> list[str]:
    """Problemi della ricetta strutturata; lista vuota = superato."""
    attese = caso.get("attese") or {}
    problemi: list[str] = []

    voci = [v for v in (dati.get("ingredienti") or []) if isinstance(v, dict)]
    minimo, massimo = attese.get("ingredienti", [0, recipe_import.MAX_INGREDIENTS])
    if not minimo <= len(voci) <= massimo:
        problemi.append(f"{len(voci)} ingredienti invece di {minimo}-{massimo}")

    if "porzioni" in attese and dati.get("porzioni") != attese["porzioni"]:
        problemi.append(f"porzioni {dati.get('porzioni')} invece di {attese['porzioni']}")

    elenco = "\n".join(_nomi(v) for v in voci)
    for alternative in attese.get("presenti") or []:
        if not harness.una_fra(elenco, alternative):
            problemi.append(f"manca l'ingrediente {alternative}")
    for inventato in harness.nessuna_fra(elenco, attese.get("assenti")):
        problemi.append(f"ingrediente inventato «{inventato}»")

    for vietata in harness.nessuna_fra(_campi(dati), attese.get("campi_senza")):
        problemi.append(f"«{vietata}» finito nei campi della ricetta")

    for atteso in attese.get("grammi") or []:
        indici = [i for i, v in enumerate(voci) if harness.contiene(_nomi(v), atteso["ingrediente"])]
        if not indici:
            continue  # l'ingrediente manca: già segnalato sopra, se era atteso
        valore, origine = grammi.get(indici[0], (None, "non riconosciuto"))
        basso, alto = atteso["range"]
        if valore is None:
            problemi.append(f"{atteso['ingrediente']}: quantità non convertita")
            continue
        if not basso <= valore <= alto:
            problemi.append(f"{atteso['ingrediente']}: {valore:g} g fuori da {basso}-{alto}")
        atteso_stimato = atteso.get("stimato")
        if atteso_stimato is True and origine != "llm":
            problemi.append(f"{atteso['ingrediente']}: doveva risultare stimato, è «{origine}»")
        if atteso_stimato is False and origine != "diretta":
            problemi.append(f"{atteso['ingrediente']}: quantità scritta nel testo ma letta come «{origine}»")

    return problemi


# --- controlli che non passano dal modello -----------------------------------


def controlli_deterministici(golden: dict) -> dict[str, dict]:
    """Le parti dell'importazione che non dipendono dal modello.

    Girano sempre, anche senza chiave: se cedono è un difetto del codice, non
    una risposta diversa del modello.
    """
    esiti: dict[str, dict] = {}

    # 1. conversioni che non richiedono interpretazione.
    problemi = []
    for voce in golden["conversioni_dirette"]:
        ottenuto = recipe_analyzer.parse_measure_directly(voce["misura"])
        atteso = voce["grammi"]
        if atteso is None and ottenuto is not None:
            problemi.append(f"«{voce['misura']}» convertita a {ottenuto:g} g invece di essere lasciata al modello")
        elif atteso is not None and (ottenuto is None or abs(ottenuto - atteso) > 0.01):
            problemi.append(f"«{voce['misura']}» → {ottenuto} invece di {atteso}")
    esiti["conversioni-dirette"] = {
        "stato": harness.stato_di(problemi),
        "categoria": "deterministico",
        "problemi": problemi,
    }

    # 2. il testo non fidato non può chiudere il tag che lo contiene.
    problemi = []
    for caso in golden["casi"]:
        if not caso.get("tag_da_neutralizzare"):
            continue
        avvolto = prompt_safety.wrap(recipe_import._clean(caso["testo"]), "ricetta")
        if avvolto.count("</ricetta>") != 1 or avvolto.count("<ricetta>") != 1:
            problemi.append(f"{caso['id']}: il testo riesce ancora a chiudere il tag")
    esiti["tag-non-chiudibili"] = {
        "stato": harness.stato_di(problemi),
        "categoria": "deterministico",
        "problemi": problemi,
    }

    # 3. testo troppo corto: rifiutato prima di spendere una chiamata.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    problemi = []
    try:
        recipe_import.import_from_text(db, "ciao")
        problemi.append("testo di 4 caratteri accettato")
    except recipe_import.RecipeImportError as e:
        if "corto" not in str(e).lower():
            problemi.append(f"rifiutato con il messaggio sbagliato: {e}")
    esiti["testo-troppo-corto"] = {
        "stato": harness.stato_di(problemi),
        "categoria": "deterministico",
        "problemi": problemi,
    }

    # 4. senza chiave l'importazione spiega il problema invece di rompersi.
    # La chiave viene tolta e rimessa qui: serve a provare quel ramo anche
    # quando la chiave c'è, senza consumare quota.
    impostazioni = get_settings()
    chiave = impostazioni.gemini_api_key
    problemi = []
    try:
        impostazioni.gemini_api_key = ""
        recipe_import.import_from_text(db, "Torta di mele\n- 200 g di mele\n- 100 g di farina")
        problemi.append("importazione riuscita senza chiave: impossibile")
    except recipe_import.RecipeImportError as e:
        if "disponibile" not in str(e).lower():
            problemi.append(f"messaggio poco chiaro: {e}")
    except Exception as e:  # qualunque altra eccezione arriverebbe all'utente
        problemi.append(f"eccezione non gestita: {type(e).__name__}: {e}")
    finally:
        impostazioni.gemini_api_key = chiave
    esiti["senza-chiave-messaggio-chiaro"] = {
        "stato": harness.stato_di(problemi),
        "categoria": "deterministico",
        "problemi": problemi,
    }

    db.close()
    for cid, esito in esiti.items():
        harness.stampa_esito(cid, esito["stato"], esito["problemi"])
    return esiti


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    harness.argomenti_comuni(parser)
    parser.add_argument("--pause", type=float, default=4.5, help="secondi fra una chiamata e l'altra")
    args = parser.parse_args()

    golden = harness.carica_golden(GOLDEN)
    casi = harness.seleziona(golden["casi"], args.only)

    esiti = controlli_deterministici(golden)

    if not llm_client.is_configured():
        print(
            "\nGEMINI_API_KEY non configurata: la lettura dei testi non può essere "
            "valutata (restano i controlli qui sopra, che non usano il modello)."
        )
        for caso in casi:
            esiti[caso["id"]] = {
                "stato": harness.NON_VALUTATO,
                "categoria": caso["categoria"],
                "problemi": ["serve GEMINI_API_KEY"],
            }
    else:
        for n, caso in enumerate(casi):
            if n:
                time.sleep(args.pause)
            testo = recipe_import._clean(caso["testo"])
            try:
                dati = recipe_import._parse_text(testo)
            except recipe_import.RecipeImportError as e:
                esiti[caso["id"]] = {
                    "stato": harness.NON_VALUTATO,
                    "categoria": caso["categoria"],
                    "problemi": [str(e)],
                }
                harness.stampa_esito(caso["id"], harness.NON_VALUTATO, [str(e)])
                continue

            voci = [v for v in (dati.get("ingredienti") or []) if isinstance(v, dict)]
            porzioni = dati.get("porzioni") if isinstance(dati.get("porzioni"), int) else 1
            grammi = calcola_grammi(voci, max(1, porzioni)) if voci else {}
            problemi = controlla_lettura(caso, dati, grammi)
            stato = harness.stato_di(problemi)
            esiti[caso["id"]] = {
                "stato": stato,
                "categoria": caso["categoria"],
                "problemi": problemi,
                "ricetta": {
                    "nome": dati.get("nome"),
                    "porzioni": dati.get("porzioni"),
                    "ingredienti": [
                        f"{v.get('nome')} ({v.get('nome_en')}) — {v.get('quantita') or 'senza dose'}"
                        f" → {grammi.get(i, (None, ''))[0]} g [{grammi.get(i, (None, 'n/d'))[1]}]"
                        for i, v in enumerate(voci)
                    ],
                },
            }
            harness.stampa_esito(caso["id"], stato, problemi)

    uscita = harness.finalizza(
        esiti,
        baseline=BASELINE,
        prefisso="recipe-",
        intestazione={"modello": llm_client.get_settings().gemini_model},
        salva_baseline=args.save_baseline,
    )

    rotti = [
        cid for cid, e in esiti.items()
        if e["categoria"] == "deterministico" and e["stato"] == harness.FALLITO
    ]
    if rotti:
        print(f"CONTROLLI DETERMINISTICI FALLITI: {', '.join(rotti)}")
        return 1
    return uscita


if __name__ == "__main__":
    sys.exit(main())
