"""Quali notifiche merita oggi una persona, e a che ora.

Le regole stanno qui, l'invio in `push_notifications`. Ogni notifica nasce
da una condizione sui dati dell'utente e da un parametro delle fonti: il
modello non scrive nulla, come per il resto di Kilo.

Tre principi, per non diventare rumore:
  1. **Una notifica sola per evento.** La chiave descrive l'evento
     (`carichi:12:2026-W39`): la stessa situazione non si ripete, una nuova
     sì (vedi `NotificationLog`).
  2. **Al massimo tre al giorno**, le più importanti per prime.
  3. **Al momento giusto**: l'allenamento all'ora in cui vai in palestra,
     gli integratori quando ha senso prenderli, il resto la sera.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    MealLog,
    NotificationLog,
    NotificationSettings,
    SavedRecipe,
    TrainingFeedback,
    User,
    UserProfile,
    WorkoutSession,
)
from app.services import (
    daily_reminders,
    food_diary,
    nutrition_targets,
    progression,
    supplement_intake,
    supplements,
    training_log,
    training_schedule,
    weekly_summary,
)

# Ora in cui si presume si vada in palestra se non ci sono sessioni avviate
# da cui ricavarla.
DEFAULT_GYM_HOUR = 18
# Sessioni recenti guardate per capire a che ora ci si allena.
GYM_HOUR_SESSIONS = 12

# Settimane con la stessa scheda dopo cui proporre di variare: stesso
# orizzonte delle note di Kilo (4-6 settimane per valutare, 6-8 per cambiare).
PLAN_AGE_WEEKS = 6
# Giorni senza registrare nulla prima di ricordare il diario, a chi lo usava.
DIARY_SILENT_DAYS = 2
# Quante volte insistere sul diario prima di lasciar perdere.
DIARY_MAX_REMINDERS = 3
# Giorni prima di ricordare una ricetta salvata e mai cucinata.
SAVED_RECIPE_DAYS = 10
# Proteine: oltre questo valore in g/kg le fonti (`protein_intake.md`) le
# considerano probabilmente inutili in più, non pericolose.
PROTEIN_HIGH_G_PER_KG = 2.5
# Sotto questa quota del target, la sera, vale la pena segnalarlo.
PROTEIN_LOW_RATIO = 0.7


@dataclass
class Notification:
    key: str
    title: str
    body: str
    section: str
    category: str
    priority: int
    # Ore (italiane) in cui ha senso mandarla, estremi inclusi.
    hours: tuple[int, int]


def settings_for(db: Session, user_id: int) -> NotificationSettings:
    """Preferenze dell'account, create alla prima lettura con i valori di
    partenza (tutto acceso tranne il meal prep della domenica)."""
    s = db.scalar(select(NotificationSettings).where(NotificationSettings.user_id == user_id))
    if s is None:
        s = NotificationSettings(user_id=user_id)
        db.add(s)
        db.flush()
    return s


def gym_hour(db: Session, profile: UserProfile, *, fuso: dt.tzinfo, override: int | None = None) -> int:
    """A che ora si allena di solito, dagli avvii delle ultime sessioni.

    La mediana e non la media: una sessione avviata alle 7 del mattino in
    vacanza non deve spostare il promemoria di tutte le altre.
    """
    if override is not None:
        return override
    avvii = db.scalars(
        select(WorkoutSession.started_at)
        .where(WorkoutSession.profile_id == profile.id, WorkoutSession.started_at.is_not(None))
        .order_by(WorkoutSession.date.desc())
        .limit(GYM_HOUR_SESSIONS)
    ).all()
    # Senza fuso (SQLite) l'orario salvato è in UTC: `astimezone` lo
    # leggerebbe invece nell'ora locale del server.
    ore = [
        (a if a.tzinfo else a.replace(tzinfo=dt.timezone.utc)).astimezone(fuso).hour
        for a in avvii
        if a is not None
    ]
    return round(statistics.median(ore)) if ore else DEFAULT_GYM_HOUR


def _kg(valore: float) -> str:
    """Chili come si scrivono in italiano: 62,5 e non 62.5."""
    return f"{valore:g}".replace(".", ",")


def _settimana(d: dt.date) -> str:
    anno, numero, _ = d.isocalendar()
    return f"{anno}-W{numero:02d}"


# --- Allenamento -----------------------------------------------------------


def _training(db: Session, profile: UserProfile, today: dt.date, ora_palestra: int) -> list[Notification]:
    note: list[Notification] = []
    for piano in daily_reminders.workouts_due(db, profile, today):
        note.append(
            Notification(
                key=f"allenamento:{piano.id}:{today}",
                title="È il tuo giorno",
                body=f"Oggi tocca a {piano.name}. Apri la scheda e avvia la sessione: i carichi si segnano da soli mentre ti alleni.",
                section="scheda",
                category="training",
                priority=1,
                hours=(ora_palestra, min(ora_palestra + 2, 22)),
            )
        )
    note.extend(_progressione(db, profile, today))
    note.extend(_scheda_vecchia(db, profile, today))
    return note


def _progressione(db: Session, profile: UserProfile, today: dt.date) -> list[Notification]:
    """Esercizi della scheda in uso pronti a salire di carico, con la stessa
    regola che l'app mostra durante l'allenamento (`progression.suggest`):
    tutte le serie dell'ultima volta al massimo del range, con il RIR previsto."""
    piano = training_schedule.current_plan(db, profile.id)
    if piano is None:
        return []
    note: list[Notification] = []
    for riga in piano.exercises:
        storia = training_log.exercise_history(
            db, profile.id, riga.exercise_id, since=today - dt.timedelta(days=21), limit=1
        )
        if not storia:
            continue
        consiglio = progression.suggest(
            storia[0].sets,
            reps_min=riga.target_reps_min,
            reps_max=riga.target_reps_max,
            target_rir=riga.target_rir,
            is_compound=riga.exercise.is_compound,
        )
        if consiglio is None or consiglio.kind != "carico" or consiglio.weight_kg is None:
            continue
        nome = riga.exercise.name_it or riga.exercise.name
        note.append(
            Notification(
                key=f"carichi:{riga.exercise_id}:{_settimana(today)}",
                title="Sei pronto a salire",
                body=f"{nome}: prova {_kg(consiglio.weight_kg)} kg. {consiglio.reason}",
                section="scheda",
                category="training",
                priority=2,
                hours=(17, 21),
            )
        )
    return note[:1]  # una sola per volta: l'esercizio più avanti è già un segnale


