"use client";

/**
 * Nota di Kilo: la mascotte "parla" in cima alla sezione.
 *
 * Compare solo quando c'è qualcosa di utile da dire, una nota alla volta
 * (la più importante), con le fonti da cui viene. Tre uscite:
 *  - **Approfondisci**: apre la chat con la domanda della nota;
 *  - l'**azione** della sezione, se c'è (es. "Fai il punto" apre il feedback);
 *  - **Ho capito**: la chiude per sempre, su tutti i dispositivi.
 *
 * In "Oggi" mostra la nota più importante di tutta l'app, con il pulsante
 * per aprire la sezione a cui si riferisce.
 */

import { AnimatePresence, motion } from "framer-motion";
import { askCoach, SECTION_LABELS } from "@/lib/coach";
import { useNotes } from "@/lib/notes";
import type { AgentNote } from "@/lib/api";
import type { SectionId } from "@/components/Shell";
import { SourceTags } from "@/components/ui";
import { Mascot } from "@/components/Mascot";

const TONE: Record<AgentNote["tone"], { bubble: string; dot: string; label: string }> = {
  success: { bubble: "border-lime-400/25 bg-lime-400/[0.06]", dot: "bg-lime-400", label: "Traguardo" },
  info: { bubble: "border-iris-400/25 bg-iris-400/[0.07]", dot: "bg-iris-300", label: "Da sapere" },
  attention: { bubble: "border-amber-300/25 bg-amber-300/[0.06]", dot: "bg-amber-300", label: "Da guardare" },
};

const ACTION_LABELS: Record<string, string> = {
  feedback: "Fai il punto",
};

export function KiloNote({
  section,
  onAction,
  onNavigate,
  className = "mb-5",
}: {
  section: SectionId;
  /** Gestisce l'azione dedicata della nota (es. "feedback"). */
  onAction?: (action: string) => void;
  /** Solo in "Oggi": apre la sezione a cui si riferisce la nota. */
  onNavigate?: (section: SectionId) => void;
  className?: string;
}) {
  const { forSection, dismiss } = useNotes();
  const notes = forSection(section);
  const note = notes[0];

  return (
    <AnimatePresence mode="wait" initial={false}>
      {note && (
        <motion.div
          key={note.key}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6, transition: { duration: 0.18 } }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className={`flex items-start gap-2.5 sm:gap-3 ${className}`}
        >
          {/* Su schermi piccoli la mascotte entra nel fumetto: a lato
              toglierebbe troppa larghezza al testo. */}
          <div className="mt-1 hidden shrink-0 sm:block">
            <Mascot size={44} mood={note.tone === "success" ? "happy" : "idle"} />
          </div>

          <div
            className={`relative min-w-0 flex-1 rounded-2xl border px-4 py-3.5 backdrop-blur-md sm:rounded-tl-md ${TONE[note.tone].bubble}`}
          >
            <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-[0.14em] text-white/45">
                <Mascot size={20} mood={note.tone === "success" ? "happy" : "idle"} className="-my-1 sm:hidden" />
                <span className={`hidden h-1.5 w-1.5 rounded-full sm:inline-block ${TONE[note.tone].dot}`} />
                Kilo · {TONE[note.tone].label}
                {section === "oggi" && note.section !== "oggi" && (
                  <> · {SECTION_LABELS[note.section as SectionId] ?? note.section}</>
                )}
              </span>
              {notes.length > 1 && (
                <span className="text-[10.5px] text-white/30">1 di {notes.length}</span>
              )}
            </div>
            <p className="text-[14px] font-semibold leading-snug text-white">{note.title}</p>
            <p className="mt-1 text-[13px] leading-relaxed text-white/65">{note.text}</p>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                onClick={() => askCoach(note.question, `Nota di Kilo: ${note.title}`)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-iris-400/30 bg-iris-400/[0.1] px-2.5 py-1.5 text-[12px] font-medium text-iris-100 transition hover:border-iris-400/50 hover:bg-iris-400/[0.18]"
              >
                <Mascot size={15} />
                Approfondisci
              </button>
              {note.action && onAction && ACTION_LABELS[note.action] && (
                <button
                  onClick={() => onAction(note.action!)}
                  className="rounded-lg border border-lime-400/30 bg-lime-400/[0.08] px-2.5 py-1.5 text-[12px] font-medium text-lime-200 transition hover:border-lime-400/50 hover:bg-lime-400/[0.15]"
                >
                  {ACTION_LABELS[note.action]}
                </button>
              )}
              {onNavigate && note.section !== section && (
                <button
                  onClick={() => onNavigate(note.section as SectionId)}
                  className="rounded-lg border border-white/12 bg-white/[0.04] px-2.5 py-1.5 text-[12px] font-medium text-white/75 transition hover:border-white/25 hover:text-white"
                >
                  Apri {SECTION_LABELS[note.section as SectionId] ?? note.section} →
                </button>
              )}
              <button
                onClick={() => dismiss(note.key)}
                className="ml-auto rounded-lg px-2 py-1.5 text-[12px] text-white/40 transition hover:bg-white/[0.06] hover:text-white/80"
              >
                Ho capito
              </button>
            </div>

            {note.knowledge_tags.length > 0 && (
              <div className="mt-2.5 border-t border-white/[0.06] pt-2.5">
                <SourceTags tags={note.knowledge_tags} />
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
