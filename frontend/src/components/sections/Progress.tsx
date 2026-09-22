"use client";

/**
 * Report di progressione.
 *
 * La pagina è un impianto di card indipendenti: ognuna legge il proprio
 * endpoint e si arrangia con caricamento, vuoto ed errore, così una statistica
 * che manca non porta giù il resto. L'ordine segue le domande che ci si fa
 * davvero, dalla più generale alla più specifica:
 *
 *  1. peso — dove sta andando il corpo, con il ritmo settimanale a confronto
 *     con quello atteso;
 *  2. costanza — quante sessioni si fanno davvero rispetto al piano;
 *  3. serie per gruppo muscolare — la leva che decide se il programma
 *     funziona, ed è per questo che sta a tutta larghezza;
 *  4. massimale stimato e carichi — due grafici sullo stesso esercizio, che si
 *     leggono in coppia e quindi condividono il selettore;
 *  5. alimentazione — la benzina, che spiega i primi quattro.
 */

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { api, type ProgressReport } from "@/lib/api";
import { Card, CardHeader, Empty, Notice, Spinner } from "@/components/ui";
import { AskCoachButton } from "@/components/controls";
import { PageHeader } from "@/components/Shell";
import { KiloNote } from "@/components/KiloNote";
import { useLoggedExercises } from "@/components/progress/common";
import { WeightCard, type WeightPoint } from "@/components/progress/WeightCard";
import { ConsistencyCard } from "@/components/progress/ConsistencyCard";
import { VolumeCard } from "@/components/progress/VolumeCard";
import { OneRmCard } from "@/components/progress/OneRmCard";
import { NutritionCard } from "@/components/progress/NutritionCard";
import { LoadChartCard } from "@/components/progress/LoadChartCard";

export function Progress({ profileId }: { profileId: number }) {
  const [report, setReport] = useState<ProgressReport | null>(null);
  const [weights, setWeights] = useState<WeightPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [weeks, setWeeks] = useState(12);
  // Il selettore dell'esercizio è unico per i due grafici sui carichi: è la
  // stessa domanda ("come va la panca?") vista da due angoli.
  const { exercises, selected, setSelected } = useLoggedExercises(profileId, weeks);

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

  if (loading || !report) return <Spinner label="Costruisco il report…" />;

  return (
    <>
      <PageHeader
        eyebrow="Progressi"
        title="Come sta andando"
        description={`Periodo di ${report.weeks} settimane · ${report.sessions_done} sessioni registrate`}
        action={
          <div className="flex flex-wrap items-center gap-1.5">
            <AskCoachButton
              question={`Analizza i miei progressi delle ultime ${weeks} settimane (peso, costanza, serie per gruppo muscolare, carichi e alimentazione): cosa sta andando bene e cosa cambieresti?`}
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

      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <WeightCard
            profileId={profileId}
            weeks={weeks}
            weights={weights}
            onLogged={load}
          />
          <ConsistencyCard profileId={profileId} weeks={weeks} />
        </div>

        <VolumeCard profileId={profileId} weeks={weeks} />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <OneRmCard
            profileId={profileId}
            weeks={weeks}
            exercises={exercises}
            selected={selected}
            onSelect={setSelected}
          />
          <LoadChartCard
            profileId={profileId}
            weeks={weeks}
            exercises={exercises}
            selected={selected}
            onSelect={setSelected}
          />
        </div>

        <NutritionCard profileId={profileId} weeks={weeks} />

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
                    transition={{ delay: Math.min(i * 0.05, 0.5) }}
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

        {report.plateau_advice && (
          <Card>
            <CardHeader title="Sei fermo su qualcosa" />
            <p className="px-5 py-4 text-[13px] leading-relaxed text-white/70">
              {report.plateau_advice}
            </p>
          </Card>
        )}

        {report.notes.length > 0 && (
          <div className="space-y-2.5">
            {report.notes.map((n, i) => (
              <Notice key={i}>{n}</Notice>
            ))}
          </div>
        )}
      </div>
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
