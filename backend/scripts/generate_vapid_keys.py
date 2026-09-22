"""Genera la coppia di chiavi VAPID per le notifiche push.

    python scripts/generate_vapid_keys.py

Stampa le due righe da mettere nelle variabili d'ambiente di Render
(VAPID_PUBLIC_KEY e VAPID_PRIVATE_KEY). La privata non va nel repository.
Va fatto una volta sola: con chiavi nuove i telefoni già iscritti smettono
di ricevere e devono riattivare i promemoria.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
privata = key.private_numbers().private_value.to_bytes(32, "big")
pubblica = key.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)
print(f"VAPID_PUBLIC_KEY={b64url(pubblica)}")
print(f"VAPID_PRIVATE_KEY={b64url(privata)}")
