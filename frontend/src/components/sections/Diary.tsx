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
  localDate,
  type Diary as DiaryData,
  type FoodResult,
  type GapSuggestions,
  type RecentFood,
  type SavedFood,
} from "@/lib/api";
import { mealForNow, type Intent } from "@/lib/coach";
import { Card, Empty, Notice, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import {
  AskCoachButton,
  CloseButton,
  Field,
  MacroGrid,
  Modal,
  NumberField,
  OptionGroup,
} from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { BarcodeScanner } from "@/components/BarcodeScanner";
import { FoodPhotoPanel } from "@/components/FoodPhoto";
import { RecipeToDiaryDialog } from "@/components/RecipeToDiary";
import { ApiError, notifyLogged } from "@/lib/api";
import { KiloNote } from "@/components/KiloNote";

import { MEAL_ORDER, MealTimeline } from "@/components/diary/MealTimeline";
import { DaySummary } from "@/components/diary/DaySummary";
import { DayStrip } from "@/components/diary/DayStrip";
import { ClockIcon, PlannedToggle } from "@/components/diary/Planned";

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
  // Il giorno mostrato: oggi, uno passato o uno futuro (i previsti) scelto dalla striscia.
  const [today, setToday] = useState(() => localDate());
  const [day, setDay] = useState(today);
  const [refreshKey, setRefreshKey] = useState(0);
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
    setData(await api.get<DiaryData>(`/nutrition/diary?profile_id=${profileId}&date=${day}`));
    setLoading(false);
    setRefreshKey((k) => k + 1);
    loadGap();
    // Banner e pallino del menu: il pasto di oggi potrebbe essere appena segnato.
    notifyLogged();
  }, [profileId, day, loadGap]);

  useEffect(() => {
    load();
  }, [load]);

  // L'app resta aperta oltre la mezzanotte: "oggi" va aggiornato, e chi
  // guardava oggi passa al giorno nuovo.
  useEffect(() => {
    const t = setInterval(() => {
      const adesso = localDate();
      if (adesso !== today) {
        setDay((d) => (d === today ? adesso : d));
        setToday(adesso);
      }
    }, 60_000);
    return () => clearInterval(t);
  }, [today]);

  // Il coach ha proposto di cercare un alimento: si apre la ricerca già compilata.
  useEffect(() => {
    if (intent?.section === "diario" && intent.foodQuery) {
      setDay(localDate());
      setAdding({ meal: mealForNow(), query: intent.foodQuery });
      onIntentHandled?.();
    }
  }, [intent, onIntentHandled]);

  if (loading || !data) return <Spinner label="Carico il diario…" />;

  const { targets } = data;

  return (
    <>
      <PageHeader
        eyebrow="Nutrizione"
        title="Diario"
        description="Cerchi l'alimento, scegli tu quale e indichi i grammi: qui non c'è niente di stimato."
      />

      <KiloNote section="diario" />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_350px]">
        <div className="space-y-4">
          <DayStrip profileId={profileId} day={day} today={today} refreshKey={refreshKey} onChange={setDay} />
          {day > today && (
            <div className="flex gap-2.5 rounded-2xl border border-dashed border-lime-400/30 bg-lime-400/[0.05] px-3.5 py-3 text-[12.5px] leading-relaxed text-white/70">
              <ClockIcon className="mt-0.5 h-4 w-4" />
              <p>
                <b className="font-semibold text-white">Giorno in anticipo.</b> Quello che aggiungi resta{" "}
                <i>previsto</i>: non conta nei totali finché, il giorno stesso, non tocchi «Mangiato».
              </p>
            </div>
          )}
          <MealTimeline
            key={`${day}-${data.planned_meals.map((m) => m.meal_type).join()}`}
            meals={data.meals}
            planned={data.planned_meals}
            canConfirm={day <= today}
            onAdd={(meal) => setAdding({ meal })}
            onAddRecipe={(meal) => setAddingRecipe(meal)}
            onChanged={load}
          />
        </div>

        <div className="space-y-4">
          {/* "Cosa mi manca oggi" vale solo per oggi. */}
          {gap && day === today && <GapCard gap={gap} profileId={profileId} onAdded={load} />}

          <DaySummary data={data} profileId={profileId} day={day} today={today} onChanged={load} />

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
            date={day}
            today={today}
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
            date={day}
            today={today}
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

