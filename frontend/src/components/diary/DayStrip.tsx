"use client";

/**
 * Storico del diario: sette giorni in una striscia.
 *
 * Ogni giorno ha un anello che si riempie verso il target di calorie (ambra
 * se l'ha superato, vuoto se non c'è niente di segnato). La finestra sono gli
 * ultimi sette giorni fino a oggi, non la settimana da lunedì: di lunedì si
 * vedrebbe solo oggi e sei giorni futuri spenti. Le frecce scorrono di sette
 * giorni; oltre oggi non si va, non c'è niente da segnare in anticipo.
 */

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api, shiftDate, type DiaryDays } from "@/lib/api";

const GIORNI = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"];

function parse(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** L'ultimo giorno della finestra che mostra `day`: oggi, se possibile. */
function windowEnd(day: string, today: string): string {
  const fine = shiftDate(day, 3);
  return fine > today ? today : fine;
}

/** "Oggi", "Ieri" o il giorno della settimana; sotto, la data per esteso. */
export function dayTitle(day: string, today: string): { title: string; date: string } {
  const lungo = parse(day).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
  if (day === today) return { title: "Oggi", date: lungo };
  if (day === shiftDate(today, -1)) return { title: "Ieri", date: lungo };
  const [giorno, ...resto] = lungo.split(" ");
  return { title: giorno.charAt(0).toUpperCase() + giorno.slice(1), date: resto.join(" ") };
}

export function DayStrip({
  profileId,
  day,
  today,
  refreshKey,
  onChange,
}: {
  profileId: number;
  day: string;
  today: string;
  /** Cambia quando si segna o si toglie qualcosa: gli anelli vanno ricaricati. */
  refreshKey: number;
  onChange: (day: string) => void;
}) {
  const [end, setEnd] = useState(today);
  const [data, setData] = useState<DiaryDays | null>(null);
  const start = shiftDate(end, -6);

  // Un giorno fuori dalla finestra ("Torna a oggi") la fa spostare.
  useEffect(() => {
    setEnd((e) => (day > e || day < shiftDate(e, -6) ? windowEnd(day, today) : e));
  }, [day, today]);

  useEffect(() => {
    let annullato = false;
    api
      .get<DiaryDays>(`/nutrition/diary/days?profile_id=${profileId}&start=${start}&end=${end}`)
      .then((d) => !annullato && setData(d))
      .catch(() => !annullato && setData(null));
    return () => {
      annullato = true;
    };
  }, [profileId, start, end, refreshKey]);

  const kcal = Object.fromEntries((data?.days ?? []).map((d) => [d.date, d.kcal]));
  const { title, date } = dayTitle(day, today);

  return (
    <section className="glass p-3" aria-label="Scegli il giorno del diario">
      <div className="mb-2.5 flex min-h-[28px] items-center justify-between gap-2 px-1">
        <p className="min-w-0 truncate text-[14px] font-semibold text-white">
          {title} <span className="font-normal text-white/45">· {date}</span>
        </p>
        {day !== today && (
          <button
            onClick={() => onChange(today)}
            className="shrink-0 rounded-full border border-lime-400/40 px-2.5 py-1 text-[11.5px] font-medium text-lime-200 transition hover:bg-lime-400/10"
          >
            Torna a oggi
          </button>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Arrow dir="prev" onClick={() => setEnd(shiftDate(end, -7))} label="Giorni precedenti" />
        <div className="grid flex-1 grid-cols-7 gap-0.5">
          {Array.from({ length: 7 }, (_, i) => {
            const iso = shiftDate(start, i);
            const nome = GIORNI[parse(iso).getDay()];
            const scelto = iso === day;
            const valore = kcal[iso];
            const quota = valore && data?.target_kcal ? valore / data.target_kcal : 0;
            return (
              <button
                key={iso}
                onClick={() => onChange(iso)}
                aria-pressed={scelto}
                aria-label={`${dayTitle(iso, today).title} ${dayTitle(iso, today).date}${valore ? `, ${Math.round(valore)} kcal` : ""}`}
                className={`relative flex flex-col items-center gap-1 rounded-xl py-1.5 transition ${
                  scelto ? "" : "hover:bg-white/[0.04]"
                }`}
              >
                {scelto && (
                  <motion.span
                    layoutId="diary-day"
                    className="absolute inset-0 rounded-xl bg-lime-400/15 ring-1 ring-lime-400/60"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className={`relative text-[10px] uppercase ${scelto ? "text-lime-200" : iso === today ? "text-white/70" : "text-white/40"}`}>
                  {nome}
                </span>
                <DayRing value={quota} over={quota > 1.05}>
                  <span className={`font-mono text-[11px] font-semibold ${scelto ? "text-white" : "text-white/70"}`}>
                    {parse(iso).getDate()}
                  </span>
                </DayRing>
              </button>
            );
          })}
        </div>
        <Arrow
          dir="next"
          onClick={() => setEnd(shiftDate(end, 7) > today ? today : shiftDate(end, 7))}
          label="Giorni successivi"
          disabled={end >= today}
        />
      </div>
    </section>
  );
}

function DayRing({ value, over, children }: { value: number; over: boolean; children: React.ReactNode }) {
  const size = 30;
  const stroke = 3;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const colore = over ? "#fcd34d" : "#aed44a";
  return (
    <span className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
        {value > 0 && (
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={colore}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: c * (1 - Math.min(value, 1)) }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          />
        )}
      </svg>
      <span className="relative">{children}</span>
    </span>
  );
}

function Arrow({ dir, onClick, label, disabled = false }: { dir: "prev" | "next"; onClick: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="grid h-9 w-8 shrink-0 place-items-center rounded-xl bg-white/[0.05] text-white/60 transition hover:text-white disabled:opacity-25"
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.4}>
        <path d={dir === "prev" ? "M15 5l-7 7 7 7" : "M9 5l7 7-7 7"} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

