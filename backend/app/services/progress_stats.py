"""Statistiche della pagina Progressi: volume, massimale, costanza, peso, dieta.

Rispetto al report testuale (`progress_report.py`), che dà un verdetto sul
periodo, qui servono **serie di numeri settimana per settimana**: sono i dati
dei grafici. Le scelte che cambiano cosa l'utente legge:

  1. **La settimana è lunedì-domenica**, come nel riepilogo settimanale. Una
     finestra mobile di 7 giorni farebbe ballare i confronti a ogni ricarica
     della pagina, e il volume di allenamento si programma per settimana
     di calendario.

  2. **Il volume si confronta al range del livello dell'utente**, quello che
     il generatore di schede usa per costruirle (`weekly_sets_range`): dire
     "12 serie a settimana" senza il riferimento non aiuta a decidere nulla.
     Il confronto è sulla media del periodo, non sull'ultima settimana, che
     da sola può essere una settimana di scarico o una saltata.

  3. **Il peso si legge a media mobile**, con la stessa finestra e la stessa
     cautela di `progress_report`: le oscillazioni giornaliere di 1-2 kg da
     acqua e glicogeno coprono il segnale.

  4. **Quando la knowledge base non dà un numero, non se ne inventa uno.** Il
     ritmo atteso di variazione del peso esiste nelle fonti per il
     dimagrimento (`diets_body_composition.md`) e non per l'aumento di massa:
     in quel caso la risposta lo dichiara invece di proporre un range
     arbitrario.

Nessun dato dipende da servizi esterni o dall'LLM: solo ciò che l'utente ha
registrato e le costanti della knowledge base.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from statistics import mean

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Exercise,
    Goal,
    MealItem,
    MealLog,
    SessionSet,
    UserProfile,
    WeightLog,
    WorkoutPlan,
    WorkoutSession,
)
from app.services import nutrition_targets, supplements
from app.services.progress_report import (
    WEIGHT_SMOOTHING_DAYS,
    WeightTrend,
    _moving_average,
    estimate_1rm,
)
from app.services.weekly_summary import MIN_WEIGH_INS, PROTEIN_OK
from app.services.workout_generator import weekly_sets_range

# `calorie_and_1rm_formulas.md`: la formula di Epley resta attendibile entro
# le ~10-12 ripetizioni. Sopra questa soglia l'andamento del massimale va
# letto con più margine, e la risposta lo segnala.
HIGH_REP_THRESHOLD = 10

# `diets_body_composition.md`: per soggetti magri e allenati si consiglia un
# calo dello 0,5-1,0% del peso a settimana (Helms); Garthe mostra che lo 0,7%
# preserva la massa magra meglio dell'1,4%. È l'unico ritmo di variazione del
# peso che le fonti danno in forma numerica.
FAT_LOSS_WEEKLY_PCT = (0.005, 0.010)

# Le calorie si considerano centrate entro ±10% del target: sotto quella
# soglia la differenza è dentro l'errore di pesata e di etichetta degli
# alimenti, non una scelta alimentare diversa.
KCAL_TOLERANCE = 0.10

# Meno di due settimane di pesate non bastano a stimare un ritmo: la
# differenza misurata sarebbe soprattutto oscillazione giornaliera.
MIN_DAYS_FOR_RATE = 14


def week_start(day: dt.date) -> dt.date:
    """Lunedì della settimana che contiene `day`."""
    return day - dt.timedelta(days=day.weekday())


def _week_starts(weeks: int, today: dt.date) -> list[dt.date]:
    """I lunedì delle ultime `weeks` settimane, dalla più vecchia, corrente
    compresa."""
    ultimo = week_start(today)
    return [ultimo - dt.timedelta(weeks=n) for n in reversed(range(weeks))]


def _kg(valore: float) -> str:
    """Chili come si scrivono in italiano: 0,07 e non 0.07."""
    return f"{valore:.2f}".replace(".", ",")


# --- Volume settimanale per gruppo muscolare ---------------------------------


@dataclass
class MuscleVolume:
    muscle: str
    sets_per_week: list[int]
    range_min: int
    range_max: int

    @property
    def average(self) -> float:
        return mean(self.sets_per_week) if self.sets_per_week else 0.0

    # La settimana in corso è ancora a metà: contarla farebbe apparire
    # "sotto il range" chiunque guardi la pagina di martedì.
    complete_weeks: int = 0

    @property
    def last(self) -> int:
        """Serie dell'ultima settimana **conclusa**."""
        conclusi = self.sets_per_week[: self.complete_weeks] or self.sets_per_week
        return conclusi[-1] if conclusi else 0

    @property
    def status(self) -> str:
        """Posizione della media rispetto al range del livello dell'utente."""
        if self.average < self.range_min:
            return "sotto"
        if self.average > self.range_max:
            return "sopra"
        return "dentro"


