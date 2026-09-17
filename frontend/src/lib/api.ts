/**
 * Client dell'API.
 *
 * Le chiamate passano da `/api/*`, che Next inoltra al backend FastAPI
 * (vedi `next.config.mjs`): niente CORS e niente URL assoluti nei componenti.
 */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "sessione";

export const session = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY)),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = session.get();
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  // Sessione scaduta o non valida: si esce, invece di lasciare l'interfaccia
  // bloccata su errori incomprensibili a ogni chiamata successiva.
  if (res.status === 401) {
    session.clear();
    if (typeof window !== "undefined" && !path.startsWith("/auth/")) {
      window.location.reload();
    }
    throw new ApiError(401, "Sessione scaduta: accedi di nuovo.");
  }

  if (!res.ok) {
    // FastAPI risponde con {detail: ...}; il detail può essere una stringa
    // o la lista di errori di validazione di Pydantic.
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      /* risposta senza corpo JSON */
    }
    throw new ApiError(res.status, detail);
  }

  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  del: (path: string) => request<void>(path, { method: "DELETE" }),
};

// --- Tipi condivisi con gli schemi Pydantic del backend ---------------------

export type AuthSession = {
  token: string;
  /** `is_admin` serve solo a mostrare le funzioni riservate: il controllo è nel backend. */
  user: { id: number; email: string; is_admin: boolean };
  profile: Profile | null;
};

