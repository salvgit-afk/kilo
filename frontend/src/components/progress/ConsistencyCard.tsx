"use client";

/**
 * Costanza: quante sessioni sono state fatte ogni settimana rispetto a quelle
 * previste, e da quante settimane di fila si sta in regola.
 *
 * Le barre sono disegnate a mano invece che con recharts: servono una barra
 * per le sessioni fatte **e** una tacca sul bersaglio previsto, e a 390 px una
 * colonna larga pochi pixel con la tacca si legge meglio di due barre affiancate.
 */

import { motion } from "framer-motion";
import { Card, CardHeader, Empty } from "@/components/ui";
import {
  RemoteFallback,
  shortDate,
  useEndpoint,
  type ConsistencyResponse,
  type ConsistencyWeek,
} from "@/components/progress/common";

export function ConsistencyCard({ profileId, weeks }: { profileId: number; weeks: number }) {
  const { data, loading, error } = useEndpoint<ConsistencyResponse>(
    `/progress/consistency?profile_id=${profileId}&weeks=${weeks}`
  );

  const settimane: ConsistencyWeek[] = Array.isArray(data?.weeks) ? data.weeks : [];

  return (
    <Card>
      <CardHeader
        title="Costanza"
        subtitle="Sessioni fatte ogni settimana; la tacca è il programmato"
        action={
          data && data.planned_total > 0 ? (
            <span className="font-mono text-[12.5px] tabular-nums text-white/45">
              {data.done_total}/{data.planned_total} sessioni
            </span>
          ) : null
        }
      />
      <div className="p-4">
        {!data ? (
          <RemoteFallback loading={loading} error={error} loadingLabel="Conto le settimane…" />
        ) : settimane.length === 0 ? (
          <Empty
            title="Ancora nessuna settimana registrata"
            hint="Chiudi un allenamento dalla Scheda: da lì in poi qui compare una barra per settimana."
          />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1.5">
              <span
                className={`pill border ${
                  data.streak_weeks > 0
                    ? "border-lime-400/25 bg-lime-400/10 text-lime-200"
                    : "border-white/12 bg-white/[0.05] text-white/55"
                }`}
              >
                {data.streak_weeks > 0
                  ? `${data.streak_weeks} ${
                      data.streak_weeks === 1 ? "settimana" : "settimane"
                    } di fila in regola`
                  : "Serie interrotta"}
              </span>
              {data.best_streak_weeks > 0 && (
                <span className="text-[11.5px] text-white/35">
                  record: {data.best_streak_weeks}{" "}
                  {data.best_streak_weeks === 1 ? "settimana" : "settimane"}
                </span>
              )}
            </div>

            <WeekBars weeks={settimane} />
          </>
        )}
      </div>
    </Card>
  );
}

function WeekBars({ weeks }: { weeks: ConsistencyWeek[] }) {
  const massimo = Math.max(1, ...weeks.map((w) => Math.max(w.done, w.planned)));
  // Con molte settimane le etichette si accavallano: se ne mostra una ogni n.
  const passo = Math.ceil(weeks.length / 6);

  return (
    <div>
      <div className="flex items-end gap-1 sm:gap-1.5">
        {weeks.map((w, i) => {
          const inRegola = w.planned > 0 && w.done >= w.planned;
          const altezza = (w.done / massimo) * 100;
          const bersaglio = w.planned > 0 ? (w.planned / massimo) * 100 : null;
          return (
            <div
              key={w.start}
              className="flex min-w-0 flex-1 flex-col items-center gap-1"
              title={`Settimana del ${shortDate(w.start)}: ${w.done} su ${w.planned || "—"}`}
            >
              <span className="font-mono text-[10.5px] tabular-nums text-white/45">{w.done}</span>
              <div className="relative h-24 w-full overflow-hidden rounded-md bg-white/[0.05]">
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: `${altezza}%` }}
                  transition={{ duration: 0.6, delay: i * 0.03, ease: [0.22, 1, 0.36, 1] }}
                  className={`absolute inset-x-0 bottom-0 rounded-md bg-gradient-to-t ${
                    inRegola
                      ? "from-lime-500 to-lime-400"
                      : w.done > 0
                        ? "from-iris-500 to-iris-400"
                        : "from-white/10 to-white/10"
                  }`}
                />
                {bersaglio !== null && (
                  <span
                    className="absolute inset-x-0 border-t border-dashed border-white/35"
                    style={{ bottom: `${Math.min(bersaglio, 100)}%` }}
                  />
                )}
              </div>
              <span className="h-3 truncate text-[9.5px] leading-3 text-white/25">
                {i % passo === 0 ? shortDate(w.start) : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
