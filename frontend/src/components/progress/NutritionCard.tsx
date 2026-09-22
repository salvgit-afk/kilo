"use client";

/**
 * Alimentazione: medie settimanali di calorie e proteine rispetto al target.
 *
 * Accanto alle medie compaiono i giorni registrati, perché una media su due
 * giorni non è una settimana: senza quel numero il confronto col target
 * sembrerebbe più solido di quanto è.
 */

import { Card, CardHeader, Empty, StatBar } from "@/components/ui";
import {
  RemoteFallback,
  shortDate,
  useEndpoint,
  type NutritionResponse,
  type NutritionWeek,
} from "@/components/progress/common";

export function NutritionCard({ profileId, weeks }: { profileId: number; weeks: number }) {
  const { data, loading, error } = useEndpoint<NutritionResponse>(
    `/progress/nutrition?profile_id=${profileId}&weeks=${weeks}`
  );

  const settimane: NutritionWeek[] = Array.isArray(data?.weeks) ? data.weeks : [];
  const conDati = settimane.filter((w) => w.days_logged > 0);
  const ultima = conDati[conDati.length - 1] ?? null;
  const kcalTarget = data?.kcal_target ?? null;
  const proteinTarget = data?.protein_target_g ?? null;

  return (
    <Card>
      <CardHeader
        title="Alimentazione"
        subtitle="Medie settimanali di calorie e proteine rispetto al target"
        action={
          kcalTarget || proteinTarget ? (
            <span className="font-mono text-[12px] tabular-nums text-white/40">
              target {kcalTarget ? `${Math.round(kcalTarget)} kcal` : "—"}
              {proteinTarget ? ` · ${Math.round(proteinTarget)} g` : ""}
            </span>
          ) : null
        }
      />
      <div className="p-4">
        {!data ? (
          <RemoteFallback loading={loading} error={error} loadingLabel="Leggo il diario…" />
        ) : !ultima ? (
          <Empty
            title="Nessun pasto registrato"
            hint="Nel Diario segna quello che mangi anche solo per qualche giorno: qui compaiono le medie della settimana e i giorni in target."
          />
        ) : (
          <>
            <p className="mb-3 text-[11px] uppercase tracking-wider text-white/35">
              Settimana del {shortDate(ultima.start)}
            </p>

            <div className="space-y-3">
              {kcalTarget ? (
                <StatBar
                  label="Calorie al giorno"
                  value={ultima.kcal_avg}
                  target={kcalTarget}
                  unit=" kcal"
                  tone="iris"
                />
              ) : (
                <PlainValue label="Calorie al giorno" value={`${Math.round(ultima.kcal_avg)} kcal`} />
              )}
              {proteinTarget ? (
                <StatBar
                  label="Proteine al giorno"
                  value={ultima.protein_avg_g}
                  target={proteinTarget}
                  unit=" g"
                  tone="lime"
                />
              ) : (
                <PlainValue
                  label="Proteine al giorno"
                  value={`${Math.round(ultima.protein_avg_g)} g`}
                />
              )}
            </div>

            <p className="mt-3 text-[12px] text-white/45">
              {ultima.days_logged} {ultima.days_logged === 1 ? "giorno registrato" : "giorni registrati"}
              {" · "}
              <span className="text-white/65">{ultima.days_in_kcal_target}</span> in target calorie
              {" · "}
              <span className="text-white/65">{ultima.days_in_protein_target}</span> in target proteine
            </p>

            {conDati.length > 1 && (
              <div className="mt-3 space-y-1 border-t border-white/[0.06] pt-3">
                {[...conDati]
                  .slice(0, -1)
                  .reverse()
                  .map((w) => (
                    <div
                      key={w.start}
                      className="flex items-baseline justify-between gap-3 rounded-lg px-1 py-1 text-[12px]"
                    >
                      <span className="shrink-0 text-white/40">{shortDate(w.start)}</span>
                      <span className="min-w-0 truncate font-mono tabular-nums text-white/60">
                        {Math.round(w.kcal_avg)} kcal · {Math.round(w.protein_avg_g)} g
                      </span>
                      <span className="shrink-0 font-mono text-[11px] tabular-nums text-white/30">
                        {w.days_logged}/7 gg
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

function PlainValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-[12px] text-white/55">{label}</span>
      <span className="font-mono text-[13px] tabular-nums text-white/80">{value}</span>
    </div>
  );
}
