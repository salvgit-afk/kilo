"use client";

/**
 * Banner dei promemoria, dentro la sezione a cui si riferisce.
 *
 * Il pallino nel menu dice già *dove* manca qualcosa; il banner, aperta la
 * sezione, dice *cosa*: gli integratori in Integratori, i pasti in Diario,
 * l'allenamento del giorno in Scheda. Nelle altre sezioni non compare.
 *
 * Per non dare fastidio:
 *  - ricorda solo abitudini che l'utente ha già (lo decide il backend);
 *  - la X lo nasconde fino al giorno dopo, e dal Profilo si spegne del tutto;
 *  - l'integratore si segna direttamente dal banner.
 *
 * Le preferenze vivono in `localStorage`: valgono per questo browser, e se
 * non è disponibile il banner funziona lo stesso (solo senza memoria).
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { REMINDERS_EVENT, api, localDate, notifyLogged, type DailyReminders } from "@/lib/api";
import type { SectionId } from "@/components/Shell";
import { supplementName } from "@/components/SupplementDiary";

const DISMISSED_KEY = "kilo-promemoria-nascosto";
const DISABLED_KEY = "kilo-promemoria-disattivati";

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage non disponibile: la scelta vale solo per questa visita */
  }
}

export const reminderSettings = {
  enabled: () => readStorage(DISABLED_KEY) !== "1",
  setEnabled: (on: boolean) => {
    writeStorage(DISABLED_KEY, on ? null : "1");
    notifyLogged();
  },
};

export function ReminderBanner({ profileId, section }: { profileId: number; section: SectionId }) {
  const [data, setData] = useState<DailyReminders | null>(null);
  const [hidden, setHidden] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

  const refresh = useCallback(() => {
    const oggi = localDate();
    const spento = !reminderSettings.enabled() || readStorage(DISMISSED_KEY) === oggi;
    setHidden(spento);
    if (spento) return;
    api
      .get<DailyReminders>(`/profile/${profileId}/reminders?today=${oggi}`)
      .then(setData)
      .catch(() => setData(null));
  }, [profileId]);

  useEffect(() => {
    refresh();
  }, [refresh, section]);

  // Si aggiorna quando qualcosa viene segnato, quando si torna sulla scheda
  // del browser e, per chi la tiene aperta, ogni mezz'ora (per il cambio di
  // giorno).
  useEffect(() => {
    const onVisible = () => document.visibilityState === "visible" && refresh();
    window.addEventListener(REMINDERS_EVENT, refresh);
    document.addEventListener("visibilitychange", onVisible);
    const timer = setInterval(refresh, 30 * 60_000);
    return () => {
      window.removeEventListener(REMINDERS_EVENT, refresh);
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(timer);
    };
  }, [refresh]);

  function dismiss() {
    writeStorage(DISMISSED_KEY, localDate());
    setHidden(true);
  }

  async function markTaken(item: DailyReminders["supplements"][number]) {
    setSaving(item.supplement_id);
    try {
      const oggi = localDate();
      await api.put(`/supplements/${item.supplement_id}/intake?profile_id=${profileId}&today=${oggi}`, {
        date: oggi,
        doses: item.doses_taken + 1,
      });
      notifyLogged();
    } finally {
      setSaving(null);
    }
  }

  const supplements = section === "integratori" ? (data?.supplements ?? []) : [];
  const meals = section === "diario" && !!data?.meals_missing;
  const workouts = section === "scheda" ? (data?.workouts_due ?? []) : [];
  const visible = !hidden && data !== null && (supplements.length > 0 || meals || workouts.length > 0);

  return (
    <AnimatePresence initial={false}>
      {visible && (
        <motion.div
          key="promemoria"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden"
        >
          <div
            role="status"
            className="mb-4 flex items-start gap-3 rounded-xl border border-iris-400/20 bg-iris-400/[0.07] py-2 pl-3.5 pr-1.5"
          >
            <svg viewBox="0 0 24 24" className="mt-[7px] h-4 w-4 shrink-0 fill-iris-300">
              <path d="M12 22a2.5 2.5 0 0 0 2.4-2h-4.8a2.5 2.5 0 0 0 2.4 2Zm7-6V11a7 7 0 0 0-5.5-6.8V3.5a1.5 1.5 0 0 0-3 0v.7A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z" />
            </svg>

            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1.5 py-0.5">
              <span className="text-[12.5px] text-white/65">
                {workouts.length > 0
                  ? `Oggi è giorno di allenamento: ${workouts.map((w) => w.plan_name).join(", ")}`
                  : meals
                    ? "Oggi non hai ancora segnato i pasti nel diario"
                    : "Oggi non hai ancora segnato"}
              </span>

              {supplements.map((s) => (
                <button
                  key={s.supplement_id}
                  disabled={saving === s.supplement_id}
                  onClick={() => markTaken(s)}
                  title="Segna un'assunzione di oggi"
                  className="flex items-center gap-1.5 rounded-lg border border-lime-400/25 bg-lime-400/[0.07] px-2 py-1 text-[12px] font-medium text-lime-200 transition hover:border-lime-400/50 hover:bg-lime-400/[0.14] disabled:opacity-50"
                >
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                    <path d="m9.5 16.2-4-4L4 13.7l5.5 5.5L20 8.7l-1.5-1.5-9 9Z" />
                  </svg>
                  {supplementName(s)}
                  {s.doses_required > 1 && (
                    <span className="font-mono tabular-nums text-lime-200/60">
                      {s.doses_taken}/{s.doses_required}
                    </span>
                  )}
                </button>
              ))}

            </div>

            <button
              onClick={dismiss}
              aria-label="Nascondi fino a domani"
              title="Nascondi fino a domani"
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white/40 transition hover:bg-white/[0.07] hover:text-white"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2.3}
                strokeLinecap="round"
              >
                <path d="M6 6l12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
