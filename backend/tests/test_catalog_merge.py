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


def test_voci_non_piu_valide_escono_dal_catalogo_e_possono_tornare(db):
    """Esercizi importati con regole vecchie (come i plank di free-exercise-db)
    non devono restare visibili, ma nemmeno sparire dal database."""
    riga = _rep("renegade", "Renegade Row", ["latissimus_dorsi"], equipment="dumbbell")
    resta = _rep("keep", "Cable Row", ["latissimus_dorsi"])
    lib.sync_library(db, dataset=[riga, resta], source=lib.SOURCE_REPDB)

    # Ora la voce ricade nelle esclusioni (esercizio a tempo).
    lib.sync_library(db, dataset=[{**riga, "name_en": "Renegade Row Hold"}, resta], source=lib.SOURCE_REPDB)
    visibili = {e.external_id for e in db.query(Exercise).filter(lib.catalog_condition(db))}
    assert visibili == {"keep"}
    assert db.query(Exercise).filter_by(external_id="renegade").one().in_catalog is False

    lib.sync_library(db, dataset=[riga, resta], source=lib.SOURCE_REPDB)
    visibili = {e.external_id for e in db.query(Exercise).filter(lib.catalog_condition(db))}
    assert visibili == {"renegade", "keep"}


def test_download_senza_voci_valide_non_svuota_il_catalogo(db):
    lib.sync_library(db, dataset=[_rep("keep", "Cable Row", ["latissimus_dorsi"])], source=lib.SOURCE_REPDB)
    lib.sync_library(db, dataset=[], source=lib.SOURCE_REPDB)
    assert db.query(Exercise).filter(lib.catalog_condition(db)).count() == 1


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
    assert lib.sync_manual(db).created == len(MANUAL_EXERCISES) == 8
    esercizi = {e.external_id: e for e in db.query(Exercise).filter_by(source=lib.SOURCE_MANUAL)}
    assert set(esercizi) == {
        "bayesian-cable-curl", "behind-back-cable-lateral-raise",
        "low-to-high-cable-fly", "pendulum-squat",
        "single-arm-overhead-cable-triceps-extension", "cross-body-cable-triceps-extension",
        "single-arm-high-cable-reverse-fly", "chest-supported-dumbbell-lateral-raise",
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


def test_ricerca_in_italiano_trova_anche_gli_esercizi_non_tradotti(db):
    base = _ex(db, lib.SOURCE_EVERKINETIC, "E1", "Lateral Dumbbell Raises", "Shoulders", equipment="dumbbell")
    _ex(db, lib.SOURCE, "F1", "Cable Rear Delt Fly", "Shoulders", equipment="cable")
    _ex(db, lib.SOURCE_REPDB, "R1", "Dumbbell Reverse Fly", "Shoulders", equipment="dumbbell")
    _ex(db, lib.SOURCE_REPDB, "R2", "Cable Lateral Raise", "Shoulders", equipment="cable")

    def cerca(q):
        return {a.exercise.external_id for a in sw.find_alternatives(db, _profilo(), base, q=q, limit=10)}

    assert cerca("cavi") == {"F1", "R2"}
    assert cerca("croci ai cavi") == {"F1"}
    assert cerca("croci inverse") == {"F1", "R1"}
    assert cerca("alzate laterali al cavo") == {"R2"}
    assert cerca("manubri") == {"R1"}


def test_nomi_scelti_a_mano_valgono_solo_per_gli_esercizi_tradotti(db):
    tradotto = _ex(db, lib.SOURCE_REPDB, "cable-fly", "Cable Fly", "Chest", equipment="cable", name_it="Croci ai cavi")
    da_tradurre = _ex(db, lib.SOURCE_EVERKINETIC, "0048", "Cable Crossover", "Chest", equipment="cable")

    assert lib.apply_name_overrides(db) == 1
    assert tradotto.name_it == "Croci ai cavi dall'alto"
    # Senza traduzione il nome arriva con quella, altrimenti l'esecuzione
    # resterebbe in inglese per sempre.
    assert da_tradurre.name_it is None
    assert lib.name_override(da_tradurre) == "Croci ai cavi a metà altezza"


def test_nomi_scelti_a_mano_ben_formati():
    from app.services.manual_exercises import NAME_IT_OVERRIDES

    for chiave, nome in NAME_IT_OVERRIDES.items():
        assert chiave.split(":", 1)[0] in lib.CATALOG_SOURCES
        assert len(nome.split()) <= 7 and translation.english_leftovers(nome) == []


# --- Adduttori ------------------------------------------------------------------------


def _free(id_, name, primary, *, equipment="machine", category="strength", secondary=()):
    return {
        "id": id_, "name": name, "category": category, "equipment": equipment,
        "primaryMuscles": list(primary), "secondaryMuscles": list(secondary),
        "mechanic": "isolation", "level": "beginner",
        "instructions": ["Step one.", "Step two."], "images": [f"{id_}/0.jpg", f"{id_}/1.jpg"],
    }


def test_adduttori_entrano_nel_catalogo_da_tutte_le_fonti():
    assert lib.parse_entry(_free("Thigh_Adductor", "Thigh Adductor", ["adductors"]))["primary_muscle"] == "Adductors"
    assert lib.parse_repdb_entry(_rep("hip-adduction", "Hip Adduction", ["adductors"]))["primary_muscle"] == "Adductors"
    ever = lib.parse_everkinetic_entry({
        "id": "0157", "title": "Thigh Adductor", "name": "thigh adductor", "type": "isolation",
        "primary": ["quadriceps"], "secondary": [], "equipment": ["machine"],
        "steps": ["Uno.", "Due."], "tips": [], "svg": ["a.svg", "b.svg"],
    })
    assert ever["primary_muscle"] == "Adductors" and ever["is_compound"] is False


def test_adduzione_al_cavo_non_e_un_esercizio_per_i_quadricipiti():
    voce = _free("Cable_Hip_Adduction", "Cable Hip Adduction", ["quadriceps"], equipment="cable")
    assert lib.parse_entry(voce)["primary_muscle"] == "Adductors"


def test_esclusa_l_adduzione_con_elastico_che_descrive_un_abduzione():
    assert lib.parse_entry(_free("Band_Hip_Adductions", "Band Hip Adductions", ["adductors"], equipment="bands")) is None


def test_adduttori_primari_solo_se_non_c_e_altro_gruppo():
    """La sumo high pull resta alle spalle; la leg press a piedi larghi va ai
    quadricipiti, con gli adduttori fra i secondari."""
    sumo = lib.parse_repdb_entry(
        _rep("kettlebell-sumo-high-pull", "Kettlebell Sumo High Pull",
             ["adductors", "lateral_deltoid", "trapezius"], mechanic="compound", equipment="kettlebell")
    )
    assert sumo["primary_muscle"] == "Shoulders"
    leg_press = lib.parse_repdb_entry(
        _rep("wide-stance-leg-press", "Wide-Stance Leg Press", ["adductors"],
             secondary=["gluteus_maximus", "quadriceps"], mechanic="compound", equipment="leg_press")
    )
    assert leg_press["primary_muscle"] == "Quads"
    assert "Adductors" in leg_press["secondary_muscles"] and "Glutes" in leg_press["secondary_muscles"]


def test_il_generatore_non_programma_gli_adduttori(db):
    for nome, muscolo in [("Adductor machine", "Adductors"), *((f"{m} base", m) for m in wg.FULL_BODY_MUSCLES)]:
        _ex(db, lib.SOURCE_EVERKINETIC, nome, nome, muscolo, is_compound=True)
    profilo = _profilo()
    db.add(profilo)
    db.commit()
    for split in ("full_body", "push_pull", "upper_lower"):
        piano = wg.generate_plan(db, profilo, split_type=split)
        assert "Adductors" not in {e.exercise.primary_muscle for e in piano.exercises}


def test_adduttori_aggiungibili_dalla_scheda(db):
    _ex(db, lib.SOURCE_EVERKINETIC, "0157", "Thigh Adductor", "Adductors", equipment="machine")
    _ex(db, lib.SOURCE_EVERKINETIC, "0135", "Hip Adduction", "Adductors", equipment="cable")
    profilo = _profilo()
    db.add(profilo)
    db.commit()
    trovati = sw.find_candidates(db, profilo, "Adductors")
    assert {c.exercise.external_id for c in trovati} == {"0157", "0135"}


# --- Doppioni rivisti -------------------------------------------------------------------


def _gruppo_di(chiave):
    return next((set(g) for g in lib.load_duplicate_groups() if chiave in g), set())


def test_doppioni_che_erano_esercizi_diversi_ora_separati():
    # Pushdown a un braccio dal cavo alto ≠ estensione sopra la testa dal cavo basso.
    assert "everkinetic:0199" not in _gruppo_di("everkinetic:0166")
    assert _gruppo_di("everkinetic:0199") == {
        "everkinetic:0199", "free_exercise_db:Standing_Low-Pulley_One-Arm_Triceps_Extension",
        "kilo:single-arm-overhead-cable-triceps-extension",
    }
    # Squat su una gamba con l'altra incrociata ≠ squat bulgaro con bilanciere.
    assert "everkinetic:0132" not in _gruppo_di("everkinetic:0147")
    # In piedi sopra un manubrio ≠ polpacci con i manubri in mano.
    assert _gruppo_di("free_exercise_db:Calf_Raise_On_A_Dumbbell") == set()
    # Rematore in ginocchio dal cavo alto ≠ dal cavo a metà altezza.
    assert _gruppo_di("repdb:kneeling-cable-row") == set()


def test_doppioni_sfuggiti_aggiunti():
    assert "repdb:hip-abduction" in _gruppo_di("everkinetic:0156")
    assert _gruppo_di("everkinetic:0157") == {
        "everkinetic:0157", "free_exercise_db:Thigh_Adductor", "repdb:hip-adduction",
    }
    assert "repdb:smith-machine-shrug" in _gruppo_di("everkinetic:0041")
    assert "free_exercise_db:Seated_One-arm_Cable_Pulley_Rows" in _gruppo_di("repdb:one-arm-seated-cable-row")


# --- Ricerca tollerante -------------------------------------------------------------


def test_ricerca_tollera_una_parola_che_non_compare_nel_nome(db):
    """Le ricerche che non trovavano nulla: ogni parola doveva comparire nel nome."""
    base = _ex(db, lib.SOURCE_EVERKINETIC, "T0", "Triceps Pushdown: Cable", "Triceps", equipment="cable")
    _ex(db, lib.SOURCE_EVERKINETIC, "0199", "Triceps Extension: Cable (One Arm, Low-Pulley)", "Triceps",
        equipment="cable", name_it="Estensioni monolaterali al cavo sopra la testa")
    _ex(db, lib.SOURCE_EVERKINETIC, "0166", "One Arm Tricep Extension with Cable", "Triceps", equipment="cable")
    _ex(db, lib.SOURCE_EVERKINETIC, "D1", "Triceps Extension: Dumbbell (Standing)", "Triceps", equipment="dumbbell")

    trovati = sw.find_alternatives(
        db, _profilo(), base, q="estensioni sopra la testa ai cavi a braccio singolo", limit=10
    )
    assert [a.exercise.external_id for a in trovati][0] == "0199"


def test_ricerca_gamba_singola_e_attrezzatura(db):
    _ex(db, lib.SOURCE_REPDB, "single-leg-extension", "Single Leg Extension", "Quads", equipment="machine")
    _ex(db, lib.SOURCE_EVERKINETIC, "0142", "Leg Extensions", "Quads", equipment="machine")
    _ex(db, lib.SOURCE_EVERKINETIC, "0157", "Thigh Adductor", "Adductors", equipment="machine",
        name_it="Adductor machine")
    profilo = _profilo()
    db.add(profilo)
    db.commit()
    gamba = sw.find_candidates(db, profilo, "Quads", q="leg extension gamba singola")
    assert [c.exercise.external_id for c in gamba] == ["single-leg-extension", "0142"]
    # "macchina" sta nell'attrezzatura, non nel nome.
    assert [c.exercise.external_id for c in sw.find_candidates(db, profilo, "Adductors", q="adduttori macchina")] == ["0157"]


def test_ricerca_di_due_parole_le_vuole_entrambe(db):
    _ex(db, lib.SOURCE_EVERKINETIC, "C1", "Hammer Curls with Rope and Cable", "Biceps", equipment="cable")
    _ex(db, lib.SOURCE_EVERKINETIC, "C2", "Biceps Curl: Dumbbell", "Biceps", equipment="dumbbell")
    profilo = _profilo()
    db.add(profilo)
    db.commit()
    assert [c.exercise.external_id for c in sw.find_candidates(db, profilo, "Biceps", q="curl corda")] == ["C1"]


# --- Storico dei carichi fra doppioni ---------------------------------------------------


def test_lo_storico_dei_carichi_vale_per_tutto_il_gruppo_di_doppioni(db):
    """Carichi segnati sulla versione scritta a mano, poi nascosta come doppione:
    la versione visibile li ritrova (e la nuova scheda riparte da lì)."""
    from app.models import SessionSet, WorkoutSession
    from app.services import training_log

    a_mano = _ex(db, lib.SOURCE_MANUAL, "single-arm-overhead-cable-triceps-extension",
                 "Single-Arm Overhead Cable Triceps Extension", "Triceps", in_catalog=True)
    disegni = _ex(db, lib.SOURCE_EVERKINETIC, "0199", "Triceps Extension: Cable (One Arm, Low-Pulley)",
                  "Triceps", in_catalog=True)
    altro = _ex(db, lib.SOURCE_EVERKINETIC, "0206", "Triceps Pushdown: Cable (Rope)", "Triceps", in_catalog=True)
    profilo = _profilo()
    db.add(profilo)
    db.commit()
    sessione = WorkoutSession(profile_id=profilo.id, date=dt.date(2026, 10, 3))
    db.add(sessione)
    db.flush()
    db.add_all([
        SessionSet(workout_session_id=sessione.id, exercise_id=a_mano.id, set_number=1, weight_kg=10, reps=8),
        SessionSet(workout_session_id=sessione.id, exercise_id=altro.id, set_number=1, weight_kg=30, reps=8),
    ])
    db.commit()

    lib.apply_duplicates(db, [["everkinetic:0199", "kilo:single-arm-overhead-cable-triceps-extension"]])
    assert a_mano.duplicate_of_id == disegni.id

    for esercizio in (disegni, a_mano):
        ultima = training_log.last_performance(db, profilo.id, [esercizio.id])[esercizio.id]
        assert [(s.weight_kg, s.reps) for s in ultima.sets] == [(10, 8)]
    assert set(training_log.same_exercise_ids(db, altro.id)) == {altro.id}


# --- Filtro per attrezzatura ------------------------------------------------------------


def test_filtro_attrezzatura(db):
    for eid, nome, att in [
        ("C", "Triceps Pushdown: Cable", "cable"), ("M", "Triceps Extension: Machine", "machine"),
        ("S", "Bench Press: Smith Machine (Close Grip)", "smith machine"),
        ("D", "Tate Press with Dumbbell", "dumbbell"), ("B", "JM Press", "barbell"),
        ("Z", "Lying Triceps Press", "e-z curl bar"), ("P", "Bench Dips", lib.BODYWEIGHT),
        ("X", "Triceps Dips", "parallel bars"),
    ]:
        _ex(db, lib.SOURCE_EVERKINETIC, eid, nome, "Triceps", equipment=att)
    profilo = _profilo()
    db.add(profilo)
    db.commit()

    def con(chiave):
        return {c.exercise.external_id for c in sw.find_candidates(db, profilo, "Triceps", equipment=chiave)}

    assert con("cavi") == {"C"}
    assert con("macchine") == {"M"}, "il multipower è a parte"
    assert con("multipower") == {"S"}
    assert con("manubri") == {"D"}
    assert con("bilanciere") == {"B", "Z"}
    assert con("corpo_libero") == {"P", "X"}
    assert len(con(None)) == len(con("sconosciuto")) == 8


def test_nota_vale_anche_per_il_doppione(db):
    from app.services import exercise_notes

    a_mano = _ex(db, lib.SOURCE_MANUAL, "single-arm-overhead-cable-triceps-extension", "Overhead", "Triceps",
                 in_catalog=True)
    disegni = _ex(db, lib.SOURCE_EVERKINETIC, "0199", "Overhead drawn", "Triceps", in_catalog=True)
    profilo = _profilo()
    db.add(profilo)
    db.commit()
    exercise_notes.set_note(db, profilo.id, a_mano.id, "Cavo alla tacca 3")
    lib.apply_duplicates(db, [["everkinetic:0199", "kilo:single-arm-overhead-cable-triceps-extension"]])
    assert exercise_notes.notes_for(db, profilo.id, [disegni.id]) == {disegni.id: "Cavo alla tacca 3"}
