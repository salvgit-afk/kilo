"use client";

/**
 * Schede di allenamento: più schede attive, giornate, esercizi, alternative
 * e feedback.
 *
 * Tre elementi non sono decorativi:
 *  - le **avvertenze** e le **fonti** stanno accanto alla scheda, non
 *    nascoste in un dettaglio;
 *  - ogni esercizio mostra **il movimento** già nella riga, e il cambio
 *    esercizio apre le alternative *viste*, non una lista di nomi: per
 *    scegliere bisogna capire di che esercizio si tratta;
 *  - il **feedback** ("non vedo progressi, i DOMS durano troppo") è
 *    raggiungibile dalla scheda stessa, perché è lì che l'utente si accorge
 *    del problema.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  EXPERIENCE_LABELS,
  GOAL_LABELS,
  MUSCLE_LABELS,
  SPLIT_HINTS,
  SPLIT_LABELS,
  api,
  exerciseName,
  formatEquipment,
  type Alternative,
  type PlanExercise,
  type PlanGeneration,
  type Profile,
  type VolumeRecommendation,
  type WorkoutPlan,
  type WorkoutSessionLog,
  localDate,
} from "@/lib/api";
import type { Intent } from "@/lib/coach";
import { Card, CardHeader, Empty, Notice, SourceTags, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import { ExerciseDetailHost } from "@/components/ExerciseDetail";
import { PreferencesDialog } from "@/components/PreferencesDialog";
import {
  AskCoachButton,
  DemoAnimation,
  Field,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  OptionGroup,
  Stepper,
  Toggle,
} from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { KiloNote } from "@/components/KiloNote";
import { ParamsChips, PlanParamsDialog, SessionDialog, clock, useElapsed } from "@/components/TrainingLog";
import { ScheduleDialog, WEEKDAY_NAMES, WeekLine, WeekdayPicker, defaultWeekdays } from "@/components/WeekSchedule";

export { formatEquipment } from "@/lib/api";

type PlanMeta = Omit<PlanGeneration, "plan">;

type PlanOptions = {
  split: string;
  weekdays?: number[];
  replacePlanId?: number;
  sets?: number | null;
  repsMin?: number | null;
  repsMax?: number | null;
};

/** Nome breve della scheda per le linguette: la divisione e i giorni. */
function planLabel(plan: WorkoutPlan) {
  const divisione = plan.split_type ? SPLIT_LABELS[plan.split_type] : null;
  return `${divisione ?? plan.name.split(" — ")[0]} · ${plan.days_per_week} g`;
}