def _scheda_vecchia(db: Session, profile: UserProfile, today: dt.date) -> list[Notification]:
    # Solo la scheda in uso: di quella che si tiene da parte non serve parlare.
    piano_in_uso = training_schedule.current_plan(db, profile.id)
    piani = [piano_in_uso] if piano_in_uso is not None else []
    note = []
    for piano in piani:
        inizio = piano.started_at or (piano.created_at.date() if piano.created_at else None)
        if inizio is None:
            continue
        settimane = (today - inizio).days // 7
        if settimane < PLAN_AGE_WEEKS:
            continue
        # Se il punto l'hai appena fatto ("Come sta andando?"), la scheda è già
        # stata valutata: niente notifica che chiede di rifarlo.
        recente = db.scalar(
            select(func.count(TrainingFeedback.id)).where(
                TrainingFeedback.workout_plan_id == piano.id,
                TrainingFeedback.date >= today - dt.timedelta(weeks=4),
            )
        )
        if recente:
            continue
        note.append(
            Notification(
                key=f"scheda-vecchia:{piano.id}",
                title="Facciamo il punto sulla scheda?",
                body=(
                    f"Sono {settimane} settimane con {piano.name}. Dimmi da «Come sta "
                    "andando?» come vanno progressi e recupero: ti dico se mantenere, "
                    "aumentare o ridurre il volume, o se è il momento di cambiare esercizi."
                ),
                section="scheda",
                category="training",
                priority=4,
                hours=(17, 21),
            )
        )
    return note


# --- Integratori -----------------------------------------------------------


def supplement_text(declarations, *, after_workout: bool) -> str:
    """L'elenco di cosa prendere e un consiglio solo per ciò che è dichiarato.

    Le proteine dopo l'allenamento: "da subito fino a 2 ore dopo"
    (`nutrient_timing.md`), non entro mezz'ora come diceva il testo di prima.
    """
    elenco = ", ".join(_nome(d) for d in declarations)
    tipi = {d.kind for d in declarations}
    consigli = []
    if "protein_powder" in tipi:
        consigli.append(
            "le proteine entro un paio d'ore dalla fine, quando ti è comodo"
            if after_workout
            else "le proteine vanno bene a merenda o con un pasto"
        )
    if "creatine" in tipi:
        consigli.append("la creatina con un pasto, a qualsiasi ora")
    frase = f" {'; '.join(consigli).capitalize()}." if consigli else ""
    inizio = "Dopo l'allenamento" if after_workout else "Giorno di riposo"
    return f"{inizio}: {elenco}.{frase}"


def _already_sent_today(db: Session, user_id: int | None, keys: list[str], today: dt.date) -> bool:
    if user_id is None:
        return False
    return db.scalar(
        select(func.count(NotificationLog.id)).where(
            NotificationLog.user_id == user_id,
            NotificationLog.sent_on == today,
            NotificationLog.key.in_(keys),
        )
    ) > 0


