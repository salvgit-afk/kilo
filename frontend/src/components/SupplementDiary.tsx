"use client";

/**
 * Diario delle assunzioni: la scheda "Diario" della sezione Integratori.
 *
 * Per ogni integratore dichiarato l'utente segna le assunzioni del giorno e
 * vede, in un anello, quanti giorni l'ha preso **sul periodo reale** (dal
 * primo giorno segnato: "16 su 18"), più la serie in corso e i saltati. Gli
 * ultimi 7 giorni sono pillole da toccare; il mese intero si apre a richiesta.
 * Niente percentuali da interpretare: solo giorni contati.
 *
 * Dove le fonti indicano una durata (creatina senza carico, beta-alanina,
 * ashwagandha) compare come fase con un nome ("Fase di saturazione") e con
 * scritto cosa succede dopo: è un'informazione, non la fine dell'assunzione.
 */

import { AnimatePresence, motion } from "framer-motion";
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
  const [monthOpen, setMonthOpen] = useState<Record<number, boolean>>({});

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
    // Tornando sull'app si ricarica: se nel frattempo è passata la mezzanotte
    // "oggi", la settimana e il mese del calendario si spostano da soli.
    const onVisible = () => document.visibilityState === "visible" && load();
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load]);

  // Con una dose al giorno il tocco segna o toglie quel giorno; con più dosi
  // lo seleziona, e le dosi si segnano in alto.
  function tapDay(item: SupplementIntake, date: string) {
    if (date > today) return;
    setSelected(date);
    if (item.doses_required !== 1) return;
    const presa = (item.history.find((h) => h.date === date)?.doses ?? 0) >= 1;
    setDoses(item, presa ? 0 : 1, date);
  }

  async function setDoses(item: SupplementIntake, doses: number, date: string = selected) {
    setSaving(item.supplement_id);
    setError(null);
    try {
      const aggiornato = await api.put<SupplementIntake>(
        `/supplements/${item.supplement_id}/intake?profile_id=${profileId}&today=${today}`,
        { date, doses }
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

            <div className="border-t border-white/[0.06] px-4 py-4 sm:px-5">
              <div className="flex items-center gap-4 sm:gap-5">
                <IntakeRing taken={item.days_taken} tracked={item.tracked_days} />
                <dl className="min-w-0 flex-1 divide-y divide-white/[0.06] text-[13px]">
                  <Kpi label="Di fila">
                    {item.current_streak > 0 && <Flame />}
                    {item.current_streak} {item.current_streak === 1 ? "giorno" : "giorni"}
                  </Kpi>
                  <Kpi label="Saltati" warn={saltati(item) > 0}>
                    {saltati(item)}
                  </Kpi>
                  <Kpi label="Dal">{item.tracked_days ? shortDate(firstDay(item, today)) : "—"}</Kpi>
                </dl>
              </div>

              <DayPills
                item={item}
                days={days.slice(-7)}
                today={today}
                selected={selected}
                busy={busy}
                onTap={(d) => tapDay(item, d)}
              />

              <button
                onClick={() => setMonthOpen((m) => ({ ...m, [item.supplement_id]: !m[item.supplement_id] }))}
                className="mt-3 w-full rounded-xl py-2 text-[12.5px] font-medium text-white/45 transition hover:bg-white/[0.04] hover:text-white/80"
                aria-expanded={!!monthOpen[item.supplement_id]}
              >
                {monthOpen[item.supplement_id] ? "Nascondi il mese" : "Vedi il mese"}
              </button>
              <AnimatePresence initial={false}>
                {monthOpen[item.supplement_id] && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <MonthGrid
                      item={item}
                      today={today}
                      selected={selected}
                      busy={busy}
                      onTap={(d) => tapDay(item, d)}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
              <p className="mt-1 text-center text-[11.5px] text-white/30">
                {item.doses_required === 1
                  ? "Tocca un giorno per segnarlo o toglierlo"
                  : "Tocca un giorno per sceglierlo, poi segna le dosi in alto"}
              </p>
            </div>

            {item.milestone && <Phase item={item} />}
          </motion.div>
        );
      })}
    </div>
  );
}


// --- Pezzi della card -------------------------------------------------------------------

function saltati(item: SupplementIntake): number {
  return Math.max(0, item.tracked_days - item.days_taken);
}

/** Il primo giorno segnato, da cui partono i giorni contati. */
function firstDay(item: SupplementIntake, today: string): string {
  return shiftDate(today, -(item.tracked_days - (item.history.some((h) => h.date === today) ? 1 : 0)));
}

type DayState = "taken" | "partial" | "missed" | "before" | "today" | "future";

function dayState(item: SupplementIntake, date: string, today: string): DayState {
  if (date > today) return "future";
  const n = item.history.find((h) => h.date === date)?.doses ?? 0;
  if (n >= item.doses_required) return "taken";
  if (n > 0) return "partial";
  if (date === today) return "today";
  if (!item.tracked_days || date < firstDay(item, today)) return "before";
  return "missed";
}

