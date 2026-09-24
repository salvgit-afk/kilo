"""Valutazione della generazione scheda sul set di prova.

Da lanciare a mano, dopo aver toccato i parametri della knowledge base, le
regole di scelta degli esercizi o il prompt di `explain_plan`:

    cd backend
    .venv/bin/python -m evals.run_plan_eval                  # tutti i casi
    .venv/bin/python -m evals.run_plan_eval --only solo-manubri
    .venv/bin/python -m evals.run_plan_eval --save-baseline  # nuovo riferimento

**Non è un test pytest**: è uno script, e i casi «spiegazione» consumano
quota Gemini (una richiesta ciascuno, con una pausa fra le chiamate).

La divisione dei compiti si vede bene qui. La scheda — giorni, serie,
ripetizioni, RIR, recuperi, scelta degli esercizi — è costruita in modo
**deterministico** da `workout_generator`: quei casi girano anche senza
chiave Gemini, ed è proprio la proprietà da non perdere. L'LLM riscrive solo
la motivazione (`explain_plan`); senza chiave quei casi risultano «non
valutati» e lo script esce comunque con codice 0.

Codice di uscita: 1 se un caso «scheda» fallisce (la parte deterministica
non dipende dal modello: se cede è un difetto, non una fluttuazione) oppure
se c'è una regressione rispetto a `evals/plan_baseline.json`.

Catalogo esercizi, profili e screening sono inventati e vivono in uno SQLite
in memoria: nessun dato reale, nessuna rete.
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
from app.models import Exercise, ScreeningRecord, UserProfile
from app.services import llm_client
from app.services import workout_generator as wg
from evals import harness

DIR = Path(__file__).resolve().parent
GOLDEN = DIR / "plan_golden_set.json"
BASELINE = DIR / "plan_baseline.json"


def prepara_db(catalogo: list[dict]):
    """SQLite in memoria con il catalogo esercizi del set di prova."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for n, voce in enumerate(catalogo, 1):
        db.add(
            Exercise(
                # `source` e `external_id` non servono ai controlli, ma il
                # catalogo vero li ha sempre: meglio un catalogo di prova
                # fatto come quello reale.
                source="kilo",
                external_id=f"prova-{n}",
                name=voce["name"],
                primary_muscle=voce["primary_muscle"],
                equipment=voce["equipment"],
                is_compound=voce["is_compound"],
                priority=voce.get("priority", 100),
            )
        )
    db.commit()
    return db


def crea_profilo(db, dati: dict) -> UserProfile:
    dati = dict(dati)
    dati["birth_date"] = dt.date.fromisoformat(dati["birth_date"])
    profilo = UserProfile(display_name="prova-scheda", **dati)
    db.add(profilo)
    db.commit()
    return profilo


def _giorni(plan: wg.GeneratedPlan) -> list[str]:
    """Etichette dei giorni nell'ordine in cui compaiono."""
    return list(dict.fromkeys(e.day_label for e in plan.exercises))


def _attrezzi_richiesti(esercizio: Exercise) -> list[str]:
    equipaggiamento = (esercizio.equipment or "").lower()
    if not equipaggiamento or wg.BODYWEIGHT in equipaggiamento:
        return []
    return [a.strip() for a in equipaggiamento.split(",") if a.strip()]


