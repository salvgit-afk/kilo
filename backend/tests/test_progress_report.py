"""Test dei report di progressione.

Il rischio specifico di questo modulo non è il crash: è **far leggere come
segnale ciò che è rumore**. I test verificano soprattutto che le
avvertenze metodologiche compaiano quando servono.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import (
    ActivityLevel,
    Exercise,
    ExperienceLevel,
    Goal,
    SessionSet,
    Sex,
    UserProfile,
    ProgressPerception,
    RecoveryQuality,
    TrainingFeedback,
    WeightLog,
    WorkoutPlan,
    WorkoutSession,
)
from app.services import progress_report as pr

OGGI = dt.date.today()


@pytest.fixture
def percorso(db):
    profilo = UserProfile(
        display_name="test",
        birth_date=dt.date(1996, 5, 20),
        sex=Sex.MALE,
        height_cm=178.0,
        weight_kg=76.0,
        goal=Goal.HYPERTROPHY,
        experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
        training_days_per_week=4,
    )
    panca = Exercise(
        wger_id=1, name="Panca piana", primary_muscle="Chest",
        equipment="Barbell", is_compound=True,
    )
    squat = Exercise(
        wger_id=2, name="Squat", primary_muscle="Quads",
        equipment="Barbell", is_compound=True,
    )
    db.add_all([profilo, panca, squat])
    db.commit()
    return db, profilo, panca, squat


def _sessione(db, profilo, data: dt.date, esercizio, *, peso: float, reps: int, serie: int = 3):
    s = WorkoutSession(profile_id=profilo.id, date=data, day_label="A")
    db.add(s)
    db.flush()
    for n in range(serie):
        db.add(
            SessionSet(
                workout_session_id=s.id, exercise_id=esercizio.id,
                set_number=n + 1, reps=reps, weight_kg=peso, rir=2,
            )
        )
    db.commit()
    return s


# --- Massimale stimato --------------------------------------------------------


def test_formula_di_epley():
    """100 kg x 5 -> 100 x (1 + 5/30) = 116,7 kg."""
    assert pr.estimate_1rm(100, 5) == pytest.approx(116.67, abs=0.01)
    assert pr.estimate_1rm(100, 1) == pytest.approx(103.33, abs=0.01)


def test_progresso_misurato_sul_massimale_non_sul_carico(percorso):
    """Passare da 60 kg x 8 a 65 kg x 3 sembra un miglioramento guardando il
    bilanciere, ma il massimale stimato scende: è la differenza che rende
    confrontabili serie con ripetizioni diverse."""
    db, profilo, panca, _ = percorso
    _sessione(db, profilo, OGGI - dt.timedelta(weeks=8), panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=65, reps=3)

    report = pr.build_report(db, profilo, since=OGGI - dt.timedelta(weeks=12))
    progresso = report.exercises[0]

    assert progresso.first_best_1rm > progresso.last_best_1rm
    assert progresso.delta_kg < 0


def test_serie_migliore_scelta_per_massimale_stimato(percorso):
    """Dentro una sessione, la serie di riferimento non è quella col carico
    più alto ma quella col massimale stimato più alto."""
    db, profilo, panca, _ = percorso
    s = WorkoutSession(profile_id=profilo.id, date=OGGI, day_label="A")
    db.add(s)
    db.flush()
    db.add_all([
        SessionSet(workout_session_id=s.id, exercise_id=panca.id, set_number=1, reps=10, weight_kg=60),
        SessionSet(workout_session_id=s.id, exercise_id=panca.id, set_number=2, reps=2, weight_kg=70),
    ])
    db.commit()

    migliore = pr._best_set_of_session(list(s.sets))
    assert (migliore.weight_kg, migliore.reps) == (60, 10)  # 80 kg vs 74,7 kg


def test_esercizio_con_una_sola_sessione_escluso(percorso):
    """Senza almeno due sessioni non c'è progressione da misurare."""
    db, profilo, panca, _ = percorso
    _sessione(db, profilo, OGGI, panca, peso=60, reps=8)

    assert pr.build_report(db, profilo).exercises == []


def test_stima_da_ripetizioni_alte_segnalata(percorso):
    """Oltre le 12 ripetizioni la formula di Epley perde precisione."""
    db, profilo, panca, _ = percorso
    _sessione(db, profilo, OGGI - dt.timedelta(weeks=6), panca, peso=40, reps=20)
    _sessione(db, profilo, OGGI, panca, peso=45, reps=18)

    report = pr.build_report(db, profilo)
    assert report.exercises[0].high_rep_estimate is True
    assert any("perde precisione" in n for n in report.notes)


# --- Peso corporeo: il punto metodologico più importante ---------------------


def test_media_mobile_filtra_le_oscillazioni_giornaliere(percorso):
    """Il peso oscilla di 1-2 kg al giorno per acqua e glicogeno. Con pesate
    frequenti la media deve restituire la tendenza vera, non il rumore."""
    db, profilo, _, _ = percorso
    inizio = OGGI - dt.timedelta(weeks=10)

    # Tendenza reale: +0,1 kg a settimana. Rumore alternato di ±1 kg.
    for settimana in range(11):
        for indice, giorno in enumerate((0, 2, 4)):
            data = inizio + dt.timedelta(weeks=settimana, days=giorno)
            if data > OGGI:
                continue
            rumore = 1.0 if indice % 2 == 0 else -1.0
            db.add(
                WeightLog(
                    profile_id=profilo.id, date=data,
                    weight_kg=76 + settimana * 0.1 + rumore,
                )
            )
    db.commit()

    peso = pr.build_report(db, profilo, since=inizio).weight
    assert peso.smoothed is True
    # Tendenza attesa ~1 kg su 10 settimane: il rumore da ±1 kg non deve
    # produrre un valore lontano da quello.
    assert peso.delta_kg == pytest.approx(1.0, abs=0.5)


def test_poche_pesate_dichiarate_come_inaffidabili(percorso):
    """Con una sola misurazione per estremo, la differenza può essere solo
    l'oscillazione del giorno: va detto invece di presentarla come tendenza."""
    db, profilo, _, _ = percorso
    db.add_all([
        WeightLog(profile_id=profilo.id, date=OGGI - dt.timedelta(weeks=8), weight_kg=76.0),
        WeightLog(profile_id=profilo.id, date=OGGI, weight_kg=78.0),
    ])
    db.commit()

    report = pr.build_report(db, profilo)
    assert report.weight.smoothed is False
    assert any("rumore" in n for n in report.notes)


def test_nessuna_pesata_segnalata(percorso):
    db, profilo, _, _ = percorso
    report = pr.build_report(db, profilo)

    assert report.weight.delta_kg is None
    assert any("Nessuna pesata" in n for n in report.notes)


def test_ritmo_settimanale_calcolato(percorso):
    """È il dato che dice se il ritmo è sensato, più del totale assoluto."""
    db, profilo, _, _ = percorso
    inizio = OGGI - dt.timedelta(weeks=10)
    for settimana in range(11):
        for giorno in (0, 3):
            data = inizio + dt.timedelta(weeks=settimana, days=giorno)
            if data <= OGGI:
                db.add(WeightLog(profile_id=profilo.id, date=data, weight_kg=76 + settimana * 0.2))
    db.commit()

    peso = pr.build_report(db, profilo, since=inizio).weight
    assert peso.weekly_rate_kg == pytest.approx(0.2, abs=0.1)


# --- Cautela sui periodi brevi -----------------------------------------------


def test_periodo_breve_dichiarato(percorso):
    """Sotto le 4 settimane il report avvisa: è la stessa cautela applicata
    nell'autoregolazione del volume."""
    db, profilo, panca, _ = percorso
    _sessione(db, profilo, OGGI - dt.timedelta(days=10), panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=65, reps=8)

    report = pr.build_report(db, profilo, since=OGGI - dt.timedelta(days=14))
    assert report.too_early is True
    assert any("fotografia" in n for n in report.notes)


def test_periodo_lungo_senza_avviso_di_prematurita(percorso):
    db, profilo, panca, _ = percorso
    inizio = OGGI - dt.timedelta(weeks=12)
    _sessione(db, profilo, inizio, panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=70, reps=8)

    report = pr.build_report(db, profilo, since=inizio)
    assert report.too_early is False
    assert not any("fotografia" in n for n in report.notes)


def test_plateau_non_segnalato_su_periodo_troppo_breve(percorso):
    """Su due settimane uno stallo non significa nulla."""
    db, profilo, panca, _ = percorso
    _sessione(db, profilo, OGGI - dt.timedelta(days=10), panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=60, reps=8)

    report = pr.build_report(db, profilo, since=OGGI - dt.timedelta(days=14))
    assert report.plateaued
    assert not any("Fermi da tempo" in n for n in report.notes)


# --- Classificazione dei risultati -------------------------------------------


def test_esercizi_classificati_per_andamento(percorso):
    db, profilo, panca, squat = percorso
    inizio = OGGI - dt.timedelta(weeks=10)

    _sessione(db, profilo, inizio, panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=70, reps=8)      # migliorato
    _sessione(db, profilo, inizio, squat, peso=100, reps=8)
    _sessione(db, profilo, OGGI, squat, peso=100, reps=8)     # fermo

    report = pr.build_report(db, profilo, since=inizio)
    assert [e.exercise_name for e in report.improved] == ["Panca piana"]
    assert [e.exercise_name for e in report.plateaued] == ["Squat"]