export type Preference = {
  exercise_id: number;
  is_preferred: boolean;
  exercise: Exercise;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

/** Azione proposta dal coach: parte solo se l'utente la conferma con un clic. */
export type ChatAction = {
  type: "open_section" | "generate_plan" | "log_weight" | "search_food" | "search_recipe" | "ask";
  label: string;
  section: string | null;
  value: string | null;
};

export type ChatReply = {
  answer: string;
  knowledge_tags: string[];
  used_llm: boolean;
  actions: ChatAction[];
};

export type Profile = {
  id: number;
  display_name: string;
  birth_date: string;
  sex: string;
  height_cm: number;
  weight_kg: number;
  goal: string;
  experience_level: string;
  activity_level: string;
  training_days_per_week: number;
  diet_type: string;
  split_type: string;
  available_equipment: string | null;
  age: number;
  bmr: number | null;
  tdee: number | null;
};

export type Exercise = {
  id: number;
  name: string;
  primary_muscle: string | null;
  secondary_muscles: string | null;
  equipment: string | null;
  category: string | null;
  description: string | null;
  image_url: string | null;
  is_compound: boolean;
  source: string;
  level: string | null;
  /** Nome italiano; `null` finché la traduzione non è pronta. */
  name_it: string | null;
  /** Fotogrammi di partenza e arrivo, per l'animazione. */
  demo_images: string[] | null;
  instructions_it: string[] | null;
  focus_it: string[] | null;
  tips_it: string[] | null;
};

export type PlanExercise = {
  id: number;
  day_label: string;
  order_index: number;
  target_sets: number;
  target_reps_min: number;
  target_reps_max: number;
  target_rir: number;
  rest_seconds: number;
  notes: string | null;
  exercise: Exercise;
};

export type WorkoutPlan = {
  id: number;
  name: string;
  goal: string;
  days_per_week: number;
  /** Divisione usata (full_body, upper_lower…); null per le schede create prima. */
  split_type: string | null;
  rationale: string | null;
  is_active: boolean;
  started_at: string;
  exercises: PlanExercise[];
};

export type PlanGeneration = {
  plan: WorkoutPlan;
  weekly_sets_per_muscle: Record<string, number>;
  warnings: string[];
  knowledge_tags: string[];
};

export type Alternative = {
  exercise: Exercise;
  preserves_stimulus: boolean;
  already_preferred: boolean;
};

export type NutritionTargets = {
  tdee_kcal: number;
  target_kcal: number;
  calorie_adjustment_pct: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  free_sugars_max_g: number;
  water_l: number;
  protein_g_per_kg: number;
  protein_pct: number;
  carbs_pct: number;
  fat_pct: number;
  rationale: string;
  warnings: string[];
  knowledge_tags: string[];
};

export type FoodResult = {
  ingredient_id: number;
  name: string;
  name_it: string | null;
  source_label: string;
  is_generic: boolean;
  kcal_100g: number;
  protein_100g: number;
  carbs_100g: number;
  fat_100g: number;
};

export type MealItem = {
  id: number;
  name: string;
  quantity_g: number;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number | null;
};

export type Meal = {
  id: number;
  meal_type: string;
  items: MealItem[];
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
};

export type Diary = {
  date: string;
  meals: Meal[];
  totals: Record<string, number>;
  targets: NutritionTargets;
  remaining: Record<string, number>;
  progress: Record<string, number>;
};

export type RecipeSuggestion = {
  name: string;
  original_name: string | null;
  category: string | null;
  area: string | null;
  thumbnail_url: string | null;
  youtube_url: string | null;
  instructions: string | null;
  kcal_per_serving: number;
  protein_per_serving: number;
  carbs_per_serving: number;
  fat_per_serving: number;
  fiber_per_serving: number;
  servings: number;
  coverage: number;
  fit_score: number;
  reasons: string[];
  ingredients: string[];
};

export type Benefit = { domain: string; evidence: string; detail: string };

/** Scheda informativa: cosa dicono le fonti, senza dose né dichiarazione. */
export type SupplementInfo = {
  kind: string;
  evidence: string;
  message: string;
  benefits: Benefit[];
  knowledge_tags: string[];
};

export type GapFood = {
  ingredient_id: number;
  name: string;
  grams: number;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  habitual: boolean;
  source_label: string;
};

export type GapSuggestions = {
  protein_left_g: number;
  kcal_left: number;
  message: string;
  foods: GapFood[];
};

export type Supplement = {
  id: number;
  kind: string;
  product_name: string | null;
  dose_amount: number | null;
  dose_unit: string | null;
  doses_per_day: number;
  evidence: string;
  message: string;
  dose_in_range: boolean | null;
  safety_flag: string | null;
  benefits: Benefit[];
  knowledge_tags: string[];
};

export type IntakeDay = { date: string; doses: number };

/** Diario delle assunzioni di un integratore dichiarato. */
export type SupplementIntake = {
  supplement_id: number;
  kind: string;
  product_name: string | null;
  dose_amount: number | null;
  dose_unit: string | null;
  doses_required: number;
  since: string;
  days_taken: number;
  current_streak: number;
  missed_days: number;
  history_days: number;
  history: IntakeDay[];
  milestone: { days: number; note: string; reached_note: string; knowledge_tag: string } | null;
};

export type DailyReminders = {
  date: string;
  supplements: {
    supplement_id: number;
    kind: string;
    product_name: string | null;
    doses_taken: number;
    doses_required: number;
  }[];
  meals_missing: boolean;
};

/** Nota di Kilo: indicazione calcolata con una regola delle fonti. */
export type AgentNote = {
  key: string;
  section: string;
  tone: "success" | "info" | "attention";
  title: string;
  text: string;
  knowledge_tags: string[];
  question: string;
  priority: number;
  action: string | null;
};

export type WeeklySummary = {
  week_start: string;
  week_end: string;
  has_data: boolean;
  sessions_done: number;
  sessions_planned: number | null;
  weight_average: number | null;
  weight_delta_kg: number | null;
  weigh_ins: number;
  logged_days: number;
  protein_average_g: number | null;
  protein_target_g: number | null;
  supplements: {
    supplement_id: number;
    kind: string;
    product_name: string | null;
    days_taken: number;
    days_expected: number;
  }[];
  focus: string | null;
};

export type VolumeRecommendation = {
  adjustment: string;
  current_weekly_sets: number;
  suggested_weekly_sets: number;
  reason: string;
  caveats: string[];
  knowledge_tags: string[];
  applied: boolean;
};

export type ExerciseProgress = {
  exercise_name: string;
  first_best_set: string;
  last_best_set: string;
  first_best_1rm: number;
  last_best_1rm: number;
  delta_kg: number;
  delta_pct: number;
  sessions: number;
  high_rep_estimate: boolean;
};

export type ProgressReport = {
  period_start: string;
  period_end: string;
  weeks: number;
  too_early: boolean;
  weight_first_average: number | null;
  weight_last_average: number | null;
  weight_delta_kg: number | null;
  weight_weekly_rate_kg: number | null;
  weight_measurements: number;
  weight_smoothed: boolean;
  sessions_done: number;
  sessions_per_week: number;
  planned_per_week: number | null;
  exercises: ExerciseProgress[];
  notes: string[];
  plateau_advice: string | null;
};

export type CatalogStatus = {
  exercises_cached: number;
  ingredients_cached: number;
  muscles: string[];
};

// --- Date locali --------------------------------------------------------------

/** Data locale in formato YYYY-MM-DD: il server è in UTC, l'utente no. */
export function localDate(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Sposta una data YYYY-MM-DD di `days` giorni, senza passare dall'UTC. */
export function shiftDate(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return localDate(new Date(y, m - 1, d + days));
}

/** Avvisa il banner dei promemoria che qualcosa è stato appena segnato. */
export const REMINDERS_EVENT = "kilo:promemoria";
export function notifyLogged() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REMINDERS_EVENT));
}

