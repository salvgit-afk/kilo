"use client";

/**
 * Scheda di una ricetta: copertina grande, valori per porzione, quanto è
 * adatta a oggi, motivi, ingredienti e preparazione.
 */

import { motion } from "framer-motion";
import { useState } from "react";
import type { RecipeSuggestion } from "@/lib/api";
import { AskCoachButton } from "@/components/controls";
import { ICONE, Icona, adattezza, categoriaDi } from "@/components/recipes/categorie";

const MACRO = [
  ["Proteine", "protein_per_serving", "bg-lime-400"],
  ["Carbo", "carbs_per_serving", "bg-iris-400"],
  ["Grassi", "fat_per_serving", "bg-amber-300"],
] as const;

export function RecipeCard({
  recipe: r,
  index,
  savedView = false,
  onToggleSaved,
}: {
  recipe: RecipeSuggestion;
  index: number;
  /** Nella vista Salvate punteggio e motivi non valgono più: erano di quel giorno. */
  savedView?: boolean;
  onToggleSaved: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const cat = categoriaDi(r);
  const fit = adattezza(r.fit_score);

  const etichetta =
    r.source === "kilo"
      ? { testo: "Ricetta Kilo", classe: "text-lime-300 font-semibold" }
      : r.source === "import"
        ? { testo: "tua", classe: "text-iris-200 font-semibold uppercase tracking-wide" }
        : { testo: "stimata", classe: "text-amber-100 font-semibold uppercase tracking-wide" };

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.45 }}
      className="glass sheen glass-hover overflow-hidden"
    >
      <div className="relative h-40 overflow-hidden">
        {r.thumbnail_url ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={r.thumbnail_url}
              alt={r.name}
              className="h-full w-full object-cover transition duration-700 hover:scale-105"
            />
            {/* Scurisce i bordi della foto: le etichette sopra devono leggersi su qualsiasi piatto. */}
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-ink-900/50 via-transparent to-ink-900/60" />
          </>
        ) : (
          <div className={`grid h-full w-full place-items-center bg-gradient-to-br ${cat.sfondo}`}>
            <Icona d={cat.icona} className={`h-16 w-16 opacity-60 ${cat.testo}`} />
          </div>
        )}

        <div className="absolute left-3 right-3 top-3 flex flex-wrap gap-1.5">
          <span className={`rounded-full bg-ink-900/70 px-2.5 py-1 text-[11px] backdrop-blur ${etichetta.classe}`}>
            {etichetta.testo}
          </span>
          {r.minutes ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-ink-900/70 px-2.5 py-1 text-[11px] text-white/80 backdrop-blur">
              <Icona d={ICONE.orologio} className="h-3 w-3" /> {r.minutes} min
            </span>
          ) : null}
        </div>

        <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between gap-2">
          <span
            className={`inline-flex min-w-0 items-center gap-1.5 rounded-full bg-ink-900/70 px-2.5 py-1 text-[11px] backdrop-blur ${cat.testo}`}
          >
            <Icona d={cat.icona} className="h-3 w-3" />
            <span className="truncate">{r.category || cat.nome}</span>
          </span>
          {r.meal_id && (
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
          )}
        </div>
      </div>

      <div className="p-4">
        <h3 className="text-[15.5px] font-semibold leading-snug text-white">{r.name}</h3>
        {r.area && <p className="mt-0.5 text-[11.5px] text-white/40">cucina {r.area.toLowerCase()}</p>}

        <div className="mt-3 rounded-xl border border-white/[0.07] bg-black/25 p-3">
          <p className="flex items-baseline gap-1.5">
            <span className="font-mono text-[22px] font-semibold leading-none tabular-nums text-white">
              {Math.round(r.kcal_per_serving)}
            </span>
            <span className="text-[12px] text-white/45">kcal a porzione</span>
          </p>
          {/* Stesse tre colonne del Diario: su una riga anche a 390 px. */}
          <div className="mt-2.5 grid grid-cols-3 gap-1.5">
            {MACRO.map(([nome, campo, pallino]) => (
              <div key={nome} className="rounded-xl bg-white/[0.05] px-2.5 py-1.5">
                <p className="font-mono text-[14px] font-semibold tabular-nums text-white/90">
                  {Math.round(r[campo])}
                  <span className="ml-0.5 text-[10.5px] font-normal text-white/40">g</span>
                </p>
                <p className="flex items-center gap-1 text-[10.5px] text-white/50">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${pallino}`} />
                  {nome}
                </p>
              </div>
            ))}
          </div>
        </div>

        {!savedView && (
          <div className="mt-3 flex items-center gap-2.5" title="Confronta kcal e proteine della porzione con ciò che ti resta oggi">
            <div className="flex flex-1 gap-1" aria-hidden>
              {[1, 2, 3].map((n) => (
                <span
                  key={n}
                  className={`h-1.5 flex-1 rounded-full ${
                    n > fit.livello ? "bg-white/[0.07]" : fit.livello === 1 ? "bg-amber-300" : "bg-lime-400"
                  }`}
                />
              ))}
            </div>
            <span className={`shrink-0 text-[11.5px] ${fit.livello === 1 ? "text-amber-100/80" : "text-white/60"}`}>
              {fit.etichetta}
            </span>
          </div>
        )}

        {r.source === "kilo" ? (
          <p className="mt-3 text-[11px] text-white/30">
            Dosi esatte · valori per porzione · {r.servings === 1 ? "1 porzione" : `${r.servings} porzioni`}
          </p>
        ) : (
          <p className="mt-3 text-[11px] text-white/30">
            Valori per porzione · {r.servings} porzioni ·{" "}
            <span className={r.coverage < 0.9 ? "text-amber-300/70" : ""}>
              {Math.round(r.coverage * 100)}% ingredienti riconosciuti
            </span>
            {r.original_name && <> · titolo originale «{r.original_name}»</>}
          </p>
        )}

        {!savedView && r.reasons.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {r.reasons.map((reason, k) => (
              <li key={k} className="flex gap-2 text-[12.5px] leading-snug text-white/60">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-lime-400" />
                {reason}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
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
    </motion.article>
  );
}
