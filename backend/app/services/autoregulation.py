"""Autoregolazione del volume in base al feedback dell'utente.

Risponde alla situazione più comune e più fraintesa in palestra: *"non vedo
miglioramenti e i DOMS durano troppo"*. La reazione istintiva è allenarsi di
più; la risposta corretta secondo le fonti è **ridurre il volume**, perché
il muscolo cresce durante il recupero e un volume oltre la capacità di
recupero impedisce proprio l'adattamento che si sta cercando.

Parametri e regole da `knowledge_base/doms_and_autoregulation.md`, che a sua
volta si appoggia ai range di `training_volume.md`.

Come per il generatore di schede, la decisione è **deterministica**: l'LLM
può spiegarla, non prenderla.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentRecommendationLog,
    ProgressPerception,
    RecommendationType,
    RecoveryQuality,
    TrainingFeedback,
    UserProfile,
    VolumeAdjustment,
    WorkoutPlan,
    WorkoutPlanExercise,
)
from app.services.workout_generator import safety_ceiling_sets, weekly_sets_range

logger = logging.getLogger("autoregulation")

# `doms_and_autoregulation.md`: si modifica di un passo per volta, circa il
# 20-25% del volume. Cambiare troppo insieme rende impossibile capire quale
# variazione abbia prodotto l'effetto. Si usa l'estremo basso perché
# `hypertrophy_prescription.md` (IUSCA) consiglia aumenti non oltre il 20%
# del volume precedente per ciclo di circa 4 settimane.
ADJUSTMENT_RATIO = 0.20

# Oltre questa soglia il dolore non è più "indolenzimento normale" ma segnale
# di recupero insufficiente.
DOMS_EXCESSIVE_HOURS = 72

# Sotto queste settimane di allenamento è presto per concludere che il piano
# non funzioni: le variazioni di massa muscolare richiedono settimane.
MIN_WEEKS_BEFORE_JUDGING = 4

# Settimane da lasciar passare fra un aumento e il successivo, anche quando
# tutto va bene: è il ciclo di circa 4 settimane di `hypertrophy_prescription.md`
# (IUSCA). Vale soprattutto sopra il range consigliato, dove ogni aumento
# porta in territorio meno studiato.
WEEKS_BETWEEN_INCREASES = 4


@dataclass
class VolumeRecommendation:
    adjustment: str
    current_weekly_sets: int
    suggested_weekly_sets: int
    reason: str
    knowledge_tags: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def changes_volume(self) -> bool:
        return self.adjustment != VolumeAdjustment.MAINTAIN


def _is_recovery_limited(feedback: TrainingFeedback) -> bool:
    """Il recupero è il fattore limitante?

    Basta uno dei segnali: recupero dichiarato scarso, DOMS oltre le 72 ore,
    oppure dolori che compromettono le sessioni successive.
    """
    return (
        feedback.recovery_quality == RecoveryQuality.POOR
        or (feedback.doms_duration_hours or 0) > DOMS_EXCESSIVE_HOURS
        or feedback.affects_performance
    )


def _weeks_since_last_increase(db: Session, profile: UserProfile) -> int | None:
    """Da quante settimane non si aumenta il volume. `None` se non è mai successo."""
    ultimo = db.scalars(
        select(AgentRecommendationLog)
        .where(
            AgentRecommendationLog.profile_id == profile.id,
            AgentRecommendationLog.recommendation_type == RecommendationType.VOLUME_ADJUSTED,
            AgentRecommendationLog.summary.startswith(VolumeAdjustment.INCREASE),
        )
        .order_by(AgentRecommendationLog.id.desc())
        .limit(1)
    ).first()
    if ultimo is None or ultimo.created_at is None:
        return None
    creato = ultimo.created_at
    if creato.tzinfo is None:
        creato = creato.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - creato).days // 7


def _current_weekly_sets(db: Session, plan: WorkoutPlan) -> int:
    """Volume settimanale per gruppo muscolare della scheda attiva.

    Si prende il massimo fra i gruppi: è quello che determina il carico di
    recupero percepito.
    """
    righe = db.scalars(
        select(WorkoutPlanExercise).where(
            WorkoutPlanExercise.workout_plan_id == plan.id
        )
    ).all()

    per_muscolo: dict[str, int] = {}
    for riga in righe:
        muscolo = riga.exercise.primary_muscle or "?"
        per_muscolo[muscolo] = per_muscolo.get(muscolo, 0) + riga.target_sets

    return max(per_muscolo.values(), default=0)


def evaluate_feedback(
    db: Session,
    profile: UserProfile,
    feedback: TrainingFeedback,
    *,
    plan: WorkoutPlan | None = None,
) -> VolumeRecommendation:
    """Applica la matrice decisionale di `doms_and_autoregulation.md`."""
    minimo, _, massimo = weekly_sets_range(profile)

    corrente = _current_weekly_sets(db, plan) if plan is not None else 0
    if corrente <= 0:
        corrente = minimo

    recupero_limitante = _is_recovery_limited(feedback)
    nessun_progresso = feedback.progress_perception == ProgressPerception.NONE
    tags = ["doms", "autoregolazione", "volume_allenamento"]
    caveats: list[str] = []

    # Quanto dura la scheda attuale: sotto le 4-6 settimane è presto per
    # trarre conclusioni sui progressi.
    if plan is not None and plan.started_at:
        settimane = (dt.date.today() - plan.started_at).days // 7
        if settimane < MIN_WEEKS_BEFORE_JUDGING:
            caveats.append(
                f"Segui questa scheda da circa {settimane} settimane: le variazioni "
                f"di massa muscolare richiedono più tempo, quindi valuta i "
                f"progressi con prudenza prima di cambiare troppo."
            )

    if nessun_progresso and recupero_limitante:
        suggerito = max(minimo, round(corrente * (1 - ADJUSTMENT_RATIO)))
        reason = (
            "I dolori post-allenamento durano a lungo e influiscono sulle sessioni "
            "successive, e nel frattempo non vedi progressi: è il quadro tipico in "
            "cui il fattore limitante è il recupero, non lo stimolo. Il muscolo "
            "cresce mentre recuperi, quindi un volume superiore alla tua capacità "
            "di recupero impedisce proprio l'adattamento che stai cercando. "
            f"Riduco da {corrente} a {suggerito} serie settimanali per gruppo "
            "muscolare: non ti stai allenando di meno, stai dando al muscolo la "
            "possibilità di ricostruirsi."
        )
        adjustment = (
            VolumeAdjustment.DECREASE if suggerito < corrente else VolumeAdjustment.MAINTAIN
        )
        if suggerito >= corrente:
            reason += (
                " Sei già al minimo del range previsto per il tuo livello: se il "
                "problema persiste, guarda sonno, apporto calorico e proteico "
                "prima del volume."
            )
            caveats.append(
                "Volume già al minimo: verifica apporto proteico, calorie e sonno."
            )

    elif nessun_progresso and not recupero_limitante:
        # Oltre il massimo del range si può andare, ma una serie alla volta e
        # solo con il recupero in ordine: vedi `training_dose_response.md`.
        tetto = safety_ceiling_sets(profile)
        oltre_il_range = corrente >= massimo
        settimane_dall_aumento = _weeks_since_last_increase(db, profile)
        troppo_presto = (
            settimane_dall_aumento is not None
            and settimane_dall_aumento < WEEKS_BETWEEN_INCREASES
        )
        # Per difetto e non arrotondato: l'aumento non deve superare il limite
        # IUSCA del 20%. Almeno una serie in più, altrimenti sotto le 5 serie
        # l'arrotondamento non aumenterebbe mai.
        suggerito = min(tetto, max(corrente + 1, int(corrente * (1 + ADJUSTMENT_RATIO))))
        if troppo_presto:
            suggerito = corrente
        adjustment = (
            VolumeAdjustment.INCREASE if suggerito > corrente else VolumeAdjustment.MAINTAIN
        )
        reason = (
            "Non vedi progressi ma recuperi bene e i dolori si esauriscono in "
            f"tempi normali: c'è margine per aumentare lo stimolo. Passo da "
            f"{corrente} a {suggerito} serie settimanali per gruppo muscolare."
        )
        if suggerito > corrente and oltre_il_range:
            tags.append("dose_risposta")
            reason += (
                f" Superi il massimo consigliato per il tuo livello ({massimo} serie): "
                "le fonti non indicano un punto oltre il quale i guadagni si fermano, "
                "ma il rendimento per serie aggiunta cala e sopra le 24 serie non "
                "esistono studi che mostrino un vantaggio. Si sale un passo alla "
                "volta, e se il recupero peggiora si torna indietro."
            )
            caveats.append(
                "Sei oltre il range consigliato: tieni d'occhio sonno, dolori e "
                "qualità delle sessioni, e riduci se peggiorano."
            )
        elif troppo_presto:
            reason = (
                "Recuperi bene, ma hai aumentato il volume da meno di "
                f"{WEEKS_BETWEEN_INCREASES} settimane: le fonti indicano di lasciar "
                "passare circa un mese fra un aumento e il successivo, altrimenti non "
                "si capisce quale variazione abbia prodotto l'effetto. Mantengo "
                f"{corrente} serie settimanali per ora."
            )
            caveats.append(
                "Ultimo aumento troppo recente: dai tempo al volume attuale di "
                "mostrare i suoi effetti."
            )
        elif suggerito <= corrente:
            reason = (
                f"Non vedi progressi e recuperi bene, ma sei già a {corrente} serie "
                "settimanali, il limite oltre il quale nessuno studio controllato "
                "mostra un vantaggio. Aggiungere serie qui è una scommessa: conviene "
                "prima verificare apporto calorico e proteico, sonno e la reale "
                "vicinanza al cedimento delle serie."
            )
            caveats.append(
                "Volume al limite di sicurezza: valuta alimentazione, sonno e "
                "intensità effettiva prima di aggiungere serie."
            )
            tags.append("cedimento")

    elif recupero_limitante:
        # Progressi presenti ma recupero al limite: si mantiene, al più si
        # riduce leggermente. Il margine si sta esaurendo.
        suggerito = corrente
        adjustment = VolumeAdjustment.MAINTAIN
        reason = (
            "Stai facendo progressi, ma il recupero è al limite. Mantengo il "
            "volume invariato: aumentarlo ora rischia di spostare il collo di "
            "bottiglia sul recupero e annullare i risultati che stai ottenendo."
        )

    else:
        suggerito = corrente
        adjustment = VolumeAdjustment.MAINTAIN
        reason = (
            "Progressi presenti e recupero buono: il volume attuale sta "
            "funzionando, non c'è motivo di cambiarlo."
        )

    # Promemoria trasversale: il volume non è mai l'unica variabile.
    if nessun_progresso:
        caveats.append(
            "«Nessun progresso» può dipendere anche da calorie e proteine "
            "insufficienti o da sonno scarso, non solo dal volume."
        )
        tags.append("proteine")

    return VolumeRecommendation(
        adjustment=adjustment,
        current_weekly_sets=corrente,
        suggested_weekly_sets=suggerito,
        reason=reason,
        knowledge_tags=tags,
        caveats=caveats,
    )


def apply_volume_change(
    db: Session, plan: WorkoutPlan, recommendation: VolumeRecommendation
) -> int:
    """Riscala le serie della scheda attiva secondo la raccomandazione.

    Restituisce il numero di righe modificate. Le serie non scendono mai
    sotto 1: un esercizio con zero serie andrebbe rimosso, non azzerato.
    """
    if not recommendation.changes_volume or recommendation.current_weekly_sets <= 0:
        return 0

    fattore = recommendation.suggested_weekly_sets / recommendation.current_weekly_sets
    modificate = 0

    for riga in db.scalars(
        select(WorkoutPlanExercise).where(
            WorkoutPlanExercise.workout_plan_id == plan.id
        )
    ):
        nuove = max(1, round(riga.target_sets * fattore))
        if nuove != riga.target_sets:
            riga.target_sets = nuove
            modificate += 1

    db.commit()
    return modificate


def record_recommendation(
    db: Session,
    profile: UserProfile,
    recommendation: VolumeRecommendation,
    *,
    plan: WorkoutPlan | None = None,
    used_llm: bool = False,
) -> AgentRecommendationLog:
    """Traccia la decisione, con le fonti che l'hanno prodotta."""
    log = AgentRecommendationLog(
        profile_id=profile.id,
        recommendation_type=RecommendationType.VOLUME_ADJUSTED,
        reference_id=plan.id if plan is not None else None,
        summary=(
            f"{recommendation.adjustment}: da {recommendation.current_weekly_sets} "
            f"a {recommendation.suggested_weekly_sets} serie/settimana. "
            f"{recommendation.reason}"
        ),
        knowledge_source_tags=",".join(recommendation.knowledge_tags),
        used_llm=used_llm,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
