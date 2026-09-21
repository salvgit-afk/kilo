"use client";

/**
 * I giorni della settimana in cui ci si allena.
 *
 * - **WeekdayPicker**: prima la frequenza, poi i giorni. Scegliere la
 *   frequenza propone giorni distanziati (3 → lunedì, mercoledì, venerdì);
 *   toccando i giorni si cambia la proposta, e la frequenza li segue.
 * - **WeekLine**: la settimana come una linea di pallini: un manubrio nei
 *   giorni di allenamento, una luna in quelli di riposo, una spunta in quelli
 *   fatti. Toccando un giorno il pallino si allarga e mostra
 *   l'allenamento di quel giorno; toccando di nuovo la pillola si richiude,
 *   e la freccia al suo interno apre quel giorno nella scheda.
 *
 * Quale allenamento cade in quale giorno: gli allenamenti della scheda (A, B,
 * Push…) si susseguono nell'ordine dei giorni scelti, e se i giorni sono più
 * degli allenamenti si alternano di settimana in settimana (A-B-A, poi B-A-B)
 * invece di ripartire sempre da A.
 */

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { api, localDate, shiftDate, type WorkoutPlan, type WorkoutSessionLog } from "@/lib/api";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "@/components/controls";
import { Notice } from "@/components/ui";

export const WEEKDAY_LETTERS = ["L", "M", "M", "G", "V", "S", "D"];
export const WEEKDAY_NAMES = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];

export const DEFAULT_WEEKDAYS: Record<number, number[]> = {
  1: [0],
  2: [0, 3],
  3: [0, 2, 4],
  4: [0, 1, 3, 4],
  5: [0, 1, 2, 3, 4],
  6: [0, 1, 2, 3, 4, 5],
  7: [0, 1, 2, 3, 4, 5, 6],
};

export function defaultWeekdays(days: number): number[] {
  return DEFAULT_WEEKDAYS[Math.min(Math.max(days, 1), 7)] ?? DEFAULT_WEEKDAYS[3];
}

function parseISO(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Il lunedì della settimana di una data. */
export function mondayOf(iso: string): string {
  return shiftDate(iso, -((parseISO(iso).getDay() + 6) % 7));
}

export function planDayLabels(plan: WorkoutPlan): string[] {
  return [...new Set(plan.exercises.map((e) => e.day_label))];
}

export function dayTitle(label: string): string {
  return label.length <= 2 ? `Giorno ${label}` : label;
}

/** Quale allenamento cade in ciascun giorno della settimana che inizia lunedì `monday`. */
export function weekAssignments(plan: WorkoutPlan, monday: string): Record<number, string> {
  const etichette = planDayLabels(plan);
  const giorni = [...plan.training_weekdays].sort((a, b) => a - b);
  if (!etichette.length || !giorni.length) return {};
  const settimane = Math.max(
    0,
    Math.round((parseISO(monday).getTime() - parseISO(mondayOf(plan.started_at)).getTime()) / (7 * 864e5))
  );
  return Object.fromEntries(
    giorni.map((g, i) => [g, etichette[(settimane * giorni.length + i) % etichette.length]])
  );
}

// --- Selettore -------------------------------------------------------------------------

export function WeekdayPicker({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  const ordinati = [...value].sort((a, b) => a - b);
  const difila = ordinati.some((g, i) => i > 0 && g - ordinati[i - 1] === 1) || (ordinati.includes(0) && ordinati.includes(6));

  return (
    <div>
      <p className="label">Quanti giorni a settimana</p>
      <div className="inline-flex gap-1 rounded-2xl border border-white/10 bg-white/[0.03] p-1">
        {[2, 3, 4, 5, 6].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(defaultWeekdays(n))}
            className={`relative h-10 w-11 rounded-xl text-[14px] font-semibold transition ${
              value.length === n ? "text-ink-900" : "text-white/55 hover:text-white"
            }`}
          >
            {value.length === n && (
              <motion.span
                layoutId="freq-pill"
                className="absolute inset-0 rounded-xl bg-gradient-to-b from-lime-400 to-lime-500"
                transition={{ type: "spring", stiffness: 420, damping: 32 }}
              />
            )}
            <span className="relative">{n}</span>
          </button>
        ))}
      </div>

      <p className="label mt-4">Quali giorni</p>
      <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
        {WEEKDAY_LETTERS.map((l, g) => {
          const on = value.includes(g);
          return (
            <motion.button
              key={g}
              type="button"
              whileTap={{ scale: 0.9 }}
              onClick={() =>
                onChange(on ? value.filter((x) => x !== g) : [...value, g].sort((a, b) => a - b))
              }
              aria-pressed={on}
              aria-label={WEEKDAY_NAMES[g]}
              className={`mx-auto grid aspect-square w-full max-w-[48px] place-items-center rounded-full border text-[14px] font-semibold transition ${
                on
                  ? "border-lime-400/60 bg-gradient-to-b from-lime-400 to-lime-500 text-ink-900 shadow-[0_6px_16px_-10px_rgba(174,212,74,0.9)]"
                  : "border-white/10 bg-white/[0.03] text-white/45 hover:text-white/80"
              }`}
            >
              {l}
            </motion.button>
          );
        })}
      </div>
      <p className={`mt-2.5 min-h-[18px] text-[12px] leading-snug ${value.length ? "text-white/40" : "text-amber-200/80"}`}>
        {!value.length
          ? "Scegli almeno un giorno."
          : difila
            ? "Due giorni di fila: va bene se la scheda lavora muscoli diversi, per esempio sopra e sotto."
            : ordinati.map((g) => WEEKDAY_NAMES[g]).join(", ")}
      </p>
    </div>
  );
}

