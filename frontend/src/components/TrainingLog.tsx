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
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import { AlternativesDialog } from "@/components/ExercisePicker";
import { ExerciseDetailHost } from "@/components/ExerciseDetail";
import { ExerciseNoteLine, recallNotes, rememberNotes } from "@/components/ExerciseNote";
import {
  QUEUE_EVENT,
  addSet,
  createSession,
  deleteSet,
  finishSession,
  isRetryable,
  newClientId,
  pendingCount,
  pendingEdits,
  pendingFinish,
  pendingSession,
  pendingSets,
  recallLast,
  rememberLast,
  reopenSession,
  updateSet,
  type QueueEvent,
} from "@/lib/offline";
import { primeRestSound, restTimer, useRest, type Rest } from "@/lib/restTimer";

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
      className="group/params flex w-full items-center gap-2 rounded-2xl border border-white/[0.07] bg-white/[0.04] px-3.5 py-2.5 text-left transition hover:border-lime-400/35 hover:bg-lime-400/[0.05] active:bg-lime-400/[0.08]"
      aria-label="Modifica serie, ripetizioni, RIR e recupero"
    >
      {[
        `${value.target_sets} × ${value.target_reps_min}-${value.target_reps_max}`,
        `RIR ${value.target_rir}`,
        restLabel(value.rest_seconds),
      ].map((c, i) => (
        <Fragment key={c}>
          {i > 0 && <span className="text-white/20">·</span>}
          <span className="whitespace-nowrap font-mono text-[13px] font-semibold tabular-nums text-white/85">{c}</span>
        </Fragment>
      ))}
      <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[12.5px] font-semibold text-lime-300">
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
  /** Identificativo dato dal telefono: vale finché la serie è in coda senza rete. */
  clientId?: string;
  /** Salvata sul telefono, non ancora arrivata al server. */
  pending?: boolean;
  /** Numero della serie salvata: dopo un'eliminazione non coincide più con la posizione. */
  num?: number;
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

/** Una serie già segnata: arrivata al server (`setId`) o ancora in coda (`pending`). */
type LoggedSet = Pick<SessionSet, "set_number" | "reps" | "weight_kg" | "rir"> & {
  setId: number | null;
  clientId?: string;
  pending?: boolean;
};

