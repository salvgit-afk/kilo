"""Due falle minori chiuse: nomi dei prodotti altrui e indirizzo per i limiti di accesso."""

from __future__ import annotations

from starlette.requests import Request

from app.config import get_settings
from app.models import Ingredient
from app.routers.auth import client_ip
from app.services import translation
from tests.test_dati_utente_intatti import _account, ambiente  # noqa: F401


def test_i_nomi_dei_prodotti_inseriti_a_mano_restano_di_chi_li_ha_inseriti(ambiente, monkeypatch):
    client, db = ambiente
    h, _ = _account(client, "salvo@example.com")
    _account(client, "altro@example.com")
    mio = Ingredient(name="Barretta di casa", created_by_user_id=1, kcal_100g=400, protein_100g=20,
                     carbs_100g=40, fat_100g=15, source="manual")
    altrui = Ingredient(name="Integratore su ricetta", created_by_user_id=2, kcal_100g=1, protein_100g=0,
                        carbs_100g=0, fat_100g=0, source="manual")
    catalogo = Ingredient(name="Rice, white", kcal_100g=130, protein_100g=2.7, carbs_100g=28,
                          fat_100g=0.3, source="usda")
    db.add_all([mio, altrui, catalogo])
    db.commit()
    monkeypatch.setattr(translation, "translate_food_names", lambda _db, ingr: {i.id: i.name for i in ingr})

    r = client.post("/nutrition/foods/names", headers=h, json={"ids": [mio.id, altrui.id, catalogo.id]})
    assert r.status_code == 200, r.text
    assert set(r.json().values()) == {"Barretta di casa", "Rice, white"}


def _richiesta(**intestazioni) -> Request:
    return Request({
        "type": "http", "method": "POST", "path": "/auth/login", "client": ("10.0.0.9", 1234),
        "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in intestazioni.items()],
    })


def test_indirizzo_firmato_dal_proxy(monkeypatch):
    monkeypatch.setattr(get_settings(), "proxy_secret", "segreto-del-proxy")
    vercel = {"x_forwarded_for": "203.0.113.7, 76.76.21.1"}
    # Con il segreto giusto vale l'indirizzo visto dal proxy di Next.
    assert client_ip(_richiesta(**vercel, x_kilo_proxy_secret="segreto-del-proxy",
                                x_kilo_client_ip="203.0.113.7")) == "203.0.113.7"
    # Senza segreto, o con uno sbagliato, si ignora: lo potrebbe scrivere chiunque.
    assert client_ip(_richiesta(**vercel, x_kilo_proxy_secret="indovino", x_kilo_client_ip="1.2.3.4")) == "76.76.21.1"
    assert client_ip(_richiesta(**vercel, x_kilo_client_ip="1.2.3.4")) == "76.76.21.1"


def test_senza_segreto_configurato_come_prima(monkeypatch):
    monkeypatch.setattr(get_settings(), "proxy_secret", "")
    assert client_ip(_richiesta(x_forwarded_for="1.1.1.1, 76.76.21.1", x_kilo_proxy_secret="",
                                x_kilo_client_ip="1.2.3.4")) == "76.76.21.1"
    assert client_ip(_richiesta()) == "10.0.0.9"
