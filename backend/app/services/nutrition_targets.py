"""Calcolo dei target nutrizionali giornalieri.

Ordine di calcolo, e il motivo per cui è questo:

  1. **TDEE** da Mifflin-St Jeor per il fattore di attività
     (`calorie_and_1rm_formulas.md`).
  2. **Calorie target** = TDEE ± scostamento dell'obiettivo.
  3. **Proteine per prime**, calcolate in g/kg di peso corporeo e non come
     percentuale delle calorie (`protein_intake.md`, ISSN): il fabbisogno
     proteico dipende dalla massa da mantenere, non da quanto si mangia. Un
     calcolo percentuale ridurrebbe le proteine proprio in deficit, cioè
     quando servono di più per preservare massa magra.
  4. **Grassi** come percentuale dell'energia (range EFSA 20-35%).
  5. **Carboidrati** come residuo.

Il residuo può cadere **sotto** il range EFSA (45-60%) in un deficit marcato
con proteine alte. Non è un errore da correggere in silenzio: i range EFSA
descrivono la popolazione generale, non chi è in un deficit deliberato con
proteine elevate. La scelta qui è tenere le proteine e **segnalare** lo
scostamento, perché abbassarle sarebbe il compromesso peggiore fra i due
(vedi `protein_intake.md` sul ruolo delle proteine in deficit).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DietType,
    Goal,
    NutritionPlan,
    Sex,
    UserProfile,
)

logger = logging.getLogger("nutrition_targets")

# Valori energetici dei macronutrienti (fattori di Atwater).
KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_CARBS = 4
KCAL_PER_G_FAT = 9

# `calorie_and_1rm_formulas.md`: scostamento dal TDEE per obiettivo.
CALORIE_ADJUSTMENT_BY_GOAL = {
    Goal.MAINTENANCE: 0.0,
    Goal.GENERAL_HEALTH: 0.0,
    Goal.FAT_LOSS: -0.18,      # deficit moderato (range indicato: -15/-20%)
    Goal.HYPERTROPHY: 0.12,    # surplus moderato (range indicato: +10/+15%)
    Goal.STRENGTH: 0.08,
}

# `protein_intake.md` (ISSN): g per kg di peso corporeo.
PROTEIN_G_PER_KG = {
    Goal.HYPERTROPHY: 1.9,     # range ipertrofia 1,6-2,4
    Goal.FAT_LOSS: 2.2,        # in deficit: preserva massa magra
    Goal.STRENGTH: 1.9,
    Goal.MAINTENANCE: 1.6,
    Goal.GENERAL_HEALTH: 1.4,  # estremo basso del range ISSN 1,4-2,0
}

# `vegetarian_vegan_nutrition.md`: sotto 1,5 g/kg da fonti vegetali gli
# adattamenti muscolari risultano compromessi.
PLANT_BASED_PROTEIN_FLOOR = 1.5

# `macronutrients_efsa.md`, verificato sul PDF ufficiale.
FAT_ENERGY_PCT_RANGE = (0.20, 0.35)
CARBS_ENERGY_PCT_RANGE = (0.45, 0.60)
FAT_ENERGY_PCT_DEFAULT = 0.27
FIBER_G_PER_DAY = 25.0
FREE_SUGARS_MAX_PCT = 0.10   # OMS: sotto il 10%, idealmente sotto il 5%
FREE_SUGARS_IDEAL_PCT = 0.05

# `macronutrients_efsa.md`: acqua totale giornaliera (bevande + alimenti).
WATER_L_BY_SEX = {Sex.MALE: 2.5, Sex.FEMALE: 2.0}

# `energy_availability_reds.md`: oltre questo deficit il rischio di bassa
# disponibilità energetica diventa concreto, tanto più se combinato con un
# volume di allenamento alto.
AGGRESSIVE_DEFICIT_PCT = -0.25
HIGH_TRAINING_DAYS = 5


@dataclass
class NutritionTargets:
    tdee_kcal: float
    target_kcal: float
    calorie_adjustment_pct: float

    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    free_sugars_max_g: float
    water_l: float

    protein_g_per_kg: float
    rationale: str
    warnings: list[str] = field(default_factory=list)
    knowledge_tags: list[str] = field(default_factory=list)

    @property
    def protein_pct(self) -> float:
        return self.protein_g * KCAL_PER_G_PROTEIN / self.target_kcal

    @property
    def carbs_pct(self) -> float:
        return self.carbs_g * KCAL_PER_G_CARBS / self.target_kcal

    @property
    def fat_pct(self) -> float:
        return self.fat_g * KCAL_PER_G_FAT / self.target_kcal


def _protein_target(profile: UserProfile) -> tuple[float, list[str]]:
    """Proteine in g/kg, con il pavimento previsto per le diete vegetali."""
    warnings: list[str] = []
    g_per_kg = PROTEIN_G_PER_KG.get(profile.goal, PROTEIN_G_PER_KG[Goal.MAINTENANCE])

    if profile.diet_type in (DietType.VEGAN, DietType.VEGETARIAN):
        if g_per_kg < PLANT_BASED_PROTEIN_FLOOR:
            g_per_kg = PLANT_BASED_PROTEIN_FLOOR
        warnings.append(
            "Dieta vegetale: punta a non scendere mai sotto 1,5 g/kg di proteine "
            "e varia le fonti nell'arco della giornata — non serve combinarle "
            "nello stesso pasto."
        )

    return g_per_kg, warnings


def compute_targets(profile: UserProfile, *, training_days: int | None = None) -> NutritionTargets:
    """Calcola i target giornalieri a partire dal profilo."""
    tdee = profile.tdee
    if not tdee:
        raise ValueError(
            "Impossibile calcolare il TDEE: servono peso, altezza e data di nascita."
        )

    adjustment = CALORIE_ADJUSTMENT_BY_GOAL.get(profile.goal, 0.0)
    target_kcal = round(tdee * (1 + adjustment))

    g_per_kg, warnings = _protein_target(profile)
    tags = ["calorie", "proteine", "macronutrienti"]
    if profile.diet_type in (DietType.VEGAN, DietType.VEGETARIAN):
        tags.extend(["vegano" if profile.diet_type == DietType.VEGAN else "vegetariano",
                     "micronutrienti"])

    protein_g = round(profile.weight_kg * g_per_kg)
    protein_kcal = protein_g * KCAL_PER_G_PROTEIN

    fat_g = round(target_kcal * FAT_ENERGY_PCT_DEFAULT / KCAL_PER_G_FAT)
    fat_kcal = fat_g * KCAL_PER_G_FAT

    carbs_kcal = max(0.0, target_kcal - protein_kcal - fat_kcal)
    carbs_g = round(carbs_kcal / KCAL_PER_G_CARBS)

    targets = NutritionTargets(
        tdee_kcal=tdee,
        target_kcal=target_kcal,
        calorie_adjustment_pct=adjustment,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=FIBER_G_PER_DAY,
        free_sugars_max_g=round(target_kcal * FREE_SUGARS_MAX_PCT / KCAL_PER_G_CARBS),
        water_l=WATER_L_BY_SEX.get(profile.sex, 2.5),
        protein_g_per_kg=g_per_kg,
        rationale="",
        warnings=warnings,
        knowledge_tags=tags,
    )

    # I carboidrati sono un residuo: può uscire dal range EFSA senza che sia
    # un errore. Va detto, non corretto abbassando le proteine.
    carbs_pct = targets.carbs_pct
    minimo, massimo = CARBS_ENERGY_PCT_RANGE
    if carbs_pct < minimo:
        targets.warnings.append(
            f"I carboidrati risultano al {carbs_pct:.0%} dell'energia, sotto il "
            f"range EFSA per la popolazione generale ({minimo:.0%}-{massimo:.0%}). "
            "È una conseguenza attesa del deficit calorico unito a proteine alte: "
            "ridurre le proteine per rientrare nel range sarebbe controproducente, "
            "perché in deficit servono proprio a preservare la massa magra."
        )

    if adjustment <= AGGRESSIVE_DEFICIT_PCT:
        targets.warnings.append(
            "Deficit calorico marcato. Se combinato con un volume di allenamento "
            "alto è il quadro che può portare a bassa disponibilità energetica: "
            "tieni d'occhio stanchezza persistente, infortuni ricorrenti, sonno "
            "e — se applicabile — regolarità del ciclo mestruale."
        )
        tags.append("deficit_calorico")

    if (
        adjustment < 0
        and training_days is not None
        and training_days >= HIGH_TRAINING_DAYS
    ):
        targets.warnings.append(
            f"Stai combinando un deficit calorico con {training_days} giorni di "
            "allenamento a settimana: è la combinazione con il rischio più alto "
            "per il recupero. Valuta un deficit più contenuto o un giorno di "
            "scarico in più."
        )
        if "deficit_calorico" not in tags:
            tags.append("deficit_calorico")

    targets.rationale = _build_rationale(profile, targets)
    return targets


def _build_rationale(profile: UserProfile, t: NutritionTargets) -> str:
    verso = (
        "in deficit" if t.calorie_adjustment_pct < 0
        else "in surplus" if t.calorie_adjustment_pct > 0
        else "a mantenimento"
    )
    return (
        f"Il tuo fabbisogno stimato è di {t.tdee_kcal:.0f} kcal al giorno "
        f"(formula di Mifflin-St Jeor con il tuo livello di attività). "
        f"Per l'obiettivo «{profile.goal}» il target è {t.target_kcal:.0f} kcal, "
        f"cioè {abs(t.calorie_adjustment_pct):.0%} {verso}. "
        f"Le proteine sono calcolate sul peso corporeo — {t.protein_g_per_kg} g/kg, "
        f"cioè {t.protein_g:.0f} g — e non come percentuale delle calorie, perché "
        f"il fabbisogno dipende dalla massa da mantenere, non da quanto mangi. "
        f"I grassi coprono il {t.fat_pct:.0%} dell'energia ({t.fat_g:.0f} g), dentro "
        f"il range EFSA 20-35%; i carboidrati sono ciò che resta "
        f"({t.carbs_g:.0f} g, {t.carbs_pct:.0%}). "
        f"Punta ad almeno {t.fiber_g:.0f} g di fibra e tieni gli zuccheri liberi "
        f"sotto i {t.free_sugars_max_g:.0f} g. "
        f"Distribuisci le proteine in 3-5 pasti da 20-40 g: conta il totale "
        f"giornaliero, non il minuto esatto in cui li assumi."
    )


def persist_plan(
    db: Session, profile: UserProfile, targets: NutritionTargets
) -> NutritionPlan:
    """Salva i target, disattivando il piano precedente."""
    for previous in db.scalars(
        select(NutritionPlan).where(
            NutritionPlan.profile_id == profile.id, NutritionPlan.is_active.is_(True)
        )
    ):
        previous.is_active = False
        previous.ended_at = dt.date.today()

    plan = NutritionPlan(
        profile_id=profile.id,
        goal=profile.goal,
        target_kcal=targets.target_kcal,
        target_protein_g=targets.protein_g,
        target_carbs_g=targets.carbs_g,
        target_fat_g=targets.fat_g,
        target_fiber_g=targets.fiber_g,
        calorie_adjustment_pct=targets.calorie_adjustment_pct,
        rationale=targets.rationale,
        is_active=True,
        started_at=dt.date.today(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan
