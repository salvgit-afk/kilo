"""Report di progressione: carichi, peso corporeo, aderenza, plateau.

Tre scelte metodologiche che cambiano la qualità di ciò che l'utente legge:

  1. **Il peso corporeo si confronta a medie mobili, non a pesate singole.**
     Il peso oscilla di 1-2 kg nella stessa giornata per acqua, glicogeno e
     contenuto intestinale. Confrontare la prima con l'ultima pesata misura
     soprattutto quel rumore: con medie su 7 giorni il segnale emerge.

  2. **La forza si misura sul massimale stimato, non sul carico grezzo.**
     Passare da 60 kg x 8 a 65 kg x 5 sembra un progresso, ma il massimale
     stimato scende. La formula di Epley (`calorie_and_1rm_formulas.md`)
     rende confrontabili serie con ripetizioni diverse.

  3. **Sotto le 4 settimane il report lo dichiara.** Le variazioni di massa
     muscolare richiedono settimane: dare un verdetto su 10 giorni produce
     conclusioni premature, ed è la stessa cautela già applicata
     nell'autoregolazione del volume.

Nessun dato di questo modulo dipende da API esterne: si basa solo su ciò che
l'utente registra, quindi resta valido anche se wger o USDA cambiano.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    SessionSet,
    UserProfile,
    WeightLog,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
)

logger = logging.getLogger("progress_report")

# Finestra della media mobile sul peso: una settimana copre le oscillazioni
# legate ad alimentazione e allenamenti infrasettimanali.
WEIGHT_SMOOTHING_DAYS = 7

# Sotto questa durata il report avvisa che è presto per trarre conclusioni.
MIN_WEEKS_FOR_CONCLUSIONS = 4

# Sessioni consecutive senza progressi su un esercizio prima di parlare di
# stallo. Con meno si scambierebbe una brutta giornata per un plateau.
PLATEAU_SESSIONS = 3

# Variazione sotto la quale si considera che il massimale stimato non sia
# cambiato: sotto il 2% è dentro la normale variabilità giornaliera.
PLATEAU_TOLERANCE = 0.02


def estimate_1rm(weight_kg: float, reps: int) -> float:
    """Massimale stimato con la formula di Epley.

    Attendibile soprattutto entro le ~10-12 ripetizioni: oltre, la stima
    perde precisione (vedi `calorie_and_1rm_formulas.md`).
    """
    return weight_kg * (1 + reps / 30)


@dataclass
class ExerciseProgress:
    exercise_name: str
    first_date: dt.date
    last_date: dt.date
    first_best_1rm: float
    last_best_1rm: float
    first_best_set: str      # es. "60 kg x 8"
    last_best_set: str
    sessions: int
    high_rep_estimate: bool  # stima meno precisa (serie sopra le 12 ripetizioni)

    @property
    def delta_kg(self) -> float:
        return self.last_best_1rm - self.first_best_1rm

    @property
    def delta_pct(self) -> float:
        if not self.first_best_1rm:
            return 0.0
        return self.delta_kg / self.first_best_1rm

    @property
    def is_plateau(self) -> bool:
        return abs(self.delta_pct) < PLATEAU_TOLERANCE


@dataclass
class WeightTrend:
    first_average: float | None
    last_average: float | None
    measurements: int
    days_covered: int
    smoothed: bool  # False = troppo poche pesate per una media affidabile

    @property
    def delta_kg(self) -> float | None:
        if self.first_average is None or self.last_average is None:
            return None
        return self.last_average - self.first_average

    @property
    def weekly_rate_kg(self) -> float | None:
        """Variazione settimanale: è il dato che dice se il ritmo è sensato."""
        delta = self.delta_kg
        if delta is None or self.days_covered < 7:
            return None
        return delta / (self.days_covered / 7)


@dataclass
class AdherenceStats:
    sessions_done: int
    weeks: float
    planned_per_week: int | None

    @property
    def actual_per_week(self) -> float:
        return self.sessions_done / self.weeks if self.weeks else 0.0

    @property
    def ratio(self) -> float | None:
        if not self.planned_per_week:
            return None
        return self.actual_per_week / self.planned_per_week


@dataclass
class ProgressReport:
    profile_name: str
    period_start: dt.date
    period_end: dt.date
    exercises: list[ExerciseProgress]
    weight: WeightTrend
    adherence: AdherenceStats
    notes: list[str] = field(default_factory=list)
    knowledge_tags: list[str] = field(default_factory=list)

    @property
    def weeks(self) -> float:
        return max((self.period_end - self.period_start).days / 7, 0.0)

    @property
    def too_early(self) -> bool:
        return self.weeks < MIN_WEEKS_FOR_CONCLUSIONS

    @property
    def improved(self) -> list[ExerciseProgress]:
        return [e for e in self.exercises if e.delta_pct >= PLATEAU_TOLERANCE]

    @property
    def plateaued(self) -> list[ExerciseProgress]:
        return [e for e in self.exercises if e.is_plateau]

    @property
    def regressed(self) -> list[ExerciseProgress]:
        return [e for e in self.exercises if e.delta_pct <= -PLATEAU_TOLERANCE]


def _moving_average(
    logs: list[WeightLog], *, window_days: int = WEIGHT_SMOOTHING_DAYS
) -> tuple[float | None, float | None, bool]:
    """Media delle pesate nella prima e nell'ultima finestra del periodo.

    Restituisce anche se la media è affidabile: con una sola pesata per
    estremo il valore resta esposto all'oscillazione giornaliera, e va detto
    invece di presentarlo come una tendenza.
    """
    if not logs:
        return None, None, False

    ordinati = sorted(logs, key=lambda l: l.date)
    inizio, fine = ordinati[0].date, ordinati[-1].date

    prima_finestra = [
        l.weight_kg for l in ordinati if (l.date - inizio).days < window_days
    ]
    ultima_finestra = [
        l.weight_kg for l in ordinati if (fine - l.date).days < window_days
    ]

    if not prima_finestra or not ultima_finestra:
        return None, None, False

    affidabile = len(prima_finestra) >= 2 and len(ultima_finestra) >= 2
    return (
        sum(prima_finestra) / len(prima_finestra),
        sum(ultima_finestra) / len(ultima_finestra),
        affidabile,
    )


def _best_set_of_session(sets: list[SessionSet]) -> SessionSet | None:
    """Serie migliore di una sessione, per massimale stimato.

    Non si prende il carico più alto: 65 kg x 3 può valere meno di 60 kg x 8,
    e il confronto fra sessioni deve usare la stessa unità di misura.
    """
    if not sets:
        return None
    return max(sets, key=lambda s: estimate_1rm(s.weight_kg, s.reps))


def _exercise_progress(
    sets_by_exercise: dict[str, list[tuple[dt.date, SessionSet]]]
) -> list[ExerciseProgress]:
    progressi: list[ExerciseProgress] = []

    for nome, voci in sets_by_exercise.items():
        per_data: dict[dt.date, list[SessionSet]] = {}
        for data, s in voci:
            per_data.setdefault(data, []).append(s)

        date_ordinate = sorted(per_data)
        # Serve almeno un confronto fra due sessioni distinte.
        if len(date_ordinate) < 2:
            continue

        prima_data, ultima_data = date_ordinate[0], date_ordinate[-1]
        prima = _best_set_of_session(per_data[prima_data])
        ultima = _best_set_of_session(per_data[ultima_data])
        if prima is None or ultima is None:
            continue

        progressi.append(
            ExerciseProgress(
                exercise_name=nome,
                first_date=prima_data,
                last_date=ultima_data,
                first_best_1rm=estimate_1rm(prima.weight_kg, prima.reps),
                last_best_1rm=estimate_1rm(ultima.weight_kg, ultima.reps),
                first_best_set=f"{prima.weight_kg:g} kg x {prima.reps}",
                last_best_set=f"{ultima.weight_kg:g} kg x {ultima.reps}",
                sessions=len(date_ordinate),
                high_rep_estimate=max(prima.reps, ultima.reps) > 12,
            )
        )

    progressi.sort(key=lambda p: p.delta_pct, reverse=True)
    return progressi


def build_report(
    db: Session,
    profile: UserProfile,
    *,
    since: dt.date | None = None,
    until: dt.date | None = None,
) -> ProgressReport:
    """Costruisce il report del periodo indicato (default: ultime 12 settimane)."""
    until = until or dt.date.today()
    since = since or (until - dt.timedelta(weeks=12))

    sessioni = db.scalars(
        select(WorkoutSession).where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.date >= since,
            WorkoutSession.date <= until,
        )
    ).all()

    per_esercizio: dict[str, list[tuple[dt.date, SessionSet]]] = {}
    for sessione in sessioni:
        for s in sessione.sets:
            nome = s.exercise.name if s.exercise else "?"
            per_esercizio.setdefault(nome, []).append((sessione.date, s))

    pesate = db.scalars(
        select(WeightLog).where(
            WeightLog.profile_id == profile.id,
            WeightLog.date >= since,
            WeightLog.date <= until,
        )
    ).all()

    prima_media, ultima_media, affidabile = _moving_average(pesate)
    giorni_coperti = (
        (max(p.date for p in pesate) - min(p.date for p in pesate)).days if pesate else 0
    )

    piano_attivo = db.scalar(
        select(WorkoutPlan)
        .where(WorkoutPlan.profile_id == profile.id, WorkoutPlan.is_active.is_(True))
        .order_by(WorkoutPlan.started_at.desc(), WorkoutPlan.id.desc())
        .limit(1)
    )

    settimane = max((until - since).days / 7, 1e-9)
    report = ProgressReport(
        profile_name=profile.display_name,
        period_start=since,
        period_end=until,
        exercises=_exercise_progress(per_esercizio),
        weight=WeightTrend(
            first_average=prima_media,
            last_average=ultima_media,
            measurements=len(pesate),
            days_covered=giorni_coperti,
            smoothed=affidabile,
        ),
        adherence=AdherenceStats(
            sessions_done=len(sessioni),
            weeks=settimane,
            planned_per_week=piano_attivo.days_per_week if piano_attivo else None,
        ),
        knowledge_tags=["1rm", "autoregolazione"],
    )

    report.notes = _build_notes(report, profile)
    return report


def _build_notes(report: ProgressReport, profile: UserProfile) -> list[str]:
    """Avvertenze metodologiche: servono a non far leggere come segnale ciò
    che è rumore."""
    note: list[str] = []

    if report.too_early:
        note.append(
            f"Il periodo analizzato è di {report.weeks:.0f} settimane. Le "
            "variazioni di massa muscolare richiedono più tempo: leggi questi "
            "numeri come una fotografia, non come un verdetto sul programma."
        )

    peso = report.weight
    if peso.measurements == 0:
        note.append(
            "Nessuna pesata registrata nel periodo: senza quel dato non posso "
            "dirti se il peso sta andando nella direzione del tuo obiettivo."
        )
    elif not peso.smoothed:
        note.append(
            f"Solo {peso.measurements} pesate nel periodo. Il peso oscilla di "
            "1-2 kg al giorno per acqua e glicogeno, quindi con poche misurazioni "
            "la differenza che vedi può essere rumore. Pesarsi 3-4 volte a "
            "settimana rende la tendenza leggibile."
        )

    if any(e.high_rep_estimate for e in report.exercises):
        note.append(
            "Su alcuni esercizi il massimale è stimato da serie sopra le 12 "
            "ripetizioni: in quel range la formula perde precisione, quindi la "
            "variazione va presa con più margine."
        )

    aderenza = report.adherence
    if aderenza.ratio is not None and aderenza.ratio < 0.7:
        note.append(
            f"Hai svolto in media {aderenza.actual_per_week:.1f} sessioni a "
            f"settimana contro le {aderenza.planned_per_week} previste. Prima di "
            "cambiare la scheda, considera che il volume effettivo è stato "
            "inferiore a quello programmato."
        )

    if report.plateaued and not report.too_early:
        nomi = ", ".join(e.exercise_name for e in report.plateaued[:3])
        note.append(
            f"Fermi da tempo su: {nomi}. Se il recupero è buono si può alzare il "
            "volume; se invece i dolori durano a lungo e le sessioni ne "
            "risentono, la risposta corretta è ridurlo."
        )

    return note


def explain_plateau(db: Session, profile: UserProfile, report: ProgressReport) -> str | None:
    """Traduce uno stallo in un'indicazione concreta, usando il feedback recente.

    Il report da solo può dire *che* sei fermo, ma non *cosa fare*: la stessa
    situazione richiede di aumentare il volume se recuperi bene e di ridurlo
    se i dolori durano a lungo (`doms_and_autoregulation.md`). Senza il
    feedback dell'utente le due direzioni restano entrambe aperte, e
    l'onestà è dirlo invece di indovinare.
    """
    from app.models import TrainingFeedback
    from app.services import autoregulation

    if not report.plateaued or report.too_early:
        return None

    nomi = ", ".join(e.exercise_name for e in report.plateaued[:3])

    recente = db.scalar(
        select(TrainingFeedback)
        .where(TrainingFeedback.profile_id == profile.id)
        .order_by(TrainingFeedback.date.desc())
    )
    if recente is None:
        return (
            f"Sei fermo su {nomi}. Per capire da che parte intervenire mi serve "
            "sapere come stai recuperando: se i dolori post-allenamento passano "
            "in fretta c'è margine per aumentare il volume, se invece durano a "
            "lungo e ti rovinano le sessioni successive va ridotto. Registra un "
            "feedback e te lo dico con precisione."
        )

    piano = db.scalar(
        select(WorkoutPlan)
        .where(WorkoutPlan.profile_id == profile.id, WorkoutPlan.is_active.is_(True))
        .order_by(WorkoutPlan.started_at.desc(), WorkoutPlan.id.desc())
        .limit(1)
    )
    raccomandazione = autoregulation.evaluate_feedback(db, profile, recente, plan=piano)
    return f"Sei fermo su {nomi}. {raccomandazione.reason}"


def format_report(report: ProgressReport) -> str:
    """Rende il report leggibile a testo (usato anche dall'interfaccia)."""
    righe = [
        f"Periodo: {report.period_start} → {report.period_end} "
        f"({report.weeks:.0f} settimane)",
        "",
    ]

    peso = report.weight
    if peso.delta_kg is not None:
        verso = "presi" if peso.delta_kg > 0 else "persi"
        ritmo = (
            f", {abs(peso.weekly_rate_kg):.2f} kg a settimana"
            if peso.weekly_rate_kg
            else ""
        )
        righe.append(
            f"Peso corporeo: {peso.first_average:.1f} → {peso.last_average:.1f} kg "
            f"({abs(peso.delta_kg):.1f} kg {verso}{ritmo})"
        )
        if not peso.smoothed:
            righe.append("  (poche pesate: valore indicativo)")
    else:
        righe.append("Peso corporeo: dati insufficienti")

    righe.append(
        f"Sessioni svolte: {report.adherence.sessions_done} "
        f"({report.adherence.actual_per_week:.1f} a settimana)"
    )

    if report.exercises:
        righe += ["", "Progressione sui carichi (massimale stimato):"]
        for e in report.exercises:
            segno = "+" if e.delta_kg >= 0 else ""
            righe.append(
                f"  {e.exercise_name[:34]:34} {e.first_best_set:>12} → "
                f"{e.last_best_set:<12} {segno}{e.delta_kg:.1f} kg "
                f"({segno}{e.delta_pct:.0%})"
            )
    else:
        righe += ["", "Nessun esercizio con almeno due sessioni registrate."]

    if report.notes:
        righe += ["", "Da tenere presente:"]
        righe += [f"  - {n}" for n in report.notes]

    return "\n".join(righe)
