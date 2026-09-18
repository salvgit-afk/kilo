"""Ricette Kilo: raccolta curata di ricette italiane con dosi in grammi.

Perché esistono: le ricette di TheMealDB hanno quantità in linguaggio comune
("¼ cup", "1 clove") che vanno stimate, e sono spesso lontane da un pasto di
chi si allena. Queste sono scritte apposta: ogni ingrediente ha i suoi
grammi, quindi i macro sono **calcolati**, non stimati, e l'analisi non
chiama mai il modello.

Come sono scritte:

- piatti comuni della cucina di casa e della cucina fit italiana, con
  procedimenti scritti da zero con parole nostre (nessun testo copiato);
- dosi di partenza coerenti con le porzioni standard LARN
  (`knowledge_base/standard_portions.md`), alzate dove il piatto è pensato
  come fonte proteica principale del pasto;
- `en` è il nome generico con cui si cerca l'alimento su USDA: il catalogo è
  in inglese, e un nome generico ("chicken breast") trova l'alimento crudo
  invece di un prodotto di marca.

Per aggiungerne una: una voce in `RECIPES`, con il test in
`tests/test_kilo_recipes.py` che controlla dosi e categorie. Prima di
committarla, `scripts/check_kilo_recipes.py` verifica che ogni ingrediente
trovi l'alimento giusto su USDA.
"""

from __future__ import annotations

from dataclasses import dataclass

OMNIVORE = "omnivore"
VEGETARIAN = "vegetarian"
VEGAN = "vegan"


@dataclass(frozen=True)
class KiloIngredient:
    it: str  # come lo legge l'utente
    en: str  # come si cerca su USDA
    grams: float


@dataclass(frozen=True)
class KiloRecipe:
    slug: str
    name: str
    category: str
    servings: int
    minutes: int
    diet: str
    ingredients: tuple[KiloIngredient, ...]
    steps: str
    # Parole con cui la si trova oltre al nome e agli ingredienti.
    keywords: tuple[str, ...] = ()

    @property
    def meal_id(self) -> str:
        return f"kilo:{self.slug}"


def _i(it: str, en: str, grams: float) -> KiloIngredient:
    return KiloIngredient(it, en, grams)


OLIO = ("olio extravergine d'oliva", "olive oil")