@dataclass
class VolumeStats:
    weeks: list[dt.date]
    muscles: list[MuscleVolume] = field(default_factory=list)


def volume_by_muscle(
    db: Session, profile: UserProfile, *, weeks: int = 8, today: dt.date | None = None
) -> VolumeStats:
    """Serie svolte per gruppo muscolare, settimana per settimana.

    Si contano le serie **realmente registrate**, non quelle previste dalla
    scheda: è la differenza fra il volume programmato e quello allenato, ed è
    il secondo a produrre gli adattamenti. Il muscolo è quello primario
    dell'esercizio, come nel generatore di schede: il metodo "frazionario"
    di `training_volume.md` (mezza serie ai secondari) alzerebbe il conteggio
    rispetto ai range con cui la scheda è stata costruita.
    """
    today = today or dt.date.today()
    lunedi = _week_starts(weeks, today)
    inizio = lunedi[0]
    indice = {giorno: n for n, giorno in enumerate(lunedi)}

    # Una sola query aggregata: il conteggio per giorno e muscolo arriva da
    # SQL, il raggruppamento per settimana si fa qui perché le funzioni di
    # data cambiano fra SQLite (test) e Postgres (produzione).
    righe = db.execute(
        select(
            WorkoutSession.date,
            Exercise.primary_muscle,
            func.count(SessionSet.id),
        )
        .join(SessionSet, SessionSet.workout_session_id == WorkoutSession.id)
        .join(Exercise, Exercise.id == SessionSet.exercise_id)
        .where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.date >= inizio,
            WorkoutSession.date <= today,
            Exercise.primary_muscle.is_not(None),
        )
        .group_by(WorkoutSession.date, Exercise.primary_muscle)
    ).all()

    per_muscolo: dict[str, list[int]] = {}
    for data, muscolo, serie in righe:
        settimana = indice.get(week_start(data))
        if settimana is None:
            continue
        conteggi = per_muscolo.setdefault(muscolo, [0] * len(lunedi))
        conteggi[settimana] += serie

    minimo, _, massimo = weekly_sets_range(profile)
    # Settimane già chiuse: l'ultima lo è solo se oggi è dopo la domenica.
    concluse = len(lunedi) - (1 if lunedi[-1] + dt.timedelta(days=6) >= today else 0)
    muscoli = [
        MuscleVolume(
            muscle=muscolo,
            sets_per_week=conteggi,
            range_min=minimo,
            range_max=massimo,
            complete_weeks=concluse,
        )
        for muscolo, conteggi in per_muscolo.items()
    ]
    # Dal volume medio più alto: in cima la pagina mostra i muscoli su cui si
    # sta lavorando di più, non il primo in ordine alfabetico.
    muscoli.sort(key=lambda m: (-m.average, m.muscle))
    return VolumeStats(weeks=lunedi, muscles=muscoli)


# --- Massimale stimato di un esercizio ---------------------------------------


@dataclass
class OneRmPoint:
    date: dt.date
    one_rm: float
    kg: float
    reps: int


@dataclass
class OneRmTrend:
    exercise_id: int
    exercise_name: str
    points: list[OneRmPoint]
    high_rep_estimate: bool

    @property
    def delta_pct(self) -> float:
        """Variazione fra il primo e l'ultimo punto: con un punto solo non
        esiste un confronto, quindi vale 0."""
        if len(self.points) < 2 or not self.points[0].one_rm:
            return 0.0
        return (self.points[-1].one_rm - self.points[0].one_rm) / self.points[0].one_rm


