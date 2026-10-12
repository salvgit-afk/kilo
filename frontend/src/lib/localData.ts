/**
 * Dati tenuti sul telefono: copie per lavorare senza rete e piccole comodità.
 *
 * Sono di chi ha fatto l'accesso. Su un telefono condiviso non devono
 * passare all'account successivo (note sulle macchine, carichi dell'ultima
 * volta, allenamento di oggi): all'uscita, o quando entra un account
 * diverso dall'ultimo, si cancellano. Resta solo la coda degli allenamenti
 * non ancora inviati, che appartiene già a un profilo preciso e parte quando
 * quel profilo rientra.
 */

import type { WorkoutPlan } from "@/lib/api";

// Le chiavi con dati di una persona. La coda (`kilo:coda-allenamento`) e il
// suggerimento d'installazione su iPhone (del dispositivo) restano fuori.
const PERSONALI = [
  "kilo:account",
  "kilo:note-esercizi",
  "kilo:ultima-volta",
  "kilo:cambi-allenamento",
  "kilo:allenamento-oggi",
  "kilo:recupero",
  "kilo-promemoria-nascosto",
  "kilo-promemoria-disattivati",
];
const PREFISSI_PERSONALI = ["kilo:schede:"];
const ULTIMO_UTENTE = "kilo:ultimo-utente";

/** Cancella dal telefono i dati di chi ha fatto l'accesso (non la coda). */
export function forgetLocalData() {
  try {
    for (const k of PERSONALI) localStorage.removeItem(k);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && PREFISSI_PERSONALI.some((p) => k.startsWith(p))) localStorage.removeItem(k);
    }
  } catch {
    /* archiviazione non disponibile: niente da cancellare */
  }
}

/**
 * Da chiamare a ogni accesso riuscito: se entra un account diverso
 * dall'ultimo (per esempio dopo una sessione scaduta), i dati dell'altro
 * spariscono prima di mostrare qualcosa.
 */
export function claimLocalData(userId: number) {
  try {
    const ultimo = localStorage.getItem(ULTIMO_UTENTE);
    if (ultimo !== null && ultimo !== String(userId)) forgetLocalData();
    localStorage.setItem(ULTIMO_UTENTE, String(userId));
  } catch {
    /* niente */
  }
}

// --- Schede, per allenarsi anche senza rete ---------------------------------------------

const schede = (profileId: number) => `kilo:schede:${profileId}`;

export function rememberPlans(profileId: number, plans: WorkoutPlan[]) {
  try {
    localStorage.setItem(schede(profileId), JSON.stringify(plans));
  } catch {
    /* memoria piena: resta la copia precedente */
  }
}

export function recallPlans(profileId: number): WorkoutPlan[] | null {
  try {
    const dati = JSON.parse(localStorage.getItem(schede(profileId)) ?? "null") as WorkoutPlan[] | null;
    return Array.isArray(dati) ? dati : null;
  } catch {
    return null;
  }
}