const DAY_STYLE: Record<DayState, string> = {
  taken: "border-lime-400/60 bg-lime-400/[0.18] text-lime-200",
  partial: "border-lime-400/40 bg-lime-400/[0.08] text-lime-200/70",
  missed: "border-rose-400/35 bg-transparent text-rose-200/60",
  before: "border-white/[0.06] bg-white/[0.02] text-white/20",
  today: "border-dashed border-white/45 bg-transparent text-white/60",
  future: "border-transparent bg-transparent text-white/15",
};

function Check() {
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={3.2}>
      <path d="m5 12.5 4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Flame() {
  return (
    <svg viewBox="0 0 24 24" className="mr-1 inline h-3.5 w-3.5 -translate-y-px fill-lime-400">
      <path d="M13.5 1s1 3.5-1.5 6.5C9.6 10.4 8 12 8 15a4 4 0 0 0 8 0c0-1.3-.4-2.3-1-3 2.4.8 4 3.3 4 6a7 7 0 1 1-14 0c0-5 4-7.5 5.5-10.5C11.6 5.2 12 3 13.5 1Z" />
    </svg>
  );
}

/** Quanti giorni presi sul periodo reale: niente percentuale, solo giorni. */
function IntakeRing({ taken, tracked }: { taken: number; tracked: number }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  const frazione = tracked ? Math.min(1, taken / tracked) : 0;
  return (
    <div className="relative h-[104px] w-[104px] shrink-0">
      <svg viewBox="0 0 104 104" className="h-full w-full -rotate-90">
        <circle cx="52" cy="52" r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="9" />
        <motion.circle
          cx="52"
          cy="52"
          r={r}
          fill="none"
          stroke="url(#intake-ring)"
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - frazione) }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        />
        <defs>
          <linearGradient id="intake-ring" x1="0" x2="1">
            <stop offset="0" stopColor="#8fbf24" />
            <stop offset="1" stopColor="#aed44a" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        {tracked ? (
          <div>
            <p className="font-mono text-[24px] font-semibold leading-none tabular-nums text-white">{taken}</p>
            <p className="mt-1 text-[11px] leading-tight text-white/45">
              su {tracked} {tracked === 1 ? "giorno" : "giorni"}
            </p>
          </div>
        ) : (
          <p className="px-3 text-[11.5px] leading-tight text-white/45">Inizia oggi</p>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, warn = false, children }: { label: string; warn?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 first:pt-0 last:pb-0">
      <dt className="text-white/45">{label}</dt>
      <dd className={`font-semibold tabular-nums ${warn ? "text-amber-200" : "text-white"}`}>{children}</dd>
    </div>
  );
}

function weekdayLetter(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return ["D", "L", "M", "M", "G", "V", "S"][new Date(y, m - 1, d).getDay()];
}

