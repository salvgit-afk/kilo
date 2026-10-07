"use client";

/**
 * Allenamento senza rete: quello che non arriva al server resta sul telefono.
 *
 * In palestra (spesso in un seminterrato) la rete va e viene. Prima una serie
 * salvata senza connessione falliva con "Serie non salvata"; ora finisce in una
 * coda in `localStorage` e parte appena la rete torna, nell'ordine in cui è
 * stata fatta (prima la sessione, poi le sue serie, poi la fine).
 *
 * Tre regole tengono i dati al sicuro:
 *
 * - **niente doppioni**: sessioni e serie create qui hanno un `client_id`
 *   generato sul telefono. Se la risposta si perde e la richiesta parte di
 *   nuovo, il server riconosce l'identificativo e restituisce quella già
 *   salvata;
 * - **niente perdite**: un'operazione esce dalla coda solo quando il server
 *   l'ha confermata, o l'ha rifiutata per sempre (4xx: per esempio una sessione
 *   cancellata nel frattempo). Gli errori di rete e il server che si sta
 *   svegliando (502-504) la lasciano in coda;
 * - **gli orari veri**: avvio e fine si mandano con l'ora del telefono, non con
 *   quella del ritorno della rete.
 *
 * Chi usa la coda ascolta `QUEUE_EVENT` per sapere quando un elemento in
 * attesa è arrivato (e con quale id) o è stato scartato.
 */

import {
  ApiError,
  api,
  session,
  type SessionSet,
  type SessionSummary,
  type WorkoutSessionLog,
} from "@/lib/api";

const KEY = "kilo:coda-allenamento";
export const QUEUE_EVENT = "kilo:coda";
// Oltre questo tempo una richiesta con segnale debole si considera persa e
// va in coda: meglio un "in attesa" subito che un pulsante bloccato un minuto.
const TIMEOUT_MS = 10_000;
const RETRY_MS = 20_000;

export type SessionBody = {
  day_label: string;
  workout_plan_id: number;
  date: string;
  start: true;
  started_at: string;
  client_id: string;
};
export type SetBody = {
  exercise_id: number;
  set_number: number;
  reps: number;
  weight_kg: number;
  rir: number | null;
  client_id: string;
};
type SetChange = { weight_kg: number; reps: number; rir: number | null };

/**
 * `ref` di una serie: l'id del server o, finché non è arrivata, il `client_id`.
 * `profileId`: il profilo che l'ha fatta. Se sullo stesso telefono entra un
 * altro account, le sue operazioni aspettano senza essere scartate né mandate
 * con l'account sbagliato.
 */
type Op = { id: string; profileId: number } & (
  | { kind: "session"; tempId: number; body: SessionBody }
  | { kind: "set"; sessionId: number; body: SetBody }
  | { kind: "set-update"; ref: number | string; body: SetChange }
  | { kind: "set-delete"; ref: number | string }
  | { kind: "reopen"; sessionId: number }
  | { kind: "finish"; sessionId: number; body: { ended_at: string } }
);
type NewOp = Op extends infer T ? (T extends Op ? Omit<T, "id" | "profileId"> : never) : never;

// Il profilo che sta usando l'app: si mandano solo le sue operazioni.
let activeProfile: number | null = null;

function mine(s: State): Op[] {
  return s.ops.filter((o) => o.profileId === activeProfile);
}

type State = {
  ops: Op[];
  /** id provvisorio (negativo) della sessione -> id del server */
  sessions: Record<string, number>;
  /** client_id della serie -> id del server */
  sets: Record<string, number>;
};

export type QueueEvent =
  | { type: "session"; tempId: number; session: WorkoutSessionLog }
  | { type: "set"; clientId: string; set: SessionSet }
  | { type: "finish"; sessionId: number; summary: SessionSummary }
  | { type: "dropped"; message: string }
  | { type: "changed"; pending: number };

// --- Archivio -------------------------------------------------------------------------

function load(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const s = JSON.parse(raw) as State;
      return { ops: s.ops ?? [], sessions: s.sessions ?? {}, sets: s.sets ?? {} };
    }
  } catch {
    /* archiviazione non leggibile: si riparte vuoti */
  }
  return { ops: [], sessions: {}, sets: {} };
}

function save(s: State) {
  // Le corrispondenze servono solo finché c'è qualcosa in coda che le usa.
  const stato = s.ops.length ? s : { ops: [], sessions: {}, sets: {} };
  try {
    localStorage.setItem(KEY, JSON.stringify(stato));
  } catch {
    /* archiviazione piena o negata: la coda vale finché la pagina è aperta */
  }
  emit({ type: "changed", pending: mine(stato).length });
}

function emit(detail: QueueEvent) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(QUEUE_EVENT, { detail }));
}

export function newClientId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 14);
}