def test_plateau_suggerisce_entrambe_le_direzioni(percorso):
    """Uno stallo non significa automaticamente "aumenta": se il recupero è
    compromesso la risposta corretta è ridurre."""
    db, profilo, panca, _ = percorso
    inizio = OGGI - dt.timedelta(weeks=10)
    _sessione(db, profilo, inizio, panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=60, reps=8)

    nota = next(n for n in pr.build_report(db, profilo, since=inizio).notes if "Fermi da tempo" in n)
    assert "alzare il volume" in nota and "ridurlo" in nota


# --- Dallo stallo all'azione --------------------------------------------------


def _stallo(db, profilo, panca):
    inizio = OGGI - dt.timedelta(weeks=10)
    _sessione(db, profilo, inizio, panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=60, reps=8)
    return pr.build_report(db, profilo, since=inizio)


def test_stallo_senza_feedback_chiede_invece_di_indovinare(percorso):
    """Senza sapere come recupera l'utente, le due direzioni restano
    entrambe aperte: dirlo è più utile che tirare a indovinare."""
    db, profilo, panca, _ = percorso
    messaggio = pr.explain_plateau(db, profilo, _stallo(db, profilo, panca))

    assert "Registra un feedback" in messaggio
    assert "aumentare" in messaggio and "ridotto" in messaggio


def test_stallo_con_recupero_compromesso_porta_a_ridurre(percorso):
    db, profilo, panca, _ = percorso
    report = _stallo(db, profilo, panca)
    db.add(TrainingFeedback(
        profile_id=profilo.id, date=OGGI,
        progress_perception=ProgressPerception.NONE,
        recovery_quality=RecoveryQuality.POOR,
        doms_duration_hours=96, affects_performance=True,
    ))
    db.commit()

    assert "Riduco" in pr.explain_plateau(db, profilo, report)


def test_stesso_stallo_con_buon_recupero_porta_ad_aumentare(percorso):
    """La conclusione opposta a parità di stallo: è il feedback a
    discriminare, non il numero fermo."""
    db, profilo, panca, _ = percorso
    report = _stallo(db, profilo, panca)
    db.add(TrainingFeedback(
        profile_id=profilo.id, date=OGGI,
        progress_perception=ProgressPerception.NONE,
        recovery_quality=RecoveryQuality.GOOD, doms_duration_hours=24,
    ))
    db.commit()

    assert "aumentare lo stimolo" in pr.explain_plateau(db, profilo, report)


def test_nessuno_stallo_nessun_messaggio(percorso):
    db, profilo, panca, _ = percorso
    inizio = OGGI - dt.timedelta(weeks=10)
    _sessione(db, profilo, inizio, panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=75, reps=8)

    report = pr.build_report(db, profilo, since=inizio)
    assert pr.explain_plateau(db, profilo, report) is None


def test_periodo_breve_non_produce_diagnosi_di_stallo(percorso):
    db, profilo, panca, _ = percorso
    _sessione(db, profilo, OGGI - dt.timedelta(days=10), panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=60, reps=8)

    report = pr.build_report(db, profilo, since=OGGI - dt.timedelta(days=14))
    assert pr.explain_plateau(db, profilo, report) is None


# --- Aderenza -----------------------------------------------------------------


def test_bassa_aderenza_segnalata_prima_di_cambiare_scheda(percorso):
    """Se il volume svolto è molto inferiore a quello programmato, il
    programma non è stato davvero messo alla prova."""
    db, profilo, panca, _ = percorso
    inizio = OGGI - dt.timedelta(weeks=8)
    db.add(WorkoutPlan(
        profile_id=profilo.id, name="p", goal=Goal.HYPERTROPHY,
        days_per_week=4, is_active=True, started_at=inizio,
    ))
    db.commit()

    _sessione(db, profilo, inizio, panca, peso=60, reps=8)
    _sessione(db, profilo, OGGI, panca, peso=62, reps=8)

    report = pr.build_report(db, profilo, since=inizio)
    assert report.adherence.ratio < 0.7
    assert any("volume effettivo" in n for n in report.notes)


def test_aderenza_senza_piano_attivo_non_calcolata(percorso):
    db, profilo, _, _ = percorso
    report = pr.build_report(db, profilo)
    assert report.adherence.planned_per_week is None
    assert report.adherence.ratio is None


# --- Formattazione -------------------------------------------------------------


def test_report_leggibile_anche_senza_dati(percorso):
    db, profilo, _, _ = percorso
    testo = pr.format_report(pr.build_report(db, profilo))

    assert "dati insufficienti" in testo
    assert "Nessun esercizio" in testo
