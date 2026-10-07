"""Note dell'utente sugli esercizi: regolazioni della macchina, presa, accorgimenti.

Una nota per esercizio e per profilo, non per riga di scheda: la macchina è
la stessa in tutte le schede, e la nota deve comparire dovunque compaia
l'esercizio, allenamento compreso. Vale anche fra i doppioni del catalogo
(`training_log.same_exercise_ids`): se l'esercizio passa alla versione con i
disegni, la nota lo segue come i carichi.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExerciseNote
from app.services.training_log import same_exercise_ids

MAX_LENGTH = 500


def notes_for(db: Session, profile_id: int, exercise_ids: list[int]) -> dict[int, str]:
    """La nota di ogni esercizio richiesto (o di un suo doppione), se c'è."""
    risultato: dict[int, str] = {}
    for exercise_id in dict.fromkeys(exercise_ids):
        gruppo = same_exercise_ids(db, exercise_id)
        note = {
            n.exercise_id: n.text
            for n in db.scalars(
                select(ExerciseNote).where(
                    ExerciseNote.profile_id == profile_id, ExerciseNote.exercise_id.in_(gruppo)
                )
            )
        }
        testo = note.get(exercise_id) or next(iter(note.values()), None)
        if testo:
            risultato[exercise_id] = testo
    return risultato


def set_note(db: Session, profile_id: int, exercise_id: int, text: str) -> str | None:
    """Salva la nota; vuota la cancella. Restituisce il testo salvato."""
    testo = text.strip()[:MAX_LENGTH]
    nota = db.scalar(
        select(ExerciseNote).where(
            ExerciseNote.profile_id == profile_id, ExerciseNote.exercise_id == exercise_id
        )
    )
    if not testo:
        if nota is not None:
            db.delete(nota)
            db.commit()
        return None
    if nota is None:
        db.add(ExerciseNote(profile_id=profile_id, exercise_id=exercise_id, text=testo))
    else:
        nota.text = testo
    db.commit()
    return testo
