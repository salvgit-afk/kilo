"use client";

/**
 * Suggerimenti di ricette e ricette salvate.
 *
 * A differenza del diario, qui i valori sono **stimati**: le quantità delle
 * ricette sono scritte per un essere umano ("¼ cup", "1 clove") e vanno
 * convertite in grammi. L'interfaccia lo dichiara apertamente — con la
 * copertura degli ingredienti riconosciuti — invece di mostrare numeri che
 * sembrano precisi e non lo sono.
 *
 * Si cerca in italiano: il backend traduce la ricerca per la fonte (che
 * conosce solo l'inglese) e poi traduce le ricette trovate.
 *
 * Tre viste con lo stesso selettore a schede della sezione Integratori:
 * **Idee per te**, **Importa** e **Salvate**. Una ricetta salvata è una copia
 * di quella già analizzata, salvata nel database: si riapre subito, su ogni
 * dispositivo.
 *
 * L'importazione è la via rapida: si incolla una ricetta già scritta invece
 * di comporla ingrediente per ingrediente. A differenza dei suggerimenti, lì
 * i grammi li conferma l'utente, quindi i valori non sono più una stima.
 */

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type RecipeSuggestion, type SavedRecipe } from "@/lib/api";
import type { Intent } from "@/lib/coach";
import { Card, Empty, Notice, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import { AskCoachButton } from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { RecipeImport } from "@/components/RecipeImport";

// Ricette per volta: la prima pagina arriva subito, le altre su richiesta.
const PAGE_SIZE = 4;

function suggestUrl(profileId: number, query: string, exclude: string[]): string {
  const params = new URLSearchParams({ profile_id: String(profileId), top: String(PAGE_SIZE) });
  if (query.trim()) params.set("query", query.trim());
  for (const id of exclude) params.append("exclude", id);
  return `/nutrition/recipes/suggest?${params.toString()}`;
}

const SPUNTI = ["pollo", "salmone", "tonno", "uova", "lenticchie", "colazione", "spuntino"];

export function Recipes({
  profileId,
  intent,
  onIntentHandled,
}: {
  profileId: number;
  intent?: Intent | null;
  onIntentHandled?: () => void;
}) {
  const [tab, setTab] = useState<"suggest" | "import" | "saved">("suggest");
  const [query, setQuery] = useState("");
  const [recipes, setRecipes] = useState<RecipeSuggestion[] | null>(null);
  const [saved, setSaved] = useState<SavedRecipe[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "Carica altre": la ricerca da proseguire e se può esserci altro.
  const [lastQuery, setLastQuery] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadSaved = useCallback(async () => {
    try {
      setSaved(await api.get<SavedRecipe[]>(`/nutrition/recipes/saved?profile_id=${profileId}`));
    } catch {
      setSaved([]);
    }
  }, [profileId]);

  useEffect(() => {
    loadSaved();
  }, [loadSaved]);

  const search = useCallback(
    async (text: string) => {
      setTab("suggest");
      setLoading(true);
      setError(null);
      try {
        const trovate = await api.get<RecipeSuggestion[]>(suggestUrl(profileId, text, []));
        setRecipes(trovate);
        setLastQuery(text);
        setHasMore(trovate.length === PAGE_SIZE);
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

  async function loadMore() {
    if (!recipes) return;
    setLoadingMore(true);
    setError(null);
    try {
      const gia = recipes.map((r) => r.meal_id).filter((id): id is string => !!id);
      const altre = await api.get<RecipeSuggestion[]>(suggestUrl(profileId, lastQuery, gia));
      const nuove = altre.filter((r) => !gia.includes(r.meal_id ?? ""));
      setRecipes([...recipes, ...nuove]);
      setHasMore(altre.length === PAGE_SIZE && nuove.length > 0);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 503
          ? e.message
          : "Non sono riuscito a caricare altre ricette. Riprova tra poco."
      );
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    if (intent?.section === "ricette" && intent.recipeQuery !== undefined) {
      setQuery(intent.recipeQuery);
      search(intent.recipeQuery);
      onIntentHandled?.();
    }
  }, [intent, search, onIntentHandled]);

  async function toggleSaved(recipe: RecipeSuggestion) {
    if (!recipe.meal_id) return;
    const salvare = !recipe.saved;
    // Aggiornamento immediato; se il salvataggio fallisce si torna indietro.
    const segna = (valore: boolean) =>
      setRecipes((prev) =>
        prev?.map((r) => (r.meal_id === recipe.meal_id ? { ...r, saved: valore } : r)) ?? prev
      );
    segna(salvare);
    try {
      if (salvare) {
        await api.post(`/nutrition/recipes/saved?profile_id=${profileId}`, recipe);
      } else {
        await api.del(`/nutrition/recipes/saved/${encodeURIComponent(recipe.meal_id)}?profile_id=${profileId}`);
      }
      loadSaved();
    } catch {
      segna(!salvare);
    }
  }

  const salvate = saved?.map((s) => s.recipe) ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Nutrizione"
        title="Idee per i tuoi target"
        description="Ricette ordinate per quanto ti avvicinano a ciò che ti manca oggi, non per quante proteine hanno in assoluto."
      />

      <div className="mb-4 inline-flex rounded-xl border border-white/10 bg-white/[0.03] p-1">
        {(
          [
            ["suggest", "Idee per te"],
            ["import", "Importa"],
            ["saved", `Salvate${saved ? ` · ${saved.length}` : ""}`],
          ] as const
        ).map(([id, text]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`relative rounded-lg px-3.5 py-2 text-[12.5px] font-medium transition ${
              tab === id ? "text-ink-900" : "text-white/55 hover:text-white"
            }`}
          >
            {tab === id && (
              <motion.span
                layoutId="recipes-tab"
                className="absolute inset-0 rounded-lg bg-gradient-to-b from-lime-400 to-lime-500"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <span className="relative">{text}</span>
          </button>
        ))}
      </div>

      {tab === "import" ? (
        <RecipeImport
          profileId={profileId}
          onSaved={() => {
            loadSaved();
            setTab("saved");
          }}
        />
      ) : tab === "saved" ? (
        !saved ? (
          <Spinner label="Carico le ricette salvate…" />
        ) : salvate.length === 0 ? (
          <Card>
            <div className="grid place-items-center px-6 py-12 text-center">
              <Mascot size={54} interactive />
              <p className="mt-3 text-[14px] text-white/75">Nessuna ricetta salvata</p>
              <p className="mt-1.5 max-w-sm text-[12.5px] leading-relaxed text-white/40">
                Tocca il segnalibro su una ricetta che ti piace: la ritrovi qui, con macro,
                ingredienti e preparazione, senza doverla cercare di nuovo.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <button className="btn-primary" onClick={() => setTab("suggest")}>
                  Cerca ricette
                </button>
                <button className="btn-ghost" onClick={() => setTab("import")}>
                  Incolla una ricetta tua
                </button>
              </div>
            </div>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {salvate.map((r, i) => (
              <RecipeCard
                key={r.meal_id ?? `${r.name}-${i}`}
                recipe={r}
                index={i}
                savedView
                onToggleSaved={async () => {
                  if (!r.meal_id) return;
                  setSaved((prev) => prev?.filter((s) => s.recipe.meal_id !== r.meal_id) ?? prev);
                  setRecipes((prev) =>
                    prev?.map((x) => (x.meal_id === r.meal_id ? { ...x, saved: false } : x)) ?? prev
                  );
                  await api
                    .del(`/nutrition/recipes/saved/${encodeURIComponent(r.meal_id)}?profile_id=${profileId}`)
                    .catch(loadSaved);
                }}
              />
            ))}
          </div>
        )
      ) : (
        <>
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
              Le <strong>Ricette Kilo</strong> vengono per prime: hanno ogni dose in grammi, quindi i
              valori sono esatti. Le altre arrivano da una raccolta internazionale con quantità in
              linguaggio comune, e i loro valori sono <strong>stimati</strong>.
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
                <RecipeCard
                  key={r.meal_id ?? `${r.name}-${i}`}
                  recipe={r}
                  index={i}
                  onToggleSaved={() => toggleSaved(r)}
                />
              ))}
          </div>

          {!loading && recipes && recipes.length > 0 && (
            <div className="mt-5 flex flex-col items-center gap-2">
              {hasMore ? (
                <>
                  <button className="btn-ghost min-w-[220px]" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? (
                      <>
                        <Mascot size={20} mood="thinking" />
                        Cerco altre ricette…
                      </>
                    ) : (
                      "Carica altre ricette"
                    )}
                  </button>
                  {loadingMore && (
                    <p className="max-w-sm text-center text-[11.5px] leading-snug text-white/35">
                      Finite le Ricette Kilo, analizzo quelle della raccolta internazionale: la prima
                      volta può servire fino a un minuto.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[12px] text-white/35">
                  Non ci sono altre ricette per questa ricerca.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}

function RecipeCard({
  recipe: r,
  index,
  savedView = false,
  onToggleSaved,
}: {
  recipe: RecipeSuggestion;
  index: number;
  /** Nella vista Salvate i motivi del punteggio non valgono più: erano di quel giorno. */
  savedView?: boolean;
  onToggleSaved: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const bookmark = r.meal_id && (
    <button
      onClick={onToggleSaved}
      aria-pressed={r.saved}
      aria-label={r.saved ? "Rimuovi dalle ricette salvate" : "Salva la ricetta"}
      title={r.saved ? "Rimuovi dalle salvate" : "Salva la ricetta"}
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl border backdrop-blur-md transition ${
        r.saved
          ? "border-lime-400/50 bg-lime-400/90 text-ink-900"
          : "border-white/20 bg-black/40 text-white/80 hover:border-lime-400/50 hover:text-lime-200"
      }`}
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill={r.saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth={2}>
        <path d="M6 3h12v18l-6-4-6 4V3Z" strokeLinejoin="round" />
      </svg>
    </button>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.45 }}
      className="glass sheen glass-hover overflow-hidden"
    >
      {r.thumbnail_url ? (
        <div className="relative h-44 overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={r.thumbnail_url}
            alt={r.name}
            className="h-full w-full object-cover transition duration-700 hover:scale-105"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-ink-900 via-ink-900/35 to-transparent" />
          <div className="absolute right-3 top-3">{bookmark}</div>
          <div className="absolute bottom-3 left-4 right-4">
            <h3 className="text-[16px] font-semibold leading-tight text-white drop-shadow">{r.name}</h3>
            <p className="mt-0.5 text-[11.5px] text-white/55">
              {[r.category, r.area ? `cucina ${r.area.toLowerCase()}` : null].filter(Boolean).join(" · ")}
            </p>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3 px-4 pt-4">
          <h3 className="text-[16px] font-semibold leading-tight text-white">{r.name}</h3>
          {bookmark}
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

        {r.source === "kilo" ? (
          <p className="mb-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-white/30">
            <span className="rounded bg-lime-400/15 px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wide text-lime-200">
              Ricetta Kilo · dosi esatte
            </span>
            per porzione · {r.servings === 1 ? "1 porzione" : `${r.servings} porzioni`}
            {r.minutes ? <> · {r.minutes} min</> : null}
          </p>
        ) : (
          <p className="mb-3 text-[11px] text-white/30">
            {r.source === "import" ? (
              <span className="mr-1.5 rounded bg-iris-400/15 px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wide text-iris-200">
                tua
              </span>
            ) : (
              <span className="mr-1.5 rounded bg-amber-300/15 px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wide text-amber-100">
                stimata
              </span>
            )}
            per porzione · {r.servings} porzioni ·{" "}
            <span className={r.coverage < 0.9 ? "text-amber-300/70" : ""}>
              {Math.round(r.coverage * 100)}% ingredienti riconosciuti
            </span>
            {r.original_name && <> · titolo originale «{r.original_name}»</>}
          </p>
        )}

        {!savedView && r.reasons.length > 0 && (
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
          <button onClick={() => setExpanded(!expanded)} className="btn-ghost flex-1 text-[12.5px]">
            {expanded ? "Nascondi" : "Ingredienti e preparazione"}
          </button>
          {r.youtube_url && (
            <a href={r.youtube_url} target="_blank" rel="noopener noreferrer" className="btn-ghost text-[12.5px]">
              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-rose-300">
                <path d="M8 5v14l11-7L8 5Z" />
              </svg>
              Video
            </a>
          )}
        </div>

        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} className="overflow-hidden">
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
                  <p className="whitespace-pre-line text-[12.5px] leading-relaxed text-white/55">{r.instructions}</p>
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
  );
}
