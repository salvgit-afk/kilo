"""Catalogo unito: RepDB, esercizi scritti a mano, doppioni fra fonti, ricerca.

Nessuna rete: i dataset sono costruiti a mano.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models import ActivityLevel, Exercise, ExperienceLevel, Goal, Sex, UserProfile
from app.services import exercise_library as lib
from app.services import exercise_swap as sw
from app.services import translation
from app.services import workout_generator as wg
from app.services.manual_exercises import MANUAL_EXERCISES


def _rep(id_, name, primary, *, category="strength", mechanic="isolation", equipment="cable",
         images=None, secondary=()):
    return {
        "id": id_, "name_en": name, "category": category, "mechanic": mechanic,
        "equipment": equipment, "primary_muscles": list(primary),
        "secondary_muscles": list(secondary), "difficulty": "beginner",
        "instructions_en": ["Step one.", "Step two."], "tips_en": ["Tip."],
        "images": {"flat": images if images is not None else {
            "start": f"images/flat/{id_}-start.webp", "peak": f"images/flat/{id_}-peak.webp",
        }},
    }


def _ex(db, source, external_id, name, muscle="Chest", **campi):
    esercizio = Exercise(source=source, external_id=external_id, name=name, primary_muscle=muscle, **campi)
    db.add(esercizio)
    db.commit()
    return esercizio


def _profilo():
    return UserProfile(
        display_name="t", birth_date=dt.date(1995, 1, 1), sex=Sex.MALE, height_cm=178,
        weight_kg=76, goal=Goal.HYPERTROPHY, experience_level=ExperienceLevel.INTERMEDIATE,
        activity_level=ActivityLevel.MODERATELY_ACTIVE, training_days_per_week=4,
    )


# --- RepDB ---------------------------------------------------------------------------


def test_repdb_mappa_muscoli_attrezzi_e_immagini():
    c = lib.parse_repdb_entry(
        _rep("cable-lateral-raise", "Cable Lateral Raise", ["lateral_deltoid"],
             secondary=["trapezius", "supraspinatus"])
    )
    assert c["primary_muscle"] == "Shoulders"
    assert c["secondary_muscles"] == "Trapezius", "il sovraspinato è già nelle spalle"
    assert c["equipment"] == "cable"
    assert c["demo_images"] == [
        f"{lib.REPDB_IMAGE_BASE_URL}images/flat/cable-lateral-raise-start.webp",
        f"{lib.REPDB_IMAGE_BASE_URL}images/flat/cable-lateral-raise-peak.webp",
    ]
    assert c["priority"] == lib.staple_priority("repdb", "cable-lateral-raise") < lib.DEFAULT_PRIORITY


@pytest.mark.parametrize(
    "equipment,atteso",
    [
        (None, lib.BODYWEIGHT),
        ("ez_bar", "e-z curl bar"),
        ("pec_deck", "machine"),
        ("chest_press_machine", "machine"),
        ("lat_pulldown_machine", "cable"),
        ("suspension_trainer", "suspension trainer"),
        ("battle_rope", "battle rope"),
    ],
)
def test_repdb_attrezzatura_nel_vocabolario_dell_app(equipment, atteso):
    voce = _rep("x", "Machine Row", ["latissimus_dorsi"], equipment=equipment)
    assert lib.parse_repdb_entry(voce)["equipment"] == atteso


def test_repdb_addominali_sempre_isolamento():
    """Come per Everkinetic: il generatore mette i multi-articolari per primi,
    e un leg raise non deve passare davanti come se fosse uno squat."""
    c = lib.parse_repdb_entry(
        _rep("hanging-leg-raise", "Hanging Leg Raise", ["hip_flexors", "rectus_abdominis"],
             mechanic="compound", equipment="pull_up_bar")
    )
    assert c["primary_muscle"] == "Abs" and c["is_compound"] is False


def test_repdb_una_sola_posa():
    c = lib.parse_repdb_entry(_rep("x", "Dumbbell Pullover", ["latissimus_dorsi"],
                                   images={"main": "images/flat/x-main.webp"}))
    assert len(c["demo_images"]) == 1


@pytest.mark.parametrize(
    "voce",
    [
        _rep("plank", "Plank", ["rectus_abdominis"], equipment=None),
        _rep("farmer", "Dumbbell Farmer's Walk", ["trapezius"], equipment="dumbbell"),
        _rep("stretch", "Doorway Chest Stretch", ["pectoralis_major"], category="stretching"),
        _rep("wrist", "Cable Wrist Curl", ["forearm_flexors"]),
        _rep("noimg", "Cable Curl", ["biceps_brachii"], images={}),
    ],
)
def test_repdb_scarta_cio_che_non_va_in_scheda(voce):
    assert lib.parse_repdb_entry(voce) is None


def test_affondi_camminati_restano():
    """Si contano in ripetizioni: non sono esercizi a tempo."""
    assert lib.parse_repdb_entry(_rep("walking-lunge", "Walking Lunge", ["quadriceps"], equipment=None))


def test_free_exercise_db_scarta_il_plank():
    voce = {
        "id": "Plank", "name": "Plank", "category": "strength", "mechanic": None,
        "equipment": "body only", "primaryMuscles": ["abdominals"], "secondaryMuscles": [],
        "instructions": ["a"], "images": ["Plank/0.jpg", "Plank/1.jpg"],
    }
    assert lib.parse_entry(voce) is None


def test_download_repdb_estrae_l_elenco(monkeypatch):
    class Risposta:
        def raise_for_status(self):
            pass

        def json(self):
            return {"count": 1, "exercises": [{"id": "a"}]}

    monkeypatch.setattr(lib.httpx, "get", lambda *a, **k: Risposta())
    assert lib.fetch_dataset(lib.REPDB_DATASET_URL) == [{"id": "a"}]


# --- Esercizi scritti a mano ----------------------------------------------------------


def test_esercizi_manuali_completi_e_coerenti_con_il_catalogo(db):
    assert lib.sync_manual(db).created == len(MANUAL_EXERCISES) == 4
    esercizi = {e.external_id: e for e in db.query(Exercise).filter_by(source=lib.SOURCE_MANUAL)}
    assert set(esercizi) == {
        "bayesian-cable-curl", "behind-back-cable-lateral-raise",
        "low-to-high-cable-fly", "pendulum-squat",
    }
    gruppi = wg.PUSH_MUSCLES + wg.PULL_MUSCLES + wg.LEG_MUSCLES + wg.CORE_MUSCLES
    for e in esercizi.values():
        # Stesse regole del prompt di traduzione del catalogo.
        assert e.name_it and len(e.name_it.split()) <= 6
        assert translation.english_leftovers(e.name_it) == []
        assert 3 <= len(e.instructions_it) <= 8 and len(e.instructions) >= 3
        assert 2 <= len(e.focus_it) <= 3 and all(len(f.split()) <= 14 for f in e.focus_it)
        assert e.primary_muscle in gruppi
        assert not e.demo_images and not e.image_url
    assert lib.sync_manual(db).created == 0, "rieseguire non crea doppioni"


# --- Doppioni fra fonti ---------------------------------------------------------------


def test_file_dei_doppioni_ben_formato():
    gruppi = lib.load_duplicate_groups()
    chiavi = [k for g in gruppi for k in g]
    assert len(gruppi) > 200
    assert all(len(g) >= 2 for g in gruppi)
    assert len(chiavi) == len(set(chiavi)), "un esercizio non può stare in due gruppi"
    assert {k.split(":", 1)[0] for k in chiavi} <= set(lib.CATALOG_SOURCES)


def test_doppioni_disegni_poi_illustrazioni_poi_foto(db):
    foto = _ex(db, lib.SOURCE, "F", "Cable Crunch", "Abs")
    illustrazione = _ex(db, lib.SOURCE_REPDB, "R", "Cable Crunch", "Abs")
    nascosti = lib.apply_duplicates(
        db, groups=[[f"{lib.SOURCE}:F", f"{lib.SOURCE_REPDB}:R", "everkinetic:non-importato"]]
    )
    assert nascosti == 1
    assert foto.duplicate_of_id == illustrazione.id and illustrazione.duplicate_of_id is None

    disegno = _ex(db, lib.SOURCE_EVERKINETIC, "E", "Seated Ab Crunch with Cable", "Abs")
    lib.apply_duplicates(
        db, groups=[[f"{lib.SOURCE}:F", f"{lib.SOURCE_REPDB}:R", f"{lib.SOURCE_EVERKINETIC}:E"]]
    )
    assert foto.duplicate_of_id == disegno.id and illustrazione.duplicate_of_id == disegno.id

    # Si ricalcola da capo: senza gruppi torna tutto visibile.
    lib.apply_duplicates(db, groups=[])
    assert all(e.duplicate_of_id is None for e in (foto, illustrazione, disegno))


def test_catalogo_senza_wger_ne_doppioni_ma_con_i_non_tradotti(db):
    _ex(db, "wger", "W", "Old Curl", "Biceps")
    visibile = _ex(db, lib.SOURCE_REPDB, "R", "Cable Curl", "Biceps")
    _ex(db, lib.SOURCE, "F", "Standing Biceps Cable Curl", "Biceps")
    lib.apply_duplicates(db, groups=[[f"{lib.SOURCE}:F", f"{lib.SOURCE_REPDB}:R"]])

    assert db.query(Exercise).filter(lib.catalog_condition(db)).all() == [visibile]


def test_esercizi_di_base_senza_voci_ripetute():
    """Una voce ripetuta prenderebbe la priorità dell'ultima posizione."""
    voci = [v for elenco in lib.CATALOG_STAPLES.values() for v in elenco]
    assert len(voci) == len(set(voci))
    # Lat machine e shoulder press restano in cima anche senza i disegni.
    assert lib.staple_priority("repdb", "lat-pulldown") == 0
    assert lib.staple_priority("repdb", "dumbbell-shoulder-press") == 0


