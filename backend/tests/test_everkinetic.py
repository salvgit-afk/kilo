"""Test del catalogo Everkinetic (disegni) e dei controlli sulle traduzioni.

Nessuna rete: il dataset è costruito a mano e l'LLM è sostituito.
"""

from __future__ import annotations

import pytest

from app.models import Exercise
from app.services import exercise_library as lib
from app.services import translation
from app.services import workout_generator as wg


def _voce(id_, title, primary, *, type_="isolation", equipment=("barbell",),
          steps=("Passo uno.", "Passo due."), secondary=()):
    return {
        "id": id_, "title": title, "name": title.lower(), "type": type_,
        "primary": [primary], "secondary": list(secondary),
        "equipment": list(equipment), "steps": list(steps), "tips": [],
        "svg": [f"svg/{id_}-relaxation.svg", f"svg/{id_}-tension.svg"],
    }


def test_panca_piana():
    c = lib.parse_everkinetic_entry(
        _voce("0042", "Bench Press: Barbell", "pectoralis major", type_="compound",
              equipment=("bench", "barbell"), secondary=("triceps brachii",))
    )
    assert c["primary_muscle"] == "Chest"
    assert c["is_compound"] and c["priority"] == 0
    assert c["equipment"] == "bench, barbell"
    assert c["secondary_muscles"] == "Triceps"
    assert len(c["demo_images"]) == 2 and c["demo_images"][0].endswith("0042-relaxation.svg")


def test_classificazione_ricavata_dal_movimento():
    """Il dataset marca le trazioni "isolation": da questo dipendono recuperi
    e ripetizioni, quindi la classificazione si ricalcola."""
    trazioni = lib.parse_everkinetic_entry(_voce("0087", "Pull Ups", "latissimus dorsi", equipment=("bar",)))
    assert trazioni["is_compound"] and trazioni["equipment"] == "pull-up bar"

    pushdown = lib.parse_everkinetic_entry(
        _voce("0206", "Triceps Pushdown: Cable (Rope)", "triceps brachii", equipment=("cable",))
    )
    assert not pushdown["is_compound"]

    stretta = lib.parse_everkinetic_entry(_voce("0049", "Bench Press: Barbell (Close Grip)", "pectoralis major"))
    assert stretta["primary_muscle"] == "Triceps" and stretta["is_compound"]

    affondi = lib.parse_everkinetic_entry(
        _voce("0115", "Lunges: Dumbbell", "ischiocrural muscles", equipment=("dumbbells",))
    )
    assert affondi["primary_muscle"] == "Quads" and affondi["equipment"] == "dumbbell"


@pytest.mark.parametrize(
    "voce",
    [
        _voce("0113", "Side Plank", "abdominals"),
        _voce("0001", "Static Neck Flexion and Extension", "trapezius", type_="isometric"),
        _voce("0103", "Hyperextensions", "erector spinae"),
        {**_voce("0500", "Senza disegni", "deltoid"), "svg": []},
    ],
)
def test_voci_escluse(voce):
    assert lib.parse_everkinetic_entry(voce) is None


def test_corpo_libero():
    c = lib.parse_everkinetic_entry(_voce("0077", "Push Up: Body Weight", "pectoralis major", equipment=("body",)))
    assert c["equipment"] == wg.BODYWEIGHT and c["is_compound"]


def test_fonti_convivono_e_il_doppione_lascia_il_disegno(db):
    foto = {
        "id": "Barbell_Bench_Press_-_Medium_Grip", "name": "Barbell Bench Press",
        "category": "strength", "mechanic": "compound", "equipment": "barbell",
        "primaryMuscles": ["chest"], "secondaryMuscles": [], "instructions": ["a"],
        "images": ["x/0.jpg", "x/1.jpg"],
    }
    lib.sync_library(db, dataset=[foto])
    lib.sync_library(db, dataset=[_voce("0042", "Bench Press: Barbell", "pectoralis major")],
                     source=lib.SOURCE_EVERKINETIC)
    assert sorted(e.source for e in wg._pick_exercises(db, "Chest", None, wanted=2)) == [
        lib.SOURCE_EVERKINETIC, lib.SOURCE,
    ]

    # Stesso esercizio in due fonti: resta il disegno.
    lib.apply_duplicates(db, groups=[["everkinetic:0042", "free_exercise_db:Barbell_Bench_Press_-_Medium_Grip"]])
    assert [e.source for e in wg._pick_exercises(db, "Chest", None, wanted=2)] == [lib.SOURCE_EVERKINETIC]