def one_rm_trend(
    db: Session,
    profile: UserProfile,
    exercise_id: int,
    *,
    weeks: int = 26,
    today: dt.date | None = None,
) -> OneRmTrend | None:
    """Andamento del massimale stimato, un punto per sessione.

    Di ogni sessione si tiene la serie con il massimale stimato più alto e
    non il carico più alto: 65 kg x 3 può valere meno di 60 kg x 8, e le
    sessioni vanno confrontate con la stessa unità di misura.

    Restituisce `None` se il profilo non ha mai registrato una serie su
    questo esercizio: il grafico non esiste, non è vuoto.
    """
    today = today or dt.date.today()
    inizio = today - dt.timedelta(weeks=weeks)

    righe = db.execute(
        select(WorkoutSession.date, SessionSet.weight_kg, SessionSet.reps, Exercise)
        .join(SessionSet, SessionSet.workout_session_id == WorkoutSession.id)
        .join(Exercise, Exercise.id == SessionSet.exercise_id)
        .where(
            WorkoutSession.profile_id == profile.id,
            SessionSet.exercise_id == exercise_id,
        )
        .order_by(WorkoutSession.date)
    ).all()

    if not righe:
        return None

    esercizio = righe[0][3]
    migliori: dict[dt.date, tuple[float, float, int]] = {}
    for data, kg, reps, _ in righe:
        if data < inizio or data > today:
            continue
        stimato = estimate_1rm(kg, reps)
        if data not in migliori or stimato > migliori[data][0]:
            migliori[data] = (stimato, kg, reps)

    punti = [
        OneRmPoint(date=data, one_rm=round(stimato, 1), kg=kg, reps=reps)
        for data, (stimato, kg, reps) in sorted(migliori.items())
    ]
    return OneRmTrend(
        exercise_id=exercise_id,
        exercise_name=esercizio.name_it or esercizio.name,
        points=punti,
        high_rep_estimate=any(p.reps > HIGH_REP_THRESHOLD for p in punti),
    )


# --- Costanza rispetto alla scheda -------------------------------------------


@dataclass
class ConsistencyWeek:
    start: dt.date
    done: int
    planned: int

    @property
    def is_hit(self) -> bool:
        return self.planned > 0 and self.done >= self.planned


@dataclass
class ConsistencyStats:
    weeks: list[ConsistencyWeek]
    streak_weeks: int
    best_streak_weeks: int

    @property
    def done_total(self) -> int:
        return sum(w.done for w in self.weeks)

    @property
    def planned_total(self) -> int:
        return sum(w.planned for w in self.weeks)


def _planned_days(plans: list[WorkoutPlan], lunedi: dt.date) -> int:
    """Giorni di allenamento previsti nella settimana che inizia il `lunedi`.

    Con più schede attive insieme (es. una full body e una push/pull/gambe)
    si prende il **massimo**, non la somma: l'utente non fa due programmi in
    parallelo, ne segue uno per volta, e sommarli renderebbe la costanza
    irraggiungibile per costruzione. I giorni prima dell'inizio o dopo la
    chiusura di una scheda non si contano: una scheda creata di giovedì non
    prevedeva nulla per il lunedì precedente.
    """
    previsti = 0
    for piano in plans:
        giorni = [
            lunedi + dt.timedelta(days=g)
            for g in piano.training_weekdays
            if piano.started_at <= lunedi + dt.timedelta(days=g)
            and (piano.ended_at is None or lunedi + dt.timedelta(days=g) <= piano.ended_at)
        ]
        previsti = max(previsti, len(giorni))
    return previsti


def _streaks(weeks: list[ConsistencyWeek], today: dt.date) -> tuple[int, int]:
    """Serie attuale e serie migliore, in settimane.

    La settimana in corso non è ancora finita: se l'obiettivo non è (ancora)
    raggiunto viene ignorata invece di spezzare la serie, altrimenti ogni
    lunedì mattina il conteggio ripartirebbe da zero.
    """
    in_corso = week_start(today)

    attuale = 0
    for settimana in reversed(weeks):
        if settimana.is_hit:
            attuale += 1
        elif settimana.start == in_corso:
            continue
        else:
            break

    migliore = corrente = 0
    for settimana in weeks:
        if settimana.is_hit:
            corrente += 1
            migliore = max(migliore, corrente)
        elif settimana.start == in_corso:
            continue
        else:
            corrente = 0
    return attuale, migliore


