"use client";

/**
 * Diario delle assunzioni: la scheda "Diario" della sezione Integratori.
 *
 * Per ogni integratore dichiarato l'utente segna le assunzioni del giorno e
 * vede da quanti giorni lo prende, la serie in corso e i giorni saltati.
 * Le ultime 4 settimane sono una striscia di quadratini: un clic su un
 * giorno lo seleziona, così si può segnare anche un'assunzione dimenticata.
 *
 * Dove le fonti indicano una durata (creatina senza carico, beta-alanina,
 * ashwagandha) compare a che punto si è: è un'informazione, non un obiettivo.
 */

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import {
  SUPPLEMENT_LABELS,
  api,
  localDate,
  notifyLogged,
  shiftDate,
  type SupplementIntake,
} from "@/lib/api";
import { Card, Notice, SourceTags, Spinner } from "@/components/ui";

export function supplementName(s: { kind: string; product_name: string | null }) {
  if (s.kind === "other" && s.product_name) return s.product_name;
  return SUPPLEMENT_LABELS[s.kind] ?? s.kind;
}

function dayLabel(date: string, today: string) {
  if (date === today) return "Oggi";
  if (date === shiftDate(today, -1)) return "Ieri";
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("it-IT", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function shortDate(date: string) {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

export function SupplementDiary({ profileId }: { profileId: number }) {
  const [today, setToday] = useState(localDate);
  const [selected, setSelected] = useState(today);
  const [items, setItems] = useState<SupplementIntake[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<number | null>(null);

  const load = useCallback(async () => {
    const oggi = localDate();
    setToday(oggi);
    try {
      setItems(
        await api.get<SupplementIntake[]>(`/supplements/intake?profile_id=${profileId}&today=${oggi}`)
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Diario non disponibile");
    }
  }, [profileId]);

  useEffect(() => {
    load();
  }, [load]);

  async function setDoses(item: SupplementIntake, doses: number) {
    setSaving(item.supplement_id);
    setError(null);
    try {
      const aggiornato = await api.put<SupplementIntake>(
        `/supplements/${item.supplement_id}/intake?profile_id=${profileId}&today=${today}`,
        { date: selected, doses }
      );
      setItems((prev) =>
        prev?.map((i) => (i.supplement_id === aggiornato.supplement_id ? aggiornato : i)) ?? null
      );
      notifyLogged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Salvataggio non riuscito");
    } finally {
      setSaving(null);
    }
  }

  if (!items) return error ? <Notice>{error}</Notice> : <Spinner label="Carico il diario…" />;

  const span = items[0]?.history_days ?? 28;
  const first = shiftDate(today, -(span - 1));
  const days = Array.from({ length: span }, (_, i) => shiftDate(first, i));

  return (
    <div className="space-y-3">
      <Card>
        <div className="flex items-center justify-between gap-3 px-3 py-2.5">
          <button
            onClick={() => setSelected(shiftDate(selected, -1))}
            disabled={selected <= first}
            aria-label="Giorno precedente"
            className="grid h-9 w-9 place-items-center rounded-lg text-white/50 transition hover:bg-white/[0.06] hover:text-white disabled:opacity-25 disabled:hover:bg-transparent"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
              <path d="M15.4 7.4 14 6l-6 6 6 6 1.4-1.4-4.6-4.6 4.6-4.6Z" />
            </svg>
          </button>
          <div className="text-center">
            <p className="text-[14px] font-semibold text-white first-letter:uppercase">{dayLabel(selected, today)}</p>
            {selected !== today ? (
              <button
                onClick={() => setSelected(today)}
                className="text-[11.5px] text-lime-300/80 transition hover:text-lime-200"
              >
                Torna a oggi
              </button>
            ) : (
              <p className="text-[11.5px] text-white/35">Segna cosa hai preso</p>
            )}
          </div>
          <button
            onClick={() => setSelected(shiftDate(selected, 1))}
            disabled={selected >= today}
            aria-label="Giorno successivo"
            className="grid h-9 w-9 place-items-center rounded-lg text-white/50 transition hover:bg-white/[0.06] hover:text-white disabled:opacity-25 disabled:hover:bg-transparent"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
              <path d="M8.6 16.6 10 18l6-6-6-6-1.4 1.4 4.6 4.6-4.6 4.6Z" />
            </svg>
          </button>
        </div>
      </Card>

      {error && <Notice>{error}</Notice>}

      {items.map((item, i) => {
        const byDate = Object.fromEntries(item.history.map((h) => [h.date, h.doses]));
        const doses = byDate[selected] ?? 0;
        const done = doses >= item.doses_required;
        const busy = saving === item.supplement_id;
        const dose = item.dose_amount
          ? `${item.dose_amount.toLocaleString("it-IT")} ${item.dose_unit ?? ""}`
          : null;

        return (
          <motion.div
            key={item.supplement_id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass sheen overflow-hidden"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
              <div className="min-w-0">
                <h3 className="text-[15px] font-semibold text-white">{supplementName(item)}</h3>
                <p className="mt-0.5 text-[12px] text-white/35">
                  {[
                    item.kind !== "other" ? item.product_name : null,
                    dose,
                    item.doses_required > 1 ? `${item.doses_required} volte al giorno` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "dose non indicata"}
                </p>
              </div>

              {item.doses_required === 1 ? (
                <button
                  disabled={busy}
                  onClick={() => setDoses(item, done ? 0 : 1)}
                  className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-[13px] font-medium transition disabled:opacity-60 ${
                    done
                      ? "border-lime-400/40 bg-lime-400/15 text-lime-200 hover:bg-lime-400/10"
                      : "border-white/12 bg-white/[0.04] text-white/70 hover:border-lime-400/35 hover:bg-lime-400/[0.08] hover:text-lime-200"
                  }`}
                >
                  <span
                    className={`grid h-5 w-5 place-items-center rounded-md border ${
                      done ? "border-lime-400 bg-lime-400 text-ink-900" : "border-white/25"
                    }`}
                  >
                    {done && (
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                        <path d="m9.5 16.2-4-4L4 13.7l5.5 5.5L20 8.7l-1.5-1.5-9 9Z" />
                      </svg>
                    )}
                  </span>
                  {done ? "Preso" : "Segna come preso"}
                </button>
              ) : (
                <div className="flex items-center gap-2.5">
                  <div className="flex gap-1.5">
                    {Array.from({ length: item.doses_required }, (_, n) => {
                      const filled = n < doses;
                      return (
                        <button
                          key={n}
                          disabled={busy}
                          // Clic sull'ultima dose segnata la toglie, sulle altre
                          // porta il conteggio fin lì.
                          onClick={() => setDoses(item, doses === n + 1 ? n : n + 1)}
                          aria-label={`Dose ${n + 1} di ${item.doses_required}`}
                          className={`h-8 w-8 rounded-lg border text-[12px] font-semibold transition disabled:opacity-60 ${
                            filled
                              ? "border-lime-400 bg-lime-400 text-ink-900"
                              : "border-white/15 bg-white/[0.03] text-white/40 hover:border-lime-400/40 hover:text-lime-200"
                          }`}
                        >
                          {n + 1}
                        </button>
                      );
                    })}
                  </div>
                  <span className="font-mono text-[12.5px] tabular-nums text-white/50">
                    {doses}/{item.doses_required}
                  </span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-3 border-t border-white/[0.06]">
              {[
                [item.days_taken, item.days_taken === 1 ? "giorno di assunzione" : "giorni di assunzione", `dal ${shortDate(item.since)}`],
                [item.current_streak, item.current_streak === 1 ? "giorno di fila" : "giorni di fila", "serie in corso"],
                [item.missed_days, item.missed_days === 1 ? "giorno saltato" : "giorni saltati", `ultime ${span / 7} settimane`],
              ].map(([value, text, hint], n) => (
                <div
                  key={n}
                  className={`px-3 py-3 text-center sm:px-5 ${n > 0 ? "border-l border-white/[0.06]" : ""}`}
                >
                  <p
                    className={`font-mono text-[20px] font-semibold tabular-nums ${
                      n === 2 && Number(value) > 0 ? "text-amber-200" : "text-white"
                    }`}
                  >
                    {value}
                  </p>
                  <p className="text-[11.5px] leading-tight text-white/55">{text}</p>
                  <p className="text-[10.5px] text-white/30">{hint}</p>
                </div>
              ))}
            </div>

            <div className="border-t border-white/[0.06] px-5 py-3.5">
              <div className="grid grid-cols-[repeat(14,minmax(0,1fr))] gap-1 sm:grid-cols-[repeat(28,minmax(0,1fr))]">
                {days.map((d) => {
                  const n = byDate[d] ?? 0;
                  const beforeStart = d < item.since;
                  const state =
                    n >= item.doses_required
                      ? "bg-lime-400 border-lime-400"
                      : n > 0
                        ? "bg-lime-400/35 border-lime-400/50"
                        : d === today || beforeStart
                          ? "bg-white/[0.03] border-white/10"
                          : "bg-rose-400/20 border-rose-400/45";
                  return (
                    <button
                      key={d}
                      onClick={() => setSelected(d)}
                      title={`${shortDate(d)}: ${
                        n ? `${n}/${item.doses_required}` : beforeStart ? "prima dell'inizio" : d === today ? "da segnare" : "saltato"
                      }`}
                      aria-label={shortDate(d)}
                      className={`aspect-square rounded-[4px] border transition hover:scale-110 ${state} ${
                        d === selected ? "ring-2 ring-white/70 ring-offset-1 ring-offset-ink-900" : ""
                      }`}
                    />
                  );
                })}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-white/35">
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-[2px] bg-lime-400" /> preso
                </span>
                {item.doses_required > 1 && (
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-[2px] bg-lime-400/35" /> in parte
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-[2px] border border-rose-400/45 bg-rose-400/20" /> saltato
                </span>
                <span>un clic su un giorno per segnarlo</span>
              </div>
            </div>

            {item.milestone && (
              <div className="space-y-2 border-t border-white/[0.06] px-5 py-3.5">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-[12.5px] text-white/65">
                    {item.days_taken >= item.milestone.days
                      ? `${item.days_taken} giorni: durata indicata dalle fonti raggiunta`
                      : `${item.days_taken} di ${item.milestone.days} giorni`}
                  </p>
                  <span className="font-mono text-[11.5px] tabular-nums text-white/35">
                    {Math.min(100, Math.round((item.days_taken / item.milestone.days) * 100))}%
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-lime-500 to-lime-400"
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (item.days_taken / item.milestone.days) * 100)}%` }}
                    transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
                <p className="text-[11.5px] leading-snug text-white/40">
                  {item.days_taken >= item.milestone.days ? item.milestone.reached_note : item.milestone.note}
                </p>
                <SourceTags tags={[item.milestone.knowledge_tag]} />
              </div>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