function rowsFor(target: PlanExerciseParams, logged: LoggedSet[]): Row[] {
  const rows: Row[] = logged.map((s) => ({
    key: newKey(),
    setId: s.setId,
    clientId: s.clientId,
    pending: s.pending,
    num: s.set_number,
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

// --- Cosa il telefono ricorda dell'allenamento di oggi ---------------------------------
//
// Chiave: scheda, giorno della scheda e data. Si tiene solo il giorno corrente.

const SWAPS_KEY = "kilo:cambi-allenamento";
const TODAY_KEY = "kilo:allenamento-oggi";
type Swaps = Record<number, PlanExercise["exercise"]>;

function readStore<T>(key: string, chiave: string): T | null {
  try {
    return (JSON.parse(localStorage.getItem(key) ?? "{}") as Record<string, T>)[chiave] ?? null;
  } catch {
    return null;
  }
}

function writeStore<T>(key: string, chiave: string, valore: T | null) {
  try {
    const data = chiave.split(":").pop();
    const tutto = JSON.parse(localStorage.getItem(key) ?? "{}") as Record<string, T>;
    // Gli altri giorni non servono più.
    const tenuti = Object.fromEntries(Object.entries(tutto).filter(([k]) => k.endsWith(`:${data}`) && k !== chiave));
    if (valore !== null) tenuti[chiave] = valore;
    localStorage.setItem(key, JSON.stringify(tenuti));
  } catch {
    /* solo una comodità */
  }
}

/** Gli esercizi cambiati "solo per oggi": riga della scheda -> esercizio scelto. */
function readSwaps(chiave: string): Swaps {
  return readStore<Swaps>(SWAPS_KEY, chiave) ?? {};
}

function writeSwaps(chiave: string, swaps: Swaps) {
  writeStore(SWAPS_KEY, chiave, Object.keys(swaps).length ? swaps : null);
}

/** La sessione di oggi letta l'ultima volta: senza rete non se ne crea una seconda. */
function rememberToday(chiave: string, s: WorkoutSessionLog | null) {
  if (s && s.id > 0) writeStore(TODAY_KEY, chiave, s);
}

function recallToday(chiave: string): WorkoutSessionLog | null {
  return readStore<WorkoutSessionLog>(TODAY_KEY, chiave);
}

/**
 * Le serie della sessione: quelle del server, con le correzioni ancora in coda,
 * più quelle salvate sul telefono e non ancora arrivate. Una serie arrivata ma
 * ancora in coda (risposta persa) compare una volta sola.
 */
function loggedSets(corrente: WorkoutSessionLog | null): (LoggedSet & { exercise_id: number })[] {
  if (!corrente) return [];
  const { updates, deletes } = pendingEdits();
  const dalServer = corrente.sets
    .filter((x) => !deletes.has(x.id))
    .map((x) => {
      const u = updates.get(x.id);
      return {
        exercise_id: x.exercise_id,
        set_number: x.set_number,
        reps: u?.reps ?? x.reps,
        weight_kg: u?.weight_kg ?? x.weight_kg,
        rir: u ? u.rir : x.rir,
        setId: x.id,
        clientId: x.client_id ?? undefined,
        pending: !!u,
      };
    });
  const arrivate = new Set(dalServer.map((x) => x.clientId).filter(Boolean));
  const inAttesa = pendingSets([corrente.id])
    .filter((x) => !arrivate.has(x.client_id))
    .map((x) => ({
      exercise_id: x.exercise_id,
      set_number: x.set_number,
      reps: x.reps,
      weight_kg: x.weight_kg,
      rir: x.rir,
      setId: null,
      clientId: x.client_id,
      pending: true,
    }));
  return [...dalServer, ...inAttesa];
}

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
  // Gli esercizi di oggi: quelli della scheda, con i cambi "solo per oggi".
  const [items, setItems] = useState<PlanExercise[]>(exercises);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [editing, setEditing] = useState<PlanExercise | null>(null);
  const [savingParams, setSavingParams] = useState(false);
  const [paramsError, setParamsError] = useState<string | null>(null);
  const [history, setHistory] = useState<PlanExercise | null>(null);
  const [swapping, setSwapping] = useState<PlanExercise | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);
  // Operazioni salvate sul telefono e non ancora arrivate al server.
  const [inCoda, setInCoda] = useState(() => pendingCount());
  // Terminato senza rete: il riepilogo del server arriva quando torna.
  const [fineInCoda, setFineInCoda] = useState(false);
  const creating = useRef<Promise<WorkoutSessionLog> | null>(null);
  const sessionRef = useRef<WorkoutSessionLog | null>(null);
  sessionRef.current = session;
  const elapsed = useElapsed(phase === "running" ? session?.started_at : null);
  const oggi = useMemo(() => localDate(), []);
  const chiaveGiorno = `${plan.id}:${dayLabel}:${oggi}`;

  // La sessione di oggi (se c'è) e l'ultima volta di ogni esercizio. Senza
  // rete si riparte da quello che il telefono ricorda: la sessione di oggi,
  // le serie in coda, l'ultima volta e le note lette l'ultima volta.
  useEffect(() => {
    let annullato = false;
    (async () => {
      const cambi = readSwaps(chiaveGiorno);
      const lista = exercises.map((e) => (cambi[e.id] ? { ...e, exercise: cambi[e.id] } : e));
      const ids = lista.map((e) => e.exercise.id);
      let corrente: WorkoutSessionLog | null = null;
      let ultime: Record<number, ExerciseSession> = {};
      let note: Record<number, string> = {};
      try {
        corrente = await api.get<WorkoutSessionLog | null>(
          `/workout/sessions/current?profile_id=${profileId}&day_label=${encodeURIComponent(dayLabel)}&plan_id=${plan.id}&today=${oggi}`
        );
        const params = new URLSearchParams({ profile_id: String(profileId) });
        ids.forEach((id) => params.append("exercise_ids", String(id)));
        const perNote = new URLSearchParams(params);
        if (corrente) params.set("exclude_session_id", String(corrente.id));
        ultime = await api.get<Record<number, ExerciseSession>>(`/workout/last-performance?${params}`);
        rememberLast(ultime);
        note = await api.get<Record<number, string>>(`/workout/exercise-notes?${perNote}`).catch(() => recallNotes(ids));
        rememberNotes(note, ids);
        rememberToday(chiaveGiorno, corrente);
      } catch (e) {
        if (annullato) return;
        if (!isRetryable(e)) {
          setError(e instanceof Error ? e.message : "Non riesco a caricare l'allenamento.");
          return;
        }
        corrente = recallToday(chiaveGiorno);
        ultime = recallLast<ExerciseSession>(ids);
        note = recallNotes(ids);
        setError("Sei senza rete: l'allenamento continua, le serie si salvano sul telefono e partono appena torna.");
      }
      if (annullato) return;
      // Avviato senza rete e non ancora arrivato: la sessione provvisoria.
      if (!corrente) corrente = pendingSession(plan.id, dayLabel, oggi);
      const segnate = loggedSets(corrente);
      setItems(lista);
      setSession(corrente);
      setLast(ultime);
      setNotes(note);
      setRows(
        Object.fromEntries(
          lista.map((e) => [
            e.id,
            rowsFor(
              paramsOf(e),
              segnate.filter((s) => s.exercise_id === e.exercise.id).sort((a, b) => a.set_number - b.set_number)
            ),
          ])
        )
      );
      const chiusa = !!corrente?.ended_at || (corrente ? pendingFinish(corrente.id) : false);
      setPhase(corrente?.started_at && !chiusa ? "running" : "ready");
    })();
    return () => {
      annullato = true;
    };
  }, [profileId, plan.id, dayLabel, exercises, oggi, chiaveGiorno]);

  // Quello che era in coda arriva al server: le righe prendono l'id vero.
  useEffect(() => {
    const onQueue = (ev: Event) => {
      const d = (ev as CustomEvent<QueueEvent>).detail;
      if (d.type === "changed") {
        setInCoda(d.pending);
        if (d.pending === 0) {
          setRows((prev) =>
            Object.fromEntries(Object.entries(prev).map(([k, righe]) => [k, righe.map((r) => (r.pending ? { ...r, pending: false } : r))]))
          );
        }
      } else if (d.type === "session") {
        const s = sessionRef.current;
        if (s && s.id === d.tempId) {
          const vera = { ...d.session, ended_at: s.ended_at };
          setSession(vera);
          rememberToday(chiaveGiorno, vera);
          restTimer.rename(d.tempId, d.session.id);
          onSessionChange?.(vera.started_at && !vera.ended_at ? vera : null);
        }
      } else if (d.type === "set") {
        setRows((prev) =>
          Object.fromEntries(
            Object.entries(prev).map(([k, righe]) => [
              k,
              righe.map((r) => (r.clientId === d.clientId ? { ...r, setId: d.set.id, pending: false } : r)),
            ])
          )
        );
      } else if (d.type === "finish") {
        setSummary((prima) => prima ?? d.summary);
      } else if (d.type === "dropped") {
        setError(d.message);
      }
    };
    window.addEventListener(QUEUE_EVENT, onQueue);
    return () => window.removeEventListener(QUEUE_EVENT, onQueue);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chiaveGiorno]);

  // Recupero: condiviso con la pillola della scheda, sopravvive a "Riduci".
  const { rest, remaining } = useRest(phase === "running" ? session?.id : null);

  function update(s: WorkoutSessionLog | null) {
    setSession(s);
    onSessionChange?.(s && s.started_at && !s.ended_at ? s : null);
  }

  /** Avvia l'allenamento: crea la sessione di oggi, o riapre quella chiusa.
   * Senza rete la sessione è provvisoria e parte con la coda. */
  const start = useCallback(async () => {
    setError(null);
    try {
      let s = sessionRef.current;
      if (s && (!s.started_at || s.ended_at)) {
        const riaperta = await reopenSession(s.id);
        s = riaperta.session ?? { ...s, started_at: s.started_at ?? new Date().toISOString(), ended_at: null };
      } else if (!s) {
        if (!creating.current) {
          creating.current = createSession(profileId, {
            day_label: dayLabel,
            workout_plan_id: plan.id,
            date: oggi,
          }).then((r) => r.session);
        }
        s = await creating.current;
      }
      rememberToday(chiaveGiorno, s);
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
  }, [profileId, dayLabel, plan.id, oggi, chiaveGiorno]);

  async function finish() {
    const s = sessionRef.current;
    if (!s) return;
    setFinishing(true);
    try {
      const r = await finishSession(s.id);
      restTimer.clearSession(s.id);
      if (r.summary) {
        setSummary(r.summary);
        update(r.summary.session);
      } else {
        // Senza rete: chiuso sul telefono, il riepilogo del server arriva dopo.
        setFineInCoda(true);
        update({ ...s, ended_at: new Date().toISOString() });
      }
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
    // Prima di ogni attesa: il suono di fine recupero si sblocca solo dentro il tocco.
    primeRestSound();
    const pesi = row.kg ?? hint.kg;
    const ripetizioni = row.reps ?? hint.reps;
    const rir = row.rir ?? hint.rir;
    if (pesi === null || !ripetizioni) return;
    patchRow(item.id, row.key, { busy: true });
    setError(null);
    try {
      const corpo = { weight_kg: pesi, reps: ripetizioni, rir };
      const salvata = { busy: false, kg: pesi, reps: ripetizioni, rir, saved: { kg: pesi, reps: ripetizioni, rir } };
      const ref = row.setId ?? (row.saved ? row.clientId : undefined);
      if (ref !== undefined) {
        // Correzione di una serie già segnata (anche se ancora in coda).
        const { queued } = await updateSet(ref, corpo);
        patchRow(item.id, row.key, { ...salvata, pending: row.pending || queued });
      } else {
        const s = sessionRef.current?.started_at && !sessionRef.current.ended_at ? sessionRef.current : await start();
        if (!s) throw new Error("allenamento non avviato");
        // La posizione, se libera: eliminata la serie 2 di 3, la nuova terza
        // non deve prendere il numero 3 che ha già l'ultima.
        const usati = (rows[item.id] ?? []).filter((r) => r.saved && r.num).map((r) => r.num!);
        const numero = usati.includes(index + 1) ? Math.max(...usati) + 1 : index + 1;
        const clientId = newClientId();
        const { set, queued } = await addSet(s.id, {
          ...corpo,
          exercise_id: item.exercise.id,
          set_number: numero,
          client_id: clientId,
        });
        patchRow(item.id, row.key, {
          ...salvata,
          setId: set?.id ?? null,
          clientId,
          pending: queued,
          num: set?.set_number ?? numero,
        });
        const prossima = nextStep(item, index, pesi, ripetizioni);
        if (prossima) restTimer.start({ sessionId: s.id, total: targets[item.id].rest_seconds, ...prossima });
      }
    } catch (e) {
      patchRow(item.id, row.key, { busy: false });
      setError(e instanceof Error ? `Serie non salvata: ${e.message}` : "Serie non salvata.");
    }
  }

  /** Cosa viene dopo la serie appena salvata; niente dopo l'ultima dell'allenamento. */
  function nextStep(item: PlanExercise, index: number, pesi: number, ripetizioni: number) {
    const serie = rows[item.id]?.length ?? 0;
    if (index + 1 < serie) {
      return { next: `Poi la serie ${index + 2}`, detail: `${kg(pesi)} kg × ${ripetizioni} · ${exerciseName(item.exercise)}` };
    }
    const n = items.findIndex((e) => e.id === item.id);
    const dopo = items[n + 1];
    return dopo
      ? { next: `Poi: ${exerciseName(dopo.exercise)}`, detail: `Esercizio ${n + 2} di ${items.length}` }
      : null;
  }

  async function deleteRow(item: PlanExercise, row: Row) {
    if (!row.confirmDelete) {
      patchRow(item.id, row.key, { confirmDelete: true });
      setTimeout(() => patchRow(item.id, row.key, { confirmDelete: false }), 3000);
      return;
    }
    const ref = row.setId ?? (row.saved ? row.clientId : undefined);
    if (ref !== undefined) {
      patchRow(item.id, row.key, { busy: true });
      try {
        // Senza rete l'eliminazione parte con la coda; una serie mai partita
        // si toglie solo dal telefono.
        await deleteSet(ref);
      } catch (e) {
        patchRow(item.id, row.key, { busy: false });
        setError(e instanceof Error ? `Serie non eliminata: ${e.message}` : "Serie non eliminata.");
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
      while (righe.length > v.target_sets && righe[righe.length - 1].saved === null) righe = righe.slice(0, -1);
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
  const fatte = tutte.filter((r) => r.saved).length;
  const stimaMinuti = Math.round(
    items.reduce((t, e) => t + targets[e.id].target_sets * (targets[e.id].rest_seconds + 45), 0) / 60
  );
  // Il riscaldamento si propone sul primo multi-articolare della seduta.
  const primoMulti = items.find((e) => e.exercise.is_compound)?.id;
  const cambiOggi = readSwaps(chiaveGiorno);

  /** Cambio dell'esercizio durante l'allenamento (prima di averne segnato le serie). */
  function cambiaEsercizio(item: PlanExercise, nuovo: PlanExercise["exercise"], ancheScheda: boolean) {
    const cambi = readSwaps(chiaveGiorno);
    const originale = exercises.find((e) => e.id === item.id)?.exercise;
    if (ancheScheda || nuovo.id === originale?.id) delete cambi[item.id];
    else cambi[item.id] = nuovo;
    writeSwaps(chiaveGiorno, cambi);
    setItems((prev) => prev.map((e) => (e.id === item.id ? { ...e, exercise: nuovo } : e)));
    setRows((prev) => ({ ...prev, [item.id]: rowsFor(targets[item.id], []) }));
    // L'ultima volta e la nota del nuovo esercizio.
    const params = new URLSearchParams({ profile_id: String(profileId), exercise_ids: String(nuovo.id) });
    const s = sessionRef.current;
    if (s && s.id > 0) params.set("exclude_session_id", String(s.id));
    api
      .get<Record<number, ExerciseSession>>(`/workout/last-performance?${params}`)
      .then((u) => {
        rememberLast(u);
        setLast((prev) => ({ ...prev, ...u }));
      })
      .catch(() => setLast((prev) => ({ ...prev, ...recallLast<ExerciseSession>([nuovo.id]) })));
    api
      .get<Record<number, string>>(`/workout/exercise-notes?profile_id=${profileId}&exercise_ids=${nuovo.id}`)
      .then((n) => setNotes((prev) => ({ ...prev, ...n })))
      .catch(() => setNotes((prev) => ({ ...prev, ...recallNotes([nuovo.id]) })));
  }

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
        <div
          className={`min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-4 sm:px-5 ${
            phase === "running" && rest ? "pb-24" : "pb-4"
          }`}
        >
          {error && (
            <div className="mb-3">
              <Notice>{error}</Notice>
            </div>
          )}
          {inCoda > 0 && phase !== "loading" && (
            <div className="mb-3 flex items-start gap-2 rounded-xl border border-amber-300/25 bg-amber-300/[0.07] px-3 py-2 text-[12.5px] leading-snug text-amber-100/90">
              <svg viewBox="0 0 24 24" className="mt-[1px] h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M3 3l18 18M8.5 8.6A5 5 0 0 0 7 18h10.5M20.3 16.4A4 4 0 0 0 17 10h-.5A6 6 0 0 0 11 5.1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>
                {inCoda === 1 ? "1 modifica salvata" : `${inCoda} modifiche salvate`} sul telefono: le invio appena torna la rete.
              </span>
            </div>
          )}
          {phase === "loading" && !error && <Spinner label="Preparo l'allenamento…" />}

          {phase === "done" && summary && <Summary summary={summary} />}
          {phase === "done" && !summary && fineInCoda && <OfflineSummary rows={tutte} />}

          {(phase === "ready" || phase === "running") && (
            <div className="space-y-4">
              {items.map((item, n) => {
                const t = targets[item.id];
                const volta = last[item.exercise.id];
                const cambiati = !sameParams(t, base[item.id]);
                const righe = rows[item.id] ?? [];
                const suggerimenti = hintsFor(righe, t, volta);
                const iniziato = righe.some((r) => r.saved);
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
                        <div className="flex items-start gap-2">
                          <h3 className="min-w-0 flex-1 text-[16px] font-semibold leading-snug text-white">
                            {exerciseName(item.exercise)}
                            {cambiOggi[item.id] && (
                              <span className="ml-1.5 align-middle text-[11px] font-medium text-iris-200/80">· solo oggi</span>
                            )}
                          </h3>
                          {/* Macchina occupata: si cambia prima di cominciare l'esercizio. */}
                          {!iniziato && (
                            <button
                              onClick={() => setSwapping(item)}
                              aria-label={`Cambia ${exerciseName(item.exercise)}`}
                              className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 text-[12px] font-medium text-white/60 transition hover:border-lime-400/30 hover:text-lime-200"
                            >
                              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                                <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7Zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4Z" />
                              </svg>
                              Cambia
                            </button>
                          )}
                        </div>
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
                        <div className="mt-1.5">
                          <ExerciseNoteLine
                            exerciseId={item.exercise.id}
                            profileId={profileId}
                            note={notes[item.exercise.id]}
                            compact
                            onSaved={(id, testo) => {
                              setNotes((prev) => {
                                const nuove = { ...prev };
                                if (testo) nuove[id] = testo;
                                else delete nuove[id];
                                rememberNotes(nuove, [id]);
                                return nuove;
                              });
                            }}
                          />
                        </div>
                      </div>
                    </div>

                    {/* I parametri: la stessa riga e la stessa finestra della scheda */}
                    <div className="mt-3">
                      <ParamsChips value={t} changed={cambiati} onEdit={() => setEditing(item)} />
                    </div>

                    {item.id === primoMulti && !iniziato && (
                      <WarmupLine workKg={righe[0]?.kg ?? suggerimenti[0]?.kg ?? null} />
                    )}

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
                                  aria-label={
                                    salvata && !modificata
                                      ? row.pending
                                        ? `Serie ${i + 1} salvata sul telefono, in attesa di rete`
                                        : `Serie ${i + 1} salvata`
                                      : `Salva la serie ${i + 1}`
                                  }
                                  className={`grid h-11 w-[46px] place-items-center rounded-xl border transition ${
                                    salvata && !modificata && row.pending
                                      ? "border-amber-300/60 bg-amber-300/80 text-ink-900"
                                      : salvata && !modificata
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
                                {row.pending && salvata && !modificata && (
                                  <motion.p
                                    key="attesa"
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    exit={{ opacity: 0 }}
                                    className="mt-1 pr-1 text-right text-[11px] text-amber-200/75"
                                  >
                                    salvata sul telefono · parte appena torna la rete
                                  </motion.p>
                                )}
                                {confronto && !row.pending && (
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

        {/* Piede: avvio, fine. Il recupero galleggia sopra, senza spostare niente. */}
        <div className="relative shrink-0 border-t border-white/[0.06] bg-ink-900/50">
          <AnimatePresence>
            {phase === "running" && rest && (
              <RestCapsule key="recupero" rest={rest} remaining={remaining} />
            )}
          </AnimatePresence>
          <AnimatePresence mode="wait" initial={false}>
            {phase === "running" ? (
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
        {swapping && (
          <AlternativesDialog
            key={`cambia-${swapping.id}`}
            item={swapping}
            profileId={profileId}
            inSession={{ onPick: (nuovo, ancheScheda) => cambiaEsercizio(swapping, nuovo, ancheScheda) }}
            onClose={() => setSwapping(null)}
            onSwapped={onPlanUpdated}
            onOpenDetail={setDetailId}
          />
        )}
      </AnimatePresence>
      <ExerciseDetailHost exerciseId={detailId} profileId={profileId} onClose={() => setDetailId(null)} />
    </>
  );
}

// --- Riscaldamento ---------------------------------------------------------------
//
// `advanced_techniques_efficiency.md` (Iversen 2021): riscaldamento specifico
// dell'esercizio, non generico. Le fonti non danno percentuali: le due serie
// di avvicinamento (metà del carico × 8, tre quarti × 4) sono una proposta
// operativa di Kilo, dichiarata come tale. Pesi arrotondati a 2,5 kg.

export function warmupSets(workKg: number | null): { kg: number; reps: number }[] | null {
  if (workKg === null || workKg < 10) return null;
  const arrotonda = (x: number) => Math.round(x / 2.5) * 2.5;
  const serie = [
    { kg: arrotonda(workKg * 0.5), reps: 8 },
    { kg: arrotonda(workKg * 0.75), reps: 4 },
  ];
  return serie.filter((x, i) => x.kg > 0 && x.kg < workKg && (i === 0 || x.kg > serie[i - 1].kg));
}

function WarmupLine({ workKg }: { workKg: number | null }) {
  const serie = warmupSets(workKg);
  return (
    <div className="mt-3 rounded-xl border border-iris-400/20 bg-iris-400/[0.06] px-3 py-2 text-[12.5px] leading-snug text-white/70">
      <span className="font-semibold text-iris-100">Riscaldamento</span>{" "}
      <span className="font-mono tabular-nums">
        {serie?.length
          ? serie.map((x) => `${kg(x.kg)} kg × ${x.reps}`).join(" · ")
          : "due serie leggere: metà del carico × 8, poi tre quarti × 4"}
      </span>
      <span className="mt-0.5 block text-[11px] text-white/40">
        Specifico per questo esercizio, prima delle serie di lavoro. Non si segna e non conta nel volume. Proposta di Kilo.
      </span>
    </div>
  );
}

/** Allenamento terminato senza rete: quello che si sa sul telefono. */
function OfflineSummary({ rows }: { rows: Row[] }) {
  const fatte = rows.filter((r) => r.saved);
  const volume = fatte.reduce((t, r) => t + r.saved!.kg * r.saved!.reps, 0);
  return (
    <div className="space-y-2 py-4 text-center">
      <div className="flex justify-center">
        <Mascot size={56} mood="happy" />
      </div>
      <p className="text-[17px] font-semibold text-white">Allenamento terminato</p>
      <p className="font-mono text-[13px] tabular-nums text-white/65">
        {fatte.length} serie · {kg(Math.round(volume))} kg sollevati
      </p>
      <p className="mx-auto max-w-sm text-[12.5px] leading-snug text-amber-100/85">
        Sei senza rete: è tutto salvato sul telefono. Lo invio appena torna la connessione, con l&apos;ora vera
        di fine; durata e record compaiono qui allora.
      </p>
    </div>
  );
}

// --- Recupero ---------------------------------------------------------------------

/** Anello del recupero: si svuota man mano che il tempo passa. */
export function RestRing({
  fraction,
  size,
  stroke,
  children,
}: {
  fraction: number;
  size: number;
  stroke: number;
  children?: ReactNode;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <span
      className="relative grid shrink-0 place-items-center rounded-full shadow-[0_0_18px_-6px_rgba(174,212,74,0.9)]"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#aed44a"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(1, fraction)))}
          className="transition-[stroke-dashoffset] duration-300 ease-linear"
        />
      </svg>
      <span className="relative">{children}</span>
    </span>
  );
}

export function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={3} aria-hidden>
      <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** La capsula sopra i pulsanti: conto alla rovescia, poi "tocca a te". */
function RestCapsule({ rest, remaining }: { rest: Rest; remaining: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 16, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 420, damping: 32 }}
      className="absolute inset-x-3 bottom-full z-10 mb-3 sm:inset-x-4"
      role="timer"
      aria-live="polite"
    >
      <motion.div
        layout
        className={`flex items-center gap-3 rounded-full border py-2 pl-2 pr-2 transition-colors duration-300 ${
          rest.done
            ? "border-lime-300 bg-lime-400 text-ink-900 shadow-[0_0_34px_-6px_rgba(174,212,74,0.9)]"
            : "border-lime-400/60 bg-[#101214] shadow-[0_0_24px_-8px_rgba(174,212,74,0.7),0_12px_40px_-12px_rgba(0,0,0,0.9)]"
        }`}
      >
        {rest.done ? (
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink-900/15">
            <CheckIcon />
          </span>
        ) : (
          <RestRing fraction={remaining / rest.total} size={44} stroke={4}>
            <span className="block h-1.5 w-1.5 rounded-full bg-lime-400" />
          </RestRing>
        )}
        <div className="min-w-0 flex-1">
          {rest.done ? (
            <>
              <p className="truncate text-[14px] font-semibold">{rest.next.replace(/^Poi:? ?/, "Tocca a te: ")}</p>
              <p className="truncate text-[11.5px] text-ink-900/70">{rest.detail}</p>
            </>
          ) : (
            <>
              <p className="font-mono text-[22px] font-semibold leading-none tabular-nums text-white">{clock(remaining)}</p>
              <p className="mt-0.5 truncate text-[11.5px] text-white/50">{rest.next.toLowerCase()}</p>
            </>
          )}
        </div>
        {rest.done ? (
          <button
            onClick={() => restTimer.clear()}
            className="shrink-0 rounded-full bg-ink-900 px-4 py-2.5 text-[13px] font-semibold text-lime-200"
          >
            Ok
          </button>
        ) : (
          <>
            <button
              onClick={() => restTimer.shift(15)}
              aria-label="Aggiungi 15 secondi"
              className="grid h-10 w-12 shrink-0 place-items-center rounded-full bg-white/[0.08] font-mono text-[12.5px] text-white/80 transition hover:bg-white/[0.14]"
            >
              +15
            </button>
            <button
              onClick={() => restTimer.clear()}
              className="grid h-10 shrink-0 place-items-center rounded-full bg-lime-400 px-4 text-[13px] font-semibold text-ink-900 transition hover:bg-lime-300"
            >
              Salta
            </button>
          </>
        )}
      </motion.div>
    </motion.div>
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
type ManualRow = { key: string; kg: number | null; reps: number | null; rir: number | null };

function manualRow(kgValue: number | null = null, reps: number | null = null, rir: number | null = null): ManualRow {
  return { key: Math.random().toString(36).slice(2), kg: kgValue, reps, rir };
}

const RIR_VALUES = [0, 1, 2, 3, 4, 5];

export function LoadHistoryDialog({
  profileId,
  exerciseId,
  planId,
  dayLabel,
  editSetId,
  onClose,
  onChanged,
}: {
  profileId: number;
  exerciseId: number;
  /** Scheda e giorno da cui si arriva: le serie segnate a mano vanno lì. */
  planId?: number;
  dayLabel?: string;
  /** Serie da aprire già in modifica (toccata nella scheda). */
  editSetId?: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const [data, setData] = useState<ExerciseHistory | null>(null);
  // Carichi segnati fuori dall'allenamento.
  const [adding, setAdding] = useState(false);
  const [date, setDate] = useState(() => localDate());
  const [rows, setRows] = useState<ManualRow[]>([]);
  const [savingManual, setSavingManual] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const oggi = localDate();
  const ieri = localDate(new Date(Date.now() - 86_400_000));
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<SessionSet | null>(null);
  const [draft, setDraft] = useState<{ kg: number | null; reps: number | null; rir: number | null }>({
    kg: null,
    reps: null,
    rir: null,
  });
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  // La serie toccata nella scheda si apre in modifica una volta sola, al primo caricamento.
  const daAprire = useRef(editSetId);

  const load = useCallback(async () => {
    try {
      const storico = await api.get<ExerciseHistory>(`/workout/exercises/${exerciseId}/history?profile_id=${profileId}`);
      setData(storico);
      const id = daAprire.current;
      if (id !== undefined) {
        daAprire.current = undefined;
        const serie = storico.sessions.flatMap((x) => x.sets).find((x) => x.id === id);
        if (serie) {
          setEditing(serie);
          setDraft({ kg: serie.weight_kg, reps: serie.reps, rir: serie.rir ?? null });
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non riesco a caricare lo storico.");
    }
  }, [exerciseId, profileId]);

  useEffect(() => {
    load();
  }, [load]);

  function startEdit(serie: SessionSet) {
    setEditing(serie);
    setDraft({ kg: serie.weight_kg, reps: serie.reps, rir: serie.rir ?? null });
    setEditError(null);
  }

  async function save() {
    if (!editing || draft.kg === null || !draft.reps) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      await api.patch(`/workout/sets/${editing.id}`, { weight_kg: draft.kg, reps: draft.reps, rir: draft.rir });
      setEditing(null);
      await load();
      onChanged?.();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Non sono riuscito a salvare la serie.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function remove(s: SessionSet) {
    setSavingEdit(true);
    setEditError(null);
    try {
      await api.del(`/workout/sets/${s.id}`);
      setEditing(null);
      await load();
      onChanged?.();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Non sono riuscito a eliminare la serie.");
    } finally {
      setSavingEdit(false);
    }
  }

  function openManual() {
    // Si parte dalle serie dell'ultima volta: di solito si cambia poco.
    const ultima = data?.sessions[0]?.sets ?? [];
    setRows(ultima.length ? ultima.map((s) => manualRow(s.weight_kg, s.reps, s.rir ?? null)) : [manualRow()]);
    setDate(oggi);
    setManualError(null);
    setAdding(true);
  }

  function patchManual(key: string, change: Partial<ManualRow>) {
    setRows((r) => r.map((x) => (x.key === key ? { ...x, ...change } : x)));
  }

  const manualOk = rows.length > 0 && rows.every((r) => r.kg !== null && !!r.reps) && !!date && date <= oggi;

  async function saveManual() {
    if (!manualOk) return;
    setSavingManual(true);
    setManualError(null);
    try {
      setData(
        await api.post<ExerciseHistory>(`/workout/exercises/${exerciseId}/manual-sets?profile_id=${profileId}`, {
          date,
          workout_plan_id: planId ?? null,
          day_label: dayLabel ?? null,
          sets: rows.map((r) => ({ weight_kg: r.kg, reps: r.reps, rir: r.rir })),
        })
      );
      setAdding(false);
      onChanged?.();
    } catch (e) {
      setManualError(e instanceof Error ? e.message : "Non sono riuscito a salvare le serie.");
    } finally {
      setSavingManual(false);
    }
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
        {data && !adding && (
          <button
            onClick={openManual}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-lime-400/40 bg-lime-400/[0.1] py-2.5 text-[13px] font-semibold text-lime-200 transition hover:bg-lime-400/[0.16]"
          >
            <span className="grid h-5 w-5 place-items-center rounded-full bg-lime-400 text-ink-900">
              <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={3.2}>
                <path d="M12 5v14M5 12h14" strokeLinecap="round" />
              </svg>
            </span>
            Segna carichi fuori dall&apos;allenamento
          </button>
        )}
        <AnimatePresence initial={false}>
          {adding && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="space-y-3 rounded-xl border border-lime-400/30 bg-lime-400/[0.05] p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="mr-auto text-[13px] font-semibold text-white">Nuove serie</p>
                  {[
                    [oggi, "Oggi"],
                    [ieri, "Ieri"],
                  ].map(([valore, etichetta]) => (
                    <button
                      key={valore}
                      onClick={() => setDate(valore)}
                      className={`rounded-full border px-3 py-1 text-[12px] font-medium transition ${
                        date === valore
                          ? "border-lime-400/60 bg-lime-400 text-ink-900"
                          : "border-white/15 text-white/60 hover:text-white"
                      }`}
                    >
                      {etichetta}
                    </button>
                  ))}
                  <input
                    type="date"
                    value={date}
                    max={oggi}
                    onChange={(e) => setDate(e.target.value)}
                    aria-label="Giorno dell'allenamento"
                    className="input h-8 w-[140px] px-2 py-0 text-[12.5px]"
                  />
                </div>
                <div className="space-y-1.5">
                  {rows.map((r, i) => (
                    <div key={r.key} className="grid grid-cols-[22px_1fr_1fr_54px_32px] items-center gap-1.5">
                      <span className="text-center font-mono text-[12px] text-white/45">{i + 1}</span>
                      <NumberField
                        value={r.kg}
                        onChange={(v) => patchManual(r.key, { kg: v })}
                        step={2.5}
                        decimals={2}
                        min={0}
                        max={1000}
                        suffix="kg"
                        size="sm"
                        steppers="sm"
                        placeholder="kg"
                        ariaLabel={`Carico serie ${i + 1}`}
                      />
                      <NumberField
                        value={r.reps}
                        onChange={(v) => patchManual(r.key, { reps: v })}
                        min={1}
                        max={100}
                        suffix="rip"
                        size="sm"
                        steppers="sm"
                        placeholder="rip"
                        ariaLabel={`Ripetizioni serie ${i + 1}`}
                      />
                      <select
                        value={r.rir ?? ""}
                        onChange={(e) => patchManual(r.key, { rir: e.target.value === "" ? null : Number(e.target.value) })}
                        aria-label={`RIR serie ${i + 1}`}
                        className="h-9 rounded-lg border border-white/10 bg-black/30 px-1 text-center font-mono text-[12.5px] text-white outline-none focus:border-lime-400/50"
                      >
                        <option value="">RIR</option>
                        {RIR_VALUES.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => setRows((x) => x.filter((y) => y.key !== r.key))}
                        disabled={rows.length === 1}
                        aria-label={`Togli la serie ${i + 1}`}
                        className="grid h-9 place-items-center rounded-lg text-white/40 transition hover:text-rose-200 disabled:opacity-20"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => {
                    const ultima = rows[rows.length - 1];
                    // Come carico e ripetizioni, anche il RIR riparte da quello della serie prima.
                    setRows((x) => [...x, manualRow(ultima?.kg ?? null, ultima?.reps ?? null, ultima?.rir ?? null)]);
                  }}
                  disabled={rows.length >= 12}
                  className="w-full rounded-lg py-1.5 text-[12.5px] font-medium text-white/50 transition hover:text-white/85"
                >
                  + Aggiungi serie
                </button>
                {manualError && <Notice>{manualError}</Notice>}
                <div className="flex gap-2">
                  <button className="btn-ghost flex-1 justify-center py-2 text-[12.5px]" onClick={() => setAdding(false)}>
                    Annulla
                  </button>
                  <button
                    className="btn-primary flex-[1.6] justify-center py-2 text-[12.5px]"
                    disabled={!manualOk || savingManual}
                    onClick={saveManual}
                  >
                    {savingManual ? "Salvo…" : `Salva ${rows.length === 1 ? "la serie" : `${rows.length} serie`}`}
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {!data && !error && <Spinner label="Carico lo storico…" />}
        {data && data.sessions.length === 0 && (
          <Empty title="Ancora nessuna serie" hint="Le serie segnate durante l'allenamento, o qui sopra, compaiono qui sessione per sessione." />
        )}
        {data?.sessions.map((s) => (
          <div key={s.session_id} className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2.5">
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <p className="text-[13px] font-medium text-white/85">
                {shortDate(s.date)}
                {s.day_label && (
                  <span className="ml-1.5 text-white/35">
                    · {s.day_label.length <= 2 ? `giorno ${s.day_label}` : s.day_label}
                  </span>
                )}
              </p>
              <p className="font-mono text-[11.5px] tabular-nums text-white/40">
                max {kg(s.top_weight_kg)} kg · 1RM ~{kg(Math.round(s.best_e1rm))}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {s.sets.map((set) =>
                editing?.id === set.id ? (
                  <div key={set.id} className="w-full space-y-2 rounded-lg border border-lime-400/30 bg-black/25 p-2">
                    <p className="text-[11.5px] text-white/45">Serie {set.set_number}</p>
                    <div className="grid grid-cols-[1fr_1fr_58px] items-center gap-1.5">
                      <NumberField
                        value={draft.kg}
                        onChange={(v) => setDraft((d) => ({ ...d, kg: v }))}
                        step={2.5}
                        decimals={2}
                        min={0}
                        max={1000}
                        suffix="kg"
                        size="sm"
                        steppers="sm"
                        ariaLabel="Carico"
                      />
                      <NumberField
                        value={draft.reps}
                        onChange={(v) => setDraft((d) => ({ ...d, reps: v }))}
                        min={1}
                        max={100}
                        suffix="rip"
                        size="sm"
                        steppers="sm"
                        ariaLabel="Ripetizioni"
                        onEnter={save}
                      />
                      <select
                        value={draft.rir ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, rir: e.target.value === "" ? null : Number(e.target.value) }))}
                        aria-label="RIR"
                        className="h-9 rounded-lg border border-white/10 bg-black/30 px-1 text-center font-mono text-[12.5px] text-white outline-none focus:border-lime-400/50"
                      >
                        <option value="">RIR</option>
                        {RIR_VALUES.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </div>
                    {editError && <Notice>{editError}</Notice>}
                    <div className="flex gap-1.5">
                      <button
                        className="btn-ghost h-9 px-3 text-[12px] text-rose-200"
                        onClick={() => remove(set)}
                        disabled={savingEdit}
                      >
                        Elimina
                      </button>
                      <button className="btn-ghost ml-auto h-9 px-3 text-[12px]" onClick={() => setEditing(null)} disabled={savingEdit}>
                        Annulla
                      </button>
                      <button
                        className="btn-primary h-9 px-3 text-[12px]"
                        onClick={save}
                        disabled={savingEdit || draft.kg === null || !draft.reps}
                      >
                        {savingEdit ? "Salvo…" : "Salva"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    key={set.id}
                    onClick={() => startEdit(set)}
                    aria-label={`Modifica la serie ${set.set_number}: ${kg(set.weight_kg)} kg per ${set.reps}`}
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