def consistency(
    db: Session, profile: UserProfile, *, weeks: int = 12, today: dt.date | None = None
) -> ConsistencyStats:
    """Allenamenti svolti rispetto a quelli previsti, settimana per settimana.

    Conta come svolto un giorno in cui la sessione è stata **avviata oppure
    ha almeno una serie registrata**: chi usa il cronometro senza segnare i
    carichi si è comunque allenato, e una sessione creata e mai iniziata no.
    Si contano i giorni distinti e non le sessioni, perché il confronto è con
    i giorni di allenamento della scheda.
    """
    today = today or dt.date.today()
    lunedi = _week_starts(weeks, today)
    inizio = lunedi[0]
    indice = {giorno: n for n, giorno in enumerate(lunedi)}

    date_svolte = db.scalars(
        select(WorkoutSession.date)
        .where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.date >= inizio,
            WorkoutSession.date <= today,
            or_(WorkoutSession.started_at.is_not(None), WorkoutSession.sets.any()),
        )
        .distinct()
    ).all()

    svolti = [0] * len(lunedi)
    for data in date_svolte:
        posizione = indice.get(week_start(data))
        if posizione is not None:
            svolti[posizione] += 1

    # Anche le schede archiviate nel periodo: quando erano attive prevedevano
    # allenamenti, e ignorarle farebbe risultare "senza obiettivo" le
    # settimane precedenti all'ultima scheda.
    fine = lunedi[-1] + dt.timedelta(days=6)
    piani = list(
        db.scalars(
            select(WorkoutPlan).where(
                WorkoutPlan.profile_id == profile.id,
                WorkoutPlan.started_at <= fine,
                or_(WorkoutPlan.ended_at.is_(None), WorkoutPlan.ended_at >= inizio),
            )
        ).all()
    )

    settimane = [
        ConsistencyWeek(start=giorno, done=svolti[n], planned=_planned_days(piani, giorno))
        for n, giorno in enumerate(lunedi)
    ]
    attuale, migliore = _streaks(settimane, today)
    return ConsistencyStats(
        weeks=settimane, streak_weeks=attuale, best_streak_weeks=migliore
    )


# --- Andamento del peso ------------------------------------------------------


@dataclass
class WeightPoint:
    date: dt.date
    weight_kg: float
    average_kg: float


@dataclass
class WeightTrendStats:
    points: list[WeightPoint]
    weekly_rate_kg: float | None
    expected_min: float | None
    expected_max: float | None
    verdict: str
    note: str


def _expected_weekly_range(profile: UserProfile, weight_kg: float) -> tuple[float, float] | None:
    """Ritmo settimanale atteso in kg, dalle fonti.

    Solo il dimagrimento ha un numero: `diets_body_composition.md` riporta
    0,5-1,0% del peso a settimana. Per l'aumento di massa le fonti ragionano
    in surplus calorico e riportano esempi di singoli studi, non un ritmo
    consigliato: restituire `None` è l'unica risposta onesta.
    """
    if profile.goal != Goal.FAT_LOSS or not weight_kg:
        return None
    minimo, massimo = FAT_LOSS_WEEKLY_PCT
    # Un calo: il più veloce è il più negativo, e resta il limite inferiore.
    return -weight_kg * massimo, -weight_kg * minimo


def _moving_series(logs: list[WeightLog], since: dt.date) -> list[WeightPoint]:
    """Media mobile a 7 giorni, un punto per pesata da `since` in poi.

    Le pesate della settimana precedente a `since` vengono usate nel calcolo
    ma non mostrate: senza, i primi punti del grafico avrebbero una media
    costruita su meno giorni e sembrerebbero più mossi del resto.
    """
    punti: list[WeightPoint] = []
    for n, log in enumerate(logs):
        finestra = [
            p.weight_kg
            for p in logs[: n + 1]
            if (log.date - p.date).days < WEIGHT_SMOOTHING_DAYS
        ]
        if log.date >= since:
            punti.append(
                WeightPoint(
                    date=log.date,
                    weight_kg=log.weight_kg,
                    average_kg=round(mean(finestra), 1),
                )
            )
    return punti


