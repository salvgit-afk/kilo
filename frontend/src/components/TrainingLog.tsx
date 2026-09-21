"use client";

/**
 * Allenamento in corso, storico dei carichi e parametri della scheda.
 *
 * - **Parametri** (serie, ripetizioni, RIR, recupero): si cambiano sia nella
 *   scheda sia durante l'allenamento. Durante l'allenamento valgono per la
 *   sessione, e con "Salva anche nella scheda" diventano il nuovo modello.
 * `exercises` va passato stabile (una copia fatta all'apertura): la sessione
 * si carica una volta sola, e un nuovo array a ogni render della pagina la
 * ricaricherebbe azzerando le serie in corso.
 *
 * - **Sessione**: ogni serie si salva appena la si conferma, non a fine
 *   allenamento: se il telefono si blocca a metà non si perde niente, e
 *   riaprendo si ritrovano le serie già segnate. I campi partono dalla serie
 *   precedente o da quella dell'ultima volta; dopo ogni serie parte il
 *   recupero.
 * - **Storico**: ogni sessione ha le sue serie. Correggere un carico cambia
 *   solo quella serie, così la progressione resta leggibile.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  exerciseName,
  type ExerciseHistory,
  type ExerciseSession,
  type PlanExercise,
  type PlanExerciseParams,
  type SessionSet,
  type WorkoutPlan,
  type WorkoutSessionLog,
} from "@/lib/api";
import { Modal, ModalHeader, NumberField } from "@/components/controls";
import { Empty, Notice, Spinner } from "@/components/ui";

// --- Formati ----------------------------------------------------------------------

export function kg(n: number): string {
  return n.toLocaleString("it-IT", { maximumFractionDigits: 2 });
}

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

function restLabel(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}

export function setsSummary(sets: SessionSet[]): string {
  return sets.map((s) => `${kg(s.weight_kg)}×${s.reps}`).join(" · ");
}

function paramsOf(item: PlanExercise): PlanExerciseParams {
  return {
    target_sets: item.target_sets,
    target_reps_min: item.target_reps_min,
    target_reps_max: item.target_reps_max,
    target_rir: item.target_rir,
    rest_seconds: item.rest_seconds,
  };
}

function sameParams(a: PlanExerciseParams, b: PlanExerciseParams): boolean {
  return (Object.keys(a) as (keyof PlanExerciseParams)[]).every((k) => a[k] === b[k]);
}

// --- Parametri ----------------------------------------------------------------------

export function ParamsEditor({
  value,
  onChange,
}: {
  value: PlanExerciseParams;
  onChange: (v: PlanExerciseParams) => void;
}) {
  const set = (k: keyof PlanExerciseParams) => (n: number | null) =>
    n !== null && onChange({ ...value, [k]: n });
  const campi: [keyof PlanExerciseParams, string, number, number, number, string?][] = [
    ["target_sets", "Serie", 1, 10, 1],
    ["target_reps_min", "Rip. min", 1, 50, 1],
    ["target_reps_max", "Rip. max", 1, 50, 1],
    ["target_rir", "RIR", 0, 5, 1],
    ["rest_seconds", "Recupero", 15, 600, 15, "s"],
  ];
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 sm:grid-cols-5">
      {campi.map(([k, label, min, max, step, suffix]) => (
        <label key={k} className={k === "rest_seconds" ? "col-span-2 sm:col-span-1" : ""}>
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-white/40">{label}</span>
          <NumberField
            value={value[k]}
            onChange={set(k)}
            min={min}
            max={max}
            step={step}
            suffix={suffix}
            size="sm"
            ariaLabel={label}
          />
        </label>
      ))}
    </div>
  );
}

/** Parametri di un esercizio nella scheda (fuori dall'allenamento). */
export function PlanParamsDialog({
  item,
  profileId,
  onClose,
  onSaved,
}: {
  item: PlanExercise;
  profileId: number;
  onClose: () => void;
  onSaved: (plan: WorkoutPlan) => void;
}) {
  const [value, setValue] = useState(paramsOf(item));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invalid = value.target_reps_min > value.target_reps_max;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onSaved(await api.patch<WorkoutPlan>(`/workout/plan-exercises/${item.id}?profile_id=${profileId}`, value));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito a salvare.");
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose} className="max-w-lg">
      <ModalHeader
        eyebrow="Modifica scheda"
        title={exerciseName(item.exercise)}
        subtitle="I valori iniziali vengono dalle fonti; da qui in poi sono una tua scelta."
        onClose={onClose}
      />
      <div className="space-y-4 overflow-y-auto p-5">
        <ParamsEditor value={value} onChange={setValue} />
        {invalid && <Notice>Le ripetizioni minime non possono superare le massime.</Notice>}
        {error && <Notice>{error}</Notice>}
        <div className="flex gap-2">
          <button className="btn-primary flex-1" onClick={save} disabled={saving || invalid}>
            {saving ? "Salvo…" : "Salva nella scheda"}
          </button>
          <button className="btn-ghost" onClick={onClose}>
            Annulla
          </button>
        </div>
      </div>
    </Modal>
  );
}

