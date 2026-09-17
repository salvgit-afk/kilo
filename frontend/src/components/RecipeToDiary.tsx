"use client";

/**
 * Aggiunge una ricetta salvata a un pasto del diario, in un colpo solo.
 *
 * Senza questo, segnare un piatto cucinato significa cercare a mano ogni
 * ingrediente e ricordarsi i grammi: sei ricerche per un porridge. Qui la
 * ricetta li porta già con sé, e restano voci separate nel diario — così una
 * si può correggere o togliere senza rifare tutto.
 *
 * Si sceglie **quanto** se ne è mangiato in porzioni: le quantità della
 * ricetta valgono per il totale e vengono scalate di conseguenza.
 *
 * Gli ingredienti senza corrispondenza nel catalogo non vengono aggiunti, e
 * la finestra lo dice prima di confermare: un ingrediente senza valori
 * falserebbe il conteggio della giornata in silenzio.
 */

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { MEAL_LABELS, api, type SavedRecipe } from "@/lib/api";
import { Modal, ModalHeader } from "@/components/controls";
import { Empty, Notice, Spinner } from "@/components/ui";

const PORZIONI = [0.5, 1, 1.5, 2];

export function RecipeToDiaryDialog({
  profileId,
  mealType,
  mealOrder,
  date,
  onClose,
  onAdded,
}: {
  profileId: number;
  mealType: string;
  mealOrder: string[];
  /** Il giorno mostrato nel diario: non sempre è oggi. */
  date?: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [recipes, setRecipes] = useState<SavedRecipe[] | null>(null);
  const [meal, setMeal] = useState(mealType);
  const [selected, setSelected] = useState<SavedRecipe | null>(null);
  const [eaten, setEaten] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<SavedRecipe[]>(`/nutrition/recipes/saved?profile_id=${profileId}`)
      .then(setRecipes)
      .catch(() => setRecipes([]));
  }, [profileId]);

  const items = selected?.recipe.items ?? [];
  const collegati = items.filter((i) => i.ingredient_id !== null && i.grams);
  const mancanti = items.length - collegati.length;
  const porzioni = Math.max(1, selected?.recipe.servings ?? 1);
  const fattore = eaten / porzioni;

  async function add() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await api.post(`/nutrition/diary/recipe?profile_id=${profileId}`, {
        items,
        meal_type: meal,
        date: date ?? null,
        servings: porzioni,
        eaten_servings: eaten,
      });
      onAdded();
    } catch (e) {
      setError(
        e instanceof Error
          ? `Non sono riuscito ad aggiungere la ricetta: ${e.message}`
          : "Non sono riuscito ad aggiungere la ricetta."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose} align="top">
      <ModalHeader
        eyebrow="Diario"
        title="Aggiungi una ricetta"
        subtitle="Gli ingredienti entrano nel pasto come voci separate: puoi correggerne una senza rifare tutto."
        onClose={onClose}
      >
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {mealOrder.map((m) => (
            <button
              key={m}
              onClick={() => setMeal(m)}
              className={`rounded-lg border px-2.5 py-1 text-[11.5px] font-medium transition ${
                meal === m
                  ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
                  : "border-white/[0.08] text-white/45 hover:text-white/80"
              }`}
            >
              {MEAL_LABELS[m]}
            </button>
          ))}
        </div>
      </ModalHeader>

      <div className="min-h-[140px] flex-1 overflow-y-auto overscroll-contain p-2">
        {!recipes && <Spinner label="Carico le tue ricette…" />}

        {recipes && recipes.length === 0 && (
          <Empty
            title="Nessuna ricetta salvata"
            hint="Salva una ricetta dalla sezione Ricette, o incollane una tua con «Importa»: da lì la ritrovi qui e la aggiungi al diario in un tocco."
          />
        )}

        {recipes?.map((s) => {
          const r = s.recipe;
          const attiva = selected?.id === s.id;
          const usabile = r.items.some((i) => i.ingredient_id !== null && i.grams);
          return (
            <button
              key={s.id}
              onClick={() => usabile && setSelected(attiva ? null : s)}
              disabled={!usabile}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                attiva ? "bg-lime-400/[0.1] ring-1 ring-lime-400/35" : "hover:bg-white/[0.04]"
              } ${usabile ? "" : "opacity-40"}`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] text-white/85">{r.name}</p>
                <p className="truncate text-[11px] text-white/35">
                  {usabile
                    ? `${r.servings} porzioni · ${Math.round(r.kcal_per_serving)} kcal e ${Math.round(
                        r.protein_per_serving
                      )} g di proteine a porzione`
                    : "ingredienti non collegati al catalogo: non si può aggiungere"}
                </p>
              </div>
              {r.source === "import" && (
                <span className="shrink-0 rounded-md border border-iris-400/25 bg-iris-400/[0.08] px-1.5 py-0.5 text-[9.5px] uppercase tracking-wide text-iris-200/80">
                  tua
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selected && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="shrink-0 border-t border-white/[0.06] bg-black/25 p-4"
        >
          <p className="label">Quanto ne hai mangiato</p>
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            {PORZIONI.map((p) => (
              <button
                key={p}
                onClick={() => setEaten(p)}
                className={`rounded-lg border px-3 py-1.5 text-[12.5px] font-medium tabular-nums transition ${
                  eaten === p
                    ? "border-lime-400/50 bg-lime-400/15 text-lime-200"
                    : "border-white/[0.08] text-white/50 hover:text-white/85"
                }`}
              >
                {p === 1 ? "1 porzione" : `${p.toString().replace(".", ",")} porzioni`}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-white/30">
              la ricetta è per {porzioni} porzioni
            </span>
          </div>

          <div className="mb-3 grid grid-cols-4 gap-2 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
            {[
              ["kcal", Math.round(selected.recipe.kcal_per_serving * eaten)],
              ["proteine", `${(selected.recipe.protein_per_serving * eaten).toFixed(1)}g`],
              ["carboid.", `${(selected.recipe.carbs_per_serving * eaten).toFixed(1)}g`],
              ["grassi", `${(selected.recipe.fat_per_serving * eaten).toFixed(1)}g`],
            ].map(([label, value]) => (
              <div key={label} className="text-center">
                <p className="font-mono text-[14px] tabular-nums text-white">{value}</p>
                <p className="text-[10px] uppercase tracking-wide text-white/30">{label}</p>
              </div>
            ))}
          </div>

          <p className="mb-3 text-[11.5px] leading-snug text-white/35">
            Entrano {collegati.length} ingredienti, con le quantità della ricetta
            {fattore !== 1 && <> ridotte al {Math.round(fattore * 100)}%</>}.
            {mancanti > 0 && (
              <span className="text-amber-200/70">
                {" "}
                {mancanti} {mancanti === 1 ? "ingrediente non è collegato" : "ingredienti non sono collegati"}{" "}
                al catalogo e {mancanti === 1 ? "resta fuori" : "restano fuori"} dal conteggio.
              </span>
            )}
          </p>

          {error && (
            <div className="mb-3">
              <Notice>{error}</Notice>
            </div>
          )}

          <button className="btn-primary w-full" onClick={add} disabled={saving}>
            {saving ? "Aggiungo…" : `Aggiungi a ${MEAL_LABELS[meal]}`}
          </button>
        </motion.div>
      )}
    </Modal>
  );
}
