"use client";

/**
 * Scheda di allenamento: giornate, esercizi, alternative e feedback.
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
import { useCallback, useEffect, useState } from "react";
import {
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
} from "@/lib/api";
import type { Intent } from "@/lib/coach";
import { Card, CardHeader, Empty, Notice, SourceTags, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import { ExerciseDetailHost } from "@/components/ExerciseDetail";
import { PreferencesDialog } from "@/components/PreferencesDialog";
import { AskCoachButton, DemoAnimation, Modal, ModalHeader } from "@/components/controls";
import { Mascot } from "@/components/Mascot";

export { formatEquipment } from "@/lib/api";

export function Workout({
  profile,
  intent,
  onIntentHandled,
}: {
  profile: Profile;
  intent?: Intent | null;
  onIntentHandled?: () => void;
}) {
  const [plan, setPlan] = useState<WorkoutPlan | null>(null);
  const [meta, setMeta] = useState<Omit<PlanGeneration, "plan"> | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [swapping, setSwapping] = useState<PlanExercise | null>(null);
  const [splitType, setSplitType] = useState(profile.split_type ?? "auto");

  useEffect(() => {
    api
      .get<WorkoutPlan | null>(`/workout/plans/active?profile_id=${profile.id}`)
      .then((p) => {
        // Se nel frattempo è arrivata una scheda appena generata, vince quella.
        setPlan((corrente) => corrente ?? p);
        if (p?.exercises.length) setActiveDay((d) => d ?? p.exercises[0].day_label);
      })
      .finally(() => setLoading(false));
  }, [profile.id]);

  const generate = useCallback(
    async (split: string) => {
      setGenerating(true);
      setError(null);
      try {
        const res = await api.post<PlanGeneration>(
          `/workout/plans/generate?profile_id=${profile.id}&explain=true&split_type=${split}`
        );
        setPlan(res.plan);
        setMeta({
          weekly_sets_per_muscle: res.weekly_sets_per_muscle,
          warnings: res.warnings,
          knowledge_tags: res.knowledge_tags,
        });
        if (res.plan.exercises.length) setActiveDay(res.plan.exercises[0].day_label);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Non sono riuscito a generare la scheda");
      } finally {
        setGenerating(false);
      }
    },
    [profile.id]
  );

  // Il coach ha proposto una scheda e l'utente ha confermato con un clic.
  useEffect(() => {
    if (intent?.section === "scheda" && intent.generateSplit) {
      setSplitType(intent.generateSplit);
      generate(intent.generateSplit);
      onIntentHandled?.();
    }
  }, [intent, generate, onIntentHandled]);

  if (loading) return <Spinner label="Carico la scheda…" />;

  const days = plan ? [...new Set(plan.exercises.map((e) => e.day_label))] : [];
  const dayExercises = plan?.exercises.filter((e) => e.day_label === activeDay) ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Allenamento"
        title={plan ? plan.name : "Nessuna scheda attiva"}
        description={
          plan
            ? `${plan.days_per_week} giorni a settimana · attiva dal ${new Date(
                plan.started_at
              ).toLocaleDateString("it-IT")}`
            : "Genero una scheda sui parametri del tuo profilo, presi dai documenti della knowledge base."
        }
        action={
          <div className="flex flex-wrap gap-2">
            {plan && (
              <button className="btn-ghost" onClick={() => setFeedbackOpen(true)}>
                Come sta andando?
              </button>
            )}
            <button
              className="btn-primary"
              onClick={() => generate(splitType)}
              disabled={generating}
            >
              {generating ? "Genero…" : plan ? "Rigenera" : "Genera scheda"}
            </button>
          </div>
        }
      />

      <Card className="mb-4">
        <div className="flex flex-col gap-4 p-4 lg:flex-row lg:items-end">
          <div className="min-w-0 flex-1">
            <label className="label">Come vuoi dividere gli allenamenti</label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(SPLIT_LABELS).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setSplitType(value)}
                  className={`rounded-xl border px-3 py-2 text-[12.5px] font-medium transition ${
                    splitType === value
                      ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
                      : "border-white/[0.08] bg-white/[0.025] text-white/55 hover:bg-white/[0.06] hover:text-white/85"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11.5px] leading-relaxed text-white/35">
              {SPLIT_HINTS[splitType]}
            </p>
          </div>
          <button className="btn-ghost shrink-0" onClick={() => setPrefsOpen(true)}>
            Esercizi preferiti
          </button>
        </div>
      </Card>

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
            <Empty
              title="Non hai ancora una scheda"
              hint="Serie, ripetizioni, RIR e recuperi vengono calcolati dai parametri delle fonti, non inventati dal modello."
            />
          </Card>
        )
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {days.map((d) => (
                <button
                  key={d}
                  onClick={() => setActiveDay(d)}
                  className={`relative rounded-xl px-4 py-2 text-[13px] font-medium transition ${
                    d === activeDay
                      ? "text-ink-900"
                      : "border border-white/10 bg-white/[0.04] text-white/60 hover:text-white"
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

            <div className="space-y-2.5">
              <AnimatePresence mode="popLayout">
                {dayExercises.map((ex, i) => (
                  <ExerciseRow
                    key={ex.id}
                    item={ex}
                    index={i}
                    onOpenDetail={setDetailId}
                    onSwap={setSwapping}
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
        {feedbackOpen && (
          <FeedbackDialog profileId={profile.id} onClose={() => setFeedbackOpen(false)} />
        )}
        {prefsOpen && (
          <PreferencesDialog profileId={profile.id} onClose={() => setPrefsOpen(false)} />
        )}
        {swapping && (
          <AlternativesDialog
            key={swapping.id}
            item={swapping}
            profileId={profile.id}
            onClose={() => setSwapping(null)}
            onSwapped={setPlan}
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

function thumbnails(ex: PlanExercise["exercise"]) {
  return ex.demo_images?.length ? ex.demo_images : ex.image_url ? [ex.image_url] : [];
}

function ExerciseRow({
  item,
  index,
  onOpenDetail,
  onSwap,
}: {
  item: PlanExercise;
  index: number;
  onOpenDetail: (id: number) => void;
  onSwap: (item: PlanExercise) => void;
}) {
  const ex = item.exercise;
  const nome = exerciseName(ex);
  const schema = `${item.target_sets} × ${item.target_reps_min}-${item.target_reps_max}`;

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
          <p className="truncate text-[14px] font-medium text-white underline-offset-4 group-hover:underline">
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

        <div className="hidden shrink-0 items-center gap-4 sm:flex">
          <Metric value={schema} label="serie × rip." />
          <Metric value={`RIR ${item.target_rir}`} label="intensità" />
          <Metric value={`${item.rest_seconds}s`} label="recupero" />
        </div>

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

      <div className="flex items-center gap-4 px-4 pb-3 sm:hidden">
        <Metric value={schema} label="serie × rip." />
        <Metric value={`RIR ${item.target_rir}`} label="intensità" />
        <Metric value={`${item.rest_seconds}s`} label="recupero" />
      </div>
    </motion.div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <p className="font-mono text-[13px] tabular-nums leading-tight text-white/85">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-white/30">{label}</p>
    </div>
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

  useEffect(() => {
    api
      .get<Alternative[]>(
        `/workout/plan-exercises/${item.id}/alternatives?profile_id=${profileId}&limit=6`
      )
      .then(setAlts)
      .catch((e) => {
        setAlts([]);
        setError(e instanceof Error ? e.message : "Alternative non disponibili");
      });
  }, [item.id, profileId]);

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

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {error && (
          <div className="mb-3">
            <Notice>{error}</Notice>
          </div>
        )}
        {!alts ? (
          <Spinner label="Cerco le alternative…" />
        ) : alts.length === 0 ? (
          !error && <Empty title="Nessuna alternativa disponibile con la tua attrezzatura" />
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
function FeedbackDialog({ profileId, onClose }: { profileId: number; onClose: () => void }) {
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
          <div className="space-y-3.5 p-5">
            <div className={`rounded-xl border p-4 ${toneByAdjustment[result.adjustment]}`}>
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

            <button className="btn-primary w-full" onClick={onClose}>
              {result.applied ? "Scheda aggiornata" : "Chiudi"}
            </button>
          </div>
        ) : (
          <div className="space-y-4 p-5">
            <div>
              <label className="label">Vedi miglioramenti?</label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { v: "none", l: "Nessuno" },
                  { v: "slow", l: "Lenti" },
                  { v: "good", l: "Buoni" },
                ].map((o) => (
                  <Choice key={o.v} active={progress === o.v} onClick={() => setProgress(o.v)} label={o.l} />
                ))}
              </div>
            </div>

            <div>
              <label className="label">Come recuperi fra le sessioni?</label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { v: "poor", l: "Male" },
                  { v: "moderate", l: "Così così" },
                  { v: "good", l: "Bene" },
                ].map((o) => (
                  <Choice key={o.v} active={recovery === o.v} onClick={() => setRecovery(o.v)} label={o.l} />
                ))}
              </div>
            </div>

            <div>
              <label className="label">Quanto durano i dolori — {domsHours}h</label>
              <input
                type="range"
                min={0}
                max={120}
                step={12}
                value={domsHours}
                onChange={(e) => setDomsHours(Number(e.target.value))}
                className="w-full"
              />
              <p className="mt-1 text-[10.5px] text-white/25">
                Oltre le 72 ore indicano che il recupero non sta bastando
              </p>
            </div>

            <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-white/70">
              <input
                type="checkbox"
                className="h-4 w-4 accent-amber-400"
                checked={affects}
                onChange={(e) => setAffects(e.target.checked)}
              />
              I dolori mi rovinano le sessioni successive
            </label>

            <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-white/70">
              <input
                type="checkbox"
                className="h-4 w-4 accent-lime-400"
                checked={apply}
                onChange={(e) => setApply(e.target.checked)}
              />
              Applica subito la modifica alla scheda
            </label>

            <button className="btn-primary w-full" disabled={sending} onClick={submit}>
              {sending ? "Valuto…" : "Dimmi cosa cambiare"}
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function Choice({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl border px-3 py-2.5 text-[12.5px] font-medium transition ${
        active
          ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
          : "border-white/[0.08] bg-white/[0.025] text-white/55 hover:bg-white/[0.06]"
      }`}
    >
      {label}
    </button>
  );
}
