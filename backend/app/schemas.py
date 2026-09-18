"""Schemi Pydantic per le richieste e le risposte dell'API.

Convenzione seguita ovunque: le risposte che contengono un consiglio
dell'agente portano con sé anche **le avvertenze** e **i tag della knowledge
base** che l'hanno prodotto. L'interfaccia può così mostrare il consiglio
senza separarlo dal suo contesto — che è il requisito di
`evidence_conduct.md`.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Account ------------------------------------------------------------------


class CredentialsIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    # Solo per mostrare o nascondere le funzioni riservate: il controllo vero
    # lo fa il backend a ogni richiesta.
    is_admin: bool = False


class AuthOut(BaseModel):
    """Sessione: token + account + profilo, se già creato.

    Restituire anche il profilo evita al frontend una seconda chiamata subito
    dopo l'accesso, e permette di capire se mostrare l'onboarding.
    """

    token: str
    user: UserOut
    profile: "ProfileOut | None" = None


# --- Profilo ------------------------------------------------------------------


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    birth_date: dt.date
    sex: str
    height_cm: float = Field(gt=50, lt=260)
    weight_kg: float = Field(gt=20, lt=400)
    goal: str
    experience_level: str = "beginner"
    activity_level: str = "moderately_active"
    training_days_per_week: int = Field(default=3, ge=1, le=7)
    diet_type: str = "omnivore"
    available_equipment: str | None = None


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    weight_kg: float | None = Field(default=None, gt=20, lt=400)
    goal: str | None = None
    experience_level: str | None = None
    activity_level: str | None = None
    training_days_per_week: int | None = Field(default=None, ge=1, le=7)
    diet_type: str | None = None
    available_equipment: str | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    birth_date: dt.date
    sex: str
    height_cm: float
    weight_kg: float
    goal: str
    experience_level: str
    activity_level: str
    training_days_per_week: int
    diet_type: str
    available_equipment: str | None
    age: int
    bmr: float | None
    tdee: float | None


class ScreeningIn(BaseModel):
    """Questionario PAR-Q+. Un "sì" non blocca l'app, ma rende più prudente
    ogni piano generato."""

    heart_condition: bool = False
    chest_pain: bool = False
    dizziness_loss_consciousness: bool = False
    chronic_condition: bool = False
    blood_pressure_heart_medication: bool = False
    bone_joint_problem: bool = False
    pregnant_or_postpartum: bool = False
    eating_disorder_history: bool = False
    notes: str | None = None


class ScreeningOut(ScreeningIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: dt.datetime
    requires_medical_clearance: bool


class WeightLogIn(BaseModel):
    weight_kg: float = Field(gt=20, lt=400)
    date: dt.date | None = None
    body_fat_pct: float | None = Field(default=None, ge=1, le=70)
    note: str | None = None


class WeightLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    weight_kg: float
    body_fat_pct: float | None


# --- Allenamento ---------------------------------------------------------------


class ExerciseGuidanceOut(BaseModel):
    """Biomeccanica e suggerimento di focus, calcolati (vedi `exercise_guidance.py`)."""

    pattern: str | None
    movement: str
    joints: list[str]
    actions: list[str]
    plane: str
    plane_hint: str
    cues: list[str]
    muscle_cue: str | None = None
    lengthened_note: str | None
    knowledge_tags: list[str]


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    primary_muscle: str | None
    secondary_muscles: str | None
    equipment: str | None
    category: str | None
    description: str | None
    image_url: str | None
    is_compound: bool
    source: str = "wger"
    level: str | None = None
    name_it: str | None = None
    demo_images: list[str] | None = None
    instructions_it: list[str] | None = None
    focus_it: list[str] | None = None
    tips_it: list[str] | None = None
    # Solo nel dettaglio dell'esercizio (overlay), non negli elenchi.
    guidance: ExerciseGuidanceOut | None = None


class PlanExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_label: str
    order_index: int
    target_sets: int
    target_reps_min: int
    target_reps_max: int
    target_rir: int
    rest_seconds: int
    notes: str | None
    exercise: ExerciseOut


class WorkoutPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    goal: str
    days_per_week: int
    split_type: str | None = None
    rationale: str | None
    is_active: bool
    started_at: dt.date
    exercises: list[PlanExerciseOut] = []


class PlanGenerationOut(BaseModel):
    """La scheda insieme al contesto che la giustifica."""

    plan: WorkoutPlanOut
    weekly_sets_per_muscle: dict[str, int]
    warnings: list[str]
    knowledge_tags: list[str]


class AlternativeOut(BaseModel):
    exercise: ExerciseOut
    preserves_stimulus: bool
    already_preferred: bool


class PreferenceIn(BaseModel):
    exercise_id: int
    is_preferred: bool = True


class PreferenceOut(BaseModel):
    exercise_id: int
    is_preferred: bool
    exercise: ExerciseOut


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    # Lo storico arriva dal browser: senza limiti si potrebbero spedire
    # prompt enormi e costosi.
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)
    # Dove si trova l'utente quando chiede (sezione, esercizio aperto...):
    # permette risposte su "questo" senza doverlo rispiegare.
    context: str | None = Field(default=None, max_length=500)


class ChatActionOut(BaseModel):
    """Azione proposta dall'assistente. Non viene mai eseguita da sola:
    l'utente la conferma con un clic."""

    type: str
    label: str
    section: str | None = None
    value: str | None = None