// --- Allenamento in corso -----------------------------------------------------------

type Row = {
  key: string;
  setId: number | null;
  kg: number | null;
  reps: number | null;
  rir: number | null;
  // Valori salvati: se diversi da quelli nei campi, la serie va risalvata.
  saved: { kg: number; reps: number; rir: number | null } | null;
  busy?: boolean;
  confirmDelete?: boolean;
};

let rowSeq = 0;
const newKey = () => `r${++rowSeq}`;

function rowsFor(
  item: PlanExercise,
  target: PlanExerciseParams,
  logged: SessionSet[],
  last: ExerciseSession | undefined
): Row[] {
  const rows: Row[] = logged.map((s) => ({
    key: newKey(),
    setId: s.id,
    kg: s.weight_kg,
    reps: s.reps,
    rir: s.rir,
    saved: { kg: s.weight_kg, reps: s.reps, rir: s.rir },
  }));
  while (rows.length < target.target_sets) rows.push(prefill(rows, rows.length, target, last));
  return rows;
}

/** La serie successiva parte dalla precedente, o da quella dell'ultima volta. */
function prefill(rows: Row[], index: number, target: PlanExerciseParams, last?: ExerciseSession): Row {
  const prima = rows[index - 1];
  const volta = last?.sets[index] ?? last?.sets[last.sets.length - 1];
  return {
    key: newKey(),
    setId: null,
    kg: prima?.kg ?? volta?.weight_kg ?? null,
    reps: prima?.reps ?? volta?.reps ?? target.target_reps_max,
    rir: prima?.rir ?? target.target_rir,
    saved: null,
  };
}

