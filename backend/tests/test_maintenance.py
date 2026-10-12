"""Manutenzione del job orario: traduzioni del catalogo e pulizia dei registri."""

from __future__ import annotations

import datetime as dt

from app.config import get_settings
from app.models import ApiUsage, Exercise, NotificationLog
from app.routers import maintenance
from app.services import locks, translation
from tests.test_dati_utente_intatti import _account, ambiente  # noqa: F401

OGGI = dt.date(2026, 10, 12)


def test_pulizia_solo_dei_registri_che_non_servono(ambiente):
    client, db = ambiente
    _account(client, "a@example.com")
    vecchio = OGGI - dt.timedelta(days=90)
    db.add_all([
        NotificationLog(user_id=1, key=f"integratori:{vecchio}", sent_on=vecchio),
        # Senza data nella chiave: è il registro a impedire che torni, resta.
        NotificationLog(user_id=1, key="scheda-vecchia:3", sent_on=vecchio),
        NotificationLog(user_id=1, key=f"integratori:{OGGI}", sent_on=OGGI),
        ApiUsage(user_id=1, day=vecchio, kind="chat", count=4),
        ApiUsage(user_id=1, day=OGGI, kind="chat", count=1),
    ])
    db.commit()
    assert maintenance.prune(db, today=OGGI) == {"notification_log": 1, "api_usage": 1, "email_codes": 0}
    assert sorted(k for (k,) in db.query(NotificationLog.key)) == [f"integratori:{OGGI}", "scheda-vecchia:3"]


def test_run_vuole_il_segreto_e_traduce_quello_che_manca(ambiente, monkeypatch):
    client, db = ambiente
    monkeypatch.setattr(get_settings(), "push_cron_secret", "segreto-cron")
    assert client.post("/maintenance/run").status_code == 403
    assert client.post("/maintenance/run", headers={"X-Cron-Secret": "sbagliato"}).status_code == 403

    db.add(Exercise(source="everkinetic", external_id="X", name="Cable Fly", primary_muscle="Chest",
                    instructions="Step one.", in_catalog=True))
    db.commit()
    assert translation.pending_count(db) == 1
    monkeypatch.setattr(get_settings(), "gemini_api_key", "finta")
    chiamate = []

    def finta(**kw):
        chiamate.append(kw)
        db.query(Exercise).update({"name_it": "Croci ai cavi"})
        db.commit()
        return 1

    monkeypatch.setattr(translation, "translate_library", finta)
    r = client.post("/maintenance/run", headers={"X-Cron-Secret": "segreto-cron"})
    assert r.status_code == 200, r.text
    assert r.json()["translated"] == 1 and r.json()["pending"] == 0
    assert chiamate == [{"budget_seconds": maintenance.TRANSLATION_BUDGET_SECONDS}]
    # Niente da tradurre: il giro dopo non chiama nemmeno l'LLM.
    client.post("/maintenance/run", headers={"X-Cron-Secret": "segreto-cron"})
    assert len(chiamate) == 1


def test_un_solo_giro_alla_volta(monkeypatch):
    from sqlalchemy import create_engine

    monkeypatch.setattr(locks, "engine", create_engine("sqlite://"))
    with locks.exclusive("prova") as primo:
        with locks.exclusive("prova") as secondo:
            assert primo is True and secondo is False
    with locks.exclusive("prova") as di_nuovo:
        assert di_nuovo is True


def test_traduzione_al_volo_solo_di_quello_che_si_vede(db, monkeypatch):
    """Una pagina non resta appesa a tradurre 200 esercizi: al più due blocchi,
    con un tempo massimo; il resto lo fa il lavoro di fondo."""
    esercizi = [Exercise(source="everkinetic", external_id=str(i), name=f"Ex {i}", primary_muscle="Chest",
                         instructions="Step.") for i in range(50)]
    db.add_all(esercizi)
    db.commit()
    viste = []
    monkeypatch.setattr(translation, "translate_exercises",
                        lambda _db, lista, *, timeout: viste.append((len(lista), timeout)) or 0)
    translation.ensure_translated(db, esercizi)
    assert viste == [(translation.INLINE_MAX_EXERCISES, translation.INLINE_TIMEOUT_SECONDS)]
