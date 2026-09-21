"use client";

/**
 * Diario alimentare — la via precisa del conteggio.
 *
 * La ricerca mostra **tutti** i candidati con i loro valori per 100 g e non
 * sceglie al posto dell'utente. È voluto: i dati di Open Food Facts sono
 * inseriti dagli utenti e a volte sbagliati (esiste davvero una voce "petto
 * di pollo" da 65 kcal e 3 g di proteine). Con i valori in vista un errore
 * del genere si riconosce a colpo d'occhio prima di finire nel conteggio.
 *
 * La parte agentica è «Cosa mi manca oggi»: alimenti e grammi calcolati per
 * chiudere le proteine nelle calorie rimaste, aggiunti solo con un clic.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  MEAL_LABELS,
  api,
  type Diary as DiaryData,
  type FoodResult,
  type GapSuggestions,
} from "@/lib/api";
import { mealForNow, type Intent } from "@/lib/coach";
import { Card, Empty, Notice, ProgressRing, StatBar, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import { AskCoachButton, CloseButton, Modal, NumberField } from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { BarcodeScanner } from "@/components/BarcodeScanner";
import { RecipeToDiaryDialog } from "@/components/RecipeToDiary";
import { ApiError } from "@/lib/api";
import { KiloNote } from "@/components/KiloNote";

const MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"];

export function Diary({
  profileId,
  intent,
  onIntentHandled,
}: {
  profileId: number;
  intent?: Intent | null;
  onIntentHandled?: () => void;
}) {
  const [data, setData] = useState<DiaryData | null>(null);
  const [gap, setGap] = useState<GapSuggestions | null>(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState<{ meal: string; query?: string } | null>(null);
  // Aggiunta di una ricetta intera: porta dentro tutti i suoi ingredienti.
  const [addingRecipe, setAddingRecipe] = useState<string | null>(null);

  const loadGap = useCallback(() => {
    api
      .get<GapSuggestions>(`/nutrition/diary/fill-gap?profile_id=${profileId}`)
      .then(setGap)
      .catch(() => setGap(null));
  }, [profileId]);

  const load = useCallback(async () => {
    setData(await api.get<DiaryData>(`/nutrition/diary?profile_id=${profileId}`));
    setLoading(false);
    loadGap();
  }, [profileId, loadGap]);

  useEffect(() => {
    load();
  }, [load]);

  // Il coach ha proposto di cercare un alimento: si apre la ricerca già compilata.
  useEffect(() => {
    if (intent?.section === "diario" && intent.foodQuery) {
      setAdding({ meal: mealForNow(), query: intent.foodQuery });
      onIntentHandled?.();
    }
  }, [intent, onIntentHandled]);

  if (loading || !data) return <Spinner label="Carico il diario…" />;

  const { totals, targets, remaining, progress } = data;
  const byType = Object.fromEntries(data.meals.map((m) => [m.meal_type, m]));

  return (
    <>
      <PageHeader
        eyebrow="Nutrizione"
        title="Diario di oggi"
        description="Cerchi l'alimento, scegli tu quale e indichi i grammi: qui non c'è niente di stimato."
      />

      <KiloNote section="diario" />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_350px]">
        <div className="space-y-3">
          {MEAL_ORDER.map((type) => {
            const meal = byType[type];
            return (
              <Card key={type} hover>
                <div className="flex items-center justify-between gap-3 px-5 py-3.5">
                  <div className="flex items-baseline gap-3">
                    <h3 className="text-[14px] font-semibold text-white">{MEAL_LABELS[type]}</h3>
                    {meal && meal.items.length > 0 && (
                      <span className="font-mono text-[12px] tabular-nums text-white/45">
                        {Math.round(meal.kcal)} kcal · P {Math.round(meal.protein_g)}g
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      onClick={() => setAddingRecipe(type)}
                      title="Aggiungi una ricetta salvata con tutti i suoi ingredienti"
                      className="flex h-9 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 text-[12.5px] text-white/60 transition hover:border-iris-400/40 hover:bg-iris-400/[0.09] hover:text-iris-200"
                    >
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                        <path d="M4 3h13a3 3 0 0 1 3 3v15H7a3 3 0 0 1-3-3V3Zm2 2v13a1 1 0 0 0 1 1h11V6a1 1 0 0 0-1-1H6Zm3 3h7v2H9V8Zm0 4h7v2H9v-2Z" />
                      </svg>
                      <span className="hidden sm:inline">Ricetta</span>
                    </button>
                    <button
                      onClick={() => setAdding({ meal: type })}
                      className="flex h-9 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 text-[12.5px] text-white/60 transition hover:border-lime-400/30 hover:bg-lime-400/[0.08] hover:text-lime-200"
                    >
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                        <path d="M11 11V5h2v6h6v2h-6v6h-2v-6H5v-2h6Z" />
                      </svg>
                      Aggiungi
                    </button>
                  </div>
                </div>

                {meal && meal.items.length > 0 && (
                  <div className="border-t border-white/[0.06] px-2 py-1.5">
                    {meal.items.map((item) => (
                      <div
                        key={item.id}
                        className="group flex items-center gap-3 rounded-lg px-3 py-2 transition hover:bg-white/[0.03]"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] text-white/80">{item.name}</p>
                          <p className="text-[11px] text-white/35">{Math.round(item.quantity_g)} g</p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-mono text-[12.5px] tabular-nums text-white/70">
                            {Math.round(item.kcal)} kcal
                          </p>
                          <p className="font-mono text-[10.5px] tabular-nums text-white/30">
                            P{Math.round(item.protein_g)} C{Math.round(item.carbs_g)} G
                            {Math.round(item.fat_g)}
                          </p>
                        </div>
                        <button
                          onClick={async () => {
                            await api.del(`/nutrition/diary/items/${item.id}`);
                            load();
                          }}
                          aria-label="Elimina"
                          className="shrink-0 rounded-lg p-1.5 text-white/20 opacity-0 transition group-hover:opacity-100 hover:bg-rose-400/10 hover:text-rose-300"
                        >
                          <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                            <path d="M7 6V4h10v2h4v2h-2v12H5V8H3V6h4Zm2 4v8h2v-8H9Zm4 0v8h2v-8h-2Z" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            );
          })}
        </div>

        <div className="space-y-4">
          {gap && <GapCard gap={gap} profileId={profileId} onAdded={load} />}

          <Card>
            <div className="flex flex-col items-center gap-4 px-5 py-5">
              <ProgressRing
                value={progress.kcal ?? 0}
                label={`${Math.round(totals.kcal ?? 0)}`}
                sublabel={`di ${Math.round(targets.target_kcal)} kcal`}
              />
              <p className="text-center text-[12.5px] text-white/45">
                {remaining.kcal > 0
                  ? `Ti restano ${Math.round(remaining.kcal)} kcal`
                  : `Hai superato di ${Math.abs(Math.round(remaining.kcal))} kcal`}
              </p>
            </div>

            <div className="space-y-3 border-t border-white/[0.06] px-5 py-4">
              <StatBar label="Proteine" value={totals.protein_g ?? 0} target={targets.protein_g} tone="lime" />
              <StatBar label="Carboidrati" value={totals.carbs_g ?? 0} target={targets.carbs_g} tone="iris" />
              <StatBar label="Grassi" value={totals.fat_g ?? 0} target={targets.fat_g} tone="rose" />
              <StatBar label="Fibra" value={totals.fiber_g ?? 0} target={targets.fiber_g} tone="lime" />
            </div>
          </Card>

          {targets.warnings.map((w, i) => (
            <Notice key={i}>{w}</Notice>
          ))}
        </div>
      </div>

      <AnimatePresence>
        {addingRecipe && (
          <RecipeToDiaryDialog
            profileId={profileId}
            mealType={addingRecipe}
            mealOrder={MEAL_ORDER}
            onClose={() => setAddingRecipe(null)}
            onAdded={() => {
              setAddingRecipe(null);
              load();
            }}
          />
        )}
        {adding && (
          <FoodSearchDialog
            profileId={profileId}
            mealType={adding.meal}
            initialQuery={adding.query}
            onClose={() => setAdding(null)}
            onAdded={() => {
              setAdding(null);
              load();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function BarcodeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current" aria-hidden>
      <path d="M3 5h2v14H3V5Zm3 0h1v14H6V5Zm2 0h2v14H8V5Zm3 0h1v14h-1V5Zm2 0h3v14h-3V5Zm4 0h1v14h-1V5Zm2 0h2v14h-2V5Z" />
    </svg>
  );
}

/** Prodotto non trovato (o incompleto) su Open Food Facts: si copia l'etichetta. */
function ManualProductForm({
  barcode,
  reason,
  onCancel,
  onCreated,
}: {
  barcode: string | null;
  reason: string | null;
  onCancel: () => void;
  onCreated: (prodotto: FoodResult) => void;
}) {
  const [name, setName] = useState("");
  const [kcal, setKcal] = useState<number | null>(null);
  const [protein, setProtein] = useState<number | null>(null);
  const [carbs, setCarbs] = useState<number | null>(null);
  const [fat, setFat] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const completo = name.trim().length >= 2 && [kcal, protein, carbs, fat].every((v) => v !== null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onCreated(
        await api.post<FoodResult>("/nutrition/foods/manual", {
          name: name.trim(),
          barcode,
          kcal_100g: kcal,
          protein_100g: protein,
          carbs_100g: carbs,
          fat_100g: fat,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Salvataggio non riuscito");
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 p-2">
      <Notice>{reason ?? "Prodotto non trovato, vuoi inserirlo manualmente?"}</Notice>
      <p className="text-[12px] leading-snug text-white/45">
        Copia i valori <strong className="text-white/70">per 100 g</strong> dalla tabella
        nutrizionale sulla confezione. Il prodotto resta visibile solo a te
        {barcode ? ", e la prossima scansione di questo codice lo ritrova subito" : ""}.
      </p>
      <div>
        <label className="label">Nome del prodotto</label>
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="es. Kefir magro · marca"
        />
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        {(
          [
            ["Calorie", kcal, setKcal, "kcal", 950],
            ["Proteine", protein, setProtein, "g", 100],
            ["Carboidrati", carbs, setCarbs, "g", 100],
            ["Grassi", fat, setFat, "g", 100],
          ] as const
        ).map(([etichetta, valore, imposta, unita, massimo]) => (
          <div key={etichetta}>
            <label className="label">{etichetta}</label>
            <NumberField
              value={valore}
              onChange={imposta}
              min={0}
              max={massimo}
              decimals={1}
              suffix={unita}
              placeholder="—"
              ariaLabel={`${etichetta} per 100 g`}
            />
          </div>
        ))}
      </div>
      {barcode && <p className="font-mono text-[11px] text-white/30">Codice {barcode}</p>}
      {error && <p className="text-[12px] text-rose-200/80">{error}</p>}
      <div className="flex gap-2">
        <button className="btn-ghost flex-1" onClick={onCancel}>
          Annulla
        </button>
        <button className="btn-primary flex-1" disabled={!completo || saving} onClick={save}>
          {saving ? "Salvo…" : "Salva e usa"}
        </button>
      </div>
    </div>
  );
}

function GapCard({
  gap,
  profileId,
  onAdded,
}: {
  gap: GapSuggestions;
  profileId: number;
  onAdded: () => void;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const meal = mealForNow();

  async function add(ingredientId: number, grams: number) {
    setBusy(ingredientId);
    try {
      await api.post(`/nutrition/diary/items?profile_id=${profileId}`, {
        ingredient_id: ingredientId,
        grams,
        meal_type: meal,
      });
      onAdded();
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <div className="flex items-start gap-3 border-b border-white/[0.06] px-4 py-4">
        <Mascot size={36} />
        <div className="min-w-0">
          <h2 className="text-[14.5px] font-semibold text-white">Cosa mi manca oggi</h2>
          <p className="mt-0.5 text-[12.5px] leading-snug text-white/50">{gap.message}</p>
        </div>
      </div>

      {gap.foods.length > 0 && (
        <div className="space-y-1.5 p-3">
          {gap.foods.map((f) => (
            <div
              key={f.ingredient_id}
              className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] text-white/85" title={f.name}>
                  {f.name}
                </p>
                <p className="font-mono text-[11px] tabular-nums text-white/40">
                  {f.grams} g · {f.kcal} kcal · P{f.protein_g} C{f.carbs_g} G{f.fat_g}
                </p>
                {f.habitual && <p className="text-[10.5px] text-lime-300/70">lo registri spesso</p>}
              </div>
              <button
                disabled={busy !== null}
                onClick={() => add(f.ingredient_id, f.grams)}
                title={`Aggiungi ${f.grams} g a ${MEAL_LABELS[meal]}`}
                aria-label={`Aggiungi ${f.grams} g di ${f.name}`}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-lime-400/25 bg-lime-400/[0.08] text-lime-200 transition hover:bg-lime-400/[0.18] disabled:opacity-40"
              >
                {busy === f.ingredient_id ? (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-lime-200/30 border-t-lime-200" />
                ) : (
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                    <path d="M11 11V5h2v6h6v2h-6v6h-2v-6H5v-2h6Z" />
                  </svg>
                )}
              </button>
            </div>
          ))}
          <p className="px-1 pt-1 text-[11px] leading-snug text-white/30">
            Con + la porzione va in {MEAL_LABELS[meal].toLowerCase()}: puoi eliminarla quando
            vuoi.
          </p>
        </div>
      )}

      <div className="border-t border-white/[0.06] px-4 py-3">
        <AskCoachButton
          size="sm"
          question="Cosa potrei mangiare nel resto della giornata per chiudere i miei macro?"
          context="Sezione Diario"
          label="Chiedi idee a Kilo"
        />
      </div>
    </Card>
  );
}

function FoodSearchDialog({
  profileId,
  mealType,
  initialQuery,
  onClose,
  onAdded,
}: {
  profileId: number;
  mealType: string;
  initialQuery?: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [meal, setMeal] = useState(mealType);
  const [query, setQuery] = useState(initialQuery ?? "");
  const [results, setResults] = useState<FoodResult[]>([]);
  const [names, setNames] = useState<Record<number, string>>({});
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<FoodResult | null>(null);
  const [grams, setGrams] = useState<number | null>(100);
  const [saving, setSaving] = useState(false);
  // "scan": fotocamera; "manual": prodotto non trovato, si inserisce dall'etichetta.
  const [mode, setMode] = useState<"search" | "scan" | "manual">("search");
  const [lookingUp, setLookingUp] = useState(false);
  const [manualBarcode, setManualBarcode] = useState<string | null>(null);
  const [manualReason, setManualReason] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const gramsRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function lookupBarcode(code: string) {
    setLookingUp(true);
    setError(null);
    try {
      const prodotto = await api.get<FoodResult>(`/nutrition/foods/barcode/${encodeURIComponent(code)}`);
      setResults([prodotto]);
      setSelected(prodotto);
      setQuery("");
      setMode("search");
      setTimeout(() => gramsRef.current?.focus(), 80);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setManualBarcode(code);
        setManualReason(e.message);
        setMode("manual");
      } else {
        setError(e instanceof Error ? e.message : "Lettura del codice non riuscita");
        setMode("search");
      }
    } finally {
      setLookingUp(false);
    }
  }

  // La ricerca interroga USDA e Open Food Facts: si aspetta che l'utente
  // smetta di digitare invece di partire a ogni tasto.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    let annullata = false;
    const timer = setTimeout(async () => {
      setSearching(true);
      setError(null);
      try {
        const res = await api.get<FoodResult[]>(
          `/nutrition/foods/search?q=${encodeURIComponent(q)}&limit=12`
        );
        if (annullata) return;
        setResults(res);
        // I nomi italiani mancanti arrivano dopo, senza far aspettare i risultati.
        const mancanti = res.filter((r) => !r.name_it).map((r) => r.ingredient_id);
        if (mancanti.length) {
          api
            .post<Record<string, string>>("/nutrition/foods/names", { ids: mancanti })
            .then((tradotti) => {
              if (annullata) return;
              setNames((prev) => ({
                ...prev,
                ...Object.fromEntries(Object.entries(tradotti).map(([k, v]) => [Number(k), v])),
              }));
            })
            .catch(() => {});
        }
      } catch (e) {
        if (!annullata) setError(e instanceof Error ? e.message : "Ricerca non riuscita");
      } finally {
        if (!annullata) setSearching(false);
      }
    }, 450);
    return () => {
      annullata = true;
      clearTimeout(timer);
    };
  }, [query]);

  const nameOf = (r: FoodResult) => r.name_it ?? names[r.ingredient_id] ?? r.name;

  async function add() {
    if (!selected || !grams) return;
    setSaving(true);
    setError(null);
    try {
      await api.post(`/nutrition/diary/items?profile_id=${profileId}`, {
        ingredient_id: selected.ingredient_id,
        grams,
        meal_type: meal,
      });
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito ad aggiungere l'alimento");
      setSaving(false);
    }
  }

  const factor = (grams ?? 0) / 100;

  return (
    <Modal onClose={onClose} align="top" className="max-w-xl">
      {/* Intestazione fissa: ricerca e pasto */}
      <div className="shrink-0 space-y-3 border-b border-white/[0.06] p-4">
        <div className="flex items-center gap-2.5">
          <div className="relative flex-1">
            <svg
              viewBox="0 0 24 24"
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 fill-white/25"
            >
              <path d="M10 2a8 8 0 1 0 4.9 14.3l5.4 5.4 1.4-1.4-5.4-5.4A8 8 0 0 0 10 2Zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12Z" />
            </svg>
            <input
              ref={inputRef}
              className="input pl-10"
              placeholder="Cerca un alimento — es. petto di pollo, riso"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelected(null);
                setMode("search");
              }}
            />
          </div>
          <button
            onClick={() => {
              setSelected(null);
              setMode(mode === "scan" ? "search" : "scan");
            }}
            aria-pressed={mode === "scan"}
            title="Scansiona il codice a barre del prodotto"
            className={`flex h-10 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-[12.5px] font-semibold transition ${
              mode === "scan"
                ? "border-lime-400/60 bg-lime-400 text-ink-900"
                : "border-lime-400/40 bg-lime-400/[0.12] text-lime-200 hover:bg-lime-400/[0.2]"
            }`}
          >
            <BarcodeIcon />
            <span className="hidden sm:inline">Scansiona</span>
          </button>
          <CloseButton onClose={onClose} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {MEAL_ORDER.map((m) => (
            <button
              key={m}
              onClick={() => setMeal(m)}
              className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium transition ${
                meal === m
                  ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
                  : "border-white/[0.08] text-white/45 hover:text-white/80"
              }`}
            >
              {MEAL_LABELS[m]}
            </button>
          ))}
          <span className="ml-auto text-[11px] text-white/30">valori per 100 g</span>
        </div>
      </div>

      {/* Risultati: l'unica parte che scorre */}
      <div className="min-h-[140px] flex-1 overflow-y-auto overscroll-contain p-2">
        {mode === "scan" && (
          <div className="p-2">
            <BarcodeScanner onDetected={lookupBarcode} busy={lookingUp} />
            <p className="mt-2 text-[11.5px] leading-snug text-white/35">
              I valori arrivano da Open Food Facts per il prodotto esatto. Una seconda
              scansione dello stesso prodotto è immediata.
            </p>
          </div>
        )}

        {mode === "manual" && (
          <ManualProductForm
            barcode={manualBarcode}
            reason={manualReason}
            onCancel={() => setMode("search")}
            onCreated={(prodotto) => {
              setResults([prodotto]);
              setSelected(prodotto);
              setMode("search");
              setTimeout(() => gramsRef.current?.focus(), 80);
            }}
          />
        )}

        {mode === "search" && query.trim().length < 2 && !selected && (
          <button
            onClick={() => setMode("scan")}
            className="m-2 flex w-[calc(100%-1rem)] items-center gap-3.5 rounded-2xl border border-lime-400/25 bg-lime-400/[0.06] p-4 text-left transition hover:border-lime-400/45 hover:bg-lime-400/[0.1]"
          >
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-lime-400 text-ink-900">
              <BarcodeIcon />
            </span>
            <span className="min-w-0">
              <span className="block text-[14px] font-semibold text-white">
                Hai il prodotto in mano? Scansiona il codice a barre
              </span>
              <span className="mt-0.5 block text-[12px] leading-snug text-white/50">
                È il modo più preciso per i prodotti confezionati: trovi quello esatto, non una
                voce con lo stesso nome. Per frutta, carne o riso sfusi usa la ricerca.
              </span>
            </span>
          </button>
        )}

        {mode === "search" && searching && <Spinner label="Cerco su USDA e Open Food Facts…" />}

        {error && (
          <div className="p-2">
            <Notice>{error}</Notice>
          </div>
        )}

        {mode === "search" && !searching && !error && query.trim().length >= 2 && results.length === 0 && (
          <Empty title="Nessun risultato" hint="Prova con un nome più semplice, es. «riso» o «yogurt greco», oppure scansiona il codice a barre." />
        )}

        {mode === "search" &&
          !searching &&
          results.map((r) => {
            const isSelected = selected?.ingredient_id === r.ingredient_id;
            const nome = nameOf(r);
            return (
              <button
                key={r.ingredient_id}
                onClick={() => {
                  setSelected(r);
                  setTimeout(() => gramsRef.current?.focus(), 60);
                }}
                className={`mb-1 flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition ${
                  isSelected
                    ? "border-lime-400/40 bg-lime-400/[0.08]"
                    : "border-transparent hover:border-white/10 hover:bg-white/[0.04]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-white/85" title={r.name}>
                    {nome}
                  </p>
                  <span
                    className={`mt-0.5 block truncate text-[11.5px] ${
                      r.is_generic ? "text-lime-200/70" : "text-white/40"
                    }`}
                  >
                    {r.source_label}
                  </span>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-mono text-[13px] tabular-nums text-white/80">
                    {Math.round(r.kcal_100g)}
                    <span className="text-[10px] text-white/35"> kcal</span>
                  </p>
                  <p className="font-mono text-[10.5px] tabular-nums text-white/35">
                    P{r.protein_100g.toFixed(1)} C{r.carbs_100g.toFixed(1)} G{r.fat_100g.toFixed(1)}
                  </p>
                </div>
              </button>
            );
          })}
      </div>

      {/* Piè di pagina fisso: sempre visibile, anche con molti risultati */}
      <AnimatePresence initial={false}>
        {selected && (
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 14 }}
            transition={{ duration: 0.18 }}
            className="shrink-0 border-t border-white/[0.08] bg-ink-800/95 p-4"
          >
            <p className="mb-3 truncate text-[13px] font-medium text-white">{nameOf(selected)}</p>
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <NumberField
                value={grams}
                onChange={setGrams}
                min={1}
                max={5000}
                step={10}
                suffix="g"
                ariaLabel="Grammi"
                inputRef={gramsRef}
                onEnter={add}
                className="w-40"
              />
              <div className="flex gap-1.5">
                {[50, 100, 150, 200].map((g) => (
                  <button
                    key={g}
                    onClick={() => setGrams(g)}
                    className={`rounded-lg border px-2.5 py-1.5 text-[11.5px] transition ${
                      grams === g
                        ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
                        : "border-white/10 bg-white/[0.04] text-white/55 hover:bg-white/[0.09] hover:text-white"
                    }`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-3 grid grid-cols-4 gap-2 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
              {[
                ["kcal", Math.round(selected.kcal_100g * factor)],
                ["proteine", `${(selected.protein_100g * factor).toFixed(1)}g`],
                ["carboid.", `${(selected.carbs_100g * factor).toFixed(1)}g`],
                ["grassi", `${(selected.fat_100g * factor).toFixed(1)}g`],
              ].map(([label, value]) => (
                <div key={label} className="text-center">
                  <p className="font-mono text-[14px] tabular-nums text-white">{value}</p>
                  <p className="text-[10px] uppercase tracking-wide text-white/30">{label}</p>
                </div>
              ))}
            </div>

            <button className="btn-primary w-full" disabled={saving || !grams} onClick={add}>
              {saving ? "Aggiungo…" : `Aggiungi a ${MEAL_LABELS[meal]}`}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </Modal>
  );
}