/** "oggi", "ieri", "3 giorni fa", poi la data. */
function quando(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const giorni = Math.round((new Date(localDate()).getTime() - new Date(y, m - 1, d).getTime()) / 86_400_000);
  if (giorni <= 0) return "oggi";
  if (giorni === 1) return "ieri";
  if (giorni < 7) return `${giorni} giorni fa`;
  return new Date(y, m - 1, d).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

function BarcodeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current" aria-hidden>
      <path d="M3 5h2v14H3V5Zm3 0h1v14H6V5Zm2 0h2v14H8V5Zm3 0h1v14h-1V5Zm2 0h3v14h-3V5Zm4 0h1v14h-1V5Zm2 0h2v14h-2V5Z" />
    </svg>
  );
}

function PhotoIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current" aria-hidden>
      <path d="M9 3h6l1.2 2H20a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h3.8L9 3Zm3 5a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0 2a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z" />
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
    <div className="space-y-3 p-2 sm:p-3">
      <Notice>{reason ?? "Prodotto non trovato, vuoi inserirlo manualmente?"}</Notice>
      <p className="text-[12px] leading-snug text-white/45">
        Copia i valori <strong className="text-white/70">per 100 g</strong> dalla tabella
        nutrizionale sulla confezione. Il prodotto resta visibile solo a te
        {barcode ? ", e la prossima scansione di questo codice lo ritrova subito" : ""}.
      </p>
      <Field title="Nome del prodotto">
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="es. Kefir magro · marca"
        />
      </Field>
      <Field title="Valori per 100 g" hint={barcode ? <span className="font-mono">Codice {barcode}</span> : undefined}>
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
              <p className="mb-1.5 text-[11px] text-white/45">{etichetta}</p>
              <NumberField
                value={valore}
                onChange={imposta}
                min={0}
                max={massimo}
                decimals={1}
                suffix={unita}
                steppers="sm"
                placeholder="—"
                ariaLabel={`${etichetta} per 100 g`}
              />
            </div>
          ))}
        </div>
      </Field>
      {error && <Notice>{error}</Notice>}
      <div className="flex gap-2">
        <button className="btn-ghost flex-1 justify-center" onClick={onCancel}>
          Annulla
        </button>
        <button className="btn-primary flex-[1.6] justify-center" disabled={!completo || saving} onClick={save}>
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
  date,
  today,
  initialQuery,
  onClose,
  onAdded,
}: {
  profileId: number;
  mealType: string;
  /** Il giorno mostrato nel diario: non sempre è oggi. */
  date: string;
  today: string;
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
  // "scan": codice a barre; "manual": prodotto non trovato, si inserisce
  // dall'etichetta; "photo": foto dell'etichetta o del piatto.
  const [mode, setMode] = useState<"search" | "scan" | "manual" | "photo">("search");
  const [lookingUp, setLookingUp] = useState(false);
  const [manualBarcode, setManualBarcode] = useState<string | null>(null);
  const [manualReason, setManualReason] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const gramsRef = useRef<HTMLInputElement>(null);
  // Segnati di recente: si riaggiungono in un tocco, anche senza la
  // confezione da scansionare.
  const [recent, setRecent] = useState<RecentFood[] | null>(null);
  const [allRecent, setAllRecent] = useState(false);
  const [quickAdding, setQuickAdding] = useState<number | null>(null);
  // I miei prodotti: gli scansionati restano sempre, non scorrono via.
  const [saved, setSaved] = useState<SavedFood[] | null>(null);
  const [list, setList] = useState<"recent" | "saved">("recent");
  // Ricerca fra i miei prodotti, dentro il loro elenco.
  const [filtroMiei, setFiltroMiei] = useState("");
  // Previsto: nei giorni futuri sempre (lo decide il server), oggi a scelta.
  const [plannedToday, setPlannedToday] = useState(false);
  const planned = date > today || (date === today && plannedToday);

  const loadSaved = useCallback(
    () =>
      api
        .get<SavedFood[]>(`/nutrition/diary/saved?profile_id=${profileId}`)
        .then(setSaved)
        .catch(() => setSaved([])),
    [profileId]
  );

  useEffect(() => {
    inputRef.current?.focus();
    api
      .get<RecentFood[]>(`/nutrition/diary/recent?profile_id=${profileId}&limit=20`)
      .then(setRecent)
      .catch(() => setRecent([]));
    loadSaved();
  }, [profileId, loadSaved]);

  // Stella: aggiunge o toglie da "I miei prodotti", senza chiudere niente.
  async function toggleSaved(food: FoodResult, isSaved: boolean, grams?: number | null) {
    const id = food.ingredient_id;
    setRecent((prev) => prev?.map((r) => (r.ingredient_id === id ? { ...r, saved: !isSaved } : r)) ?? null);
    try {
      if (isSaved) {
        await api.del(`/nutrition/diary/saved/${id}?profile_id=${profileId}`);
      } else {
        await api.put(`/nutrition/diary/saved/${id}?profile_id=${profileId}${grams ? `&grams=${grams}` : ""}`);
      }
      await loadSaved();
    } catch (e) {
      setRecent((prev) => prev?.map((r) => (r.ingredient_id === id ? { ...r, saved: isSaved } : r)) ?? null);
      setError(e instanceof Error ? e.message : "Non sono riuscito a salvarlo");
    }
  }

  async function quickAdd(r: { ingredient_id: number; grams: number | null }) {
    if (!r.grams) return;
    setQuickAdding(r.ingredient_id);
    setError(null);
    try {
      await api.post(`/nutrition/diary/items?profile_id=${profileId}`, {
        ingredient_id: r.ingredient_id,
        grams: r.grams,
        meal_type: meal,
        date,
        planned,
      });
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito ad aggiungere l'alimento");
      setQuickAdding(null);
    }
  }

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

  function savedRow(r: SavedFood) {
    return (
      <QuickRow
        key={r.ingredient_id}
        name={r.name_it ?? r.name}
        detail={[
          r.grams ? `${Math.round(r.grams)} g · ${Math.round((r.kcal_100g * r.grams) / 100)} kcal` : `${Math.round(r.kcal_100g)} kcal/100 g`,
          r.uses ? `usato ${r.uses} ${r.uses === 1 ? "volta" : "volte"}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        saved
        onStar={() => toggleSaved(r, true)}
        onPick={() => {
          setSelected(r);
          setGrams(r.grams ?? r.portion_g ?? 100);
          setTimeout(() => gramsRef.current?.focus(), 60);
        }}
        onAdd={r.grams ? () => quickAdd(r) : undefined}
        adding={quickAdding === r.ingredient_id}
        disabled={quickAdding !== null}
        addLabel={`Aggiungi ${Math.round(r.grams ?? 0)} g di ${r.name_it ?? r.name} a ${MEAL_LABELS[meal]}`}
      />
    );
  }

  // Scrivendo nella barra principale, i miei prodotti che corrispondono
  // compaiono subito in cima; i risultati del database arrivano sotto.
  const mieiTrovati = query.trim().length >= 2 && saved ? searchSavedFoods(saved, query).slice(0, 5) : [];
  const giaMostrati = new Set(mieiTrovati.map((r) => r.ingredient_id));

  async function add() {
    if (!selected || !grams) return;
    setSaving(true);
    setError(null);
    try {
      await api.post(`/nutrition/diary/items?profile_id=${profileId}`, {
        ingredient_id: selected.ingredient_id,
        grams,
        meal_type: meal,
        date,
        planned,
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
      <div className="shrink-0 space-y-3 border-b border-white/[0.06] px-4 py-4 sm:px-5">
        <div className="flex items-center gap-2.5">
          <div className="relative min-w-0 flex-1">
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
          <button
            onClick={() => {
              setSelected(null);
              setMode(mode === "photo" ? "search" : "photo");
            }}
            aria-pressed={mode === "photo"}
            title="Fotografa l'etichetta nutrizionale o il piatto"
            className={`flex h-10 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-[12.5px] font-semibold transition ${
              mode === "photo"
                ? "border-iris-400/60 bg-iris-400 text-ink-900"
                : "border-iris-400/40 bg-iris-400/[0.12] text-iris-200 hover:bg-iris-400/[0.2]"
            }`}
          >
            <PhotoIcon />
            <span className="hidden sm:inline">Foto</span>
          </button>
          <CloseButton onClose={onClose} />
        </div>
        <OptionGroup
          ariaLabel="Pasto"
          size="sm"
          value={meal}
          onChange={setMeal}
          options={MEAL_ORDER.map((m) => ({ value: m, label: MEAL_LABELS[m] }))}
        />
        <PlannedToggle date={date} today={today} value={plannedToday} onChange={setPlannedToday} />
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

        {mode === "photo" && (
          <FoodPhotoPanel
            profileId={profileId}
            mealType={meal}
            date={date}
            planned={planned}
            onAdded={onAdded}
          />
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

        {mode === "search" &&
          query.trim().length < 2 &&
          !selected &&
          ((recent && recent.length > 0) || (saved && saved.length > 0)) && (
            <div className="p-2 pb-3">
              <div className="mb-2 inline-flex rounded-xl border border-white/10 bg-white/[0.03] p-1">
                {(
                  [
                    ["recent", "Recenti"],
                    ["saved", `I miei prodotti${saved && saved.length ? ` · ${saved.length}` : ""}`],
                  ] as const
                ).map(([id, text]) => (
                  <button
                    key={id}
                    onClick={() => setList(id)}
                    aria-pressed={list === id}
                    className={`rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition ${
                      list === id ? "bg-gradient-to-b from-lime-400 to-lime-500 text-ink-900" : "text-white/55 hover:text-white"
                    }`}
                  >
                    {text}
                  </button>
                ))}
              </div>

              {list === "recent" ? (
                recent && recent.length > 0 ? (
                  <>
                    <div className="space-y-1">
                      {(allRecent ? recent : recent.slice(0, 6)).map((r) => (
                        <QuickRow
                          key={r.ingredient_id}
                          name={r.name_it ?? r.name}
                          detail={`${Math.round(r.grams)} g · ${Math.round(r.kcal)} kcal · ${quando(r.last_date)}${
                            MEAL_LABELS[r.meal_type] ? ` a ${MEAL_LABELS[r.meal_type].toLowerCase()}` : ""
                          }`}
                          saved={r.saved}
                          onStar={() => toggleSaved(r, r.saved, r.grams)}
                          onPick={() => {
                            setSelected(r);
                            setGrams(r.grams);
                            setTimeout(() => gramsRef.current?.focus(), 60);
                          }}
                          onAdd={() => quickAdd(r)}
                          adding={quickAdding === r.ingredient_id}
                          disabled={quickAdding !== null}
                          addLabel={`Aggiungi di nuovo ${Math.round(r.grams)} g di ${r.name_it ?? r.name} a ${MEAL_LABELS[meal]}`}
                        />
                      ))}
                    </div>
                    {recent.length > 6 && (
                      <button
                        onClick={() => setAllRecent(!allRecent)}
                        className="mt-1.5 w-full rounded-xl py-2 text-[12.5px] font-medium text-white/45 transition hover:text-white/80"
                      >
                        {allRecent ? "Mostra meno" : `Mostra tutti (${recent.length})`}
                      </button>
                    )}
                  </>
                ) : (
                  <p className="px-1.5 py-2 text-[12.5px] text-white/40">Ancora niente di segnato.</p>
                )
              ) : saved && saved.length > 0 ? (
                <>
                  <p className="mb-2 px-1 text-[11.5px] leading-snug text-white/40">
                    Ogni prodotto scansionato resta qui, dal più usato. Con la stella lo togli, o salvi anche un
                    alimento dai recenti.
                  </p>
                  <div className="relative mb-2">
                    <svg
                      viewBox="0 0 24 24"
                      className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 fill-white/30"
                    >
                      <path d="M10 2a8 8 0 1 0 4.9 14.3l5.4 5.4 1.4-1.4-5.4-5.4A8 8 0 0 0 10 2Zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12Z" />
                    </svg>
                    <input
                      className="input h-10 py-0 pl-9 pr-9 text-[13px]"
                      placeholder="Cerca fra i tuoi prodotti"
                      aria-label="Cerca fra i tuoi prodotti"
                      value={filtroMiei}
                      onChange={(e) => setFiltroMiei(e.target.value)}
                    />
                    {filtroMiei && (
                      <button
                        onClick={() => setFiltroMiei("")}
                        aria-label="Cancella la ricerca"
                        className="absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-lg text-white/40 hover:text-white"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  {(() => {
                    const trovati = searchSavedFoods(saved, filtroMiei);
                    return trovati.length ? (
                      <div className="space-y-1">{trovati.map(savedRow)}</div>
                    ) : (
                      <p className="px-1.5 py-2 text-[12.5px] text-white/40">
                        Nessuno dei tuoi prodotti si chiama così. Prova la barra in alto, cerca in tutto il database.
                      </p>
                    );
                  })()}
                </>
              ) : (
                <p className="px-1.5 py-2 text-[12.5px] leading-snug text-white/40">
                  Qui restano per sempre i prodotti che scansioni, anche quando escono dai recenti.
                </p>
              )}
            </div>
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

        {mode === "search" && query.trim().length < 2 && !selected && (
          <button
            onClick={() => setMode("photo")}
            className="mx-2 mb-2 flex w-[calc(100%-1rem)] items-center gap-3 rounded-2xl border border-iris-400/20 bg-iris-400/[0.05] px-4 py-3 text-left transition hover:border-iris-400/45 hover:bg-iris-400/[0.1]"
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-iris-400/20 text-iris-100">
              <PhotoIcon />
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold text-white">
                Niente codice a barre? Usa la fotocamera
              </span>
              <span className="mt-0.5 block text-[11.5px] leading-snug text-white/45">
                Leggo la tabella nutrizionale da una foto, oppure provo a riconoscere il piatto: i
                valori restano da controllare.
              </span>
            </span>
          </button>
        )}

        {mode === "search" && !selected && mieiTrovati.length > 0 && (
          <div className="p-2 pb-1">
            <p className="mb-1.5 flex items-center gap-1.5 px-1 text-[11.5px] font-semibold uppercase tracking-wide text-lime-200/70">
              <svg viewBox="0 0 24 24" className="h-3 w-3 fill-current" aria-hidden>
                <path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z" />
              </svg>
              Tra i tuoi prodotti
            </p>
            <div className="space-y-1">{mieiTrovati.map(savedRow)}</div>
          </div>
        )}

        {mode === "search" && searching && <Spinner label="Cerco su USDA e Open Food Facts…" />}

        {error && (
          <div className="p-2">
            <Notice>{error}</Notice>
          </div>
        )}

        {mode === "search" && !searching && !error && query.trim().length >= 2 && results.length === 0 && mieiTrovati.length === 0 && (
          <Empty title="Nessun risultato" hint="Prova con un nome più semplice, es. «riso» o «yogurt greco», oppure scansiona il codice a barre." />
        )}

        {mode === "search" &&
          !searching &&
          // Quelli già in cima fra i miei prodotti non si ripetono.
          results.filter((r) => !giaMostrati.has(r.ingredient_id)).map((r) => {
            const isSelected = selected?.ingredient_id === r.ingredient_id;
            const nome = nameOf(r);
            return (
              <button
                key={r.ingredient_id}
                onClick={() => {
                  setSelected(r);
                  // La porzione tipica (CREA), quando c'è, è il punto di partenza.
                  if (r.portion_g) setGrams(r.portion_g);
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
            className="shrink-0 space-y-3 border-t border-white/[0.06] bg-ink-900/50 px-4 py-3 sm:px-5"
          >
            <div className="flex items-center gap-2">
              <p className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-white">{nameOf(selected)}</p>
              {selected.portion_g ? (
                <button
                  onClick={() => setGrams(selected.portion_g ?? null)}
                  className={`shrink-0 rounded-full border px-2.5 py-1 text-[11.5px] font-medium transition ${
                    grams === selected.portion_g
                      ? "border-lime-400/50 bg-lime-400/15 text-lime-200"
                      : "border-white/15 text-white/60 hover:text-white"
                  }`}
                  title="Porzione tipica secondo le tabelle CREA"
                >
                  porzione tipica {selected.portion_g} g
                </button>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
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
                className="w-36"
              />
              <div className="min-w-[180px] flex-1">
                <OptionGroup
                  ariaLabel="Grammi rapidi"
                  size="sm"
                  mono
                  value={grams}
                  onChange={setGrams}
                  options={[50, 100, 150, 200].map((g) => ({ value: g, label: g }))}
                />
              </div>
            </div>

            <MacroGrid
              items={[
                ["kcal", Math.round(selected.kcal_100g * factor)],
                ["proteine", `${(selected.protein_100g * factor).toFixed(1)}g`],
                ["carboid.", `${(selected.carbs_100g * factor).toFixed(1)}g`],
                ["grassi", `${(selected.fat_100g * factor).toFixed(1)}g`],
              ]}
            />

            <button className="btn-primary w-full justify-center" disabled={saving || !grams} onClick={add}>
              {saving ? "Aggiungo…" : planned ? `Prevedi per ${MEAL_LABELS[meal]}` : `Aggiungi a ${MEAL_LABELS[meal]}`}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </Modal>
  );
}

/** Testo confrontabile: minuscolo e senza accenti ("Caffè" trova "caffe"). */
function normalizza(t: string): string {
  return t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/**
 * I miei prodotti che corrispondono a quello che si scrive: ogni parola deve
 * comparire nel nome (italiano o originale) o nella fonte, in qualsiasi
 * ordine. L'elenco è già tutto sul telefono: il risultato è immediato.
 */
export function searchSavedFoods<T extends { name: string; name_it: string | null; source_label: string }>(
  lista: T[],
  testo: string
): T[] {
  const parole = normalizza(testo).split(/\s+/).filter((p) => p.length > 0);
  if (!parole.length) return lista;
  return lista.filter((r) => {
    const dove = normalizza(`${r.name_it ?? ""} ${r.name} ${r.source_label}`);
    return parole.every((p) => dove.includes(p));
  });
}

/** Una riga di "Recenti" o "I miei prodotti": stella, nome, + per aggiungere al volo. */
function QuickRow({
  name,
  detail,
  saved,
  onStar,
  onPick,
  onAdd,
  adding,
  disabled,
  addLabel,
}: {
  name: string;
  detail: string;
  saved: boolean;
  onStar: () => void;
  onPick: () => void;
  onAdd?: () => void;
  adding: boolean;
  disabled: boolean;
  addLabel: string;
}) {
  return (
    <div className="flex items-center gap-1 rounded-xl border border-white/[0.06] bg-white/[0.025] py-1.5 pl-1 pr-1.5">
      <button
        onClick={onStar}
        aria-pressed={saved}
        aria-label={saved ? `Togli ${name} da I miei prodotti` : `Salva ${name} fra I miei prodotti`}
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg transition ${
          saved ? "text-lime-300" : "text-white/25 hover:text-white/60"
        }`}
      >
        <svg viewBox="0 0 24 24" className="h-[17px] w-[17px]" aria-hidden>
          <path
            d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z"
            fill={saved ? "currentColor" : "none"}
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <button onClick={onPick} className="min-w-0 flex-1 py-1 text-left" title="Scegli i grammi prima di aggiungerlo">
        <p className="truncate text-[13px] text-white/85">{name}</p>
        <p className="truncate text-[11.5px] text-white/40">{detail}</p>
      </button>
      {onAdd && (
        <button
          onClick={onAdd}
          disabled={disabled}
          aria-label={addLabel}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-lime-400/40 bg-lime-400/[0.12] text-lime-200 transition hover:bg-lime-400/25 disabled:opacity-50"
        >
          {adding ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.6}>
              <path d="M12 5v14M5 12h14" strokeLinecap="round" />
            </svg>
          )}
        </button>
      )}
    </div>
  );
}
