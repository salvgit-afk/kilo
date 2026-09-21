"use client";

/**
 * Importazione di una ricetta incollata come testo.
 *
 * Nasce da un problema pratico: inserire una ricetta ingrediente per
 * ingrediente è lento, mentre le ricette che si vogliono davvero usare sono
 * già scritte da qualche parte — un blog di cucina fit, un quaderno, un
 * messaggio. Qui si incolla il testo e diventa una ricetta di Kilo.
 *
 * La bozza che torna dal backend **non è un risultato definitivo**: i grammi
 * si correggono qui prima di salvare, e i macro si ricalcolano mentre si
 * scrive. È la differenza fra una stima e un conteggio: l'ultima parola sui
 * grammi resta a chi ha cucinato.
 *
 * I grammi che non erano scritti nel testo sono marcati **stimato** finché
 * non li si tocca: una stima confermata o corretta diventa un dato di chi
 * ha cucinato, una stima non guardata resta dichiarata come tale.
 *
 * Gli ingredienti che il catalogo non conosce restano visibili e dichiarati,
 * ma non entrano nei totali: meglio un totale dichiarato incompleto che un
 * numero inventato.
 */

import { motion } from "framer-motion";
import { useState } from "react";
import { ApiError, api, type ImportedRecipe, type RecipeItem, type RecipeSuggestion } from "@/lib/api";
import { Card, Notice } from "@/components/ui";
import { Mascot } from "@/components/Mascot";
import { Field, MacroGrid, NumberField, Stepper } from "@/components/controls";

const ESEMPIO = `Porridge proteico — per 2 persone
80 g di fiocchi d'avena
300 g di albume
1 cucchiaio di burro d'arachidi
20 g di mirtilli

Scalda l'avena con l'albume, aggiungi il burro d'arachidi e i mirtilli.`;

export type Totali = { kcal: number; protein: number; carbs: number; fat: number; fiber: number };

/** Somma i macro degli ingredienti collegati al catalogo, per la ricetta intera. */
export function totali(items: RecipeItem[]): Totali {
  const somma = { kcal: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 };
  for (const i of items) {
    if (i.ingredient_id === null || !i.grams) continue;
    const f = i.grams / 100;
    somma.kcal += (i.kcal_100g ?? 0) * f;
    somma.protein += (i.protein_100g ?? 0) * f;
    somma.carbs += (i.carbs_100g ?? 0) * f;
    somma.fat += (i.fat_100g ?? 0) * f;
    somma.fiber += (i.fiber_100g ?? 0) * f;
  }
  return somma;
}