// --- Etichette in italiano ---------------------------------------------------

export const GOAL_LABELS: Record<string, string> = {
  hypertrophy: "Massa muscolare",
  strength: "Forza",
  fat_loss: "Definizione",
  maintenance: "Mantenimento",
  general_health: "Salute generale",
};

export const EXPERIENCE_LABELS: Record<string, string> = {
  beginner: "Principiante",
  intermediate: "Intermedio",
  advanced: "Avanzato",
};

export const ACTIVITY_LABELS: Record<string, string> = {
  sedentary: "Sedentario",
  lightly_active: "Poco attivo",
  moderately_active: "Moderatamente attivo",
  very_active: "Molto attivo",
  extremely_active: "Estremamente attivo",
};

export const DIET_LABELS: Record<string, string> = {
  omnivore: "Onnivora",
  vegetarian: "Vegetariana",
  vegan: "Vegana",
};

export const SPLIT_LABELS: Record<string, string> = {
  auto: "Scegli tu per me",
  full_body: "Full body",
  upper_lower: "Upper / Lower",
  push_pull_legs: "Push / Pull / Gambe",
  muscle_group: "Per gruppo muscolare",
};

export const SPLIT_HINTS: Record<string, string> = {
  auto: "Decido io in base ai giorni che hai a disposizione",
  full_body: "Tutto il corpo a ogni sessione: ogni muscolo più volte a settimana",
  upper_lower: "Un giorno parte alta, un giorno parte bassa",
  push_pull_legs: "Spinta, trazione e gambe in giorni separati",
  muscle_group: "Es. lunedì petto e bicipiti, mercoledì gambe e dorso, venerdì spalle e tricipiti",
};

export const MUSCLE_LABELS: Record<string, string> = {
  Chest: "Petto",
  Lats: "Dorso",
  Shoulders: "Spalle",
  Biceps: "Bicipiti",
  Triceps: "Tricipiti",
  Quads: "Quadricipiti",
  Hamstrings: "Femorali",
  Glutes: "Glutei",
  Calves: "Polpacci",
  Abs: "Addominali",
  Trapezius: "Trapezio",
  Brachialis: "Brachiale",
  Soleus: "Soleo",
  "Serratus anterior": "Dentato anteriore",
  "Obliquus externus abdominis": "Obliqui",
  Forearms: "Avambracci",
  "Lower back": "Zona lombare",
  Adductors: "Adduttori",
  Neck: "Collo",
};

/** Attrezzatura, dai nomi delle fonti (inglesi) all'italiano. */
const EQUIPMENT_LABELS: Record<string, string> = {
  barbell: "bilanciere",
  dumbbell: "manubri",
  cable: "cavi",
  machine: "macchina",
  kettlebells: "kettlebell",
  kettlebell: "kettlebell",
  bands: "elastici",
  "resistance band": "elastici",
  "e-z curl bar": "bilanciere EZ",
  "sz-bar": "bilanciere EZ",
  "exercise ball": "fitball",
  "swiss ball": "fitball",
  "medicine ball": "palla medica",
  "foam roll": "foam roller",
  bench: "panca",
  "incline bench": "panca inclinata",
  "pull-up bar": "sbarra",
  "gym mat": "tappetino",
  "decline bench": "panca declinata",
  "smith machine": "multipower",
  "parallel bars": "parallele",
  "weight plate": "disco",
  "t-bar machine": "macchina T-bar",
  towel: "asciugamano",
  "suspension trainer": "TRX",
  rings: "anelli",
  "trap bar": "trap bar",
  "ab wheel": "ruota per addominali",
  other: "altro",
};

