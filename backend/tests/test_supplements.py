"""Test della sezione integratori.

Due proprietà da garantire, in ordine di importanza:

1. **L'agente non propone integratori.** È una sezione facoltativa: se
   l'utente non dichiara nulla, non deve uscirne alcun consiglio.
2. **L'evidenza non viene appiattita.** Creatina e glutammina non stanno
   sullo stesso piano, e dirlo è il valore aggiunto rispetto a un'app che
   asseconda l'utente.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import (
    ActivityLevel,
    EvidenceTier,
    ExperienceLevel,
    Goal,
    Sex,
    SupplementDeclaration,
    SupplementKind,
    UserProfile,
)
from app.services import supplements as sup


@pytest.fixture
def profilo(db) -> UserProfile:
    p = UserProfile(
        display_name="test",
        birth_date=dt.date(1996, 5, 20),
        sex=Sex.MALE,
        height_cm=178.0,
        weight_kg=76.0,
        goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
        training_days_per_week=4,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _dichiara(db, profilo, **kwargs) -> SupplementDeclaration:
    d = SupplementDeclaration(profile_id=profilo.id, **kwargs)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


# --- La sezione è facoltativa -------------------------------------------------


def test_nessun_integratore_dichiarato_nessun_consiglio(db, profilo):
    """Chi non usa integratori non deve ricevere suggerimenti per iniziare:
    è una sezione a cui si accede, non un consiglio che arriva da solo."""
    assert sup.assess_all(db, profilo) == []


def test_nessun_contributo_proteico_senza_dichiarazioni(db, profilo):
    assert sup.protein_from_supplements(db, profilo) == 0.0


# --- L'evidenza non viene appiattita -----------------------------------------


@pytest.mark.parametrize(
    "tipo,atteso",
    [
        (SupplementKind.CREATINE, EvidenceTier.STRONG),
        (SupplementKind.CAFFEINE, EvidenceTier.STRONG),
        (SupplementKind.PROTEIN_POWDER, EvidenceTier.STRONG),
        (SupplementKind.BETA_ALANINE, EvidenceTier.MODERATE),
        (SupplementKind.HMB, EvidenceTier.MODERATE),
        (SupplementKind.BCAA, EvidenceTier.WEAK),
        (SupplementKind.GLUTAMINE, EvidenceTier.WEAK),
        (SupplementKind.CITRULLINE, EvidenceTier.WEAK),
    ],
)
def test_livello_di_evidenza_dichiarato(db, profilo, tipo, atteso):
    d = _dichiara(db, profilo, kind=tipo, dose_amount=5, dose_unit="g")
    assert sup.assess(d, profilo).evidence == atteso


def test_glutammina_non_validata_acriticamente(db, profilo):
    """L'utente l'ha nominata, ma questo non la rende efficace."""
    d = _dichiara(db, profilo, kind=SupplementKind.GLUTAMINE, dose_amount=5, dose_unit="g")
    valutazione = sup.assess(d, profilo)

    assert valutazione.evidence == EvidenceTier.WEAK
    assert "non mostrano effetti significativi" in valutazione.message
    # Onestà in entrambe le direzioni: né validata né demonizzata.
    assert "controindicazione" in valutazione.message


def test_bcaa_segnalati_come_ridondanti(db, profilo):
    d = _dichiara(db, profilo, kind=SupplementKind.BCAA, dose_amount=10, dose_unit="g")
    assert "ridondanti" in sup.assess(d, profilo).message


def test_integratore_sconosciuto_non_riceve_dosaggio_inventato(db, profilo):
    """Regola di `evidence_conduct.md` per gli argomenti non coperti."""
    d = _dichiara(db, profilo, kind=SupplementKind.OTHER, product_name="Ashwagandha")
    valutazione = sup.assess(d, profilo)

    assert valutazione.evidence == EvidenceTier.UNKNOWN
    assert "non ho una fonte verificata" in valutazione.message.lower()
    assert valutazione.dose_in_range is None


# --- L'evidenza è riferita a un esito, non all'integratore in sé -------------


def test_glutammina_ha_esiti_con_evidenza_diversa(db, profilo):
    """Non fa crescere il muscolo **e** riduce marcatori intestinali ad alte
    dosi: sono entrambe vere, riportarne una sola dà un'immagine falsa."""
    d = _dichiara(db, profilo, kind=SupplementKind.GLUTAMINE, dose_amount=5, dose_unit="g")
    valutazione = sup.assess(d, profilo)

    assert valutazione.evidence_for("forza e massa") == EvidenceTier.WEAK
    assert valutazione.evidence_for("barriera intestinale") == EvidenceTier.MODERATE


def test_glutammina_sotto_dose_per_leffetto_intestinale(db, profilo):
    """I 5 g venduti per la palestra sono molto lontani dai >30 g a cui
    l'effetto sull'intestino è documentato: chi spera in quello sta usando
    una dose che per quell'esito non fa nulla."""
    d = _dichiara(db, profilo, kind=SupplementKind.GLUTAMINE, dose_amount=5, dose_unit="g")
    messaggio = sup.assess(d, profilo).message

    assert "30 g" in messaggio
    assert "sotto quella soglia" in messaggio


def test_ashwagandha_riconosciuta_su_stress_e_sonno(db, profilo):
    """Valutarla solo sull'ipertrofia la liquiderebbe come inutile, mentre ha
    evidenze discrete su altri esiti."""
    d = _dichiara(
        db, profilo, kind=SupplementKind.ASHWAGANDHA, dose_amount=600, dose_unit="mg"
    )
    valutazione = sup.assess(d, profilo)

    assert valutazione.evidence == EvidenceTier.MODERATE
    assert valutazione.evidence_for("sonno") == EvidenceTier.MODERATE
    assert valutazione.evidence_for("cortisolo") == EvidenceTier.MODERATE
    # Ma senza spacciarla per un sostituto di creatina o proteine.
    assert valutazione.evidence_for("forza e massa") == EvidenceTier.WEAK


def test_ashwagandha_sotto_dose_efficace_segnalata(db, profilo):
    d = _dichiara(
        db, profilo, kind=SupplementKind.ASHWAGANDHA, dose_amount=200, dose_unit="mg"
    )
    valutazione = sup.assess(d, profilo)
    assert valutazione.dose_in_range is False
    assert "600" in valutazione.message


def test_ashwagandha_collega_sonno_e_recupero(db, profilo):
    """Sonno e stress non sono argomenti collaterali: determinano quanto
    volume si riesce a recuperare."""
    d = _dichiara(
        db, profilo, kind=SupplementKind.ASHWAGANDHA, dose_amount=600, dose_unit="mg"
    )
    assert "recuperare" in sup.assess(d, profilo).message


def test_moringa_distingue_poche_prove_da_inefficacia(db, profilo):
    """"Pochi studi" e "non funziona" sono affermazioni diverse."""
    d = _dichiara(db, profilo, kind=SupplementKind.MORINGA, dose_amount=1, dose_unit="g")
    valutazione = sup.assess(d, profilo)

    assert "non significa che non funzioni" in valutazione.message
    assert valutazione.evidence_for("recupero dall'esercizio") == EvidenceTier.UNKNOWN


def test_moringa_non_attribuisce_benefici_non_documentati(db, profilo):
    """Energia e recupero sono ciò che le viene comunemente attribuito, ed è
    proprio dove non ci sono evidenze."""
    d = _dichiara(db, profilo, kind=SupplementKind.MORINGA)
    assert "recupero" in sup.assess(d, profilo).message.lower()


