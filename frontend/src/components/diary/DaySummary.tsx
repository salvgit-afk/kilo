"use client";

/**
 * Riepilogo della giornata, in due viste nello stesso riquadro.
 *
 *  - **Totale**: calorie sul target e le barre dei macro, come sempre;
 *  - **Per pasto**: come si distribuiscono le calorie fra colazione,
 *    spuntino, pranzo e cena, e i macro di ciascuno. Serve a capire *dove*
 *    si è mangiato, non solo quanto.
 *
 * Nel totale i previsti sono un arco tenue dopo le calorie segnate e una
 * parte chiara nella barra delle proteine: si vede come chiuderebbe la
 * giornata, senza contarli. Le proteine in polvere contano solo nei giorni
 * in cui si segnano (la riga col barattolo, la stessa spunta di Integratori)
 * e nella barra sono a righe, per distinguerle dal cibo.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { MEAL_LABELS, api, notifyLogged, type Diary, type ProteinPowder } from "@/lib/api";
import { ProgressRing, StatBar } from "@/components/ui";
import { MACROS, MEAL_ORDER, MEAL_THEME } from "@/components/diary/MealTimeline";
import { supplementName } from "@/components/SupplementDiary";

type View = "total" | "meals";

const STRIPES =
  "repeating-linear-gradient(135deg, rgba(174,212,74,0.95) 0 4px, rgba(174,212,74,0.4) 4px 8px)";

export function DaySummary({
  data,
  profileId,
  day,
  today,
  onChanged,
}: {
  data: Diary;
  profileId: number;
  day: string;
  today: string;
  onChanged: () => void | Promise<void>;
}) {
  const [view, setView] = useState<View>("total");
  const { totals, targets, remaining, progress } = data;
  const previste = data.planned_totals?.kcal ?? 0;
  const futuro = day > today;

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
                planned={targets.target_kcal > 0 ? previste / targets.target_kcal : 0}
                label={`${Math.round(totals.kcal ?? 0)}`}
                sublabel={`di ${Math.round(targets.target_kcal)} kcal`}
              />
              {previste > 0 && (
                <p className="-mt-1 rounded-full border border-dashed border-lime-400/40 px-3 py-1 text-[12px] text-lime-200/90">
                  + {Math.round(previste)} kcal previste{" "}
                  {futuro ? "" : day === today ? "da confermare" : "non confermate"}
                </p>
              )}
              <p className="text-center text-[12.5px] text-white/45">
                {futuro
                  ? "I previsti contano quando li confermi, il giorno stesso"
                  : remaining.kcal > 0
                    ? `Ti restano ${Math.round(remaining.kcal)} kcal`
                    : `Hai superato di ${Math.abs(Math.round(remaining.kcal))} kcal`}
              </p>
            </div>
            <div className="space-y-3 border-t border-white/[0.06] px-5 py-4">
              <ProteinBar
                total={totals.protein_g ?? 0}
                powder={data.powder_protein_g ?? 0}
                planned={data.planned_totals?.protein_g ?? 0}
                target={targets.protein_g}
              />
              {!futuro &&
                (data.protein_powders ?? []).map((p) => (
                  <PowderRow
                    key={p.supplement_id}
                    powder={p}
                    profileId={profileId}
                    day={day}
                    today={today}
                    onChanged={onChanged}
                  />
                ))}
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

/**
 * Barra delle proteine in tre parti: cibo (piena), polvere (a righe),
 * previste (tenue). Il numero in alto è il totale contato, senza i previsti.
 */
