"use client";

/**
 * I pasti della giornata come tappe di una linea.
 *
 * Chiusi, dicono l'essenziale: quale pasto, quante kcal e il riassunto dei
 * macro. Toccando l'icona (o il nome) il pasto si apre e mostra gli alimenti
 * uno per uno. Un alimento toccato si seleziona in modo evidente e offre le
 * due cose che si fanno davvero su una voce del diario: correggere i grammi o
 * eliminarla.
 *
 * Il + di ogni pasto apre la stessa aggiunta di sempre: ricerca, codice a
 * barre, inserimento manuale e foto.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { MEAL_LABELS, api, type Meal, type MealItem } from "@/lib/api";
import { NumberField } from "@/components/controls";

export const MEAL_ORDER = ["breakfast", "snack", "lunch", "dinner"];

/** Colore e icona di ogni pasto: gli stessi nella linea e nel riepilogo. */
export const MEAL_THEME: Record<
  string,
  { icon: string; text: string; bg: string; border: string; bar: string }
> = {
  breakfast: {
    icon: "M12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10Zm0-5 1 3h-2l1-3Zm0 20-1-3h2l-1 3ZM2 12l3-1v2l-3-1Zm20 0-3 1v-2l3 1ZM4.9 4.9l2.8 1.4-1.4 1.4-1.4-2.8Zm14.2 14.2-2.8-1.4 1.4-1.4 1.4 2.8Zm0-14.2-1.4 2.8-1.4-1.4 2.8-1.4ZM4.9 19.1l1.4-2.8 1.4 1.4-2.8 1.4Z",
    text: "text-amber-200",
    bg: "bg-amber-300/15",
    border: "border-amber-300/35",
    bar: "bg-amber-300",
  },
  snack: {
    icon: "M13 3c1.5 0 3 .8 3 2.5-1 .1-2.2-.3-3-1V3Zm-1 3c3.2-1.3 7 .5 7 5.5 0 4.6-3.2 9.5-5.5 9.5-.8 0-1-.4-1.5-.4s-.7.4-1.5.4C8.2 21 5 16.1 5 11.5 5 6.5 8.8 4.7 12 6Z",
    text: "text-rose-200",
    bg: "bg-rose-400/15",
    border: "border-rose-400/35",
    bar: "bg-rose-400",
  },
  lunch: {
    icon: "M3 11h18a9 9 0 0 1-18 0Zm2-3h14l-1 2H6L5 8Zm4-5h2v4H9V3Zm4 0h2v4h-2V3Z",
    text: "text-lime-200",
    bg: "bg-lime-400/15",
    border: "border-lime-400/35",
    bar: "bg-lime-400",
  },
  dinner: {
    icon: "M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z",
    text: "text-iris-100",
    bg: "bg-iris-400/15",
    border: "border-iris-400/35",
    bar: "bg-iris-400",
  },
};

/** I tre macro con il loro colore, uguali in tutta la sezione. */
export const MACROS = [
  { key: "protein_g", label: "Proteine", dot: "bg-lime-400" },
  { key: "carbs_g", label: "Carbo", dot: "bg-iris-400" },
  { key: "fat_g", label: "Grassi", dot: "bg-amber-300" },
] as const;