function DayPills({
  item,
  days,
  today,
  selected,
  busy,
  onTap,
}: {
  item: SupplementIntake;
  days: string[];
  today: string;
  selected: string;
  busy: boolean;
  onTap: (date: string) => void;
}) {
  return (
    <div className="mx-auto mt-4 grid max-w-[340px] grid-cols-7 gap-1">
      {days.map((d) => {
        const st = dayState(item, d, today);
        return (
          <div key={d} className="text-center">
            <motion.button
              whileTap={{ scale: 0.9 }}
              disabled={busy || st === "future"}
              onClick={() => onTap(d)}
              aria-label={`${shortDate(d)}: ${st === "taken" ? "preso" : st === "missed" ? "saltato" : "da segnare"}`}
              className={`mx-auto grid h-9 w-9 place-items-center rounded-full border transition disabled:opacity-60 ${DAY_STYLE[st]} ${
                d === selected && item.doses_required > 1 ? "ring-2 ring-white/60 ring-offset-2 ring-offset-ink-900" : ""
              }`}
            >
              {st === "taken" ? <Check /> : st === "partial" ? <span className="text-[11px] font-semibold">½</span> : null}
            </motion.button>
            <span className={`mt-1 block text-[10.5px] ${d === today ? "font-semibold text-white/70" : "text-white/35"}`}>
              {d === today ? "oggi" : weekdayLetter(d)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// I mesi che devono ancora venire si possono guardare, spenti come i giorni
// futuri: si vede cosa arriva, senza poter segnare niente.
const MESI_AVANTI = 2;

const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];

function iso(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/**
 * Il calendario di un mese vero (dall'1 all'ultimo giorno), sfogliabile con
 * le frecce. Colonne da lunedì a domenica; i giorni futuri si vedono ma sono
 * spenti, quelli prima dell'inizio appena accennati.
 */
function MonthGrid({
  item,
  today,
  selected,
  busy,
  onTap,
}: {
  item: SupplementIntake;
  today: string;
  selected: string;
  busy: boolean;
  onTap: (date: string) => void;
}) {
  const [ty, tm] = today.split("-").map(Number);
  const [scarto, setScarto] = useState(0); // 0 = mese corrente, -1 = precedente
  const base = new Date(ty, tm - 1 + scarto, 1);
  const anno = base.getFullYear();
  const mese = base.getMonth();
  const giorni = new Date(anno, mese + 1, 0).getDate();
  const vuoti = (base.getDay() + 6) % 7; // lunedì = 0
  // Si torna indietro fino al mese del primo giorno segnato (al massimo 3 mesi).
  const inizio = item.tracked_days ? firstDay(item, today) : today;
  const [iy, im] = inizio.split("-").map(Number);
  const mesiIndietro = Math.min(3, (ty - iy) * 12 + (tm - im));

  const freccia = (dir: -1 | 1) => (
    <button
      onClick={() => setScarto((n) => n + dir)}
      disabled={dir < 0 ? scarto <= -mesiIndietro : scarto >= MESI_AVANTI}
      aria-label={dir < 0 ? "Mese precedente" : "Mese successivo"}
      className="grid h-8 w-8 place-items-center rounded-full text-white/50 transition hover:bg-white/[0.06] hover:text-white disabled:opacity-20"
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
        <path d={dir < 0 ? "M15.4 7.4 14 6l-6 6 6 6 1.4-1.4-4.6-4.6 4.6-4.6Z" : "M8.6 16.6 10 18l6-6-6-6-1.4 1.4 4.6 4.6-4.6 4.6Z"} />
      </svg>
    </button>
  );

  return (
    <div className="mx-auto mt-2 max-w-[300px]">
      <div className="mb-1.5 flex items-center justify-between">
        {freccia(-1)}
        <p className="text-[13px] font-medium capitalize text-white/75">
          {MESI[mese]} {anno !== ty ? anno : ""}
        </p>
        {freccia(1)}
      </div>
      <div className="grid grid-cols-7 gap-y-1">
        {["L", "M", "M", "G", "V", "S", "D"].map((l, k) => (
          <span key={k} className="pb-0.5 text-center text-[10.5px] text-white/30">
            {l}
          </span>
        ))}
        {Array.from({ length: vuoti }, (_, k) => (
          <span key={`v${k}`} />
        ))}
        {Array.from({ length: giorni }, (_, k) => {
          const d = iso(anno, mese, k + 1);
          const st = dayState(item, d, today);
          return (
            <div key={d} className="grid place-items-center">
              <button
                disabled={busy || st === "future"}
                onClick={() => onTap(d)}
                aria-label={shortDate(d)}
                className={`grid h-7 w-7 place-items-center rounded-full border text-[10.5px] font-medium tabular-nums transition disabled:cursor-default ${MINI_STYLE[st]} ${
                  d === selected && item.doses_required > 1 ? "ring-2 ring-white/60" : ""
                }`}
              >
                {k + 1}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Nel calendario i giorni sono piccoli: pieni solo quelli presi.
const MINI_STYLE: Record<DayState, string> = {
  taken: "border-transparent bg-lime-400 text-ink-900",
  partial: "border-lime-400/50 bg-lime-400/20 text-lime-100",
  missed: "border-rose-400/40 text-rose-200/70",
  before: "border-transparent text-white/25",
  today: "border-white/60 text-white",
  future: "border-transparent text-white/15",
};

/** La fase indicata dalle fonti, con il suo nome e cosa succede dopo. */
function Phase({ item }: { item: SupplementIntake }) {
  const f = item.milestone!;
  const raggiunta = item.days_taken >= f.days;
  const oltre = item.days_taken - f.days;
  return (
    <div className="border-t border-white/[0.06] px-4 py-4 sm:px-5">
      <div className="rounded-2xl border border-iris-400/25 bg-iris-400/[0.08] px-3.5 py-3">
        <div className="flex items-baseline justify-between gap-3 text-[13px]">
          <p className="font-medium text-white/85">
            {raggiunta ? f.reached_label : f.label}
            <span className="font-normal text-white/50">
              {" · "}
              {raggiunta
                ? oltre > 0
                  ? `da ${oltre} ${oltre === 1 ? "giorno" : "giorni"}`
                  : "da oggi"
                : `${item.days_taken} di ${f.days} giorni`}
            </span>
          </p>
          {!raggiunta && (
            <span className="font-mono text-[12px] tabular-nums text-white/40">
              {Math.round((item.days_taken / f.days) * 100)}%
            </span>
          )}
        </div>
        {!raggiunta && (
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-iris-400 to-iris-300"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, (item.days_taken / f.days) * 100)}%` }}
              transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
        )}
        <p className="mt-2 text-[12px] leading-snug text-white/55">{raggiunta ? f.reached_note : f.note}</p>
        <div className="mt-2">
          <SourceTags tags={[f.knowledge_tag]} />
        </div>
      </div>
    </div>
  );
}
