"use client";

/**
 * Allenamento: avvio, serie, fine. E i parametri della scheda.
 *
 * L'allenamento ha tre stati, e il pannello li mostra in modo diverso:
 * - **pronto**: cosa ti aspetta oggi e un grande "Avvia allenamento";
 * - **in corso**: il cronometro, le serie una a una e il recupero. Chiudendo
 *   il pannello l'allenamento continua: nella pagina il pulsante diventa
 *   "Allenamento in corso" con il tempo che scorre, e lo si riapre da lì;
 * - **completato**: il riepilogo (durata, serie, chili, record).
 *
 * Le serie: i valori dell'ultima volta sono un **suggerimento in grigio**
 * dentro i campi, non numeri già scritti. Diventano tuoi quando li confermi
 * con ✓ (anche lasciando il campo vuoto, se il suggerimento va bene) o li
 * cambi. Ogni serie confermata si salva subito e dice com'è andata rispetto
 * all'ultima volta.
 *
 * I parametri (serie, ripetizioni, RIR, recupero) si cambiano con riquadri
 * grandi: nella scheda valgono per sempre, durante l'allenamento per la
 * sessione, con "Salva anche nella scheda" per tenerli.
 *
 * `exercises` va passato stabile (una copia fatta all'apertura): la sessione
 * si carica una volta sola, e un nuovo array a ogni render della pagina la
 * ricaricherebbe azzerando le serie in corso.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  exerciseName,
  localDate,
  notifyLogged,
  type ExerciseHistory,
  type ExerciseSession,
  type PlanExercise,
  type PlanExerciseParams,
  type SessionSet,
  type SessionSummary,
  type WorkoutPlan,
  type WorkoutSessionLog,
} from "@/lib/api";
import {
  Field,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  NumberField,
  OptionGroup,
  Stepper,
} from "@/components/controls";
import { Empty, Notice, Spinner } from "@/components/ui";
import { Mascot } from "@/components/Mascot";

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

/** Durata in forma di cronometro: 4:05, 1:02:10. */
export function clock(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

/** Le date del server senza fuso (SQLite) sono in UTC. */
export function serverTime(iso: string): number {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

/** Secondi trascorsi da `startedAt`, aggiornati ogni secondo. */
export function useElapsed(startedAt: string | null | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [startedAt]);
  return startedAt ? Math.max(0, Math.floor((now - serverTime(startedAt)) / 1000)) : 0;
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

const RECUPERI = [60, 90, 120, 150, 180];

export function ParamsEditor({
  value,
  onChange,
}: {
  value: PlanExerciseParams;
  onChange: (v: PlanExerciseParams) => void;
}) {
  const set = <K extends keyof PlanExerciseParams>(k: K, n: number) => onChange({ ...value, [k]: n });
  return (
    <div className="space-y-3">
      <Field title="Serie">
        <div className="mx-auto max-w-[220px]">
          <Stepper value={value.target_sets} onChange={(n) => set("target_sets", n)} min={1} max={10} label="serie" />
        </div>
      </Field>
      <Field title="Ripetizioni" hint="Da quante a quante per serie.">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="mb-1.5 text-center text-[11px] text-white/40">minime</p>
            <Stepper
              compact
              value={value.target_reps_min}
              onChange={(n) => onChange({ ...value, target_reps_min: n, target_reps_max: Math.max(n, value.target_reps_max) })}
              min={1}
              max={50}
              label="ripetizioni minime"
            />
          </div>
          <div>
            <p className="mb-1.5 text-center text-[11px] text-white/40">massime</p>
            <Stepper
              compact
              value={value.target_reps_max}
              onChange={(n) => onChange({ ...value, target_reps_max: n, target_reps_min: Math.min(n, value.target_reps_min) })}
              min={1}
              max={50}
              label="ripetizioni massime"
            />
          </div>
        </div>
      </Field>
      <Field title="RIR" hint="Ripetizioni che tieni di riserva a fine serie: 0 è il cedimento.">
        <OptionGroup
          ariaLabel="RIR"
          mono
          columns="grid-cols-6"
          value={value.target_rir}
          onChange={(n) => set("target_rir", n)}
          options={[0, 1, 2, 3, 4, 5].map((n) => ({ value: n, label: n }))}
        />
      </Field>
      <Field title="Recupero tra le serie">
        <OptionGroup
          ariaLabel="Recupero"
          mono
          columns="grid-cols-5"
          value={value.rest_seconds}
          onChange={(n) => set("rest_seconds", n)}
          options={RECUPERI.map((sec) => ({ value: sec, label: restLabel(sec) }))}
        />
        <div className="mt-3">
          <Stepper
            value={value.rest_seconds}
            onChange={(n) => set("rest_seconds", n)}
            min={15}
            max={600}
            step={15}
            label="recupero"
            format={restLabel}
          />
        </div>
      </Field>
    </div>
  );
}

/**
 * La stessa finestra per cambiare i parametri, dalla scheda e durante
 * l'allenamento. Nella scheda c'è un solo salvataggio; durante l'allenamento
 * si sceglie se valgono solo per oggi o anche per le prossime volte.
 */
function ParamsDialog({
  title,
  subtitle,
  initial,
  saving,
  error,
  onClose,
  onSaveToPlan,
  onApplyToday,
}: {
  title: string;
  subtitle: string;
  initial: PlanExerciseParams;
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onSaveToPlan: (v: PlanExerciseParams) => void;
  onApplyToday?: (v: PlanExerciseParams) => void;
}) {
  const [value, setValue] = useState(initial);
  const cambiati = !sameParams(value, initial);
  return (
    <Modal onClose={onClose} className="max-w-lg" align="top" z={onApplyToday ? "z-[90]" : undefined}>
      <ModalHeader eyebrow="Modifica l'esercizio" title={title} subtitle={subtitle} onClose={onClose} />
      <ModalBody>
        <ParamsEditor value={value} onChange={setValue} />
        {error && <Notice>{error}</Notice>}
      </ModalBody>
      <ModalFooter>
        {onApplyToday ? (
          <button className="btn-ghost flex-1 justify-center whitespace-nowrap px-3" onClick={() => onApplyToday(value)} disabled={saving}>
            Solo per oggi
          </button>
        ) : (
          <button className="btn-ghost flex-1 justify-center" onClick={onClose}>
            Annulla
          </button>
        )}
        <button
          className="btn-primary flex-[1.6] justify-center whitespace-nowrap"
          onClick={() => onSaveToPlan(value)}
          disabled={saving || (!onApplyToday && !cambiati)}
        >
          {saving ? "Salvo…" : "Salva nella scheda"}
        </button>
      </ModalFooter>
    </Modal>
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(value: PlanExerciseParams) {
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
    <ParamsDialog
      title={exerciseName(item.exercise)}
      subtitle="I valori di partenza vengono dalle fonti. Da qui in poi decidi tu: valgono per tutte le prossime sessioni."
      initial={paramsOf(item)}
      saving={saving}
      error={error}
      onClose={onClose}
      onSaveToPlan={save}
    />
  );
}

/** La riga dei parametri: la stessa nella scheda e nell'allenamento. */
export function ParamsChips({
  value,
  changed = false,
  onEdit,
}: {
  value: PlanExerciseParams;
  changed?: boolean;
  onEdit: () => void;
}) {
  return (
    <button
      onClick={onEdit}
      className="group/params flex w-full flex-wrap items-center gap-1.5 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-2.5 py-2 text-left transition hover:border-lime-400/35 hover:bg-lime-400/[0.04]"
      aria-label="Modifica serie, ripetizioni, RIR e recupero"
    >
      {[
        `${value.target_sets} serie`,
        `${value.target_reps_min}-${value.target_reps_max} rip.`,
        `RIR ${value.target_rir}`,
        `rec. ${restLabel(value.rest_seconds)}`,
      ].map((c) => (
        <span key={c} className="rounded-full bg-white/[0.06] px-2.5 py-1 font-mono text-[12px] tabular-nums text-white/80">
          {c}
        </span>
      ))}
      <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-lime-400/15 px-2.5 py-1 text-[12px] font-medium text-lime-300 transition group-hover/params:bg-lime-400 group-hover/params:text-ink-900">
        <PencilIcon />
        {changed ? "Modificato" : "Modifica"}
      </span>
    </button>
  );
}

// --- Allenamento ----------------------------------------------------------------------

type Row = {
  key: string;
  setId: number | null;
  // null = campo vuoto: vale il suggerimento mostrato in grigio.
  kg: number | null;
  reps: number | null;
  rir: number | null;
  saved: { kg: number; reps: number; rir: number | null } | null;
  busy?: boolean;
  confirmDelete?: boolean;
};

let rowSeq = 0;
const newKey = () => `r${++rowSeq}`;

function emptyRow(): Row {
  return { key: newKey(), setId: null, kg: null, reps: null, rir: null, saved: null };
}

function rowsFor(target: PlanExerciseParams, logged: SessionSet[]): Row[] {
  const rows: Row[] = logged.map((s) => ({
    key: newKey(),
    setId: s.id,
    kg: s.weight_kg,
    reps: s.reps,
    rir: s.rir,
    saved: { kg: s.weight_kg, reps: s.reps, rir: s.rir },
  }));
  while (rows.length < target.target_sets) rows.push(emptyRow());
  return rows;
}

type Hint = { kg: number | null; reps: number; rir: number };

/** Il suggerimento di ogni riga: la serie prima, o quella dell'ultima volta. */
function hintsFor(rows: Row[], target: PlanExerciseParams, last?: ExerciseSession): Hint[] {
  const out: Hint[] = [];
  rows.forEach((r, i) => {
    const volta = last?.sets[i] ?? last?.sets[last.sets.length - 1];
    const prima = i > 0 ? out[i - 1] : null;
    const primaRiga = i > 0 ? rows[i - 1] : null;
    out.push({
      kg: primaRiga?.kg ?? prima?.kg ?? volta?.weight_kg ?? null,
      reps: primaRiga?.reps ?? prima?.reps ?? volta?.reps ?? target.target_reps_max,
      rir: primaRiga?.rir ?? prima?.rir ?? target.target_rir,
    });
  });
  return out;
}

/** Com'è andata la serie rispetto alla stessa serie dell'ultima volta. */
function compare(saved: { kg: number; reps: number }, prev?: SessionSet): { text: string; better: boolean | null } | null {
  if (!prev) return null;
  const dKg = Math.round((saved.kg - prev.weight_kg) * 100) / 100;
  if (dKg > 0) return { text: `+${kg(dKg)} kg`, better: true };
  if (dKg < 0) return { text: `${kg(dKg)} kg`, better: false };
  const dReps = saved.reps - prev.reps;
  if (dReps > 0) return { text: `+${dReps} rip.`, better: true };
  if (dReps < 0) return { text: `${dReps} rip.`, better: false };
  return { text: "come l'ultima volta", better: null };
}

type Phase = "loading" | "ready" | "running" | "done";

export function SessionDialog({
  profileId,
  plan,
  dayLabel,
  exercises,
  onClose,
  onPlanUpdated,
  onSessionChange,
}: {
  profileId: number;
  plan: WorkoutPlan;
  dayLabel: string;
  exercises: PlanExercise[];
  onClose: () => void;
  onPlanUpdated: (plan: WorkoutPlan) => void;
  /** L'allenamento in corso (o null quando termina): per il pulsante nella pagina. */
  onSessionChange?: (session: WorkoutSessionLog | null) => void;
}) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [session, setSession] = useState<WorkoutSessionLog | null>(null);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [last, setLast] = useState<Record<number, ExerciseSession>>({});
  const [targets, setTargets] = useState<Record<number, PlanExerciseParams>>(() =>
    Object.fromEntries(exercises.map((e) => [e.id, paramsOf(e)]))
  );
  const [base, setBase] = useState<Record<number, PlanExerciseParams>>(() =>
    Object.fromEntries(exercises.map((e) => [e.id, paramsOf(e)]))
  );
  const [rows, setRows] = useState<Record<number, Row[]>>({});
  const [editing, setEditing] = useState<PlanExercise | null>(null);
  const [savingParams, setSavingParams] = useState(false);
  const [paramsError, setParamsError] = useState<string | null>(null);
  const [history, setHistory] = useState<PlanExercise | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rest, setRest] = useState<{ endsAt: number; total: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  const [finishing, setFinishing] = useState(false);
  const creating = useRef<Promise<WorkoutSessionLog> | null>(null);
  const sessionRef = useRef<WorkoutSessionLog | null>(null);
  sessionRef.current = session;
  const elapsed = useElapsed(phase === "running" ? session?.started_at : null);
  const oggi = useMemo(() => localDate(), []);

  // La sessione di oggi (se c'è) e l'ultima volta di ogni esercizio.
  useEffect(() => {
    let annullato = false;
    (async () => {
      try {
        const corrente = await api.get<WorkoutSessionLog | null>(
          `/workout/sessions/current?profile_id=${profileId}&day_label=${encodeURIComponent(dayLabel)}&plan_id=${plan.id}&today=${oggi}`
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
                paramsOf(e),
                (corrente?.sets ?? [])
                  .filter((s) => s.exercise_id === e.exercise.id)
                  .sort((a, b) => a.set_number - b.set_number)
              ),
            ])
          )
        );
        setPhase(corrente?.started_at && !corrente.ended_at ? "running" : "ready");
      } catch (e) {
        if (!annullato) setError(e instanceof Error ? e.message : "Non riesco a caricare l'allenamento.");
      }
    })();
    return () => {
      annullato = true;
    };
  }, [profileId, plan.id, dayLabel, exercises, oggi]);

  // Recupero.
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

  function update(s: WorkoutSessionLog | null) {
    setSession(s);
    onSessionChange?.(s && s.started_at && !s.ended_at ? s : null);
  }

  /** Avvia l'allenamento: crea la sessione di oggi, o riapre quella chiusa. */
  const start = useCallback(async () => {
    setError(null);
    try {
      let s = sessionRef.current;
      if (s) {
        s = await api.post<WorkoutSessionLog>(`/workout/sessions/${s.id}/start`);
      } else {
        if (!creating.current) {
          creating.current = api.post<WorkoutSessionLog>(`/workout/sessions?profile_id=${profileId}`, {
            day_label: dayLabel,
            workout_plan_id: plan.id,
            date: oggi,
            start: true,
          });
        }
        s = await creating.current;
      }
      update(s);
      setPhase("running");
      notifyLogged(); // il pallino della Scheda sparisce: l'allenamento è iniziato
      return s;
    } catch (e) {
      creating.current = null;
      setError(e instanceof Error ? e.message : "Non sono riuscito ad avviare l'allenamento.");
      return null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId, dayLabel, plan.id, oggi]);

  async function finish() {
    const s = sessionRef.current;
    if (!s) return;
    setFinishing(true);
    try {
      const r = await api.post<SessionSummary>(`/workout/sessions/${s.id}/finish`);
      setSummary(r);
      update(r.session);
      setRest(null);
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito a chiudere l'allenamento.");
    } finally {
      setFinishing(false);
    }
  }

  function patchRow(itemId: number, key: string, change: Partial<Row>) {
    setRows((prev) => ({ ...prev, [itemId]: prev[itemId].map((r) => (r.key === key ? { ...r, ...change } : r)) }));
  }

  async function saveRow(item: PlanExercise, row: Row, index: number, hint: Hint) {
    const pesi = row.kg ?? hint.kg;
    const ripetizioni = row.reps ?? hint.reps;
    const rir = row.rir ?? hint.rir;
    if (pesi === null || !ripetizioni) return;
    patchRow(item.id, row.key, { busy: true });
    setError(null);
    try {
      const corpo = { weight_kg: pesi, reps: ripetizioni, rir };
      let id = row.setId;
      if (id) {
        await api.patch(`/workout/sets/${id}`, corpo);
      } else {
        const s = sessionRef.current?.started_at && !sessionRef.current.ended_at ? sessionRef.current : await start();
        if (!s) throw new Error("allenamento non avviato");
        const creata = await api.post<SessionSet>(`/workout/sessions/${s.id}/sets`, {
          ...corpo,
          exercise_id: item.exercise.id,
          set_number: index + 1,
        });
        id = creata.id;
        const recupero = targets[item.id].rest_seconds;
        setRest({ endsAt: Date.now() + recupero * 1000, total: recupero });
      }
      patchRow(item.id, row.key, { setId: id, busy: false, kg: pesi, reps: ripetizioni, rir, saved: { kg: pesi, reps: ripetizioni, rir } });
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
    setRows((prev) => ({ ...prev, [item.id]: prev[item.id].filter((r) => r.key !== row.key) }));
  }

  function changeTargets(item: PlanExercise, v: PlanExerciseParams) {
    setTargets((prev) => ({ ...prev, [item.id]: v }));
    setRows((prev) => {
      let righe = [...prev[item.id]];
      while (righe.length < v.target_sets) righe.push(emptyRow());
      while (righe.length > v.target_sets && righe[righe.length - 1].setId === null) righe = righe.slice(0, -1);
      return { ...prev, [item.id]: righe };
    });
  }

  async function saveTargetsToPlan(item: PlanExercise, v: PlanExerciseParams) {
    setSavingParams(true);
    setParamsError(null);
    try {
      onPlanUpdated(await api.patch<WorkoutPlan>(`/workout/plan-exercises/${item.id}?profile_id=${profileId}`, v));
      changeTargets(item, v);
      setBase((prev) => ({ ...prev, [item.id]: v }));
      setEditing(null);
    } catch (e) {
      setParamsError(e instanceof Error ? e.message : "Non sono riuscito a salvare nella scheda.");
    } finally {
      setSavingParams(false);
    }
  }

  const tutte = Object.values(rows).flat();
  const fatte = tutte.filter((r) => r.setId).length;
  const stimaMinuti = Math.round(
    exercises.reduce((t, e) => t + targets[e.id].target_sets * (targets[e.id].rest_seconds + 45), 0) / 60
  );

  return (
    <>
      <Modal onClose={onClose} align="top" className="max-w-2xl">
        {/* Intestazione: la stessa degli altri pannelli, con il cronometro
            sotto il titolo quando l'allenamento è in corso. */}
        <ModalHeader
          eyebrow={plan.name}
          title={dayLabel.length <= 2 ? `Giorno ${dayLabel}` : dayLabel}
          subtitle={
            phase === "ready"
              ? `${exercises.length} esercizi · ${tutte.length} serie · circa ${stimaMinuti} minuti${session?.ended_at ? " · già completato oggi" : ""}`
              : undefined
          }
          onClose={onClose}
        >
          {phase === "running" && (
            <div className="mt-3 flex items-end justify-between gap-4">
              <div>
                <p className="flex items-center gap-1.5 text-[11.5px] font-medium text-lime-300/90">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-lime-400 opacity-70" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-lime-400" />
                  </span>
                  In corso
                </p>
                <p className="font-mono text-[30px] font-semibold leading-none tabular-nums text-white">{clock(elapsed)}</p>
              </div>
              <div className="min-w-0 flex-1 pb-1">
                <div className="mb-1 flex justify-between text-[11.5px] text-white/45">
                  <span>serie</span>
                  <span className="font-mono tabular-nums text-white/70">
                    {fatte}/{tutte.length}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-lime-500 to-lime-400"
                    animate={{ width: `${tutte.length ? (fatte / tutte.length) * 100 : 0}%` }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
              </div>
            </div>
          )}
        </ModalHeader>

        {/* Corpo */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5">
          {error && (
            <div className="mb-3">
              <Notice>{error}</Notice>
            </div>
          )}
          {phase === "loading" && !error && <Spinner label="Preparo l'allenamento…" />}

          {phase === "done" && summary && <Summary summary={summary} />}

          {(phase === "ready" || phase === "running") && (
            <div className="space-y-4">
              {exercises.map((item, n) => {
                const t = targets[item.id];
                const volta = last[item.exercise.id];
                const cambiati = !sameParams(t, base[item.id]);
                const righe = rows[item.id] ?? [];
                const suggerimenti = hintsFor(righe, t, volta);
                return (
                  <motion.section
                    key={item.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: n * 0.04 }}
                    className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-3.5"
                  >
                    <div className="flex items-start gap-3">
                      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white/[0.07] font-mono text-[12px] text-white/60">
                        {n + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-[16px] font-semibold leading-snug text-white">{exerciseName(item.exercise)}</h3>
                        <button
                          onClick={() => setHistory(item)}
                          className="mt-0.5 text-left text-[12.5px] leading-snug text-white/45 transition hover:text-white/75"
                        >
                          {volta ? (
                            <>
                              Ultima volta, {shortDate(volta.date)}:{" "}
                              <span className="font-mono tabular-nums text-white/65">{setsSummary(volta.sets)}</span>
                            </>
                          ) : (
                            "Prima volta: scegli un carico con cui arrivi al RIR indicato"
                          )}
                        </button>
                      </div>
                    </div>

                    {/* I parametri: la stessa riga e la stessa finestra della scheda */}
                    <div className="mt-3">
                      <ParamsChips value={t} changed={cambiati} onEdit={() => setEditing(item)} />
                    </div>

                    <div className="mt-4">
                      <div className="grid grid-cols-[34px_1fr_1fr_62px_46px] items-center gap-2 px-0.5 pb-1.5 text-[11px] uppercase tracking-wide text-white/35">
                        <span className="text-center">#</span>
                        <span className="text-center">kg</span>
                        <span className="text-center">rip.</span>
                        <span className="text-center">RIR</span>
                        <span />
                      </div>
                      <div className="space-y-2">
                        {righe.map((row, i) => {
                          const h = suggerimenti[i];
                          const salvata = row.saved !== null;
                          const effettivo = { kg: row.kg ?? h.kg, reps: row.reps ?? h.reps, rir: row.rir ?? h.rir };
                          const modificata =
                            salvata &&
                            (effettivo.kg !== row.saved!.kg || effettivo.reps !== row.saved!.reps || effettivo.rir !== row.saved!.rir);
                          const confronto = salvata && !modificata ? compare(row.saved!, volta?.sets[i] ?? volta?.sets[volta.sets.length - 1]) : null;
                          return (
                            <div key={row.key}>
                              <div
                                className={`grid grid-cols-[34px_1fr_1fr_62px_46px] items-center gap-2 rounded-2xl p-0.5 transition ${
                                  salvata && !modificata ? "bg-lime-400/[0.07]" : ""
                                }`}
                              >
                                <button
                                  onClick={() => deleteRow(item, row)}
                                  aria-label={row.confirmDelete ? "Conferma: elimina la serie" : `Serie ${i + 1}: tocca per eliminarla`}
                                  className={`grid h-11 place-items-center rounded-xl font-mono text-[13px] tabular-nums transition ${
                                    row.confirmDelete ? "bg-rose-500/80 text-white" : "text-white/50 hover:bg-white/[0.06]"
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
                                  steppers="sm"
                                  placeholder={h.kg !== null ? kg(h.kg) : "kg"}
                                  ariaLabel={`Carico serie ${i + 1}`}
                                />
                                <NumberField
                                  value={row.reps}
                                  onChange={(v) => patchRow(item.id, row.key, { reps: v })}
                                  min={1}
                                  max={100}
                                  steppers="sm"
                                  placeholder={String(h.reps)}
                                  ariaLabel={`Ripetizioni serie ${i + 1}`}
                                  onEnter={() => saveRow(item, row, i, h)}
                                />
                                <select
                                  value={row.rir ?? ""}
                                  onChange={(e) =>
                                    patchRow(item.id, row.key, { rir: e.target.value === "" ? null : Number(e.target.value) })
                                  }
                                  aria-label={`RIR serie ${i + 1}`}
                                  className={`h-11 rounded-xl border border-white/10 bg-black/30 px-1 text-center font-mono text-[14px] outline-none focus:border-lime-400/50 ${
                                    row.rir === null ? "text-white/35" : "text-white"
                                  }`}
                                >
                                  <option value="">{h.rir}</option>
                                  {[0, 1, 2, 3, 4, 5].map((v) => (
                                    <option key={v} value={v}>
                                      {v}
                                    </option>
                                  ))}
                                </select>
                                <motion.button
                                  whileTap={{ scale: 0.88 }}
                                  onClick={() => saveRow(item, row, i, h)}
                                  disabled={row.busy || effettivo.kg === null || !effettivo.reps || (salvata && !modificata)}
                                  aria-label={salvata && !modificata ? `Serie ${i + 1} salvata` : `Salva la serie ${i + 1}`}
                                  className={`grid h-11 w-[46px] place-items-center rounded-xl border transition ${
                                    salvata && !modificata
                                      ? "border-lime-400/60 bg-lime-400 text-ink-900"
                                      : "border-lime-400/45 bg-lime-400/[0.12] text-lime-200 hover:bg-lime-400/25 disabled:border-white/10 disabled:bg-transparent disabled:text-white/25"
                                  }`}
                                >
                                  {row.busy ? (
                                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                                  ) : (
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={3}>
                                      <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                  )}
                                </motion.button>
                              </div>
                              <AnimatePresence>
                                {confronto && (
                                  <motion.p
                                    initial={{ opacity: 0, y: -4 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                    className={`mt-1 pr-1 text-right text-[11.5px] font-medium ${
                                      confronto.better === true
                                        ? "text-lime-300"
                                        : confronto.better === false
                                          ? "text-white/40"
                                          : "text-white/45"
                                    }`}
                                  >
                                    {confronto.better === true && "↑ "}
                                    {confronto.text}
                                    {confronto.better !== null && " rispetto all'ultima volta"}
                                  </motion.p>
                                )}
                              </AnimatePresence>
                            </div>
                          );
                        })}
                      </div>
                      <button
                        onClick={() => setRows((prev) => ({ ...prev, [item.id]: [...prev[item.id], emptyRow()] }))}
                        className="mt-2 w-full rounded-2xl py-2.5 text-[13px] font-medium text-white/45 transition hover:bg-white/[0.04] hover:text-white/80"
                      >
                        + Aggiungi serie
                      </button>
                    </div>
                  </motion.section>
                );
              })}
            </div>
          )}
        </div>

        {/* Piede: avvio, recupero, fine */}
        <div className="shrink-0 border-t border-white/[0.06] bg-ink-900/50">
          <AnimatePresence mode="wait" initial={false}>
            {phase === "running" && rest ? (
              <motion.div
                key="recupero"
                initial={{ y: 24, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: 24, opacity: 0 }}
                className="px-4 py-3 sm:px-5"
              >
                <div className="flex items-center gap-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] uppercase tracking-wide text-white/40">Recupero</p>
                    <p className="font-mono text-[26px] font-semibold leading-none tabular-nums text-white">
                      {restLabel(remaining)}
                    </p>
                  </div>
                  <button className="btn-ghost h-11 px-3" onClick={() => setRest({ ...rest, endsAt: rest.endsAt - 15000 })}>
                    −15s
                  </button>
                  <button className="btn-ghost h-11 px-3" onClick={() => setRest({ ...rest, endsAt: rest.endsAt + 15000 })}>
                    +15s
                  </button>
                  <button className="btn-primary h-11 px-4" onClick={() => setRest(null)}>
                    Salta
                  </button>
                </div>
                <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-white/[0.08]">
                  <div
                    className="h-full rounded-full bg-lime-400 transition-[width] duration-300"
                    style={{ width: `${Math.min(100, (remaining / rest.total) * 100)}%` }}
                  />
                </div>
              </motion.div>
            ) : phase === "running" ? (
              <motion.div key="corso" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex gap-2 px-4 py-3 sm:px-5">
                <button className="btn-ghost flex-1 justify-center py-3" onClick={onClose} title="L'allenamento continua: lo riapri dalla scheda">
                  Riduci
                </button>
                <button className="btn-primary flex-[2] justify-center whitespace-nowrap px-3 py-3" onClick={finish} disabled={finishing}>
                  {finishing ? "Chiudo…" : "Termina allenamento"}
                </button>
              </motion.div>
            ) : phase === "ready" ? (
              <motion.div key="pronto" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="px-4 py-3 sm:px-5">
                <button className="btn-primary w-full justify-center py-3.5 text-[15px]" onClick={start}>
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                    <path d="M8 5v14l11-7L8 5Z" />
                  </svg>
                  {session?.ended_at ? "Riprendi l'allenamento" : "Avvia allenamento"}
                </button>
              </motion.div>
            ) : phase === "done" ? (
              <motion.div key="fine" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="px-4 py-3 sm:px-5">
                <button className="btn-primary w-full justify-center py-3.5 text-[15px]" onClick={onClose}>
                  Chiudi
                </button>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </Modal>

      {/* Fuori dal pannello: dentro un contenitore animato un elemento fixed
          si posizionerebbe rispetto a lui, non allo schermo. */}
      <AnimatePresence>
        {editing && (
          <ParamsDialog
            key="params"
            title={exerciseName(editing.exercise)}
            subtitle="Scegli se valgono solo per l'allenamento di oggi o anche per le prossime volte."
            initial={targets[editing.id]}
            saving={savingParams}
            error={paramsError}
            onClose={() => setEditing(null)}
            onApplyToday={(v) => {
              changeTargets(editing, v);
              setEditing(null);
            }}
            onSaveToPlan={(v) => saveTargetsToPlan(editing, v)}
          />
        )}
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

function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
      <path d="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75L3 17.25Zm17.7-10.2a1 1 0 0 0 0-1.42l-2.33-2.33a1 1 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.83-1.83Z" />
    </svg>
  );
}

/** Il riepilogo a fine allenamento. */
function Summary({ summary }: { summary: SessionSummary }) {
  const numeri: [string, string][] = [
    ["Durata", summary.duration_seconds !== null ? clock(summary.duration_seconds) : "—"],
    ["Serie", String(summary.sets_count)],
    ["Esercizi", String(summary.exercises_count)],
    ["Kg sollevati", kg(Math.round(summary.volume_kg))],
  ];
  return (
    <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="py-2">
      <div className="flex flex-col items-center text-center">
        <Mascot size={72} mood={summary.records.length ? "goal" : "happy"} />
        <h3 className="mt-3 text-[20px] font-semibold tracking-tight text-white">Allenamento completato</h3>
        <p className="mt-1 text-[13px] text-white/50">
          {summary.sets_count ? "Ecco com'è andata." : "Nessuna serie segnata questa volta."}
        </p>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-2.5">
        {numeri.map(([label, value], i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.05 }}
            className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3.5"
          >
            <p className="text-[11.5px] uppercase tracking-wide text-white/40">{label}</p>
            <p className="mt-1 font-mono text-[22px] font-semibold tabular-nums text-white">{value}</p>
          </motion.div>
        ))}
      </div>
      {summary.records.length > 0 && (
        <div className="mt-4 rounded-2xl border border-lime-400/25 bg-lime-400/[0.07] p-4">
          <p className="text-[13px] font-semibold text-lime-200">
            {summary.records.length === 1 ? "Un nuovo record" : `${summary.records.length} nuovi record`}
          </p>
          <ul className="mt-2 space-y-1.5">
            {summary.records.map((r) => (
              <li key={r.exercise_id} className="flex items-baseline justify-between gap-3 text-[13px]">
                <span className="min-w-0 truncate text-white/80">{r.exercise_name}</span>
                <span className="shrink-0 font-mono tabular-nums text-lime-300">
                  {kg(r.weight_kg)} kg
                  {r.previous_best_kg !== null && (
                    <span className="ml-1.5 text-white/35">prima {kg(r.previous_best_kg)}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </motion.div>
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