def supplements_already_pushed(db: Session, profile: UserProfile, today: dt.date) -> bool:
    """Oggi gli integratori sono già stati ricordati (a fine allenamento o a
    metà giornata): non si ripetono, neanche nel promemoria della sera."""
    return _already_sent_today(
        db, profile.user_id, [f"integratori:{today}", f"post-allenamento:{profile.id}:{today}"], today
    )


def _supplements(db: Session, profile: UserProfile, today: dt.date, allenamento_oggi: bool) -> list[Notification]:
    da_prendere = supplement_intake.pending(db, profile, today=today)
    note: list[Notification] = []
    if da_prendere and not supplements_already_pushed(db, profile, today):
        corpo = supplement_text([d for d, _ in da_prendere], after_workout=allenamento_oggi)
        note.append(
            Notification(
                key=f"integratori:{today}",
                title="Integratori di oggi",
                body=corpo,
                section="integratori",
                category="supplements",
                priority=3,
                hours=(13, 14) if not allenamento_oggi else (19, 21),
            )
        )
    note.extend(_tappe(db, profile, today))
    return note


def _nome(declaration) -> str:
    from app.services.push_notifications import SUPPLEMENT_NAMES

    return declaration.product_name or SUPPLEMENT_NAMES.get(declaration.kind, declaration.kind)


def _tappe(db: Session, profile: UserProfile, today: dt.date) -> list[Notification]:
    """Traguardi raggiunti oggi: per la creatina il giorno in cui le scorte
    sono piene e si passa al mantenimento."""
    note = []
    for dichiarato in supplement_intake.active_declarations(db, profile):
        riepilogo = supplement_intake.summarize(db, dichiarato, today=today)
        traguardo = riepilogo.milestone
        if traguardo is None or riepilogo.days_taken < traguardo.days:
            continue
        note.append(
            Notification(
                key=f"tappa:{dichiarato.id}:{traguardo.days}",
                title=traguardo.reached_label,
                body=f"{_nome(dichiarato)}: {traguardo.reached_note}",
                section="integratori",
                category="supplements",
                priority=3,
                hours=(10, 21),
            )
        )
    return note


# --- Diario e proteine -----------------------------------------------------


def _diary(db: Session, profile: UserProfile, today: dt.date) -> list[Notification]:
    ultimo = db.scalar(
        select(func.max(MealLog.date)).where(
            MealLog.profile_id == profile.id, MealLog.is_planned.is_(False)
        )
    )
    note: list[Notification] = []
    if ultimo is None:
        return note
    fermo_da = (today - ultimo).days
    if fermo_da >= DIARY_SILENT_DAYS:
        note.append(
            Notification(
                key=f"diario-fermo:{today}",
                title="Il diario ti aspetta",
                body=(
                    f"Sono {fermo_da} giorni che non segni cosa mangi. Bastano i pasti "
                    "principali: senza, calorie e proteine restano una stima."
                ),
                section="diario",
                category="diary",
                priority=5,
                hours=(20, 21),
            )
        )
        return note

    if ultimo != today:
        return note
    totali = food_diary.daily_totals(db, profile, date=today)
    proteine = totali.protein_g + supplements.protein_from_supplements(db, profile, today)
    target = nutrition_targets.compute_targets(profile)
    peso = profile.weight_kg or 0
    if peso and proteine / peso >= PROTEIN_HIGH_G_PER_KG:
        note.append(
            Notification(
                key=f"proteine-alte:{today}",
                title="Proteine oltre il necessario",
                body=(
                    f"Oggi sei a {proteine:.0f} g, cioè {proteine / peso:.1f} g per chilo. "
                    "Le fonti indicano fino a 2,4 g/kg: sopra non servono ai muscoli, "
                    "e sono calorie che potresti usare altrove."
                ),
                section="diario",
                category="diary",
                priority=6,
                hours=(21, 22),
            )
        )
    elif target.protein_g and proteine < target.protein_g * PROTEIN_LOW_RATIO and _dinner_logged(db, profile, today):
        # Solo a cena segnata: alle 19 mancano quasi sempre le proteine della cena.
        mancano = target.protein_g - proteine
        note.append(
            Notification(
                key=f"proteine-basse:{today}",
                title=f"Ti mancano {mancano:.0f} g di proteine",
                body="Anche con la cena sei sotto: uno spuntino proteico chiude il conto. Ti cerco cosa?",
                section="ricette",
                category="recipes",
                priority=6,
                hours=(20, 22),
            )
        )
    return note


# --- Ricette ---------------------------------------------------------------


