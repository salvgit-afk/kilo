"""Biomeccanica e suggerimenti dell'overlay esercizio.

Il caso da cui nasce: il box "Dove concentrarti" mostrava per qualunque
esercizio la stessa frase su bicipiti e quadricipiti, anche per lo squat.
"""

from __future__ import annotations

import pytest

from app.models import Exercise
from app.services import exercise_guidance as g


def ex(name: str, muscle: str, compound: bool = False) -> Exercise:
    return Exercise(name=name, primary_muscle=muscle, is_compound=compound, source="test")


@pytest.mark.parametrize(
    "name,muscle,pattern",
    [
        ("Barbell Squat", "Quads", "squat"),
        ("Leg Press", "Quads", "squat"),
        ("Bulgarian Split Squat", "Glutes", "lunge"),
        ("Romanian Deadlift", "Hamstrings", "hinge"),
        ("Barbell Hip Thrust", "Glutes", "hip_thrust"),
        ("Seated Leg Curl", "Hamstrings", "leg_curl"),
        ("Leg Extension", "Quads", "leg_extension"),
        ("Standing Calf Raise", "Calves", "calf_raise"),
        ("Bench Press: Barbell", "Chest", "horizontal_press"),
        ("Bench Press: Machine", "Chest", "horizontal_press"),  # "machine" contiene "chin"
        ("Cable Crossover", "Chest", "fly"),
        ("Rear Delt Fly", "Shoulders", "rear_delt"),
        ("Lateral Dumbbell Raises", "Shoulders", "lateral_raise"),
        ("Seated Military Press", "Shoulders", "overhead_press"),
        ("Pike Push Ups", "Shoulders", "overhead_press"),
        ("Lat Pulldown", "Lats", "vertical_pull"),
        ("Straight-Arm Pulldown", "Lats", "straight_arm"),
        ("Pendlay Row", "Lats", "row"),
        ("EZ-Bar Upright Row", "Shoulders", "upright_row"),
        ("Kneeling Single-Arm High Pulley Row", "Lats", "row"),  # "pulley" non è "high pull"
        ("Barbell Shrugs", "Trapezius", "shrug"),
        ("EZ-Bar Curl", "Biceps", "curl"),
        ("Triceps Pushdown: Cable", "Triceps", "triceps_extension"),
        ("Lying Close Grip Triceps Press to Chin", "Triceps", "triceps_extension"),
        ("Cable External Rotation", "Shoulders", "shoulder_rotation"),
        ("Cable Russian Twists", "Abs", "rotation"),
        ("Hanging Leg Raise", "Abs", "leg_raise"),
        ("Cable Crunch", "Abs", "crunch"),
        ("Plank", "Abs", "anti_movement"),
    ],
)
def test_schema_di_movimento_riconosciuto(name, muscle, pattern):
    assert g.build(ex(name, muscle)).pattern == pattern


def test_ogni_schema_ha_articolazioni_piano_e_indicazioni():
    for p in g.PATTERNS:
        assert p.joints and p.actions and p.cues, p.key
        assert p.plane in g.PLANES, p.key


def test_esercizio_non_riconosciuto_senza_indicazioni_inventate():
    guida = g.build(ex("Warrior II", "Glutes"))
    assert guida.pattern is None
    assert guida.cues == []
    assert guida.joints == ["anca"]


# --- Come sentire il muscolo (era il bug del box verde) ---------------------------------------------------------


def test_indicazione_diversa_per_ogni_movimento():
    curl = g.build(ex("EZ-Bar Curl", "Biceps"))
    squat = g.build(ex("Barbell Squat", "Quads", compound=True))
    lat = g.build(ex("Lat Pulldown: Cable (Wide Grip)", "Lats", compound=True))
    assert len({curl.muscle_cue, squat.muscle_cue, lat.muscle_cue}) == 3
    # Allo squat non si parla più di bicipiti.
    assert "gomit" not in squat.muscle_cue
    assert "gomiti" in lat.muscle_cue and "non con le mani" in lat.muscle_cue


def test_stesso_schema_muscolo_diverso_indicazione_diversa():
    """La panca a presa stretta lavora il tricipite: l'indicazione lo segue."""
    petto = g.build(ex("Bench Press: Barbell", "Chest", compound=True))
    tricipite = g.build(ex("Bench Press: Barbell (Close Grip)", "Triceps", compound=True))
    assert petto.pattern == tricipite.pattern == "horizontal_press"
    assert "abbracciare" in petto.muscle_cue
    assert "tricip" not in petto.muscle_cue and "gomiti vicini" in tricipite.muscle_cue


def test_ogni_schema_ha_la_sua_indicazione():
    senza = {p.key for p in g.PATTERNS} - set(g.MUSCLE_CUES_BY_PATTERN) - {"total_body"}
    assert not senza


def test_esercizio_non_riconosciuto_usa_il_muscolo():
    assert g.build(ex("Qualcosa", "Chest")).muscle_cue == g.MUSCLE_CUES_BY_MUSCLE["Chest"]
    assert g.build(ex("Qualcosa", "Muscolo sconosciuto")).muscle_cue is None


def test_niente_etichette_di_evidenza_nelle_indicazioni():
    """Le etichette misurato/non misurato non davano un'azione da fare."""
    for p in g.PATTERNS:
        frase = g.muscle_cue("Chest", p.key) or ""
        assert "studio" not in frase and "misurat" not in frase


def test_allungamento_solo_dove_la_fonte_ha_dati():
    assert "seduti" in g.build(ex("Seated Leg Curl", "Hamstrings")).lengthened_note
    assert "sopra la testa" in g.build(ex("Triceps Extension: Cable (Overhead)", "Triceps")).lengthened_note
    assert g.build(ex("Bench Press: Barbell", "Chest")).lengthened_note is None


def test_dato_sull_allungamento_solo_sotto_l_esercizio_studiato():
    """Lo studio sulla leg extension non va mostrato sotto lo squat, né quello
    sul leg curl sotto lo stacco rumeno."""
    assert g.build(ex("Front Squat with Barbell", "Quads", compound=True)).lengthened_note is None
    assert g.build(ex("Leg Extension", "Quads")).lengthened_note is not None
    assert g.build(ex("Romanian Deadlift", "Hamstrings", compound=True)).lengthened_note is None
    assert g.build(ex("Bench Dips", "Triceps", compound=True)).lengthened_note is None
