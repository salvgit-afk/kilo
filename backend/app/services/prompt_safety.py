"""Testo non fidato dentro un prompt.

Tutto ciò che non scriviamo noi — una ricetta incollata da un sito, il
messaggio dell'utente, il testo letto da un'immagine — per il modello è
indistinguibile dalle nostre istruzioni. È la **prompt injection**: una riga
come «ignora le istruzioni precedenti» dentro i dati può cambiare il
comportamento del modello.

La difesa qui è in tre strati, nessuno dei quali basta da solo:
  1. le regole stanno nel `systemInstruction`, separate dal messaggio;
  2. i dati non fidati stanno fra tag e non possono chiuderli, perché le
     parentesi angolari vengono sostituite con caratteri simili ma innocui;
  3. l'output è vincolato a uno schema JSON, quindi anche un modello
     convinto non può rispondere qualcos'altro.

Resta il limite di fondo: non esiste un equivalente dei prepared statement
per gli LLM. Per questo nessuno di questi percorsi esegue azioni: al massimo
produce dati che l'utente conferma.
"""

from __future__ import annotations

# Caratteri visivamente simili a < e >, ma che il modello non legge come tag.
_SOSTITUZIONI = {"<": "‹", ">": "›"}


def untrusted(text: str) -> str:
    """Testo pronto per stare fra tag senza poterli chiudere."""
    pulito = text or ""
    for carattere, sostituto in _SOSTITUZIONI.items():
        pulito = pulito.replace(carattere, sostituto)
    return pulito


def wrap(text: str, tag: str) -> str:
    """Testo non fidato racchiuso nel suo tag, pronto per il prompt."""
    return f"<{tag}>\n{untrusted(text)}\n</{tag}>"