def test_esercizi_di_base_hip_thrust_e_panca():
    """Everkinetic non ha l'hip thrust: arriva da RepDB e diventa il primo dei
    glutei, senza spostare gli esercizi di base degli altri gruppi."""
    assert lib.staple_priority("repdb", "hip-thrust") == 0
    assert lib.staple_priority("everkinetic", "0109") == 1
    assert lib.staple_priority("everkinetic", "0042") == 0
    assert lib.staple_priority("repdb", "qualcosa-di-non-base") == lib.DEFAULT_PRIORITY


def test_sync_catalog_unisce_le_fonti_e_applica_i_doppioni(db, monkeypatch):
    monkeypatch.setattr(
        lib, "load_duplicate_groups",
        lambda path=lib.DUPLICATES_FILE: [["everkinetic:0042", "repdb:bench-press"]],
    )
    everkinetic = {
        "id": "0042", "title": "Bench Press: Barbell", "name": "bench", "type": "compound",
        "primary": ["pectoralis major"], "secondary": [], "equipment": ["barbell"],
        "steps": ["a", "b"], "tips": [], "svg": ["svg/0042-a.svg", "svg/0042-b.svg"],
    }
    repdb = [
        _rep("bench-press", "Barbell Bench Press", ["pectoralis_major"], mechanic="compound", equipment="barbell"),
        _rep("pec-deck", "Pec Deck", ["pectoralis_major"], equipment="pec_deck"),
    ]

    esito = lib.sync_catalog(
        db, datasets={lib.SOURCE_EVERKINETIC: [everkinetic], lib.SOURCE_REPDB: repdb, lib.SOURCE: []}
    )

    assert esito.created == 3 + len(MANUAL_EXERCISES)
    visibili = {(e.source, e.external_id) for e in db.query(Exercise).filter(lib.catalog_condition(db))}
    assert ("everkinetic", "0042") in visibili and ("repdb", "pec-deck") in visibili
    assert ("repdb", "bench-press") not in visibili
    assert ("kilo", "bayesian-cable-curl") in visibili


# --- Ricerca fra le alternative -------------------------------------------------------


def test_ricerca_fra_le_alternative_per_nome_italiano_o_originale(db):
    base = _ex(db, lib.SOURCE_EVERKINETIC, "E1", "Biceps Curl: Barbell", "Biceps", equipment="barbell")
    _ex(db, lib.SOURCE_EVERKINETIC, "E2", "Hammer Curls with Rope and Cable", "Biceps",
        equipment="cable", name_it="Curl a martello ai cavi con corda")
    _ex(db, lib.SOURCE_REPDB, "R1", "Dumbbell Hammer Curl", "Biceps", equipment="dumbbell")

    assert [a.exercise.external_id for a in sw.find_alternatives(db, _profilo(), base, q="cavi")] == ["E2"]
    trovati = sw.find_alternatives(db, _profilo(), base, q="hammer", limit=10)
    assert {a.exercise.external_id for a in trovati} == {"E2", "R1"}
    assert len(sw.find_alternatives(db, _profilo(), base, limit=10)) == 2
