/**
 * Canale fra le sezioni e il coach.
 *
 * Ogni sezione può chiedere qualcosa al coach ("com'è andata la settimana?",
 * "come sento meglio il petto in questo esercizio?") senza conoscere la
 * chat: emette un evento, la chat lo raccoglie, si apre e risponde con il
 * contesto della schermata.
 *
 * Nella direzione opposta, le azioni proposte dal coach diventano un
 * `Intent` che la pagina consegna alla sezione giusta (apri il diario con
 * questa ricerca, genera la scheda con questo split). L'intent parte solo da
 * un clic dell'utente: il coach propone, non esegue.
 */

import type { SectionId } from "@/components/Shell";

export const COACH_EVENT = "coach:ask";

export type CoachAsk = { question: string; context?: string };

export function askCoach(question: string, context?: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<CoachAsk>(COACH_EVENT, { detail: { question, context } }));
}

export type Intent = {
  section: SectionId;
  foodQuery?: string;
  recipeQuery?: string;
  generateSplit?: string;
  /** Distingue due intent uguali consecutivi (stessa ricerca ripetuta). */
  nonce: number;
};

export const SECTION_LABELS: Record<SectionId, string> = {
  oggi: "Oggi",
  scheda: "Scheda",
  diario: "Diario",
  ricette: "Ricette",
  progressi: "Progressi",
  integratori: "Integratori",
  profilo: "Profilo",
};

/** Il pasto più probabile in base all'ora, per le aggiunte rapide. */
export function mealForNow(date = new Date()): string {
  const h = date.getHours();
  if (h < 11) return "breakfast";
  if (h < 15) return "lunch";
  if (h < 18) return "snack";
  return "dinner";
}
