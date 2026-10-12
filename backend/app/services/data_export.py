"""Esportazione di tutti i dati di una persona: la sua copia, da tenere.

Due formati:

- JSON: tutto, tabella per tabella, come è nel database. Si raccoglie con le
  stesse regole di "Azzera dati" (`data_reset`): i profili dell'utente e
  tutto ciò che vi appartiene, più impostazioni delle notifiche e prodotti
  inseriti a mano. Restano fuori i segreti (password, codici email, chiavi
  dei dispositivi per le notifiche) e i registri interni (quote, notifiche
  già mandate).
- CSV in uno ZIP: allenamenti, pesate e diario, leggibili in un foglio di
  calcolo, con i nomi degli esercizi e degli alimenti invece degli id.
"""

from __future__ import annotations

import csv
import datetime as dt
import enum
import io
import json
import zipfile
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Table, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Exercise,
    Ingredient,
    MealItem,
    MealLog,
    NotificationSettings,
    SessionSet,
    User,
    UserProfile,
    WeightLog,
    WorkoutSession,
)
from app.services import clock

FORMAT_VERSION = 1
PASTI = {"breakfast": "colazione", "lunch": "pranzo", "dinner": "cena", "snack": "spuntino"}

Tabelle = dict[str, dict[int, dict[str, Any]]]


def _collect(db: Session, table: Table, where: ColumnElement[bool], out: Tabelle) -> None:
    """Le righe di `table` che soddisfano `where` e, a cascata, le figlie.

    Le stesse chiavi esterne che segue "Azzera dati": ciò che verrebbe
    cancellato con il profilo è ciò che gli appartiene.
    """
    righe = list(db.execute(select(table).where(where)).mappings())
    if not righe:
        return
    tabella = out.setdefault(table.name, {})
    for r in righe:
        tabella[r["id"]] = dict(r)
    ids = select(table.c.id).where(where)
    for figlia in Base.metadata.sorted_tables:
        for fk in figlia.foreign_keys:
            if fk.column is table.c.id and (fk.ondelete or "").upper() == "CASCADE":
                _collect(db, figlia, fk.parent.in_(ids), out)


def collect(db: Session, user: User) -> dict[str, list[dict[str, Any]]]:
    """Tutte le righe che appartengono all'utente, per tabella."""
    out: Tabelle = {}
    _collect(db, UserProfile.__table__, UserProfile.user_id == user.id, out)
    _collect(db, NotificationSettings.__table__, NotificationSettings.user_id == user.id, out)
    # Solo i prodotti scritti a mano: le loro righe, non quelle del catalogo
    # condiviso (le ricette che li usano non sono dell'utente).
    manuali = list(
        db.execute(
            select(Ingredient.__table__).where(Ingredient.created_by_user_id == user.id)
        ).mappings()
    )
    if manuali:
        out.setdefault(Ingredient.__table__.name, {}).update({r["id"]: dict(r) for r in manuali})
    return {nome: [righe[i] for i in sorted(righe)] for nome, righe in sorted(out.items())}


def _json_value(v: Any) -> Any:
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, (bytes, bytearray)):
        return None
    return str(v)


def export_json(db: Session, user: User) -> bytes:
    dati = {
        "formato": "kilo-export",
        "versione": FORMAT_VERSION,
        "creato_il": dt.datetime.now(dt.timezone.utc).isoformat(),
        "account": {"email": user.email, "creato_il": user.created_at},
        "tabelle": collect(db, user),
    }
    return json.dumps(dati, ensure_ascii=False, indent=1, default=_json_value).encode("utf-8")


def _csv(intestazione: list[str], righe: list[list[Any]]) -> bytes:
    testo = io.StringIO()
    # Il punto e virgola e il BOM: Excel in italiano lo apre già in colonne.
    scrittore = csv.writer(testo, delimiter=";")
    scrittore.writerow(intestazione)
    for riga in righe:
        scrittore.writerow(
            ["" if v is None else str(v).replace(".", ",") if isinstance(v, float) else v for v in riga]
        )
    return ("﻿" + testo.getvalue()).encode("utf-8")


def _locale(momento: dt.datetime | None) -> str:
    if momento is None:
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=dt.timezone.utc)
    return momento.astimezone(clock.FUSO).strftime("%Y-%m-%d %H:%M")


def export_csv_zip(db: Session, user: User) -> bytes:
    profili = list(db.scalars(select(UserProfile).where(UserProfile.user_id == user.id).order_by(UserProfile.id)))
    ids = [p.id for p in profili]
    nomi = {p.id: p.display_name for p in profili}

    serie = db.execute(
        select(WorkoutSession, SessionSet, Exercise)
        .join(SessionSet, SessionSet.workout_session_id == WorkoutSession.id)
        .join(Exercise, Exercise.id == SessionSet.exercise_id)
        .where(WorkoutSession.profile_id.in_(ids))
        .order_by(WorkoutSession.date, WorkoutSession.id, SessionSet.exercise_id, SessionSet.set_number)
    ).all()
    allenamenti = [
        [nomi[s.profile_id], s.date.isoformat(), s.day_label, _locale(s.started_at),
         e.name_it or e.name, x.set_number, x.weight_kg, x.reps, x.rir]
        for s, x, e in serie
    ]

    pesate = [
        [nomi[w.profile_id], w.date.isoformat(), w.weight_kg, w.body_fat_pct, w.note]
        for w in db.scalars(
            select(WeightLog).where(WeightLog.profile_id.in_(ids)).order_by(WeightLog.date, WeightLog.id)
        )
    ]

    diario: list[list[Any]] = []
    pasti = db.scalars(
        select(MealLog).where(MealLog.profile_id.in_(ids)).order_by(MealLog.date, MealLog.id)
    ).all()
    voci: dict[int, list[MealItem]] = {}
    for item in db.scalars(
        select(MealItem).where(MealItem.meal_log_id.in_([m.id for m in pasti])).order_by(MealItem.id)
    ):
        voci.setdefault(item.meal_log_id, []).append(item)
    for m in pasti:
        inizio = [nomi[m.profile_id], m.date.isoformat(), PASTI.get(m.meal_type, m.meal_type)]
        previsto = "sì" if m.is_planned else ""
        if voci.get(m.id):
            for i in voci[m.id]:
                diario.append([*inizio, i.name, i.quantity_g, i.kcal, i.protein_g, i.carbs_g, i.fat_g, previsto])
        else:
            # Un pasto da ricetta o scritto a mano: una riga con i suoi totali.
            diario.append([*inizio, m.description, None, m.kcal, m.protein_g, m.carbs_g, m.fat_g, previsto])

    archivio = io.BytesIO()
    with zipfile.ZipFile(archivio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("allenamenti.csv", _csv(
            ["profilo", "data", "giorno", "inizio", "esercizio", "serie", "kg", "ripetizioni", "rir"], allenamenti))
        z.writestr("pesate.csv", _csv(["profilo", "data", "kg", "massa_grassa_pct", "nota"], pesate))
        z.writestr("diario.csv", _csv(
            ["profilo", "data", "pasto", "alimento", "grammi", "kcal", "proteine_g", "carboidrati_g",
             "grassi_g", "previsto"], diario))
        z.writestr("tutto.json", export_json(db, user))
    return archivio.getvalue()