def weight_trend(
    db: Session, profile: UserProfile, *, weeks: int = 12, today: dt.date | None = None
) -> WeightTrendStats:
    """Peso corporeo a media mobile e confronto con il ritmo atteso."""
    today = today or dt.date.today()
    inizio = today - dt.timedelta(weeks=weeks)

    logs = db.scalars(
        select(WeightLog)
        .where(
            WeightLog.profile_id == profile.id,
            WeightLog.date >= inizio - dt.timedelta(days=WEIGHT_SMOOTHING_DAYS),
            WeightLog.date <= today,
        )
        .order_by(WeightLog.date)
    ).all()

    nel_periodo = [l for l in logs if l.date >= inizio]
    punti = _moving_series(list(logs), inizio)

    # Stesso calcolo del report: medie della prima e dell'ultima finestra,
    # rapportate ai giorni coperti.
    prima, ultima, affidabile = _moving_average(nel_periodo)
    giorni = (
        (nel_periodo[-1].date - nel_periodo[0].date).days if nel_periodo else 0
    )
    tendenza = WeightTrend(
        first_average=prima,
        last_average=ultima,
        measurements=len(nel_periodo),
        days_covered=giorni,
        smoothed=affidabile,
    )
    ritmo = tendenza.weekly_rate_kg

    peso_attuale = ultima if ultima is not None else profile.weight_kg
    atteso = _expected_weekly_range(profile, peso_attuale or 0.0)
    minimo = round(atteso[0], 2) if atteso else None
    massimo = round(atteso[1], 2) if atteso else None

    if len(nel_periodo) < MIN_WEIGH_INS or giorni < MIN_DAYS_FOR_RATE or ritmo is None:
        return WeightTrendStats(
            points=punti,
            weekly_rate_kg=round(ritmo, 2) if ritmo is not None else None,
            expected_min=minimo,
            expected_max=massimo,
            verdict="pochi_dati",
            note=(
                "Servono almeno due settimane di pesate per leggere una "
                "tendenza: sotto quella durata la differenza che vedresti "
                "sarebbe soprattutto acqua e glicogeno. Pesarsi 3-4 volte a "
                "settimana rende il grafico leggibile in fretta."
            ),
        )

    ritmo = round(ritmo, 2)
    verdetto, nota = _weight_verdict(ritmo, atteso)
    if not tendenza.smoothed:
        nota += (
            " Le pesate nel periodo sono poche: il ritmo è indicativo, non un "
            "dato stabile."
        )
    return WeightTrendStats(
        points=punti,
        weekly_rate_kg=ritmo,
        expected_min=minimo,
        expected_max=massimo,
        verdict=verdetto,
        note=nota,
    )


def _weight_verdict(rate: float, expected: tuple[float, float] | None) -> tuple[str, str]:
    """Verdetto e frase da mostrare.

    Senza un ritmo di riferimento nelle fonti il verdetto è
    `non_valutabile`: il grafico resta utile, ma nessuno può dire se quei
    grammi a settimana siano troppi o troppo pochi.
    """
    verso = "in calo" if rate < 0 else "in aumento" if rate > 0 else "stabile"
    if expected is None:
        return (
            "non_valutabile",
            f"Il peso è {verso} di {_kg(abs(rate))} kg a settimana. Per il tuo "
            "obiettivo le fonti della knowledge base non indicano un ritmo "
            "consigliato in kg a settimana — parlano di surplus calorico e di "
            "casi singoli — quindi non invento un range: guarda la direzione e "
            "confrontala con i carichi e con la circonferenza della vita.",
        )

    minimo, massimo = expected
    sul_calo = massimo <= 0
    if rate < minimo:
        veloce = sul_calo
    elif rate > massimo:
        veloce = not sul_calo
    else:
        nota = (
            f"Stai perdendo {_kg(abs(rate))} kg a settimana, dentro lo 0,5-1,0% "
            "del peso a settimana che le fonti indicano per preservare la massa "
            "magra."
            if sul_calo
            else f"Ritmo di {_kg(rate)} kg a settimana, dentro il range atteso."
        )
        return "in_linea", nota

    if veloce:
        return (
            "troppo_veloce",
            f"Stai perdendo {_kg(abs(rate))} kg a settimana, più dello 0,5-1,0% "
            "del peso a settimana indicato dalle fonti. Un calo più rapido "
            "costa massa magra: alzare un po' le calorie protegge i risultati "
            "dell'allenamento.",
        )
    return (
        "troppo_lento",
        f"Il peso si muove di {_kg(rate)} kg a settimana, meno dello 0,5-1,0% "
        "del peso a settimana atteso per il tuo obiettivo. Prima di tagliare "
        "le calorie, verifica quanto stai davvero mangiando nel diario: è la "
        "spiegazione più frequente.",
    )


# --- Dieta: medie settimanali rispetto ai target -----------------------------


@dataclass
class NutritionWeek:
    start: dt.date
    kcal_avg: float
    protein_avg_g: float
    days_logged: int
    days_in_kcal_target: int
    days_in_protein_target: int


@dataclass
class NutritionStats:
    weeks: list[NutritionWeek]
    kcal_target: float | None
    protein_target_g: float | None


