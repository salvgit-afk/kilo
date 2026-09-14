"use client";

/**
 * Suggerimenti di ricette.
 *
 * A differenza del diario, qui i valori sono **stimati**: le quantità delle
 * ricette sono scritte per un essere umano ("¼ cup", "1 clove") e vanno
 * convertite in grammi. L'interfaccia lo dichiara apertamente — con la
 * copertura degli ingredienti riconosciuti — invece di mostrare numeri che
 * sembrano precisi e non lo sono.
 *
 * Si cerca in italiano: il backend traduce la ricerca per la fonte (che
 * conosce solo l'inglese) e poi traduce le ricette trovate.
 */

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type RecipeSuggestion } from "@/lib/api";
import type { Intent } from "@/lib/coach";
import { Card, Empty, Notice } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import { AskCoachButton } from "@/components/controls";
import { Mascot } from "@/components/Mascot";

const SPUNTI = ["pollo", "salmone", "tonno", "uova", "lenticchie", "manzo", "tofu"];

export function Recipes({
  profileId,
  intent,
  onIntentHandled,
}: {
  profileId: number;
  intent?: Intent | null;
  onIntentHandled?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [recipes, setRecipes] = useState<RecipeSuggestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const search = useCallback(
    async (text: string) => {
      setLoading(true);
      setError(null);
      try {
        const q = text.trim() ? `&query=${encodeURIComponent(text.trim())}` : "";
        setRecipes(
          await api.get<RecipeSuggestion[]>(
            `/nutrition/recipes/suggest?profile_id=${profileId}&top=4${q}`
          )
        );
      } catch (e) {
        setRecipes(null);
        setError(
          e instanceof ApiError && e.status === 503
            ? e.message
            : `Non sono riuscito a cercare le ricette${e instanceof Error ? `: ${e.message}` : ""}. Riprova tra poco.`
        );
      } finally {
        setLoading(false);
      }
    },
    [profileId]
  );

  useEffect(() => {
    if (intent?.section === "ricette" && intent.recipeQuery !== undefined) {
      setQuery(intent.recipeQuery);
      search(intent.recipeQuery);
      onIntentHandled?.();
    }
  }, [intent, search, onIntentHandled]);

  return (
    <>
      <PageHeader
        eyebrow="Nutrizione"
        title="Idee per i tuoi target"
        description="Ricette ordinate per quanto ti avvicinano a ciò che ti manca oggi, non per quante proteine hanno in assoluto."
      />

      <Card className="mb-4">
        <div className="flex flex-col gap-3 p-4 sm:flex-row">
          <input
            className="input flex-1"
            placeholder="Un ingrediente o un piatto — es. pollo, salmone, lenticchie (vuoto = scelgo io)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !loading && search(query)}
          />
          <button className="btn-primary sm:w-44" onClick={() => search(query)} disabled={loading}>
            {loading ? "Cerco…" : "Trova ricette"}
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 border-t border-white/[0.06] px-4 py-2.5">
          <span className="mr-1 text-[11px] text-white/30">Prova con</span>
          {SPUNTI.map((s) => (
            <button
              key={s}
              disabled={loading}
              onClick={() => {
                setQuery(s);
                search(s);
              }}
              className="rounded-lg border border-white/[0.08] px-2.5 py-1 text-[12px] text-white/55 transition hover:border-lime-400/30 hover:bg-lime-400/[0.07] hover:text-lime-200 disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
      </Card>

      <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-iris-400/20 bg-iris-400/[0.06] px-4 py-3 text-[12.5px] leading-relaxed text-iris-100/80">
        <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0 fill-iris-300">
          <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 15h-2v-6h2v6Zm0-8h-2V7h2v2Z" />
        </svg>
        <p>
          I valori qui sono <strong>stimati</strong>: le quantità delle ricette sono scritte in
          linguaggio comune e vengono convertite in grammi. Per un conteggio esatto usa il
          diario, dove scegli tu l'alimento e i grammi.
        </p>
      </div>

      {error && (
        <div className="mb-4">
          <Notice>{error}</Notice>
        </div>
      )}

      {loading && (
        <Card className="mb-4">
          <div className="flex items-center gap-4 px-5 py-5">
            <Mascot size={46} mood="thinking" />
            <div>
              <p className="text-[14px] font-medium text-white">Analizzo gli ingredienti…</p>
              <p className="text-[12.5px] leading-snug text-white/45">
                Converto le quantità in grammi e sommo i macro dal database. La prima volta
                può servire fino a un minuto; le ricette già viste tornano subito.
              </p>
            </div>
          </div>
        </Card>
      )}

      {recipes && !loading && recipes.length === 0 && (
        <Card>
          <Empty
            title="Nessuna ricetta abbastanza affidabile"
            hint="Le ricette con meno del 75% di ingredienti riconosciuti vengono scartate: meglio non proporre un totale che sembra un dato e non lo è. Prova con un altro ingrediente."
          />
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {!loading &&
          recipes?.map((r, i) => (
            <motion.div
              key={`${r.name}-${i}`}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07, duration: 0.45 }}
              className="glass sheen glass-hover overflow-hidden"
            >
              {r.thumbnail_url && (
                <div className="relative h-44 overflow-hidden">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={r.thumbnail_url}
                    alt={r.name}
                    className="h-full w-full object-cover transition duration-700 hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-ink-900 via-ink-900/35 to-transparent" />
                  <div className="absolute bottom-3 left-4 right-4">
                    <h3 className="text-[16px] font-semibold leading-tight text-white drop-shadow">
                      {r.name}
                    </h3>
                    <p className="mt-0.5 text-[11.5px] text-white/55">
                      {[r.category, r.area ? `cucina ${r.area.toLowerCase()}` : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                </div>
              )}

              <div className="p-4">
                <div className="mb-3 grid grid-cols-4 gap-2 rounded-xl border border-white/[0.07] bg-black/25 p-3">
                  {[
                    ["kcal", Math.round(r.kcal_per_serving)],
                    ["prot.", `${Math.round(r.protein_per_serving)}g`],
                    ["carb.", `${Math.round(r.carbs_per_serving)}g`],
                    ["grassi", `${Math.round(r.fat_per_serving)}g`],
                  ].map(([l, v]) => (
                    <div key={l} className="text-center">
                      <p className="font-mono text-[14px] tabular-nums text-white">{v}</p>
                      <p className="text-[9.5px] uppercase tracking-wide text-white/30">{l}</p>
                    </div>
                  ))}
                </div>

                <p className="mb-3 text-[11px] text-white/30">
                  per porzione · {r.servings} porzioni ·{" "}
                  <span className={r.coverage < 0.9 ? "text-amber-300/70" : ""}>
                    {Math.round(r.coverage * 100)}% ingredienti riconosciuti
                  </span>
                  {r.original_name && <> · titolo originale «{r.original_name}»</>}
                </p>

                {r.reasons.length > 0 && (
                  <ul className="mb-3 space-y-1.5">
                    {r.reasons.map((reason, k) => (
                      <li key={k} className="flex gap-2 text-[12.5px] leading-snug text-white/60">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-lime-400" />
                        {reason}
                      </li>
                    ))}
                  </ul>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setExpanded(expanded === r.name ? null : r.name)}
                    className="btn-ghost flex-1 text-[12.5px]"
                  >
                    {expanded === r.name ? "Nascondi" : "Ingredienti e preparazione"}
                  </button>
                  {r.youtube_url && (
                    <a
                      href={r.youtube_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-ghost text-[12.5px]"
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4 fill-rose-300">
                        <path d="M8 5v14l11-7L8 5Z" />
                      </svg>
                      Video
                    </a>
                  )}
                </div>

                {expanded === r.name && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-3 space-y-3">
                      <div>
                        <p className="label">Ingredienti</p>
                        <ul className="space-y-1">
                          {r.ingredients.map((ing, k) => (
                            <li key={k} className="text-[12.5px] text-white/60">
                              {ing}
                            </li>
                          ))}
                        </ul>
                      </div>
                      {r.instructions && (
                        <div>
                          <p className="label">Preparazione</p>
                          <p className="whitespace-pre-line text-[12.5px] leading-relaxed text-white/55">
                            {r.instructions}
                          </p>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}

                <div className="mt-3 border-t border-white/[0.06] pt-3">
                  <AskCoachButton
                    size="sm"
                    question={`Ho trovato la ricetta «${r.name}»: ${Math.round(r.kcal_per_serving)} kcal, ${Math.round(r.protein_per_serving)} g di proteine, ${Math.round(r.carbs_per_serving)} g di carboidrati e ${Math.round(r.fat_per_serving)} g di grassi a porzione. Come la adatto ai miei target di oggi?`}
                    context="Sezione Ricette"
                    label="Come la adatto ai miei macro?"
                  />
                </div>
              </div>
            </motion.div>
          ))}
      </div>
    </>
  );
}
