"use client";

/**
 * "La tua settimana": il riepilogo della settimana conclusa, in Oggi.
 *
 * Numeri calcolati (allenamenti, peso, proteine, integratori) e una sola
 * cosa su cui concentrarsi. Il commento discorsivo arriva solo se l'utente
 * lo chiede, dalla chat: così non consuma la quota dell'LLM a ogni apertura.
 */

import { useEffect, useState } from "react";
import { api, localDate, type WeeklySummary } from "@/lib/api";
import { askCoach } from "@/lib/coach";
import { Card } from "@/components/ui";
import { Mascot } from "@/components/Mascot";
import { supplementName } from "@/components/SupplementDiary";

function shortDate(date: string) {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

const fmt = (n: number, decimals = 0) =>
  n.toLocaleString("it-IT", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export function WeeklySummaryCard({ profileId }: { profileId: number }) {
  const [data, setData] = useState<WeeklySummary | null>(null);

  useEffect(() => {
    api
      .get<WeeklySummary>(`/profile/${profileId}/weekly-summary?today=${localDate()}`)
      .then(setData)
      .catch(() => setData(null));
  }, [profileId]);

  if (!data?.has_data) return null;

  const periodo = `${shortDate(data.week_start)} – ${shortDate(data.week_end)}`;
  const tiles: { label: string; value: string; hint: string; good: boolean | null }[] = [
    {
      label: "Allenamenti",
      value: data.sessions_planned
        ? `${data.sessions_done}/${data.sessions_planned}`
        : String(data.sessions_done),
      hint: data.sessions_planned ? "previsti dalla scheda" : "sedute registrate",
      good: data.sessions_planned ? data.sessions_done >= data.sessions_planned : null,
    },
    {
      label: "Peso medio",
      value: data.weight_average !== null ? `${fmt(data.weight_average, 1)} kg` : "—",
      hint:
        data.weight_delta_kg !== null
          ? `${data.weight_delta_kg > 0 ? "+" : ""}${fmt(data.weight_delta_kg, 1)} kg sulla settimana prima`
          : `${data.weigh_ins} ${data.weigh_ins === 1 ? "pesata" : "pesate"}`,
      good: null,
    },
    {
      label: "Proteine",
      value:
        data.protein_average_g !== null && data.protein_target_g
          ? `${Math.round((data.protein_average_g / data.protein_target_g) * 100)}%`
          : "—",
      hint:
        data.protein_average_g !== null
          ? `${data.protein_average_g} g in media · ${data.logged_days} giorni registrati`
          : "nessun giorno registrato",
      good:
        data.protein_average_g !== null && data.protein_target_g
          ? data.protein_average_g / data.protein_target_g >= 0.9
          : null,
    },
    ...data.supplements.map((s) => ({
      label: supplementName(s),
      value: `${s.days_taken}/${s.days_expected}`,
      hint: "giorni di assunzione",
      good: s.days_taken >= s.days_expected,
    })),
  ];

  const domanda =
    `Commenta la mia settimana (${periodo}): allenamenti ${tiles[0].value}, ` +
    `peso medio ${tiles[1].value} (${tiles[1].hint}), proteine ${tiles[2].value} del target ` +
    `(${tiles[2].hint})` +
    data.supplements.map((s) => `, ${supplementName(s)} ${s.days_taken}/${s.days_expected} giorni`).join("") +
    `. Cosa è andato bene e su cosa mi concentro la prossima settimana?`;

  return (
    <Card className="mb-4" delay={0.05}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
        <div>
          <h2 className="text-[15.5px] font-semibold text-white">La tua settimana</h2>
          <p className="text-[12.5px] text-white/45">{periodo} · calcolata sui dati che hai registrato</p>
        </div>
        <button
          onClick={() => askCoach(domanda, "Sezione Oggi · Riepilogo settimanale")}
          className="inline-flex items-center gap-1.5 rounded-lg border border-iris-400/30 bg-iris-400/[0.1] px-2.5 py-1.5 text-[12px] font-medium text-iris-100 transition hover:border-iris-400/50 hover:bg-iris-400/[0.18]"
        >
          <Mascot size={15} />
          Commentala con Kilo
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2.5 p-4 md:grid-cols-[repeat(auto-fit,minmax(160px,1fr))]">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-white/[0.07] bg-white/[0.025] px-3.5 py-3">
            <p className="truncate text-[11.5px] text-white/45">{t.label}</p>
            <p
              className={`mt-0.5 font-mono text-[19px] font-semibold tabular-nums ${
                t.good === true ? "text-lime-300" : t.good === false ? "text-amber-200" : "text-white"
              }`}
            >
              {t.value}
            </p>
            <p className="text-[11px] leading-snug text-white/35">{t.hint}</p>
          </div>
        ))}
      </div>

      {data.focus && (
        <div className="flex items-start gap-3 border-t border-white/[0.06] px-5 py-3.5">
          <Mascot
            size={30}
            mood={data.focus.startsWith("Settimana solida") ? "goal" : "happy"}
            className="shrink-0"
          />
          <div className="min-w-0">
            <p className="text-[10.5px] font-medium uppercase tracking-[0.14em] text-lime-400/70">
              Per la prossima settimana
            </p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-white/70">{data.focus}</p>
          </div>
        </div>
      )}
    </Card>
  );
}
