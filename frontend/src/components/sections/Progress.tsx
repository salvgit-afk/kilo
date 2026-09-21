"use client";

/**
 * Report di progressione.
 *
 * Il grafico del peso mostra le pesate singole **e** la media mobile, con la
 * media in evidenza: serve a far vedere con gli occhi perché la tendenza si
 * legge sulla linea liscia e non sui punti, che oscillano di 1-2 kg al
 * giorno per acqua e glicogeno.
 *
 * Accanto, la progressione dei carichi di un esercizio a scelta: carico
 * massimo di ogni sessione e massimale stimato. I due grafici si leggono
 * insieme: il peso che sale con i carichi fermi racconta una cosa diversa
 * dal peso che sale mentre i carichi crescono.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type LoggedExercise, type ProgressReport } from "@/lib/api";
import { LoadHistoryDialog, kg, useHistory } from "@/components/TrainingLog";
import { Card, CardHeader, Empty, Notice, Spinner } from "@/components/ui";
import { AskCoachButton, NumberField } from "@/components/controls";
import { PageHeader } from "@/components/Shell";
import { KiloNote } from "@/components/KiloNote";

type WeightPoint = { date: string; weight_kg: number };

export function Progress({ profileId }: { profileId: number }) {
  const [report, setReport] = useState<ProgressReport | null>(null);
  const [weights, setWeights] = useState<WeightPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [weeks, setWeeks] = useState(12);
  const [logging, setLogging] = useState(false);
  const [newWeight, setNewWeight] = useState<number | null>(null);

  const load = useCallback(async () => {
    const [r, w] = await Promise.all([
      api.get<ProgressReport>(`/progress/report?profile_id=${profileId}&weeks=${weeks}`),
      api.get<WeightPoint[]>(`/profile/${profileId}/weight?limit=120`),
    ]);
    setReport(r);
    setWeights([...w].reverse());
    setLoading(false);
  }, [profileId, weeks]);

  useEffect(() => {
    load();
  }, [load]);

  async function logWeight() {
    const value = newWeight;
    if (!value) return;
    setLogging(true);
    try {
      await api.post(`/profile/${profileId}/weight`, { weight_kg: value });
      setNewWeight(null);
      await load();
    } finally {
      setLogging(false);
    }
  }

  if (loading || !report) return <Spinner label="Costruisco il report…" />;

  // Media mobile a 7 giorni, la stessa logica usata dal backend: qui serve a
  // rendere visibile la differenza fra rumore e tendenza.
  const chartData = weights.map((p, i) => {
    const finestra = weights.slice(Math.max(0, i - 6), i + 1);
    return {
      date: new Date(p.date).toLocaleDateString("it-IT", { day: "2-digit", month: "short" }),
      peso: p.weight_kg,
      media: Number(
        (finestra.reduce((s, x) => s + x.weight_kg, 0) / finestra.length).toFixed(2)
      ),
    };
  });

  return (
    <>
      <PageHeader
        eyebrow="Progressi"
        title="Come sta andando"
        description={`Periodo di ${report.weeks} settimane · ${report.sessions_done} sessioni registrate`}
        action={
          <div className="flex flex-wrap items-center gap-1.5">
            <AskCoachButton
              question={`Analizza i miei progressi delle ultime ${weeks} settimane (peso, sessioni e carichi): cosa sta andando bene e cosa cambieresti?`}
              context="Sezione Progressi"
              label="Analizza con Kilo"
              className="mr-1.5"
            />
            <div className="flex gap-1.5">
            {[4, 12, 24].map((w) => (
              <button
                key={w}
                onClick={() => setWeeks(w)}
                className={`rounded-lg px-3 py-2 text-[12.5px] font-medium transition ${
                  weeks === w
                    ? "bg-white/[0.09] text-white"
                    : "border border-white/10 text-white/45 hover:text-white"
                }`}
              >
                {w} sett.
              </button>
            ))}
            </div>
          </div>
        }
      />

      <KiloNote section="progressi" />

      {report.too_early && (
        <div className="mb-4">
          <Notice>
            Il periodo è breve: leggi questi numeri come una fotografia, non come un
            verdetto sul programma.
          </Notice>
        </div>
      )}

      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Metric
          label="Peso corporeo"
          value={
            report.weight_delta_kg !== null
              ? `${report.weight_delta_kg > 0 ? "+" : ""}${report.weight_delta_kg} kg`
              : "—"
          }
          hint={
            report.weight_weekly_rate_kg !== null
              ? `${report.weight_weekly_rate_kg > 0 ? "+" : ""}${report.weight_weekly_rate_kg} kg a settimana`
              : `${report.weight_measurements} pesate registrate`
          }
          tone={
            report.weight_delta_kg === null
              ? "neutral"
              : report.weight_delta_kg > 0
                ? "lime"
                : "iris"
          }
          warning={!report.weight_smoothed && report.weight_measurements > 0}
        />
        <Metric
          label="Sessioni"
          value={`${report.sessions_per_week}/sett.`}
          hint={
            report.planned_per_week
              ? `su ${report.planned_per_week} programmate`
              : "nessun piano attivo"
          }
          tone={
            report.planned_per_week && report.sessions_per_week / report.planned_per_week < 0.7
              ? "amber"
              : "lime"
          }
        />
        <Metric
          label="Esercizi in progresso"
          value={`${report.exercises.filter((e) => e.delta_pct > 0.02).length}/${report.exercises.length}`}
          hint="massimale stimato in crescita"
          tone="iris"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
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
                    tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={28}
                  />
                  <YAxis
                    domain={["dataMin - 1", "dataMax + 1"]}
                    tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "rgba(12,14,22,0.96)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "rgba(255,255,255,0.5)" }}
                  />
                  <Scatter dataKey="peso" fill="rgba(255,255,255,0.28)" />
                  <Area
                    type="monotone"
                    dataKey="media"
                    stroke="#8b7dff"
                    strokeWidth={2.5}
                    fill="url(#weightFill)"
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <LoadChartCard profileId={profileId} weeks={weeks} />
      </div>

      <div className="mt-4">
        <Card>
          <CardHeader title="Carichi" subtitle="Massimale stimato, inizio → fine periodo" />
          <div className="p-3">
            {report.exercises.length === 0 ? (
              <Empty
                title="Nessun esercizio con due sessioni"
                hint="Registra gli allenamenti per vedere la progressione."
              />
            ) : (
              <div className="grid gap-1.5 md:grid-cols-2">
                {report.exercises.map((e, i) => (
                  <motion.div
                    key={e.exercise_name}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3"
                  >
                    <div className="mb-1.5 flex items-center justify-between gap-3">
                      <p className="min-w-0 truncate text-[13px] text-white/85">
                        {e.exercise_name}
                      </p>
                      <span
                        className={`shrink-0 font-mono text-[12.5px] tabular-nums ${
                          e.delta_pct > 0.02
                            ? "text-lime-300"
                            : e.delta_pct < -0.02
                              ? "text-rose-300"
                              : "text-white/35"
                        }`}
                      >
                        {e.delta_kg > 0 ? "+" : ""}
                        {e.delta_kg} kg
                      </span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[11px] text-white/35">
                      <span>{e.first_best_set}</span>
                      <svg viewBox="0 0 24 24" className="h-3 w-3 fill-white/20">
                        <path d="m13 5 7 7-7 7v-4H4v-6h9V5Z" />
                      </svg>
                      <span className="text-white/55">{e.last_best_set}</span>
                      {e.high_rep_estimate && (
                        <span className="ml-auto text-[10px] text-amber-300/50">
                          stima meno precisa
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      {report.plateau_advice && (
        <Card className="mt-4">
          <CardHeader title="Sei fermo su qualcosa" />
          <p className="px-5 py-4 text-[13px] leading-relaxed text-white/70">
            {report.plateau_advice}
          </p>
        </Card>
      )}

      {report.notes.length > 0 && (
        <div className="mt-4 space-y-2.5">
          {report.notes.map((n, i) => (
            <Notice key={i}>{n}</Notice>
          ))}
        </div>
      )}
    </>
  );
}

function Metric({
  label,
  value,
  hint,
  tone,
  warning,
}: {
  label: string;
  value: string;
  hint: string;
  tone: "lime" | "iris" | "amber" | "neutral";
  warning?: boolean;
}) {
  const colors = {
    lime: "text-lime-300",
    iris: "text-iris-300",
    amber: "text-amber-300",
    neutral: "text-white/50",
  }[tone];

  return (
    <Card hover>
      <div className="px-5 py-4">
        <p className="text-[11px] uppercase tracking-wider text-white/35">{label}</p>
        <p className={`mt-1.5 font-mono text-[26px] tabular-nums leading-none ${colors}`}>
          {value}
        </p>
        <p className="mt-1.5 text-[12px] text-white/40">
          {hint}
          {warning && (
            <span className="ml-1.5 text-amber-300/70">· poche misurazioni</span>
          )}
        </p>
      </div>
    </Card>
  );
}


/**
 * Progressione dei carichi di un esercizio: il carico massimo di ogni
 * sessione (linea piena) e il massimale stimato (tratteggio), che rende
 * confrontabili sessioni con ripetizioni diverse.
 */