export function SessionDialog({
  profileId,
  plan,
  dayLabel,
  exercises,
  onClose,
  onPlanUpdated,
}: {
  profileId: number;
  plan: WorkoutPlan;
  dayLabel: string;
  exercises: PlanExercise[];
  onClose: () => void;
  onPlanUpdated: (plan: WorkoutPlan) => void;
}) {
  const [session, setSession] = useState<WorkoutSessionLog | null>(null);
  const [last, setLast] = useState<Record<number, ExerciseSession>>({});
  const [targets, setTargets] = useState<Record<number, PlanExerciseParams>>(() =>
    Object.fromEntries(exercises.map((e) => [e.id, paramsOf(e)]))
  );
  // I parametri della scheda: dopo "Salva anche nella scheda" diventano i nuovi.
  const [base, setBase] = useState<Record<number, PlanExerciseParams>>(() =>
    Object.fromEntries(exercises.map((e) => [e.id, paramsOf(e)]))
  );
  const [rows, setRows] = useState<Record<number, Row[]> | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [history, setHistory] = useState<PlanExercise | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rest, setRest] = useState<{ endsAt: number; total: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  const creating = useRef<Promise<WorkoutSessionLog> | null>(null);
  const sessionRef = useRef<WorkoutSessionLog | null>(null);
  sessionRef.current = session;

  // Sessione di oggi (se già iniziata) e ultima volta di ogni esercizio.
  useEffect(() => {
    let annullato = false;
    (async () => {
      try {
        const corrente = await api.get<WorkoutSessionLog | null>(
          `/workout/sessions/current?profile_id=${profileId}&day_label=${encodeURIComponent(dayLabel)}&plan_id=${plan.id}`
        );
        const params = new URLSearchParams({ profile_id: String(profileId) });
        exercises.forEach((e) => params.append("exercise_ids", String(e.exercise.id)));
        if (corrente) params.set("exclude_session_id", String(corrente.id));
        const ultime = await api.get<Record<number, ExerciseSession>>(`/workout/last-performance?${params}`);
        if (annullato) return;
        setSession(corrente);
        setLast(ultime);
        setRows(
          Object.fromEntries(
            exercises.map((e) => [
              e.id,
              rowsFor(
                e,
                paramsOf(e),
                (corrente?.sets ?? [])
                  .filter((s) => s.exercise_id === e.exercise.id)
                  .sort((a, b) => a.set_number - b.set_number),
                ultime[e.exercise.id]
              ),
            ])
          )
        );
      } catch (e) {
        if (!annullato) setError(e instanceof Error ? e.message : "Non riesco a caricare la sessione.");
      }
    })();
    return () => {
      annullato = true;
    };
  }, [profileId, plan.id, dayLabel, exercises]);

  // Il timer del recupero.
  useEffect(() => {
    if (!rest) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [rest]);
  const remaining = rest ? Math.max(0, Math.ceil((rest.endsAt - now) / 1000)) : 0;
  useEffect(() => {
    if (rest && remaining === 0) {
      try {
        navigator.vibrate?.([120, 60, 120]);
      } catch {
        /* vibrazione non supportata */
      }
      setRest(null);
    }
  }, [rest, remaining]);

  const ensureSession = useCallback(async () => {
    if (sessionRef.current) return sessionRef.current;
    if (!creating.current) {
      creating.current = api.post<WorkoutSessionLog>(`/workout/sessions?profile_id=${profileId}`, {
        day_label: dayLabel,
        workout_plan_id: plan.id,
      });
    }
    const s = await creating.current;
    setSession(s);
    return s;
  }, [profileId, dayLabel, plan.id]);

  function patchRow(itemId: number, key: string, change: Partial<Row>) {
    setRows((prev) =>
      prev ? { ...prev, [itemId]: prev[itemId].map((r) => (r.key === key ? { ...r, ...change } : r)) } : prev
    );
  }

  async function saveRow(item: PlanExercise, row: Row, index: number) {
    if (row.kg === null || row.reps === null || row.reps < 1) return;
    patchRow(item.id, row.key, { busy: true });
    setError(null);
    try {
      const corpo = { weight_kg: row.kg, reps: row.reps, rir: row.rir };
      let id = row.setId;
      if (id) {
        await api.patch(`/workout/sets/${id}`, corpo);
      } else {
        const s = await ensureSession();
        const creata = await api.post<SessionSet>(`/workout/sessions/${s.id}/sets`, {
          ...corpo,
          exercise_id: item.exercise.id,
          set_number: index + 1,
        });
        id = creata.id;
        const recupero = targets[item.id].rest_seconds;
        setRest({ endsAt: Date.now() + recupero * 1000, total: recupero });
      }
      patchRow(item.id, row.key, {
        setId: id,
        busy: false,
        saved: { kg: row.kg, reps: row.reps, rir: row.rir },
      });
    } catch (e) {
      patchRow(item.id, row.key, { busy: false });
      setError(e instanceof Error ? `Serie non salvata: ${e.message}` : "Serie non salvata.");
    }
  }

  async function deleteRow(item: PlanExercise, row: Row) {
    if (!row.confirmDelete) {
      patchRow(item.id, row.key, { confirmDelete: true });
      setTimeout(() => patchRow(item.id, row.key, { confirmDelete: false }), 3000);
      return;
    }
    if (row.setId) {
      patchRow(item.id, row.key, { busy: true });
      try {
        await api.del(`/workout/sets/${row.setId}`);
      } catch {
        patchRow(item.id, row.key, { busy: false });
        return;
      }
    }
    setRows((prev) => (prev ? { ...prev, [item.id]: prev[item.id].filter((r) => r.key !== row.key) } : prev));
  }

  function addRow(item: PlanExercise) {
    setRows((prev) =>
      prev
        ? {
            ...prev,
            [item.id]: [...prev[item.id], prefill(prev[item.id], prev[item.id].length, targets[item.id], last[item.exercise.id])],
          }
        : prev
    );
  }

  function changeTargets(item: PlanExercise, v: PlanExerciseParams) {
    setTargets((prev) => ({ ...prev, [item.id]: v }));
    // Più serie: righe in più già precompilate. Meno serie: si tolgono solo
    // quelle non ancora salvate.
    setRows((prev) => {
      if (!prev) return prev;
      let righe = [...prev[item.id]];
      while (righe.length < v.target_sets) righe.push(prefill(righe, righe.length, v, last[item.exercise.id]));
      while (righe.length > v.target_sets && righe[righe.length - 1].setId === null) righe = righe.slice(0, -1);
      return { ...prev, [item.id]: righe };
    });
  }

  async function saveTargetsToPlan(item: PlanExercise) {
    try {
      onPlanUpdated(
        await api.patch<WorkoutPlan>(`/workout/plan-exercises/${item.id}?profile_id=${profileId}`, targets[item.id])
      );
      setBase((prev) => ({ ...prev, [item.id]: targets[item.id] }));
      setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito a salvare nella scheda.");
    }
  }

  const done = rows ? Object.values(rows).flat().filter((r) => r.setId).length : 0;
  const total = rows ? Object.values(rows).flat().length : 0;

  return (
    <>
    <Modal onClose={onClose} align="top" className="max-w-2xl">
      <ModalHeader
        eyebrow={`Allenamento · ${plan.name}`}
        title={`Giorno ${dayLabel}`}
        subtitle={
          rows
            ? `${done} di ${total} serie segnate · ogni serie si salva appena la confermi`
            : "Carico la sessione…"
        }
        onClose={onClose}
      />

      <div className="flex-1 space-y-3 overflow-y-auto overscroll-contain p-3 sm:p-4">
        {error && <Notice>{error}</Notice>}
        {!rows && !error && <Spinner label="Carico la sessione…" />}

        {rows &&
          exercises.map((item) => {
            const t = targets[item.id];
            const volta = last[item.exercise.id];
            const cambiati = !sameParams(t, base[item.id]);
            return (
              <div key={item.id} className="rounded-2xl border border-white/[0.08] bg-white/[0.025]">
                <div className="flex items-start gap-3 px-3.5 pt-3 sm:px-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] font-semibold leading-snug text-white">{exerciseName(item.exercise)}</p>
                    <p className="mt-0.5 font-mono text-[12px] tabular-nums text-white/50">
                      {t.target_sets} × {t.target_reps_min}-{t.target_reps_max} · RIR {t.target_rir} · rec.{" "}
                      {restLabel(t.rest_seconds)}
                      {cambiati && <span className="ml-1.5 text-amber-200/80">modificato</span>}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <IconButton
                      label="Modifica serie, ripetizioni, RIR e recupero"
                      active={editing === item.id}
                      onClick={() => setEditing(editing === item.id ? null : item.id)}
                      path="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75L3 17.25Zm17.7-10.2a1 1 0 0 0 0-1.42l-2.33-2.33a1 1 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.83-1.83Z"
                    />
                    <IconButton
                      label="Storico dei carichi"
                      onClick={() => setHistory(item)}
                      path="M13 3a9 9 0 0 0-9 9H1l4 4 4-4H6a7 7 0 1 1 2.05 4.95l-1.42 1.42A9 9 0 1 0 13 3Zm-1 5v5l4.25 2.52.77-1.28-3.52-2.09V8H12Z"
                    />
                  </div>
                </div>

                <AnimatePresence initial={false}>
                  {editing === item.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mx-3.5 mt-3 space-y-3 rounded-xl border border-white/[0.07] bg-black/20 p-3 sm:mx-4">
                        <ParamsEditor value={t} onChange={(v) => changeTargets(item, v)} />
                        <p className="text-[11.5px] leading-snug text-white/40">
                          Valgono per questa sessione.{" "}
                          {cambiati ? "Vuoi tenerli anche per le prossime?" : ""}
                        </p>
                        {cambiati && (
                          <button
                            className="btn-ghost w-full text-[12.5px]"
                            disabled={t.target_reps_min > t.target_reps_max}
                            onClick={() => saveTargetsToPlan(item)}
                          >
                            Salva anche nella scheda
                          </button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <p className="px-3.5 pt-2 text-[12px] text-white/40 sm:px-4">
                  {volta ? (
                    <>
                      Ultima volta ({shortDate(volta.date)}):{" "}
                      <span className="font-mono tabular-nums text-white/60">{setsSummary(volta.sets)}</span>
                    </>
                  ) : (
                    "Prima volta: scegli un carico con cui arrivi al RIR indicato."
                  )}
                </p>

                <div className="px-2 pb-2 pt-2 sm:px-3">
                  <div className="grid grid-cols-[32px_1fr_1fr_60px_44px] items-center gap-1.5 px-1 pb-1 text-[10.5px] uppercase tracking-wide text-white/30 sm:gap-2">
                    <span className="text-center">#</span>
                    <span className="text-center">kg</span>
                    <span className="text-center">rip.</span>
                    <span className="text-center">RIR</span>
                    <span />
                  </div>
                  {rows[item.id].map((row, i) => {
                    const salvata = row.saved !== null;
                    const modificata =
                      salvata && (row.kg !== row.saved!.kg || row.reps !== row.saved!.reps || row.rir !== row.saved!.rir);
                    return (
                      <div
                        key={row.key}
                        className={`grid grid-cols-[32px_1fr_1fr_60px_44px] items-center gap-1.5 rounded-xl px-1 py-1 transition sm:gap-2 ${
                          salvata && !modificata ? "bg-lime-400/[0.06]" : ""
                        }`}
                      >
                        <button
                          onClick={() => deleteRow(item, row)}
                          aria-label={row.confirmDelete ? "Conferma: elimina la serie" : `Serie ${i + 1}: tocca per eliminarla`}
                          title="Elimina la serie"
                          className={`grid h-9 place-items-center rounded-lg font-mono text-[12.5px] tabular-nums transition ${
                            row.confirmDelete
                              ? "bg-rose-500/80 text-white"
                              : "text-white/45 hover:bg-white/[0.06]"
                          }`}
                        >
                          {row.confirmDelete ? "✕" : i + 1}
                        </button>
                        <NumberField
                          value={row.kg}
                          onChange={(v) => patchRow(item.id, row.key, { kg: v })}
                          min={0}
                          max={1000}
                          step={2.5}
                          decimals={2}
                          size="sm"
                          steppers="sm"
                          placeholder="kg"
                          ariaLabel={`Carico serie ${i + 1}`}
                        />
                        <NumberField
                          value={row.reps}
                          onChange={(v) => patchRow(item.id, row.key, { reps: v })}
                          min={1}
                          max={100}
                          size="sm"
                          steppers="sm"
                          placeholder="rip."
                          ariaLabel={`Ripetizioni serie ${i + 1}`}
                          onEnter={() => saveRow(item, row, i)}
                        />
                        <select
                          value={row.rir ?? ""}
                          onChange={(e) =>
                            patchRow(item.id, row.key, { rir: e.target.value === "" ? null : Number(e.target.value) })
                          }
                          aria-label={`RIR serie ${i + 1}`}
                          className="h-9 rounded-xl border border-white/10 bg-black/30 px-1 text-center font-mono text-[13px] text-white outline-none focus:border-lime-400/50"
                        >
                          <option value="">—</option>
                          {[0, 1, 2, 3, 4, 5].map((n) => (
                            <option key={n} value={n}>
                              {n}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => saveRow(item, row, i)}
                          disabled={row.busy || row.kg === null || !row.reps || (salvata && !modificata)}
                          aria-label={salvata && !modificata ? `Serie ${i + 1} salvata` : `Salva la serie ${i + 1}`}
                          className={`grid h-9 w-11 place-items-center rounded-xl border transition ${
                            salvata && !modificata
                              ? "border-lime-400/60 bg-lime-400 text-ink-900"
                              : "border-lime-400/40 bg-lime-400/[0.1] text-lime-200 hover:bg-lime-400/20 disabled:border-white/10 disabled:bg-transparent disabled:text-white/25"
                          }`}
                        >
                          {row.busy ? (
                            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          ) : (
                            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={3}>
                              <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          )}
                        </button>
                      </div>
                    );
                  })}
                  <button
                    onClick={() => addRow(item)}
                    className="mt-1 w-full rounded-xl py-2 text-[12.5px] font-medium text-white/45 transition hover:bg-white/[0.04] hover:text-white/80"
                  >
                    + Aggiungi serie
                  </button>
                </div>
              </div>
            );
          })}
      </div>

      <AnimatePresence>
        {rest && (
          <motion.div
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            className="shrink-0 border-t border-white/[0.08] bg-ink-900/95 px-4 py-3 backdrop-blur"
          >
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] uppercase tracking-wide text-white/40">Recupero</p>
                <p className="font-mono text-[24px] font-semibold leading-none tabular-nums text-white">
                  {restLabel(remaining)}
                </p>
              </div>
              <button className="btn-ghost h-10 px-3 text-[13px]" onClick={() => setRest({ ...rest, endsAt: rest.endsAt - 15000 })}>
                −15s
              </button>
              <button className="btn-ghost h-10 px-3 text-[13px]" onClick={() => setRest({ ...rest, endsAt: rest.endsAt + 15000 })}>
                +15s
              </button>
              <button className="btn-primary h-10 px-4 text-[13px]" onClick={() => setRest(null)}>
                Salta
              </button>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className="h-full rounded-full bg-lime-400 transition-[width] duration-300"
                style={{ width: `${Math.min(100, (remaining / rest.total) * 100)}%` }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!rest && (
        <div className="shrink-0 border-t border-white/[0.06] p-3">
          <button className="btn-primary w-full" onClick={onClose}>
            {done > 0 ? "Fine allenamento" : "Chiudi"}
          </button>
        </div>
      )}

    </Modal>

    {/* Fuori dal pannello: dentro un contenitore animato un elemento fixed
        si posizionerebbe rispetto a lui, non allo schermo. */}
    <AnimatePresence>
      {history && (
        <LoadHistoryDialog
          key="history"
          profileId={profileId}
          exerciseId={history.exercise.id}
          onClose={() => setHistory(null)}
        />
      )}
    </AnimatePresence>
    </>
  );
}

function IconButton({
  label,
  path,
  onClick,
  active = false,
}: {
  label: string;
  path: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={`grid h-10 w-10 place-items-center rounded-xl border transition ${
        active
          ? "border-lime-400/50 bg-lime-400/15 text-lime-200"
          : "border-white/10 bg-white/[0.04] text-white/55 hover:text-white"
      }`}
    >
      <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current">
        <path d={path} />
      </svg>
    </button>
  );
}

// --- Storico ----------------------------------------------------------------------------

/** Storico di un esercizio: ogni sessione con le sue serie, correggibili. */
export function LoadHistoryDialog({
  profileId,
  exerciseId,
  onClose,
  onChanged,
}: {
  profileId: number;
  exerciseId: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const [data, setData] = useState<ExerciseHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<SessionSet | null>(null);
  const [draft, setDraft] = useState<{ kg: number | null; reps: number | null }>({ kg: null, reps: null });

  const load = useCallback(async () => {
    try {
      setData(await api.get<ExerciseHistory>(`/workout/exercises/${exerciseId}/history?profile_id=${profileId}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non riesco a caricare lo storico.");
    }
  }, [exerciseId, profileId]);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    if (!editing || draft.kg === null || !draft.reps) return;
    await api.patch(`/workout/sets/${editing.id}`, { weight_kg: draft.kg, reps: draft.reps });
    setEditing(null);
    await load();
    onChanged?.();
  }

  async function remove(s: SessionSet) {
    await api.del(`/workout/sets/${s.id}`);
    setEditing(null);
    await load();
    onChanged?.();
  }

  return (
    <Modal onClose={onClose} className="max-w-lg" z="z-[90]">
      <ModalHeader
        eyebrow="Storico dei carichi"
        title={data?.exercise_name ?? "…"}
        subtitle="Tocca una serie per correggerla: cambia solo quella, le altre sessioni restano com'erano."
        onClose={onClose}
      />
      <div className="flex-1 space-y-2 overflow-y-auto overscroll-contain p-3 sm:p-4">
        {error && <Notice>{error}</Notice>}
        {!data && !error && <Spinner label="Carico lo storico…" />}
        {data && data.sessions.length === 0 && (
          <Empty title="Ancora nessuna serie" hint="Le serie segnate durante l'allenamento compaiono qui, sessione per sessione." />
        )}
        {data?.sessions.map((s) => (
          <div key={s.session_id} className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2.5">
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <p className="text-[13px] font-medium text-white/85">
                {shortDate(s.date)}
                {s.day_label && <span className="ml-1.5 text-white/35">· giorno {s.day_label}</span>}
              </p>
              <p className="font-mono text-[11.5px] tabular-nums text-white/40">
                max {kg(s.top_weight_kg)} kg · 1RM ~{kg(Math.round(s.best_e1rm))}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {s.sets.map((set) =>
                editing?.id === set.id ? (
                  <div key={set.id} className="flex w-full flex-wrap items-center gap-2 rounded-lg bg-black/25 p-2">
                    <NumberField
                      value={draft.kg}
                      onChange={(v) => setDraft({ ...draft, kg: v })}
                      step={2.5}
                      decimals={2}
                      min={0}
                      max={1000}
                      suffix="kg"
                      size="sm"
                      ariaLabel="Carico"
                      className="w-36"
                    />
                    <NumberField
                      value={draft.reps}
                      onChange={(v) => setDraft({ ...draft, reps: v })}
                      min={1}
                      max={100}
                      suffix="rip"
                      size="sm"
                      ariaLabel="Ripetizioni"
                      className="w-32"
                    />
                    <div className="ml-auto flex gap-1.5">
                      <button className="btn-ghost h-9 px-3 text-[12px] text-rose-200" onClick={() => remove(set)}>
                        Elimina
                      </button>
                      <button className="btn-primary h-9 px-3 text-[12px]" onClick={save}>
                        Salva
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    key={set.id}
                    onClick={() => {
                      setEditing(set);
                      setDraft({ kg: set.weight_kg, reps: set.reps });
                    }}
                    className="rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 font-mono text-[12.5px] tabular-nums text-white/75 transition hover:border-lime-400/40 hover:text-lime-100"
                  >
                    {kg(set.weight_kg)}×{set.reps}
                    {set.rir !== null && <span className="ml-1 text-white/35">@{set.rir}</span>}
                  </button>
                )
              )}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}

// --- Grafico della progressione (per il resoconto) --------------------------------------

export function useHistory(profileId: number, exerciseId: number | null, weeks: number) {
  const [data, setData] = useState<ExerciseHistory | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (exerciseId === null) return;
    let annullato = false;
    setData(null);
    api
      .get<ExerciseHistory>(`/workout/exercises/${exerciseId}/history?profile_id=${profileId}&weeks=${weeks}`)
      .then((d) => !annullato && setData(d))
      .catch(() => !annullato && setData({ exercise_id: exerciseId, exercise_name: "", sessions: [] }));
    return () => {
      annullato = true;
    };
  }, [profileId, exerciseId, weeks, version]);
  const points = useMemo(
    () =>
      [...(data?.sessions ?? [])].reverse().map((s) => ({
        date: shortDate(s.date),
        carico: s.top_weight_kg,
        massimale: Math.round(s.best_e1rm * 10) / 10,
        serie: setsSummary(s.sets),
      })),
    [data]
  );
  return { data, points, reload: () => setVersion((v) => v + 1) };
}