def controlla_scheda(caso: dict, plan: wg.GeneratedPlan, profilo: UserProfile) -> list[str]:
    """Problemi della scheda generata; lista vuota = superato.

    Ogni controllo è deterministico e verificabile: o il numero di giorni è
    quello chiesto, o non lo è.
    """
    attese = caso.get("attese") or {}
    problemi: list[str] = []
    giorni = _giorni(plan)

    # --- invarianti, valgono per ogni scheda --------------------------------
    for giorno in giorni:
        del_giorno = [e for e in plan.exercises if e.day_label == giorno]
        if len(del_giorno) > wg.MAX_EXERCISES_PER_SESSION:
            problemi.append(f"{giorno}: {len(del_giorno)} esercizi, oltre il tetto di sessione")
        nomi = [e.exercise.name for e in del_giorno]
        if attese.get("no_duplicati_nel_giorno") and len(set(nomi)) != len(nomi):
            ripetuti = sorted({n for n in nomi if nomi.count(n) > 1})
            problemi.append(f"{giorno}: esercizi ripetuti ({', '.join(ripetuti)})")
    for voce in plan.exercises:
        if voce.sets < 1 or voce.reps_min > voce.reps_max:
            problemi.append(f"parametri incoerenti su «{voce.exercise.name}»")
    if not plan.rationale.strip():
        problemi.append("motivazione vuota")

    # --- attese dichiarate nel set di prova ---------------------------------
    if "giorni" in attese and len(giorni) != attese["giorni"]:
        problemi.append(f"{len(giorni)} giorni invece di {attese['giorni']}")
    if "split" in attese and plan.split_type != attese["split"]:
        problemi.append(f"split {plan.split_type} invece di {attese['split']}")

    if attese.get("serie_nel_range_fonti"):
        minimo, _, massimo = wg.weekly_sets_range(profilo)
        fuori = {
            m: s for m, s in plan.weekly_sets_per_muscle.items() if not minimo <= s <= massimo
        }
        if fuori:
            problemi.append(f"serie settimanali fuori dal range {minimo}-{massimo}: {fuori}")

    if attese.get("volume_al_minimo"):
        minimo, _, _ = wg.weekly_sets_range(profilo)
        # +1 di tolleranza: il volume settimanale viene diviso per il numero
        # di sedute e riarrotondato, quindi può fermarsi una serie sopra il
        # minimo senza che il parametro sia cambiato.
        troppo = {m: s for m, s in plan.weekly_sets_per_muscle.items() if s > minimo + 1}
        if troppo:
            problemi.append(f"volume non riportato al minimo ({minimo}): {troppo}")

    if attese.get("attrezzatura_rispettata"):
        consentiti = wg._available_equipment_filter(profilo)
        non_usabili = sorted(
            {e.exercise.name for e in plan.exercises if not wg._is_usable(e.exercise, consentiti)}
        )
        if non_usabili:
            problemi.append(f"attrezzatura non disponibile: {', '.join(non_usabili)}")

    for attrezzo in attese.get("attrezzi_vietati") or []:
        colpevoli = sorted(
            {
                e.exercise.name
                for e in plan.exercises
                if any(attrezzo in richiesto for richiesto in _attrezzi_richiesti(e.exercise))
            }
        )
        if colpevoli:
            problemi.append(f"richiede «{attrezzo}»: {', '.join(colpevoli)}")

    mancanti = [t for t in attese.get("tag_attesi") or [] if t not in plan.knowledge_tags]
    if mancanti:
        problemi.append(f"tag della knowledge base mancanti: {', '.join(mancanti)}")

    for muscolo in attese.get("muscoli_attesi") or []:
        if muscolo not in plan.weekly_sets_per_muscle:
            problemi.append(f"nessuna serie per {muscolo}")

    attese_reps = attese.get("ripetizioni_attese") or {}
    for voce in plan.exercises:
        chiave = "compound" if voce.exercise.is_compound else "isolation"
        atteso = attese_reps.get(chiave)
        if atteso and [voce.reps_min, voce.reps_max] != list(atteso):
            problemi.append(
                f"{voce.exercise.name}: {voce.reps_min}-{voce.reps_max} ripetizioni "
                f"invece di {atteso[0]}-{atteso[1]}"
            )
            break  # un esempio basta: sono tutti uguali per tipologia

    ammessi = attese.get("recuperi_ammessi")
    if ammessi:
        fuori = sorted({e.rest_seconds for e in plan.exercises} - set(ammessi))
        if fuori:
            problemi.append(f"recuperi non previsti: {fuori}")

    if "rir" in attese:
        diversi = sorted({e.rir for e in plan.exercises if e.rir != attese["rir"]})
        if diversi:
            problemi.append(f"RIR {diversi} invece di {attese['rir']}")

    if "nome_contiene" in attese and not harness.contiene(plan.name, attese["nome_contiene"]):
        problemi.append(f"nome «{plan.name}» senza «{attese['nome_contiene']}»")

    for frase in attese.get("motivazione_contiene") or []:
        if not harness.contiene(plan.rationale, frase):
            problemi.append(f"la motivazione non cita «{frase}»")

    avvertenze = " | ".join(plan.warnings)
    for frase in attese.get("avvertenze_contengono") or []:
        if not harness.contiene(avvertenze, frase):
            problemi.append(f"manca l'avvertenza su «{frase}»")
    for frase in harness.nessuna_fra(avvertenze, attese.get("nessuna_avvertenza_contiene")):
        problemi.append(f"avvertenza inattesa su «{frase}»")

    return problemi


def _numeri(plan: wg.GeneratedPlan) -> list[tuple]:
    """Fotografia dei parametri numerici, per verificare che l'LLM non li tocchi."""
    return [
        (e.exercise.id, e.day_label, e.sets, e.reps_min, e.reps_max, e.rir, e.rest_seconds)
        for e in plan.exercises
    ]


