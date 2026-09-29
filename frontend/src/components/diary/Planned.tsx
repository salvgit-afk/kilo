"use client";

/**
 * Pasti previsti: segnati in anticipo e confermati quando si mangiano.
 *
 * Servono a chi domani è fuori casa e le confezioni le ha adesso: le
 * scansiona oggi, e domani tocca «Mangiato». Nei giorni futuri tutto quello
 * che si aggiunge è previsto; oggi lo si sceglie con l'interruttore (la cena
 * già decisa); nei giorni passati no. Finché non si confermano non contano
 * in nessun totale.
 */

import { Toggle } from "@/components/controls";
import { shiftDate } from "@/lib/api";

/** Quanti giorni avanti si pianifica: lo stesso limite del server. */
export const MAX_PLAN_DAYS = 7;

export function isFuture(date: string, today: string) {
  return date > today;
}

export function lastPlannableDay(today: string) {
  return shiftDate(today, MAX_PLAN_DAYS);
}

/**
 * L'interruttore "previsto" della finestra di aggiunta.
 *
 * Nel futuro non è una scelta: si dice e basta. Nel passato non compare.
 */
export function PlannedToggle({
  date,
  today,
  value,
  onChange,
  className = "",
}: {
  date: string;
  today: string;
  value: boolean;
  onChange: (v: boolean) => void;
  className?: string;
}) {
  if (isFuture(date, today)) {
    return (
      <p
        className={`flex items-center gap-2 rounded-xl border border-dashed border-lime-400/35 bg-lime-400/[0.05] px-3 py-2 text-[12px] leading-snug text-white/65 ${className}`}
      >
        <ClockIcon />
        <span>
          <b className="font-semibold text-lime-200">Previsto.</b> Lo confermi quando lo mangi: fino ad allora non
          conta nei totali.
        </span>
      </p>
    );
  }
  if (date !== today) return null;
  return (
    <div className={className}>
      <Toggle
        checked={value}
        onChange={onChange}
        label="Segna come previsto"
        hint="Per quello che mangerai più tardi: lo confermi dopo con «Mangiato»."
      />
    </div>
  );
}

export function ClockIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} shrink-0 text-lime-300`} fill="none" stroke="currentColor" strokeWidth={2.2} aria-hidden>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
