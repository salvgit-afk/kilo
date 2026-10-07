"use client";

/**
 * Il recupero fra una serie e l'altra, condiviso fra il pannello
 * dell'allenamento e la pillola della scheda.
 *
 * Vive fuori dai componenti (e in localStorage) perché deve sopravvivere a
 * "Riduci": il pannello si chiude, la pillola continua a contare, e
 * riaprendo si ritrova lo stesso conto alla rovescia. Il tempo è un istante
 * di fine, non un contatore: se il telefono si blocca o la pagina resta in
 * secondo piano, al ritorno il numero è comunque giusto.
 */

import { useEffect, useState } from "react";

export type Rest = {
  sessionId: number;
  endsAt: number;
  total: number;
  /** "Poi la serie 3" oppure "Poi: Croci ai cavi". */
  next: string;
  /** "62,5 kg × 8 · Panca piana": i numeri prima, il nome si può troncare. */
  detail: string;
  /** Il recupero è finito: resta a dire "tocca a te" finché non lo si chiude. */
  done: boolean;
};

const KEY = "kilo:recupero";
const EVENT = "kilo:recupero";
// Un "tocca a te" dimenticato non resta lì per sempre.
const DONE_TTL_MS = 3 * 60_000;

let current: Rest | null = null;
let loaded = false;

function read(): Rest | null {
  if (!loaded) {
    loaded = true;
    try {
      const raw = localStorage.getItem(KEY);
      current = raw ? (JSON.parse(raw) as Rest) : null;
    } catch {
      current = null;
    }
  }
  if (current && Date.now() > current.endsAt + DONE_TTL_MS) {
    // Senza avvisare nessuno: si è dentro il render di un componente.
    current = null;
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* niente */
    }
  }
  return current;
}

function write(next: Rest | null) {
  current = next;
  try {
    if (next) localStorage.setItem(KEY, JSON.stringify(next));
    else localStorage.removeItem(KEY);
  } catch {
    /* archiviazione non disponibile: il timer vale finché la pagina è aperta */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENT));
}

export const restTimer = {
  start(rest: Omit<Rest, "endsAt" | "done">) {
    write({ ...rest, endsAt: Date.now() + rest.total * 1000, done: false });
  },
  /** +15 / −15 secondi; non scende sotto i 5 rimasti. */
  shift(seconds: number) {
    const r = read();
    if (!r || r.done) return;
    write({ ...r, endsAt: Math.max(Date.now() + 5000, r.endsAt + seconds * 1000) });
  },
  clear() {
    write(null);
  },
  /** La sessione avviata senza rete ha ricevuto il suo id vero: il recupero la segue. */
  rename(from: number, to: number) {
    const r = read();
    if (r?.sessionId === from) write({ ...r, sessionId: to });
  },
  /** Da chiamare quando la sessione finisce: il timer non le sopravvive. */
  clearSession(sessionId: number) {
    if (read()?.sessionId === sessionId) write(null);
  },
};

/** Il recupero in corso per `sessionId` e i secondi che mancano. */
export function useRest(sessionId: number | null | undefined): { rest: Rest | null; remaining: number } {
  const [, force] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const aggiorna = () => force((n) => n + 1);
    window.addEventListener(EVENT, aggiorna);
    window.addEventListener("storage", aggiorna);
    return () => {
      window.removeEventListener(EVENT, aggiorna);
      window.removeEventListener("storage", aggiorna);
    };
  }, []);

  const r = typeof window !== "undefined" ? read() : null;
  const rest = r && r.sessionId === sessionId ? r : null;
  const attivo = rest !== null && !rest.done;

  useEffect(() => {
    if (!attivo) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [attivo]);

  const remaining = rest && !rest.done ? Math.max(0, Math.ceil((rest.endsAt - now) / 1000)) : 0;

  // Fine del recupero: il primo componente che se ne accorge lo segna e
  // avvisa; gli altri trovano già `done` e non ripetono il suono.
  useEffect(() => {
    if (rest && !rest.done && remaining === 0) {
      write({ ...rest, done: true });
      signal();
    }
  }, [rest, remaining]);

  return { rest, remaining };
}

// --- Avviso di fine recupero ------------------------------------------------------

let audio: AudioContext | null = null;

/**
 * Da chiamare dentro un tocco dell'utente (il salvataggio della serie): i
 * browser, Safari su iPhone per primo, fanno suonare una pagina solo dopo
 * che l'audio è stato sbloccato da un gesto.
 */
export function primeRestSound() {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    audio ??= new Ctx();
    if (audio.state === "suspended") void audio.resume();
  } catch {
    audio = null;
  }
}

/** Due note brevi e morbide, più la vibrazione dove esiste (non su iPhone). */
function signal() {
  try {
    navigator.vibrate?.([120, 60, 120]);
  } catch {
    /* vibrazione non supportata */
  }
  if (!audio) return;
  try {
    const t0 = audio.currentTime;
    [880, 1175].forEach((freq, i) => {
      const osc = audio!.createOscillator();
      const gain = audio!.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = t0 + i * 0.16;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.22);
      osc.connect(gain).connect(audio!.destination);
      osc.start(start);
      osc.stop(start + 0.24);
    });
  } catch {
    /* audio non disponibile: resta l'avviso a schermo */
  }
}
