"use client";

/**
 * Massimale stimato di un esercizio nel tempo.
 *
 * È la misura che rende confrontabili sessioni con ripetizioni diverse: 80×5 e
 * 70×10 sono due allenamenti diversi ma un massimale simile. La stima regge
 * bene fino a ~10 ripetizioni; oltre, il backend lo segnala e lo diciamo.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LoggedExercise } from "@/lib/api";
import { Card, CardHeader, Empty, Notice, Spinner } from "@/components/ui";
import {
  ExercisePicker,
  RemoteFallback,
  axisTick,
  num,
  shortDate,
  signed,
  tooltipStyle,
  useEndpoint,
  type OneRmResponse,
} from "@/components/progress/common";

type PuntoGrafico = { data: string; massimale: number; kg: number; reps: number };

export function OneRmCard({
  profileId,
  weeks,
  exercises,
  selected,
  onSelect,
}: {
  profileId: number;
  weeks: number;
  exercises: LoggedExercise[] | null;
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const { data, loading, error } = useEndpoint<OneRmResponse>(
    selected === null
      ? null
      : `/progress/one-rm/${selected}?profile_id=${profileId}&weeks=${weeks}`
  );

  const punti: PuntoGrafico[] = (Array.isArray(data?.points) ? data.points : []).map((p) => ({
    data: shortDate(p.date),
    massimale: p.one_rm,
    kg: p.kg,
    reps: p.reps,
  }));
  const delta = data?.delta_pct ?? null;

  return (
    <Card>
      <CardHeader
        title="Massimale stimato"
        subtitle="Stimato da kg e ripetizioni della serie migliore di ogni sessione"
        action={
          delta !== null && punti.length > 1 ? (
            <span
              className={`font-mono text-[12.5px] tabular-nums ${
                delta > 0.02 ? "text-lime-300" : delta < -0.02 ? "text-rose-300" : "text-white/40"
              }`}
            >
              {signed(delta * 100, 1)}% nel periodo
            </span>
          ) : null
        }
      />
      <div className="p-4">
        {!exercises ? (
          <Spinner label="Carico gli esercizi…" />
        ) : exercises.length === 0 ? (
          <Empty
            title="Ancora nessun carico registrato"
            hint="Nella Scheda tocca «Inizia allenamento» e segna kg e ripetizioni: il massimale stimato compare qui."
          />
        ) : (
          <>
            <ExercisePicker exercises={exercises} selected={selected} onSelect={onSelect} />

            {!data ? (
              <RemoteFallback
                loading={loading}
                error={error}
                loadingLabel="Calcolo il massimale…"
              />
            ) : punti.length < 2 ? (
              <Empty
                title={
                  punti.length === 1
                    ? `Una sola sessione: ${num(punti[0].massimale)} kg stimati`
                    : "Nessuna sessione nel periodo"
                }
                hint="Con almeno due sessioni dello stesso esercizio si vede la curva del massimale."
              />
            ) : (
              <>
                <div className="mb-2 flex items-baseline gap-2">
                  <span className="font-mono text-[22px] font-semibold tabular-nums text-white">
                    {num(punti[punti.length - 1].massimale)} kg
                  </span>
                  <span className="text-[12px] text-white/40">stimati oggi</span>
                </div>

                <ResponsiveContainer width="100%" height={230}>
                  <LineChart data={punti} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis
                      dataKey="data"
                      tick={axisTick}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={24}
                    />
                    <YAxis
                      // Estremi arrotondati ai 5 kg: niente tacche come 96,8.
                      domain={[
                        (min: number) => Math.max(0, Math.floor((min - 2.5) / 5) * 5),
                        (max: number) => Math.ceil((max + 2.5) / 5) * 5,
                      ]}
                      tick={axisTick}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <Tooltip
                      {...tooltipStyle}
                      formatter={(
                        v: number,
                        _nome: string,
                        voce: { payload?: PuntoGrafico }
                      ) => [
                        `${num(v)} kg${
                          voce?.payload ? ` · da ${num(voce.payload.kg)}×${voce.payload.reps}` : ""
                        }`,
                        "massimale stimato",
                      ]}
                    />
                    <Line
                      type="monotone"
                      dataKey="massimale"
                      stroke="#aed44a"
                      strokeWidth={2.5}
                      dot={{ r: 3, fill: "#aed44a", strokeWidth: 0 }}
                      activeDot={{ r: 5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>

                {data.high_rep_estimate && (
                  <div className="mt-3">
                    <Notice>
                      Alcune serie superano le 10 ripetizioni: oltre quella soglia la stima del
                      massimale è meno precisa, leggila come una tendenza e non come un numero
                      esatto.
                    </Notice>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