function Icon({ d, className = "h-4 w-4" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} shrink-0 fill-current`} aria-hidden>
      <path d={d} />
    </svg>
  );
}

const PLUS = "M11 11V5h2v6h6v2h-6v6h-2v-6H5v-2h6Z";
const TRASH = "M7 6V4h10v2h4v2h-2v12H5V8H3V6h4Zm2 4v8h2v-8H9Zm4 0v8h2v-8h-2Z";
const BOOK = "M4 3h13a3 3 0 0 1 3 3v15H7a3 3 0 0 1-3-3V3Zm2 2v13a1 1 0 0 0 1 1h11V6a1 1 0 0 0-1-1H6Zm3 3h7v2H9V8Zm0 4h7v2H9v-2Z";
const CHEVRON = "M7 10l5 5 5-5H7Z";

export function MealTimeline({
  meals,
  onAdd,
  onAddRecipe,
  onChanged,
}: {
  meals: Meal[];
  onAdd: (mealType: string) => void;
  onAddRecipe: (mealType: string) => void;
  onChanged: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const byType = Object.fromEntries(meals.map((m) => [m.meal_type, m]));

  function toggle(type: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  return (
    <div className="glass p-3.5 sm:p-4">
      <ol className="relative space-y-2 before:absolute before:bottom-6 before:left-[23px] before:top-6 before:w-px before:bg-white/10 sm:before:left-[25px]">
        {MEAL_ORDER.map((type) => (
          <MealStop
            key={type}
            type={type}
            meal={byType[type]}
            expanded={open.has(type)}
            onToggle={() => toggle(type)}
            onAdd={() => onAdd(type)}
            onAddRecipe={() => onAddRecipe(type)}
            onChanged={onChanged}
          />
        ))}
      </ol>
    </div>
  );
}

function MealStop({
  type,
  meal,
  expanded,
  onToggle,
  onAdd,
  onAddRecipe,
  onChanged,
}: {
  type: string;
  meal?: Meal;
  expanded: boolean;
  onToggle: () => void;
  onAdd: () => void;
  onAddRecipe: () => void;
  onChanged: () => void | Promise<void>;
}) {
  const t = MEAL_THEME[type];
  const items = meal?.items ?? [];
  const pieno = items.length > 0;

  return (
    <li className="relative">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={`${expanded ? "Chiudi" : "Apri"} ${MEAL_LABELS[type]}`}
          className={`relative z-10 grid h-12 w-12 shrink-0 place-items-center rounded-full border transition active:scale-95 ${t.border} ${t.bg} ${t.text}`}
        >
          <Icon d={t.icon} className="h-[22px] w-[22px]" />
        </button>

        <button onClick={onToggle} className="min-w-0 flex-1 py-1 text-left">
          <div className="flex items-baseline gap-2">
            <h3 className="text-[15px] font-semibold text-white">{MEAL_LABELS[type]}</h3>
            {pieno && (
              <span className={`font-mono text-[14px] font-semibold tabular-nums ${t.text}`}>
                {Math.round(meal!.kcal)} kcal
              </span>
            )}
            <Icon
              d={CHEVRON}
              className={`ml-auto h-4 w-4 text-white/35 transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}
            />
          </div>
          {pieno ? (
            <p className="mt-0.5 flex flex-wrap gap-x-2.5 text-[11.5px] text-white/45">
              {MACROS.map((m) => (
                <span key={m.key} className="inline-flex items-center gap-1">
                  <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
                  {m.label} <b className="font-semibold text-white/75">{Math.round(meal![m.key])} g</b>
                </span>
              ))}
            </p>
          ) : (
            <p className="mt-0.5 text-[12px] text-white/35">Ancora niente</p>
          )}
        </button>

        <button
          onClick={onAdd}
          aria-label={`Aggiungi a ${MEAL_LABELS[type]}`}
          title="Cerca, scansiona il codice a barre, inserisci a mano o fotografa"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.05] text-white/75 transition hover:border-lime-400/40 hover:text-lime-200 active:scale-95"
        >
          <Icon d={PLUS} />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="pb-2 pl-[60px] pt-2">
              {pieno ? (
                <MealItems items={items} onChanged={onChanged} />
              ) : (
                <button
                  onClick={onAdd}
                  className="w-full rounded-2xl border border-dashed border-white/12 py-3 text-[12.5px] text-white/45 transition hover:border-lime-400/35 hover:text-lime-200"
                >
                  + Aggiungi {type === "snack" ? "lo spuntino" : `la ${MEAL_LABELS[type].toLowerCase()}`}
                </button>
              )}
              <button
                onClick={onAddRecipe}
                className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] text-white/55 transition hover:border-iris-400/40 hover:text-iris-200"
              >
                <Icon d={BOOK} className="h-3.5 w-3.5" /> Da una ricetta salvata
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