export function formatEquipment(equipment: string | null): string {
  if (!equipment || equipment.includes("none (bodyweight")) return "corpo libero";
  return equipment
    .split(",")
    .map((e) => EQUIPMENT_LABELS[e.trim().toLowerCase()] ?? e.trim())
    .join(", ");
}

/** Il nome da mostrare: italiano quando c'è, altrimenti quello della fonte. */
export function exerciseName(ex: { name: string; name_it?: string | null }): string {
  return ex.name_it || ex.name;
}

export const MEAL_LABELS: Record<string, string> = {
  breakfast: "Colazione",
  lunch: "Pranzo",
  dinner: "Cena",
  snack: "Spuntino",
};

export const SUPPLEMENT_LABELS: Record<string, string> = {
  protein_powder: "Proteine in polvere",
  creatine: "Creatina",
  caffeine: "Caffeina",
  beta_alanine: "Beta-alanina",
  hmb: "HMB",
  bcaa: "BCAA",
  glutamine: "Glutammina",
  citrulline: "Citrullina",
  vitamin_d: "Vitamina D",
  omega3: "Omega-3",
  omega_3: "Omega-3",
  ashwagandha: "Ashwagandha",
  moringa: "Moringa",
  other: "Altro",
};

export const EVIDENCE_LABELS: Record<string, string> = {
  strong: "Evidenza solida",
  moderate: "Evidenza moderata",
  weak: "Evidenza debole",
  unknown: "Nessuna fonte verificata",
};

/** I documenti della knowledge base, in forma leggibile. */
export const TAG_LABELS: Record<string, string> = {
  volume_allenamento: "Volume di allenamento",
  recupero: "Recuperi",
  intensità: "Intensità (RIR)",
  cedimento: "Prossimità al cedimento",
  doms: "DOMS e recupero",
  autoregolazione: "Autoregolazione",
  scelta_esercizi: "Scelta esercizi",
  focus_attentivo: "Focus attentivo",
  screening: "Screening PAR-Q+",
  attivita_generale: "Linee guida WHO",
  calorie: "Calcolo calorico",
  "1rm": "Massimale stimato",
  proteine: "Fabbisogno proteico",
  macronutrienti: "Macronutrienti EFSA",
  micronutrienti: "Micronutrienti EFSA",
  zuccheri: "Zuccheri liberi",
  timing_pasti: "Timing dei pasti",
  idratazione: "Idratazione",
  vegetariano: "Dieta vegetariana",
  vegano: "Dieta vegana",
  deficit_calorico: "Disponibilità energetica",
  reds: "REDs",
  creatina: "Creatina",
  caffeina: "Caffeina",
  glutammina: "Glutammina",
  beta_alanina: "Beta-alanina",
  hmb: "HMB",
  bcaa: "BCAA",
  citrullina: "Citrullina",
  vitamina_d: "Vitamina D",
  omega3: "Omega-3",
  qualita_prodotto: "Qualità del prodotto",
  integratori_oltre_muscolo: "Integratori oltre il muscolo",
  ipertrofia: "Prescrizione per l'ipertrofia",
  forza: "Allenamento per la forza",
  progressione: "Progressione dei carichi",
  periodizzazione: "Periodizzazione",
  frequenza_allenamento: "Frequenza di allenamento",
  tecniche_avanzate: "Tecniche avanzate",
  cardio: "Allenamento aerobico",
  biomeccanica: "Biomeccanica",
  tecnica_esecuzione: "Tecnica di esecuzione",
  ampiezza_movimento: "Ampiezza di movimento",
  composizione_corporea: "Diete e composizione corporea",
  surplus_calorico: "Surplus calorico",
  tipi_dieta: "Tipi di dieta",
  categorie_integratori: "Categorie di evidenza degli integratori",
};
