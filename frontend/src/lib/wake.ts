/**
 * Risveglio del backend.
 *
 * Render gratuito spegne il backend dopo 15 minuti senza richieste e la
 * ripartenza richiede 20-40 secondi. La pagina invece arriva subito da
 * Vercel: appena si apre l'app si chiama `/health`, così il backend parte
 * mentre si scrive email e password, e l'accesso aspetta che sia pronto
 * invece di andare in errore.
 *
 * Un solo risveglio per pagina, condiviso da chi lo chiede.
 */

import { useEffect, useState } from "react";

export type WakeState = "checking" | "ready" | "waking";

// Oltre questo tempo senza risposta si dice che il server si sta avviando.
const SLOW_MS = 2500;
const RETRY_MS = 3000;
const ATTEMPT_TIMEOUT_MS = 10_000;

let state: WakeState = "checking";
let ready: Promise<void> | null = null;
const listeners = new Set<(s: WakeState) => void>();

function set(next: WakeState) {
  state = next;
  listeners.forEach((l) => l(next));
}

async function ping(): Promise<boolean> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ATTEMPT_TIMEOUT_MS);
  try {
    const res = await fetch("/api/health", { cache: "no-store", signal: ctrl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

/** Promessa che si risolve quando il backend risponde. */
export function wakeBackend(): Promise<void> {
  if (ready) return ready;
  const slow = setTimeout(() => state === "checking" && set("waking"), SLOW_MS);
  ready = (async () => {
    while (!(await ping())) {
      if (state === "checking") set("waking");
      await new Promise((r) => setTimeout(r, RETRY_MS));
    }
    clearTimeout(slow);
    set("ready");
  })();
  return ready;
}

export function useBackendWake(): WakeState {
  const [s, setS] = useState<WakeState>(state);
  useEffect(() => {
    listeners.add(setS);
    setS(state);
    wakeBackend();
    return () => {
      listeners.delete(setS);
    };
  }, []);
  return s;
}