RECIPES: tuple[KiloRecipe, ...] = (
    # --- Colazione -----------------------------------------------------------------
    KiloRecipe(
        "porridge-proteico", "Porridge proteico ai mirtilli", "Colazione", 1, 10, VEGETARIAN,
        (
            _i("fiocchi d'avena", "oats", 60),
            _i("albume", "egg white", 150),
            _i("latte parzialmente scremato", "lowfat milk", 150),
            _i("mirtilli", "blueberries", 60),
            _i("burro d'arachidi", "peanut butter", 10),
        ),
        "Scalda latte e avena in un pentolino per 3-4 minuti mescolando. Togli dal fuoco, "
        "aggiungi l'albume a filo continuando a mescolare e rimetti sul fuoco basso un minuto, "
        "finché si addensa. Completa con mirtilli e burro d'arachidi.",
        ("avena", "porridge", "colazione proteica"),
    ),
    KiloRecipe(
        "yogurt-bowl", "Yogurt bowl con frutta secca", "Colazione", 1, 5, VEGETARIAN,
        (
            _i("yogurt greco magro", "greek yogurt nonfat plain", 250),
            _i("fiocchi d'avena", "oats", 30),
            _i("bananas raw", "bananas raw", 100),
            _i("noci", "walnuts", 15),
            _i("miele", "honey", 10),
        ),
        "Versa lo yogurt in una ciotola, aggiungi l'avena, la banana a rondelle e le noci "
        "spezzettate. Finisci con un filo di miele.",
        ("yogurt", "bowl", "colazione veloce"),
    ),
    KiloRecipe(
        "pancake-avena-albume", "Pancake avena e albume", "Colazione", 1, 15, VEGETARIAN,
        (
            _i("fiocchi d'avena", "oats", 50),
            _i("albume", "egg white", 150),
            _i("bananas raw", "bananas raw", 60),
            _i("yogurt greco magro", "greek yogurt nonfat plain", 100),
            _i("frutti di bosco", "raspberries", 50),
        ),
        "Frulla avena, albume e banana fino a un impasto liscio. Cuoci a cucchiaiate in una "
        "padella antiaderente calda, un paio di minuti per lato. Servi con yogurt e frutti di "
        "bosco.",
        ("pancake", "avena", "colazione proteica"),
    ),
    KiloRecipe(
        "toast-uova-avocado", "Toast integrale con uova e avocado", "Colazione", 1, 10, VEGETARIAN,
        (
            _i("pane integrale", "whole wheat bread", 60),
            _i("uova", "egg", 100),
            _i("avocado", "avocado", 50),
            _i("pomodorini", "tomatoes red ripe raw", 60),
        ),
        "Tosta il pane. Cuoci le uova strapazzate in padella antiaderente senza grassi. "
        "Schiaccia l'avocado sul pane, aggiungi le uova e i pomodorini a spicchi, un pizzico "
        "di sale e pepe.",
        ("toast", "uova", "avocado"),
    ),
    KiloRecipe(
        "ricotta-cacao", "Crema di ricotta al cacao con fette biscottate", "Colazione", 1, 5, VEGETARIAN,
        (
            _i("ricotta vaccina", "ricotta cheese part skim", 150),
            _i("cacao amaro", "cocoa powder unsweetened", 8),
            _i("miele", "honey", 10),
            _i("fette biscottate integrali", "melba toast wheat", 30),
            _i("fragole", "strawberries", 100),
        ),
        "Lavora la ricotta con cacao e miele fino a una crema liscia. Spalmala sulle fette "
        "biscottate e accompagna con le fragole.",
        ("ricotta", "cacao", "colazione dolce"),
    ),
    KiloRecipe(
        "overnight-oats", "Overnight oats con skyr e mela", "Colazione", 1, 5, VEGETARIAN,
        (
            _i("fiocchi d'avena", "oats", 50),
            _i("skyr (o yogurt greco magro)", "greek yogurt nonfat plain", 170),
            _i("latte parzialmente scremato", "lowfat milk", 100),
            _i("mela", "apples raw with skin", 120),
            _i("semi di chia", "chia seeds", 10),
        ),
        "La sera prima mescola avena, yogurt, latte e semi di chia in un barattolo e lascia in "
        "frigo. Al mattino aggiungi la mela a cubetti e una spolverata di cannella.",
        ("avena", "preparare in anticipo", "colazione veloce"),
    ),
    # --- Pollo e tacchino -------------------------------------------------------------
    KiloRecipe(
        "pollo-riso-zucchine", "Pollo, riso basmati e zucchine", "Pollo e tacchino", 1, 25, OMNIVORE,
        (
            _i("petto di pollo", "chicken breast", 150),
            _i("riso basmati", "white rice", 80),
            _i("zucchine", "zucchini", 200),
            (_i(*OLIO, 10)),
        ),
        "Cuoci il riso in acqua salata. Intanto taglia il pollo a bocconcini e rosolalo in "
        "padella con metà dell'olio, 6-7 minuti. Aggiungi le zucchine a rondelle e cuoci altri "
        "5 minuti. Servi sul riso con l'olio rimasto a crudo.",
        ("pollo", "riso", "pranzo classico", "meal prep"),
    ),
    KiloRecipe(
        "piadina-pollo", "Piadina di pollo e formaggio", "Pollo e tacchino", 1, 15, OMNIVORE,
        (
            _i("piadina", "flour tortilla", 100),
            _i("petto di pollo", "chicken breast", 120),
            _i("mozzarella light", "mozzarella part skim", 50),
            _i("concentrato di pomodoro", "tomato paste", 15),
            _i("lattuga", "lettuce", 30),
            (_i(*OLIO, 5)),
        ),
        "Cuoci il pollo a bocconcini in padella con l'olio e il concentrato di pomodoro, "
        "sale e paprika. Scalda la piadina, farciscila con mozzarella, pollo e lattuga e "
        "chiudila; ripassala un minuto per lato perché il formaggio si sciolga.",
        ("pollo", "piadina", "tacos", "veloce"),
    ),
    KiloRecipe(
        "pollo-limone-patate", "Pollo al limone con patate al forno", "Pollo e tacchino", 1, 40, OMNIVORE,
        (
            _i("petto di pollo", "chicken breast", 150),
            _i("patate", "potatoes", 200),
            _i("succo di limone", "lemon juice raw", 20),
            (_i(*OLIO, 10)),
        ),
        "Taglia le patate a spicchi, condiscile con metà dell'olio, sale e rosmarino e "
        "infornale a 200 °C per 30 minuti. Batti il pollo, cuocilo in padella con l'olio "
        "rimasto e sfuma con il limone negli ultimi 2 minuti.",
        ("pollo", "limone", "patate", "forno"),
    ),
    KiloRecipe(
        "insalata-pollo-ceci", "Insalata di pollo, ceci e feta", "Pollo e tacchino", 1, 15, OMNIVORE,
        (
            _i("petto di pollo", "chicken breast", 120),
            _i("ceci lessati", "chickpeas cooked", 100),
            _i("feta", "feta cheese", 30),
            _i("cetriolo", "cucumber with peel raw", 100),
            _i("pomodorini", "tomatoes red ripe raw", 100),
            (_i(*OLIO, 10)),
        ),
        "Cuoci il pollo alla piastra e taglialo a strisce. Unisci in una ciotola ceci "
        "sciacquati, cetriolo e pomodorini a pezzi, la feta sbriciolata e il pollo. Condisci "
        "con olio, sale e origano.",
        ("pollo", "insalata", "ceci", "pranzo freddo"),
    ),
    KiloRecipe(
        "tacchino-funghi-quinoa", "Straccetti di tacchino ai funghi con quinoa", "Pollo e tacchino", 1, 25, OMNIVORE,
        (
            _i("fesa di tacchino", "turkey breast meat only raw", 150),
            _i("quinoa uncooked", "quinoa uncooked", 70),
            _i("funghi champignon", "mushrooms", 150),
            (_i(*OLIO, 10)),
        ),
        "Cuoci la quinoa in acqua per 15 minuti. Rosola i funghi a fettine in padella con "
        "l'olio e uno spicchio d'aglio, poi aggiungi il tacchino a straccetti e cuoci 4-5 "
        "minuti a fuoco vivo. Servi sulla quinoa con prezzemolo.",
        ("tacchino", "funghi", "quinoa uncooked"),
    ),
    KiloRecipe(
        "polpette-tacchino", "Polpette di tacchino al sugo", "Pollo e tacchino", 2, 35, OMNIVORE,
        (
            _i("macinato di tacchino", "ground turkey 93% lean raw", 300),
            _i("uovo", "egg", 50),
            _i("pangrattato", "bread crumbs", 30),
            _i("parmigiano grattugiato", "parmesan cheese grated", 20),
            _i("passata di pomodoro", "tomato products canned puree", 300),
            (_i(*OLIO, 10)),
        ),
        "Impasta tacchino, uovo, pangrattato e parmigiano con un pizzico di sale e forma "
        "polpette piccole. Scalda la passata con l'olio e un po' di basilico, aggiungi le "
        "polpette e cuoci coperto a fuoco basso per 20 minuti.",
        ("tacchino", "polpette", "sugo", "meal prep"),
    ),
    # --- Pesce --------------------------------------------------------------------------
    KiloRecipe(
        "salmone-patate-dolci", "Salmone al forno con patate dolci", "Pesce", 1, 35, OMNIVORE,
        (
            _i("filetto di salmone", "salmon atlantic", 150),
            _i("patate dolci", "sweet potato raw unprepared", 200),
            _i("broccoli", "broccoli", 150),
            (_i(*OLIO, 5)),
        ),
        "Inforna le patate dolci a cubetti con l'olio a 200 °C per 15 minuti. Aggiungi sulla "
        "stessa teglia il salmone e i broccoli a cimette e cuoci altri 12-15 minuti. Completa "
        "con limone e pepe.",
        ("salmone", "pesce", "forno"),
    ),
    KiloRecipe(
        "pasta-tonno-pomodorini", "Pasta integrale tonno e pomodorini", "Pesce", 1, 20, OMNIVORE,
        (
            _i("pasta integrale", "whole wheat pasta", 80),
            _i("tonno al naturale sgocciolato", "tuna light canned in water", 80),
            _i("pomodorini", "tomatoes red ripe raw", 150),
            (_i(*OLIO, 10)),
        ),
        "Mentre cuoce la pasta, fai appassire i pomodorini tagliati a metà in padella con "
        "l'olio e uno spicchio d'aglio. A fuoco spento aggiungi il tonno sgocciolato e il "
        "basilico, poi salta la pasta nel condimento.",
        ("tonno", "pasta", "pesce", "veloce"),
    ),
    KiloRecipe(
        "merluzzo-cous-cous", "Merluzzo in padella con cous cous alle verdure", "Pesce", 1, 20, OMNIVORE,
        (
            _i("filetto di merluzzo", "cod atlantic", 200),
            _i("cous cous", "couscous dry", 70),
            _i("peperoni", "red bell pepper", 100),
            _i("zucchine", "zucchini", 100),
            (_i(*OLIO, 10)),
        ),
        "Reidrata il cous cous con acqua bollente salata, 5 minuti coperto. Salta peperoni e "
        "zucchine a dadini con metà dell'olio. Cuoci il merluzzo in padella con l'olio rimasto, "
        "4 minuti per lato, e servi tutto insieme.",
        ("merluzzo", "pesce bianco", "cous cous"),
    ),
    KiloRecipe(
        "gamberi-riso-piselli", "Riso saltato con gamberi e piselli", "Pesce", 1, 25, OMNIVORE,
        (
            _i("gamberi sgusciati", "shrimp", 150),
            _i("riso basmati", "white rice", 80),
            _i("piselli", "green peas", 80),
            _i("salsa di soia", "soy sauce", 10),
            (_i(*OLIO, 10)),
        ),
        "Cuoci il riso e lascialo raffreddare qualche minuto. In una padella larga salta i "
        "gamberi con l'olio per 2-3 minuti, aggiungi i piselli e poi il riso. Sfuma con la "
        "salsa di soia e salta ancora un minuto.",
        ("gamberi", "riso", "pesce"),
    ),
    KiloRecipe(
        "insalata-tonno-fagioli", "Insalata di tonno, fagioli e cipolla rossa", "Pesce", 1, 10, OMNIVORE,
        (
            _i("tonno al naturale sgocciolato", "tuna light canned in water", 100),
            _i("fagioli cannellini lessati", "white beans cooked", 150),
            _i("cipolla rossa", "onion", 30),
            _i("rucola", "arugula", 40),
            (_i(*OLIO, 10)),
        ),
        "Sciacqua i fagioli e uniscili al tonno sgocciolato, alla cipolla a fettine sottili e "
        "alla rucola. Condisci con olio, sale e un po' di aceto.",
        ("tonno", "fagioli", "insalata", "senza cottura"),
    ),
    # --- Carne rossa ----------------------------------------------------------------------
    KiloRecipe(
        "straccetti-manzo-rucola", "Straccetti di manzo con rucola e grana", "Carne rossa", 1, 15, OMNIVORE,
        (
            _i("controfiletto di manzo", "beef top sirloin", 150),
            _i("rucola", "arugula", 50),
            _i("grana a scaglie", "parmesan cheese hard", 15),
            _i("pane integrale", "whole wheat bread", 60),
            (_i(*OLIO, 10)),
        ),
        "Taglia la carne a strisce sottili e scottala in padella molto calda con metà "
        "dell'olio, un minuto per lato. Servila su un letto di rucola con le scaglie di grana, "
        "l'olio rimasto e il pane.",
        ("manzo", "tagliata", "rucola"),
    ),
    KiloRecipe(
        "pasta-ragu-magro", "Pasta al ragù magro", "Carne rossa", 2, 45, OMNIVORE,
        (
            _i("pasta di semola", "pasta dry", 160),
            _i("macinato di manzo magro", "ground beef 90% lean", 250),
            _i("passata di pomodoro", "tomato products canned puree", 300),
            _i("carota", "carrots", 60),
            _i("cipolla", "onion", 60),
            (_i(*OLIO, 10)),
        ),
        "Trita carota e cipolla e falle appassire con l'olio. Aggiungi il macinato e rosolalo "
        "finché perde il colore rosso, poi la passata, sale e un po' d'acqua. Cuoci a fuoco "
        "basso 30 minuti e condisci la pasta.",
        ("manzo", "ragù", "pasta", "meal prep"),
    ),
    KiloRecipe(
        "burger-manzo-patate", "Burger di manzo con patate al forno", "Carne rossa", 1, 35, OMNIVORE,
        (
            _i("macinato di manzo magro", "ground beef 90% lean", 150),
            _i("patate", "potatoes", 200),
            _i("insalata verde", "lettuce", 60),
            (_i(*OLIO, 10)),
        ),
        "Inforna le patate a spicchi con l'olio a 200 °C per 30 minuti. Forma il burger, "
        "salalo solo in superficie e cuocilo su piastra caldissima 3-4 minuti per lato. Servi "
        "con patate e insalata.",
        ("manzo", "burger", "hamburger"),
    ),
    # --- Legumi e vegetariane ---------------------------------------------------------------
    KiloRecipe(
        "pasta-lenticchie", "Pasta e lenticchie", "Legumi e vegetariane", 2, 35, VEGAN,
        (
            _i("pasta corta di semola", "pasta dry", 140),
            _i("lenticchie lessate", "lentils mature seeds cooked boiled", 300),
            _i("passata di pomodoro", "tomato products canned puree", 100),
            _i("carota", "carrots", 60),
            _i("sedano", "celery", 40),
            (_i(*OLIO, 15)),
        ),
        "Fai un soffritto di carota e sedano tritati con l'olio. Aggiungi lenticchie, passata "
        "e acqua calda quanto basta a coprire, poi la pasta, e cuocila direttamente nel sugo "
        "aggiungendo acqua se serve.",
        ("lenticchie", "legumi", "pasta", "vegano"),
    ),
    KiloRecipe(
        "frittata-spinaci", "Frittata di albumi e spinaci", "Legumi e vegetariane", 1, 15, VEGETARIAN,
        (
            _i("uova", "egg", 100),
            _i("albume", "egg white", 150),
            _i("spinaci", "spinach", 150),
            _i("parmigiano grattugiato", "parmesan cheese grated", 10),
            _i("pane integrale", "whole wheat bread", 50),
        ),
        "Fai appassire gli spinaci in padella antiaderente. Sbatti uova, albume e parmigiano "
        "con un pizzico di sale, versali sugli spinaci e cuoci coperto a fuoco basso finché la "
        "frittata si rapprende. Servi con il pane.",
        ("uova", "albumi", "frittata", "spinaci"),
    ),
    KiloRecipe(
        "buddha-bowl-ceci", "Bowl di ceci, quinoa e hummus", "Legumi e vegetariane", 1, 20, VEGAN,
        (
            _i("quinoa uncooked", "quinoa uncooked", 60),
            _i("ceci lessati", "chickpeas cooked", 150),
            _i("hummus commercial", "hummus commercial", 40),
            _i("carote", "carrots", 80),
            _i("cavolo cappuccio", "cabbage", 80),
            _i("semi di zucca", "pumpkin seeds", 10),
        ),
        "Cuoci la quinoa. Arrostisci i ceci in padella con paprika finché diventano "
        "croccanti. Componi la bowl con quinoa, ceci, carote e cavolo tagliati sottili, "
        "l'hummus al centro e i semi di zucca.",
        ("ceci", "bowl", "vegano", "quinoa uncooked"),
    ),
    KiloRecipe(
        "tofu-verdure-riso", "Tofu saltato con verdure e riso", "Legumi e vegetariane", 1, 25, VEGAN,
        (
            _i("tofu", "tofu firm", 200),
            _i("riso basmati", "white rice", 70),
            _i("broccoli", "broccoli", 150),
            _i("peperoni", "red bell pepper", 100),
            _i("salsa di soia", "soy sauce", 15),
            (_i(*OLIO, 10)),
        ),
        "Taglia il tofu a cubetti, asciugalo bene e rosolalo con l'olio finché è dorato. "
        "Aggiungi broccoli e peperoni e salta a fuoco vivo 5 minuti, poi la salsa di soia. "
        "Servi con il riso.",
        ("tofu", "vegano", "saltato"),
    ),
    KiloRecipe(
        "zuppa-fagioli-farro", "Zuppa di fagioli e farro", "Legumi e vegetariane", 2, 40, VEGAN,
        (
            _i("farro perlato", "spelt uncooked", 120),
            _i("fagioli borlotti lessati", "cranberry beans cooked", 300),
            _i("passata di pomodoro", "tomato products canned puree", 100),
            _i("carota", "carrots", 60),
            _i("cipolla", "onion", 50),
            (_i(*OLIO, 15)),
        ),
        "Soffriggi carota e cipolla tritate con l'olio, aggiungi fagioli, passata e un litro "
        "d'acqua. Porta a bollore, unisci il farro e cuoci 25 minuti mescolando ogni tanto. "
        "Frulla metà zuppa se la vuoi più cremosa.",
        ("fagioli", "spelt uncooked", "zuppa", "vegano"),
    ),
    KiloRecipe(
        "omelette-ricotta", "Omelette ripiena di ricotta e zucchine", "Legumi e vegetariane", 1, 15, VEGETARIAN,
        (
            _i("uova", "egg", 150),
            _i("ricotta vaccina", "ricotta cheese part skim", 80),
            _i("zucchine", "zucchini", 150),
            _i("pane integrale", "whole wheat bread", 50),
        ),
        "Salta le zucchine a rondelle in padella antiaderente. Sbatti le uova con un pizzico "
        "di sale, versale in padella e, quando la base si rapprende, farcisci metà con ricotta "
        "e zucchine. Chiudi a libro e cuoci ancora un minuto.",
        ("uova", "omelette", "ricotta"),
    ),
    KiloRecipe(
        "insalata-lenticchie-feta", "Insalata tiepida di lenticchie e feta", "Legumi e vegetariane", 1, 10, VEGETARIAN,
        (
            _i("lenticchie lessate", "lentils mature seeds cooked boiled", 200),
            _i("feta", "feta cheese", 50),
            _i("pomodorini", "tomatoes red ripe raw", 100),
            _i("rucola", "arugula", 40),
            (_i(*OLIO, 10)),
        ),
        "Scalda appena le lenticchie in padella. Uniscile a pomodorini, rucola e feta a "
        "cubetti, e condisci con olio, sale e succo di limone.",
        ("lenticchie", "feta", "insalata"),
    ),
    # --- Spuntini ---------------------------------------------------------------------------
    KiloRecipe(
        "skyr-frutti-bosco", "Skyr con frutti di bosco e mandorle", "Spuntini", 1, 3, VEGETARIAN,
        (
            _i("skyr (o yogurt greco magro)", "greek yogurt nonfat plain", 170),
            _i("frutti di bosco", "raspberries", 80),
            _i("mandorle", "almonds raw", 15),
        ),
        "Versa lo yogurt in una ciotola e aggiungi frutti di bosco e mandorle tritate.",
        ("yogurt", "spuntino", "merenda"),
    ),
    KiloRecipe(
        "gallette-fiocchi-latte", "Gallette di riso con fiocchi di latte e tacchino", "Spuntini", 1, 3, OMNIVORE,
        (
            _i("gallette di riso", "rice cakes brown rice plain", 20),
            _i("fiocchi di latte", "cottage cheese lowfat", 100),
            _i("fesa di tacchino a fette", "turkey breast deli", 50),
        ),
        "Spalma i fiocchi di latte sulle gallette e completa con il tacchino e un pizzico di "
        "pepe.",
        ("tacchino", "spuntino", "fiocchi di latte"),
    ),
    KiloRecipe(
        "hummus-verdure", "Hummus con verdure crude e crackers", "Spuntini", 1, 5, VEGAN,
        (
            _i("hummus commercial", "hummus commercial", 60),
            _i("carote", "carrots", 100),
            _i("cetriolo", "cucumber with peel raw", 100),
            _i("crackers integrali", "whole wheat crackers", 25),
        ),
        "Taglia carote e cetriolo a bastoncini e servili con l'hummus e i crackers.",
        ("hummus commercial", "ceci", "spuntino", "vegano"),
    ),
    KiloRecipe(
        "banana-burro-arachidi", "Banana e burro d'arachidi pre-allenamento", "Spuntini", 1, 2, VEGAN,
        (
            _i("bananas raw", "bananas raw", 120),
            _i("burro d'arachidi", "peanut butter", 15),
            _i("gallette di riso", "rice cakes brown rice plain", 20),
        ),
        "Spalma il burro d'arachidi sulle gallette e aggiungi la banana a rondelle. Da "
        "mangiare 60-90 minuti prima dell'allenamento.",
        ("bananas raw", "pre allenamento", "spuntino"),
    ),
)

BY_ID: dict[str, KiloRecipe] = {r.meal_id: r for r in RECIPES}


def get(meal_id: str | None) -> KiloRecipe | None:
    return BY_ID.get(meal_id or "")