/** Modifica dei giorni di una scheda già creata. */
export function ScheduleDialog({
  plan,
  profileId,
  onClose,
  onSaved,
}: {
  plan: WorkoutPlan;
  profileId: number;
  onClose: () => void;
  onSaved: (plan: WorkoutPlan) => void;
}) {
  const [value, setValue] = useState(plan.training_weekdays);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allenamenti = planDayLabels(plan).length;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onSaved(await api.put<WorkoutPlan>(`/workout/plans/${plan.id}/schedule?profile_id=${profileId}`, { weekdays: value }));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito a salvare i giorni.");
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose} className="max-w-md">
      <ModalHeader
        eyebrow="Giorni di allenamento"
        title={plan.name}
        subtitle="Scegli quando ti alleni: la proposta distanzia gli allenamenti, ma decidi tu."
        onClose={onClose}
      />
      <ModalBody>
        <WeekdayPicker value={value} onChange={setValue} />
        {value.length > 0 && value.length !== allenamenti && (
          <p className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-3 text-[12px] leading-snug text-white/50">
            La scheda ha {allenamenti} {allenamenti === 1 ? "allenamento" : "allenamenti diversi"}
            {value.length > allenamenti
              ? `: con ${value.length} giorni si alternano di settimana in settimana.`
              : `: con ${value.length} ${value.length === 1 ? "giorno" : "giorni"} a settimana ne fai una parte ogni settimana, a rotazione. Valuta di crearne una nuova con la nuova frequenza.`}
          </p>
        )}
        {error && <Notice>{error}</Notice>}
      </ModalBody>
      <ModalFooter>
        <button className="btn-ghost flex-1 justify-center" onClick={onClose}>
          Annulla
        </button>
        <button className="btn-primary flex-[1.6] justify-center" onClick={save} disabled={saving || !value.length}>
          {saving ? "Salvo…" : "Salva i giorni"}
        </button>
      </ModalFooter>
    </Modal>
  );
}

// --- Linea della settimana ------------------------------------------------------------------

// Apertura e chiusura dei giorni: una curva che accelera e rallenta in modo
// simmetrico, uguale per la colonna che si allarga e per la pillola, così si
// muovono insieme. Una curva sbilanciata in partenza faceva quasi tutto il
// movimento nei primi 100 ms e la chiusura sembrava uno scatto.
const MORBIDA = { duration: 0.6, ease: [0.45, 0, 0.2, 1] } as const;

const ANELLO_OGGI = "ring-2 ring-white/60 ring-offset-1 ring-offset-ink-900";

function colore(allenamento: boolean, fatto: boolean): string {
  if (!allenamento) return "border-white/10 bg-ink-800 text-white/30";
  return fatto
    ? "border-lime-400 bg-gradient-to-b from-lime-400 to-lime-500 text-ink-900"
    : "border-lime-400/55 bg-ink-800 text-lime-100 shadow-[0_0_18px_-6px_rgba(174,212,74,0.8)]";
}

