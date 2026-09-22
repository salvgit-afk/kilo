"use client";

/**
 * Progressione dei carichi di un esercizio: il carico massimo di ogni
 * sessione (linea piena) e il massimale stimato (tratteggio), che rende
 * confrontabili sessioni con ripetizioni diverse.
 *
 * L'esercizio è lo stesso scelto nella card del massimale stimato: i due
 * grafici si leggono in coppia, e due selettori scollegati facevano confondere
 * i periodi.
 */

import { AnimatePresence } from "framer-motion";
import { useState } from "react";
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
import { LoadHistoryDialog, kg, useHistory } from "@/components/TrainingLog";
import { Card, CardHeader, Empty, Spinner } from "@/components/ui";
import { ExercisePicker, axisTick, tooltipStyle } from "@/components/progress/common";

export function LoadChartCard({
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
  const [editing, setEditing] = useState(false);
  const { data, points, reload } = useHistory(profileId, selected, weeks);

  const ultimo = points[points.length - 1];
  const primo = points[0];
  const delta = ultimo && primo && points.length > 1 ? ultimo.carico - primo.carico : null;

  return (
    <>
      <Card>
        <CardHeader
          title="Progressione dei carichi"
          subtitle="Carico massimo di ogni sessione; il tratteggio è il massimale stimato"
          action={
            selected !== null && (
              <button
                className="btn-ghost px-3 py-1.5 text-[12px]"
                onClick={() => setEditing(true)}
              >
                Storico
              </button>
            )
          }
        />
        <div className="p-4">
          {!exercises ? (
            <Spinner label="Carico gli esercizi…" />
          ) : exercises.length === 0 ? (
            <Empty
              title="Ancora nessun carico registrato"
              hint="Nella Scheda tocca «Inizia allenamento» e segna kg e ripetizioni di ogni serie: la progressione compare qui."
            />
          ) : (
            <>
              <ExercisePicker exercises={exercises} selected={selected} onSelect={onSelect} />

              {!data ? (
                <Spinner label="Carico lo storico…" />
              ) : points.length < 2 ? (
                <Empty
                  title={
                    points.length === 1
                      ? `Una sessione: ${kg(points[0].carico)} kg`
                      : "Nessuna sessione nel periodo"
                  }
                  hint="Con almeno due sessioni dello stesso esercizio si vede la linea della progressione."
                />
              ) : (
                <>
                  <div className="mb-2 flex items-baseline gap-2">
                    <span className="font-mono text-[22px] font-semibold tabular-nums text-white">
                      {kg(ultimo.carico)} kg
                    </span>
                    {delta !== null && (
                      <span
                        className={`font-mono text-[12.5px] tabular-nums ${
                          delta > 0
                            ? "text-lime-300"
                            : delta < 0
                              ? "text-rose-300"
                              : "text-white/40"
                        }`}
                      >
                        {delta > 0 ? "+" : ""}
                        {kg(delta)} kg nel periodo
                      </span>
                    )}
                  </div>
                  <ResponsiveContainer width="100%" height={230}>
                    <LineChart data={points} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                      <XAxis
                        dataKey="date"
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
                        formatter={(v: number, nome: string) => [
                          `${kg(v)} kg`,
                          nome === "carico" ? "carico massimo" : "massimale stimato",
                        ]}
                      />
                      <Line
                        type="monotone"
                        dataKey="massimale"
                        stroke="#8b7dff"
                        strokeWidth={1.8}
                        strokeDasharray="5 4"
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="carico"
                        stroke="#aed44a"
                        strokeWidth={2.5}
                        dot={{ r: 3, fill: "#aed44a", strokeWidth: 0 }}
                        activeDot={{ r: 5 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </>
              )}
            </>
          )}
        </div>
      </Card>
      {/* Fuori dalla card: la card è animata e un fixed al suo interno si
          posizionerebbe rispetto a lei, non allo schermo. */}
      <AnimatePresence>
        {editing && selected !== null && (
          <LoadHistoryDialog
            profileId={profileId}
            exerciseId={selected}
            onClose={() => setEditing(false)}
            onChanged={reload}
          />
        )}
      </AnimatePresence>
    </>
  );
}
