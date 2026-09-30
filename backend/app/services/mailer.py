"""Invio delle email con Brevo (piano gratuito, circa 300 email al giorno).

Render gratuito blocca le porte SMTP in uscita (25, 465 e 587, dal
settembre 2025): Nodemailer o `smtplib` verso Gmail lì non funzionano. Brevo
si chiama con una richiesta HTTPS, che passa. Il mittente (`MAIL_FROM`) va
verificato una volta su Brevo, in *Senders*.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("mailer")

TIMEOUT_SECONDS = 10.0


class MailNotConfigured(RuntimeError):
    """Mancano `BREVO_API_KEY` o `MAIL_FROM`."""


class MailError(RuntimeError):
    """Brevo non ha accettato l'email o non ha risposto."""


def send(to: str, subject: str, html: str, text: str) -> None:
    settings = get_settings()
    if not settings.email_configured:
        raise MailNotConfigured("Invio delle email non configurato.")
    try:
        risposta = httpx.post(
            settings.brevo_api_url,
            headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
            json={
                "sender": {"name": settings.mail_from_name, "email": settings.mail_from},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": html,
                "textContent": text,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as e:
        logger.error("Brevo non raggiungibile: %s", e)
        raise MailError("Servizio email non raggiungibile.") from e
    if risposta.status_code >= 300:
        # Il corpo dice il motivo (chiave sbagliata, mittente non verificato,
        # quota finita): nel log di Render, non all'utente.
        logger.error("Brevo ha rifiutato l'email (%s): %s", risposta.status_code, risposta.text[:300])
        raise MailError("Email non accettata dal servizio di invio.")
