"""Schema del database (SQLAlchemy ORM).

Modello dati dell'agente allenamento + nutrizione:

  Profilo e sicurezza
  - UserProfile        : dati antropometrici, obiettivo, esperienza, dieta.
  - ScreeningRecord    : risposte PAR-Q+ (versionate, mai sovrascritte).
  - WeightLog          : storico del peso corporeo.

  Allenamento
  - Exercise           : cache locale del database esercizi wger.
  - WorkoutPlan        : una scheda generata per l'utente.
  - WorkoutPlanExercise: riga della scheda (esercizio + parametri target).
  - WorkoutSession     : una sessione realmente svolta.
  - SessionSet         : singola serie eseguita (carico/ripetizioni reali).

  Nutrizione
  - Ingredient         : cache locale ingredienti (wger/Open Food Facts, USDA).
  - Recipe             : ricetta con macro *calcolati* dagli ingredienti.
  - RecipeIngredient   : riga di una ricetta.
  - NutritionPlan      : target calorico/macro attivo.
  - MealLog            : pasto pianificato o consumato.

  Integratori e tracciabilità
  - SupplementDeclaration : integratore dichiarato dall'utente + valutazione.
  - AgentRecommendationLog: traccia ispezionabile di ogni output dell'agente,
                            incluse le fonti della knowledge base usate.

Principio guida (dalla knowledge base, `evidence_conduct.md`): ogni
raccomandazione generata deve essere ricostruibile — quali parametri, da
quale documento. Per questo `AgentRecommendationLog` registra i tag KB usati.

I dati che l'utente registra (serie, carichi, peso) non dipendono da nessuna
API esterna: restano validi e affidabili anche se wger/USDA cambiano o
diventano irraggiungibili.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# --- Costanti (stringhe nel DB, per semplicità nelle migrazioni Alembic) ---


class Sex:
    """Serve alla formula di Mifflin-St Jeor, che ha costanti diverse per sesso
    biologico (vedi `knowledge_base/calorie_and_1rm_formulas.md`)."""

    MALE = "male"
    FEMALE = "female"


class Goal:
    HYPERTROPHY = "hypertrophy"      # aumento massa muscolare
    STRENGTH = "strength"            # forza massimale
    FAT_LOSS = "fat_loss"            # definizione
    MAINTENANCE = "maintenance"
    GENERAL_HEALTH = "general_health"  # usa i range WHO, non quelli ipertrofia


class ExperienceLevel:
    """Determina i range di volume settimanale (`training_volume.md`)."""

    BEGINNER = "beginner"        # < 6 mesi continuativi
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ActivityLevel:
    """Moltiplicatori TDEE (`calorie_and_1rm_formulas.md`)."""

    SEDENTARY = "sedentary"              # 1.2
    LIGHTLY_ACTIVE = "lightly_active"    # 1.375
    MODERATELY_ACTIVE = "moderately_active"  # 1.55
    VERY_ACTIVE = "very_active"          # 1.725
    EXTREMELY_ACTIVE = "extremely_active"  # 1.9


class SplitType:
    """Come distribuire i gruppi muscolari sui giorni.

    `AUTO` lascia scegliere in base ai giorni disponibili; gli altri
    rispettano la preferenza dell'utente — una scheda che si esegue
    volentieri vale più di una teoricamente ottimale che si abbandona.
    """

    AUTO = "auto"
    FULL_BODY = "full_body"
    UPPER_LOWER = "upper_lower"
    PUSH_PULL_LEGS = "push_pull_legs"
    MUSCLE_GROUP = "muscle_group"   # es. lunedì petto+bicipiti, mercoledì gambe+dorso


class DietType:
    """Attiva il caricamento di `vegetarian_vegan_nutrition.md` quando serve."""

    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"


class EvidenceTier:
    """Solidità dell'evidenza, da comunicare senza appiattirla.

    Trattare la glutammina come la creatina solo perché l'utente le ha
    nominate entrambe è esattamente ciò che `evidence_conduct.md` vieta.
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


class IngredientSource:
    WGER = "wger"        # database wger (re-import di Open Food Facts)
    USDA = "usda"        # USDA FoodData Central (alimenti generici/grezzi)
    OFF = "off"          # Open Food Facts, letto dal codice a barre del prodotto
    MANUAL = "manual"    # inserito a mano dall'utente (dall'etichetta)


class RecipeSource:
    THEMEALDB = "themealdb"    # struttura ricetta importata
    GENERATED = "generated"    # composta dall'agente sui target macro
    MANUAL = "manual"