def controlla_spiegazione(
    caso: dict, plan: wg.GeneratedPlan, testo: str, numeri_prima: list[tuple]
) -> list[str]:
    """Problemi della spiegazione riscritta dall'LLM."""
    attese = caso.get("attese") or {}
    problemi: list[str] = []

    if attese.get("numeri_scheda_invariati") and _numeri(plan) != numeri_prima:
        problemi.append("la spiegazione ha cambiato i parametri della scheda")

    if not harness.una_fra(testo, attese.get("contiene_una_fra")):
        problemi.append(f"manca uno fra {attese.get('contiene_una_fra')}")
    for vietata in harness.nessuna_fra(testo, attese.get("non_contiene")):
        problemi.append(f"contiene «{vietata}»")

    parole = len(testo.split())
    if "max_parole" in attese and parole > attese["max_parole"]:
        problemi.append(f"troppo lunga ({parole} parole)")
    return problemi


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    harness.argomenti_comuni(parser)
    parser.add_argument("--pause", type=float, default=4.5, help="secondi fra una chiamata e l'altra")
    args = parser.parse_args()

    golden = harness.carica_golden(GOLDEN)
    casi = harness.seleziona(golden["casi"], args.only)
    db = prepara_db(golden["catalogo"])

    con_llm = llm_client.is_configured()
    if not con_llm:
        print(
            "GEMINI_API_KEY non configurata: valuto solo la scheda (parte "
            "deterministica). I casi «spiegazione» restano non valutati."
        )

    esiti: dict[str, dict] = {}
    chiamate = 0
    for caso in casi:
        profilo = crea_profilo(db, golden["profili"][caso["profilo"]])
        screening = (
            ScreeningRecord(profile_id=profilo.id, **caso["screening"])
            if caso.get("screening")
            else None
        )
        plan = wg.generate_plan(db, profilo, screening=screening)

        if caso["categoria"] == "spiegazione":
            if not con_llm:
                esiti[caso["id"]] = {
                    "stato": harness.NON_VALUTATO,
                    "categoria": caso["categoria"],
                    "problemi": ["serve GEMINI_API_KEY"],
                }
                harness.stampa_esito(caso["id"], harness.NON_VALUTATO, ["serve GEMINI_API_KEY"])
                continue
            if chiamate:
                time.sleep(args.pause)
            chiamate += 1
            numeri_prima = _numeri(plan)
            testo = wg.explain_plan(plan, profilo)
            if testo.strip() == plan.rationale.strip():
                # `explain_plan` ripiega sulla motivazione deterministica
                # quando il modello non risponde (quota esaurita, rete): la
                # scheda resta valida, ma non c'è una spiegazione da giudicare.
                motivo = ["il modello non ha risposto: spiegazione deterministica"]
                esiti[caso["id"]] = {
                    "stato": harness.NON_VALUTATO,
                    "categoria": caso["categoria"],
                    "problemi": motivo,
                }
                harness.stampa_esito(caso["id"], harness.NON_VALUTATO, motivo)
                continue
            problemi = controlla_spiegazione(caso, plan, testo, numeri_prima)
            dettagli = {"spiegazione": testo}
        else:
            problemi = controlla_scheda(caso, plan, profilo)
            dettagli = {
                "giorni": _giorni(plan),
                "split": plan.split_type,
                "serie_settimanali": dict(sorted(plan.weekly_sets_per_muscle.items())),
                "esercizi": [f"{e.day_label}: {e.exercise.name} {e.sets}x{e.reps_min}-{e.reps_max}"
                             for e in plan.exercises],
                "avvertenze": plan.warnings,
                "tag": plan.knowledge_tags,
            }

        stato = harness.stato_di(problemi)
        esiti[caso["id"]] = {
            "stato": stato,
            "categoria": caso["categoria"],
            "problemi": problemi,
            **dettagli,
        }
        harness.stampa_esito(caso["id"], stato, problemi)

    uscita = harness.finalizza(
        esiti,
        baseline=BASELINE,
        prefisso="plan-",
        intestazione={"modello": llm_client.get_settings().gemini_model if con_llm else None},
        salva_baseline=args.save_baseline,
    )

    # La parte deterministica non dipende dal modello: se cede è un difetto
    # del generatore, e va segnalato anche senza un riferimento con cui
    # confrontarsi.
    rotte = [
        cid for cid, e in esiti.items()
        if e["categoria"] == "scheda" and e["stato"] == harness.FALLITO
    ]
    if rotte:
        print(f"SCHEDE NON VALIDE (controlli senza LLM): {', '.join(rotte)}")
        return 1
    return uscita


if __name__ == "__main__":
    sys.exit(main())
