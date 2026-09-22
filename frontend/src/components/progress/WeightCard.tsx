"use client";

/**
 * Peso corporeo: le pesate singole (punti) e la media a 7 giorni (linea).
 *
 * La media è la protagonista — la tendenza si legge lì, non sui punti, che
 * oscillano di 1-2 kg al giorno per acqua e glicogeno — e sopra al grafico
 * c'è il verdetto: quanto si sta muovendo la media a settimana, confrontato
 * con il ritmo atteso per l'obiettivo.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, CardHeader, Empty, Spinner } from "@/components/ui";
import { NumberField } from "@/components/controls";
import {
  axisTick,
  num,
  signed,
  tooltipStyle,
  useEndpoint,
  type WeightTrendResponse,
  type WeightTrendVerdict,
} from "@/components/progress/common";

export type WeightPoint = { date: string; weight_kg: number };

const VERDICTS: Record<WeightTrendVerdict, { label: string; tone: string; dot: string }> = {
  in_linea: {
    label: "In linea con l'obiettivo",
    tone: "border-lime-400/25 bg-lime-400/10 text-lime-200",
    dot: "bg-lime-400",
  },
  troppo_veloce: {
    label: "Più veloce del previsto",
    tone: "border-rose-400/25 bg-rose-400/10 text-rose-200",
    dot: "bg-rose-400",
  },
  troppo_lento: {
    label: "Più lento del previsto",
    tone: "border-amber-300/25 bg-amber-300/10 text-amber-100",
    dot: "bg-amber-300",
  },
  pochi_dati: {
    label: "Ancora pochi dati",
    tone: "border-white/12 bg-white/[0.05] text-white/60",
    dot: "bg-white/40",
  },
  non_valutabile: {
    label: "Solo la tendenza",
    tone: "border-iris-400/25 bg-iris-400/10 text-iris-100",
    dot: "bg-iris-300",
  },
};

export function WeightCard({
  profileId,
  weeks,
  weights,
  onLogged,
}: {
  profileId: number;
  weeks: number;
  weights: WeightPoint[];
  onLogged: () => void | Promise<void>;
}) {
  const [logging, setLogging] = useState(false);
  const [newWeight, setNewWeight] = useState<number | null>(null);
  const trend = useEndpoint<WeightTrendResponse>(
    `/progress/weight-trend?profile_id=${profileId}&weeks=${weeks}`
  );

  async function logWeight() {
    const value = newWeight;
    if (!value) return;
    setLogging(true);
    try {
      await api.post(`/profile/${profileId}/weight`, { weight_kg: value });
      setNewWeight(null);
      await onLogged();
    } finally {
      setLogging(false);
    }
  }

  // Media mobile a 7 giorni, la stessa logica del backend: qui serve a
  // rendere visibile la differenza fra rumore e tendenza.
  const chartData = weights.map((p, i) => {
    const finestra = weights.slice(Math.max(0, i - 6), i + 1);
    return {
      date: new Date(p.date).toLocaleDateString("it-IT", { day: "2-digit", month: "short" }),
      peso: p.weight_kg,
      media: Number((finestra.reduce((s, x) => s + x.weight_kg, 0) / finestra.length).toFixed(2)),
    };
  });

  return (
    <Card>
      <CardHeader
        title="Peso corporeo"
        subtitle="I punti sono le pesate, la linea è la media a 7 giorni"
        action={
          <div className="flex gap-2">
            <NumberField
              value={newWeight}
              onChange={setNewWeight}
              min={30}
              max={300}
              decimals={1}
              suffix="kg"
              placeholder="peso"
              size="sm"
              ariaLabel="Peso di oggi"
              onEnter={logWeight}
              className="w-36"
            />
            <button className="btn-ghost px-3 py-1.5" disabled={logging} onClick={logWeight}>
              Registra
            </button>
          </div>
        }
      />
      <div className="p-4">
        <WeightVerdict trend={trend.data} loading={trend.loading} />

        {chartData.length < 2 ? (
          <Empty
            title="Servono più pesate"
            hint="Il peso oscilla di 1-2 kg al giorno: con 3-4 misurazioni a settimana la tendenza diventa leggibile."
          />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="weightFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b7dff" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#8b7dff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={axisTick}
                axisLine={false}
                tickLine={false}
                minTickGap={28}
              />
              <YAxis
                domain={["dataMin - 1", "dataMax + 1"]}
                tick={axisTick}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                {...tooltipStyle}
                formatter={(v: number, nome: string) => [
                  `${num(v)} kg`,
                  nome === "media" ? "media a 7 giorni" : "pesata",
                ]}
              />
              {/* I punti restano volutamente smorti: la linea della media è
                  quella che si deve leggere per prima. */}
              <Scatter dataKey="peso" fill="rgba(255,255,255,0.22)" />
              <Area
                type="monotone"
                dataKey="media"
                stroke="#8b7dff"
                strokeWidth={3}
                fill="url(#weightFill)"
                dot={false}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}

function WeightVerdict({
  trend,
  loading,
}: {
  trend: WeightTrendResponse | null;
  loading: boolean;
}) {
  if (loading) return <Spinner label="Calcolo la tendenza…" />;
  // Endpoint non disponibile: la card resta utile col solo grafico, senza
  // riquadri d'errore per una riga di commento.
  if (!trend) return null;

  const stato = VERDICTS[trend.verdict] ?? VERDICTS.pochi_dati;
  const ritmo = trend.weekly_rate_kg;
  const atteso =
    trend.expected_min !== null && trend.expected_max !== null
      ? `atteso fra ${signed(trend.expected_min, 2)} e ${signed(trend.expected_max, 2)} kg`
      : null;

  return (
    <div className="mb-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
        {ritmo !== null && trend.verdict !== "pochi_dati" ? (
          <>
            <span className="font-mono text-[22px] font-semibold leading-none tabular-nums text-white">
              {signed(ritmo, 2)} kg
            </span>
            <span className="text-[12.5px] text-white/45">a settimana</span>
          </>
        ) : (
          <span className="text-[13px] text-white/60">Ritmo non ancora calcolabile</span>
        )}
        <span className={`pill ml-auto border ${stato.tone}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${stato.dot}`} />
          {stato.label}
        </span>
      </div>
      {atteso && trend.verdict !== "pochi_dati" && (
        <p className="mt-1.5 font-mono text-[11.5px] tabular-nums text-white/35">{atteso}</p>
      )}
      {trend.note && (
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-white/55">{trend.note}</p>
      )}
    </div>
  );
}
