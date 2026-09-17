"""Note di Kilo: indicazioni che l'agente dà di sua iniziativa, sezione per sezione.

Sono **regole scritte sulle fonti**, non testo generato: ogni nota nasce da
una soglia presente in un documento della knowledge base e ne cita il tag.
Così sono istantanee, non consumano la quota dell'LLM e non inventano nulla.
L'LLM interviene solo se l'utente chiede di approfondire (apre la chat con
la domanda della nota).

Tre regole di comportamento:
  - **mai proporre integratori**: le note riguardano solo quelli dichiarati;
  - **una nota vista e chiusa non torna**. Le note legate a un evento (28
    giorni di creatina) hanno una chiave fissa; quelle legate a una
    situazione che si ripete (giorni saltati, stallo) includono la settimana
    nella chiave, così possono ripresentarsi al massimo una volta a settimana;
  - **dove la fonte tace, la nota lo dice** invece di completare a memoria.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentNoteDismissal,
    Goal,
    SupplementDeclaration,
    SupplementKind,
    TrainingFeedback,
    UserProfile,
    WorkoutPlan,
)
from app.services import food_diary, nutrition_targets, progress_report, supplement_intake

# `creatine.md`: senza carico le scorte salgono in 3-4 settimane; con il
# carico (~0,3 g/kg, circa 20 g in 4 dosi) in 5-7 giorni.
CREATINE_SATURATION_DAYS = 28
CREATINE_LOADING_DAILY_G = 15.0
CREATINE_LOADING_DAYS = 7
# Giorni saltati (nelle ultime 4 settimane) oltre i quali la nota rassicura.
CREATINE_MISSED_DAYS = 3
# `beta_alanine.md`: almeno 4 settimane per aumentare la carnosina.
BETA_ALANINE_DAYS = 28
# `supplements_beyond_muscle.md`: effetti sul sonno con ≥8 settimane.
ASHWAGANDHA_DAYS = 56

# `doms_and_autoregulation.md`: i progressi si valutano su 4-6 settimane;
# `hypertrophy_prescription.md`: il volume si ritocca per cicli di ~4 settimane.
PLAN_REVIEW_DAYS = 28

# `diets_body_composition.md`: nei soggetti magri un calo dello 0,7% del peso
# a settimana ha preservato la massa magra meglio dell'1,4%; per chi è in
# preparazione è suggerito 0,5-1,0%.
FAT_LOSS_MAX_WEEKLY_PCT = 1.0
MIN_WEIGHT_DAYS = 28
# Sotto questo calo le medie mobili non distinguono una tendenza dal rumore.
MASS_GAIN_WEIGHT_DROP_KG = 0.5

# `protein_intake.md`: target proteico giornaliero. La nota compare solo con
# abbastanza giorni registrati da fare una media.
PROTEIN_MIN_LOGGED_DAYS = 3
PROTEIN_COVERAGE_WARNING = 0.8


@dataclass
class AgentNote:
    key: str
    section: str  # id della sezione nel frontend
    tone: str  # "success" | "info" | "attention"
    title: str
    text: str
    knowledge_tags: list[str]
    question: str  # cosa chiedere alla chat con "Approfondisci"
    priority: int = 50
    action: str | None = None  # azione dedicata nella sezione (es. "feedback")


def _week(today: dt.date) -> str:
    anno, settimana, _ = today.isocalendar()
    return f"{anno}w{settimana}"


# --- Integratori ------------------------------------------------------------------


def _daily_grams(d: SupplementDeclaration) -> float | None:
    if d.dose_amount is None or (d.dose_unit or "g") != "g":
        return None
    return d.dose_amount * (d.doses_per_day or 1.0)


def _supplement_notes(db: Session, profile: UserProfile, today: dt.date) -> list[AgentNote]:
    note: list[AgentNote] = []
    for d in supplement_intake.active_declarations(db, profile):
        r = supplement_intake.summarize(db, d, today=today)

        if d.kind == SupplementKind.CREATINE:
            giornaliera = _daily_grams(d)
            in_carico = giornaliera is not None and giornaliera >= CREATINE_LOADING_DAILY_G
            if in_carico and r.days_taken >= CREATINE_LOADING_DAYS:
                note.append(AgentNote(
                    key=f"creatina-carico-finito:{d.id}",
                    section="integratori",
                    tone="attention",
                    title="Fase di carico completata",
                    text=(
                        f"Hai segnato {r.days_taken} giorni a {giornaliera:g} g: il carico "
                        "satura le scorte in 5-7 giorni, oltre non aggiunge nulla. Da qui "
                        "basta il mantenimento, 3-5 g al giorno. Puoi aggiornare la dose "
                        "in «I tuoi»."
                    ),
                    knowledge_tags=["creatina"],
                    question="Ho finito la fase di carico della creatina: come passo al mantenimento?",
                    priority=80,
                ))
            elif not in_carico and r.days_taken >= CREATINE_SATURATION_DAYS:
                note.append(AgentNote(
                    key=f"creatina-scorte-piene:{d.id}",
                    section="integratori",
                    tone="success",
                    title="Creatina: scorte piene",
                    text=(
                        f"{r.days_taken} giorni di assunzione: senza fase di carico le "
                        "scorte muscolari si riempiono in 3-4 settimane, quindi ci sei. "
                        "Da qui è mantenimento, 3-5 g al giorno. Non serve fare pause o "
                        "cicli, e la fonte non indica un limite di durata: riporta "
                        "sicurezza nelle persone sane fino a 5 anni di studi."
                    ),
                    knowledge_tags=["creatina"],
                    question=(
                        "Ho superato i 28 giorni di creatina: devo fare pause? "
                        "Per quanto tempo posso continuare?"
                    ),
                    priority=60,
                ))

            if r.days_taken >= CREATINE_LOADING_DAYS and r.missed_days >= CREATINE_MISSED_DAYS:
                note.append(AgentNote(
                    key=f"creatina-giorni-saltati:{d.id}:{_week(today)}",
                    section="integratori",
                    tone="info",
                    title=f"{r.missed_days} giorni saltati nelle ultime 4 settimane",
                    text=(
                        "Qualche giorno saltato non azzera il lavoro fatto: anche "
                        "sospendendo del tutto, le scorte tornano al livello di partenza "
                        "in 4-6 settimane, non in pochi giorni."
                    ),
                    knowledge_tags=["creatina"],
                    question="Ho saltato qualche giorno di creatina: cosa succede alle scorte?",
                    priority=40,
                ))

        elif d.kind == SupplementKind.BETA_ALANINE and r.days_taken >= BETA_ALANINE_DAYS:
            note.append(AgentNote(
                key=f"beta-alanina-4-settimane:{d.id}",
                section="integratori",
                tone="success",
                title="Beta-alanina: 4 settimane raggiunte",
                text=(
                    "È la durata minima con cui le fonti osservano l'aumento di "
                    "carnosina nel muscolo. Su quanto proseguire o se fare pause, la "
                    "mia fonte non dà indicazioni: non te ne invento."
                ),
                knowledge_tags=["beta_alanina"],
                question="Ho fatto 4 settimane di beta-alanina: cosa dicono le fonti su come proseguire?",
                priority=55,
            ))

        elif d.kind == SupplementKind.ASHWAGANDHA and r.days_taken >= ASHWAGANDHA_DAYS:
            note.append(AgentNote(
                key=f"ashwagandha-8-settimane:{d.id}",
                section="integratori",
                tone="info",
                title="Ashwagandha: 8 settimane raggiunte",
                text=(
                    "Gli effetti sul sonno sono documentati soprattutto da qui in poi. "
                    "Da sapere se pensi di continuare a lungo: la sicurezza a lungo "
                    "termine non è ancora ben caratterizzata."
                ),
                knowledge_tags=["integratori_oltre_muscolo"],
                question="Assumo ashwagandha da 8 settimane: cosa sappiamo sull'uso a lungo termine?",
                priority=55,
            ))
    return note


# --- Scheda -------------------------------------------------------------------------


def _plan_notes(
    db: Session, profile: UserProfile, today: dt.date, report: progress_report.ProgressReport
) -> list[AgentNote]:
    note: list[AgentNote] = []
    piano = db.scalar(
        select(WorkoutPlan)
        .where(WorkoutPlan.profile_id == profile.id, WorkoutPlan.is_active.is_(True))
        .order_by(WorkoutPlan.started_at.desc(), WorkoutPlan.id.desc())
        .limit(1)
    )
    if piano is None:
        return note

    giorni = (today - piano.started_at).days
    if giorni >= PLAN_REVIEW_DAYS:
        feedback_recente = db.scalar(
            select(TrainingFeedback.id).where(
                TrainingFeedback.workout_plan_id == piano.id,
                TrainingFeedback.date >= today - dt.timedelta(days=PLAN_REVIEW_DAYS),
            ).limit(1)
        )
        if feedback_recente is None:
            note.append(AgentNote(
                key=f"scheda-fai-il-punto:{piano.id}:{giorni // PLAN_REVIEW_DAYS}",
                section="scheda",
                tone="info",
                title=f"{giorni // 7} settimane con questa scheda: facciamo il punto",
                text=(
                    "È l'orizzonte giusto per valutare: prima di 4-6 settimane si "
                    "rischiano conclusioni premature. Dimmi come vanno progressi e "
                    "recupero e ti dico se mantenere, aumentare o ridurre il volume, "
                    "cambiandolo al massimo del 20-25% per volta."
                ),
                knowledge_tags=["autoregolazione", "ipertrofia"],
                question=(
                    f"Uso la scheda «{piano.name}» da {giorni // 7} settimane: come capisco "
                    "se sta funzionando e se devo cambiare il volume?"
                ),
                priority=60,
                action="feedback",
            ))

    fermi = report.plateaued
    if fermi:
        nomi = ", ".join(e.exercise_name for e in fermi[:3])
        note.append(AgentNote(
            key=f"stallo-carichi:{_week(today)}",
            section="scheda",
            tone="attention",
            title="Carichi fermi da qualche seduta",
            text=(
                f"Su {nomi} il massimale stimato non sale nelle ultime sedute. Prima "
                "di toccare il volume vale la pena escludere le altre cause: calorie e "
                "proteine sufficienti, sonno e stress. Se sono a posto, il feedback su "
                "progressi e recupero dice se aumentare o ridurre."
            ),
            knowledge_tags=["autoregolazione", "proteine"],
            question=f"I carichi su {nomi} sono fermi: cosa controllo prima di cambiare la scheda?",
            priority=70,
            action="feedback",
        ))
    return note


# --- Progressi e alimentazione ------------------------------------------------------


def _weight_notes(
    profile: UserProfile, today: dt.date, report: progress_report.ProgressReport
) -> list[AgentNote]:
    peso = report.weight
    if not peso.smoothed or peso.days_covered < MIN_WEIGHT_DAYS or peso.weekly_rate_kg is None:
        return []

    note: list[AgentNote] = []
    percentuale = abs(peso.weekly_rate_kg) / profile.weight_kg * 100 if profile.weight_kg else 0.0

    if profile.goal == Goal.FAT_LOSS and peso.weekly_rate_kg < 0 and percentuale > FAT_LOSS_MAX_WEEKLY_PCT:
        note.append(AgentNote(
            key=f"calo-troppo-rapido:{_week(today)}",
            section="progressi",
            tone="attention",
            title=f"Stai scendendo di circa l'{percentuale:.1f}% a settimana",
            text=(
                "È un ritmo veloce. Negli studi, chi è già abbastanza magro ha "
                "conservato più massa muscolare calando dello 0,7% a settimana che "
                "dell'1,4%; per chi è in preparazione le fonti indicano 0,5-1%."
            ),
            knowledge_tags=["composizione_corporea"],
            question="Sto perdendo peso velocemente: rischio di perdere muscolo? Come regolo il deficit?",
            priority=70,
        ))

    if (
        profile.goal == Goal.HYPERTROPHY
        and peso.delta_kg is not None
        and peso.delta_kg <= -MASS_GAIN_WEIGHT_DROP_KG
    ):
        note.append(AgentNote(
            key=f"massa-peso-in-calo:{_week(today)}",
            section="progressi",
            tone="attention",
            title="Obiettivo massa, ma il peso scende",
            text=(
                f"Le medie delle pesate sono calate di {abs(peso.delta_kg):.1f} kg. "
                "Senza un surplus calorico il muscolo ha meno materiale per crescere: "
                "controlla nel diario se stai raggiungendo le calorie previste."
            ),
            knowledge_tags=["doms", "surplus_calorico"],
            question="Voglio mettere massa ma il peso scende: cosa sto sbagliando?",
            priority=65,
        ))
    return note


def _nutrition_notes(db: Session, profile: UserProfile, today: dt.date) -> list[AgentNote]:
    try:
        target = nutrition_targets.compute_targets(
            profile, training_days=profile.training_days_per_week
        ).protein_g
    except ValueError:
        return []

    giorni = []
    for n in range(1, 8):
        totali = food_diary.daily_totals(db, profile, date=today - dt.timedelta(days=n))
        if totali.kcal > 0:
            giorni.append(totali.protein_g)
    if len(giorni) < PROTEIN_MIN_LOGGED_DAYS or not target:
        return []

    copertura = sum(giorni) / len(giorni) / target
    if copertura >= PROTEIN_COVERAGE_WARNING:
        return []
    return [AgentNote(
        key=f"proteine-sotto-target:{_week(today)}",
        section="diario",
        tone="attention",
        title=f"Proteine al {copertura:.0%} del target in media",
        text=(
            f"Nei {len(giorni)} giorni registrati dell'ultima settimana hai assunto in "
            f"media {sum(giorni) / len(giorni):.0f} g di proteine su {target:.0f} g. "
            "Il target conta sul totale della giornata: «Cosa mi manca oggi» calcola "
            "alimenti e grammi per chiuderlo."
        ),
        knowledge_tags=["proteine"],
        question="Non riesco ad arrivare al target di proteine: come le distribuisco nei pasti?",
        priority=60,
    )]


# --- Raccolta -----------------------------------------------------------------------


def build(db: Session, profile: UserProfile, *, today: dt.date) -> list[AgentNote]:
    """Tutte le note attive, dalla più importante, senza quelle già chiuse."""
    report = progress_report.build_report(db, profile, until=today)
    note = [
        *_supplement_notes(db, profile, today),
        *_plan_notes(db, profile, today, report),
        *_weight_notes(profile, today, report),
        *_nutrition_notes(db, profile, today),
    ]
    chiuse = set(
        db.scalars(
            select(AgentNoteDismissal.note_key).where(AgentNoteDismissal.profile_id == profile.id)
        )
    )
    return sorted(
        (n for n in note if n.key not in chiuse), key=lambda n: -n.priority
    )


def dismiss(db: Session, profile: UserProfile, key: str) -> None:
    esiste = db.scalar(
        select(AgentNoteDismissal.id).where(
            AgentNoteDismissal.profile_id == profile.id,
            AgentNoteDismissal.note_key == key,
        )
    )
    if esiste is None:
        db.add(AgentNoteDismissal(profile_id=profile.id, note_key=key))
        db.commit()
