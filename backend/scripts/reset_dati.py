"""Azzera scheda, allenamenti, integratori e diario di un account, tenendo un giorno del diario.

    python scripts/reset_dati.py --email tu@esempio.it                 # prova: mostra cosa sparirebbe
    python scripts/reset_dati.py --email tu@esempio.it --applica       # cancella davvero

Il giorno del diario che resta è oggi (ora italiana); con `--tieni-diario
2026-09-28` se ne sceglie un altro, con `--tieni-diario nessuno` si cancella
tutto il diario. Restano i dati del profilo, le pesate, le ricette salvate e
le preferenze sugli esercizi.

Prima di cancellare salva una copia di tutte le righe tolte in
`backup-reset-<data e ora>.json`, nella cartella da cui lo lanci.

Usa il database indicato da DATABASE_URL (variabile d'ambiente o `.env`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import User, UserProfile  # noqa: E402
from app.services import auth, clock, data_reset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--tieni-diario", default=None, help="AAAA-MM-GG, oppure 'nessuno' (predefinito: oggi)")
    parser.add_argument("--applica", action="store_true", help="senza, è solo una prova e non cancella niente")
    args = parser.parse_args()

    if args.tieni_diario is None:
        giorno: dt.date | None = clock.today()
    elif args.tieni_diario == "nessuno":
        giorno = None
    else:
        giorno = dt.date.fromisoformat(args.tieni_diario)

    db = SessionLocal()
    try:
        utente = db.scalar(select(User).where(User.email == auth.normalize_email(args.email)))
        if utente is None:
            print(f"Nessun account con email {args.email}.")
            return 1
        profili = db.scalars(select(UserProfile).where(UserProfile.user_id == utente.id)).all()
        if not profili:
            print("L'account non ha profili: non c'è niente da azzerare.")
            return 0

        backup: data_reset.Backup = {}
        for profilo in profili:
            for tabella, righe in data_reset.reset_tracking(db, profilo, keep_diary_day=giorno).items():
                backup.setdefault(tabella, []).extend(righe)

        print(f"Account {utente.email}, {len(profili)} profilo/i.")
        print(f"Diario tenuto: {giorno.isoformat() if giorno else 'nessun giorno'}.")
        conteggi = data_reset.counts(backup)
        if not conteggi:
            print("Niente da cancellare.")
        for tabella, n in conteggi.items():
            print(f"  {tabella:<28} {n:>6}")

        if not args.applica:
            db.rollback()
            print("\nProva: non ho cancellato niente. Rilancia con --applica per farlo davvero.")
            return 0

        file = Path(f"backup-reset-{clock.now():%Y%m%d-%H%M%S}.json")
        file.write_text(json.dumps(backup, default=str, ensure_ascii=False, indent=1))
        db.commit()
        print(f"\nFatto. Copia di quello che ho tolto: {file.resolve()}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