class ChatOut(BaseModel):
    answer: str
    knowledge_tags: list[str] = []
    used_llm: bool
    actions: list[ChatActionOut] = []


class SwapIn(BaseModel):
    replacement_exercise_id: int
    mark_old_as_disliked: bool = False


class SessionSetIn(BaseModel):
    exercise_id: int
    set_number: int = Field(ge=1)
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0, le=1000)
    rir: int | None = Field(default=None, ge=0, le=10)


class SessionIn(BaseModel):
    date: dt.date | None = None
    day_label: str | None = None
    perceived_fatigue: int | None = Field(default=None, ge=1, le=10)
    note: str | None = None
    sets: list[SessionSetIn] = []


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    day_label: str | None
    perceived_fatigue: int | None
    note: str | None


class FeedbackIn(BaseModel):
    """Come sta rispondendo l'utente all'allenamento: è l'input
    dell'autoregolazione del volume."""

    progress_perception: str = "good"
    recovery_quality: str = "good"
    doms_duration_hours: int | None = Field(default=None, ge=0, le=336)
    affects_performance: bool = False
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None
    apply_to_plan: bool = False
    # Con più schede attive: quella a cui si riferisce il feedback. Se manca,
    # la più recente.
    plan_id: int | None = None


class VolumeRecommendationOut(BaseModel):
    adjustment: str
    current_weekly_sets: int
    suggested_weekly_sets: int
    reason: str
    caveats: list[str]
    knowledge_tags: list[str]
    applied: bool = False


# --- Nutrizione ----------------------------------------------------------------


class NutritionTargetsOut(BaseModel):
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
    protein_pct: float
    carbs_pct: float
    fat_pct: float
    rationale: str
    warnings: list[str]
    knowledge_tags: list[str]


class FoodNamesIn(BaseModel):
    ids: list[int] = Field(max_length=50)


class FoodSearchOut(BaseModel):
    ingredient_id: int
    name: str
    name_it: str | None = None
    source_label: str
    is_generic: bool
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float


class BarcodeFoodOut(FoodSearchOut):
    barcode: str
    cached: bool


class ManualProductIn(BaseModel):
    """Valori per 100 g copiati dall'etichetta."""

    name: str = Field(min_length=2, max_length=200)
    barcode: str | None = Field(default=None, max_length=32)
    kcal_100g: float = Field(ge=0, le=950)
    protein_100g: float = Field(ge=0, le=100)
    carbs_100g: float = Field(ge=0, le=100)
    fat_100g: float = Field(ge=0, le=100)


class MealItemIn(BaseModel):
    ingredient_id: int
    grams: float = Field(gt=0, le=5000)
    meal_type: str = "lunch"
    date: dt.date | None = None


class MealItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    quantity_g: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None


class MealOut(BaseModel):
    id: int
    meal_type: str
    items: list[MealItemOut]
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class DiaryOut(BaseModel):
    """Giornata completa, con il confronto rispetto ai target."""

    date: dt.date
    meals: list[MealOut]
    totals: dict[str, float]
    targets: NutritionTargetsOut
    remaining: dict[str, float]
    progress: dict[str, float]


class RecipeItemOut(BaseModel):
    """Un ingrediente della ricetta gia abbinato al catalogo alimenti.

    E quello che permette di versare una ricetta nel diario senza cercare
    gli alimenti uno a uno: `ingredient_id` e `grams` bastano a creare la
    voce del pasto. Quando l'abbinamento non riesce `ingredient_id` e nullo
    e la riga va sistemata a mano.
    """

    name: str = Field(min_length=1, max_length=120)
    measure: str | None = Field(default=None, max_length=80)
    grams: float | None = Field(default=None, ge=0, le=5000)
    ingredient_id: int | None = None
    matched_name: str | None = Field(default=None, max_length=300)
    source_label: str | None = Field(default=None, max_length=60)
    kcal_100g: float | None = None
    protein_100g: float | None = None
    carbs_100g: float | None = None
    fat_100g: float | None = None
    fiber_100g: float | None = None


class RecipeSuggestionOut(BaseModel):
    # Id della ricetta nella fonte (TheMealDB): serve a salvarla.
    meal_id: str | None = None
    saved: bool = False
    # "themealdb" oppure "import" per le ricette incollate dall'utente.
    source: str = "themealdb"
    name: str
    original_name: str | None = None
    category: str | None
    area: str | None
    thumbnail_url: str | None
    youtube_url: str | None = None
    instructions: str | None
    kcal_per_serving: float
    protein_per_serving: float
    carbs_per_serving: float
    fat_per_serving: float
    fiber_per_serving: float
    servings: int
    coverage: float
    fit_score: float
    reasons: list[str]
    ingredients: list[str]
    items: list[RecipeItemOut] = Field(default_factory=list)


class SavedRecipeIn(RecipeSuggestionOut):
    meal_id: str = Field(min_length=1, max_length=64)
    source: str = Field(default="themealdb", pattern="^(themealdb|import)$")
    name: str = Field(min_length=1, max_length=300)
    instructions: str | None = Field(default=None, max_length=20000)
    reasons: list[str] = Field(default_factory=list, max_length=20)
    ingredients: list[str] = Field(default_factory=list, max_length=60)
    items: list[RecipeItemOut] = Field(default_factory=list, max_length=60)


class RecipeImportIn(BaseModel):
    text: str = Field(min_length=10, max_length=8000)


class RecipeImportOut(BaseModel):
    """Bozza di ricetta letta da un testo: si rivede e poi si salva."""

    name: str
    servings: int
    instructions: str | None
    items: list[RecipeItemOut]
    warnings: list[str]


class RecipeToDiaryIn(BaseModel):
    """Versa gli ingredienti di una ricetta in un pasto del diario."""

    items: list[RecipeItemOut] = Field(min_length=1, max_length=60)
    meal_type: str = "lunch"
    date: dt.date | None = None
    # Le quantita degli ingredienti sono per la ricetta intera: si dividono
    # per le porzioni e si moltiplicano per quelle davvero mangiate.
    servings: int = Field(default=1, ge=1, le=20)
    eaten_servings: float = Field(default=1.0, gt=0, le=20)


class SavedRecipeOut(BaseModel):
    id: int
    saved_at: dt.datetime
    recipe: RecipeSuggestionOut


# --- Integratori ---------------------------------------------------------------


class SupplementIn(BaseModel):
    kind: str
    product_name: str | None = None
    dose_amount: float | None = Field(default=None, ge=0)
    dose_unit: str | None = None
    doses_per_day: float = Field(default=1.0, gt=0, le=20)
    timing: str | None = None
    protein_g_per_dose: float | None = Field(default=None, ge=0, le=200)