def test_integratori_oltre_il_muscolo_citano_la_fonte(db, profilo):
    for tipo in (SupplementKind.ASHWAGANDHA, SupplementKind.MORINGA, SupplementKind.GLUTAMINE):
        d = _dichiara(db, profilo, kind=tipo, dose_amount=1, dose_unit="g")
        assert "integratori_oltre_muscolo" in sup.assess(d, profilo).knowledge_tags


# --- Creatina -----------------------------------------------------------------


@pytest.mark.parametrize(
    "dose,atteso", [(1.0, False), (3.0, True), (5.0, True), (25.0, False)]
)
def test_dosaggio_creatina_confrontato_col_range(db, profilo, dose, atteso):
    d = _dichiara(db, profilo, kind=SupplementKind.CREATINE, dose_amount=dose, dose_unit="g")
    assert sup.assess(d, profilo).dose_in_range is atteso


def test_creatina_alta_non_genera_allarmismo(db, profilo):
    """La fonte riporta sicurezza fino a 30 g/giorno per 5 anni: la dose alta
    è inutile, non pericolosa, e vanno dette entrambe le cose."""
    d = _dichiara(db, profilo, kind=SupplementKind.CREATINE, dose_amount=25, dose_unit="g")
    messaggio = sup.assess(d, profilo).message
    assert "non c'è beneficio aggiuntivo" in messaggio
    assert "sicurezza" in messaggio


def test_carico_creatina_calcolato_sul_peso(db, profilo):
    """0,3 g/kg: per 76 kg sono ~23 g al giorno."""
    d = _dichiara(db, profilo, kind=SupplementKind.CREATINE)
    assert "23 g" in sup.assess(d, profilo).message


def test_creatina_senza_obbligo_di_ciclizzare(db, profilo):
    d = _dichiara(db, profilo, kind=SupplementKind.CREATINE, dose_amount=5, dose_unit="g")
    assert "ciclizza" in sup.assess(d, profilo).message


# --- Caffeina: due soglie distinte -------------------------------------------


def test_soglia_giornaliera_somma_tutte_le_fonti(db, profilo):
    """Valutare solo il pre-workout ignorerebbe il caffè, che spesso è la
    parte più grossa del totale."""
    d = _dichiara(
        db, profilo, kind=SupplementKind.CAFFEINE, dose_amount=250, dose_unit="mg"
    )
    valutazione = sup.assess(d, profilo, other_caffeine_mg=200)

    assert valutazione.safety_flag is not None
    assert "450 mg" in valutazione.message


def test_range_ergogenico_valutato_sulla_dose_singola(db, profilo):
    """Il range 3-6 mg/kg riguarda la singola assunzione pre-allenamento, il
    tetto EFSA il totale del giorno: sono confronti diversi."""
    d = _dichiara(
        db, profilo, kind=SupplementKind.CAFFEINE, dose_amount=300,
        dose_unit="mg", doses_per_day=1,
    )
    valutazione = sup.assess(d, profilo)
    assert valutazione.dose_in_range is True
    assert "pre-allenamento" in valutazione.message


def test_entrambe_le_soglie_segnalate_quando_superate(db, profilo):
    """Superarle insieme deve produrre due avvisi, non solo il primo."""
    d = _dichiara(
        db, profilo, kind=SupplementKind.CAFFEINE, dose_amount=400,
        dose_unit="mg", doses_per_day=2,
    )
    valutazione = sup.assess(d, profilo, other_caffeine_mg=300)

    assert "giornaliero" in valutazione.safety_flag
    assert "dose singola" in valutazione.safety_flag


def test_caffeina_nella_norma_senza_avvisi(db, profilo):
    d = _dichiara(
        db, profilo, kind=SupplementKind.CAFFEINE, dose_amount=200, dose_unit="mg"
    )
    assert sup.assess(d, profilo, other_caffeine_mg=80).safety_flag is None


# --- Proteine in polvere: sommate, non extra ---------------------------------