class MealType:
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class SupplementKind:
    """Determina quale file della knowledge base viene caricato per la
    valutazione. `OTHER` attiva la regola di `evidence_conduct.md`: dire
    onestamente che non esiste una fonte verificata, invece di inventare."""

    CREATINE = "creatine"
    CAFFEINE = "caffeine"
    PROTEIN_POWDER = "protein_powder"
    BETA_ALANINE = "beta_alanine"
    HMB = "hmb"
    BCAA = "bcaa"
    GLUTAMINE = "glutamine"
    CITRULLINE = "citrulline"
    VITAMIN_D = "vitamin_d"
    OMEGA_3 = "omega_3"
    # Valutati su esiti diversi da forza/massa: stress, sonno, intestino.
    ASHWAGANDHA = "ashwagandha"
    MORINGA = "moringa"
    OTHER = "other"


class ProgressPerception:
    """Come l'utente percepisce i propri progressi (`doms_and_autoregulation.md`)."""

    NONE = "none"          # nessun miglioramento percepito
    SLOW = "slow"
    GOOD = "good"


class RecoveryQuality:
    """Qualità del recupero percepita fra una sessione e l'altra.

    Il DOMS oltre le 72 ore, unito ad assenza di progressi, è il segnale che
    il collo di bottiglia è il recupero e non lo stimolo.
    """

    POOR = "poor"          # DOMS oltre 72h, fatica persistente, performance in calo
    MODERATE = "moderate"  # indolenzimento che passa entro 48-72h
    GOOD = "good"          # nessun dolore residuo alla sessione successiva


class VolumeAdjustment:
    DECREASE = "decrease"
    MAINTAIN = "maintain"
    INCREASE = "increase"


class RecommendationType:
    WORKOUT_PLAN_GENERATED = "workout_plan_generated"
    NUTRITION_PLAN_GENERATED = "nutrition_plan_generated"
    RECIPE_SUGGESTED = "recipe_suggested"
    SUPPLEMENT_EVALUATED = "supplement_evaluated"
    PROGRESSION_ADVICE = "progression_advice"
    PLATEAU_DETECTED = "plateau_detected"
    SAFETY_ALERT_SCREENING = "safety_alert_screening"  # PAR-Q+ positivo
    SAFETY_ALERT_REDS = "safety_alert_reds"            # deficit + volume alto
    VOLUME_ADJUSTED = "volume_adjusted"                # autoregolazione da feedback
    EXERCISE_SWAPPED = "exercise_swapped"


# --- Account -----------------------------------------------------------------


class User(Base):
    """Account di accesso.

    Separato da `UserProfile` di proposito: l'account è l'identità con cui si
    entra, il profilo sono i dati fisici che alimentano i calcoli. Tenerli
    distinti permette in futuro più profili sotto lo stesso account (es. per
    seguire un familiare) senza toccare l'autenticazione.

    Nel database finisce solo l'hash della password, mai la password.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profiles: Mapped[list[UserProfile]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# --- Profilo e sicurezza ----------------------------------------------------


class UserProfile(Base):
    """Profilo dell'utente. Tutti i calcoli (TDEE, target proteico, volume)
    partono da qui, applicando i parametri della knowledge base."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    display_name: Mapped[str] = mapped_column(String(120))

    birth_date: Mapped[dt.date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(16))
    height_cm: Mapped[float] = mapped_column(Float)
    # Peso "corrente" denormalizzato per comodità di calcolo; lo storico
    # completo vive in WeightLog.
    weight_kg: Mapped[float] = mapped_column(Float)

    goal: Mapped[str] = mapped_column(String(32), default=Goal.HYPERTROPHY)
    experience_level: Mapped[str] = mapped_column(
        String(32), default=ExperienceLevel.BEGINNER
    )
    activity_level: Mapped[str] = mapped_column(
        String(32), default=ActivityLevel.MODERATELY_ACTIVE
    )
    diet_type: Mapped[str] = mapped_column(String(32), default=DietType.OMNIVORE)
    split_type: Mapped[str] = mapped_column(String(32), default=SplitType.AUTO)

    # Attrezzatura disponibile (es. "palestra completa", "manubri, panca").
    # Filtra gli esercizi wger proponibili nella scheda.
    available_equipment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Allergie/intolleranze/cibi esclusi, testo libero usato nelle ricette.
    food_exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_days_per_week: Mapped[int] = mapped_column(Integer, default=3)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="profiles")
    screenings: Mapped[list[ScreeningRecord]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="ScreeningRecord.created_at.desc()",
    )

    _ACTIVITY_FACTORS = {
        ActivityLevel.SEDENTARY: 1.2,
        ActivityLevel.LIGHTLY_ACTIVE: 1.375,
        ActivityLevel.MODERATELY_ACTIVE: 1.55,
        ActivityLevel.VERY_ACTIVE: 1.725,
        ActivityLevel.EXTREMELY_ACTIVE: 1.9,
    }

    @property
    def age(self) -> int:
        today = dt.date.today()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    @property
    def bmr(self) -> float:
        """Metabolismo basale, equazione di Mifflin-St Jeor."""
        base = 10 * self.weight_kg + 6.25 * self.height_cm - 5 * self.age
        return round(base + 5 if self.sex == Sex.MALE else base - 161, 1)

    @property
    def tdee(self) -> float:
        """Fabbisogno calorico giornaliero totale."""
        factor = self._ACTIVITY_FACTORS.get(self.activity_level, 1.55)
        return round(self.bmr * factor, 1)


