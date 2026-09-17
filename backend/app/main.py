"""Entry point FastAPI dell'applicazione."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title="Kilo — allenamento e nutrizione",
    description=(
        "Genera schede di allenamento e piani alimentari personalizzati a "
        "partire da parametri presi da fonti scientifiche verificate "
        "(ISSN, EFSA, WHO, IOC), non dalla memoria del modello. "
        "L'agente propone e spiega: non sostituisce un medico o un "
        "professionista della nutrizione."
    ),
    version="0.1.0",
    # In produzione la documentazione interattiva resta spenta (DOCS_ENABLED).
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request, call_next):
    """Intestazioni per le risposte dell'API.

    `no-store`: le risposte contengono dati personali (peso, diario,
    integratori) e nessun proxy o browser deve tenerne una copia.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


from app.routers import auth, nutrition, profile, progress, supplements, workout

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(workout.router)
app.include_router(nutrition.router)
app.include_router(supplements.router)
app.include_router(progress.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Stato del servizio e quali integrazioni esterne risultano configurate."""
    return {
        "status": "ok",
        "gemini_configured": settings.gemini_configured,
        "gemini_model": settings.gemini_model,
        "usda_configured": settings.usda_configured,
        # wger e TheMealDB non richiedono chiavi: sempre disponibili.
        "wger_base_url": settings.wger_base_url,
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "app": "agente-allenamento-nutrizione",
        "docs": "/docs" if settings.docs_enabled else None,
        "health": "/health",
    }