def test_proteine_in_polvere_sommate_al_totale(db, profilo):
    """Il target è il totale proteico giornaliero: l'integratore non è un
    "extra" che si aggiunge fuori conteggio."""
    _dichiara(
        db, profilo, kind=SupplementKind.PROTEIN_POWDER,
        protein_g_per_dose=24, doses_per_day=2,
    )
    assert sup.protein_from_supplements(db, profilo) == pytest.approx(48)


def test_totale_proteico_eccessivo_segnalato(db, profilo):
    """Oltre 2,5 g/kg non ci sono benefici aggiuntivi documentati: l'agente
    lo dice invece di lasciar comprare più integratore del necessario."""
    d = _dichiara(
        db, profilo, kind=SupplementKind.PROTEIN_POWDER,
        protein_g_per_dose=30, doses_per_day=3,
    )
    valutazione = sup.assess(d, profilo, protein_from_food_g=160)

    assert valutazione.dose_in_range is False
    assert "non ci sono benefici aggiuntivi" in valutazione.message


def test_totale_proteico_adeguato_non_segnalato(db, profilo):
    d = _dichiara(
        db, profilo, kind=SupplementKind.PROTEIN_POWDER,
        protein_g_per_dose=24, doses_per_day=1,
    )
    assert sup.assess(d, profilo, protein_from_food_g=120).dose_in_range is True


def test_niente_ansia_da_finestra_anabolica(db, profilo):
    """`nutrient_timing.md` corregge il mito dei 30 minuti."""
    d = _dichiara(db, profilo, kind=SupplementKind.PROTEIN_POWDER, protein_g_per_dose=24)
    assert "finestra stretta" in sup.assess(d, profilo).message


# --- Soglie di sicurezza EFSA -------------------------------------------------


def test_vitamina_d_oltre_il_limite_efsa(db, profilo):
    d = _dichiara(
        db, profilo, kind=SupplementKind.VITAMIN_D, dose_amount=150, dose_unit="mcg"
    )
    valutazione = sup.assess(d, profilo)
    assert valutazione.safety_flag is not None
    assert valutazione.dose_in_range is False


def test_vitamina_d_sotto_il_limite_ok(db, profilo):
    d = _dichiara(
        db, profilo, kind=SupplementKind.VITAMIN_D, dose_amount=25, dose_unit="mcg"
    )
    assert sup.assess(d, profilo).safety_flag is None


def test_omega3_ricorda_lolio_algale_ai_vegani(db, profilo):
    d = _dichiara(db, profilo, kind=SupplementKind.OMEGA_3, dose_amount=2, dose_unit="g")
    assert "algale" in sup.assess(d, profilo).message


# --- Tracciabilità e qualità del prodotto ------------------------------------


def test_ogni_valutazione_cita_le_fonti(db, profilo):
    for tipo in (
        SupplementKind.CREATINE, SupplementKind.CAFFEINE, SupplementKind.BCAA,
        SupplementKind.GLUTAMINE, SupplementKind.OTHER,
    ):
        d = _dichiara(db, profilo, kind=tipo, dose_amount=5, dose_unit="g")
        valutazione = sup.assess(d, profilo)
        assert valutazione.knowledge_tags, f"{tipo} senza fonti"
        # Il rischio da contaminazione/etichettatura vale per ogni prodotto.
        assert "qualita_prodotto" in valutazione.knowledge_tags


def test_valutazione_salvata_sulla_dichiarazione(db, profilo):
    _dichiara(db, profilo, kind=SupplementKind.CREATINE, dose_amount=5, dose_unit="g")
    sup.assess_all(db, profilo)

    salvata = db.query(SupplementDeclaration).one()
    assert salvata.agent_assessment
    assert "creatina" in salvata.knowledge_source_tag


def test_integratori_disattivati_ignorati(db, profilo):
    d = _dichiara(db, profilo, kind=SupplementKind.CREATINE, dose_amount=5, dose_unit="g")
    d.is_active = False
    db.commit()

    assert sup.assess_all(db, profilo) == []