class ScreeningRecord(Base):
    """Risposte al questionario di sicurezza (PAR-Q+).

    Versionato di proposito: un nuovo screening crea un nuovo record, non
    sovrascrive il precedente — serve poter ricostruire su quali risposte era
    basata una scheda generata mesi prima.
    """

    __tablename__ = "screening_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )

    heart_condition: Mapped[bool] = mapped_column(Boolean, default=False)
    chest_pain: Mapped[bool] = mapped_column(Boolean, default=False)
    dizziness_loss_consciousness: Mapped[bool] = mapped_column(Boolean, default=False)
    chronic_condition: Mapped[bool] = mapped_column(Boolean, default=False)
    blood_pressure_heart_medication: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    bone_joint_problem: Mapped[bool] = mapped_column(Boolean, default=False)
    pregnant_or_postpartum: Mapped[bool] = mapped_column(Boolean, default=False)
    eating_disorder_history: Mapped[bool] = mapped_column(Boolean, default=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped[UserProfile] = relationship(back_populates="screenings")

    _GATE_FIELDS = (
        "heart_condition",
        "chest_pain",
        "dizziness_loss_consciousness",
        "chronic_condition",
        "blood_pressure_heart_medication",
        "bone_joint_problem",
        "pregnant_or_postpartum",
        "eating_disorder_history",
    )

    @property
    def requires_medical_clearance(self) -> bool:
        """Un solo "sì" disattiva la generazione automatica di piani aggressivi
        (deficit marcato, progressione standard) — vedi
        `knowledge_base/screening_and_red_flags.md`."""
        return any(getattr(self, field) for field in self._GATE_FIELDS)


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_weight_profile_date", "profile_id", "date"),)


# --- Allenamento ------------------------------------------------------------


class Exercise(Base):
    """Cache locale del database esercizi wger.

    Stesso principio della vecchia cache dei nomi merchant: evita di
    ribattere l'API esterna a ogni generazione di scheda, e permette di
    generare schede anche se wger è momentaneamente irraggiungibile.
    """

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wger_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    primary_muscle: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    secondary_muscles: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_compound: Mapped[bool] = mapped_column(Boolean, default=False)

    # Provenienza: "everkinetic", "repdb", "free_exercise_db", "kilo" (scritti
    # a mano) oppure "wger" per le vecchie schede (vedi exercise_library).
    source: Mapped[str] = mapped_column(
        String(32), default="wger", server_default="wger", index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    # Stesso esercizio già presente in un'altra fonte: resta nel database per le
    # schede e le preferenze che lo usano, ma esce dal catalogo.
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercises.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Falso quando la fonte non fornisce più l'esercizio o le regole di import
    # lo escludono (es. esercizi a tempo). Come per i doppioni, resta nel
    # database per le schede che lo usano ma esce dal catalogo.
    in_catalog: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Più basso = esercizio "di base" del distretto, proposto per primo.
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    # Passaggi originali della fonte e fotogrammi dell'animazione.
    instructions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    demo_images: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Traduzioni italiane, salvate una volta per tutte (vedi translation).
    name_it: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    instructions_it: Mapped[list | None] = mapped_column(JSON, nullable=True)
    focus_it: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Consigli della fonte (Everkinetic li fornisce per alcuni esercizi).
    tips: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tips_it: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LlmCache(Base):
    """Risposte LLM riutilizzabili (traduzioni di ricette e ricerche).

    Una traduzione non cambia da una richiesta all'altra: rifarla ogni volta
    costerebbe quota e tempo, e renderebbe instabile il testo mostrato.
    """

    __tablename__ = "llm_cache"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_llm_cache_kind_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkoutPlan(Base):
    """Una scheda generata.

    Più schede possono essere attive insieme (es. una full body e una push,
    pull, gambe). Non viene mai cancellata: quando la si rigenera o la si
    elimina dall'interfaccia si archivia (`is_active=False`), così i report
    possono confrontare inizio e fine di un percorso."""

    __tablename__ = "workout_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(String(32))
    days_per_week: Mapped[int] = mapped_column(Integer)
    # Divisione effettivamente usata (vedi SplitType; mai "auto", già risolto).
    # Serve a distinguere le schede attive nelle schede dell'interfaccia.
    split_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Motivazione testuale generata dall'agente (perché questa scheda, per te).
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    started_at: Mapped[dt.date] = mapped_column(Date)
    ended_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    exercises: Mapped[list[WorkoutPlanExercise]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        # Ordine di inserimento = ordine in cui il generatore costruisce i
        # giorni (Push, Pull, Gambe). Per nome uscirebbero in ordine alfabetico.
        order_by="WorkoutPlanExercise.id",
    )


class WorkoutPlanExercise(Base):
    """Riga di una scheda: esercizio + parametri target.

    I parametri (serie, ripetizioni, RIR, recupero) vengono dai file
    `training_volume.md` e `rest_periods_and_rir.md`, non inventati dall'LLM.
    Si usa RIR invece della percentuale di 1RM perché si autoregola su
    stanchezza/sonno/stress del giorno.
    """

    __tablename__ = "workout_plan_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_plan_id: Mapped[int] = mapped_column(
        ForeignKey("workout_plans.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), index=True
    )

    day_label: Mapped[str] = mapped_column(String(32))  # es. "A", "Push", "Giorno 1"
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    target_sets: Mapped[int] = mapped_column(Integer)
    target_reps_min: Mapped[int] = mapped_column(Integer)
    target_reps_max: Mapped[int] = mapped_column(Integer)
    target_rir: Mapped[int] = mapped_column(Integer, default=2)
    rest_seconds: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[WorkoutPlan] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    workout_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    day_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    perceived_fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-10
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sets: Mapped[list[SessionSet]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionSet.id",
    )


class SessionSet(Base):
    """Singola serie realmente eseguita.

    È il dato più importante del sistema: 100% inserito dall'utente, nessuna
    dipendenza da API esterne. Alimenta i report (carico iniziale vs finale)
    e il rilevamento di plateau.
    """

    __tablename__ = "session_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), index=True
    )

    set_number: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float)
    rir: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[WorkoutSession] = relationship(back_populates="sets")
    exercise: Mapped[Exercise] = relationship()

    __table_args__ = (Index("ix_set_exercise_session", "exercise_id", "workout_session_id"),)

    @property
    def estimated_1rm(self) -> float:
        """Stima con la formula di Epley (`calorie_and_1rm_formulas.md`).

        Serve solo a confrontare i progressi nel tempo sullo stesso esercizio:
        non si propone mai un test di massimale reale a un principiante.
        """
        return round(self.weight_kg * (1 + self.reps / 30), 1)


