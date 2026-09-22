"use client";

/**
 * Serie settimanali per gruppo muscolare rispetto al range consigliato.
 *
 * È la statistica che decide se il programma funziona: i carichi salgono se il
 * volume è nella fascia giusta. Per ogni muscolo si vede il numero di serie
 * dell'ultima settimana, dove cade rispetto al range (la fascia chiara sulla
 * barra) e un'etichetta che dice se è poco, giusto o troppo.
 */

import { motion } from "framer-motion";
import { MUSCLE_LABELS } from "@/lib/api";
import { Card, CardHeader, Empty, SourceTags } from "@/components/ui";
import {
  RemoteFallback,
  num,
  useEndpoint,
  type VolumeMuscle,
  type VolumeResponse,
  type VolumeStatus,
} from "@/components/progress/common";

const STATUS: Record<VolumeStatus, { label: string; pill: string; bar: string }> = {
  sotto: {
    label: "Sotto il range",
    pill: "border-amber-300/25 bg-amber-300/10 text-amber-100",
    bar: "from-amber-300 to-amber-500",
  },
  dentro: {
    label: "Nel range",
    pill: "border-lime-400/25 bg-lime-400/10 text-lime-200",
    bar: "from-lime-400 to-lime-500",
  },
  sopra: {
    label: "Sopra il range",
    pill: "border-rose-400/25 bg-rose-400/10 text-rose-200",
    bar: "from-rose-400 to-rose-500",
  },
};

export function VolumeCard({ profileId, weeks }: { profileId: number; weeks: number }) {
  const { data, loading, error } = useEndpoint<VolumeResponse>(
    `/progress/volume?profile_id=${profileId}&weeks=${weeks}`
  );

  const muscoli: VolumeMuscle[] = Array.isArray(data?.muscles) ? data.muscles : [];

  return (
    <Card>
      <CardHeader
        title="Serie per gruppo muscolare"
        subtitle="Ultima settimana conclusa e media del periodo, rispetto al range consigliato"
        action={
          muscoli.length > 0 ? (
            <span className="font-mono text-[12.5px] tabular-nums text-white/45">
              {muscoli.filter((m) => m.status === "dentro").length}/{muscoli.length} nel range
            </span>
          ) : null
        }
      />
      <div className="p-3 sm:p-4">
        {!data ? (
          <RemoteFallback loading={loading} error={error} loadingLabel="Conto le serie…" />
        ) : muscoli.length === 0 ? (
          <Empty
            title="Nessuna serie registrata"
            hint="Segna kg e ripetizioni durante l'allenamento: le serie vengono contate per gruppo muscolare."
          />
        ) : (
          <>
            <div className="grid gap-1.5 md:grid-cols-2">
              {muscoli.map((m, i) => (
                <MuscleRow key={m.muscle} muscle={m} index={i} />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-white/[0.06] pt-3">
              <p className="text-[11.5px] leading-snug text-white/35">
                I range settimanali per gruppo muscolare vengono dalle fonti del progetto, non da
                una regola inventata qui.
              </p>
              <SourceTags tags={["volume_allenamento"]} />
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

function MuscleRow({ muscle, index }: { muscle: VolumeMuscle; index: number }) {
  const stato = STATUS[muscle.status] ?? STATUS.dentro;
  // La scala lascia sempre un po' d'aria oltre il massimo consigliato, così la
  // fascia del range non tocca mai il bordo e "sopra" si vede come sporgenza.
  const scala = Math.max(muscle.range_max * 1.25, muscle.last * 1.1, 1);
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / scala) * 100))}%`;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.4) }}
      className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3"
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <p className="min-w-0 truncate text-[13px] text-white/85">
          {MUSCLE_LABELS[muscle.muscle] ?? muscle.muscle}
        </p>
        <div className="flex shrink-0 items-baseline gap-1.5">
          <span className="font-mono text-[15px] font-semibold tabular-nums text-white">
            {muscle.last}
          </span>
          <span className="text-[11px] text-white/35">serie · ultima settimana</span>
        </div>
      </div>

      <div className="relative h-3 overflow-hidden rounded-full bg-white/[0.05]">
        {/* Fascia consigliata: resta visibile sopra e sotto la barra piena. */}
        <span
          className="absolute inset-y-0 rounded-full bg-white/[0.12]"
          style={{ left: pct(muscle.range_min), width: pct(muscle.range_max - muscle.range_min) }}
        />
        <motion.span
          initial={{ width: 0 }}
          animate={{ width: pct(muscle.last) }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className={`absolute inset-y-[3px] left-0 rounded-full bg-gradient-to-r ${stato.bar}`}
        />
      </div>

      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <span className={`pill border ${stato.pill}`}>{stato.label}</span>
        <span className="font-mono text-[11px] tabular-nums text-white/35">
          consigliate {muscle.range_min}–{muscle.range_max} · media {num(muscle.average, 1)} a settimana
        </span>
      </div>
    </motion.div>
  );
}