function MealItems({ items, onChanged }: { items: MealItem[]; onChanged: () => void | Promise<void> }) {
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <div className="space-y-1.5">
      {items.map((item) => (
        <FoodRow
          key={item.id}
          item={item}
          selected={selected === item.id}
          onSelect={() => setSelected(selected === item.id ? null : item.id)}
          onDone={async () => {
            setSelected(null);
            await onChanged();
          }}
        />
      ))}
    </div>
  );
}

function FoodRow({
  item,
  selected,
  onSelect,
  onDone,
}: {
  item: MealItem;
  selected: boolean;
  onSelect: () => void;
  onDone: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [grams, setGrams] = useState<number | null>(Math.round(item.quantity_g));
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await api.del(`/nutrition/diary/items/${item.id}`);
      await onDone();
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!grams) return;
    setBusy(true);
    try {
      await api.patch(`/nutrition/diary/items/${item.id}?grams=${grams}`);
      setEditing(false);
      await onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`rounded-2xl border px-3 py-2.5 transition ${
        selected
          ? "border-lime-400/70 bg-white/[0.06] shadow-[0_0_0_1px_rgba(174,212,74,0.35)]"
          : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]"
      }`}
    >
      <button onClick={onSelect} aria-pressed={selected} className="block w-full text-left">
        <div className="flex items-baseline gap-2">
          <p className="min-w-0 flex-1 truncate text-[14px] text-white/90">{item.name}</p>
          <p className="font-mono text-[14px] font-semibold tabular-nums text-white">
            {Math.round(item.kcal)}
            <span className="ml-0.5 text-[11px] font-normal text-white/40">kcal</span>
          </p>
        </div>
        <p className="text-[11.5px] text-white/35">{Math.round(item.quantity_g)} g</p>
        {/* Tre colonne fisse: stanno sempre su una riga, anche con i nomi per
            esteso, e il numero si legge prima dell'etichetta. */}
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {MACROS.map((m) => (
            <div key={m.key} className="rounded-xl bg-white/[0.05] px-2 py-1.5">
              <p className="font-mono text-[13px] font-semibold tabular-nums text-white/90">
                {Math.round(item[m.key])}
                <span className="ml-0.5 text-[10.5px] font-normal text-white/40">g</span>
              </p>
              <p className="flex items-center gap-1 text-[10.5px] text-white/50">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${m.dot}`} />
                {m.label}
              </p>
            </div>
          ))}
        </div>
      </button>

      <AnimatePresence initial={false}>
        {selected && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            {editing ? (
              <div className="mt-2.5 flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <NumberField value={grams} onChange={setGrams} min={1} max={5000} step={5} suffix="g" ariaLabel="Grammi" />
                </div>
                <button className="btn-ghost shrink-0 px-3 py-2 text-[12.5px]" onClick={() => setEditing(false)} disabled={busy}>
                  Annulla
                </button>
                <button className="btn-primary shrink-0 px-3 py-2 text-[12.5px]" onClick={save} disabled={busy || !grams}>
                  Salva
                </button>
              </div>
            ) : (
              <div className="mt-2.5 flex gap-2">
                <button
                  onClick={() => setEditing(true)}
                  className="flex-1 rounded-xl border border-white/10 bg-white/[0.05] py-2 text-[12.5px] text-white/80 transition hover:bg-white/[0.08]"
                >
                  Modifica grammi
                </button>
                <button
                  onClick={remove}
                  disabled={busy}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-rose-400/40 bg-rose-400/15 py-2 text-[12.5px] font-semibold text-rose-100 transition hover:bg-rose-400/25 disabled:opacity-50"
                >
                  <Icon d={TRASH} className="h-3.5 w-3.5" /> {busy ? "Elimino…" : "Elimina"}
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