class TrainingFeedback(Base):
    """Feedback dell'utente su come sta rispondendo all'allenamento.

    È l'input dell'autoregolazione del volume (`doms_and_autoregulation.md`):
    la combinazione "nessun progresso + DOMS prolungato" indica che il collo
    di bottiglia è il recupero, non lo stimolo — e la risposta corretta è
    **ridurre** il volume, non aumentarlo.
    """

    __tablename__ = "training_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    workout_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_plans.id", ondelete="SET NULL"), nullable=True
    )

    date: Mapped[dt.date] = mapped_column(Date, index=True)
    progress_perception: Mapped[str] = mapped_column(String(16))
    recovery_quality: Mapped[str] = mapped_column(String(16))
    # Durata dei DOMS in ore: oltre 72 è il segnale di recupero insufficiente.
    doms_duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # L'utente riferisce che i dolori compromettono le sessioni successive.
    affects_performance: Mapped[bool] = mapped_column(Boolean, default=False)
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExercisePreference(Base):
    """Gradimento dichiarato dall'utente per un esercizio.

    Serve all'aderenza (`exercise_choice_and_focus.md`): a parità di gruppo
    muscolare stimolato, un esercizio che l'utente sceglie e che gli piace
    vale più di uno "ottimale" che evita — una scheda abbandonata non
    produce risultati.
    """

    __tablename__ = "exercise_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
    # True = da preferire nelle prossime schede, False = da evitare.
    is_preferred: Mapped[bool] = mapped_column(Boolean, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    exercise: Mapped[Exercise] = relationship()

    __table_args__ = (
        Index("ix_preference_profile_exercise", "profile_id", "exercise_id", unique=True),
    )


# --- Nutrizione -------------------------------------------------------------


class Ingredient(Base):
    """Cache locale degli ingredienti.

    Valori per 100 g. wger/Open Food Facts copre bene i prodotti confezionati,
    USDA gli alimenti generici/grezzi — per questo la fonte è tracciata.
    """

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)

    kcal_100g: Mapped[float] = mapped_column(Float)
    protein_100g: Mapped[float] = mapped_column(Float)
    carbs_100g: Mapped[float] = mapped_column(Float)
    fat_100g: Mapped[float] = mapped_column(Float)
    sugars_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturated_fat_100g: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Codice a barre (EAN/UPC) del prodotto: una seconda scansione trova qui i
    # valori senza richiamare Open Food Facts.
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Solo per i prodotti inseriti a mano: sono visibili unicamente a chi li
    # ha inseriti, così un valore sbagliato (o malevolo) non finisce nel
    # diario di altri utenti che scansionano lo stesso codice.
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_ingredient_source_id", "source", "source_id"),)