let opSeq = 0;
const opId = () => `${Date.now().toString(36)}-${++opSeq}`;

export function pendingCount(): number {
  return mine(load()).length;
}

// --- Errori: di rete (si riprova) o definitivi (si scarta) ------------------------------

class Timeout extends Error {}

function withTimeout<T>(p: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Timeout("tempo scaduto")), TIMEOUT_MS);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      }
    );
  });
}

/** Rete assente, segnale perso o server che si sta svegliando: si riprova. */
export function isRetryable(e: unknown): boolean {
  if (e instanceof ApiError) return [408, 429, 500, 502, 503, 504].includes(e.status);
  return true; // TypeError "Failed to fetch", timeout
}

// --- Esecuzione delle operazioni ---------------------------------------------------------

function realSession(s: State, id: number): number | null {
  return id > 0 ? id : (s.sessions[String(id)] ?? null);
}

function realSet(s: State, ref: number | string): number | null {
  return typeof ref === "number" ? ref : (s.sets[ref] ?? null);
}

/** Esegue un'operazione. `null` se dipende da qualcosa che non c'è più: va scartata. */
async function run(op: Op, s: State): Promise<QueueEvent | null | "ok"> {
  switch (op.kind) {
    case "session": {
      const session = await withTimeout(
        api.post<WorkoutSessionLog>(`/workout/sessions?profile_id=${op.profileId}`, op.body)
      );
      s.sessions[String(op.tempId)] = session.id;
      return { type: "session", tempId: op.tempId, session };
    }
    case "set": {
      const sessione = realSession(s, op.sessionId);
      if (sessione === null) return null;
      const set = await withTimeout(api.post<SessionSet>(`/workout/sessions/${sessione}/sets`, op.body));
      s.sets[op.body.client_id] = set.id;
      return { type: "set", clientId: op.body.client_id, set };
    }
    case "set-update": {
      const id = realSet(s, op.ref);
      if (id === null) return null;
      await withTimeout(api.patch(`/workout/sets/${id}`, op.body));
      return "ok";
    }
    case "set-delete": {
      const id = realSet(s, op.ref);
      if (id === null) return "ok"; // mai arrivata: non c'è niente da togliere
      try {
        await withTimeout(api.del(`/workout/sets/${id}`));
      } catch (e) {
        // Già tolta (la risposta precedente si era persa): va bene così.
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
      return "ok";
    }
    case "reopen": {
      const sessione = realSession(s, op.sessionId);
      if (sessione === null) return null;
      await withTimeout(api.post(`/workout/sessions/${sessione}/start`));
      return "ok";
    }
    case "finish": {
      const sessione = realSession(s, op.sessionId);
      if (sessione === null) return null;
      const summary = await withTimeout(
        api.post<SessionSummary>(`/workout/sessions/${sessione}/finish`, op.body)
      );
      return { type: "finish", sessionId: op.sessionId, summary };
    }
  }
}

let flushing: Promise<void> | null = null;
let inFlight: string | null = null;

/** Manda quello che è in coda, in ordine; si ferma al primo errore di rete. */
export function flush(): Promise<void> {
  if (flushing) return flushing;
  // Senza accesso valido un invio risponderebbe 401, e `api` ricarica la
  // pagina: la coda aspetta il prossimo accesso.
  if (!session.get()) return Promise.resolve();
  flushing = (async () => {
    try {
      for (;;) {
        const stato = load();
        const op = mine(stato)[0];
        if (!op) return;
        inFlight = op.id;
        let esito: QueueEvent | null | "ok";
        try {
          esito = await run(op, stato);
        } catch (e) {
          if (isRetryable(e)) return; // si riprova più tardi
          esito = null;
          emit({
            type: "dropped",
            message:
              e instanceof Error && e.message
                ? `Un dato dell'allenamento non è stato accettato dal server: ${e.message}`
                : "Un dato dell'allenamento non è stato accettato dal server.",
          });
        } finally {
          inFlight = null;
        }
        // Rilettura: mentre si aspettava la risposta può essersi aggiunto altro.
        const dopo = load();
        dopo.sessions = { ...dopo.sessions, ...stato.sessions };
        dopo.sets = { ...dopo.sets, ...stato.sets };
        dopo.ops = dopo.ops.filter((o) => o.id !== op.id);
        save(dopo);
        if (esito && esito !== "ok") emit(esito);
      }
    } finally {
      flushing = null;
    }
  })();
  return flushing;
}

function enqueue(nuova: NewOp) {
  if (activeProfile === null) throw new Error("nessun profilo attivo");
  const s = load();
  s.ops.push({ ...nuova, id: opId(), profileId: activeProfile } as Op);
  save(s);
  void flush();
}

/**
 * Prova subito, se non c'è niente in coda prima; altrimenti (o se la rete
 * manca) accoda. L'ordine conta: una serie non deve arrivare prima della sua
 * sessione.
 */
async function sendOrQueue<T>(op: NewOp, now: () => Promise<T>, after?: (r: T, s: State) => void): Promise<{ result: T | null; queued: boolean }> {
  if (mine(load()).length === 0) {
    try {
      const result = await withTimeout(now());
      if (after) {
        const s = load();
        after(result, s);
        save(s);
      }
      return { result, queued: false };
    } catch (e) {
      if (!isRetryable(e)) throw e;
    }
  }
  enqueue(op);
  return { result: null, queued: true };
}

// --- Le operazioni dell'allenamento ---------------------------------------------------

/** Avvia l'allenamento. Senza rete restituisce una sessione provvisoria (id negativo). */
export async function createSession(
  profileId: number,
  body: Omit<SessionBody, "start" | "started_at" | "client_id">
): Promise<{ session: WorkoutSessionLog; queued: boolean }> {
  const corpo: SessionBody = { ...body, start: true, started_at: new Date().toISOString(), client_id: newClientId() };
  const tempId = -Date.now();
  const { result, queued } = await sendOrQueue(
    { kind: "session", tempId, body: corpo },
    () => api.post<WorkoutSessionLog>(`/workout/sessions?profile_id=${profileId}`, corpo)
  );
  if (result) return { session: result, queued: false };
  return {
    queued,
    session: {
      id: tempId,
      date: body.date,
      day_label: body.day_label,
      workout_plan_id: body.workout_plan_id,
      perceived_fatigue: null,
      note: null,
      started_at: corpo.started_at,
      ended_at: null,
      sets: [],
    },
  };
}

/** Riapre un allenamento già chiuso oggi. */
export async function reopenSession(sessionId: number): Promise<{ session: WorkoutSessionLog | null; queued: boolean }> {
  // Chiuso senza rete e ripreso prima che la chiusura partisse: basta
  // toglierla dalla coda, per il server non è mai finito.
  const s = load();
  const prima = s.ops.length;
  s.ops = s.ops.filter(
    (o) =>
      !(
        o.profileId === activeProfile &&
        o.kind === "finish" &&
        o.id !== inFlight &&
        (o.sessionId === sessionId || realSession(s, o.sessionId) === sessionId)
      )
  );
  if (s.ops.length !== prima) {
    save(s);
    return { session: null, queued: true };
  }
  if (sessionId < 0) return { session: null, queued: true };
  const { result, queued } = await sendOrQueue(
    { kind: "reopen", sessionId },
    () => api.post<WorkoutSessionLog>(`/workout/sessions/${sessionId}/start`)
  );
  return { session: result, queued };
}

export async function addSet(sessionId: number, body: SetBody): Promise<{ set: SessionSet | null; queued: boolean }> {
  if (sessionId < 0) {
    // La sessione stessa è ancora in coda: la serie la segue.
    enqueue({ kind: "set", sessionId, body });
    return { set: null, queued: true };
  }
  const { result, queued } = await sendOrQueue(
    { kind: "set", sessionId, body },
    () => api.post<SessionSet>(`/workout/sessions/${sessionId}/sets`, body),
    (set, s) => {
      s.sets[body.client_id] = set.id;
    }
  );
  return { set: result, queued };
}

/** Corregge una serie: `ref` è l'id del server o il `client_id` se non è ancora arrivata. */
export async function updateSet(ref: number | string, body: SetChange): Promise<{ queued: boolean }> {
  if (typeof ref === "string") {
    // Ancora in coda (e non in volo): si corregge la serie in attesa.
    const s = load();
    const attesa = mine(s).find((o) => o.kind === "set" && o.body.client_id === ref && o.id !== inFlight);
    if (attesa && attesa.kind === "set") {
      attesa.body = { ...attesa.body, ...body };
      save(s);
      return { queued: true };
    }
    const id = s.sets[ref];
    if (id === undefined) {
      enqueue({ kind: "set-update", ref, body });
      return { queued: true };
    }
    ref = id;
  }
  const id = ref;
  const { queued } = await sendOrQueue({ kind: "set-update", ref: id, body }, () =>
    api.patch(`/workout/sets/${id}`, body)
  );
  return { queued };
}

export async function deleteSet(ref: number | string): Promise<{ queued: boolean }> {
  if (typeof ref === "string") {
    const s = load();
    const attesa = mine(s).find((o) => o.kind === "set" && o.body.client_id === ref && o.id !== inFlight);
    if (attesa) {
      // Mai partita: basta toglierla dalla coda.
      s.ops = s.ops.filter((o) => o !== attesa && !(o.kind === "set-update" && o.ref === ref));
      save(s);
      return { queued: false };
    }
    const id = s.sets[ref];
    if (id === undefined) {
      enqueue({ kind: "set-delete", ref });
      return { queued: true };
    }
    ref = id;
  }
  const id = ref;
  try {
    const { queued } = await sendOrQueue({ kind: "set-delete", ref: id }, () =>
      api.del(`/workout/sets/${id}`)
    );
    return { queued };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return { queued: false };
    throw e;
  }
}

/** Termina l'allenamento con l'ora di adesso. Senza rete il riepilogo arriva dopo. */
export async function finishSession(sessionId: number): Promise<{ summary: SessionSummary | null; queued: boolean }> {
  const body = { ended_at: new Date().toISOString() };
  if (sessionId < 0) {
    enqueue({ kind: "finish", sessionId, body });
    return { summary: null, queued: true };
  }
  const { result, queued } = await sendOrQueue({ kind: "finish", sessionId, body }, () =>
    api.post<SessionSummary>(`/workout/sessions/${sessionId}/finish`, body)
  );
  return { summary: result, queued };
}

// --- Cosa è ancora in attesa, per mostrarlo ---------------------------------------------

export type PendingSet = SetBody & { sessionId: number };

/** La sessione provvisoria creata senza rete per quel giorno della scheda, se c'è. */
export function pendingSession(planId: number, dayLabel: string, date: string): WorkoutSessionLog | null {
  const op = mine(load()).find(
    (o) => o.kind === "session" && o.body.workout_plan_id === planId && o.body.day_label === dayLabel && o.body.date === date
  );
  if (!op || op.kind !== "session") return null;
  return {
    id: op.tempId,
    date,
    day_label: dayLabel,
    workout_plan_id: planId,
    perceived_fatigue: null,
    note: null,
    started_at: op.body.started_at,
    ended_at: null,
    sets: [],
  };
}

/** Serie in coda per una sessione (id del server o provvisorio). */
export function pendingSets(sessionIds: number[]): PendingSet[] {
  const s = load();
  const ids = new Set(sessionIds);
  // Una sessione provvisoria già arrivata vale anche con il suo id vero.
  for (const [temp, real] of Object.entries(s.sessions)) if (ids.has(real)) ids.add(Number(temp));
  return mine(s).flatMap((o) => (o.kind === "set" && ids.has(o.sessionId) ? [{ ...o.body, sessionId: o.sessionId }] : []));
}

/** Correzioni ed eliminazioni in coda su serie già arrivate al server. */
export function pendingEdits(): { updates: Map<number, SetChange>; deletes: Set<number> } {
  const s = load();
  const updates = new Map<number, SetChange>();
  const deletes = new Set<number>();
  for (const o of mine(s)) {
    if (o.kind !== "set-update" && o.kind !== "set-delete") continue;
    const id = realSet(s, o.ref);
    if (id === null) continue;
    if (o.kind === "set-update") updates.set(id, o.body);
    else deletes.add(id);
  }
  return { updates, deletes };
}

/** Allenamento terminato senza rete e non ancora arrivato. */
export function pendingFinish(sessionId: number): boolean {
  const s = load();
  return mine(s).some((o) => o.kind === "finish" && (o.sessionId === sessionId || realSession(s, o.sessionId) === sessionId));
}

// --- Avvio ------------------------------------------------------------------------------

let started = false;

/** Da chiamare dopo l'accesso, con il profilo attivo: rimanda la coda quando si può. */
export function startOfflineSync(profileId: number): () => void {
  activeProfile = profileId;
  emit({ type: "changed", pending: pendingCount() });
  if (started || typeof window === "undefined") return () => undefined;
  started = true;
  const prova = () => {
    if (pendingCount()) void flush();
  };
  prova();
  window.addEventListener("online", prova);
  document.addEventListener("visibilitychange", prova);
  const timer = window.setInterval(prova, RETRY_MS);
  return () => {
    started = false;
    activeProfile = null;
    window.removeEventListener("online", prova);
    document.removeEventListener("visibilitychange", prova);
    window.clearInterval(timer);
  };
}

// --- Ultima volta e note, per aprire l'allenamento anche senza rete ------------------------

const LAST_KEY = "kilo:ultima-volta";

export function rememberLast<T>(byExercise: Record<number, T>) {
  try {
    const prima = JSON.parse(localStorage.getItem(LAST_KEY) ?? "{}") as Record<string, T>;
    localStorage.setItem(LAST_KEY, JSON.stringify({ ...prima, ...byExercise }));
  } catch {
    /* solo una comodità */
  }
}

export function recallLast<T>(exerciseIds: number[]): Record<number, T> {
  try {
    const tutti = JSON.parse(localStorage.getItem(LAST_KEY) ?? "{}") as Record<string, T>;
    return Object.fromEntries(exerciseIds.filter((id) => tutti[id]).map((id) => [id, tutti[id]]));
  } catch {
    return {};
  }
}
