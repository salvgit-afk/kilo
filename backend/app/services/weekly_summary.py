"""Riepilogo della settimana appena conclusa (lunedì-domenica).

Tutti i numeri sono calcolati dai dati registrati: allenamenti rispetto a
quelli previsti, media del peso rispetto alla settimana prima, proteine
rispetto al target nei giorni registrati, costanza con gli integratori
dichiarati. In più, **una sola cosa** su cui concentrarsi nella settimana
successiva: la più lontana dall'obiettivo, così il riepilogo resta un
indirizzo e non un elenco di mancanze.

Il commento discorsivo lo scrive la chat, solo se l'utente lo chiede.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserProfile, WeightLog, WorkoutPlan, WorkoutSession
from app.services import food_diary, nutrition_targets, supplement_intake

# Coerente con `progress_report._moving_average`: con meno di 2 pesate in una
# settimana la media resta esposta all'oscillazione di un singolo giorno.
MIN_WEIGH_INS = 2
PROTEIN_OK = 0.9
SUPPLEMENT_OK_DAYS = 6

NOMI = {
    "creatine": "la creatina", "caffeine": "la caffeina", "protein_powder": "le proteine in polvere",
    "beta_alanine": "la beta-alanina", "hmb": "l'HMB", "bcaa": "i BCAA",
    "glutamine": "la glutammina", "citrulline": "la citrullina", "vitamin_d": "la vitamina D",
    "omega_3": "gli omega-3", "ashwagandha": "l'ashwagandha", "moringa": "la moringa",
}


@dataclass
class SupplementWeek:
    supplement_id: int
    kind: str
    product_name: str | None
    days_taken: int
    days_expected: int


@dataclass
class WeeklySummary:
    week_start: dt.date
    week_end: dt.date
    sessions_done: int
    sessions_planned: int | None
    weight_average: float | None
    weight_previous_average: float | None
    weigh_ins: int
    logged_days: int
    protein_average_g: float | None
    protein_target_g: float | None
    supplements: list[SupplementWeek] = field(default_factory=list)
    focus: str | None = None
    has_data: bool = False

    @property
    def weight_delta_kg(self) -> float | None:
        if self.weight_average is None or self.weight_previous_average is None:
            return None
        return self.weight_average - self.weight_previous_average


def last_week(today: dt.date) -> tuple[dt.date, dt.date]:
    """Lunedì e domenica della settimana conclusa prima di `today`."""
    lunedi = today - dt.timedelta(days=today.weekday() + 7)
    return lunedi, lunedi + dt.timedelta(days=6)


def _weight_average(db: Session, profile: UserProfile, start: dt.date, end: dt.date) -> tuple[float | None, int]:
    pesi = db.scalars(
        select(WeightLog.weight_kg).where(
            WeightLog.profile_id == profile.id,
            WeightLog.date >= start,
            WeightLog.date <= end,
        )
    ).all()
    return (mean(pesi) if pesi else None), len(pesi)


def build(db: Session, profile: UserProfile, *, today: dt.date) -> WeeklySummary:
    inizio, fine = last_week(today)
    giorni = [inizio + dt.timedelta(days=n) for n in range(7)]

    sessioni = len(
        db.scalars(
            select(WorkoutSession.id).where(
                WorkoutSession.profile_id == profile.id,
                WorkoutSession.date >= inizio,
                WorkoutSession.date <= fine,
            )
        ).all()
    )
    piano = db.scalar(
        select(WorkoutPlan)
        .where(
            WorkoutPlan.profile_id == profile.id,
            WorkoutPlan.is_active.is_(True),
            WorkoutPlan.started_at <= fine,
        )
        .order_by(WorkoutPlan.started_at.desc(), WorkoutPlan.id.desc())
        .limit(1)
    )

    media, pesate = _weight_average(db, profile, inizio, fine)
    media_prima, _ = _weight_average(
        db, profile, inizio - dt.timedelta(days=7), inizio - dt.timedelta(days=1)
    )

    proteine = [
        t.protein_g
        for t in (food_diary.daily_totals(db, profile, date=g) for g in giorni)
        if t.kcal > 0
    ]
    try:
        target = nutrition_targets.compute_targets(
            profile, training_days=profile.training_days_per_week
        ).protein_g
    except ValueError:
        target = None

    integratori = []
    for d in supplement_intake.active_declarations(db, profile):
        r = supplement_intake.summarize(db, d, today=fine)
        attesi = sum(1 for g in giorni if g >= r.since)
        if attesi:
            integratori.append(SupplementWeek(
                supplement_id=d.id,
                kind=d.kind,
                product_name=d.product_name,
                days_taken=sum(1 for g in giorni if r.doses_on(g) > 0),
                days_expected=attesi,
            ))

    riepilogo = WeeklySummary(
        week_start=inizio,
        week_end=fine,
        sessions_done=sessioni,
        sessions_planned=piano.days_per_week if piano else None,
        weight_average=round(media, 1) if media is not None else None,
        weight_previous_average=round(media_prima, 1) if media_prima is not None else None,
        weigh_ins=pesate,
        logged_days=len(proteine),
        protein_average_g=round(mean(proteine)) if proteine else None,
        protein_target_g=round(target) if target else None,
        supplements=integratori,
    )
    riepilogo.has_data = bool(
        sessioni or pesate or proteine or any(i.days_taken for i in integratori)
    )
    riepilogo.focus = _focus(riepilogo)
    return riepilogo


def _focus(r: WeeklySummary) -> str | None:
    """La cosa più lontana dall'obiettivo, in ordine di impatto sui risultati."""
    if not r.has_data:
        return None
    if r.sessions_planned and r.sessions_done < r.sessions_planned:
        return (
            f"Allenamenti: {r.sessions_done} su {r.sessions_planned}. La prossima settimana "
            "punta a completarli tutti: le serie della scheda sono calcolate sul totale "
            "della settimana."
        )
    if r.protein_average_g is not None and r.protein_target_g and (
        r.protein_average_g / r.protein_target_g < PROTEIN_OK
    ):
        return (
            f"Proteine: in media {r.protein_average_g} g su {r.protein_target_g} g. Conta il "
            "totale della giornata: «Cosa mi manca oggi» nel diario calcola come chiuderlo."
        )
    for i in r.supplements:
        if i.days_expected >= SUPPLEMENT_OK_DAYS and i.days_taken < SUPPLEMENT_OK_DAYS:
            nome = i.product_name if i.kind == "other" and i.product_name else NOMI.get(i.kind, i.kind)
            return (
                f"Costanza con {nome}: {i.days_taken} giorni su {i.days_expected}. Il "
                "banner dei promemoria può aiutarti a non dimenticarlo."
            )
    if r.weigh_ins < MIN_WEIGH_INS:
        return (
            f"Pesate: {r.weigh_ins} in tutta la settimana. Con 3-4 pesate a settimana "
            "la tendenza del peso diventa leggibile."
        )
    return "Settimana solida su tutti i fronti: mantieni così."
