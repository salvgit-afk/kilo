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

import { AnimatePresence, Reorder, motion, useDragControls } from "framer-motion";
import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
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
  type ExerciseSession,
  type PlanExercise,
  type PlanVolume,
  type PlanGeneration,
  type Profile,
  type VolumeRecommendation,
  type WorkoutPlan,
  type WorkoutSessionLog,
  localDate,
  notifyLogged,
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
import {
  CheckIcon,
  LoadHistoryDialog,
  ParamsChips,
  PlanParamsDialog,
  RestRing,
  SessionDialog,
  clock,
  kg,
  useElapsed,
} from "@/components/TrainingLog";
import { useRest } from "@/lib/restTimer";
import {
  ScheduleDialog,
  WEEKDAY_NAMES,
  WeekLine,
  WeekdayPicker,
  defaultWeekdays,
  planDayLabels,
  scheduledToday,
  todayDayLabel,
} from "@/components/WeekSchedule";

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
  // Giorno a cui aggiungere un esercizio.
  const [adding, setAdding] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [volume, setVolume] = useState<PlanVolume | null>(null);
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
    // Si parte dall'allenamento di oggi (mercoledì → giorno B), non sempre dal primo.
    setActiveDay(p ? todayDayLabel(p) : null);
  }, []);

  useEffect(() => {
    api
      .get<WorkoutPlan[]>(`/workout/plans?profile_id=${profile.id}&active_only=true`)
      .then((lista) => {
        // Se nel frattempo è arrivata una scheda appena generata, vince quella.
        // Altrimenti si apre la scheda in uso; senza scelta la più recente,
        // come fa il server per promemoria e pagina Oggi.
        setPlans((correnti) => {
          if (correnti) return correnti;
          selectPlan(lista.find((p) => p.is_current) ?? lista[0] ?? null);
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
            weekly_sets_equivalent: res.weekly_sets_equivalent,
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

  /** Scelta dal menu: diventa la scheda in uso anche per promemoria e Oggi. */
  function choosePlan(p: WorkoutPlan) {
    selectPlan(p);
    setPlans((correnti) => (correnti ?? []).map((x) => ({ ...x, is_current: x.id === p.id })));
    api
      .put<WorkoutPlan>(`/workout/plans/${p.id}/current?profile_id=${profile.id}`)
      // Il banner "oggi è giorno di allenamento" si ricalcola sulla scheda nuova.
      .then(() => notifyLogged())
      .catch(() => undefined);
  }

  async function removePlan(target: WorkoutPlan) {
    await api.del(`/workout/plans/${target.id}?profile_id=${profile.id}`);
    const rimaste = (plans ?? []).filter((p) => p.id !== target.id);
    setPlans(rimaste);
    if (target.id === selectedId) selectPlan(rimaste[0] ?? null);
    setDeleting(null);
  }

  // Volume della scheda ricalcolato dal server a ogni modifica: la scheda
  // cambia oggetto quando si aggiunge, toglie o cambia un esercizio.
  const pianoMostrato = plans?.find((p) => p.id === selectedId) ?? null;
  useEffect(() => {
    if (!pianoMostrato) {
      setVolume(null);
      return;
    }
    let annullato = false;
    api
      .get<PlanVolume>(`/workout/plans/${pianoMostrato.id}/volume?profile_id=${profile.id}`)
      .then((v) => !annullato && setVolume(v))
      .catch(() => !annullato && setVolume(null));
    return () => {
      annullato = true;
    };
  }, [pianoMostrato, profile.id]);

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
  const days = plan ? planDayLabels(plan) : [];
  // Un giorno che la scheda non ha più (rinominato, tolto) non lascia la pagina vuota.
  const giornoMostrato = activeDay && days.includes(activeDay) ? activeDay : plan ? todayDayLabel(plan) : null;
  const dayExercises = plan?.exercises.filter((e) => e.day_label === giornoMostrato) ?? [];
  const giornoDiOggi = plan ? scheduledToday(plan) : null;

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

  async function removeExercise(item: PlanExercise) {
    setRemoveError(null);
    try {
      replacePlan(await api.del<WorkoutPlan>(`/workout/plan-exercises/${item.id}?profile_id=${profile.id}`));
    } catch (e) {
      setRemoveError(e instanceof Error ? e.message : "Non sono riuscito a togliere l'esercizio.");
    }
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
        inline
        action={
          plan && (
            <button
              onClick={() => setFeedbackOpen(true)}
              className="mb-0.5 inline-flex h-9 shrink-0 items-center gap-1 whitespace-nowrap rounded-full border border-iris-400/35 bg-iris-400/[0.12] px-2.5 text-[11.5px] sm:gap-1.5 font-semibold text-iris-100 transition hover:bg-iris-400/20 sm:h-10 sm:px-3.5 sm:text-[12.5px]"
              title="Racconta a Kilo progressi e recupero: ti dice se mantenere, aumentare o ridurre il volume"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current sm:h-4 sm:w-4">
                <path d="M4 4h16v12H8l-4 4V4Z" />
              </svg>
              Come sta andando?
            </button>
          )
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
                          choosePlan(p);
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

              <div className="mt-4">
                <div>
                  <div className="flex gap-1 rounded-2xl border border-white/10 bg-white/[0.03] p-1">
                    {days.map((d) => (
                      <button
                        key={d}
                        onClick={() => setActiveDay(d)}
                        className={`relative h-10 min-w-0 flex-1 rounded-xl px-2 text-[13px] font-semibold transition ${
                          d === giornoMostrato ? "text-ink-900" : "text-white/55 hover:text-white"
                        }`}
                      >
                        {d === giornoMostrato && (
                          <motion.span
                            layoutId="day-pill"
                            className="absolute inset-0 rounded-xl bg-gradient-to-b from-lime-400 to-lime-500"
                            transition={{ type: "spring", stiffness: 380, damping: 30 }}
                          />
                        )}
                        <span className="relative block truncate">{d}</span>
                        {d === giornoDiOggi && (
                          <span
                            className={`absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full ${d === giornoMostrato ? "bg-ink-900/70" : "bg-lime-400"}`}
                            title="L'allenamento di oggi"
                          />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-3">
                <AnimatePresence mode="wait" initial={false}>
                  {activeSession ? (
                    <ActiveWorkoutPill key="in-corso" session={activeSession} onOpen={openActive} />
                  ) : (
                    giornoMostrato &&
                    dayExercises.length > 0 && (
                      <motion.button
                        key="inizia"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        onClick={() => setSessionDay({ plan, day: giornoMostrato, exercises: dayExercises })}
                        className="btn-primary w-full justify-center py-3.5 text-[14.5px]"
                      >
                        <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                          <path d="M8 5v14l11-7L8 5Z" />
                        </svg>
                        Inizia allenamento · {giornoMostrato.length <= 2 ? `giorno ${giornoMostrato}` : giornoMostrato}
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
              {giornoMostrato && (
                <DayExerciseList
                  key={`${plan.id}-${giornoMostrato}`}
                  planId={plan.id}
                  day={giornoMostrato}
                  exercises={dayExercises}
                  profileId={profile.id}
                  onOpenDetail={setDetailId}
                  onSwap={setSwapping}
                  onEdit={setEditingParams}
                  onRemove={removeExercise}
                  onReordered={replacePlan}
                />
              )}
              {removeError && <Notice>{removeError}</Notice>}
              {giornoMostrato && (
                <button
                  onClick={() => setAdding(giornoMostrato)}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl border border-lime-400/40 bg-lime-400/[0.1] py-3.5 text-[14px] font-semibold text-lime-200 shadow-[0_0_24px_-12px_rgba(174,212,74,0.8)] transition hover:border-lime-400/70 hover:bg-lime-400/[0.16] active:scale-[0.99]"
                >
                  <span className="grid h-6 w-6 place-items-center rounded-full bg-lime-400 text-ink-900">
                    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={3}>
                      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
                    </svg>
                  </span>
                  Aggiungi esercizio · {giornoMostrato.length <= 2 ? `giorno ${giornoMostrato}` : giornoMostrato}
                </button>
              )}
            </div>
          </div>

          <div className="space-y-4">
            {meta?.warnings.map((w, i) => <Notice key={i}>{w}</Notice>)}
            {volume?.warnings.map((w, i) => <Notice key={`v${i}`}>{w}</Notice>)}

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

            {volume && Object.keys(volume.weekly_sets_equivalent).length > 0 && (
              <Card delay={0.1}>
                <CardHeader title="Volume settimanale" subtitle="Serie per gruppo, le indirette contano mezza" />
                <div className="space-y-2 px-5 py-4">
                  {Object.entries(volume.weekly_sets_equivalent).map(([m, s]) => (
                    <div key={m} className="flex items-center gap-3">
                      <span className="w-32 shrink-0 truncate text-[12px] text-white/50">
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
                      <span className="w-8 text-right font-mono text-[12px] tabular-nums text-white/70">
                        {s.toLocaleString("it-IT")}
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
            onSaved={(aggiornata) => {
              replacePlan(aggiornata);
              // Con i giorni nuovi oggi può toccare un altro allenamento.
              setActiveDay(todayDayLabel(aggiornata));
            }}
          />
        )}
        {editingParams && (
          <PlanParamsDialog
            key={`params-${editingParams.id}`}
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
        {adding && plan && (
          <AlternativesDialog
            key={`add-${adding}`}
            addTo={{ planId: plan.id, day: adding }}
            profileId={profile.id}
            onClose={() => setAdding(null)}
            onSwapped={replacePlan}
            onOpenDetail={setDetailId}
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

// Tocco prolungato per entrare nel riordino: abbastanza lungo da non
// scattare mentre si scorre la pagina, abbastanza breve da non sembrare rotto.
const LONG_PRESS_MS = 350;
// Un dito che si sposta di più prima del tempo sta scorrendo, non trascinando.
const LONG_PRESS_SLOP_PX = 10;

/**
 * Gli esercizi di un giorno, riordinabili.
 *
 * Per spostarli si entra nel riordino (tocco prolungato su una scheda o
 * "Riordina"): le schede diventano righe basse, così tutto il giorno sta in
 * uno schermo e uno spostamento di tre posti è un gesto corto, non mezza
 * pagina. Ogni riga ha una maniglia che trascina subito, senza attesa.
 * L'ordine si salva a ogni rilascio.
 */
function DayExerciseList({
  planId,
  day,
  exercises,
  profileId,
  onOpenDetail,
  onSwap,
  onEdit,
  onRemove,
  onReordered,
}: {
  planId: number;
  day: string;
  exercises: PlanExercise[];
  profileId: number;
  onOpenDetail: (id: number) => void;
  onSwap: (item: PlanExercise) => void;
  onEdit: (item: PlanExercise) => void;
  onRemove: (item: PlanExercise) => Promise<void>;
  onReordered: (plan: WorkoutPlan) => void;
}) {
  const [ordine, setOrdine] = useState(() => exercises.map((e) => e.id));
  const [errore, setErrore] = useState<string | null>(null);
  const [carichi, setCarichi] = useState<Record<number, ExerciseSession>>({});
  // Esercizio di cui è aperto lo storico, con la serie toccata da modificare.
  const [storico, setStorico] = useState<{ exerciseId: number; setId?: number } | null>(null);
  const [riordino, setRiordino] = useState(false);
  const inizio = useRef<HTMLDivElement>(null);
  const perId = Object.fromEntries(exercises.map((e) => [e.id, e]));

  // Entrando nel riordino la lista sale in cima allo schermo: le righe basse
  // stanno tutte a vista e nessuna finisce sotto la barra di navigazione.
  useEffect(() => {
    if (!riordino || !inizio.current) return;
    const top = inizio.current.getBoundingClientRect().top + window.scrollY - 72;
    window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, [riordino]);
  const chiave = exercises.map((e) => e.id).join(",");
  const esercizi = exercises.map((e) => e.exercise.id).join(",");

  // La scheda cambia da fuori (aggiunta, rimozione, sostituzione): si riparte
  // dal suo ordine.
  useEffect(() => {
    setOrdine(chiave ? chiave.split(",").map(Number) : []);
  }, [chiave]);

  // L'ultima volta di ogni esercizio del giorno, con una richiesta sola.
  const caricaCarichi = useCallback(() => {
    if (!esercizi) return;
    const params = new URLSearchParams({ profile_id: String(profileId) });
    esercizi.split(",").forEach((id) => params.append("exercise_ids", id));
    api
      .get<Record<number, ExerciseSession>>(`/workout/last-performance?${params}`)
      .then(setCarichi)
      .catch(() => setCarichi({}));
  }, [esercizi, profileId]);
  useEffect(caricaCarichi, [caricaCarichi]);

  async function salvaOrdine() {
    const prima = exercises.map((e) => e.id);
    if (ordine.join(",") === prima.join(",")) return;
    setErrore(null);
    try {
      onReordered(
        await api.put<WorkoutPlan>(`/workout/plans/${planId}/order?profile_id=${profileId}`, {
          day_label: day,
          plan_exercise_ids: ordine,
        })
      );
    } catch (e) {
      setOrdine(prima);
      setErrore(e instanceof Error ? e.message : "Non sono riuscito a salvare l'ordine.");
    }
  }

  function entraNelRiordino() {
    setRiordino(true);
    vibra(12);
  }

  return (
    <>
      <div ref={inizio} />
      {ordine.length > 1 && (
        <div className="flex items-center justify-between gap-3 px-1">
          <p className="text-[11.5px] text-white/35">
            {riordino ? "Trascina dalla maniglia ≡" : "Tieni premuto un esercizio per spostarlo"}
          </p>
          <button
            onClick={() => (riordino ? setRiordino(false) : entraNelRiordino())}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] font-semibold transition ${
              riordino
                ? "border-lime-400/60 bg-lime-400 text-ink-900"
                : "border-white/10 bg-white/[0.04] text-white/60 hover:text-white"
            }`}
          >
            {riordino ? (
              "Fatto"
            ) : (
              <>
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.4}>
                  <path d="M7 4v16m0 0-3-3m3 3 3-3M17 20V4m0 0-3 3m3-3 3 3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Riordina
              </>
            )}
          </button>
        </div>
      )}

      {riordino ? (
        <Reorder.Group
          axis="y"
          values={ordine}
          onReorder={(nuovo) => {
            // Un colpetto a ogni scambio di posto, dove il telefono lo permette.
            if (nuovo.join(",") !== ordine.join(",")) vibra(6);
            setOrdine(nuovo);
          }}
          className="space-y-1.5"
        >
          {ordine.map((id, i) =>
            perId[id] ? (
              <CompactRow key={id} item={perId[id]} index={i} onDragEnd={salvaOrdine} />
            ) : null
          )}
        </Reorder.Group>
      ) : (
        <div className="space-y-2.5">
          {ordine.map((id, i) =>
            perId[id] ? (
              <ExerciseRow
                key={id}
                item={perId[id]}
                index={i}
                last={carichi[perId[id].exercise.id]}
                onOpenDetail={onOpenDetail}
                onSwap={onSwap}
                onEdit={onEdit}
                onRemove={ordine.length > 1 ? onRemove : undefined}
                onOpenLoads={(setId) => setStorico({ exerciseId: perId[id].exercise.id, setId })}
                onLongPress={ordine.length > 1 ? entraNelRiordino : undefined}
              />
            ) : null
          )}
        </div>
      )}
      {errore && <Notice>{errore}</Notice>}
      <AnimatePresence>
        {storico !== null && (
          <LoadHistoryDialog
            key={`carichi-${storico.exerciseId}`}
            profileId={profileId}
            exerciseId={storico.exerciseId}
            editSetId={storico.setId}
            planId={planId}
            dayLabel={day}
            onClose={() => setStorico(null)}
            onChanged={caricaCarichi}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function vibra(ms: number) {
  try {
    navigator.vibrate?.(ms);
  } catch {
    /* vibrazione non supportata (iPhone) */
  }
}

/** La riga del riordino: bassa, con la maniglia che trascina subito. */
function CompactRow({ item, index, onDragEnd }: { item: PlanExercise; index: number; onDragEnd: () => void }) {
  const controls = useDragControls();
  const [trascino, setTrascino] = useState(false);
  const ex = item.exercise;

  // Mentre si trascina la pagina non deve scorrere sotto il dito (iOS).
  useEffect(() => {
    if (!trascino) return;
    const blocca = (e: TouchEvent) => e.preventDefault();
    document.addEventListener("touchmove", blocca, { passive: false });
    return () => document.removeEventListener("touchmove", blocca);
  }, [trascino]);

  return (
    <Reorder.Item
      value={item.id}
      dragListener={false}
      dragControls={controls}
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{
        opacity: 1,
        scale: trascino ? 1.035 : 1,
        boxShadow: trascino
          ? "0 18px 40px -12px rgba(0,0,0,0.85), 0 0 26px -10px rgba(174,212,74,0.85)"
          : "0 0 0 0 rgba(0,0,0,0)",
      }}
      // Gli altri si spostano con una molla morbida, non a scatti.
      transition={{ type: "spring", stiffness: 520, damping: 38, mass: 0.8 }}
      dragElastic={0.08}
      dragTransition={{ bounceStiffness: 520, bounceDamping: 36 }}
      onDragStart={() => setTrascino(true)}
      onDragEnd={() => {
        setTrascino(false);
        onDragEnd();
      }}
      className={`relative flex select-none items-center gap-3 rounded-2xl border py-1.5 pl-1.5 pr-3 [-webkit-touch-callout:none] ${
        trascino ? "z-10 border-lime-400/60 bg-ink-800" : "border-white/[0.08] bg-ink-800/80"
      }`}
    >
      <span
        onPointerDown={(e) => {
          e.preventDefault();
          setTrascino(true);
          vibra(10);
          controls.start(e);
        }}
        onPointerUp={() => setTrascino(false)}
        aria-label={`Trascina ${exerciseName(ex)}`}
        role="button"
        className={`grid h-10 w-10 shrink-0 cursor-grab touch-none place-items-center rounded-xl transition-colors active:cursor-grabbing ${
          trascino ? "bg-lime-400/15 text-lime-200" : "text-white/40 hover:text-white/70"
        }`}
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
          <circle cx="9" cy="6" r="1.6" />
          <circle cx="15" cy="6" r="1.6" />
          <circle cx="9" cy="12" r="1.6" />
          <circle cx="15" cy="12" r="1.6" />
          <circle cx="9" cy="18" r="1.6" />
          <circle cx="15" cy="18" r="1.6" />
        </svg>
      </span>
      <span className="grid h-6 min-w-6 shrink-0 place-items-center rounded-md bg-white/[0.06] px-1 font-mono text-[11px] text-white/60">
        {index + 1}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold text-white">{exerciseName(ex)}</span>
        <span className="block truncate text-[11.5px] text-white/40">
          {MUSCLE_LABELS[ex.primary_muscle ?? ""] ?? ex.primary_muscle} · {item.target_sets} × {item.target_reps_min}-
          {item.target_reps_max}
        </span>
      </span>
    </Reorder.Item>
  );
}

function ExerciseRow({
  item,
  index,
  last,
  onOpenDetail,
  onSwap,
  onEdit,
  onRemove,
  onOpenLoads,
  onLongPress,
}: {
  item: PlanExercise;
  index: number;
  /** L'ultima volta che è stato fatto, con le serie segnate. */
  last?: ExerciseSession;
  onOpenDetail: (id: number) => void;
  onSwap: (item: PlanExercise) => void;
  onEdit: (item: PlanExercise) => void;
  /** Assente sull'unico esercizio del giorno: senza, il giorno sparirebbe. */
  onRemove?: (item: PlanExercise) => Promise<void>;
  /** Con l'id di una serie, la apre già in modifica. */
  onOpenLoads: (setId?: number) => void;
  /** Tocco prolungato: si entra nel riordino. Assente se l'esercizio è uno solo. */
  onLongPress?: () => void;
}) {
  const ex = item.exercise;
  const nome = exerciseName(ex);
  const [premuto, setPremuto] = useState(false);
  const [carichiAperti, setCarichiAperti] = useState(false);
  const pressione = useRef<{ timer: number; x: number; y: number } | null>(null);
  // Il rilascio dopo il tocco prolungato non deve valere come tocco su un pulsante.
  const appenaPremuto = useRef(false);

  function annullaPressione() {
    if (pressione.current) window.clearTimeout(pressione.current.timer);
    pressione.current = null;
    setPremuto(false);
  }
  // Doppio tocco: il primo chiede conferma, come nel diario.
  const [confirm, setConfirm] = useState(false);
  const [removing, setRemoving] = useState(false);
  useEffect(() => {
    if (!confirm) return;
    const t = setTimeout(() => setConfirm(false), 3500);
    return () => clearTimeout(t);
  }, [confirm]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      // Mentre si tiene premuto la scheda si abbassa appena: si capisce che
      // sta per succedere qualcosa, prima che succeda.
      animate={{ opacity: 1, y: 0, scale: premuto ? 0.98 : 1 }}
      transition={{ delay: premuto ? 0 : index * 0.035, scale: { duration: LONG_PRESS_MS / 1000 } }}
      onPointerDown={(e: ReactPointerEvent) => {
        if (!onLongPress) return;
        annullaPressione();
        setPremuto(true);
        pressione.current = {
          x: e.clientX,
          y: e.clientY,
          timer: window.setTimeout(() => {
            pressione.current = null;
            appenaPremuto.current = true;
            setPremuto(false);
            onLongPress();
            window.setTimeout(() => (appenaPremuto.current = false), 400);
          }, LONG_PRESS_MS),
        };
      }}
      onPointerMove={(e: ReactPointerEvent) => {
        const p = pressione.current;
        if (p && Math.hypot(e.clientX - p.x, e.clientY - p.y) > LONG_PRESS_SLOP_PX) annullaPressione();
      }}
      onPointerUp={annullaPressione}
      onPointerCancel={annullaPressione}
      onPointerLeave={annullaPressione}
      onClickCapture={(e: ReactMouseEvent) => {
        if (appenaPremuto.current) {
          e.preventDefault();
          e.stopPropagation();
          appenaPremuto.current = false;
        }
      }}
      onContextMenu={(e: ReactMouseEvent) => e.preventDefault()}
      className="glass sheen glass-hover relative touch-manipulation select-none overflow-hidden [-webkit-touch-callout:none]"
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
          title="Non ti piace? Scegli un'alternativa, anche per un altro muscolo"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
            <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7Zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4Z" />
          </svg>
          <span className="hidden md:inline">Cambia</span>
        </button>
        {onRemove && (
          <button
            onClick={async () => {
              if (!confirm) return setConfirm(true);
              setRemoving(true);
              await onRemove(item);
              setRemoving(false);
              setConfirm(false);
            }}
            disabled={removing}
            aria-label={confirm ? `Conferma: togli ${nome}` : `Togli ${nome} dalla scheda`}
            className={`inline-flex h-[34px] shrink-0 items-center justify-center gap-1.5 rounded-xl border px-2.5 text-[12px] font-semibold transition ${
              confirm
                ? "border-rose-400/60 bg-rose-500/85 text-white"
                : "border-white/10 bg-white/[0.04] text-white/45 hover:border-rose-400/40 hover:text-rose-200"
            }`}
          >
            {confirm ? (
              removing ? "…" : "Togli"
            ) : (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
        )}
      </div>

      <div className="px-3.5 pb-3">
        <ParamsChips value={item} onEdit={() => onEdit(item)} />
      </div>

      {/* Carichi dell'ultima volta: a comparsa, modificabili dallo storico. */}
      <div className="border-t border-white/[0.05]">
        <button
          onClick={() => (last ? setCarichiAperti(!carichiAperti) : onOpenLoads())}
          aria-expanded={last ? carichiAperti : undefined}
          className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-[12px] transition hover:bg-white/[0.03]"
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0 text-iris-300" fill="none" stroke="currentColor" strokeWidth={2.2}>
            <path d="M4 19V5m0 14h16M8 15l3-4 3 2 5-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {last ? (
            <>
              <span className="shrink-0 text-white/45">
                Carichi · {new Date(last.date).toLocaleDateString("it-IT", { day: "numeric", month: "short" })}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono tabular-nums text-white/75">
                {last.sets.map((s) => `${kg(s.weight_kg)}×${s.reps}`).join(" · ")}
              </span>
              <svg
                viewBox="0 0 24 24"
                className={`h-3.5 w-3.5 shrink-0 text-white/35 transition-transform ${carichiAperti ? "rotate-180" : ""}`}
                fill="none"
                stroke="currentColor"
                strokeWidth={2.4}
              >
                <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </>
          ) : (
            <span className="text-white/35">Nessun carico ancora: tocca per segnarli, o avvia l&apos;allenamento</span>
          )}
        </button>
        <AnimatePresence initial={false}>
          {last && carichiAperti && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="px-3.5 pb-3">
                <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-1.5">
                  {last.sets.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => onOpenLoads(s.id)}
                      aria-label={`Modifica la serie ${s.set_number}`}
                      className="rounded-xl border border-transparent bg-white/[0.05] px-2.5 py-1.5 text-left transition hover:border-lime-400/40"
                    >
                      <p className="flex items-center justify-between text-[10.5px] text-white/40">
                        serie {s.set_number}
                        <svg viewBox="0 0 24 24" className="h-3 w-3 text-white/30" fill="none" stroke="currentColor" strokeWidth={2.2}>
                          <path d="M4 20h4L19 9l-4-4L4 16v4Z" strokeLinejoin="round" />
                        </svg>
                      </p>
                      <p className="font-mono text-[13.5px] font-semibold tabular-nums text-white/90">
                        {kg(s.weight_kg)}
                        <span className="text-[10.5px] font-normal text-white/40"> kg</span> × {s.reps}
                      </p>
                      {s.rir !== null && s.rir !== undefined && (
                        <p className="text-[10.5px] text-white/35">RIR {s.rir}</p>
                      )}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => onOpenLoads()}
                  className="mt-2 inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-lime-300"
                >
                  Modifica i carichi e vedi lo storico →
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

// Gruppi fra cui scegliere quando si cambia proprio il muscolo: quelli che
// la scheda allena, senza i gruppi minori. Gli adduttori il generatore non li
// programma, ma si possono aggiungere a mano.
const GRUPPI_SOSTITUZIONE = [
  "Chest", "Lats", "Shoulders", "Trapezius", "Biceps", "Triceps",
  "Quads", "Hamstrings", "Glutes", "Adductors", "Calves", "Abs",
];

// Esercizi caricati per volta: "Mostra altri" ne aggiunge altrettanti. Un
// gruppo arriva a 150 esercizi; con un elenco fisso di 24 la maggior parte non
// si vedeva mai.
const PAGINA_ALTERNATIVE = 24;

/**
 * Cambio o aggiunta di un esercizio: le alternative come schede con
 * l'animazione, il tipo di esercizio e il primo spunto di focus muscolare —
 * abbastanza per capire di cosa si tratta prima di sceglierlo.
 *
 * Con `item` sostituisce quell'esercizio; con `addTo` ne aggiunge uno nuovo
 * in fondo al giorno.
 */
function AlternativesDialog({
  item,
  addTo,
  profileId,
  onClose,
  onSwapped,
  onOpenDetail,
}: {
  item?: PlanExercise;
  addTo?: { planId: number; day: string };
  profileId: number;
  onClose: () => void;
  onSwapped: (plan: WorkoutPlan) => void;
  onOpenDetail: (id: number) => void;
}) {
  const [alts, setAlts] = useState<Alternative[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [quanti, setQuanti] = useState(PAGINA_ALTERNATIVE);
  const originale = item?.exercise.primary_muscle ?? "";
  // Il gruppo da cui pescare: di base lo stesso, ma si può cambiare proprio
  // il muscolo allenato da questo esercizio.
  const [muscle, setMuscle] = useState(originale || GRUPPI_SOSTITUZIONE[0]);
  const cambiaMuscolo = !!item && muscle !== originale;

  useEffect(() => {
    // "Mostra altri" tiene a vista quelli già caricati; una nuova ricerca o
    // un altro gruppo ripartono dallo spinner.
    if (quanti === PAGINA_ALTERNATIVE) setAlts(null);
    setError(null);
    const q = query.trim() ? `&q=${encodeURIComponent(query.trim())}` : "";
    const m = cambiaMuscolo ? `&muscle=${encodeURIComponent(muscle)}` : "";
    // Durante la ricerca si aspetta che l'utente smetta di scrivere.
    const timer = setTimeout(
      () => {
        api
          .get<Alternative[]>(
            addTo
              ? `/workout/plans/${addTo.planId}/candidates?profile_id=${profileId}&limit=${quanti}&muscle=${encodeURIComponent(muscle)}${q}`
              : `/workout/plan-exercises/${item!.id}/alternatives?profile_id=${profileId}&limit=${quanti}${q}${m}`
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
  }, [item, addTo, profileId, query, muscle, cambiaMuscolo, quanti]);

  async function swap(exerciseId: number) {
    setBusy(exerciseId);
    setError(null);
    try {
      if (addTo) {
        onSwapped(
          await api.post<WorkoutPlan>(`/workout/plans/${addTo.planId}/exercises?profile_id=${profileId}`, {
            exercise_id: exerciseId,
            day_label: addTo.day,
          })
        );
        onClose();
        return;
      }
      const updated = await api.post<WorkoutPlan>(
        `/workout/plan-exercises/${item!.id}/swap?profile_id=${profileId}`,
        // Cambiando muscolo l'esercizio tolto non è sgradito: si vuole allenare altro.
        { replacement_exercise_id: exerciseId, mark_old_as_disliked: !cambiaMuscolo, allow_muscle_change: cambiaMuscolo }
      );
      onSwapped(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sostituzione non riuscita");
    } finally {
      setBusy(null);
    }
  }

  const attuale = item?.exercise;
  const nomeMuscolo = (m: string) => MUSCLE_LABELS[m] ?? m;
  const parametri = item ? `${item.target_sets} × ${item.target_reps_min}-${item.target_reps_max} a RIR ${item.target_rir}` : "";
  const giorno = addTo ? (addTo.day.length <= 2 ? `giorno ${addTo.day}` : addTo.day) : "";

  return (
    <Modal onClose={onClose} className="max-w-3xl">
      <ModalHeader
        eyebrow={`${addTo ? "Aggiungi esercizio" : "Cambia esercizio"} · ${nomeMuscolo(muscle)}`}
        title={attuale ? `Al posto di «${exerciseName(attuale)}»` : `Nuovo esercizio per ${giorno}`}
        subtitle={
          addTo
            ? "Entra in fondo al giorno con 3 serie e ripetizioni, RIR e recupero delle fonti per quel tipo di esercizio: poi li cambi come gli altri."
            : cambiaMuscolo
            ? `Cambi gruppo: da ${nomeMuscolo(originale).toLowerCase()} a ${nomeMuscolo(muscle).toLowerCase()}. Restano ${parametri}; le serie settimanali si spostano sul nuovo muscolo.`
            : `Stesso muscolo principale: restano ${parametri}. Scegli quello in cui senti meglio il muscolo e che esegui volentieri.`
        }
        onClose={onClose}
      />

      <div className="shrink-0 space-y-2.5 border-b border-white/[0.06] px-4 py-3">
        <input
          className="input py-2 text-[13px]"
          placeholder={addTo ? "Cerca un esercizio — es. cavi, manubri, macchina, hammer" : "Cerca fra le alternative — es. cavi, manubri, macchina, hammer"}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setQuanti(PAGINA_ALTERNATIVE);
          }}
        />
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none]" role="radiogroup" aria-label="Gruppo muscolare">
          {GRUPPI_SOSTITUZIONE.map((m) => {
            const scelto = m === muscle;
            return (
              <button
                key={m}
                role="radio"
                aria-checked={scelto}
                onClick={() => {
                  setMuscle(m);
                  setQuanti(PAGINA_ALTERNATIVE);
                }}
                // Niente layoutId qui: un'animazione condivisa dentro un
                // pannello che si chiude ne blocca l'uscita.
                className={`relative shrink-0 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors duration-200 ${
                  scelto
                    ? "border-lime-400/60 bg-gradient-to-b from-lime-400 to-lime-500 text-ink-900"
                    : "border-white/10 text-white/60 hover:border-white/25 hover:text-white"
                }`}
              >
                <span className="relative">
                  {nomeMuscolo(m)}
                  {item && m === originale && !scelto && <span className="ml-1 text-white/35">· attuale</span>}
                </span>
              </button>
            );
          })}
        </div>
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
                  // Solo le prime entrano una dopo l'altra: con "Mostra altri"
                  // l'ultima comparirebbe dopo secondi.
                  transition={{ delay: (i % PAGINA_ALTERNATIVE) < 8 ? (i % PAGINA_ALTERNATIVE) * 0.05 : 0.4 }}
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
                        {busy === ex.id ? (addTo ? "Aggiungo…" : "Cambio…") : addTo ? "Aggiungi" : "Scegli questo"}
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
        {/* Il server ne ha restituiti quanti chiesti: probabilmente ce ne sono altri. */}
        {alts && alts.length >= quanti && (
          <button
            onClick={() => setQuanti((n) => n + PAGINA_ALTERNATIVE)}
            className="mt-4 w-full rounded-2xl border border-white/10 bg-white/[0.03] py-3 text-[13px] font-semibold text-white/70 transition hover:border-lime-400/40 hover:text-lime-200"
          >
            Mostra altri esercizi
          </button>
        )}
      </div>

      <p className="shrink-0 border-t border-white/[0.06] px-5 py-3 text-[11.5px] leading-snug text-white/35">
        {addTo
          ? "Quello che aggiungi diventa un preferito: le prossime schede lo propongono per primo."
          : cambiaMuscolo
          ? "L'esercizio tolto resta disponibile per le prossime schede; quello che scegli diventa un preferito."
          : "L'esercizio sostituito non ti verrà più proposto nelle prossime schede; quello che scegli diventa un preferito."}
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

/**
 * Il pulsante che prende il posto di "Inizia allenamento" mentre si è in corso.
 * Con il pannello ridotto porta anche il recupero: anello e secondi a sinistra,
 * durata della sessione sempre a destra; a recupero finito diventa lime.
 */
function ActiveWorkoutPill({ session, onOpen }: { session: WorkoutSessionLog; onOpen: () => void }) {
  const secondi = useElapsed(session.started_at);
  const { rest, remaining } = useRest(session.id);
  const giorno = session.day_label ?? "";
  const nome = giorno.length <= 2 ? `Giorno ${giorno}` : giorno;
  const finito = rest?.done ?? false;
  return (
    <motion.button
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 380, damping: 28 }}
      onClick={onOpen}
      className={`flex w-full items-center gap-3 rounded-full border py-2 pr-2 text-left transition-colors duration-300 sm:w-auto sm:min-w-[340px] ${
        rest ? "pl-2" : "pl-4"
      } ${
        finito
          ? "border-lime-300 bg-lime-400 text-ink-900 shadow-[0_0_34px_-6px_rgba(174,212,74,0.9)]"
          : "border-lime-400/50 bg-gradient-to-r from-lime-400/[0.18] to-lime-400/[0.06] shadow-[0_0_28px_-10px_rgba(174,212,74,0.8)] hover:border-lime-400/80"
      }`}
      aria-label="Riapri l'allenamento in corso"
    >
      {finito ? (
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink-900/15">
          <CheckIcon />
        </span>
      ) : rest ? (
        <RestRing fraction={remaining / rest.total} size={40} stroke={3.5}>
          <span className="font-mono text-[11px] font-semibold tabular-nums text-white">{clock(remaining)}</span>
        </RestRing>
      ) : (
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-lime-400 opacity-70" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-lime-400" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        {finito && rest ? (
          <>
            <span className="block truncate text-[13.5px] font-semibold">{rest.next.replace(/^Poi:? ?/, "Tocca a te: ")}</span>
            <span className="block truncate text-[11.5px] text-ink-900/70">{rest.detail}</span>
          </>
        ) : (
          <>
            <span className="block truncate text-[13.5px] font-semibold text-lime-100">
              {rest ? `Recupero · ${rest.next.replace(/^Poi:? (la )?/, "")}` : "Allenamento in corso"}
            </span>
            <span className="block truncate text-[11.5px] text-white/50">{nome} · tocca per riaprirlo</span>
          </>
        )}
      </span>
      <span
        className={`shrink-0 rounded-full px-3 py-1.5 font-mono text-[16px] font-semibold tabular-nums ${
          finito ? "bg-ink-900 text-white" : "bg-ink-900/70 text-white"
        }`}
      >
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
