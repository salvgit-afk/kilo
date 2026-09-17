"""Biomeccanica e suggerimenti dell'overlay esercizio.

Due contenuti, entrambi **calcolati** e non generati dall'LLM, così sono
uguali per tutti, verificabili e non consumano quota:

1. **Come si muove il corpo**: dal nome dell'esercizio si riconosce lo schema
   di movimento (squat, stacco, spinta orizzontale, rematore, curl...). Ogni
   schema dichiara articolazioni, azioni articolari, piano di movimento e
   indicazioni di forma. Le indicazioni vengono da anatomia e biomeccanica
   applicate: `biomechanics_technique.md` ricorda che raramente sono state
   testate sull'ipertrofia, e l'overlay lo dice.
   Se il nome non corrisponde a nessuno schema si ripiega sul movimento
   tipico del muscolo principale, senza indicazioni di forma inventate.

2. **Focus sul muscolo**: una mappa muscolo → nota, coerente con quello che
   lo studio in `exercise_choice_and_focus.md` ha misurato davvero (più
   crescita sui bicipiti, nessuna differenza sui quadricipiti), invece di una
   frase unica uguale per ogni esercizio. Più, dove la fonte lo documenta,
   cosa dice la ricerca sull'allenamento in allungamento per quel muscolo.

Per estendere: aggiungere uno schema a `PATTERNS` o una voce a `FOCUS_NOTES`
/ `LENGTHENED_NOTES`, con il test in `tests/test_exercise_guidance.py`.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.models import Exercise

PLANES = {
    "sagittale": "avanti e indietro, come piegare e distendere",
    "frontale": "di lato, allontanando o avvicinando al corpo",
    "trasversale": "in orizzontale o in rotazione",
}


@dataclass(frozen=True)
class Pattern:
    key: str
    name: str
    match: str  # espressione regolare sul nome inglese, in minuscolo
    joints: tuple[str, ...]
    actions: tuple[str, ...]
    plane: str
    cues: tuple[str, ...]
    muscles: tuple[str, ...] = ()  # se indicati, lo schema vale solo per questi muscoli


# L'ordine conta: vince il primo schema che corrisponde. I più specifici
# (leg curl, hip thrust) stanno prima di quelli generici (curl, squat).
PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        "leg_curl", "Flessione del ginocchio",
        r"leg curl|hamstring curl|nordic|glute[- ]ham|ball leg curl|lying curl",
        ("ginocchio",), ("flessione del ginocchio",), "sagittale",
        (
            "Bacino fermo contro la panca o il sedile: se si solleva, il carico è troppo alto.",
            "Torna fino a gamba quasi distesa, dove i femorali sono allungati.",
            "Discesa controllata, senza lasciar cadere il peso.",
        ),
        muscles=("Hamstrings", "Glutes"),
    ),
    Pattern(
        "leg_extension", "Estensione del ginocchio",
        r"leg extension|knee extension",
        ("ginocchio",), ("estensione del ginocchio",), "sagittale",
        (
            "Regola lo schienale in modo che il ginocchio sia allineato al perno della macchina.",
            "Scendi fino in fondo: la parte con il ginocchio piegato è quella in allungamento.",
            "Sali senza slancio e senza staccare i glutei dal sedile.",
        ),
    ),
    Pattern(
        "calf_raise", "Flessione plantare della caviglia",
        r"calf|calves|heel raise|toe raise|donkey",
        ("caviglia",), ("flessione plantare (salire sulle punte)", "dorsiflessione (scendere col tallone)"), "sagittale",
        (
            "Scendi con il tallone fino al massimo allungamento e fermati un istante.",
            "Sali sulle punte in modo controllato, senza rimbalzare in basso.",
            "Ginocchia distese allenano di più il gastrocnemio, piegate il soleo.",
        ),
        muscles=("Calves",),
    ),
    Pattern(
        "hip_thrust", "Estensione dell'anca",
        r"hip thrust|glute bridge|bridg|hip lift|hip raise|pull[- ]through|frog pump|reverse hyper|glute drive|hip extension",
        ("anca",), ("estensione dell'anca",), "sagittale",
        (
            "Spingi con i talloni e chiudi il movimento contraendo i glutei.",
            "In alto porta il bacino in leggera retroversione invece di inarcare la schiena.",
            "Mento verso il petto e costole basse, così il movimento resta sull'anca.",
        ),
        muscles=("Glutes", "Hamstrings"),
    ),
    Pattern(
        "hinge", "Cerniera d'anca",
        r"deadlift|dead lift|rack pull|good morning|romanian|rdl|stiff[- ]leg|swing|hyperextension|back extension|superman|jefferson",
        ("anca", "ginocchio", "colonna (stabile)"),
        ("flesso-estensione dell'anca", "leggera flessione del ginocchio"), "sagittale",
        (
            "Schiena neutra dall'inizio alla fine: il movimento avviene nell'anca, non nella colonna.",
            "Porta i fianchi indietro in discesa e tieni il carico vicino alle gambe.",
            "Risali estendendo l'anca, senza inarcare la zona lombare in alto.",
        ),
    ),
    Pattern(
        "lunge", "Squat su una gamba (affondo)",
        r"lunge|split squat|bulgarian|step[- ]up|pistol|single[- ]leg squat|skater",
        ("anca", "ginocchio", "caviglia"),
        ("flesso-estensione di anca e ginocchio", "dorsiflessione della caviglia"), "sagittale",
        (
            "Busto stabile e bacino dritto: evita di ruotare o cadere di lato.",
            "Il ginocchio avanti segue la direzione del piede, senza chiudersi verso l'interno.",
            "Spingi con tutto il piede della gamba davanti per risalire.",
        ),
    ),
    Pattern(
        "squat", "Squat",
        r"squat|leg press|hack|belt squat|thruster|wall sit",
        ("anca", "ginocchio", "caviglia"),
        ("flesso-estensione di anca e ginocchio", "dorsiflessione della caviglia"), "sagittale",
        (
            "Ginocchia nella stessa direzione delle punte dei piedi, anche in risalita.",
            "Scendi finché mantieni la schiena neutra e i talloni a terra: più profondità allunga di più i quadricipiti.",
            "Risali spingendo con tutto il piede, senza che il busto salga prima delle anche.",
        ),
    ),
    Pattern(
        "hip_abduction", "Abduzione / adduzione dell'anca",
        r"abduct|adduct|clamshell|clam|fire hydrant|side[- ]lying leg|lateral leg raise|hip circle|monster walk|band walk|lateral walk",
        ("anca",), ("abduzione o adduzione dell'anca",), "frontale",
        (
            "Bacino fermo: il movimento parte dall'anca, non dal busto che si inclina.",
            "Controlla anche il ritorno, senza far sbattere la macchina o l'elastico.",
        ),
    ),
    Pattern(
        "rear_delt", "Abduzione orizzontale della spalla",
        r"rear delt|reverse .*fl(y|ie)|back fly|face pull|rear lateral|bent[- ]over lateral|band pull[- ]apart|posterior",
        ("spalla", "scapole"), ("abduzione orizzontale della spalla", "retrazione delle scapole"), "trasversale",
        (
            "Tira con i gomiti larghi, portandoli indietro in linea con le spalle.",
            "Niente slancio del busto: il carico giusto è più leggero di quanto sembri.",
        ),
    ),
    Pattern(
        "fly", "Adduzione orizzontale della spalla",
        r"\bfly\b|flys|flye|flies|pec deck|cross ?over|butterfly|iron cross",
        ("spalla",), ("adduzione orizzontale della spalla",), "trasversale",
        (
            "Gomiti leggermente piegati e fissi: il movimento avviene solo nella spalla.",
            "Apri fino a sentire il petto allungato, senza spingere la spalla in avanti.",
            "Chiudi come se abbracciassi un albero, senza far toccare i pesi con slancio.",
        ),
        muscles=("Chest",),
    ),
    Pattern(
        "lateral_raise", "Abduzione della spalla",
        r"lateral raise|side lateral|laterals|lateral dumbbell raise|lateral cable|side raise|y[- ]raise|lu raise|scaption|deltoid raise|y[- ]fly",
        ("spalla",), ("abduzione della spalla",), "frontale",
        (
            "Gomiti leggermente piegati, sali fino all'altezza delle spalle.",
            "Guidi con i gomiti, non con le mani, e senza alzare le spalle verso le orecchie.",
            "Discesa lenta: senza slancio lavora il deltoide laterale, non il trapezio.",
        ),
    ),
    Pattern(
        "front_raise", "Flessione della spalla",
        r"front raise|front .*raise|front plate|front cable",
        ("spalla",), ("flessione della spalla",), "sagittale",
        (
            "Braccia quasi distese, sali fino all'altezza delle spalle.",
            "Busto fermo: se oscilli per sollevare, il carico è troppo.",
        ),
    ),
    Pattern(
        "upright_row", "Abduzione della spalla con flessione del gomito",
        r"upright row|high pull\b",
        ("spalla", "gomito", "scapole"), ("abduzione della spalla", "flessione del gomito", "elevazione delle scapole"), "frontale",
        (
            "Tira con i gomiti che salgono per primi, fino all'altezza delle spalle e non oltre.",
            "Presa non troppo stretta: se la spalla dà fastidio, allarga le mani.",
        ),
    ),
    Pattern(
        "shrug", "Elevazione delle scapole",
        r"shrug",
        ("scapole",), ("elevazione e abbassamento delle scapole",), "frontale",
        (
            "Sali dritto verso le orecchie, senza ruotare le spalle.",
            "Scendi fino a sentire il trapezio allungato.",
        ),
    ),
    Pattern(
        "straight_arm", "Estensione della spalla a braccia tese",
        r"straight[- ]arm|pullover",
        ("spalla",), ("estensione della spalla",), "sagittale",
        (
            "Gomiti quasi distesi e fissi: il movimento è solo nella spalla.",
            "Porta le mani verso le cosce senza piegare il busto in avanti.",
        ),
    ),
    Pattern(
        "vertical_pull", "Trazione verticale",
        r"pull[- ]?ups?\b|\bchin|pulldown|pull[- ]down|muscle[- ]up|rope climb",
        ("spalla", "scapole", "gomito"),
        ("adduzione ed estensione della spalla", "depressione delle scapole", "flessione del gomito"), "frontale",
        (
            "Inizia abbassando le scapole, poi porta i gomiti verso i fianchi.",
            "Petto verso la sbarra, senza dondolare il busto indietro.",
            "Torna fino a braccia distese, dove i dorsali sono allungati.",
        ),
        muscles=("Lats", "Biceps", "Trapezius"),
    ),
    Pattern(
        "row", "Trazione orizzontale (rematore)",
        r"\brow\b|rows|rowing|renegade|bench pull",
        ("spalla", "scapole", "gomito"),
        ("estensione della spalla", "retrazione delle scapole", "flessione del gomito"), "sagittale",
        (
            "Schiena neutra e busto fermo: non usare lo slancio per tirare.",
            "Tira con il gomito verso il fianco e avvicina le scapole alla fine.",
            "Allunga le braccia in avanti lasciando scivolare le scapole, senza curvare la schiena.",
        ),
    ),
    Pattern(
        "overhead_press", "Spinta verticale",
        r"overhead press|shoulder press|military|push press|arnold|landmine press|jerk|press overhead|bradford|z press|seated press|standing press|pike push|handstand|behind the neck press|bottoms[- ]up press|seesaw press|kettlebell press|cuban press",
        ("spalla", "gomito", "scapole"),
        ("flessione e abduzione della spalla", "estensione del gomito", "rotazione verso l'alto delle scapole"), "frontale",
        (
            "Addome e glutei contratti: evita di inarcare la zona lombare per spingere.",
            "Il carico sale in linea sopra la testa, vicino al viso.",
            "Scendi fino all'altezza del mento o poco sotto, in modo controllato.",
        ),
    ),
    Pattern(
        "horizontal_press", "Spinta orizzontale",
        r"bench press|chest press|push[- ]?ups?\b|press[- ]?up|floor press|incline press|decline press|svend|guillotine|spoto|board press|pin press",
        ("spalla", "gomito", "scapole"),
        ("adduzione orizzontale e flessione della spalla", "estensione del gomito"), "trasversale",
        (
            "Scapole addotte e abbassate per tutta la serie: danno una base stabile alle spalle.",
            "Gomiti a circa 45° dal busto, non spalancati a 90°.",
            "Scendi controllato fino al petto o poco sopra, senza rimbalzare.",
        ),
    ),
    Pattern(
        "triceps_extension", "Estensione del gomito",
        r"triceps|tricep|pushdown|push[- ]down|kickback|skull ?crusher|french press|jm press|overhead extension|tate press|reverse extension|handle extension",
        ("gomito",), ("estensione del gomito",), "sagittale",
        (
            "Gomiti fermi: si muove solo l'avambraccio.",
            "Distendi completamente il braccio e torna fino a gomito ben piegato.",
            "Con il braccio sopra la testa il capo lungo lavora più allungato.",
        ),
    ),
    Pattern(
        "dip", "Spinta verso il basso (dip)",
        r"\bdips?\b|dip machine",
        ("spalla", "gomito"), ("estensione della spalla", "estensione del gomito"), "sagittale",
        (
            "Scendi finché le spalle restano comode, senza forzare in fondo.",
            "Busto più inclinato in avanti sposta il lavoro sul petto, più dritto sui tricipiti.",
        ),
    ),
    Pattern(
        "horizontal_press", "Spinta orizzontale",
        r"dumbbell press|machine press|cable press|smith press|bar press|close[- ]grip|dumbbell bench|chain press",
        ("spalla", "gomito", "scapole"),
        ("adduzione orizzontale e flessione della spalla", "estensione del gomito"), "trasversale",
        (
            "Scapole addotte e abbassate per tutta la serie: danno una base stabile alle spalle.",
            "Gomiti a circa 45° dal busto, non spalancati a 90°.",
            "Scendi controllato fino al petto o poco sopra, senza rimbalzare.",
        ),
        muscles=("Chest", "Triceps"),
    ),
    Pattern(
        "overhead_press", "Spinta verticale",
        r"press",
        ("spalla", "gomito", "scapole"),
        ("flessione e abduzione della spalla", "estensione del gomito", "rotazione verso l'alto delle scapole"), "frontale",
        (
            "Addome e glutei contratti: evita di inarcare la zona lombare per spingere.",
            "Il carico sale in linea sopra la testa, vicino al viso.",
            "Scendi fino all'altezza del mento o poco sotto, in modo controllato.",
        ),
        muscles=("Shoulders",),
    ),
    Pattern(
        "wrist", "Flesso-estensione del polso",
        r"wrist|forearm",
        ("polso",), ("flessione ed estensione del polso",), "sagittale",
        ("Avambraccio appoggiato e fermo: si muove solo il polso.",),
    ),
    Pattern(
        "curl", "Flessione del gomito",
        r"curl",
        ("gomito",), ("flessione del gomito", "supinazione dell'avambraccio"), "sagittale",
        (
            "Gomiti fermi ai fianchi e busto immobile: niente slancio con la schiena.",
            "Scendi fino a braccio quasi disteso, dove il bicipite è allungato.",
            "Ruota il palmo verso l'alto salendo, se la presa lo permette.",
        ),
        muscles=("Biceps", "Forearms"),
    ),
    Pattern(
        "shoulder_rotation", "Rotazione della spalla",
        r"internal rotation|external rotation|cable rotation|band rotation",
        ("spalla",), ("rotazione interna o esterna della spalla",), "trasversale",
        (
            "Gomito fermo al fianco (o appoggiato): ruota solo l'avambraccio attorno al gomito.",
            "Carichi leggeri e movimento lento: sono muscoli piccoli della cuffia dei rotatori.",
        ),
        muscles=("Shoulders",),
    ),
    Pattern(
        "rotation", "Rotazione del tronco",
        r"twist|woodchop|wood chop|rotation|russian|landmine rotation|judo|windshield|pallof|windmill|landmine 180|halo|figure 8",
        ("colonna", "anca"), ("rotazione del tronco o resistenza alla rotazione",), "trasversale",
        (
            "La rotazione parte dal busto con il bacino stabile, senza strattoni.",
            "Addome contratto per tutta la serie.",
        ),
    ),
    Pattern(
        "side_bend", "Flessione laterale del tronco",
        r"side bend|oblique crunch|side crunch|side plank|side jackknife",
        ("colonna",), ("flessione laterale del tronco",), "frontale",
        ("Muoviti solo di lato, senza ruotare il busto in avanti o indietro.",),
    ),
    Pattern(
        "leg_raise", "Flessione dell'anca con retroversione del bacino",
        r"leg raise|knee raise|leg lift|knee tuck|leg tuck|hanging|jackknife|v[- ]up|v[- ]sit|pike|flutter|scissor|toes to bar|mountain climber|l[- ]sit|pull[- ]in|dragon flag|butt[- ]up",
        ("anca", "colonna"), ("flessione dell'anca", "retroversione del bacino"), "sagittale",
        (
            "Porta il bacino verso le costole alla fine: così lavora l'addome, non solo i flessori dell'anca.",
            "Zona lombare aderente o controllata, senza inarcarla in discesa.",
        ),
        muscles=("Abs",),
    ),
    Pattern(
        "crunch", "Flessione della colonna",
        r"crunch|sit[- ]?up|roll[- ]?up|rollout|ab wheel|ab roller|heel touch|elbow to knee|otis",
        ("colonna",), ("flessione del tronco",), "sagittale",
        (
            "Arrotola il busto avvicinando le costole al bacino, invece di tirare con il collo.",
            "Espira mentre ti chiudi e torna controllato.",
        ),
    ),
    Pattern(
        "anti_movement", "Stabilità del tronco (isometria)",
        r"plank|bird[- ]dog|dead ?bug|hollow|stir the pot|bear|carry|suitcase|farmer|lever|planche|human flag|get[- ]?up",
        ("colonna", "anca", "spalla"), ("mantenere la colonna neutra contro il carico",), "sagittale",
        (
            "Colonna neutra dalla testa al bacino: niente fianchi cadenti o sedere alto.",
            "Respira normalmente mantenendo l'addome contratto.",
        ),
    ),
    Pattern(
        "total_body", "Movimento esplosivo multi-articolare",
        r"clean|snatch|burpee|jump|sprint|sled|battle rope|slam|throw",
        ("anca", "ginocchio", "caviglia", "spalla"),
        ("estensione rapida di anca, ginocchio e caviglia",), "sagittale",
        (
            "La spinta parte dalle gambe e dall'anca, le braccia guidano il carico.",
            "Impara il movimento con carichi leggeri: la tecnica viene prima della velocità.",
        ),
    ),
)

# Movimento tipico del muscolo, quando il nome non corrisponde a nessuno schema.
MUSCLE_DEFAULTS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "Chest": (("spalla",), ("adduzione orizzontale della spalla",), "trasversale"),
    "Lats": (("spalla", "scapole"), ("adduzione ed estensione della spalla",), "sagittale"),
    "Shoulders": (("spalla",), ("flessione e abduzione della spalla",), "frontale"),
    "Biceps": (("gomito",), ("flessione del gomito",), "sagittale"),
    "Triceps": (("gomito",), ("estensione del gomito",), "sagittale"),
    "Quads": (("ginocchio", "anca"), ("estensione del ginocchio",), "sagittale"),
    "Hamstrings": (("ginocchio", "anca"), ("flessione del ginocchio", "estensione dell'anca"), "sagittale"),
    "Glutes": (("anca",), ("estensione e abduzione dell'anca",), "sagittale"),
    "Calves": (("caviglia",), ("flessione plantare della caviglia",), "sagittale"),
    "Abs": (("colonna",), ("flessione e stabilizzazione del tronco",), "sagittale"),
    "Trapezius": (("scapole",), ("elevazione e retrazione delle scapole",), "frontale"),
    "Forearms": (("polso",), ("flesso-estensione del polso",), "sagittale"),
    "Lower back": (("colonna", "anca"), ("estensione del tronco",), "sagittale"),
    "Adductors": (("anca",), ("adduzione dell'anca",), "frontale"),
}

# --- Focus sul muscolo (`exercise_choice_and_focus.md`, Schoenfeld 2018) -------

FOCUS_SUPPORTED = "supported"      # misurato: più crescita con il focus sul muscolo
FOCUS_NOT_SHOWN = "not_shown"      # misurato: nessuna differenza
FOCUS_UNTESTED = "untested"        # non misurato per questo muscolo

FOCUS_NOTES: dict[str, tuple[str, str]] = {
    "Biceps": (
        FOCUS_SUPPORTED,
        "Qui vale la pena: nello studio delle fonti concentrarsi sul bicipite mentre "
        "lavora ha dato più crescita (12,4% contro 6,9% in 8 settimane).",
    ),
    "Triceps": (
        FOCUS_UNTESTED,
        "Sui tricipiti non è stato misurato, ma il beneficio osservato riguarda i "
        "muscoli piccoli delle braccia come il bicipite: provarlo ha senso, "
        "soprattutto negli esercizi di isolamento.",
    ),
    "Forearms": (
        FOCUS_UNTESTED,
        "Non misurato sugli avambracci; il beneficio osservato riguarda i muscoli "
        "piccoli delle braccia, quindi provarlo ha senso.",
    ),
    "Quads": (
        FOCUS_NOT_SHOWN,
        "Sui quadricipiti concentrarsi sul muscolo non ha cambiato la crescita "
        "nello studio delle fonti: qui conta di più scendere in profondità con "
        "carico e controllo.",
    ),
    "Hamstrings": (
        FOCUS_NOT_SHOWN,
        "Sulle gambe lo studio non ha trovato differenze (misurate sui "
        "quadricipiti): per i femorali conta di più arrivare in allungamento.",
    ),
    "Glutes": (
        FOCUS_NOT_SHOWN,
        "Sulle gambe lo studio non ha trovato differenze (misurate sui "
        "quadricipiti): usa il focus se ti aiuta a sentire i glutei, ma la "
        "priorità è la tecnica.",
    ),
    "Calves": (
        FOCUS_NOT_SHOWN,
        "Sulle gambe lo studio non ha trovato differenze: per i polpacci conta "
        "di più scendere fino al massimo allungamento.",
    ),
    "Adductors": (
        FOCUS_NOT_SHOWN,
        "Sulle gambe lo studio non ha trovato differenze: la priorità è un "
        "movimento completo e controllato.",
    ),
}
FOCUS_DEFAULT = (
    FOCUS_UNTESTED,
    "Per questo muscolo non ci sono misure dirette: concentrarsi sul muscolo è un "
    "aiuto da provare, soprattutto negli esercizi di isolamento, non una regola.",
)
FOCUS_COMPOUND_NOTE = (
    " Negli esercizi multi-articolari, però, la priorità resta il movimento e il carico."
)

# --- Allenamento in allungamento (`biomechanics_technique.md`) -----------------

LENGTHENED_NOTES: dict[str, str] = {
    "Hamstrings": (
        "Il leg curl da seduti (anca piegata, femorali allungati) ha dato più "
        "crescita di quello da sdraiati: +14% contro +9% in 12 settimane."
    ),
    "Triceps": (
        "Le estensioni con il braccio sopra la testa hanno fatto crescere di più il "
        "tricipite (+19,9% contro +13,9%), soprattutto il capo lungo."
    ),
    "Calves": (
        "Lavorare nella parte bassa, con la caviglia in allungamento, ha fatto "
        "crescere il gastrocnemio più del movimento completo (+15,2% contro +6,7%)."
    ),
    "Quads": (
        "Nella leg extension la parte con il ginocchio piegato ha dato più crescita "
        "di quella finale: non fermarti a metà."
    ),
    "Biceps": (
        "Nei soggetti allenati, parziali in allungamento e movimento completo hanno "
        "dato risultati simili: conta arrivare fino a braccio disteso."
    ),
}


@dataclass
class ExerciseGuidance:
    pattern: str | None
    movement: str
    joints: list[str]
    actions: list[str]
    plane: str
    plane_hint: str
    cues: list[str] = field(default_factory=list)
    focus_evidence: str = FOCUS_UNTESTED
    focus_note: str = ""
    lengthened_note: str | None = None
    knowledge_tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def match_pattern(exercise: Exercise) -> Pattern | None:
    nome = f"{exercise.name or ''}".lower()
    for pattern in PATTERNS:
        if pattern.muscles and exercise.primary_muscle not in pattern.muscles:
            continue
        if re.search(pattern.match, nome):
            return pattern
    return None


def build(exercise: Exercise) -> ExerciseGuidance:
    muscolo = exercise.primary_muscle or ""
    pattern = match_pattern(exercise)

    if pattern is not None:
        movimento, articolazioni, azioni, piano, cues = (
            pattern.name, list(pattern.joints), list(pattern.actions), pattern.plane, list(pattern.cues)
        )
    else:
        articolazioni, azioni, piano = MUSCLE_DEFAULTS.get(
            muscolo, ((), ("movimento specifico dell'esercizio",), "sagittale")
        )
        movimento, articolazioni, azioni, cues = (
            "Movimento tipico del muscolo principale", list(articolazioni), list(azioni), []
        )

    evidenza, nota = FOCUS_NOTES.get(muscolo, FOCUS_DEFAULT)
    if exercise.is_compound and evidenza != FOCUS_NOT_SHOWN:
        nota += FOCUS_COMPOUND_NOTE

    allungamento = LENGTHENED_NOTES.get(muscolo)
    tags = ["focus_attentivo", "tecnica_esecuzione"]
    if allungamento:
        tags.append("ampiezza_movimento")

    return ExerciseGuidance(
        pattern=pattern.key if pattern else None,
        movement=movimento,
        joints=articolazioni,
        actions=azioni,
        plane=piano,
        plane_hint=PLANES[piano],
        cues=cues,
        focus_evidence=evidenza,
        focus_note=nota,
        lengthened_note=allungamento,
        knowledge_tags=tags,
    )