def _logged_days(
    db: Session, profile: UserProfile, since: dt.date, until: dt.date
) -> dict[dt.date, tuple[float, float]]:
    """Calorie e proteine per giorno, dai soli pasti consumati.

    Due query aggregate invece di una chiamata a `daily_totals` per giorno:
    su otto settimane sarebbero cinquantasei query più i pasti caricati uno
    a uno. La somma segue la stessa regola del diario — alimenti pesati più
    i pasti liberi con i macro dichiarati a mano.
    """
    comuni = (
        MealLog.profile_id == profile.id,
        MealLog.date >= since,
        MealLog.date <= until,
        MealLog.is_planned.is_(False),
    )

    totali: dict[dt.date, tuple[float, float]] = {}

    pesati = db.execute(
        select(
            MealLog.date,
            func.sum(MealItem.kcal),
            func.sum(func.coalesce(MealItem.protein_g, 0.0)),
        )
        .join(MealItem, MealItem.meal_log_id == MealLog.id)
        .where(*comuni)
        .group_by(MealLog.date)
    ).all()
    for data, kcal, proteine in pesati:
        totali[data] = (kcal or 0.0, proteine or 0.0)

    liberi = db.execute(
        select(
            MealLog.date,
            func.sum(MealLog.kcal * func.coalesce(MealLog.servings, 1.0)),
            func.sum(
                func.coalesce(MealLog.protein_g, 0.0)
                * func.coalesce(MealLog.servings, 1.0)
            ),
        )
        .where(*comuni, MealLog.kcal.is_not(None), ~MealLog.items.any())
        .group_by(MealLog.date)
    ).all()
    for data, kcal, proteine in liberi:
        kcal_prec, prot_prec = totali.get(data, (0.0, 0.0))
        totali[data] = (kcal_prec + (kcal or 0.0), prot_prec + (proteine or 0.0))

    return totali


def nutrition_weeks(
    db: Session, profile: UserProfile, *, weeks: int = 8, today: dt.date | None = None
) -> NutritionStats:
    """Medie settimanali del diario rispetto ai target.

    Le medie si calcolano **solo sui giorni registrati**: includere i giorni
    vuoti come zero kcal farebbe sembrare in deficit chi semplicemente non ha
    aperto il diario. Le proteine degli integratori dichiarati si sommano al
    totale come in `GET /diary`, perché il target è l'apporto proteico della
    giornata e non il cibo solido.
    """
    today = today or dt.date.today()
    lunedi = _week_starts(weeks, today)
    inizio = lunedi[0]
    indice = {giorno: n for n, giorno in enumerate(lunedi)}

    try:
        targets = nutrition_targets.compute_targets(
            profile, training_days=profile.training_days_per_week
        )
        kcal_target: float | None = float(targets.target_kcal)
        protein_target: float | None = float(targets.protein_g)
    except ValueError:
        # Senza peso, altezza o data di nascita il TDEE non è calcolabile: le
        # medie restano leggibili, il confronto no.
        kcal_target = protein_target = None

    giornaliero = _logged_days(db, profile, inizio, today)
    if not giornaliero:
        return NutritionStats(
            weeks=[], kcal_target=kcal_target, protein_target_g=protein_target
        )

    # Dose dichiarata oggi, applicata ai giorni registrati: è la stessa
    # approssimazione del diario, che non tiene uno storico delle assunzioni
    # di proteine in polvere.
    proteine_integratori = supplements.protein_from_supplements(db, profile)

    raccolta: list[list[tuple[float, float]]] = [[] for _ in lunedi]
    for data, (kcal, proteine) in giornaliero.items():
        posizione = indice.get(week_start(data))
        if posizione is None or kcal <= 0:
            continue
        raccolta[posizione].append(
            (
                kcal + proteine_integratori * nutrition_targets.KCAL_PER_G_PROTEIN,
                proteine + proteine_integratori,
            )
        )

    settimane: list[NutritionWeek] = []
    for n, giorno in enumerate(lunedi):
        giorni = raccolta[n]
        settimane.append(
            NutritionWeek(
                start=giorno,
                kcal_avg=round(mean(k for k, _ in giorni)) if giorni else 0.0,
                protein_avg_g=round(mean(p for _, p in giorni)) if giorni else 0.0,
                days_logged=len(giorni),
                days_in_kcal_target=sum(
                    1
                    for k, _ in giorni
                    if kcal_target and abs(k - kcal_target) <= kcal_target * KCAL_TOLERANCE
                ),
                days_in_protein_target=sum(
                    1 for _, p in giorni if protein_target and p >= protein_target * PROTEIN_OK
                ),
            )
        )

    return NutritionStats(
        weeks=settimane, kcal_target=kcal_target, protein_target_g=protein_target
    )
