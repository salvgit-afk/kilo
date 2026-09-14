"""«Cosa mi manca oggi?» — alimenti e grammi per chiudere le proteine.

È la parte agentica del diario: invece di mostrare solo quanto manca, propone
**con quali alimenti e in che quantità** colmarlo, restando nelle calorie
rimaste. L'utente conferma con un clic; nulla viene aggiunto da solo.

Nessun numero viene stimato:

  - i candidati sono alimenti **già presenti nel database** con valori per
    100 g da USDA o Open Food Facts — prima quelli che l'utente ha già
    registrato (le sue abitudini reali), poi i generici USDA;
  - i grammi sono una divisione: proteine mancanti / proteine per grammo,
    limitata dalle calorie rimaste;
  - le voci con valori incoerenti vengono scartate con un controllo di
    Atwater (4-4-9 kcal/g): una "banana da 0 kcal" crowdsourced non deve
    finire in un suggerimento.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DietType, Ingredient, IngredientSource, MealItem, MealLog, UserProfile

# Sotto questa densità un alimento non "chiude" le proteine in una porzione
# ragionevole: servirebbero centinaia di grammi.
MIN_PROTEIN_100G = 10.0

# Porzioni proposte: sotto i 30 g non vale la pena, sopra i 300 g non è una
# porzione che si mangia in un pasto.
MIN_GRAMS, MAX_GRAMS = 30, 300

# Scarto massimo fra kcal dichiarate e kcal ricalcolate dai macro.
ATWATER_TOLERANCE = 0.30

# Sotto questa soglia le proteine sono di fatto coperte.
PROTEIN_DONE_G = 5.0

# `protein_intake.md`: 20-40 g di proteine a pasto è la quota utile alla
# sintesi proteica. Ogni proposta è una porzione da un pasto, non l'intero
# fabbisogno mancante in un solo alimento (300 g di albume non è un pasto).
PROTEIN_PER_PORTION_G = 40.0

# Forme trasformate che non sono ciò che si intende come "fonte proteica da
# aggiungere": albume disidratato, pollo impanato, prodotti in polvere.
_PROCESSED = (
    "dried", "dehydrated", "powder", "fried", "breaded", "battered", "candied",
    "syrup", "sweetened", "nuggets", "imitation", "substitute", "stabilized",
)

MAX_SUGGESTIONS = 4

# Parole che identificano prodotti animali nei nomi (in inglese, come in
# USDA, e in italiano, come in Open Food Facts).
_MEAT_FISH = (
    "chicken", "beef", "pork", "turkey", "ham", "fish", "tuna", "salmon", "cod",
    "shrimp", "prawn", "lamb", "veal", "bacon", "sausage", "pollo", "manzo",
    "maiale", "tacchino", "prosciutto", "tonno", "salmone", "merluzzo", "pesce",
    "gamberi", "bresaola", "vitello",
)
_DAIRY_EGGS = (
    "egg", "milk", "cheese", "yogurt", "yoghurt", "whey", "casein", "cottage",
    "uova", "uovo", "latte", "formaggio", "ricotta", "skyr", "fiocchi di latte",
    "parmigiano", "mozzarella",
)


@dataclass
class GapFood:
    ingredient: Ingredient
    grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    habitual: bool


@dataclass
class GapSuggestions:
    protein_left_g: float
    kcal_left: float
    message: str
    foods: list[GapFood] = field(default_factory=list)


def is_plausible(ing: Ingredient) -> bool:
    kcal = ing.kcal_100g or 0.0
    if kcal <= 0:
        return False
    atwater = 4 * (ing.protein_100g or 0) + 4 * (ing.carbs_100g or 0) + 9 * (ing.fat_100g or 0)
    return abs(atwater - kcal) <= kcal * ATWATER_TOLERANCE


def compatible_with_diet(name: str, diet_type: str | None) -> bool:
    nome = name.lower()
    if diet_type == DietType.VEGAN:
        return not any(p in nome for p in _MEAT_FISH + _DAIRY_EGGS)
    if diet_type == DietType.VEGETARIAN:
        return not any(p in nome for p in _MEAT_FISH)
    return True


def portion_for(ing: Ingredient, protein_left_g: float, kcal_left: float) -> float | None:
    """Grammi che chiudono le proteine senza sforare le calorie rimaste."""
    grammi = protein_left_g / ing.protein_100g * 100
    grammi = min(grammi, kcal_left / ing.kcal_100g * 100, MAX_GRAMS)
    grammi = int(grammi // 10 * 10)
    return float(grammi) if grammi >= MIN_GRAMS else None


def suggest(
    db: Session, profile: UserProfile, *, protein_left_g: float, kcal_left: float
) -> GapSuggestions:
    if protein_left_g <= PROTEIN_DONE_G:
        return GapSuggestions(
            protein_left_g=max(0.0, protein_left_g),
            kcal_left=kcal_left,
            message="Le proteine di oggi sono coperte: non serve aggiungere altro per il target proteico.",
        )
    if kcal_left <= 0:
        return GapSuggestions(
            protein_left_g=protein_left_g,
            kcal_left=kcal_left,
            message=(
                f"Ti mancano {protein_left_g:.0f} g di proteine ma hai già raggiunto le "
                "calorie: qualsiasi aggiunta le sforerebbe. Domani conviene spostare "
                "una parte delle calorie verso fonti più proteiche."
            ),
        )

    # Alimenti che l'utente ha registrato, dal più frequente.
    abituali = [
        ing
        for ing, _ in db.execute(
            select(Ingredient, func.count(MealItem.id).label("volte"))
            .join(MealItem, MealItem.ingredient_id == Ingredient.id)
            .join(MealLog, MealLog.id == MealItem.meal_log_id)
            .where(MealLog.profile_id == profile.id)
            .group_by(Ingredient.id)
            .order_by(func.count(MealItem.id).desc())
            .limit(30)
        )
    ]
    id_abituali = {ing.id for ing in abituali}

    generici = db.scalars(
        select(Ingredient)
        .where(
            Ingredient.source == IngredientSource.USDA,
            Ingredient.protein_100g >= MIN_PROTEIN_100G,
            Ingredient.kcal_100g > 0,
        )
        .limit(300)
    ).all()

    candidati: list[GapFood] = []
    visti: set[int] = set()
    obiettivo = min(protein_left_g, PROTEIN_PER_PORTION_G)
    for ing in [*abituali, *generici]:
        if ing.id in visti:
            continue
        visti.add(ing.id)
        if (ing.protein_100g or 0) < MIN_PROTEIN_100G or not is_plausible(ing):
            continue
        abituale = ing.id in id_abituali
        # Le abitudini dell'utente sono già compatibili con la sua dieta.
        if not abituale and (
            not compatible_with_diet(ing.name, profile.diet_type)
            or any(m in ing.name.lower() for m in _PROCESSED)
        ):
            continue
        grammi = portion_for(ing, obiettivo, kcal_left)
        if grammi is None:
            continue
        f = grammi / 100
        candidati.append(
            GapFood(
                ingredient=ing,
                grams=grammi,
                kcal=round((ing.kcal_100g or 0) * f),
                protein_g=round((ing.protein_100g or 0) * f, 1),
                carbs_g=round((ing.carbs_100g or 0) * f, 1),
                fat_g=round((ing.fat_100g or 0) * f, 1),
                habitual=abituale,
            )
        )

    # Prima le abitudini, poi chi dà più proteine per caloria.
    candidati.sort(
        key=lambda c: (not c.habitual, -(c.ingredient.protein_100g or 0) / (c.ingredient.kcal_100g or 1))
    )
    # Un alimento per tipo: quattro varianti di petto di pollo non sono
    # quattro proposte. La prima parola identifica l'alimento sia nei nomi
    # USDA ("Chicken, breast…", "Chicken breast, roasted…") sia nei prodotti.
    scelti: list[GapFood] = []
    basi: set[str] = set()
    for c in candidati:
        base = (c.ingredient.name.lower().replace(",", " ").split() or [""])[0]
        if base in basi:
            continue
        basi.add(base)
        scelti.append(c)
        if len(scelti) == MAX_SUGGESTIONS:
            break

    if not scelti:
        messaggio = (
            f"Ti mancano {protein_left_g:.0f} g di proteine, ma nel database non ho ancora "
            "alimenti adatti con valori verificati. Cercane uno dal diario: da lì in poi "
            "potrò proporlo."
        )
    else:
        messaggio = (
            f"Ti mancano {protein_left_g:.0f} g di proteine e ti restano {kcal_left:.0f} kcal. "
            f"Porzioni da circa {obiettivo:.0f} g di proteine (la quota utile per pasto "
            "secondo le fonti), calcolate sui valori per 100 g:"
        )
    return GapSuggestions(
        protein_left_g=protein_left_g, kcal_left=kcal_left, message=messaggio, foods=scelti
    )
