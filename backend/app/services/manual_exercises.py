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
    {
        "external_id": "single-arm-overhead-cable-triceps-extension",
        "name": "Single-Arm Overhead Cable Triceps Extension",
        "primary_muscle": "Triceps",
        "secondary_muscles": None,
        "equipment": "cable",
        "is_compound": False,
        "instructions": [
            "Set a single handle on a low pulley and stand facing away from the machine.",
            "Grab the handle with one hand and bring it over your head, elbow bent and pointing up, with the cable running behind your back.",
            "Take a small step forward and keep the torso upright, with the free hand on your hip or supporting the working elbow.",
            "Keeping the upper arm still next to your head, straighten the elbow until the arm is fully extended above you.",
            "Lower the handle slowly behind your head until you feel the triceps stretch, then repeat and switch arms.",
        ],
        "tips": [
            "Keep the elbow pointing up: do not let it drift out to the side.",
            "Do not arch the lower back to move the handle.",
        ],
        "name_it": "Estensioni monolaterali sopra la testa",
        "instructions_it": [
            "Monta una maniglia singola sul cavo basso e mettiti in piedi dando le spalle alla macchina.",
            "Afferra la maniglia con una mano e portala sopra la testa, con il gomito piegato rivolto verso l'alto e il cavo che passa dietro la schiena.",
            "Fai un piccolo passo avanti e tieni il busto dritto, con la mano libera sul fianco o a sostenere il gomito che lavora.",
            "Tenendo fermo il braccio vicino alla testa, distendi il gomito fino ad allungare completamente il braccio sopra di te.",
            "Riporta lentamente la maniglia dietro la testa fino a sentire il tricipite allungarsi, poi ripeti e cambia braccio.",
        ],
        "tips_it": [
            "Tieni il gomito rivolto verso l'alto: non lasciarlo scivolare di lato.",
            "Non inarcare la zona lombare per muovere la maniglia.",
        ],
        "focus_it": [
            "Senti il tricipite allungarsi quando la maniglia scende dietro la testa",
            "Muovi solo l'avambraccio, il braccio resta fermo vicino alla testa",
            "Distendi il gomito fino in fondo contraendo il tricipite",
        ],
    },
    {
        "external_id": "cross-body-cable-triceps-extension",
        "name": "Cross-Body Cable Triceps Extension",
        "primary_muscle": "Triceps",
        "secondary_muscles": None,
        "equipment": "cable",
        "is_compound": False,
        "instructions": [
            "Set a single handle on a pulley at about head height and stand sideways to the machine.",
            "Grab the handle with the hand farther from the machine, so the cable crosses in front of your body.",
            "Start with the elbow bent and pointing forward at shoulder height, the hand close to the opposite shoulder.",
            "Straighten the elbow, moving the hand out to the side and away from the machine, until the arm is fully extended.",
            "Return slowly to the start keeping the elbow at the same height, then repeat and switch arms.",
        ],
        "tips": [
            "Keep the elbow still: only the forearm moves.",
            "Do not rotate the torso to help the movement.",
        ],
        "name_it": "Estensioni tricipiti incrociate al cavo",
        "instructions_it": [
            "Monta una maniglia singola su un cavo all'altezza della testa e mettiti di fianco alla macchina.",
            "Afferra la maniglia con la mano più lontana dalla macchina, così che il cavo passi davanti al corpo.",
            "Parti con il gomito piegato, rivolto in avanti all'altezza della spalla, e la mano vicina alla spalla opposta.",
            "Distendi il gomito portando la mano di lato, lontano dalla macchina, fino ad allungare completamente il braccio.",
            "Torna lentamente alla posizione di partenza tenendo il gomito alla stessa altezza, poi ripeti e cambia braccio.",
        ],
        "tips_it": [
            "Tieni fermo il gomito: si muove solo l'avambraccio.",
            "Non ruotare il busto per aiutarti.",
        ],
        "focus_it": [
            "Senti lavorare il tricipite mentre la mano si allontana dalla spalla",
            "Gomito fermo alla stessa altezza per tutta la ripetizione",
            "Controlla il ritorno senza farti tirare dal cavo",
        ],
    },
    {
        "external_id": "single-arm-high-cable-reverse-fly",
        "name": "Single-Arm High Cable Reverse Fly",
        "primary_muscle": "Shoulders",
        "secondary_muscles": "Trapezius",
        "equipment": "cable",
        "is_compound": False,
        "instructions": [
            "Set a single handle on a high pulley, at about head height or slightly above, and stand facing the machine.",
            "Grab the handle with the opposite hand, so the arm starts crossed in front of your chest.",
            "With a slight bend in the elbow, pull the arm out and back in a wide arc until it is in line with your shoulder.",
            "Pause for a moment, then return slowly along the same arc until the arm crosses in front of you again.",
            "Complete the reps, then repeat with the other arm.",
        ],
        "tips": [
            "Move from the shoulder: do not turn the torso to finish the rep.",
            "Keep the elbow angle fixed throughout.",
        ],
        "name_it": "Croce inversa monolaterale al cavo alto",
        "instructions_it": [
            "Monta una maniglia singola sul cavo alto, all'altezza della testa o poco sopra, e mettiti di fronte alla macchina.",
            "Afferra la maniglia con la mano del lato opposto, così che il braccio parta incrociato davanti al petto.",
            "Con il gomito leggermente piegato, porta il braccio in fuori e indietro con un ampio arco, fino ad allinearlo alla spalla.",
            "Fermati un istante, poi torna lentamente lungo lo stesso arco finché il braccio incrocia di nuovo davanti a te.",
            "Completa le ripetizioni e ripeti con l'altro braccio.",
        ],
        "tips_it": [
            "Muovi il braccio dalla spalla: non ruotare il busto per finire la ripetizione.",
            "Tieni fisso l'angolo del gomito per tutto il movimento.",
        ],
        "focus_it": [
            "Senti lavorare la parte posteriore della spalla mentre apri il braccio",
            "Apri il braccio senza ruotare il busto",
            "Controlla il ritorno fino a incrociare davanti al petto",
        ],
    },
    {
        "external_id": "chest-supported-dumbbell-lateral-raise",
        "name": "Chest-Supported Dumbbell Lateral Raise",
        "primary_muscle": "Shoulders",
        "secondary_muscles": "Trapezius",
        "equipment": "dumbbell, incline bench",
        "is_compound": False,
        "instructions": [
            "Set an incline bench at a low angle and lie face down with your chest on the backrest and your feet on the floor.",
            "Hold a dumbbell in each hand, arms hanging down with a slight bend in the elbows.",
            "Raise the dumbbells out to the sides, slightly forward of the body, until the arms are roughly parallel to the floor.",
            "Pause briefly at the top, then lower slowly back to the start.",
        ],
        "tips": [
            "Keep the chest on the pad: do not lift the torso to help.",
            "Lead with the elbows and raise the arms to the sides, not backward.",
        ],
        "name_it": "Alzate laterali con petto appoggiato",
        "instructions_it": [
            "Regola una panca inclinata con poca pendenza e sdraiati a pancia in giù, con il petto sullo schienale e i piedi a terra.",
            "Tieni un manubrio per mano, con le braccia verso il basso e i gomiti leggermente piegati.",
            "Solleva i manubri lateralmente, un po' in avanti rispetto al corpo, fino a portare le braccia circa parallele al pavimento.",
            "Fermati un istante in alto, poi riscendi lentamente fino alla posizione di partenza.",
        ],
        "tips_it": [
            "Tieni il petto appoggiato: non sollevare il busto per aiutarti.",
            "Guida con i gomiti e alza le braccia di lato, non all'indietro.",
        ],
        "focus_it": [
            "Senti lavorare la parte laterale della spalla, non il trapezio",
            "Petto sempre appoggiato, nessuno slancio dal busto",
            "Scendi lentamente mantenendo la tensione sulla spalla",
        ],
    },
]