def _recipes(db: Session, profile: UserProfile, today: dt.date, meal_prep: bool) -> list[Notification]:
    note: list[Notification] = []
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=SAVED_RECIPE_DAYS)
    salvate = db.scalars(
        select(SavedRecipe)
        .where(SavedRecipe.profile_id == profile.id, SavedRecipe.created_at <= limite)
        .order_by(SavedRecipe.created_at)
    ).all()
    for salvata in salvate:
        # Una sola volta per ricetta: la chiave contiene il suo id.
        nome = (salvata.data or {}).get("name") or "una ricetta"
        note.append(
            Notification(
                key=f"ricetta-salvata:{salvata.id}",
                title="L'avevi salvata",
                body=f"{nome} è fra le tue ricette da dieci giorni. La provi stasera?",
                section="ricette",
                category="recipes",
                priority=7,
                hours=(17, 19),
            )
        )
        break  # una alla volta

    if meal_prep and today.weekday() == 6:
        note.append(
            Notification(
                key=f"meal-prep:{_settimana(today)}",
                title="Prepariamo la settimana",
                body="Ho due ricette adatte al tuo obiettivo da cucinare in anticipo.",
                section="ricette",
                category="recipes",
                priority=8,
                hours=(10, 12),
            )
        )
    return note


# --- Progressi -------------------------------------------------------------


def _progress(db: Session, profile: UserProfile, today: dt.date) -> list[Notification]:
    """Riepilogo del lunedì: come è andata la settimana appena chiusa."""
    if today.weekday() != 0:
        return []
    r = weekly_summary.build(db, profile, today=today)
    if not r.has_data:
        return []
    pezzi = []
    if r.sessions_planned:
        pezzi.append(f"{r.sessions_done} allenamenti su {r.sessions_planned}")
    elif r.sessions_done:
        pezzi.append(f"{r.sessions_done} allenamenti")
    delta = r.weight_delta_kg
    if delta is not None:
        verso = "in su" if delta > 0 else "in giù"
        pezzi.append(f"peso {abs(delta):.1f} kg {verso}")
    if r.protein_average_g and r.protein_target_g:
        pezzi.append(f"proteine {r.protein_average_g:.0f} g al giorno")
    if not pezzi:
        return []
    bene = r.sessions_planned is not None and r.sessions_done >= r.sessions_planned
    return [
        Notification(
            key=f"riepilogo:{_settimana(today)}",
            title="Continua così" if bene else "Settimana chiusa",
            body=f"La settimana scorsa: {', '.join(pezzi)}. Apri i progressi per il quadro completo.",
            section="progressi",
            category="progress",
            priority=5,
            hours=(9, 11),
        )
    ]


# --- Riepilogo della sera --------------------------------------------------


def evening_summary(db: Session, profile: UserProfile, today: dt.date, hour: int) -> list[Notification]:
    """Il promemoria di quello che oggi non è ancora segnato."""
    from app.services.push_notifications import build_message

    promemoria = daily_reminders.build(db, profile, today=today)
    if supplements_already_pushed(db, profile, today):
        promemoria.supplements = []
    messaggio = build_message(promemoria, name=profile.display_name)
    if messaggio is None:
        return []
    return [
        Notification(
            key=f"promemoria:{profile.id}:{today}",
            title=messaggio.title,
            body=messaggio.body,
            section=messaggio.section,
            category="evening",
            priority=9,
            hours=(hour, 22),
        )
    ]


def build(
    db: Session,
    user: User,
    *,
    today: dt.date,
    fuso: dt.tzinfo,
    settings: NotificationSettings,
    evening_hour: int,
) -> list[Notification]:
    """Tutte le notifiche che oggi avrebbero senso, dalla più importante."""
    note: list[Notification] = []
    for profile in db.scalars(select(UserProfile).where(UserProfile.user_id == user.id)):
        allenamento_oggi = bool(daily_reminders.workouts_due(db, profile, today))
        ora_palestra = gym_hour(db, profile, fuso=fuso, override=settings.gym_hour)
        if settings.training:
            note += _training(db, profile, today, ora_palestra)
        if settings.supplements:
            note += _supplements(db, profile, today, allenamento_oggi)
        if settings.diary:
            note += _diary(db, profile, today)
        if settings.recipes:
            note += _recipes(db, profile, today, settings.meal_prep)
        if settings.progress:
            note += _progress(db, profile, today)
        note += evening_summary(db, profile, today, evening_hour)
    note.sort(key=lambda n: n.priority)
    return note


def _dinner_logged(db: Session, profile: UserProfile, today: dt.date) -> bool:
    return bool(
        db.scalar(
            select(func.count(MealLog.id)).where(
                MealLog.profile_id == profile.id,
                MealLog.date == today,
                MealLog.meal_type == "dinner",
                MealLog.is_planned.is_(False),
            )
        )
    )
