"""Valutazione degli integratori dichiarati dall'utente.

**L'agente non propone integratori.** Questa è una sezione facoltativa, che
si apre solo se l'utente vuole: come il diario alimentare e i suggerimenti
di ricette, è uno strumento a disposizione, non un consiglio che arriva da
solo. Nessuna funzione qui produce raccomandazioni non richieste, e nessuna
scheda o piano alimentare cambia perché l'utente non assume qualcosa.

Quando invece l'utente dichiara cosa assume, l'agente fa tre cose che a mano
sono scomode:

  1. **Somma il contributo ai totali giornalieri.** Le proteine in polvere
     rientrano nel target proteico, non si aggiungono "extra" — l'obiettivo è
     il totale giornaliero, non massimizzare l'integratore.
  2. **Confronta la dose con i range delle fonti**, incluse le soglie di
     sicurezza (la caffeina va sommata fra tutte le fonti, non valutata sul
     solo pre-workout).
  3. **Dichiara onestamente quanto è solida l'evidenza.** Creatina e
     glutammina non stanno sullo stesso piano, e appiattirle sarebbe
     assecondare l'utente invece che informarlo.

Ogni valutazione cita il file della knowledge base da cui proviene.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvidenceTier,
    SupplementDeclaration,
    SupplementKind,
    UserProfile,
)

logger = logging.getLogger("supplements")

# --- Parametri dalle fonti ---------------------------------------------------

# `creatine.md` (ISSN 2017)
CREATINE_MAINTENANCE_G = (3.0, 5.0)
CREATINE_LOADING_G_PER_KG = 0.3

# `caffeine.md` (ISSN 2021): dose ergogenica.
CAFFEINE_MG_PER_KG = (3.0, 6.0)
# `vitamin_d_omega3_supplementation.md` non copre la caffeina; il tetto di
# sicurezza è dell'opinione EFSA sulla caffeina: 400 mg/giorno per l'adulto
# sano, 200 mg in dose singola.
CAFFEINE_DAILY_SAFETY_MG = 400.0
CAFFEINE_SINGLE_DOSE_SAFETY_MG = 200.0

# `beta_alanine.md` (ISSN 2015)
BETA_ALANINE_G = (4.0, 6.0)
# `hmb.md` (ISSN)
HMB_MG_PER_KG = 38.0
# `citrulline_malate.md`
CITRULLINE_G = 8.0
# `supplements_beyond_muscle.md`: soglia oltre la quale si osserva l'effetto
# sulla permeabilità intestinale — molto sopra i 5 g venduti per la palestra.
GLUTAMINE_GUT_EFFECT_G = 30.0
# Dosaggio a cui gli effetti su sonno e stress sono documentati.
ASHWAGANDHA_EFFECTIVE_MG = 600.0
# `vitamin_d_omega3_supplementation.md` (EFSA)
VITAMIN_D_UL_MCG = 100.0
OMEGA3_EPA_DHA_MAX_G = 5.0

# `protein_intake.md`: oltre questa soglia l'apporto proteico non mostra
# benefici aggiuntivi documentati.
PROTEIN_G_PER_KG_POINTLESS_ABOVE = 2.5

KIND_TO_TAG = {
    SupplementKind.PROTEIN_POWDER: "proteine",
    SupplementKind.CREATINE: "creatina",
    SupplementKind.CAFFEINE: "caffeina",
    SupplementKind.BETA_ALANINE: "beta_alanina",
    SupplementKind.HMB: "hmb",
    SupplementKind.BCAA: "bcaa",
    SupplementKind.GLUTAMINE: "glutammina",
    SupplementKind.ASHWAGANDHA: "integratori_oltre_muscolo",
    SupplementKind.MORINGA: "integratori_oltre_muscolo",
    SupplementKind.CITRULLINE: "citrullina",
    SupplementKind.VITAMIN_D: "vitamina_d",
    SupplementKind.OMEGA_3: "omega3",
}

EVIDENCE_BY_KIND = {
    SupplementKind.CREATINE: EvidenceTier.STRONG,
    SupplementKind.CAFFEINE: EvidenceTier.STRONG,
    SupplementKind.PROTEIN_POWDER: EvidenceTier.STRONG,
    SupplementKind.BETA_ALANINE: EvidenceTier.MODERATE,
    SupplementKind.HMB: EvidenceTier.MODERATE,
    SupplementKind.VITAMIN_D: EvidenceTier.MODERATE,
    SupplementKind.OMEGA_3: EvidenceTier.MODERATE,
    SupplementKind.CITRULLINE: EvidenceTier.WEAK,
    SupplementKind.BCAA: EvidenceTier.WEAK,
    SupplementKind.GLUTAMINE: EvidenceTier.WEAK,
    SupplementKind.ASHWAGANDHA: EvidenceTier.MODERATE,
    SupplementKind.MORINGA: EvidenceTier.WEAK,
    SupplementKind.OTHER: EvidenceTier.UNKNOWN,
}


@dataclass
class BenefitFinding:
    """Evidenza riferita a **un esito specifico**.

    Un'etichetta unica per integratore è fuorviante: la glutammina non fa
    crescere il muscolo *e* riduce alcuni marcatori intestinali ad alte dosi.
    Riportare solo la prima metà dà un'immagine falsa.
    """

    domain: str          # "forza e massa", "sonno", "stress", "intestino"...
    evidence: str        # EvidenceTier
    detail: str


@dataclass
class SupplementAssessment:
    declaration: SupplementDeclaration
    evidence: str        # esito principale per cui l'integratore è usato
    message: str
    knowledge_tags: list[str] = field(default_factory=list)
    dose_in_range: bool | None = None   # None = nessun range di riferimento
    safety_flag: str | None = None
    benefits: list[BenefitFinding] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.declaration.kind

    def evidence_for(self, domain: str) -> str | None:
        for beneficio in self.benefits:
            if beneficio.domain == domain:
                return beneficio.evidence
        return None


def _daily_amount(declaration: SupplementDeclaration) -> float | None:
    if declaration.dose_amount is None:
        return None
    return declaration.dose_amount * (declaration.doses_per_day or 1.0)


def _assess_creatine(d: SupplementDeclaration, profile: UserProfile) -> SupplementAssessment:
    giornaliera = _daily_amount(d)
    minimo, massimo = CREATINE_MAINTENANCE_G
    carico = round(profile.weight_kg * CREATINE_LOADING_G_PER_KG)

    if giornaliera is None:
        messaggio = (
            f"Il mantenimento standard è {minimo:.0f}-{massimo:.0f} g al giorno. "
            f"Se preferisci arrivare prima a saturazione puoi fare una fase di "
            f"carico di ~{carico} g al giorno per 5-7 giorni, divisi in 4 dosi — "
            "ma non è obbligatoria: senza carico si arriva allo stesso livello in "
            "circa 4 settimane. Non serve ciclizzare."
        )
        in_range = None
    elif giornaliera < minimo:
        messaggio = (
            f"Stai assumendo {giornaliera:.1f} g al giorno, sotto i {minimo:.0f} g "
            "che servono a mantenere le scorte muscolari sature. Portala a "
            f"{minimo:.0f}-{massimo:.0f} g."
        )
        in_range = False
    elif giornaliera > 10:
        messaggio = (
            f"{giornaliera:.1f} g al giorno sono più del necessario: oltre i "
            f"{massimo:.0f} g di mantenimento non c'è beneficio aggiuntivo "
            "documentato per l'uso sportivo. Nessun allarme però — la fonte ISSN "
            "riporta sicurezza fino a 30 g al giorno per 5 anni."
        )
        in_range = False
    else:
        messaggio = (
            f"{giornaliera:.1f} g al giorno: dosaggio corretto. La creatina "
            "monoidrato è l'integratore con le evidenze più solide in nutrizione "
            "sportiva, e non richiede ciclizzazione."
        )
        in_range = True

    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.STRONG,
        message=messaggio,
        knowledge_tags=["creatina", "qualita_prodotto"],
        dose_in_range=in_range,
    )


def _assess_caffeine(
    d: SupplementDeclaration, profile: UserProfile, *, other_sources_mg: float = 0.0
) -> SupplementAssessment:
    dose_singola = d.dose_amount or 0.0
    da_integratore = _daily_amount(d) or 0.0
    totale = da_integratore + other_sources_mg

    minimo = CAFFEINE_MG_PER_KG[0] * profile.weight_kg
    massimo = CAFFEINE_MG_PER_KG[1] * profile.weight_kg

    parti = []
    sicurezza = None

    if other_sources_mg > 0:
        parti.append(
            f"Totale giornaliero {totale:.0f} mg ({da_integratore:.0f} mg "
            f"dall'integratore + {other_sources_mg:.0f} mg da caffè e altre fonti)."
        )

    # Le due soglie EFSA sono indipendenti e possono essere superate insieme:
    # vanno segnalate entrambe, non solo la prima incontrata.
    superamenti = []

    if totale > CAFFEINE_DAILY_SAFETY_MG:
        superamenti.append("giornaliero")
        parti.append(
            f"Sei sopra i {CAFFEINE_DAILY_SAFETY_MG:.0f} mg al giorno che EFSA "
            "indica come soglia di sicurezza per un adulto sano. Vale la pena "
            "ridurre, contando tutte le fonti."
        )

    if dose_singola > CAFFEINE_SINGLE_DOSE_SAFETY_MG:
        superamenti.append("dose singola")
        parti.append(
            f"Anche la singola assunzione da {dose_singola:.0f} mg supera i "
            f"{CAFFEINE_SINGLE_DOSE_SAFETY_MG:.0f} mg indicati da EFSA come "
            "sicuri in una volta sola: valuta di dividerla."
        )

    if superamenti:
        sicurezza = "oltre la soglia EFSA: " + " e ".join(superamenti)

    # Il range ergogenico (3-6 mg/kg) si riferisce alla **singola assunzione**
    # prima dell'allenamento, mentre il tetto di sicurezza EFSA riguarda il
    # totale della giornata: sono due confronti distinti, e vanno tenuti
    # separati anche nel messaggio, altrimenti sembra che si contraddicano.
    if not dose_singola:
        in_range = None
    elif dose_singola < minimo:
        parti.append(
            f"Come dose pre-allenamento, {dose_singola:.0f} mg sono sotto il range "
            f"utile alla prestazione ({minimo:.0f}-{massimo:.0f} mg per i tuoi "
            f"{profile.weight_kg:.0f} kg)."
        )
        in_range = False
    elif dose_singola <= massimo:
        parti.append(
            f"La dose pre-allenamento da {dose_singola:.0f} mg è nel range utile "
            f"alla prestazione ({minimo:.0f}-{massimo:.0f} mg per il tuo peso). "
            "Il momento tipico è circa un'ora prima della sessione."
        )
        in_range = True
    else:
        parti.append(
            f"Oltre i {massimo:.0f} mg per singola assunzione il beneficio non "
            "aumenta, mentre gli effetti collaterali sì."
        )
        in_range = False

    parti.append(
        "La risposta alla caffeina varia molto da persona a persona, anche per "
        "motivi genetici."
    )

    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.STRONG,
        message=" ".join(parti),
        knowledge_tags=["caffeina", "qualita_prodotto"],
        dose_in_range=in_range,
        safety_flag=sicurezza,
    )


def _assess_protein_powder(
    d: SupplementDeclaration, profile: UserProfile, *, protein_from_food_g: float | None
) -> SupplementAssessment:
    da_integratore = (d.protein_g_per_dose or 0.0) * (d.doses_per_day or 1.0)

    parti = [
        f"Le proteine in polvere contano nel totale giornaliero come qualunque "
        f"altra fonte: {da_integratore:.0f} g dal tuo integratore."
    ]
    in_range = None

    if protein_from_food_g is not None:
        totale = protein_from_food_g + da_integratore
        per_kg = totale / profile.weight_kg if profile.weight_kg else 0.0
        parti.append(
            f"Con {protein_from_food_g:.0f} g dal cibo arrivi a {totale:.0f} g "
            f"({per_kg:.1f} g/kg)."
        )
        if per_kg > PROTEIN_G_PER_KG_POINTLESS_ABOVE:
            parti.append(
                f"È oltre i {PROTEIN_G_PER_KG_POINTLESS_ABOVE} g/kg: non è "
                "dannoso, ma a quei livelli non ci sono benefici aggiuntivi "
                "dimostrati. Potresti ridurre l'integratore senza perdere nulla."
            )
            in_range = False
        else:
            in_range = True

    parti.append(
        "Nessun bisogno di assumerle entro una finestra stretta dopo "
        "l'allenamento: conta il totale della giornata."
    )

    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.STRONG,
        message=" ".join(parti),
        knowledge_tags=["proteine", "timing_pasti", "qualita_prodotto"],
        dose_in_range=in_range,
    )


def _assess_weak_evidence(
    d: SupplementDeclaration, *, nome: str, tag: str, dettaglio: str
) -> SupplementAssessment:
    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.WEAK,
        message=(
            f"{dettaglio} Non ci sono controindicazioni note alle dosi comuni, "
            f"quindi se vuoi continuare ad assumerla non c'è motivo di allarmarsi "
            f"— ma non dovrebbe avere la priorità su proteine totali, creatina e "
            f"sonno, che hanno evidenze molto più solide."
        ),
        knowledge_tags=[tag, "qualita_prodotto"],
    )


def _assess_simple_range(
    d: SupplementDeclaration,
    *,
    tag: str,
    evidenza: str,
    minimo: float,
    massimo: float,
    unita: str,
    nota: str,
) -> SupplementAssessment:
    giornaliera = _daily_amount(d)
    if giornaliera is None:
        messaggio = f"Dose di riferimento: {minimo:g}-{massimo:g} {unita} al giorno. {nota}"
        in_range = None
    elif giornaliera < minimo:
        messaggio = (
            f"{giornaliera:g} {unita} al giorno sono sotto il range di riferimento "
            f"({minimo:g}-{massimo:g} {unita}). {nota}"
        )
        in_range = False
    elif giornaliera > massimo:
        messaggio = (
            f"{giornaliera:g} {unita} al giorno superano il range di riferimento "
            f"({minimo:g}-{massimo:g} {unita}). {nota}"
        )
        in_range = False
    else:
        messaggio = f"{giornaliera:g} {unita} al giorno: dentro il range di riferimento. {nota}"
        in_range = True

    return SupplementAssessment(
        declaration=d,
        evidence=evidenza,
        message=messaggio,
        knowledge_tags=[tag, "qualita_prodotto"],
        dose_in_range=in_range,
    )


def _assess_glutamine(d: SupplementDeclaration) -> SupplementAssessment:
    """Glutammina, valutata su tutti gli esiti e non solo sul muscolo.

    Dire "evidenza debole" senza specificare l'esito è fuorviante: è debole
    per forza e immunità, ma esiste un effetto documentato sulla permeabilità
    intestinale — a dosi però molto più alte di quelle vendute in palestra.
    """
    giornaliera = _daily_amount(d)
    parti = [
        "Per forza, massa e funzione immunitaria gli studi non mostrano effetti "
        "significativi negli adulti sani che si allenano."
    ]

    if giornaliera is not None and giornaliera < GLUTAMINE_GUT_EFFECT_G:
        parti.append(
            f"Sull'intestino invece un effetto c'è, ma compare sopra i "
            f"{GLUTAMINE_GUT_EFFECT_G:.0f} g al giorno: con i tuoi "
            f"{giornaliera:g} g sei molto sotto quella soglia, quindi stai "
            "usando una dose che per quell'esito non produce l'effetto."
        )
    else:
        parti.append(
            f"L'unico esito con qualche supporto è la riduzione dei marcatori di "
            f"permeabilità intestinale, osservata sopra i {GLUTAMINE_GUT_EFFECT_G:.0f} g "
            "al giorno e soprattutto sotto sforzo in ambiente caldo."
        )

    parti.append(
        "Nessuna controindicazione nota alle dosi comuni: se vuoi continuare non "
        "c'è motivo di allarmarsi, ma non dovrebbe avere priorità su proteine "
        "totali, creatina e sonno."
    )

    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.WEAK,
        message=" ".join(parti),
        knowledge_tags=["glutammina", "integratori_oltre_muscolo", "qualita_prodotto"],
        benefits=[
            BenefitFinding("forza e massa", EvidenceTier.WEAK,
                           "Nessun effetto significativo negli adulti sani allenati."),
            BenefitFinding("funzione immunitaria", EvidenceTier.WEAK,
                           "Le meta-analisi non rilevano effetti nell'atleta."),
            BenefitFinding("performance aerobica", EvidenceTier.WEAK,
                           "Nessun effetto."),
            BenefitFinding(
                "barriera intestinale", EvidenceTier.MODERATE,
                f"Riduzione dei marcatori di permeabilità sopra i "
                f"{GLUTAMINE_GUT_EFFECT_G:.0f} g/giorno, in modo dose-dipendente.",
            ),
        ],
    )


def _assess_ashwagandha(d: SupplementDeclaration) -> SupplementAssessment:
    """Ashwagandha: evidenze reali, ma su esiti diversi dall'ipertrofia.

    Sonno e stress non sono argomenti collaterali per chi si allena:
    `doms_and_autoregulation.md` li cita fra i fattori che determinano quanto
    volume si riesce a recuperare.
    """
    giornaliera = _daily_amount(d)
    parti = [
        "Ha evidenze discrete, ma su esiti diversi dalla massa muscolare: "
        "riduzione dello stress percepito e del cortisolo, dell'ansia e "
        "miglioramento della qualità del sonno."
    ]
    in_range = None

    if giornaliera is not None:
        if giornaliera < ASHWAGANDHA_EFFECTIVE_MG:
            parti.append(
                f"Gli effetti sul sonno sono più marcati a partire da "
                f"{ASHWAGANDHA_EFFECTIVE_MG:.0f} mg al giorno per almeno 8 "
                f"settimane: con {giornaliera:g} mg sei sotto quella soglia."
            )
            in_range = False
        else:
            parti.append(
                f"{giornaliera:g} mg al giorno rientrano nel dosaggio a cui gli "
                "effetti sono documentati, purché l'assunzione prosegua per "
                "almeno 8 settimane."
            )
            in_range = True

    parti.append(
        "Due precisazioni: non è un'alternativa a creatina o proteine per la "
        "crescita muscolare, e la sicurezza a lungo termine non è ancora ben "
        "caratterizzata. Ma dormire e recuperare meglio incide sul volume di "
        "allenamento che riesci a sostenere, quindi non è un beneficio "
        "irrilevante per i tuoi obiettivi."
    )

    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.MODERATE,
        message=" ".join(parti),
        knowledge_tags=["integratori_oltre_muscolo", "qualita_prodotto"],
        dose_in_range=in_range,
        benefits=[
            BenefitFinding("stress percepito", EvidenceTier.MODERATE,
                           "Meta-analisi su 9 RCT: riduzione della Perceived Stress Scale."),
            BenefitFinding("cortisolo", EvidenceTier.MODERATE,
                           "Riduzione significativa del cortisolo sierico."),
            BenefitFinding("sonno", EvidenceTier.MODERATE,
                           "Effetto piccolo ma significativo, maggiore a ≥600 mg per ≥8 settimane."),
            BenefitFinding("ansia", EvidenceTier.MODERATE,
                           "Riduzione sulla Hamilton Anxiety Scale."),
            BenefitFinding("VO2max", EvidenceTier.WEAK,
                           "Esiste una meta-analisi dedicata, ma meno solida delle precedenti."),
            BenefitFinding("forza e massa", EvidenceTier.WEAK,
                           "Non è l'esito per cui l'evidenza è stata raccolta."),
        ],
    )


def _assess_moringa(d: SupplementDeclaration) -> SupplementAssessment:
    """Moringa: poche evidenze umane — che non è la stessa cosa di "non funziona"."""
    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.WEAK,
        message=(
            "Gli studi sull'uomo sono pochi (circa otto) e con disegni molto "
            "diversi fra loro. Qualche segnale esiste su glicemia e su alcuni "
            "marcatori infiammatori in persone con prediabete, ma una meta-analisi "
            "non conferma effetti significativi e valuta la certezza delle prove "
            "come bassa o molto bassa. **Sul recupero dall'esercizio non ho "
            "trovato evidenze specifiche.** Attenzione alla differenza: pochi "
            "studi non significa che non funzioni, significa che non lo sappiamo. "
            "Se la assumi non c'è motivo di smettere, ma non aspettarti i benefici "
            "su energia e recupero che spesso le vengono attribuiti."
        ),
        knowledge_tags=["integratori_oltre_muscolo", "qualita_prodotto"],
        benefits=[
            BenefitFinding("glicemia", EvidenceTier.WEAK,
                           "Un RCT riporta riduzione di HbA1c; la meta-analisi non conferma (certezza bassa)."),
            BenefitFinding("infiammazione", EvidenceTier.WEAK,
                           "Riduzione di hs-CRP in un RCT, nessun effetto su TNF-α, IL-6, VES."),
            BenefitFinding("recupero dall'esercizio", EvidenceTier.UNKNOWN,
                           "Nessuna evidenza specifica reperita."),
        ],
    )


def assess(
    d: SupplementDeclaration,
    profile: UserProfile,
    *,
    protein_from_food_g: float | None = None,
    other_caffeine_mg: float = 0.0,
) -> SupplementAssessment:
    """Valuta un integratore **dichiarato dall'utente**."""
    if d.kind == SupplementKind.CREATINE:
        return _assess_creatine(d, profile)

    if d.kind == SupplementKind.CAFFEINE:
        return _assess_caffeine(d, profile, other_sources_mg=other_caffeine_mg)

    if d.kind == SupplementKind.PROTEIN_POWDER:
        return _assess_protein_powder(d, profile, protein_from_food_g=protein_from_food_g)

    if d.kind == SupplementKind.BETA_ALANINE:
        return _assess_simple_range(
            d, tag="beta_alanina", evidenza=EvidenceTier.MODERATE,
            minimo=BETA_ALANINE_G[0], massimo=BETA_ALANINE_G[1], unita="g",
            nota=(
                "Serve almeno 4 settimane continuative per aumentare la carnosina "
                "muscolare. Il beneficio è documentato soprattutto su sforzi intensi "
                "di 1-4 minuti, meno sull'ipertrofia diretta. Se avverti formicolio, "
                "è innocuo: dividi la dose nella giornata."
            ),
        )

    if d.kind == SupplementKind.HMB:
        atteso = profile.weight_kg * HMB_MG_PER_KG / 1000.0
        return _assess_simple_range(
            d, tag="hmb", evidenza=EvidenceTier.MODERATE,
            minimo=round(atteso * 0.8, 1), massimo=round(atteso * 1.2, 1), unita="g",
            nota=(
                f"Il dosaggio si calcola sul peso: {HMB_MG_PER_KG:g} mg/kg, cioè "
                f"circa {atteso:.1f} g per te. Rende di più se assunto vicino "
                "all'allenamento, e iniziato circa due settimane prima di un blocco "
                "più intenso."
            ),
        )

    if d.kind == SupplementKind.CITRULLINE:
        return SupplementAssessment(
            declaration=d,
            evidence=EvidenceTier.WEAK,
            message=(
                f"La dose più studiata è {CITRULLINE_G:g} g di citrullina malato "
                "circa 30-60 minuti prima dell'allenamento. Va detto però che i "
                "risultati sono contrastanti: alcuni studi mostrano un ritardo "
                "della fatica, altri nessun beneficio con la stessa dose. Non è "
                "un problema di sicurezza, è incertezza sull'efficacia — a "
                "differenza della creatina, qui l'esito varia."
            ),
            knowledge_tags=["citrullina", "qualita_prodotto"],
        )

    if d.kind == SupplementKind.BCAA:
        return _assess_weak_evidence(
            d, nome="BCAA", tag="bcaa",
            dettaglio=(
                "I BCAA isolati stimolano la sintesi proteica circa il 50% in meno "
                "rispetto alla stessa quantità contenuta in una proteina completa, "
                "perché mancano gli altri aminoacidi essenziali. Se il tuo totale "
                "proteico giornaliero è già coperto, sono nella grande maggioranza "
                "dei casi ridondanti."
            ),
        )

    if d.kind == SupplementKind.GLUTAMINE:
        return _assess_glutamine(d)

    if d.kind == SupplementKind.ASHWAGANDHA:
        return _assess_ashwagandha(d)

    if d.kind == SupplementKind.MORINGA:
        return _assess_moringa(d)

    if d.kind == SupplementKind.VITAMIN_D:
        giornaliera = _daily_amount(d) or 0.0
        oltre = giornaliera > VITAMIN_D_UL_MCG
        return SupplementAssessment(
            declaration=d,
            evidence=EvidenceTier.MODERATE,
            message=(
                f"Il limite superiore di sicurezza EFSA è {VITAMIN_D_UL_MCG:g} µg "
                f"al giorno (4000 UI)."
                + (
                    f" Con {giornaliera:g} µg lo stai superando: vale la pena "
                    "rivedere il dosaggio con il medico."
                    if oltre
                    else " Il tuo dosaggio rientra sotto quella soglia."
                )
            ),
            knowledge_tags=["vitamina_d", "micronutrienti", "qualita_prodotto"],
            dose_in_range=not oltre if giornaliera else None,
            safety_flag="oltre il limite superiore EFSA" if oltre else None,
        )

    if d.kind == SupplementKind.OMEGA_3:
        giornaliera = _daily_amount(d) or 0.0
        oltre = giornaliera > OMEGA3_EPA_DHA_MAX_G
        return SupplementAssessment(
            declaration=d,
            evidence=EvidenceTier.MODERATE,
            message=(
                f"EFSA non rileva problemi fino a {OMEGA3_EPA_DHA_MAX_G:g} g al "
                "giorno di EPA+DHA combinati."
                + (
                    f" Con {giornaliera:g} g sei sopra: verifica la composizione "
                    "del prodotto."
                    if oltre
                    else ""
                )
                + " Se segui una dieta vegana, l'olio algale è la fonte diretta di "
                "EPA/DHA: la conversione dall'ALA vegetale è limitata."
            ),
            knowledge_tags=["omega3", "qualita_prodotto"],
            dose_in_range=not oltre if giornaliera else None,
            safety_flag="oltre il livello sicuro EFSA" if oltre else None,
        )

    # Regola di `evidence_conduct.md` per ciò che la knowledge base non copre.
    return SupplementAssessment(
        declaration=d,
        evidence=EvidenceTier.UNKNOWN,
        message=(
            f"Non ho una fonte verificata su «{d.product_name or d.kind}» nella mia "
            "base di conoscenza, quindi non ti do un dosaggio né un giudizio di "
            "efficacia che sarebbero inventati. In generale, gli integratori non "
            "sono regolamentati come i farmaci: contenuto reale e dosaggio possono "
            "discostarsi dall'etichetta."
        ),
        knowledge_tags=["qualita_prodotto"],
    )