export function RecipeImport({
  profileId,
  onSaved,
}: {
  profileId: number;
  onSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [draft, setDraft] = useState<ImportedRecipe | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function read() {
    setLoading(true);
    setError(null);
    try {
      const bozza = await api.post<ImportedRecipe>(
        `/nutrition/recipes/import?profile_id=${profileId}`,
        { text: text.trim() }
      );
      setDraft(bozza);
    } catch (e) {
      setDraft(null);
      setError(
        e instanceof ApiError
          ? e.message
          : "Non sono riuscito a leggere la ricetta. Riprova tra poco."
      );
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    const t = totali(draft.items);
    const porzioni = Math.max(1, draft.servings);
    const collegati = draft.items.filter((i) => i.ingredient_id !== null && i.grams).length;
    const payload: RecipeSuggestion = {
      // Id costruito qui: una ricetta importata non ha una fonte esterna.
      meal_id: `import:${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
      source: "import",
      saved: true,
      name: draft.name.trim().slice(0, 300) || "Ricetta importata",
      original_name: null,
      category: "Importata",
      area: null,
      thumbnail_url: null,
      youtube_url: null,
      instructions: draft.instructions,
      kcal_per_serving: Math.round(t.kcal / porzioni),
      protein_per_serving: Math.round((t.protein / porzioni) * 10) / 10,
      carbs_per_serving: Math.round((t.carbs / porzioni) * 10) / 10,
      fat_per_serving: Math.round((t.fat / porzioni) * 10) / 10,
      fiber_per_serving: Math.round((t.fiber / porzioni) * 10) / 10,
      servings: porzioni,
      coverage: draft.items.length ? collegati / draft.items.length : 0,
      fit_score: 0,
      reasons: [],
      ingredients: draft.items.map((i) =>
        i.grams ? `${Math.round(i.grams)} g di ${i.name}` : i.name
      ),
      items: draft.items,
    };
    try {
      await api.post(`/nutrition/recipes/saved?profile_id=${profileId}`, payload);
      setDraft(null);
      setText("");
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? `Non sono riuscito a salvare: ${e.message}` : "Non sono riuscito a salvare.");
    } finally {
      setSaving(false);
    }
  }

  function aggiorna(indice: number, cambio: Partial<RecipeItem>) {
    setDraft((prev) =>
      prev ? { ...prev, items: prev.items.map((i, k) => (k === indice ? { ...i, ...cambio } : i)) } : prev
    );
  }

  const t = draft ? totali(draft.items) : null;
  const porzioni = Math.max(1, draft?.servings ?? 1);

  return (
    <>
      {!draft && (
        <Card className="mb-4">
          <div className="p-4">
            <p className="label">Incolla la ricetta</p>
            <p className="mb-2.5 text-[12.5px] leading-relaxed text-white/45">
              Titolo, quantità e preparazione, così come sono scritti. Vanno bene gli appunti, un
              messaggio, la lista ingredienti di un sito che ti piace. Le quantità già in grammi
              restano esatte; quelle in cucchiai le converto io, e se mancano le stimo sulle
              porzioni standard italiane. Le stime sono segnate: le controlli prima di salvare.
            </p>
            <textarea
              className="input min-h-[190px] resize-y font-mono text-[12.5px] leading-relaxed"
              placeholder={ESEMPIO}
              value={text}
              maxLength={8000}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button className="btn-primary" onClick={read} disabled={loading || text.trim().length < 10}>
                {loading ? "Leggo…" : "Leggi la ricetta"}
              </button>
              {!text && (
                <button className="btn-ghost text-[12.5px]" onClick={() => setText(ESEMPIO)}>
                  Prova con un esempio
                </button>
              )}
              <span className="ml-auto text-[11px] tabular-nums text-white/25">
                {text.length}/8000
              </span>
            </div>
          </div>
        </Card>
      )}

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
              <p className="text-[14px] font-medium text-white">Leggo la ricetta…</p>
              <p className="text-[12.5px] leading-snug text-white/45">
                Riconosco gli ingredienti e li cerco nel catalogo alimenti. I valori nutrizionali
                li prendo da lì, non li invento.
              </p>
            </div>
          </div>
        </Card>
      )}

      {draft && t && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="mb-4">
            <div className="grid grid-cols-1 gap-3 border-b border-white/[0.06] p-4 sm:grid-cols-[1fr_220px]">
              <Field title="Nome della ricetta">
                <input
                  className="input"
                  value={draft.name}
                  maxLength={300}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
              </Field>
              <Field title="Porzioni">
                <Stepper
                  compact
                  value={draft.servings}
                  onChange={(n) => setDraft({ ...draft, servings: n })}
                  min={1}
                  max={20}
                  label="porzioni"
                />
              </Field>
              <div className="sm:col-span-2">
                <MacroGrid
                  items={[
                    ["kcal", Math.round(t.kcal / porzioni)],
                    ["prot.", `${Math.round((t.protein / porzioni) * 10) / 10}g`],
                    ["carb.", `${Math.round((t.carbs / porzioni) * 10) / 10}g`],
                    ["grassi", `${Math.round((t.fat / porzioni) * 10) / 10}g`],
                  ]}
                  note="per porzione · si aggiorna mentre correggi i grammi"
                />
              </div>
            </div>

            <div className="divide-y divide-white/[0.05] p-2">
              {draft.items.map((item, k) => {
                const mancante = item.ingredient_id === null;
                return (
                  <div key={k} className="flex items-center gap-3 px-2 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className={`truncate text-[13.5px] ${mancante ? "text-amber-200/80" : "text-white/85"}`}>
                        {item.name}
                        {item.measure && (
                          <span className="ml-1.5 text-[11.5px] text-white/30">({item.measure})</span>
                        )}
                      </p>
                      <p className="truncate text-[11px] text-white/35">
                        {item.estimated && !mancante && (
                          <span className="mr-1.5 rounded bg-amber-300/15 px-1 py-px text-[9.5px] font-semibold uppercase tracking-wide text-amber-100">
                            stimato
                          </span>
                        )}
                        {mancante ? (
                          "non trovato nel catalogo: non entra nei totali"
                        ) : (
                          <>
                            {item.matched_name}
                            {item.source_label && <span className="text-white/25"> · {item.source_label}</span>}
                          </>
                        )}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <NumberField
                        value={item.grams}
                        onChange={(v) =>
                          // Toccato il valore, è un dato di chi ha cucinato.
                          aggiorna(k, { grams: v, estimated: false })
                        }
                        min={0}
                        max={5000}
                        step={5}
                        size="sm"
                        steppers="sm"
                        suffix="g"
                        placeholder="—"
                        ariaLabel={`Grammi di ${item.name}${item.estimated ? " (stimati)" : ""}`}
                        className={`w-24 sm:w-36 ${mancante ? "pointer-events-none opacity-40" : ""}`}
                      />
                    </div>
                    <button
                      onClick={() =>
                        setDraft({ ...draft, items: draft.items.filter((_, i) => i !== k) })
                      }
                      aria-label={`Togli ${item.name}`}
                      title="Togli dalla ricetta"
                      className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white/35 transition hover:bg-rose-400/10 hover:text-rose-300"
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4" stroke="currentColor" strokeWidth={2} fill="none">
                        <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>

            {draft.warnings.map((w, k) => (
              <p key={k} className="border-t border-white/[0.06] px-4 py-3 text-[12px] leading-relaxed text-amber-200/70">
                {w}
              </p>
            ))}

            <div className="flex items-center gap-2 border-t border-white/[0.06] bg-ink-900/50 px-4 py-3 sm:px-5">
              <button className="btn-ghost flex-1 justify-center" onClick={() => setDraft(null)} disabled={saving}>
                Ricomincia
              </button>
              <button
                className="btn-primary flex-[1.6] justify-center"
                onClick={save}
                disabled={saving || draft.items.length === 0}
              >
                {saving ? "Salvo…" : "Salva ricetta"}
              </button>
            </div>
          </Card>
        </motion.div>
      )}
    </>
  );
}
