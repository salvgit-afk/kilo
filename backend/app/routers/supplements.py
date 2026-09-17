"""Sezione integratori — facoltativa.

L'agente non propone integratori: questi endpoint valutano soltanto ciò che
l'utente dichiara. Un profilo senza dichiarazioni restituisce una lista
vuota, ed è un esito normale, non qualcosa da colmare con suggerimenti.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SupplementDeclaration
from app.routers.profile import get_profile
from app.schemas import (
    BenefitOut,
    IntakeDayOut,
    IntakeIn,
    IntakeMilestoneOut,
    SupplementIn,
    SupplementInfoOut,
    SupplementIntakeOut,
    SupplementOut,
)
from app.services import food_diary, supplement_intake, supplements

router = APIRouter(prefix="/supplements", tags=["integratori"])


def _to_out(valutazione) -> SupplementOut:
    d = valutazione.declaration
    return SupplementOut(
        id=d.id,
        kind=d.kind,
        product_name=d.product_name,
        dose_amount=d.dose_amount,
        dose_unit=d.dose_unit,
        doses_per_day=d.doses_per_day,
        evidence=valutazione.evidence,
        message=valutazione.message,
        dose_in_range=valutazione.dose_in_range,
        safety_flag=valutazione.safety_flag,
        benefits=[BenefitOut(**vars(b)) for b in valutazione.benefits],
        knowledge_tags=valutazione.knowledge_tags,
    )


@router.get("", response_model=list[SupplementOut])
def list_supplements(
    profile_id: int, other_caffeine_mg: float = 0.0, db: Session = Depends(get_db)
) -> list[SupplementOut]:
    """Integratori dichiarati, con la valutazione aggiornata.

    `other_caffeine_mg` permette di includere caffè e altre fonti nel
    conteggio: valutare il solo pre-workout ignorerebbe spesso la parte più
    consistente del totale giornaliero.
    """
    profile = get_profile(profile_id, db)

    # Le proteine già assunte dal cibo servono a dire se l'integratore
    # proteico è ancora utile o è ormai superfluo.
    proteine_da_cibo = food_diary.daily_totals(db, profile).protein_g or None

    valutazioni = supplements.assess_all(
        db, profile,
        protein_from_food_g=proteine_da_cibo,
        other_caffeine_mg=other_caffeine_mg,
    )
    return [_to_out(v) for v in valutazioni]


@router.post("", response_model=SupplementOut, status_code=201)
def declare_supplement(
    profile_id: int, payload: SupplementIn, db: Session = Depends(get_db)
) -> SupplementOut:
    profile = get_profile(profile_id, db)

    dichiarazione = SupplementDeclaration(profile_id=profile.id, **payload.model_dump())
    db.add(dichiarazione)
    db.commit()
    db.refresh(dichiarazione)

    proteine_da_cibo = food_diary.daily_totals(db, profile).protein_g or None
    valutazione = supplements.assess(
        dichiarazione, profile, protein_from_food_g=proteine_da_cibo
    )

    dichiarazione.agent_assessment = valutazione.message
    dichiarazione.knowledge_source_tag = ",".join(valutazione.knowledge_tags)
    db.commit()

    return _to_out(valutazione)


def _intake_out(riepilogo: supplement_intake.IntakeSummary) -> SupplementIntakeOut:
    d = riepilogo.declaration
    return SupplementIntakeOut(
        supplement_id=d.id,
        kind=d.kind,
        product_name=d.product_name,
        dose_amount=d.dose_amount,
        dose_unit=d.dose_unit,
        doses_required=riepilogo.doses_required,
        since=riepilogo.since,
        days_taken=riepilogo.days_taken,
        current_streak=riepilogo.current_streak,
        missed_days=riepilogo.missed_days,
        history_days=supplement_intake.HISTORY_DAYS,
        history=[
            IntakeDayOut(date=giorno, doses=dosi)
            for giorno, dosi in sorted(riepilogo.history.items())
        ],
        milestone=IntakeMilestoneOut(**vars(riepilogo.milestone)) if riepilogo.milestone else None,
    )


@router.get("/intake", response_model=list[SupplementIntakeOut])
def intake_diary(
    profile_id: int, today: dt.date | None = None, db: Session = Depends(get_db)
) -> list[SupplementIntakeOut]:
    """Diario delle assunzioni degli integratori dichiarati.

    `today` è la data locale del client: i conteggi (serie, giorni saltati)
    si calcolano rispetto al suo giorno, non a quello UTC del server.
    """
    profile = get_profile(profile_id, db)
    oggi = today or dt.date.today()
    return [
        _intake_out(supplement_intake.summarize(db, d, today=oggi))
        for d in supplement_intake.active_declarations(db, profile)
    ]


@router.put("/{supplement_id}/intake", response_model=SupplementIntakeOut)
def log_intake(
    supplement_id: int,
    profile_id: int,
    payload: IntakeIn,
    today: dt.date | None = None,
    db: Session = Depends(get_db),
) -> SupplementIntakeOut:
    """Segna quante assunzioni ci sono state in un giorno (0 = nessuna)."""
    profile = get_profile(profile_id, db)
    dichiarazione = db.get(SupplementDeclaration, supplement_id)
    if dichiarazione is None or dichiarazione.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Integratore non trovato")

    oggi = today or dt.date.today()
    # Il giorno del client può essere avanti di uno rispetto al server (UTC),
    # non di più.
    if payload.date > min(oggi, dt.date.today() + dt.timedelta(days=1)):
        raise HTTPException(status_code=422, detail="Non si segnano assunzioni future")

    supplement_intake.set_doses(db, dichiarazione, payload.date, payload.doses)
    return _intake_out(supplement_intake.summarize(db, dichiarazione, today=oggi))


@router.delete("/{supplement_id}", status_code=204, response_model=None)
def remove_supplement(supplement_id: int, db: Session = Depends(get_db)) -> None:
    dichiarazione = db.get(SupplementDeclaration, supplement_id)
    if dichiarazione is None:
        raise HTTPException(status_code=404, detail="Integratore non trovato")
    db.delete(dichiarazione)
    db.commit()


@router.get("/catalog", response_model=list[SupplementInfoOut])
def supplement_catalog(profile_id: int, db: Session = Depends(get_db)) -> list[SupplementInfoOut]:
    """Cosa dicono le fonti su ciascun integratore coperto dalla knowledge base.

    È **consultazione**, non consiglio: l'utente apre la scheda che gli
    interessa, e ogni scheda riporta l'evidenza per esito — anche quando è
    debole o assente. Nessuna voce viene evidenziata come "da prendere".
    """
    profile = get_profile(profile_id, db)
    schede = []
    for kind in sorted(supplements.KIND_TO_TAG):
        # Dichiarazione temporanea, mai salvata: serve a riusare la stessa
        # valutazione della sezione, senza dose.
        valutazione = supplements.assess(
            SupplementDeclaration(profile_id=profile.id, kind=kind, doses_per_day=1.0),
            profile,
        )
        schede.append(
            SupplementInfoOut(
                kind=kind,
                evidence=valutazione.evidence,
                message=valutazione.message,
                benefits=[BenefitOut(**vars(b)) for b in valutazione.benefits],
                knowledge_tags=valutazione.knowledge_tags,
            )
        )
    return schede


@router.post("/preview", response_model=SupplementOut)
def preview_supplement(
    profile_id: int,
    payload: SupplementIn,
    other_caffeine_mg: float = 0.0,
    db: Session = Depends(get_db),
) -> SupplementOut:
    """Valuta un dosaggio **senza salvarlo**: il riscontro arriva mentre
    l'utente compila, non dopo aver confermato."""
    profile = get_profile(profile_id, db)
    bozza = SupplementDeclaration(profile_id=profile.id, **payload.model_dump())
    bozza.id = 0
    proteine_da_cibo = food_diary.daily_totals(db, profile).protein_g or None
    valutazione = supplements.assess(
        bozza, profile,
        protein_from_food_g=proteine_da_cibo,
        other_caffeine_mg=other_caffeine_mg,
    )
    return _to_out(valutazione)


@router.get("/kinds", response_model=list[str])
def list_kinds() -> list[str]:
    """Tipi su cui la knowledge base ha una fonte dedicata.

    Non è un catalogo di cose da consigliare: è l'elenco di ciò su cui
    l'agente sa rispondere. Per tutto il resto esiste `other`, che attiva la
    risposta onesta «non ho una fonte verificata».
    """
    return sorted(supplements.KIND_TO_TAG) + ["other"]
