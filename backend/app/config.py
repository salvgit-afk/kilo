"""Configurazione centralizzata dell'applicazione.

Tutte le chiavi/segreti sono letti da variabili d'ambiente (file `.env`).
Non c'è alcun default con valori reali: se una chiave manca, i servizi che
la usano falliscono in modo controllato, non l'avvio dell'app.

Nota sulle integrazioni esterne: sono tutte gratuite e, tranne USDA, non
richiedono nemmeno una chiave. wger espone senza autenticazione gli endpoint
pubblici (esercizi e ingredienti), TheMealDB accetta la chiave di test "1".
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database (Neon) — deve includere ?sslmode=require
    database_url: str = "postgresql+psycopg://user:password@localhost/db?sslmode=require"

    # --- LLM ---------------------------------------------------------------
    # Google Gemini, piano gratuito: https://aistudio.google.com/apikey
    # Serve solo a personalizzare/spiegare le schede e i consigli. Se manca,
    # l'app resta usabile: i piani si generano comunque dai parametri della
    # knowledge base, senza il testo esplicativo.
    gemini_api_key: str = ""
    # Versione fissa: con un alias "latest" il comportamento cambierebbe da
    # solo a ogni aggiornamento di Google. Se la versione viene ritirata,
    # `llm_client` ripiega sull'alias della stessa famiglia.
    gemini_model: str = "gemini-3.5-flash-lite"
    # Modello per le traduzioni del catalogo: si fanno una volta sola e
    # restano salvate, quindi conviene la qualità alla velocità. È un modello
    # diverso da quello della chat anche perché i limiti del piano gratuito
    # sono per modello: tradurre il catalogo non consuma la quota della chat.
    gemini_translation_model: str = "gemini-3.5-flash"

    # --- Database esercizi e alimenti --------------------------------------
    # wger: open source (AGPL), endpoint pubblici senza autenticazione.
    # Fornisce sia gli esercizi (con gruppo muscolare e attrezzatura) sia gli
    # ingredienti (re-import di Open Food Facts).
    wger_base_url: str = "https://wger.de/api/v2"

    # USDA FoodData Central: chiave gratuita self-service, 1000 richieste/ora.
    # https://fdc.nal.usda.gov/api-key-signup
    # Copre gli alimenti generici/grezzi, dove Open Food Facts è più debole.
    secret_key: str = ""

    # --- Sicurezza -----------------------------------------------------------
    # Email (separate da virgola) degli account che possono aggiornare il
    # catalogo: l'operazione scarica le fonti e avvia centinaia di chiamate
    # all'LLM, non deve poterla lanciare chiunque.
    admin_emails: str = ""
    # /docs e /openapi.json descrivono tutta l'API: utili in locale, in
    # produzione sono una mappa per chi cerca punti deboli. Spenti di default.
    docs_enabled: bool = False
    usda_api_key: str = ""
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"

    # TheMealDB: ricette (struttura e procedimento). I macro NON vengono da
    # qui: si calcolano sommando gli ingredienti (vedi models.Recipe).
    themealdb_base_url: str = "https://www.themealdb.com/api/json/v1/1"

    # --- Notifiche push (Web Push, gratuito) --------------------------------
    # Coppia di chiavi VAPID: identifica il server presso i servizi push di
    # Google, Apple e Mozilla. Si genera una volta con
    # `python scripts/generate_vapid_keys.py`; cambiarla invalida tutte le
    # iscrizioni dei telefoni. Senza chiavi le notifiche sono solo spente.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    # Contatto richiesto dal protocollo (mailto: o https:).
    vapid_subject: str = "mailto:admin@example.com"
    # Segreto con cui il job orario (GitHub Actions) chiama /push/dispatch.
    push_cron_secret: str = ""

    # --- CORS ---------------------------------------------------------------
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def _force_psycopg_driver(cls, v: str) -> str:
        """Accetta la connection string "grezza" di Neon.

        Neon fornisce `postgresql://…` (o `postgres://…`): forziamo il driver
        `psycopg` (v3) che usiamo qui, così si può incollare tale e quale.
        """
        if v.startswith("postgresql+"):
            return v  # driver già esplicitato
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://") :]
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://") :]
        return v

    @field_validator("vapid_public_key", "vapid_private_key", "push_cron_secret")
    @classmethod
    def _strip_secret(cls, v: str) -> str:
        """Toglie spazi, a capo e virgolette incollati per sbaglio nel pannello."""
        return v.strip().strip("'\"").strip()

    @field_validator("vapid_subject")
    @classmethod
    def _normalize_subject(cls, v: str) -> str:
        """Il protocollo vuole `mailto:nome@dominio` (o un URL https) senza
        spazi né parentesi: `mailto: nome@dominio`, `<nome@dominio>` o la sola
        email farebbero rifiutare ogni notifica."""
        v = v.strip().strip("'\"").replace("<", "").replace(">", "").strip()
        if v.lower().startswith("mailto:"):
            v = "mailto:" + v[len("mailto:"):].strip()
        elif "@" in v and not v.startswith("https://"):
            v = "mailto:" + v
        return v

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def push_configured(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)

    @property
    def usda_configured(self) -> bool:
        return bool(self.usda_api_key)


@lru_cache
def get_settings() -> Settings:
    """Istanza singleton delle impostazioni (cache per tutto il processo)."""
    return Settings()