export function Workout({
  profile,
  intent,
  onIntentHandled,
}: {
  profile: Profile;
  intent?: Intent | null;
  onIntentHandled?: () => void;
}) {
  const [plans, setPlans] = useState<WorkoutPlan[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [metaById, setMetaById] = useState<Record<number, PlanMeta>>({});
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [swapping, setSwapping] = useState<PlanExercise | null>(null);
  const [editingParams, setEditingParams] = useState<PlanExercise | null>(null);
  const [editingSchedule, setEditingSchedule] = useState(false);
  // Tendina aperta nella card della scheda: scelta della scheda o opzioni.
  const [menu, setMenu] = useState<"piano" | "opzioni" | null>(null);
  // Copia degli esercizi fatta all'apertura: la sessione non deve ricaricarsi
  // (e azzerare le serie in corso) a ogni render della pagina.
  const [sessionDay, setSessionDay] = useState<{ plan: WorkoutPlan; day: string; exercises: PlanExercise[] } | null>(null);
  // L'allenamento avviato e non terminato: il pulsante diventa "in corso".
  const [activeSession, setActiveSession] = useState<WorkoutSessionLog | null>(null);
  // Overlay di creazione: `replace` è la scheda da rigenerare, null per una nuova.
  const [dialog, setDialog] = useState<{ replace: WorkoutPlan | null } | null>(null);
  const [deleting, setDeleting] = useState<WorkoutPlan | null>(null);

  const selectPlan = useCallback((p: WorkoutPlan | null) => {
    setSelectedId(p?.id ?? null);
    setActiveDay(p?.exercises[0]?.day_label ?? null);
  }, []);

  useEffect(() => {
    api
      .get<WorkoutPlan[]>(`/workout/plans?profile_id=${profile.id}&active_only=true`)
      .then((lista) => {
        // Se nel frattempo è arrivata una scheda appena generata, vince quella.
        setPlans((correnti) => {
          if (correnti) return correnti;
          selectPlan(lista[0] ?? null);
          return lista;
        });
      })
      .catch(() => setPlans((correnti) => correnti ?? []));
  }, [profile.id, selectPlan]);

  const generate = useCallback(
    async (opts: PlanOptions) => {
      setDialog(null);
      setGenerating(true);
      setError(null);
      const params = new URLSearchParams({
        profile_id: String(profile.id),
        explain: "true",
        split_type: opts.split,
      });
      if (opts.replacePlanId) params.set("replace_plan_id", String(opts.replacePlanId));
      opts.weekdays?.forEach((g) => params.append("weekdays", String(g)));
      if (opts.sets) params.set("sets_per_exercise", String(opts.sets));
      if (opts.repsMin && opts.repsMax) {
        params.set("reps_min", String(opts.repsMin));
        params.set("reps_max", String(opts.repsMax));
      }
      try {
        const res = await api.post<PlanGeneration>(`/workout/plans/generate?${params}`);
        // La più recente in testa, come la ordina il backend.
        setPlans((correnti) => [
          res.plan,
          ...(correnti ?? []).filter((p) => p.id !== opts.replacePlanId),
        ]);
        setMetaById((m) => ({
          ...m,
          [res.plan.id]: {
            weekly_sets_per_muscle: res.weekly_sets_per_muscle,
            warnings: res.warnings,
            knowledge_tags: res.knowledge_tags,
          },
        }));
        selectPlan(res.plan);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Non sono riuscito a generare la scheda");
      } finally {
        setGenerating(false);
      }
    },
    [profile.id, selectPlan]
  );

  // Il coach ha proposto una scheda e l'utente ha confermato con un clic.
  useEffect(() => {
    if (intent?.section === "scheda" && intent.generateSplit) {
      generate({ split: intent.generateSplit });
      onIntentHandled?.();
    }
  }, [intent, generate, onIntentHandled]);

  async function removePlan(target: WorkoutPlan) {
    await api.del(`/workout/plans/${target.id}?profile_id=${profile.id}`);
    const rimaste = (plans ?? []).filter((p) => p.id !== target.id);
    setPlans(rimaste);
    if (target.id === selectedId) selectPlan(rimaste[0] ?? null);
    setDeleting(null);
  }

  // L'allenamento in corso, se c'è. Prima di ogni return anticipato: gli hook
  // devono essere sempre gli stessi, in ogni render.
  useEffect(() => {
    api
      .get<WorkoutSessionLog | null>(`/workout/sessions/active?profile_id=${profile.id}&today=${localDate()}`)
      .then(setActiveSession)
      .catch(() => setActiveSession(null));
  }, [profile.id]);

  if (plans === null) return <Spinner label="Carico le schede…" />;

  const plan = plans.find((p) => p.id === selectedId) ?? null;
  const meta = plan ? metaById[plan.id] : undefined;
  const days = plan ? [...new Set(plan.exercises.map((e) => e.day_label))] : [];
  const dayExercises = plan?.exercises.filter((e) => e.day_label === activeDay) ?? [];

  function openActive() {
    if (!activeSession) return;
    const suo = plans?.find((p) => p.id === activeSession.workout_plan_id) ?? plan;
    if (!suo || !activeSession.day_label) return;
    setSessionDay({
      plan: suo,
      day: activeSession.day_label,
      exercises: suo.exercises.filter((e) => e.day_label === activeSession.day_label),
    });
  }

  function replacePlan(aggiornata: WorkoutPlan) {
    setPlans((correnti) => (correnti ?? []).map((p) => (p.id === aggiornata.id ? aggiornata : p)));
  }

  return (
    <>
      <PageHeader
        eyebrow="Allenamento"
        title={plan ? "La tua scheda" : "Nessuna scheda attiva"}
        description={
          plan
            ? undefined
            : "Genero una scheda sui parametri del tuo profilo, presi dai documenti della knowledge base."
        }
      />

      {error && (
        <div className="mb-4">
          <Notice>{error}</Notice>
        </div>
      )}

      {generating && (
        <Card className="mb-4">
          <div className="flex items-center gap-4 px-5 py-4">
            <Mascot size={44} mood="thinking" />
            <div>
              <p className="text-[14px] font-medium text-white">Sto costruendo la scheda…</p>
              <p className="text-[12.5px] text-white/45">
                Volume, ripetizioni e recuperi dai parametri delle fonti; esercizi dalle tue
                preferenze. Serve qualche secondo.
              </p>
            </div>
          </div>
        </Card>
      )}

      {!plan ? (
        !generating && (
          <Card>
            <div className="grid place-items-center px-6 py-12 text-center">
              <Mascot size={58} interactive />
              <p className="mt-3 text-[14px] text-white/75">Non hai ancora una scheda</p>
              <p className="mt-1 max-w-sm text-[12.5px] leading-relaxed text-white/40">
                Serie, ripetizioni, RIR e recuperi vengono calcolati dai parametri delle fonti,
                non inventati dal modello. Puoi tenere più schede, per esempio una full body e
                una push, pull, gambe.
              </p>
              <button className="btn-primary mt-5" onClick={() => setDialog({ replace: null })}>
                <Sparkle /> Genera con Kilo
              </button>
            </div>
          </Card>
        )
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            {/* Tutto ciò che riguarda la scheda in una card: quale scheda,
                la settimana, il giorno e l'avvio. Le azioni rare stanno nel
                menu «⋯», per non occupare la pagina. */}
            <div className="glass relative z-20 p-3.5 sm:p-4">
              <div className="flex items-center gap-2">
                <div className="relative min-w-0 flex-1">
                  <button
                    onClick={() => setMenu(menu === "piano" ? null : "piano")}
                    aria-expanded={menu === "piano"}
                    aria-haspopup="menu"
                    className="flex h-12 w-full items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.06] pl-4 pr-3.5 text-left transition hover:border-white/20"
                  >
                    <span className="min-w-0 truncate text-[15px] font-semibold text-white">{plan.name}</span>
                    <span className="shrink-0 text-[12.5px] text-white/45">
                      · {plan.training_weekdays.length} {plan.training_weekdays.length === 1 ? "giorno" : "giorni"}
                    </span>
                    <svg
                      viewBox="0 0 24 24"
                      className={`ml-auto h-4 w-4 shrink-0 fill-white/50 transition-transform duration-300 ${menu === "piano" ? "rotate-180" : ""}`}
                    >
                      <path d="M7 10l5 5 5-5H7Z" />
                    </svg>
                  </button>
                  <Popover open={menu === "piano"} onClose={() => setMenu(null)} className="left-0 right-0">
                    {plans.map((p) => (
                      <MenuItem
                        key={p.id}
                        onClick={() => {
                          selectPlan(p);
                          setMenu(null);
                        }}
                        active={p.id === selectedId}
                      >
                        <span className="min-w-0 truncate">{p.name}</span>
                        <span className="shrink-0 text-white/40">
                          · {p.training_weekdays.length} {p.training_weekdays.length === 1 ? "giorno" : "giorni"}
                        </span>
                      </MenuItem>
                    ))}
                    <div className="mx-2 my-1 border-t border-white/[0.07]" />
                    <MenuItem
                      tone="accent"
                      disabled={generating}
                      onClick={() => {
                        setMenu(null);
                        setDialog({ replace: null });
                      }}
                    >
                      <Sparkle /> Genera con Kilo
                    </MenuItem>
                  </Popover>
                </div>

                <div className="relative shrink-0">
                  <button
                    onClick={() => setMenu(menu === "opzioni" ? null : "opzioni")}
                    aria-expanded={menu === "opzioni"}
                    aria-haspopup="menu"
                    aria-label="Opzioni della scheda"
                    className="grid h-12 w-12 place-items-center rounded-full border border-white/10 bg-white/[0.05] text-white/75 transition hover:border-white/20 hover:text-white"
                  >
                    <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
                      <circle cx="5" cy="12" r="2" />
                      <circle cx="12" cy="12" r="2" />
                      <circle cx="19" cy="12" r="2" />
                    </svg>
                  </button>
                  <Popover open={menu === "opzioni"} onClose={() => setMenu(null)} className="right-0 w-64">
                    <MenuItem
                      onClick={() => {
                        setMenu(null);
                        setEditingSchedule(true);
                      }}
                      icon="M7 2h2v2h6V2h2v2h3v18H4V4h3V2Zm11 8H6v10h12V10Z"
                    >
                      Cambia giorni
                    </MenuItem>
                    <div className="mx-2 my-1 border-t border-white/[0.07]" />
                    <MenuItem
                      tone="danger"
                      onClick={() => {
                        setMenu(null);
                        setDeleting(plan);
                      }}
                      icon="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Z"
                    >
                      Elimina scheda
                    </MenuItem>
                  </Popover>
                </div>
              </div>

              <div className="mt-4">
                <WeekLine plan={plan} profileId={profile.id} onOpenDay={(label) => setActiveDay(label)} />
              </div>

              <div className="mt-4 flex items-center justify-between gap-2">
                <div className="-my-1 min-w-0 overflow-x-auto py-1">
                  <div className="inline-flex gap-1 rounded-2xl border border-white/10 bg-white/[0.03] p-1">
                    {days.map((d) => (
                      <button
                        key={d}
                        onClick={() => setActiveDay(d)}
                        className={`relative h-9 shrink-0 rounded-xl px-4 text-[13px] font-semibold transition ${
                          d === activeDay ? "text-ink-900" : "text-white/55 hover:text-white"
                        }`}
                      >
                        {d === activeDay && (
                          <motion.span
                            layoutId="day-pill"
                            className="absolute inset-0 rounded-xl bg-gradient-to-b from-lime-400 to-lime-500"
                            transition={{ type: "spring", stiffness: 380, damping: 30 }}
                          />
                        )}
                        <span className="relative">{d}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => setFeedbackOpen(true)}
                  className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full border border-iris-400/35 bg-iris-400/[0.12] px-3.5 text-[12.5px] font-semibold text-iris-100 transition hover:bg-iris-400/20"
                  title="Racconta a Kilo progressi e recupero: ti dice se mantenere, aumentare o ridurre il volume"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                    <path d="M4 4h16v12H8l-4 4V4Z" />
                  </svg>
                  Com&apos;è andata?
                </button>
              </div>

              <div className="mt-3">
                <AnimatePresence mode="wait" initial={false}>
                  {activeSession ? (
                    <ActiveWorkoutPill key="in-corso" session={activeSession} onOpen={openActive} />
                  ) : (
                    activeDay &&
                    dayExercises.length > 0 && (
                      <motion.button
                        key="inizia"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        onClick={() => setSessionDay({ plan, day: activeDay, exercises: dayExercises })}
                        className="btn-primary w-full justify-center py-3.5 text-[14.5px]"
                      >
                        <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                          <path d="M8 5v14l11-7L8 5Z" />
                        </svg>
                        Inizia allenamento · {activeDay.length <= 2 ? `giorno ${activeDay}` : activeDay}
                      </motion.button>
                    )
                  )}
                </AnimatePresence>
              </div>
            </div>

            <KiloNote
              section="scheda"
              onAction={(azione) => azione === "feedback" && setFeedbackOpen(true)}
            />

            <div className="space-y-2.5">
              <AnimatePresence mode="popLayout">
                {dayExercises.map((ex, i) => (
                  <ExerciseRow
                    key={ex.id}
                    item={ex}
                    index={i}
                    onOpenDetail={setDetailId}
                    onSwap={setSwapping}
                    onEdit={setEditingParams}
                  />
                ))}
              </AnimatePresence>
            </div>
          </div>

          <div className="space-y-4">
            {meta?.warnings.map((w, i) => <Notice key={i}>{w}</Notice>)}

            {plan.rationale && (
              <Card delay={0.05}>
                <CardHeader title="Perché questa scheda" />
                <div className="space-y-3 px-5 py-4">
                  <p className="whitespace-pre-line text-[13px] leading-relaxed text-white/65">
                    {plan.rationale}
                  </p>
                  {meta && <SourceTags tags={meta.knowledge_tags} />}
                  <AskCoachButton
                    size="sm"
                    question="Spiegami come è costruita la mia scheda: perché queste serie, queste ripetizioni e questi recuperi?"
                    context={`Sezione Scheda: ${plan.name}`}
                    label="Fammela spiegare da Kilo"
                  />
                </div>
              </Card>
            )}

            {meta && (
              <Card delay={0.1}>
                <CardHeader title="Volume settimanale" subtitle="Serie per gruppo muscolare" />
                <div className="space-y-2 px-5 py-4">
                  {Object.entries(meta.weekly_sets_per_muscle).map(([m, s]) => (
                    <div key={m} className="flex items-center gap-3">
                      <span className="w-24 shrink-0 truncate text-[12px] text-white/50">
                        {MUSCLE_LABELS[m] ?? m}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                        <motion.div
                          className="h-full rounded-full bg-gradient-to-r from-iris-400 to-iris-500"
                          initial={{ width: 0 }}
                          animate={{ width: `${Math.min(s / 20, 1) * 100}%` }}
                          transition={{ duration: 0.7 }}
                        />
                      </div>
                      <span className="w-6 text-right font-mono text-[12px] tabular-nums text-white/70">
                        {s}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      <AnimatePresence>
        {feedbackOpen && plan && (
          <FeedbackDialog
            profileId={profile.id}
            planId={plan.id}
            onClose={() => setFeedbackOpen(false)}
          />
        )}
        {dialog && (
          <PlanDialog
            key="plan-dialog"
            profile={profile}
            current={plan}
            onClose={() => setDialog(null)}
            onGenerate={generate}
            onOpenPrefs={() => setPrefsOpen(true)}
          />
        )}
        {prefsOpen && (
          <PreferencesDialog profileId={profile.id} onClose={() => setPrefsOpen(false)} />
        )}
        {deleting && (
          <DeletePlanDialog
            key="delete-dialog"
            plan={deleting}
            onClose={() => setDeleting(null)}
            onConfirm={() => removePlan(deleting)}
          />
        )}
        {editingSchedule && plan && (
          <ScheduleDialog
            key="schedule"
            plan={plan}
            profileId={profile.id}
            onClose={() => setEditingSchedule(false)}
            onSaved={replacePlan}
          />
        )}
        {editingParams && (
          <PlanParamsDialog
            key="params"
            item={editingParams}
            profileId={profile.id}
            onClose={() => setEditingParams(null)}
            onSaved={replacePlan}
          />
        )}
        {sessionDay && (
          <SessionDialog
            key="session"
            profileId={profile.id}
            plan={sessionDay.plan}
            dayLabel={sessionDay.day}
            exercises={sessionDay.exercises}
            onClose={() => setSessionDay(null)}
            onPlanUpdated={replacePlan}
            onSessionChange={setActiveSession}
          />
        )}
        {swapping && (
          <AlternativesDialog
            key={swapping.id}
            item={swapping}
            profileId={profile.id}
            onClose={() => setSwapping(null)}
            onSwapped={(aggiornata) =>
              setPlans((correnti) =>
                (correnti ?? []).map((p) => (p.id === aggiornata.id ? aggiornata : p))
              )
            }
            onOpenDetail={setDetailId}
          />
        )}
      </AnimatePresence>

      <ExerciseDetailHost
        exerciseId={detailId}
        profileId={profile.id}
        onClose={() => setDetailId(null)}
      />
    </>
  );
}

/**
 * Creazione di una scheda, che prende anche il posto del vecchio «Rigenera».
 *
 * Due strade:
 *  - **Kilo sceglie per te**: divisione, giorni, serie e ripetizioni dal
 *    profilo e dai parametri delle fonti, senza altre domande;
 *  - **Scelgo io**: giorni, divisione, esercizi preferiti ed eventualmente
 *    serie e ripetizioni decise dall'utente (dichiarate come tali).
 * Se c'è già una scheda si sceglie se affiancarla o sostituirla: quella
 * sostituita resta nello storico dei progressi.
 */
function PlanDialog({
  profile,
  current,
  onClose,
  onGenerate,
  onOpenPrefs,
}: {
  profile: Profile;
  current: WorkoutPlan | null;
  onClose: () => void;
  onGenerate: (opts: PlanOptions) => void;
  onOpenPrefs: () => void;
}) {
  const [mode, setMode] = useState<"kilo" | "custom">("kilo");
  const [replace, setReplace] = useState(false);
  const [split, setSplit] = useState(profile.split_type ?? "auto");
  const giorniProfilo = defaultWeekdays(profile.training_days_per_week);
  const [weekdays, setWeekdays] = useState<number[]>(current?.training_weekdays ?? giorniProfilo);
  const [manual, setManual] = useState(false);
  const [sets, setSets] = useState(3);
  const [repsMin, setRepsMin] = useState(6);
  const [repsMax, setRepsMax] = useState(8);

  const invalido = mode === "custom" && !weekdays.length;
  const sostituisci = replace && current ? current.id : undefined;

  function genera() {
    if (mode === "kilo") {
      onGenerate({ split: "auto", weekdays: giorniProfilo, replacePlanId: sostituisci });
    } else {
      onGenerate({
        split,
        weekdays,
        replacePlanId: sostituisci,
        sets: manual ? sets : null,
        repsMin: manual ? repsMin : null,
        repsMax: manual ? repsMax : null,
      });
    }
  }

  const riepilogo: [string, string][] = [
    ["Obiettivo", GOAL_LABELS[profile.goal] ?? profile.goal],
    ["Esperienza", EXPERIENCE_LABELS[profile.experience_level] ?? profile.experience_level],
    ["Giorni", giorniProfilo.map((g) => WEEKDAY_NAMES[g].slice(0, 3)).join(", ")],
    ["Attrezzatura", profile.available_equipment?.trim() || "palestra attrezzata"],
  ];

  return (
    <Modal onClose={onClose} className="max-w-lg">
      <ModalHeader
        eyebrow="Nuova scheda"
        title="Crea una scheda"
        subtitle="Lasciala costruire a Kilo dal tuo profilo, o decidi tu divisione, giorni ed esercizi."
        onClose={onClose}
      />

      <ModalBody>
        <OptionGroup
          ariaLabel="Come crearla"
          columns="grid-cols-2"
          value={mode}
          onChange={setMode}
          options={[
            { value: "kilo", label: "Kilo sceglie per te", hint: "Dal profilo e dalle fonti" },
            { value: "custom", label: "Scelgo io", hint: "Divisione, giorni, esercizi" },
          ]}
        />

        {mode === "kilo" ? (
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-3.5">
            <div className="flex items-start gap-3">
              <Mascot size={40} mood="happy" />
              <p className="min-w-0 text-[12.5px] leading-relaxed text-white/60">
                Scelgo la divisione adatta ai tuoi giorni e calcolo serie, ripetizioni, RIR e
                recuperi dai documenti della knowledge base. Gli esercizi preferiti entrano per primi.
              </p>
            </div>
            <dl className="mt-3 divide-y divide-white/[0.06] text-[13px]">
              {riepilogo.map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-3 py-2">
                  <dt className="text-white/45">{k}</dt>
                  <dd className="min-w-0 truncate text-right font-medium text-white/85">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-1 text-[11.5px] leading-snug text-white/35">
              Sono i dati del Profilo: per cambiarli vai lì, oppure scegli «Scelgo io».
            </p>
          </div>
        ) : (
          <>
            <Field title="Giorni di allenamento">
              <WeekdayPicker value={weekdays} onChange={setWeekdays} />
            </Field>

            <Field title="Divisione" hint={SPLIT_HINTS[split]}>
              <OptionGroup
                ariaLabel="Divisione"
                columns="grid-cols-2"
                value={split}
                onChange={setSplit}
                options={Object.entries(SPLIT_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Field>

            <Field
              title="Esercizi preferiti"
              hint="Quelli che scegli entrano per primi nella scheda"
              action={
                <button className="btn-ghost shrink-0 px-3 py-2 text-[12.5px]" onClick={onOpenPrefs}>
                  Scegli
                </button>
              }
            />

            <Toggle
              checked={manual}
              onChange={setManual}
              label="Decido io serie e ripetizioni"
              hint={
                manual
                  ? "Valgono per tutti gli esercizi e non seguono più le fonti: la scheda lo segnalerà. RIR e recuperi restano calcolati."
                  : "Altrimenti le calcolo dalle fonti in base a obiettivo e livello."
              }
            />
            {manual && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Field title="Serie">
                  <Stepper compact value={sets} onChange={setSets} min={1} max={10} label="serie per esercizio" />
                </Field>
                <Field title="Rip. min">
                  <Stepper
                    compact
                    value={repsMin}
                    onChange={(n) => {
                      setRepsMin(n);
                      setRepsMax((m) => Math.max(m, n));
                    }}
                    min={1}
                    max={50}
                    label="ripetizioni minime"
                  />
                </Field>
                <Field title="Rip. max">
                  <Stepper
                    compact
                    value={repsMax}
                    onChange={(n) => {
                      setRepsMax(n);
                      setRepsMin((m) => Math.min(m, n));
                    }}
                    min={1}
                    max={50}
                    label="ripetizioni massime"
                  />
                </Field>
              </div>
            )}
          </>
        )}

        {current && (
          <Toggle
            checked={replace}
            onChange={setReplace}
            label={`Sostituisci «${planLabel(current)}»`}
            hint={
              replace
                ? "La nuova prende il suo posto; quella attuale resta nello storico dei progressi."
                : "Altrimenti la nuova si aggiunge alle schede che hai già."
            }
          />
        )}
      </ModalBody>

      <ModalFooter>
        <button className="btn-ghost flex-1 justify-center" onClick={onClose}>
          Annulla
        </button>
        <button className="btn-primary flex-[1.6] justify-center" disabled={invalido} onClick={genera}>
          {replace && current ? "Sostituisci scheda" : "Genera scheda"}
        </button>
      </ModalFooter>
    </Modal>
  );
}

function DeletePlanDialog({
  plan,
  onClose,
  onConfirm,
}: {
  plan: WorkoutPlan;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eliminazione non riuscita");
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="max-w-md">
      <ModalHeader
        eyebrow="Elimina scheda"
        title={`Eliminare «${planLabel(plan)}»?`}
        subtitle="Sparisce dalle tue schede. Le sessioni già registrate restano nei progressi."
        onClose={onClose}
      />
      {error && (
        <ModalBody>
          <Notice>{error}</Notice>
        </ModalBody>
      )}
      <ModalFooter>
        <button className="btn-ghost flex-1 justify-center" onClick={onClose}>
          Annulla
        </button>
        <button className="btn-danger flex-[1.6] justify-center" disabled={busy} onClick={confirm}>
          {busy ? "Elimino…" : "Elimina"}
        </button>
      </ModalFooter>
    </Modal>
  );
}

function thumbnails(ex: PlanExercise["exercise"]) {
  return ex.demo_images?.length ? ex.demo_images : ex.image_url ? [ex.image_url] : [];
}

function ExerciseRow({
  item,
  index,
  onOpenDetail,
  onSwap,
  onEdit,
}: {
  item: PlanExercise;
  index: number;
  onOpenDetail: (id: number) => void;
  onSwap: (item: PlanExercise) => void;
  onEdit: (item: PlanExercise) => void;
}) {
  const ex = item.exercise;
  const nome = exerciseName(ex);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ delay: index * 0.035 }}
      className="glass sheen glass-hover overflow-hidden"
    >
      <div className="flex items-center gap-3.5 px-3.5 py-3">
        <button
          onClick={() => onOpenDetail(ex.id)}
          className="group relative shrink-0"
          title="Vedi come si esegue"
        >
          <DemoAnimation
            images={thumbnails(ex)}
            alt={nome}
            mode="hover"
            fit="contain"
            className="h-14 w-[76px] rounded-xl border border-white/10"
          />
          <span className="absolute -left-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-md border border-white/10 bg-ink-800 px-1 font-mono text-[10px] text-white/65">
            {index + 1}
          </span>
        </button>

        <button
          onClick={() => onOpenDetail(ex.id)}
          className="group min-w-0 flex-1 text-left"
          title="Vedi come si esegue"
        >
          <p className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-white underline-offset-4 group-hover:underline">
            {nome}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11.5px] text-white/40">
            <span>{MUSCLE_LABELS[ex.primary_muscle ?? ""] ?? ex.primary_muscle}</span>
            <span className="text-white/15">•</span>
            <span>{ex.is_compound ? "multi-articolare" : "isolamento"}</span>
            <span className="text-white/15">•</span>
            <span className="truncate">{formatEquipment(ex.equipment)}</span>
          </div>
        </button>

        <button
          onClick={() => onSwap(item)}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] px-2.5 py-2 text-[12px] font-medium text-white/60 transition hover:border-lime-400/30 hover:bg-lime-400/[0.08] hover:text-lime-200"
          title="Non ti piace? Scegli un'alternativa per lo stesso muscolo"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
            <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7Zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4Z" />
          </svg>
          <span className="hidden md:inline">Cambia</span>
        </button>
      </div>

      <div className="px-3.5 pb-3">
        <ParamsChips value={item} onEdit={() => onEdit(item)} />
      </div>
    </motion.div>
  );
}

/**
 * Cambio esercizio: le alternative come schede con l'animazione, il tipo di
 * esercizio e il primo spunto di focus muscolare — abbastanza per capire di
 * cosa si tratta prima di sceglierlo.
 */
function AlternativesDialog({
  item,
  profileId,
  onClose,
  onSwapped,
  onOpenDetail,
}: {
  item: PlanExercise;
  profileId: number;
  onClose: () => void;
  onSwapped: (plan: WorkoutPlan) => void;
  onOpenDetail: (id: number) => void;
}) {
  const [alts, setAlts] = useState<Alternative[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setAlts(null);
    const q = query.trim() ? `&q=${encodeURIComponent(query.trim())}` : "";
    // Durante la ricerca si aspetta che l'utente smetta di scrivere.
    const timer = setTimeout(
      () => {
        api
          .get<Alternative[]>(
            `/workout/plan-exercises/${item.id}/alternatives?profile_id=${profileId}&limit=24${q}`
          )
          .then(setAlts)
          .catch((e) => {
            setAlts([]);
            setError(e instanceof Error ? e.message : "Alternative non disponibili");
          });
      },
      query ? 300 : 0
    );
    return () => clearTimeout(timer);
  }, [item.id, profileId, query]);

  async function swap(exerciseId: number) {
    setBusy(exerciseId);
    setError(null);
    try {
      const updated = await api.post<WorkoutPlan>(
        `/workout/plan-exercises/${item.id}/swap?profile_id=${profileId}`,
        { replacement_exercise_id: exerciseId, mark_old_as_disliked: true }
      );
      onSwapped(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sostituzione non riuscita");
    } finally {
      setBusy(null);
    }
  }

  const attuale = item.exercise;
  const muscolo = MUSCLE_LABELS[attuale.primary_muscle ?? ""] ?? attuale.primary_muscle;

  return (
    <Modal onClose={onClose} className="max-w-3xl">
      <ModalHeader
        eyebrow={`Cambia esercizio · ${muscolo}`}
        title={`Al posto di «${exerciseName(attuale)}»`}
        subtitle={`Stesso muscolo principale: restano ${item.target_sets} × ${item.target_reps_min}-${item.target_reps_max} a RIR ${item.target_rir}. Scegli quello in cui senti meglio il muscolo e che esegui volentieri.`}
        onClose={onClose}
      />

      <div className="shrink-0 border-b border-white/[0.06] px-4 py-3">
        <input
          className="input py-2 text-[13px]"
          placeholder="Cerca fra le alternative — es. cavi, manubri, macchina, hammer"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {error && (
          <div className="mb-3">
            <Notice>{error}</Notice>
          </div>
        )}
        {!alts ? (
          <Spinner label="Cerco le alternative…" />
        ) : alts.length === 0 ? (
          !error && (
            <Empty
              title={
                query.trim()
                  ? "Nessuna alternativa con questo nome"
                  : "Nessuna alternativa disponibile con la tua attrezzatura"
              }
            />
          )
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {alts.map((a, i) => {
              const ex = a.exercise;
              const nome = exerciseName(ex);
              return (
                <motion.div
                  key={ex.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.025] transition hover:border-lime-400/30"
                >
                  <button
                    onClick={() => onOpenDetail(ex.id)}
                    className="group relative block"
                    title="Come si esegue"
                  >
                    {/* "contain": i disegni interi, non ritagliati */}
                    <DemoAnimation images={thumbnails(ex)} alt={nome} fit="contain" className="aspect-[16/10] w-full" />
                    <div className="absolute left-2 top-2 flex flex-wrap gap-1">
                      {a.already_preferred && (
                        <span className="pill bg-lime-400 text-ink-900">tra i preferiti</span>
                      )}
                      {a.preserves_stimulus && (
                        <span
                          className="pill bg-black/65 text-lime-200 backdrop-blur-md"
                          title="Stessa tipologia: anche il recupero resta uguale"
                        >
                          stessa tipologia
                        </span>
                      )}
                    </div>
                    <span className="absolute bottom-2 right-2 rounded-full bg-black/65 px-2.5 py-1 text-[10.5px] text-white/90 opacity-0 backdrop-blur-md transition group-hover:opacity-100">
                      Come si esegue →
                    </span>
                  </button>
                  <div className="flex flex-1 flex-col gap-1.5 p-3.5">
                    <p className="text-[14px] font-medium leading-snug text-white">{nome}</p>
                    <p className="text-[11.5px] text-white/40">
                      {ex.is_compound ? "Multi-articolare" : "Isolamento"} ·{" "}
                      {formatEquipment(ex.equipment)}
                    </p>
                    {ex.focus_it?.[0] && (
                      <p className="text-[12px] leading-snug text-white/55">
                        <span className="text-lime-300/80">Focus:</span> {ex.focus_it[0]}
                      </p>
                    )}
                    <div className="mt-auto flex gap-2 pt-2">
                      <button
                        className="btn-ghost flex-1 px-3 py-2 text-[12.5px]"
                        onClick={() => onOpenDetail(ex.id)}
                      >
                        Esecuzione
                      </button>
                      <button
                        className="btn-primary flex-1 px-3 py-2 text-[12.5px]"
                        disabled={busy !== null}
                        onClick={() => swap(ex.id)}
                      >
                        {busy === ex.id ? "Cambio…" : "Scegli questo"}
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      <p className="shrink-0 border-t border-white/[0.06] px-5 py-3 text-[11.5px] leading-snug text-white/35">
        L'esercizio sostituito non ti verrà più proposto nelle prossime schede; quello che
        scegli diventa un preferito.
      </p>
    </Modal>
  );
}

/**
 * Il dialogo che trasforma «non vedo progressi» in una decisione.
 *
 * La stessa lamentela porta a conclusioni opposte a seconda del recupero, ed
 * è esattamente il motivo per cui vengono chieste due cose separate.
 */
function FeedbackDialog({
  profileId,
  planId,
  onClose,
}: {
  profileId: number;
  planId: number;
  onClose: () => void;
}) {
  const [progress, setProgress] = useState("none");
  const [recovery, setRecovery] = useState("good");
  const [domsHours, setDomsHours] = useState(48);
  const [affects, setAffects] = useState(false);
  const [apply, setApply] = useState(true);
  const [result, setResult] = useState<VolumeRecommendation | null>(null);
  const [sending, setSending] = useState(false);

  async function submit() {
    setSending(true);
    try {
      setResult(
        await api.post<VolumeRecommendation>(`/workout/feedback?profile_id=${profileId}`, {
          progress_perception: progress,
          recovery_quality: recovery,
          doms_duration_hours: domsHours,
          affects_performance: affects,
          apply_to_plan: apply,
          plan_id: planId,
        })
      );
    } finally {
      setSending(false);
    }
  }

  const toneByAdjustment: Record<string, string> = {
    decrease: "border-amber-300/25 bg-amber-300/[0.07]",
    increase: "border-lime-400/25 bg-lime-400/[0.07]",
    maintain: "border-white/10 bg-white/[0.04]",
  };

  return (
    <Modal onClose={onClose} className="max-w-lg">
      <ModalHeader
        title="Come sta andando"
        subtitle="Le due risposte insieme dicono cosa cambiare"
        onClose={onClose}
      />

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {result ? (
          <div className="space-y-3.5 px-4 py-4 sm:px-5">
            <div className={`rounded-2xl border p-4 ${toneByAdjustment[result.adjustment]}`}>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/45">
                  {result.adjustment === "decrease"
                    ? "Riduco il volume"
                    : result.adjustment === "increase"
                      ? "Aumento il volume"
                      : "Mantengo il volume"}
                </span>
                <span className="font-mono text-[13px] tabular-nums text-white">
                  {result.current_weekly_sets} → {result.suggested_weekly_sets} serie
                </span>
              </div>
              <p className="text-[13px] leading-relaxed text-white/75">{result.reason}</p>
            </div>

            {result.caveats.map((c, i) => (
              <Notice key={i}>{c}</Notice>
            ))}

            <SourceTags tags={result.knowledge_tags} />
          </div>
        ) : (
          <div className="space-y-3 px-4 py-4 sm:px-5">
            <Field title="Vedi miglioramenti?">
              <OptionGroup
                ariaLabel="Miglioramenti"
                columns="grid-cols-3"
                value={progress}
                onChange={setProgress}
                options={[
                  { value: "none", label: "Nessuno" },
                  { value: "slow", label: "Lenti" },
                  { value: "good", label: "Buoni" },
                ]}
              />
            </Field>

            <Field title="Come recuperi fra le sessioni?">
              <OptionGroup
                ariaLabel="Recupero"
                columns="grid-cols-3"
                value={recovery}
                onChange={setRecovery}
                options={[
                  { value: "poor", label: "Male" },
                  { value: "moderate", label: "Così così" },
                  { value: "good", label: "Bene" },
                ]}
              />
            </Field>

            <Field title="Quanto durano i dolori" hint="Oltre le 72 ore indicano che il recupero non sta bastando.">
              <Stepper
                value={domsHours}
                onChange={setDomsHours}
                min={0}
                max={120}
                step={12}
                label="durata dei dolori"
                format={(h) => `${h} ore`}
              />
            </Field>

            <Toggle checked={affects} onChange={setAffects} label="I dolori mi rovinano le sessioni successive" />
            <Toggle checked={apply} onChange={setApply} label="Applica subito la modifica alla scheda" />
          </div>
        )}
      </div>

      <ModalFooter>
        {result ? (
          <button className="btn-primary flex-1 justify-center" onClick={onClose}>
            {result.applied ? "Scheda aggiornata · Chiudi" : "Chiudi"}
          </button>
        ) : (
          <>
            <button className="btn-ghost flex-1 justify-center" onClick={onClose}>
              Annulla
            </button>
            <button className="btn-primary flex-[1.6] justify-center" disabled={sending} onClick={submit}>
              {sending ? "Valuto…" : "Dimmi cosa cambiare"}
            </button>
          </>
        )}
      </ModalFooter>
    </Modal>
  );
}

/** Il pulsante che prende il posto di "Inizia allenamento" mentre si è in corso. */
function ActiveWorkoutPill({ session, onOpen }: { session: WorkoutSessionLog; onOpen: () => void }) {
  const secondi = useElapsed(session.started_at);
  const giorno = session.day_label ?? "";
  return (
    <motion.button
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 380, damping: 28 }}
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-full border border-lime-400/50 bg-gradient-to-r from-lime-400/[0.18] to-lime-400/[0.06] py-2 pl-4 pr-2 text-left shadow-[0_0_28px_-10px_rgba(174,212,74,0.8)] transition hover:border-lime-400/80 sm:w-auto sm:min-w-[340px]"
      aria-label="Riapri l'allenamento in corso"
    >
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-lime-400 opacity-70" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-lime-400" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] font-semibold text-lime-100">Allenamento in corso</span>
        <span className="block truncate text-[11.5px] text-white/50">
          {giorno.length <= 2 ? `Giorno ${giorno}` : giorno} · tocca per riaprirlo
        </span>
      </span>
      <span className="rounded-full bg-ink-900/70 px-3 py-1.5 font-mono text-[16px] font-semibold tabular-nums text-white">
        {clock(secondi)}
      </span>
    </motion.button>
  );
}

function Sparkle() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 fill-current" aria-hidden>
      <path d="M12 2l2.1 6.4L20.5 10l-6.4 2.1L12 18.5l-2.1-6.4L3.5 10l6.4-1.6L12 2Zm7 12 1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3Z" />
    </svg>
  );
}

/** Tendina sotto un pulsante: si chiude toccando fuori o con Esc. */
function Popover({
  open,
  onClose,
  className = "",
  children,
}: {
  open: boolean;
  onClose: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    // Il contenitore comprende anche il pulsante che la apre: toccarlo di
    // nuovo la chiude con il suo onClick, non qui.
    const fuori = (e: PointerEvent) => {
      const box = ref.current?.parentElement;
      if (box && !box.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("pointerdown", fuori);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", fuori);
      document.removeEventListener("keydown", esc);
    };
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={ref}
          role="menu"
          initial={{ opacity: 0, y: -6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -4, scale: 0.98 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          className={`absolute top-full z-40 mt-2 origin-top rounded-2xl border border-white/[0.12] bg-ink-800 p-1.5 shadow-[0_24px_48px_-16px_rgba(0,0,0,0.9)] ${className}`}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function MenuItem({
  onClick,
  children,
  active = false,
  tone = "default",
  icon,
  disabled = false,
}: {
  onClick: () => void;
  children: React.ReactNode;
  active?: boolean;
  tone?: "default" | "accent" | "danger";
  icon?: string;
  disabled?: boolean;
}) {
  const colore =
    tone === "danger" ? "text-rose-300 hover:bg-rose-400/10" : tone === "accent" ? "text-lime-200 hover:bg-lime-400/10" : "text-white/85 hover:bg-white/[0.06]";
  return (
    <button
      role="menuitem"
      onClick={onClick}
      disabled={disabled}
      className={`flex min-h-[44px] w-full items-center gap-2.5 rounded-xl px-3 text-left text-[14px] font-medium transition disabled:opacity-40 ${colore} ${
        active ? "bg-lime-400/[0.1] text-lime-100" : ""
      }`}
    >
      {active && (
        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 fill-lime-300">
          <path d="m9.5 16.2-4-4L4 13.7l5.5 5.5L20 8.7l-1.5-1.5-9 9Z" />
        </svg>
      )}
      {icon && (
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0 fill-current opacity-80">
          <path d={icon} />
        </svg>
      )}
      {children}
    </button>
  );
}