export function WeekLine({
  plan,
  profileId,
  onOpenDay,
}: {
  plan: WorkoutPlan;
  profileId: number;
  /** Tocco sulla pillola di un giorno di allenamento. */
  onOpenDay?: (label: string) => void;
}) {
  const oggi = localDate();
  const lunedi = mondayOf(oggi);
  const giorni = Array.from({ length: 7 }, (_, i) => shiftDate(lunedi, i));
  const assegnati = useMemo(() => weekAssignments(plan, lunedi), [plan, lunedi]);
  const [fatti, setFatti] = useState<Set<string>>(new Set());
  const [aperto, setAperto] = useState<number | null>(null);

  // Sessioni di questa settimana con questa scheda: il giorno diventa "fatto".
  useEffect(() => {
    let annullato = false;
    api
      .get<WorkoutSessionLog[]>(`/workout/sessions?profile_id=${profileId}&limit=20`)
      .then((sessioni) => {
        if (annullato) return;
        setFatti(
          new Set(
            sessioni
              .filter((s) => s.date >= lunedi && s.workout_plan_id === plan.id && s.sets.length > 0)
              .map((s) => s.date)
          )
        );
      })
      .catch(() => undefined);
    return () => {
      annullato = true;
    };
  }, [profileId, plan.id, lunedi]);

  const esercizi = (label: string) => plan.exercises.filter((e) => e.day_label === label).length;

  return (
    <LayoutGroup id={`week-${plan.id}`}>
      <div className="relative flex items-start gap-1 py-1">
        {/* La linea che unisce i giorni, dietro ai pallini. */}
        <div className="pointer-events-none absolute left-4 right-4 top-[20px] h-[2px] rounded-full bg-white/[0.08]" />
        {giorni.map((data, g) => {
          const label = assegnati[g];
          const allenamento = label !== undefined;
          const fatto = fatti.has(data);
          const oggiQui = data === oggi;
          const espanso = aperto === g;
          return (
            <motion.div
              key={data}
              layout
              transition={MORBIDA}
              className={`relative flex min-w-0 flex-col items-center ${espanso ? "flex-[3]" : "flex-1"}`}
            >
              <AnimatePresence initial={false} mode="popLayout">
              {espanso ? (
                <motion.div
                  layoutId={`giorno-${plan.id}-${g}`}
                  key="aperta"
                  style={{ borderRadius: 999 }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0, transition: { duration: 0.35, ease: [0.45, 0, 0.2, 1] } }}
                  transition={MORBIDA}
                  className={`relative z-10 flex h-[34px] w-full items-center overflow-hidden rounded-full border ${colore(allenamento, fatto)} ${oggiQui ? ANELLO_OGGI : ""}`}
                >
                  {/* Tocco sulla pillola: si richiude, come nei giorni di riposo. */}
                  <button
                    onClick={() => setAperto(null)}
                    aria-label={`Chiudi ${WEEKDAY_NAMES[g]}`}
                    className="flex h-full min-w-0 flex-1 flex-col items-center justify-center pl-2 pr-1 leading-tight"
                  >
                    <motion.span
                      initial={{ opacity: 0, scale: 0.85 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="max-w-full truncate text-[12px] font-semibold"
                    >
                      {allenamento ? dayTitle(label) : "Riposo"}
                    </motion.span>
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className={`max-w-full truncate text-[10px] ${fatto ? "text-ink-900/70" : "text-white/50"}`}
                    >
                      {allenamento ? (fatto ? "fatto ✓" : `${esercizi(label)} esercizi`) : "recupero"}
                    </motion.span>
                  </button>
                  {/* La freccia apre quel giorno nella scheda. */}
                  {allenamento && onOpenDay && (
                    <motion.button
                      initial={{ opacity: 0, scale: 0.6 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.08 }}
                      onClick={() => onOpenDay(label)}
                      aria-label={`Apri ${dayTitle(label)} nella scheda`}
                      className={`mr-[3px] grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full ${
                        fatto ? "bg-ink-900/85 text-lime-300" : "bg-lime-400 text-ink-900"
                      }`}
                    >
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={3}>
                        <path d="M5 12h13m-5-6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </motion.button>
                  )}
                </motion.div>
              ) : (
                <motion.button
                  layoutId={`giorno-${plan.id}-${g}`}
                  key="chiusa"
                  style={{ borderRadius: 999 }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0, transition: { duration: 0.3, ease: [0.45, 0, 0.2, 1] } }}
                  transition={MORBIDA}
                  onClick={() => setAperto(g)}
                  aria-expanded={false}
                  aria-label={`${WEEKDAY_NAMES[g]}: ${allenamento ? dayTitle(label) : "riposo"}${fatto ? ", fatto" : ""}`}
                  className={`relative z-10 grid h-[34px] w-[34px] place-items-center rounded-full border text-[12.5px] font-semibold ${colore(allenamento, fatto)} ${oggiQui ? ANELLO_OGGI : ""}`}
                >
                  {/* `layout` sul testo: senza, durante il restringimento la lettera
                      si schiaccerebbe insieme al pallino. */}
                  <motion.span layout transition={MORBIDA} className="grid place-items-center">
                    {allenamento ? fatto ? <IconCheck /> : <IconDumbbell /> : <IconMoon />}
                  </motion.span>
                </motion.button>
              )}
              </AnimatePresence>
              <motion.span
                layout="position"
                transition={MORBIDA}
                className={`mt-1.5 text-[11px] ${oggiQui ? "font-semibold text-white/80" : allenamento ? "text-lime-200/70" : "text-white/30"}`}
              >
                {oggiQui ? "oggi" : WEEKDAY_LETTERS[g]}
              </motion.span>
            </motion.div>
          );
        })}
      </div>
    </LayoutGroup>
  );
}

// --- Icone dei giorni ------------------------------------------------------------------

function IconDumbbell() {
  return (
    <svg viewBox="0 0 24 24" className="h-[17px] w-[17px]" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
      <path d="M6.5 7v10M17.5 7v10M3.5 9.5v5M20.5 9.5v5M6.5 12h11" />
    </svg>
  );
}

function IconMoon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[15px] w-[15px]" fill="currentColor">
      <path d="M20 14.6A8 8 0 0 1 9.4 4a8 8 0 1 0 10.6 10.6Z" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" className="h-[17px] w-[17px]" fill="none" stroke="currentColor" strokeWidth={3}>
      <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