class Recipe(Base):
    """Ricetta con macro **calcolati sommando gli ingredienti**, mai dichiarati
    dall'LLM: i modelli sbagliano l'aritmetica sui macro, il database no."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(32), default=RecipeSource.GENERATED)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    servings: Mapped[int] = mapped_column(Integer, default=1)

    # Compatibilità dietetica, per filtrare secondo `diet_type` del profilo.
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )

    def _sum_macro(self, attr: str) -> float:
        total = 0.0
        for row in self.ingredients:
            per_100g = getattr(row.ingredient, attr, None)
            if per_100g is not None:
                total += float(per_100g) * row.quantity_g / 100
        return round(total / max(self.servings, 1), 1)

    @property
    def kcal_per_serving(self) -> float:
        return self._sum_macro("kcal_100g")

    @property
    def protein_per_serving(self) -> float:
        return self._sum_macro("protein_100g")

    @property
    def carbs_per_serving(self) -> float:
        return self._sum_macro("carbs_100g")

    @property
    def fat_per_serving(self) -> float:
        return self._sum_macro("fat_100g")

    @property
    def sugars_per_serving(self) -> float:
        return self._sum_macro("sugars_100g")

    @property
    def fiber_per_serving(self) -> float:
        return self._sum_macro("fiber_100g")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    quantity_g: Mapped[float] = mapped_column(Float)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship()


class NutritionPlan(Base):
    """Target calorico e macro attivi.

    Calorie da TDEE ± percentuale obiettivo; proteine da `protein_intake.md`
    (ISSN, non dal valore EFSA per sedentari); carboidrati/grassi/fibra dai
    range EFSA in `macronutrients_efsa.md`.
    """

    __tablename__ = "nutrition_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    goal: Mapped[str] = mapped_column(String(32))

    target_kcal: Mapped[float] = mapped_column(Float)
    target_protein_g: Mapped[float] = mapped_column(Float)
    target_carbs_g: Mapped[float] = mapped_column(Float)
    target_fat_g: Mapped[float] = mapped_column(Float)
    target_fiber_g: Mapped[float] = mapped_column(Float, default=25.0)

    # Scostamento dal TDEE in percentuale (negativo = deficit). Oltre il -25%
    # scatta l'avviso REDs (`energy_availability_reds.md`).
    calorie_adjustment_pct: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    started_at: Mapped[dt.date] = mapped_column(Date)
    ended_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MealLog(Base):
    """Pasto pianificato o effettivamente consumato.

    Può puntare a una ricetta oppure essere un pasto libero con macro inseriti
    a mano (per non costringere l'utente a modellare tutto).
    """

    __tablename__ = "meal_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )

    date: Mapped[dt.date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    servings: Mapped[float] = mapped_column(Float, default=1.0)

    # Compilati solo per i pasti liberi (senza ricetta collegata).
    kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_planned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    recipe: Mapped[Recipe | None] = relationship()
    items: Mapped[list[MealItem]] = relationship(
        back_populates="meal_log", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_meal_profile_date", "profile_id", "date"),)


class MealItem(Base):
    """Singolo alimento pesato dentro un pasto.

    È il modello del contacalorie classico: l'utente cerca l'alimento, lo
    conferma e indica i grammi. Rimuove entrambe le approssimazioni
    dell'analisi automatica delle ricette — quale alimento è, e quanto pesa —
    e produce quindi un conteggio, non una stima.

    I valori nutrizionali sono **copiati qui al momento della registrazione**,
    non solo referenziati. Il catalogo viene risincronizzato e i dati di
    Open Food Facts vengono corretti dagli utenti nel tempo: senza questa
    copia, un pasto registrato mesi fa cambierebbe i propri valori da solo,
    falsando lo storico e i report di progressione.
    """

    __tablename__ = "meal_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_log_id: Mapped[int] = mapped_column(
        ForeignKey("meal_logs.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL"), nullable=True
    )

    # Nome al momento della registrazione: resta leggibile anche se in futuro
    # l'alimento venisse rimosso dal catalogo.
    name: Mapped[str] = mapped_column(String(300))
    quantity_g: Mapped[float] = mapped_column(Float)

    kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugars_g: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    meal_log: Mapped[MealLog] = relationship(back_populates="items")
    ingredient: Mapped[Ingredient | None] = relationship()


# --- Integratori ------------------------------------------------------------


class SupplementDeclaration(Base):
    """Integratore dichiarato dall'utente.

    L'agente non prescrive: valuta ciò che l'utente già assume rispetto ai
    range della knowledge base, e — punto importante — somma il contributo al
    totale giornaliero (es. le proteine in polvere rientrano nel target
    proteico, non si aggiungono "extra").
    """

    __tablename__ = "supplement_declarations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(32), index=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dose_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # g | mg | UI
    doses_per_day: Mapped[float] = mapped_column(Float, default=1.0)
    timing: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Per le proteine in polvere: quante proteine per dose, così l'agente può
    # sommarle al target giornaliero invece di trattarle come "extra".
    protein_g_per_dose: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Valutazione generata dall'agente + tag KB che l'ha prodotta.
    agent_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_source_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplementIntake(Base):
    """Assunzioni segnate in un giorno, per un integratore dichiarato.

    Una riga per giorno: `doses` conta le assunzioni, così una fase di carico
    da 4 dosi al giorno si segna dose per dose. Nessuna riga = giorno senza
    assunzioni.
    """

    __tablename__ = "supplement_intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplement_id: Mapped[int] = mapped_column(
        ForeignKey("supplement_declarations.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[dt.date] = mapped_column(Date)
    doses: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("supplement_id", "date", name="uq_supplement_intake_day"),
    )


class AgentNoteDismissal(Base):
    """Nota di Kilo chiusa dall'utente con «Ho capito».

    Sta nel database e non nel browser: una nota chiusa dal telefono non deve
    ricomparire sul computer. La chiave identifica l'evento (vedi
    `agent_notes.py`), quindi una situazione nuova produce una nota nuova.
    """

    __tablename__ = "agent_note_dismissals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    note_key: Mapped[str] = mapped_column(String(160))
    dismissed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "note_key", name="uq_agent_note_dismissal"),
    )


class ApiUsage(Base):
    """Quante volte un account ha usato oggi una funzione costosa (chat, LLM).

    Sta nel database e non in memoria: su Render gratuito il servizio si
    riavvia ogni volta che si addormenta, e un contatore in memoria
    ripartirebbe da zero.
    """

    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("user_id", "day", "kind", name="uq_api_usage_day"),)


# --- Tracciabilità delle raccomandazioni ------------------------------------


class AgentRecommendationLog(Base):
    """Traccia ispezionabile di ogni output rilevante dell'agente.

    Erede diretto di `ghost_audit_log` del progetto precedente, stesso
    principio: si deve sempre poter rispondere a "perché mi ha consigliato
    questo, e sulla base di quale fonte".
    """

    __tablename__ = "agent_recommendation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )

    recommendation_type: Mapped[str] = mapped_column(String(48), index=True)
    # Id dell'entità generata (scheda, piano, integratore…), se applicabile.
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    summary: Mapped[str] = mapped_column(Text)
    # Tag dei file knowledge base iniettati nel prompt, separati da virgola
    # (es. "volume_allenamento,recupero,screening").
    knowledge_source_tags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Se l'LLM non era disponibile o non è stato usato (output puramente
    # deterministico dai parametri KB), va registrato per trasparenza.
    used_llm: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
