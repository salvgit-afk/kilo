"use client";

/**
 * Lista di alimenti di una bozza, con i grammi correggibili.
 *
 * È la stessa forma usata dall'importazione di una ricetta incollata: un
 * elenco di `RecipeItem` dove la quantità è una proposta finché non la si
 * tocca. Vive qui, e non dentro una singola schermata, perché la bozza arriva
 * ormai da due strade — il testo incollato e la foto del piatto — e in
 * entrambe la regola è la stessa: l'ultima parola sui grammi è di chi mangia.
 *
 * Due dettagli voluti:
 *  - correggere i grammi toglie il marchio «stimato»: una stima guardata e
 *    confermata è un dato di chi mangia, una non guardata resta dichiarata;
 *  - gli alimenti che il catalogo non conosce restano visibili ma non fanno
 *    numeri: meglio un totale dichiarato incompleto che uno inventato.
 */

import type { RecipeItem } from "@/lib/api";
import { NumberField } from "@/components/controls";

export function DraftItems({
  items,
  onChange,
}: {
  items: RecipeItem[];
  onChange: (items: RecipeItem[]) => void;
}) {
  function aggiorna(indice: number, cambio: Partial<RecipeItem>) {
    onChange(items.map((i, k) => (k === indice ? { ...i, ...cambio } : i)));
  }

  return (
    <div className="divide-y divide-white/[0.05] rounded-2xl border border-white/[0.08] bg-white/[0.02] p-1.5">
      {items.map((item, k) => {
        const mancante = item.ingredient_id === null;
        return (
          <div key={`${item.name}-${k}`} className="flex items-center gap-2 px-1.5 py-2.5 sm:gap-3 sm:px-2">
            <div className="min-w-0 flex-1">
              <p className={`truncate text-[13.5px] ${mancante ? "text-amber-200/80" : "text-white/85"}`}>
                {item.name}
                {item.measure && <span className="ml-1.5 text-[11.5px] text-white/30">({item.measure})</span>}
              </p>
              <p className="truncate text-[11px] text-white/35">
                {item.estimated && !mancante && (
                  <span className="mr-1.5 rounded bg-amber-300/15 px-1 py-px text-[9.5px] font-semibold uppercase tracking-wide text-amber-100">
                    stimato
                  </span>
                )}
                {mancante ? (
                  "non trovato nel catalogo: non entra nei totali"
                ) : (
                  <>
                    {item.matched_name}
                    {item.source_label && <span className="text-white/25"> · {item.source_label}</span>}
                  </>
                )}
              </p>
            </div>
            <NumberField
              value={item.grams}
              onChange={(v) => aggiorna(k, { grams: v, estimated: false })}
              min={0}
              max={5000}
              step={5}
              size="sm"
              steppers="sm"
              suffix="g"
              placeholder="—"
              ariaLabel={`Grammi di ${item.name}${item.estimated ? " (stimati)" : ""}`}
              className={`w-[88px] shrink-0 sm:w-36 ${mancante ? "pointer-events-none opacity-40" : ""}`}
            />
            <button
              onClick={() => onChange(items.filter((_, i) => i !== k))}
              aria-label={`Togli ${item.name}`}
              title="Togli dall'elenco"
              className="grid h-9 w-8 shrink-0 place-items-center rounded-xl text-white/35 transition hover:bg-rose-400/10 hover:text-rose-300 sm:w-9"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" stroke="currentColor" strokeWidth={2} fill="none">
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}
