"use client";

/**
 * La nota dell'utente su un esercizio: regolazioni della macchina, presa,
 * accorgimenti ("sedile 4, schienale 2"). Una per esercizio, la stessa in
 * tutte le schede e durante l'allenamento, dove serve davvero.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { api } from "@/lib/api";

const MAX = 500;
const NOTES_KEY = "kilo:note-esercizi";

/** Le note lette dal server, tenute anche sul telefono per l'allenamento senza rete. */
export function rememberNotes(note: Record<number, string>, exerciseIds: number[]) {
  try {
    const tutte = JSON.parse(localStorage.getItem(NOTES_KEY) ?? "{}") as Record<string, string>;
    for (const id of exerciseIds) {
      if (note[id]) tutte[id] = note[id];
      else delete tutte[id];
    }
    localStorage.setItem(NOTES_KEY, JSON.stringify(tutte));
  } catch {
    /* solo una comodità */
  }
}

export function recallNotes(exerciseIds: number[]): Record<number, string> {
  try {
    const tutte = JSON.parse(localStorage.getItem(NOTES_KEY) ?? "{}") as Record<string, string>;
    return Object.fromEntries(exerciseIds.filter((id) => tutte[id]).map((id) => [id, tutte[id]]));
  } catch {
    return {};
  }
}

export function ExerciseNoteLine({
  exerciseId,
  profileId,
  note,
  onSaved,
  compact = false,
}: {
  exerciseId: number;
  profileId: number;
  note: string | undefined;
  onSaved: (exerciseId: number, text: string | null) => void;
  /** Senza nota mostra solo un piccolo invito, per non allungare la riga. */
  compact?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const r = await api.put<{ exercise_id: number; text: string | null }>(
        `/workout/exercises/${exerciseId}/note?profile_id=${profileId}`,
        { text: draft }
      );
      onSaved(exerciseId, r.text);
      setEditing(false);
    } catch (e) {
      setError(
        e instanceof TypeError
          ? "Serve la rete per salvare la nota: riprova appena c'è."
          : e instanceof Error
            ? e.message
            : "Non sono riuscito a salvare la nota."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <AnimatePresence initial={false} mode="wait">
      {editing ? (
        <motion.div
          key="modifica"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="overflow-hidden"
        >
          <div className="space-y-2 pt-1">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value.slice(0, MAX))}
              rows={2}
              autoFocus
              placeholder="Es. sedile 4, schienale 2, presa stretta"
              aria-label="Nota sull'esercizio"
              className="input min-h-[64px] w-full resize-none select-text py-2 text-[13px]"
            />
            {error && <p className="text-[12px] text-rose-200/90">{error}</p>}
            <div className="flex gap-2">
              <button
                className="btn-ghost h-9 flex-1 justify-center px-3 text-[12.5px]"
                onClick={() => {
                  setEditing(false);
                  setDraft(note ?? "");
                  setError(null);
                }}
                disabled={saving}
              >
                Annulla
              </button>
              <button className="btn-primary h-9 flex-[1.4] justify-center px-3 text-[12.5px]" onClick={save} disabled={saving}>
                {saving ? "Salvo…" : draft.trim() ? "Salva la nota" : note ? "Togli la nota" : "Salva"}
              </button>
            </div>
          </div>
        </motion.div>
      ) : (
        <motion.button
          key="vista"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => {
            setDraft(note ?? "");
            setEditing(true);
          }}
          className={`flex w-full items-start gap-1.5 text-left text-[12.5px] leading-snug transition ${
            note ? "text-amber-100/85 hover:text-amber-50" : "text-white/35 hover:text-white/70"
          }`}
          aria-label={note ? `Nota: ${note}. Tocca per modificarla` : "Aggiungi una nota sull'esercizio"}
        >
          <svg viewBox="0 0 24 24" className="mt-[2px] h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth={2.2}>
            <path d="M4 20h4L19 9l-4-4L4 16v4Z" strokeLinejoin="round" />
          </svg>
          <span className={compact && !note ? "text-[11.5px]" : ""}>
            {note ?? "Aggiungi una nota (regolazioni, presa…)"}
          </span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
