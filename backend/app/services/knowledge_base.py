"""Accesso ai documenti della knowledge base.

Implementa il meccanismo descritto in `app/knowledge_base/README.md`: ogni
richiesta all'agente dichiara uno o più tag, e vengono caricati solo i
documenti pertinenti da iniettare nel prompt.

Non serve un motore vettoriale: l'insieme degli argomenti è piccolo e noto
in anticipo, quindi una mappa tag -> file è più semplice, più veloce e
soprattutto **ispezionabile** — si può sempre dire esattamente quali fonti
hanno prodotto un consiglio, che è il requisito posto da
`evidence_conduct.md`.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("knowledge_base")

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"

# Mappa tag -> file. Questa è la fonte di verità del meccanismo di
# retrieval; la tabella nel README della knowledge base ne è la
# documentazione leggibile.
TAG_TO_FILE: dict[str, str] = {
    # Sicurezza
    "screening": "screening_and_red_flags.md",
    "deficit_calorico": "energy_availability_reds.md",
    "reds": "energy_availability_reds.md",
    # Allenamento
    "volume_allenamento": "training_volume.md",
    "recupero": "rest_periods_and_rir.md",
    "intensità": "rest_periods_and_rir.md",
    "cedimento": "proximity_to_failure.md",
    "doms": "doms_and_autoregulation.md",
    "autoregolazione": "doms_and_autoregulation.md",
    "scelta_esercizi": "exercise_choice_and_focus.md",
    "focus_attentivo": "exercise_choice_and_focus.md",
    "attivita_generale": "who_physical_activity.md",
    "calorie": "calorie_and_1rm_formulas.md",
    "1rm": "calorie_and_1rm_formulas.md",
    "ipertrofia": "hypertrophy_prescription.md",
    "tecniche_avanzate": "hypertrophy_prescription.md",
    "cardio": "hypertrophy_prescription.md",
    "biomeccanica": "biomechanics_technique.md",
    "tecnica_esecuzione": "biomechanics_technique.md",
    "ampiezza_movimento": "biomechanics_technique.md",
    "progressione": "resistance_training_acsm.md",
    "forza": "resistance_training_acsm.md",
    "frequenza_allenamento": "resistance_training_acsm.md",
    "periodizzazione": "resistance_training_acsm.md",
    # Nutrizione
    "composizione_corporea": "diets_body_composition.md",
    "surplus_calorico": "diets_body_composition.md",
    "tipi_dieta": "diets_body_composition.md",
    "proteine": "protein_intake.md",
    "macronutrienti": "macronutrients_efsa.md",
    "zuccheri": "macronutrients_efsa.md",
    "micronutrienti": "micronutrients_efsa.md",
    "timing_pasti": "nutrient_timing.md",
    "idratazione": "hydration.md",
    "porzioni": "standard_portions.md",
    "vegetariano": "vegetarian_vegan_nutrition.md",
    "vegano": "vegetarian_vegan_nutrition.md",
    # Integratori
    "creatina": "creatine.md",
    "caffeina": "caffeine.md",
    "glutammina": "glutamine.md",
    "beta_alanina": "beta_alanine.md",
    "hmb": "hmb.md",
    "bcaa": "bcaa.md",
    "citrullina": "citrulline_malate.md",
    "vitamina_d": "vitamin_d_omega3_supplementation.md",
    "omega3": "vitamin_d_omega3_supplementation.md",
    "qualita_prodotto": "supplement_quality_safety.md",
    "integratori_oltre_muscolo": "supplements_beyond_muscle.md",
    "categorie_integratori": "supplement_evidence_categories.md",
}

# Regole di condotta: vanno in **ogni** prompt di generazione, qualunque sia
# l'argomento. Definiscono come l'agente deve pesare l'evidenza, comunicare
# l'incertezza e comportarsi sugli argomenti che la knowledge base non copre.
ALWAYS_INCLUDED = "evidence_conduct.md"


class KnowledgeBaseError(RuntimeError):
    """Documento della knowledge base mancante o illeggibile."""


@lru_cache(maxsize=64)
def load_document(filename: str) -> str:
    """Legge un documento (in cache: i file non cambiano a runtime)."""
    path = KB_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise KnowledgeBaseError(f"Documento non leggibile: {filename}") from e


def resolve_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    """Traduce i tag nei nomi file corrispondenti, senza duplicati.

    Un tag sconosciuto viene ignorato con un warning invece di sollevare:
    è preferibile generare un consiglio con un documento in meno piuttosto
    che far fallire l'intera richiesta.
    """
    files: list[str] = []
    for tag in tags:
        filename = TAG_TO_FILE.get(tag)
        if filename is None:
            logger.warning("Tag sconosciuto nella knowledge base: %r", tag)
            continue
        if filename not in files:
            files.append(filename)
    return files


def build_context(tags: list[str] | tuple[str, ...]) -> str:
    """Assembla il testo da iniettare nel prompt per i tag richiesti.

    `evidence_conduct.md` è sempre incluso, in coda: è la regola di condotta
    trasversale, non il contenuto specifico della richiesta.
    """
    filenames = resolve_tags(tags)
    if ALWAYS_INCLUDED not in filenames:
        filenames.append(ALWAYS_INCLUDED)

    blocchi = []
    for filename in filenames:
        try:
            blocchi.append(f"### FONTE: {filename}\n\n{load_document(filename)}")
        except KnowledgeBaseError as e:
            logger.warning("%s", e)

    return "\n\n---\n\n".join(blocchi)


def available_tags() -> list[str]:
    return sorted(TAG_TO_FILE)