def test_esercizi_non_tradotti_restano_visibili_in_inglese(db):
    lib.sync_library(
        db,
        dataset=[
            _voce("0042", "Bench Press: Barbell", "pectoralis major"),
            _voce("0055", "Bench Press: Dumbbell", "pectoralis major", equipment=("dumbbells",)),
        ],
        source=lib.SOURCE_EVERKINETIC,
    )
    panca = db.query(Exercise).filter_by(external_id="0042").one()
    panca.name_it = "Panca piana con bilanciere"
    db.commit()

    # Anche la panca con manubri, non ancora tradotta, resta disponibile: il
    # nome originale si vede finché la traduzione in background non arriva.
    scelti = wg._pick_exercises(db, "Chest", None, wanted=2)
    assert sorted(e.external_id for e in scelti) == ["0042", "0055"]


@pytest.mark.parametrize(
    "nome,atteso",
    [
        ("Panca piana con bilanciere", []),
        ("Lat machine presa larga", []),
        ("Pushdown ai cavi con corda", []),
        ("Leg press", []),
        ("Bench press con manubri", ["bench", "press"]),
        ("Curl alternato with dumbbell", ["with", "dumbbell"]),
    ],
)
def test_parole_inglesi_nel_nome(nome, atteso):
    assert translation.english_leftovers(nome) == atteso


def _esercizio(db):
    lib.sync_library(
        db,
        dataset=[_voce("0042", "Bench Press: Barbell", "pectoralis major",
                       steps=("Lie on the bench.", "Lower the bar to your chest."))],
        source=lib.SOURCE_EVERKINETIC,
    )
    return db.query(Exercise).one()


def test_nome_con_parole_inglesi_viene_corretto_al_secondo_tentativo(db, monkeypatch):
    ex = _esercizio(db)
    passi = ["Sdraiati sulla panca con i piedi a terra.", "Abbassa il bilanciere fino al petto."]
    risposte = iter([
        {"esercizi": [{"id": ex.id, "nome": "Bench press con bilanciere", "esecuzione": passi, "consigli": [], "focus": ["Spingi con il petto."]}]},
        {"esercizi": [{"id": ex.id, "nome": "Panca piana con bilanciere", "esecuzione": passi, "consigli": [], "focus": ["Spingi con il petto."]}]},
    ])
    prompt_inviati = []

    def finta(prompt, *a, **k):
        prompt_inviati.append(prompt)
        return next(risposte)

    monkeypatch.setattr("app.services.llm_client.generate_structured", finta)
    assert translation.translate_exercises(db, [ex]) == 1
    assert ex.name_it == "Panca piana con bilanciere"
    assert len(prompt_inviati) == 2 and "da_correggere" in prompt_inviati[1]


def test_esecuzione_rimasta_in_inglese_non_viene_salvata(db, monkeypatch):
    ex = _esercizio(db)
    inglese = ["Lie on the bench and keep your feet flat.", "Lower the bar to your chest until it touches."]
    monkeypatch.setattr(
        "app.services.llm_client.generate_structured",
        lambda *a, **k: {"esercizi": [{"id": ex.id, "nome": "Panca piana con bilanciere",
                                        "esecuzione": inglese, "consigli": [], "focus": []}]},
    )
    assert translation.translate_exercises(db, [ex]) == 1
    assert ex.name_it == "Panca piana con bilanciere"
    assert ex.instructions_it is None
