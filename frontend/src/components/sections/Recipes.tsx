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
import { Mascot } from "@/components/Mascot";
import { RecipeImport } from "@/components/RecipeImport";
import { RecipeCard } from "@/components/recipes/RecipeCard";
import { CATEGORIE, ICONE, Icona, type CategoriaId } from "@/components/recipes/categorie";

// Ricette per volta: la prima pagina arriva subito, le altre su richiesta.
const PAGE_SIZE = 4;

function suggestUrl(profileId: number, query: string, exclude: string[]): string {
  const params = new URLSearchParams({ profile_id: String(profileId), top: String(PAGE_SIZE) });
  if (query.trim()) params.set("query", query.trim());
  for (const id of exclude) params.append("exclude", id);
  return `/nutrition/recipes/suggest?${params.toString()}`;
}

// Le ricerche rapide, con il colore della categoria che fanno uscire.
const SPUNTI: { cerca: string; nome: string; cat: CategoriaId; icona?: string }[] = [
  { cerca: "pollo", nome: "Pollo", cat: "carne" },
  { cerca: "salmone", nome: "Salmone", cat: "pesce" },
  { cerca: "tonno", nome: "Tonno", cat: "pesce" },
  { cerca: "uova", nome: "Uova", cat: "colazione", icona: ICONE.uovo },
  { cerca: "lenticchie", nome: "Lenticchie", cat: "legumi" },
  { cerca: "colazione", nome: "Colazione", cat: "colazione" },
  { cerca: "spuntino", nome: "Spuntino", cat: "dolci" },
];

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
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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
          {/* Scorre in orizzontale: a 390 px le pillole non ci stanno tutte. */}
          <div
            role="group"
            aria-label="Prova con"
            className="-mx-4 mb-3 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {SPUNTI.map((s) => {
              const c = CATEGORIE[s.cat];
              const attiva = recipes !== null && lastQuery === s.cerca;
              return (
                <button
                  key={s.cerca}
                  disabled={loading}
                  aria-pressed={attiva}
                  onClick={() => {
                    setQuery(s.cerca);
                    search(s.cerca);
                  }}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-gradient-to-br px-3.5 py-2 text-[13px] font-medium transition disabled:opacity-40 ${c.sfondo} ${c.testo} ${
                    attiva ? "border-white/40" : "border-white/10 hover:border-white/25"
                  }`}
                >
                  <Icona d={s.icona ?? c.icona} className="h-3.5 w-3.5" /> {s.nome}
                </button>
              );
            })}
          </div>

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

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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
