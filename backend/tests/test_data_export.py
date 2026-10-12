"""Esportazione dei dati: tutto ciò che è dell'utente, niente di altri, nessun segreto."""

from __future__ import annotations

import csv
import io
import json
import zipfile

from app.models import Ingredient, PushSubscription
from tests.test_dati_utente_intatti import _account, _catalogo, _fotografia, _riempi, ambiente  # noqa: F401


def _csv(archivio: zipfile.ZipFile, nome: str) -> list[dict[str, str]]:
    testo = archivio.read(nome).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(testo), delimiter=";"))


def test_esporta_tutto_e_solo_i_dati_dell_utente(ambiente):
    client, db = ambiente
    h, pid = _account(client, "salvo@example.com")
    h2, pid2 = _account(client, "altro@example.com")
    ex = _catalogo(db)
    _riempi(db, pid, ex)
    _riempi(db, pid2, ex)
    io_utente = 1
    db.add(Ingredient(name="Barretta di casa", created_by_user_id=io_utente, kcal_100g=400, protein_100g=20,
                      carbs_100g=40, fat_100g=15, source="manual"))
    db.add(Ingredient(name="Prodotto dell'altro", created_by_user_id=2, kcal_100g=100, protein_100g=1,
                      carbs_100g=1, fat_100g=1, source="manual"))
    db.add(PushSubscription(user_id=io_utente, endpoint="https://push.example/abc", p256dh="chiave", auth="segreto"))
    db.commit()
    prima = _fotografia(db)

    r = client.get(f"/profile/{pid}/export?formato=json", headers=h)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    dati = r.json()
    tabelle = dati["tabelle"]
    assert dati["account"]["email"] == "salvo@example.com"
    assert {p["id"] for p in tabelle["user_profiles"]} == {pid}
    assert {s["profile_id"] for s in tabelle["workout_sessions"]} == {pid}
    assert len(tabelle["session_sets"]) == 4 and len(tabelle["workout_plans"]) == 2
    for nome in ("meal_items", "weight_logs", "supplement_intakes", "exercise_notes", "exercise_preferences"):
        assert len(tabelle[nome]) >= 1, nome
    assert [i["name"] for i in tabelle["ingredients"]] == ["Barretta di casa"]
    testo = r.text
    for segreto in ("password_hash", "segreto", "push_subscriptions", "email_codes", "api_usage"):
        assert segreto not in testo
    assert "altro@example.com" not in testo

    r = client.get(f"/profile/{pid}/export", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    archivio = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(archivio.namelist()) == ["allenamenti.csv", "diario.csv", "pesate.csv", "tutto.json"]
    serie = _csv(archivio, "allenamenti.csv")
    assert len(serie) == 4
    assert serie[0]["esercizio"] == "French press monolaterale al cavo"
    assert {s["kg"] for s in serie} == {"10,0", "40,0", "120,0"}
    assert _csv(archivio, "pesate.csv")[0]["kg"] == "78,4"
    assert _csv(archivio, "diario.csv")[0]["pasto"] == "pranzo"
    assert json.loads(archivio.read("tutto.json"))["tabelle"]["user_profiles"][0]["id"] == pid

    # Il profilo di un altro non si esporta, e leggere non cambia niente.
    assert client.get(f"/profile/{pid2}/export", headers=h).status_code == 404
    assert client.get(f"/profile/{pid}/export?formato=xml", headers=h).status_code == 422
    db.expire_all()
    assert _fotografia(db) == prima
