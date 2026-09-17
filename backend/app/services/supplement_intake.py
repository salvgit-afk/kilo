"""Diario delle assunzioni degli integratori dichiarati.

Serve a ricordare, non a prescrivere: l'utente segna ciò che prende e vede
da quanti giorni lo prende, se ne ha saltato qualcuno e la serie in corso.
Nessun conteggio parte da solo per integratori non dichiarati.

Le date arrivano dal client (il suo "oggi" locale): il server gira in UTC e
fra mezzanotte e le due, in Italia, avrebbe ancora la data di ieri.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SupplementDeclaration, SupplementIntake, SupplementKind, UserProfile

# Giorni mostrati nello storico e su cui si contano i giorni saltati.
HISTORY_DAYS = 28
MAX_DOSES_PER_DAY = 20

# Durate documentate nelle fonti, per mostrare a che punto è l'utente. Non
# sono obiettivi da raggiungere: dicono dopo quanto ha senso aspettarsi
# l'effetto per cui l'integratore è studiato.
MILESTONES: dict[str, tuple[int, str, str]] = {
    SupplementKind.CREATINE: (
        28,
        "Senza fase di carico, con 3-5 g al giorno le scorte muscolari salgono "
        "in 3-4 settimane.",
        "creatina",
    ),
    SupplementKind.BETA_ALANINE: (
        28,
        "Servono almeno 4 settimane continuative per aumentare la carnosina "
        "muscolare.",
        "beta_alanina",
    ),
    SupplementKind.ASHWAGANDHA: (
        56,
        "Gli effetti sul sonno sono più marcati dopo almeno 8 settimane.",
        "integratori_oltre_muscolo",
    ),
}


@dataclass
class Milestone:
    days: int
    note: str
    knowledge_tag: str


@dataclass
class IntakeSummary:
    declaration: SupplementDeclaration
    doses_required: int
    since: dt.date
    days_taken: int
    current_streak: int
    missed_days: int
    history: dict[dt.date, int] = field(default_factory=dict)
    milestone: Milestone | None = None

    def doses_on(self, date: dt.date) -> int:
        return self.history.get(date, 0)


def required_doses(declaration: SupplementDeclaration) -> int:
    """Assunzioni al giorno dichiarate, arrotondate all'intero superiore."""
    return max(1, math.ceil(declaration.doses_per_day or 1.0))


def active_declarations(db: Session, profile: UserProfile) -> list[SupplementDeclaration]:
    return list(
        db.scalars(
            select(SupplementDeclaration)
            .where(
                SupplementDeclaration.profile_id == profile.id,
                SupplementDeclaration.is_active.is_(True),
            )
            .order_by(SupplementDeclaration.id)
        )
    )


def set_doses(
    db: Session, declaration: SupplementDeclaration, date: dt.date, doses: int
) -> None:
    """Imposta le assunzioni di un giorno; zero cancella la riga."""
    if doses < 0 or doses > MAX_DOSES_PER_DAY:
        raise ValueError(f"Le assunzioni vanno da 0 a {MAX_DOSES_PER_DAY}.")

    riga = db.scalar(
        select(SupplementIntake).where(
            SupplementIntake.supplement_id == declaration.id,
            SupplementIntake.date == date,
        )
    )
    if doses == 0:
        if riga is not None:
            db.delete(riga)
    elif riga is None:
        db.add(SupplementIntake(supplement_id=declaration.id, date=date, doses=doses))
    else:
        riga.doses = doses
    db.commit()


def summarize(
    db: Session, declaration: SupplementDeclaration, *, today: dt.date
) -> IntakeSummary:
    """Totali, serie e giorni saltati, calcolati rispetto a `today`."""
    righe = db.scalars(
        select(SupplementIntake).where(
            SupplementIntake.supplement_id == declaration.id,
            SupplementIntake.date <= today,
            SupplementIntake.doses > 0,
        )
    ).all()
    presi = {r.date: r.doses for r in righe}

    dichiarato = declaration.created_at.date() if declaration.created_at else today
    # Si possono segnare anche giorni precedenti alla dichiarazione: l'inizio
    # è il primo dei due.
    inizio = min([dichiarato, today, *presi])

    # La serie include oggi solo se oggi è già segnato: fino a sera, un
    # giorno non ancora segnato non la interrompe.
    giorno = today if today in presi else today - dt.timedelta(days=1)
    serie = 0
    while giorno in presi:
        serie += 1
        giorno -= dt.timedelta(days=1)

    finestra_inizio = today - dt.timedelta(days=HISTORY_DAYS - 1)
    saltati = sum(
        1
        for n in range((today - max(inizio, finestra_inizio)).days)
        if max(inizio, finestra_inizio) + dt.timedelta(days=n) not in presi
    )

    traguardo = MILESTONES.get(declaration.kind)
    return IntakeSummary(
        declaration=declaration,
        doses_required=required_doses(declaration),
        since=inizio,
        days_taken=len(presi),
        current_streak=serie,
        missed_days=saltati,
        history={d: n for d, n in presi.items() if d >= finestra_inizio},
        milestone=Milestone(*traguardo) if traguardo else None,
    )


def pending(
    db: Session, profile: UserProfile, *, today: dt.date
) -> list[tuple[SupplementDeclaration, int]]:
    """Integratori non ancora segnati del tutto oggi, con le dosi già segnate."""
    dichiarati = active_declarations(db, profile)
    if not dichiarati:
        return []
    segnate = dict(
        db.execute(
            select(SupplementIntake.supplement_id, SupplementIntake.doses).where(
                SupplementIntake.supplement_id.in_([d.id for d in dichiarati]),
                SupplementIntake.date == today,
            )
        ).all()
    )
    return [
        (d, segnate.get(d.id, 0))
        for d in dichiarati
        if segnate.get(d.id, 0) < required_doses(d)
    ]