class BenefitOut(BaseModel):
    domain: str
    evidence: str
    detail: str


class SupplementInfoOut(BaseModel):
    """Scheda informativa di un integratore, senza dose e senza dichiarazione."""

    kind: str
    evidence: str
    message: str
    benefits: list[BenefitOut]
    knowledge_tags: list[str]


class GapFoodOut(BaseModel):
    ingredient_id: int
    name: str
    grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    habitual: bool
    source_label: str


class GapSuggestionsOut(BaseModel):
    protein_left_g: float
    kcal_left: float
    message: str
    foods: list[GapFoodOut]


class SupplementOut(BaseModel):
    id: int
    kind: str
    product_name: str | None
    dose_amount: float | None
    dose_unit: str | None
    doses_per_day: float
    evidence: str
    message: str
    dose_in_range: bool | None
    safety_flag: str | None
    benefits: list[BenefitOut]
    knowledge_tags: list[str]


class IntakeIn(BaseModel):
    date: dt.date
    doses: int = Field(ge=0, le=20)


class IntakeDayOut(BaseModel):
    date: dt.date
    doses: int


class IntakeMilestoneOut(BaseModel):
    days: int
    note: str
    reached_note: str
    knowledge_tag: str


class SupplementIntakeOut(BaseModel):
    """Diario di un integratore: storico recente, totali e serie."""

    supplement_id: int
    kind: str
    product_name: str | None
    dose_amount: float | None
    dose_unit: str | None
    doses_required: int
    since: dt.date
    days_taken: int
    current_streak: int
    missed_days: int
    history_days: int
    history: list[IntakeDayOut]
    milestone: IntakeMilestoneOut | None


class PendingSupplementOut(BaseModel):
    supplement_id: int
    kind: str
    product_name: str | None
    doses_taken: int
    doses_required: int


class DailyRemindersOut(BaseModel):
    date: dt.date
    supplements: list[PendingSupplementOut]
    meals_missing: bool


class AgentNoteOut(BaseModel):
    """Nota di Kilo: indicazione basata su una regola delle fonti."""

    key: str
    section: str
    tone: str
    title: str
    text: str
    knowledge_tags: list[str]
    question: str
    priority: int
    action: str | None


class NoteDismissIn(BaseModel):
    key: str = Field(min_length=1, max_length=160)


class SupplementWeekOut(BaseModel):
    supplement_id: int
    kind: str
    product_name: str | None
    days_taken: int
    days_expected: int


class WeeklySummaryOut(BaseModel):
    """Riepilogo della settimana conclusa: numeri calcolati e un solo obiettivo."""

    week_start: dt.date
    week_end: dt.date
    has_data: bool
    sessions_done: int
    sessions_planned: int | None
    weight_average: float | None
    weight_delta_kg: float | None
    weigh_ins: int
    logged_days: int
    protein_average_g: float | None
    protein_target_g: float | None
    supplements: list[SupplementWeekOut]
    focus: str | None


# --- Progressione ---------------------------------------------------------------


class ExerciseProgressOut(BaseModel):
    exercise_name: str
    first_best_set: str
    last_best_set: str
    first_best_1rm: float
    last_best_1rm: float
    delta_kg: float
    delta_pct: float
    sessions: int
    high_rep_estimate: bool


class ProgressReportOut(BaseModel):
    period_start: dt.date
    period_end: dt.date
    weeks: float
    too_early: bool
    weight_first_average: float | None
    weight_last_average: float | None
    weight_delta_kg: float | None
    weight_weekly_rate_kg: float | None
    weight_measurements: int
    weight_smoothed: bool
    sessions_done: int
    sessions_per_week: float
    planned_per_week: int | None
    exercises: list[ExerciseProgressOut]
    notes: list[str]
    plateau_advice: str | None


# --- Catalogo -------------------------------------------------------------------


class CatalogStatusOut(BaseModel):
    exercises_cached: int
    ingredients_cached: int
    muscles: list[str]


class SyncResultOut(BaseModel):
    fetched: int
    created: int
    updated: int
    skipped_no_muscle: int
