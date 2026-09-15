"""Esercizi assenti da tutti i cataloghi, scritti a mano.

Sono varianti comuni nelle palestre che nessuna delle fonti (Everkinetic, RepDB,
free-exercise-db) contiene. Seguono lo stesso formato degli esercizi importati:

  - nome e passaggi in inglese, come nelle fonti, così la ricerca per nome
    originale funziona anche qui;
  - nome, esecuzione, consigli e focus già in italiano, scritti con le stesse
    regole del prompt di traduzione (`translation._EXERCISE_PROMPT`): nome
    breve, imperativo con il tu, niente carichi, serie o promesse di risultati.

Non hanno immagini: nessuna fonte con licenza compatibile le fornisce.
L'interfaccia lo dichiara.
"""

from __future__ import annotations

MANUAL_EXERCISES: list[dict] = [
    {
        "external_id": "bayesian-cable-curl",
        "name": "Bayesian Cable Curl",
        "primary_muscle": "Biceps",
        "secondary_muscles": "Forearms",
        "equipment": "cable",
        "is_compound": False,
        "instructions": [
            "Set a single handle on a low pulley and stand facing away from the machine.",
            "Hold the handle with one hand, palm forward, and step forward so the arm is pulled slightly behind your body.",
            "Keep your elbow pointing down and your upper arm still, then curl the handle up by bending the elbow.",
            "Squeeze the biceps at the top, then lower the handle slowly until the arm is straight and behind the body again.",
            "Complete the reps, then repeat with the other arm.",
        ],
        "tips": [
            "Keep the torso upright: leaning forward shortens the stretch.",
            "Do not let the elbow drift forward as you curl.",
        ],
        "name_it": "Bayesian curl ai cavi",
        "instructions_it": [
            "Monta una maniglia singola sul cavo basso e mettiti in piedi dando le spalle alla macchina.",
            "Afferra la maniglia con una mano, palmo in avanti, e fai un passo avanti così che il braccio resti leggermente dietro il corpo.",
            "Tieni il gomito rivolto verso il basso e il braccio fermo, poi porta la maniglia verso l'alto piegando il gomito.",
            "Contrai il bicipite in alto e riscendi lentamente fino a distendere il braccio, di nuovo dietro il corpo.",
            "Completa le ripetizioni e ripeti con l'altro braccio.",
        ],
        "tips_it": [
            "Tieni il busto dritto: sporgerti in avanti riduce l'allungamento.",
            "Non lasciare che il gomito si sposti in avanti durante la salita.",
        ],
        "focus_it": [
            "Senti il bicipite allungarsi quando il braccio torna dietro il corpo",
            "Porta su la maniglia muovendo solo l'avambraccio",
            "Gomito fermo e rivolto verso il basso per tutta la ripetizione",
        ],
    },
    {
        "external_id": "behind-back-cable-lateral-raise",
        "name": "Cable Lateral Raise Behind the Back",
        "primary_muscle": "Shoulders",
        "secondary_muscles": "Trapezius",
        "equipment": "cable",
        "is_compound": False,
        "instructions": [
            "Set a single handle on a low pulley and stand sideways to the machine.",
            "Grab the handle with the hand farther from the machine, passing the cable behind your back.",
            "Stand tall with a slight bend in the elbow and the hand slightly behind the hip.",
            "Raise the arm out to the side until it is roughly parallel to the floor.",
            "Lower slowly under control until the hand returns behind the hip.",
        ],
        "tips": [
            "Lead the movement with the elbow, not the hand.",
            "Avoid shrugging the shoulder toward the ear.",
        ],
        "name_it": "Alzate laterali dietro la schiena",
        "instructions_it": [
            "Monta una maniglia singola sul cavo basso e mettiti di fianco alla macchina.",
            "Afferra la maniglia con la mano più lontana dalla macchina, facendo passare il cavo dietro la schiena.",
            "Stai in piedi con il busto dritto, il gomito leggermente piegato e la mano appena dietro l'anca.",
            "Solleva il braccio lateralmente fino a portarlo circa parallelo al pavimento.",
            "Riscendi lentamente e sotto controllo fino a riportare la mano dietro l'anca.",
        ],
        "tips_it": [
            "Guida il movimento con il gomito, non con la mano.",
            "Evita di alzare la spalla verso l'orecchio.",
        ],
        "focus_it": [
            "Senti lavorare la parte laterale della spalla, non il trapezio",
            "Mantieni la tensione anche nel tratto basso del movimento",
            "Sali guidando con il gomito e scendi senza farti tirare dal cavo",
        ],
    },
    {
        "external_id": "low-to-high-cable-fly",
        "name": "Low-to-High Cable Fly",
        "primary_muscle": "Chest",
        "secondary_muscles": "Shoulders",
        "equipment": "cable",
        "is_compound": False,
        "instructions": [
            "Set both handles on the low pulleys of a cable crossover and stand in the middle.",
            "Grab a handle in each hand, take a step forward and keep a slight bend in the elbows, arms down and slightly out to the sides.",
            "Bring the handles up and together in an arc until they meet in front of your upper chest.",
            "Squeeze the chest for a moment at the top.",
            "Lower the handles slowly along the same arc until you feel a stretch in the chest.",
        ],
        "tips": [
            "Keep the elbow angle fixed: it is a fly, not a press.",
            "Keep the shoulders down and back.",
        ],
        "name_it": "Croci ai cavi dal basso",
        "instructions_it": [
            "Monta entrambe le maniglie sui cavi bassi della croce ai cavi e mettiti al centro.",
            "Afferra una maniglia per mano, fai un passo avanti e tieni i gomiti leggermente piegati, con le braccia in basso e un po' aperte.",
            "Porta le maniglie verso l'alto e verso il centro con un movimento ad arco, fino a farle incontrare davanti al petto alto.",
            "Contrai il petto per un istante in alto.",
            "Riscendi lentamente lungo lo stesso arco fino a sentire il petto allungarsi.",
        ],
        "tips_it": [
            "Tieni fisso l'angolo dei gomiti: è una croce, non una spinta.",
            "Tieni le spalle basse e indietro.",
        ],
        "focus_it": [
            "Porta le maniglie verso il centro pensando di stringere il petto",
            "Concentrati sulla parte alta del petto mentre sali",
            "Controlla la discesa fino a sentire il petto allungarsi",
        ],
    },
    {
        "external_id": "pendulum-squat",
        "name": "Pendulum Squat",
        "primary_muscle": "Quads",
        "secondary_muscles": "Glutes",
        "equipment": "machine",
        "is_compound": True,
        "instructions": [
            "Stand on the platform with your back against the pad and your shoulders under the shoulder pads.",
            "Place your feet about hip-width apart, slightly forward on the platform, and release the safety.",
            "Bend your knees and lower yourself along the machine's arc as deep as you can while keeping your back on the pad.",
            "Push through the whole foot to straighten your legs and return to the start.",
            "Reset the safety before stepping off the machine.",
        ],
        "tips": [
            "Keep your heels down throughout the movement.",
            "Do not lock the knees hard at the top.",
        ],
        "name_it": "Pendulum squat",
        "instructions_it": [
            "Sali sulla pedana con la schiena appoggiata allo schienale e le spalle sotto gli appositi cuscinetti.",
            "Posiziona i piedi circa alla larghezza delle anche, leggermente avanti sulla pedana, e sblocca la sicura.",
            "Piega le ginocchia e scendi seguendo l'arco della macchina fino alla profondità che raggiungi tenendo la schiena appoggiata.",
            "Spingi con tutta la pianta del piede per distendere le gambe e tornare alla posizione di partenza.",
            "Rimetti la sicura prima di scendere dalla macchina.",
        ],
        "tips_it": [
            "Tieni i talloni a terra per tutto il movimento.",
            "In alto non bloccare le ginocchia di scatto.",
        ],
        "focus_it": [
            "Senti lavorare i quadricipiti mentre scendi in profondità",
            "Spingi con tutto il piede, talloni sempre appoggiati",
            "Tieni la schiena ben aderente allo schienale",
        ],
    },
]
