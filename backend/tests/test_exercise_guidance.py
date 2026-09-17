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


# --- Il bug del box verde ---------------------------------------------------------


def test_nota_sul_focus_diversa_per_bicipiti_e_quadricipiti():
    curl = g.build(ex("EZ-Bar Curl", "Biceps"))
    squat = g.build(ex("Barbell Squat", "Quads", compound=True))
    assert curl.focus_evidence == g.FOCUS_SUPPORTED
    assert squat.focus_evidence == g.FOCUS_NOT_SHOWN
    assert curl.focus_note != squat.focus_note
    assert "bicipit" in curl.focus_note and "quadricipit" in squat.focus_note
    # Allo squat non si parla più di bicipiti.
    assert "bicipit" not in squat.focus_note


def test_muscoli_non_misurati_dichiarati_come_tali():
    for muscolo in ("Chest", "Lats", "Shoulders", "Abs"):
        assert g.build(ex("Qualcosa", muscolo)).focus_evidence == g.FOCUS_UNTESTED


def test_nei_multiarticolari_la_priorita_resta_il_movimento():
    isolamento = g.build(ex("Cable Crossover", "Chest"))
    panca = g.build(ex("Bench Press: Barbell", "Chest", compound=True))
    assert "multi-articolari" in panca.focus_note
    assert "multi-articolari" not in isolamento.focus_note


def test_allungamento_solo_dove_la_fonte_ha_dati():
    assert "seduti" in g.build(ex("Seated Leg Curl", "Hamstrings")).lengthened_note
    assert "sopra la testa" in g.build(ex("Overhead Cable Extension", "Triceps")).lengthened_note
    assert g.build(ex("Bench Press: Barbell", "Chest")).lengthened_note is None
