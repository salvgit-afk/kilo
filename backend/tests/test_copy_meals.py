""""Copia da ieri": un pasto o la giornata su un altro giorno, senza toccare l'originale."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.models import MealItem, MealLog
from tests.test_dati_utente_intatti import IERI, OGGI, _account, _catalogo, _riempi, ambiente  # noqa: F401


def test_copia_il_pranzo_di_ieri_su_oggi(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _riempi(db, pid, _catalogo(db))
    db.add(MealLog(profile_id=pid, date=IERI, meal_type="dinner", description="Pizza margherita",
                   kcal=850, protein_g=30, carbs_g=110, fat_g=28))
    db.commit()

    r = client.post(f"/nutrition/diary/copy?profile_id={pid}", headers=h,
                    json={"from_date": IERI.isoformat(), "meal_type": "lunch"})
    assert r.status_code == 201, r.text
    assert r.json() == {"copied": 1}
    oggi = db.scalars(select(MealItem).join(MealLog).where(MealLog.profile_id == pid, MealLog.date == OGGI)).all()
    assert [(i.name, i.quantity_g, i.kcal) for i in oggi] == [("Riso", 80, 280)]
    # L'originale resta dov'era.
    assert db.scalars(select(MealItem).join(MealLog).where(MealLog.date == IERI)).all()

    # Tutta la giornata: il pranzo e la cena senza alimenti (con i suoi totali).
    domani = OGGI + dt.timedelta(days=1)
    r = client.post(f"/nutrition/diary/copy?profile_id={pid}", headers=h,
                    json={"from_date": IERI.isoformat(), "to_date": domani.isoformat()})
    assert r.json() == {"copied": 2}
    pasti = db.scalars(select(MealLog).where(MealLog.profile_id == pid, MealLog.date == domani)).all()
    assert all(m.is_planned for m in pasti), "nel futuro la copia è prevista, da confermare"
    assert {m.meal_type for m in pasti} == {"lunch", "dinner"}


def test_copia_rifiutata_sullo_stesso_giorno_o_per_altri(ambiente):
    client, db = ambiente
    h, pid = _account(client, "a@example.com")
    _h2, pid2 = _account(client, "b@example.com")
    r = client.post(f"/nutrition/diary/copy?profile_id={pid}", headers=h, json={"from_date": OGGI.isoformat()})
    assert r.status_code == 422
    r = client.post(f"/nutrition/diary/copy?profile_id={pid2}", headers=h, json={"from_date": IERI.isoformat()})
    assert r.status_code == 404
    r = client.post(f"/nutrition/diary/copy?profile_id={pid}", headers=h,
                    json={"from_date": IERI.isoformat(), "meal_type": "merenda"})
    assert r.status_code == 422
