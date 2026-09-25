"use client";

/**
 * Riepilogo della giornata, in due viste nello stesso riquadro.
 *
 *  - **Totale**: calorie sul target e le barre dei macro, come sempre;
 *  - **Per pasto**: come si distribuiscono le calorie fra colazione,
 *    spuntino, pranzo e cena, e i macro di ciascuno. Serve a capire *dove*
 *    si è mangiato, non solo quanto.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { MEAL_LABELS, type Diary } from "@/lib/api";
import { ProgressRing, StatBar } from "@/components/ui";
import { MACROS, MEAL_ORDER, MEAL_THEME } from "@/components/diary/MealTimeline";

type View = "total" | "meals";

export function DaySummary({ data }: { data: Diary }) {
  const [view, setView] = useState<View>("total");
  const { totals, targets, remaining, progress } = data;

  return (
    <section className="glass overflow-hidden">
      <div className="px-4 pt-4 sm:px-5">
        <div className="inline-flex rounded-xl border border-white/10 bg-white/[0.03] p-1">
          {(
            [
              ["total", "Totale"],
              ["meals", "Per pasto"],
            ] as const
          ).map(([id, text]) => (
            <button
              key={id}
              onClick={() => setView(id)}
              aria-pressed={view === id}
              className={`relative rounded-lg px-3.5 py-2 text-[12.5px] font-medium transition ${
                view === id ? "text-ink-900" : "text-white/55 hover:text-white"
              }`}
            >
              {view === id && (
                <motion.span
                  layoutId="diary-summary-tab"
                  className="absolute inset-0 rounded-lg bg-gradient-to-b from-lime-400 to-lime-500"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <span className="relative">{text}</span>
            </button>
          ))}
        </div>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {view === "total" ? (
          <motion.div
            key="total"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
          >
            <div className="flex flex-col items-center gap-4 px-5 py-5">
              <ProgressRing
                value={progress.kcal ?? 0}
                label={`${Math.round(totals.kcal ?? 0)}`}
                sublabel={`di ${Math.round(targets.target_kcal)} kcal`}
              />
              <p className="text-center text-[12.5px] text-white/45">
                {remaining.kcal > 0
                  ? `Ti restano ${Math.round(remaining.kcal)} kcal`
                  : `Hai superato di ${Math.abs(Math.round(remaining.kcal))} kcal`}
              </p>
            </div>
            <div className="space-y-3 border-t border-white/[0.06] px-5 py-4">
              <StatBar label="Proteine" value={totals.protein_g ?? 0} target={targets.protein_g} tone="lime" />
              <StatBar label="Carboidrati" value={totals.carbs_g ?? 0} target={targets.carbs_g} tone="iris" />
              <StatBar label="Grassi" value={totals.fat_g ?? 0} target={targets.fat_g} tone="amber" />
              <StatBar label="Fibra" value={totals.fiber_g ?? 0} target={targets.fiber_g} tone="lime" />
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="meals"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
          >
            <PerMeal data={data} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function PerMeal({ data }: { data: Diary }) {
  const byType = Object.fromEntries(data.meals.map((m) => [m.meal_type, m]));
  const totale = data.meals.reduce((s, m) => s + (m.kcal ?? 0), 0);

  return (
    <div className="px-4 pb-4 pt-4 sm:px-5">
      {totale > 0 ? (
        <>
          <div className="flex h-3 overflow-hidden rounded-full bg-white/[0.06]" aria-hidden>
            {MEAL_ORDER.map((type) => {
              const kcal = byType[type]?.kcal ?? 0;
              return kcal > 0 ? (
                <motion.span
                  key={type}
                  className={MEAL_THEME[type].bar}
                  initial={{ width: 0 }}
                  animate={{ width: `${(kcal * 100) / totale}%` }}
                  transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                />
              ) : null;
            })}
          </div>
          <p className="mt-1.5 text-[11.5px] text-white/35">
            Come si dividono le {Math.round(totale)} kcal di oggi
          </p>
        </>
      ) : (
        <p className="text-[12.5px] text-white/45">Quando segni un pasto, qui vedi come si divide la giornata.</p>
      )}

      <div className="mt-2 divide-y divide-white/[0.06]">
        {MEAL_ORDER.map((type) => {
          const m = byType[type];
          const t = MEAL_THEME[type];
          const pieno = m && m.items.length > 0;
          return (
            <div key={type} className="flex items-center gap-3 py-2.5">
              <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${t.bg} ${t.text}`}>
                <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden>
                  <path d={t.icon} />
                </svg>
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] font-medium text-white/90">{MEAL_LABELS[type]}</p>
                {pieno ? (
                  <p className="flex flex-wrap gap-x-2 text-[11.5px] text-white/45">
                    {MACROS.map((mac) => (
                      <span key={mac.key} className="inline-flex items-center gap-1">
                        <span className={`h-1.5 w-1.5 rounded-full ${mac.dot}`} />
                        {Math.round(m[mac.key])} g
                      </span>
                    ))}
                  </p>
                ) : (
                  <p className="text-[11.5px] text-white/30">niente segnato</p>
                )}
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-[14px] font-semibold tabular-nums text-white">
                  {Math.round(m?.kcal ?? 0)}
                  <span className="ml-0.5 text-[11px] font-normal text-white/40">kcal</span>
                </p>
                {pieno && totale > 0 && (
                  <p className="text-[11px] text-white/35">{Math.round(((m.kcal ?? 0) * 100) / totale)}%</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-white/35">
        {MACROS.map((mac) => (
          <span key={mac.key} className="inline-flex items-center gap-1">
            <span className={`h-1.5 w-1.5 rounded-full ${mac.dot}`} /> {mac.label.toLowerCase()}
          </span>
        ))}
      </p>
    </div>
  );
}