def assess_all(
    db: Session,
    profile: UserProfile,
    *,
    protein_from_food_g: float | None = None,
    other_caffeine_mg: float = 0.0,
) -> list[SupplementAssessment]:
    """Valuta tutti gli integratori attivi dichiarati.

    Restituisce una lista vuota se l'utente non ne ha dichiarato nessuno —
    ed è un esito normale, non qualcosa da colmare con dei suggerimenti.
    """
    dichiarati = db.scalars(
        select(SupplementDeclaration).where(
            SupplementDeclaration.profile_id == profile.id,
            SupplementDeclaration.is_active.is_(True),
        )
    ).all()

    valutazioni = []
    for d in dichiarati:
        valutazione = assess(
            d,
            profile,
            protein_from_food_g=protein_from_food_g,
            other_caffeine_mg=other_caffeine_mg,
        )
        d.agent_assessment = valutazione.message
        d.knowledge_source_tag = ",".join(valutazione.knowledge_tags)
        valutazioni.append(valutazione)

    db.commit()
    return valutazioni


def protein_from_supplements(db: Session, profile: UserProfile) -> float:
    """Proteine giornaliere provenienti dagli integratori dichiarati.

    Serve a **sommarle** al totale, non a trattarle come extra: il target è
    il totale proteico giornaliero, non l'integratore in sé.
    """
    dichiarati = db.scalars(
        select(SupplementDeclaration).where(
            SupplementDeclaration.profile_id == profile.id,
            SupplementDeclaration.is_active.is_(True),
            SupplementDeclaration.kind == SupplementKind.PROTEIN_POWDER,
        )
    ).all()

    return sum(
        (d.protein_g_per_dose or 0.0) * (d.doses_per_day or 1.0) for d in dichiarati
    )