# Nomi italiani scelti a mano per esercizi delle fonti, al posto della
# traduzione automatica: dove il nome tradotto non dice l'altezza del cavo o
# la posizione, varianti diverse sembrano lo stesso esercizio. Chiave
# "sorgente:id"; valgono anche dopo una nuova traduzione.
NAME_IT_OVERRIDES: dict[str, str] = {
    "repdb:cable-fly": "Croci ai cavi dall'alto",
    "everkinetic:0048": "Croci ai cavi a metà altezza",
    "free_exercise_db:Cable_Rear_Delt_Fly": "Croci inverse ai cavi incrociati a X",
    "everkinetic:0035": "Alzate posteriori ai cavi da seduto",
    "everkinetic:0017": "Alzata posteriore monolaterale al cavo basso",
    # A un braccio, col cavo davanti al corpo: si distingue così da quelle
    # "dietro la schiena" e si trova cercando "braccio singolo".
    "repdb:cable-lateral-raise": "Alzate laterali monolaterali al cavo basso",
    # Il curl a martello con la corda al cavo basso: "corda" e "martello" nel
    # nome, come lo si cerca.
    "everkinetic:0216": "Curl a martello al cavo con corda",
    # La hyperextension alla panca a 45° (col disco al petto per caricarla),
    # nel catalogo per i femorali: vedi `EVERKINETIC_PRIMARY_OVERRIDE`.
    "everkinetic:0103": "Hyperextension per femorali",
    "free_exercise_db:One-Arm_Incline_Lateral_Raise": "Alzate laterali su panca inclinata",
    "repdb:side-lying-lateral-raise": "Alzate laterali sdraiato su un fianco",
    "free_exercise_db:Cable_Rope_Overhead_Triceps_Extension": "French press al cavo basso con corda",
    # La versione con i disegni di "Estensioni monolaterali sopra la testa",
    # scritta a mano quando questa era nascosta per errore fra i doppioni del
    # pushdown a un braccio: nome simile, così si riconosce.
    "everkinetic:0199": "Estensioni monolaterali al cavo sopra la testa",
    "everkinetic:0166": "Pushdown a un braccio con presa inversa",
    # Adduttori e abduttori: come si chiamano le macchine in palestra.
    "everkinetic:0157": "Adductor machine",
    "everkinetic:0156": "Abductor machine",
    "everkinetic:0135": "Adduzioni al cavo basso",
    "repdb:banded-standing-hip-adduction": "Adduzioni in piedi con elastico",
    "repdb:side-lying-hip-adduction": "Adduzioni sdraiato su un fianco",
}