function ProteinBar({
  total,
  powder,
  planned,
  target,
}: {
  total: number;
  powder: number;
  planned: number;
  target: number;
}) {
  const cibo = Math.max(0, total - powder);
  const over = target > 0 && total / target > 1.02;
  const quota = (g: number) => (target > 0 ? Math.max(0, (g * 100) / target) : 0);
  const pCibo = Math.min(quota(cibo), 100);
  const pPolvere = Math.min(quota(powder), 100 - pCibo);
  const pPreviste = Math.min(quota(planned), 100 - pCibo - pPolvere);
  const anima = { duration: 0.8, ease: [0.22, 1, 0.36, 1] as const };

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-[12px] text-white/55">Proteine</span>
        <span className="font-mono text-[12px] tabular-nums text-white/80">
          {Math.round(total)}
          <span className="text-white/30">/{Math.round(target)}g</span>
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className={`h-full bg-gradient-to-r ${over ? "from-amber-300 to-amber-500" : "from-lime-400 to-lime-500"}`}
          initial={{ width: 0 }}
          animate={{ width: `${pCibo}%` }}
          transition={anima}
        />
        {pPolvere > 0 && (
          <motion.div
            className="h-full border-l-2 border-ink-800"
            style={{ background: STRIPES }}
            initial={{ width: 0 }}
            animate={{ width: `${pPolvere}%` }}
            transition={anima}
          />
        )}
        {pPreviste > 0 && (
          <motion.div
            className="h-full border-l-2 border-ink-800 bg-lime-400/25"
            initial={{ width: 0 }}
            animate={{ width: `${pPreviste}%` }}
            transition={anima}
          />
        )}
      </div>
      {(powder > 0 || planned > 0) && (
        <p className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-white/45">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-lime-400" /> cibo{" "}
            <b className="font-semibold text-white/75">{Math.round(cibo)} g</b>
          </span>
          {powder > 0 && (
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ background: STRIPES }} /> in polvere{" "}
              <b className="font-semibold text-white/75">{Math.round(powder)} g</b>
            </span>
          )}
          {planned > 0 && (
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm border border-dashed border-lime-400/60 bg-lime-400/20" /> previste{" "}
              <b className="font-semibold text-white/75">{Math.round(planned)} g</b>
            </span>
          )}
        </p>
      )}
    </div>
  );
}

const SHAKER =
  "M8 2h8v3l1.5 2v13a2 2 0 0 1-2 2h-7a2 2 0 0 1-2-2V7L8 5V2Zm2 2v1.6L8.5 7.5V9h7V7.5L14 5.6V4h-4Zm-1.5 7v9h7v-9h-7Z";

/**
 * Proteine in polvere del giorno: si segnano qui o in Integratori, è la
 * stessa assunzione. Senza la spunta non contano.
 */
function PowderRow({
  powder,
  profileId,
  day,
  today,
  onChanged,
}: {
  powder: ProteinPowder;
  profileId: number;
  day: string;
  today: string;
  onChanged: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dosi = powder.doses;
  const presa = dosi > 0;
  const perDose = Math.round(powder.protein_g_per_dose);

  async function set(doses: number) {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/supplements/${powder.supplement_id}/intake?profile_id=${profileId}&today=${today}`, {
        date: day,
        doses,
      });
      notifyLogged();
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito a segnarla");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`rounded-2xl border px-3 py-2.5 transition ${
        presa ? "border-lime-400/35 bg-lime-400/[0.07]" : "border-white/[0.08] bg-white/[0.03]"
      }`}
    >
      <div className="flex items-center gap-3">
        <span
          className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
            presa ? "bg-lime-400/20 text-lime-200" : "bg-white/[0.06] text-white/60"
          }`}
        >
          <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current" aria-hidden>
            <path d={SHAKER} />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13.5px] font-medium text-white/90">{supplementName(powder)}</p>
          <p className="text-[11.5px] text-white/45">
            {presa
              ? `${dosi} ${dosi === 1 ? "dose" : "dosi"} · ${perDose * dosi} g di proteine`
              : `${perDose} g di proteine a dose · conta solo se la segni`}
          </p>
        </div>
        {presa ? (
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={() => set(dosi - 1)}
              disabled={busy}
              aria-label={dosi === 1 ? "Non presa" : "Una dose in meno"}
              className="inline-flex items-center gap-1 rounded-xl bg-lime-400 px-3 py-2 text-[12.5px] font-semibold text-ink-900 transition disabled:opacity-60"
            >
              {dosi === 1 ? "✓ Presa" : "−"}
            </button>
            <button
              onClick={() => set(dosi + 1)}
              disabled={busy}
              aria-label="Un'altra dose"
              className="grid h-9 w-9 place-items-center rounded-xl border border-lime-400/40 bg-lime-400/[0.12] text-[16px] font-semibold text-lime-200 transition disabled:opacity-60"
            >
              +
            </button>
          </div>
        ) : (
          <button
            onClick={() => set(1)}
            disabled={busy}
            className="shrink-0 rounded-xl border border-lime-400/45 bg-lime-400/[0.12] px-3 py-2 text-[12.5px] font-semibold text-lime-200 transition hover:bg-lime-400/25 disabled:opacity-60"
          >
            {busy ? "Segno…" : day === today ? "Segna per oggi" : "Segna"}
          </button>
        )}
      </div>
      {error && <p className="mt-1.5 text-[12px] text-rose-200">{error}</p>}
    </div>
  );
}