function LoadChartCard({ profileId, weeks }: { profileId: number; weeks: number }) {
  const [exercises, setExercises] = useState<LoggedExercise[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const { data, points, reload } = useHistory(profileId, selected, weeks);

  useEffect(() => {
    api
      .get<LoggedExercise[]>(`/progress/loads?profile_id=${profileId}&weeks=${weeks}`)
      .then((lista) => {
        setExercises(lista);
        setSelected((attuale) =>
          attuale !== null && lista.some((e) => e.exercise_id === attuale) ? attuale : lista[0]?.exercise_id ?? null
        );
      })
      .catch(() => setExercises([]));
  }, [profileId, weeks]);

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
            <button className="btn-ghost px-3 py-1.5 text-[12px]" onClick={() => setEditing(true)}>
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
            <div className="-mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
              {exercises.map((e) => (
                <button
                  key={e.exercise_id}
                  onClick={() => setSelected(e.exercise_id)}
                  className={`shrink-0 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition ${
                    e.exercise_id === selected
                      ? "border-lime-400/50 bg-lime-400/15 text-lime-100"
                      : "border-white/10 bg-white/[0.03] text-white/55 hover:text-white"
                  }`}
                >
                  {e.exercise_name}
                  <span className="ml-1.5 font-mono text-[11px] text-white/35">{e.sessions}</span>
                </button>
              ))}
            </div>

            {!data ? (
              <Spinner label="Carico lo storico…" />
            ) : points.length < 2 ? (
              <Empty
                title={points.length === 1 ? `Una sessione: ${kg(points[0].carico)} kg` : "Nessuna sessione nel periodo"}
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
                        delta > 0 ? "text-lime-300" : delta < 0 ? "text-rose-300" : "text-white/40"
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
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
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
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "rgba(12,14,22,0.96)",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: 12,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: "rgba(255,255,255,0.5)" }}
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
