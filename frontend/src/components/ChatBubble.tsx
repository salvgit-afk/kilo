"use client";

/**
 * Il coach: assistente conversazionale sempre raggiungibile.
 *
 * Il coach **propone, non esegue**. Una risposta può includere azioni —
 * aprire il diario con una ricerca, generare una scheda, registrare il peso
 * appena detto — che partono solo con un clic dell'utente. Il backend valida
 * ogni azione (tipi ammessi, valori plausibili, niente integratori se non se
 * ne è parlato) prima che arrivi qui.
 *
 * Ogni sezione può fargli una domanda con `askCoach()`: la chat si apre e
 * risponde sapendo da quale schermata arriva la domanda.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { SPLIT_LABELS, api, type ChatAction, type ChatMessage, type ChatReply } from "@/lib/api";
import { COACH_EVENT, SECTION_LABELS, type CoachAsk, type Intent } from "@/lib/coach";
import type { SectionId } from "@/components/Shell";
import { SourceTags } from "@/components/ui";
import { CloseButton, useEscape } from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { useNotes } from "@/lib/notes";

type Message = ChatMessage & { tags?: string[]; actions?: ChatAction[] };

const SUGGERIMENTI: Record<SectionId, string[]> = {
  oggi: [
    "Cosa mangio stasera per chiudere i macro?",
    "Come sta andando la mia settimana?",
    "Quante proteine mi servono davvero?",
  ],
  scheda: [
    "Perché 6-8 ripetizioni sui multi-articolari?",
    "Quando devo aumentare il carico?",
    "I DOMS mi durano troppo: cosa cambio?",
  ],
  diario: [
    "Cosa mi manca per chiudere la giornata?",
    "Come distribuisco le proteine nei pasti?",
    "Quanta fibra dovrei mangiare?",
  ],
  ricette: [
    "Un'idea proteica per cena con quello che mi resta?",
    "Come rendo più leggera una ricetta?",
  ],
  progressi: [
    "Il mio peso sta andando nella direzione giusta?",
    "Come capisco se sono in stallo?",
  ],
  integratori: [
    "La creatina è sicura?",
    "Cosa dicono le fonti sulla glutammina?",
  ],
  profilo: [
    "Come vengono calcolate le mie calorie?",
    "Cosa cambia se passo a 4 allenamenti?",
  ],
};

function actionLabel(a: ChatAction): string {
  switch (a.type) {
    case "log_weight":
      return `Registra ${Number(a.value).toLocaleString("it-IT")} kg`;
    case "generate_plan":
      return `Genera scheda ${SPLIT_LABELS[a.value ?? ""] ?? ""}`.trim();
    case "search_food":
      return `Cerca «${a.value}» nel diario`;
    case "search_recipe":
      return `Ricette con «${a.value}»`;
    default:
      return a.label;
  }
}

function EscapeToClose({ onClose }: { onClose: () => void }) {
  useEscape(onClose);
  return null;
}

export function ChatBubble({
  profileId,
  section,
  onNavigate,
  onIntent,
}: {
  profileId: number;
  section: SectionId;
  onNavigate: (s: SectionId) => void;
  onIntent: (intent: Omit<Intent, "nonce">) => void;
}) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [used, setUsed] = useState<Set<string>>(new Set());
  // Note di Kilo per la sezione aperta non ancora portate in chat: fanno
  // comparire il pallino sul pulsante, e aprendo la chat diventano il primo
  // messaggio.
  const { forSection } = useNotes();
  const [shownNotes, setShownNotes] = useState<Set<string>>(new Set());
  const pendingNotes = forSection(section).filter((n) => !shownNotes.has(n.key));
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Riferimenti aggiornati: `send` viene chiamata anche dagli eventi delle
  // sezioni, che non devono vedere uno storico vecchio.
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const sectionRef = useRef(section);
  sectionRef.current = section;
  const busyRef = useRef(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 80);
  }, [open]);

  const push = (m: Message) => setMessages((prev) => [...prev, m]);

  const send = useCallback(
    async (text: string, context?: string) => {
      const domanda = text.trim();
      if (!domanda || busyRef.current) return;

      const storico = messagesRef.current.map(({ role, content }) => ({ role, content }));
      push({ role: "user", content: domanda });
      setInput("");
      setBusy(true);
      busyRef.current = true;

      try {
        const reply = await api.post<ChatReply>(`/workout/chat?profile_id=${profileId}`, {
          message: domanda,
          history: storico,
          context: context ?? `Sezione ${SECTION_LABELS[sectionRef.current]}`,
        });
        push({
          role: "assistant",
          content: reply.answer,
          tags: reply.knowledge_tags,
          actions: reply.actions,
        });
      } catch (e) {
        push({
          role: "assistant",
          content:
            e instanceof Error
              ? `Non sono riuscito a rispondere: ${e.message}`
              : "Non sono riuscito a rispondere.",
        });
      } finally {
        setBusy(false);
        busyRef.current = false;
      }
    },
    [profileId]
  );

  useEffect(() => {
    const onAsk = (e: Event) => {
      const { question, context } = (e as CustomEvent<CoachAsk>).detail;
      setOpen(true);
      send(question, context);
    };
    window.addEventListener(COACH_EVENT, onAsk);
    return () => window.removeEventListener(COACH_EVENT, onAsk);
  }, [send]);

  async function runAction(a: ChatAction, key: string) {
    if (used.has(key)) return;
    setUsed((prev) => new Set(prev).add(key));

    switch (a.type) {
      case "open_section":
        if (a.section) onNavigate(a.section as SectionId);
        break;
      case "generate_plan":
        onIntent({ section: "scheda", generateSplit: a.value ?? "auto" });
        setOpen(false);
        break;
      case "search_food":
        onIntent({ section: "diario", foodQuery: a.value ?? "" });
        setOpen(false);
        break;
      case "search_recipe":
        onIntent({ section: "ricette", recipeQuery: a.value ?? "" });
        setOpen(false);
        break;
      case "ask":
        send(a.value ?? a.label);
        break;
      case "log_weight": {
        const kg = Number(a.value);
        try {
          await api.post(`/profile/${profileId}/weight`, { weight_kg: kg });
          push({
            role: "assistant",
            content: `Fatto: ho registrato ${kg.toLocaleString("it-IT")} kg per oggi. Lo trovi nei Progressi.`,
          });
        } catch (e) {
          setUsed((prev) => {
            const next = new Set(prev);
            next.delete(key);
            return next;
          });
          push({
            role: "assistant",
            content: `Non sono riuscito a registrare il peso: ${e instanceof Error ? e.message : "errore"}`,
          });
        }
        break;
      }
    }
  }

  return (
    <>
      <motion.button
        onClick={() => {
          if (!open && pendingNotes.length) {
            const nota = pendingNotes[0];
            push({
              role: "assistant",
              content: `${nota.title}\n\n${nota.text}`,
              tags: nota.knowledge_tags,
              actions: [{ type: "ask", label: "Approfondisci", section: null, value: nota.question }],
            });
            setShownNotes((prev) => new Set(prev).add(nota.key));
          }
          setOpen((o) => !o);
        }}
        whileTap={{ scale: 0.93 }}
        whileHover={{ scale: 1.07 }}
        className="group fixed bottom-[calc(6rem+env(safe-area-inset-bottom))] right-4 z-[100] grid h-[62px] w-[62px] place-items-center rounded-full border border-lime-400/30 bg-gradient-to-b from-ink-600 to-ink-800 shadow-lift ring-4 ring-lime-400/[0.07] lg:bottom-6 lg:right-6"
        aria-label={open ? "Chiudi la chat con Kilo" : "Apri la chat con Kilo"}
      >
        <span className="coach-fab block">
          <Mascot size={48} mood={busy ? "thinking" : "idle"} />
        </span>
        <AnimatePresence>
          {!open && pendingNotes.length > 0 && (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              aria-label="Kilo ha una nota per te"
              className="absolute right-0.5 top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full border-2 border-ink-900 bg-lime-400 px-1 text-[10px] font-bold leading-none text-ink-900"
            >
              {pendingNotes.length}
            </motion.span>
          )}
        </AnimatePresence>
        {!open && (
          <span className="pointer-events-none absolute right-full mr-3 hidden whitespace-nowrap rounded-lg border border-white/10 bg-ink-800/95 px-2.5 py-1.5 text-[12px] text-white/85 opacity-0 shadow-lift transition group-hover:opacity-100 lg:block">
            Chiedi a Kilo
          </span>
        )}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 14, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 340, damping: 30 }}
            // Su mobile il pannello parte sopra la mascotte (che sta sopra la
            // barra di navigazione): altrimenti la copriva e non si poteva
            // richiudere la chat toccandola.
            className="glass fixed inset-x-3 bottom-[calc(168px+env(safe-area-inset-bottom))] z-[100] flex max-h-[calc(100dvh-190px-env(safe-area-inset-bottom))] flex-col overflow-hidden bg-ink-800/90 lg:inset-x-auto lg:bottom-[100px] lg:right-6 lg:h-[580px] lg:max-h-[75dvh] lg:w-[420px]"
          >
            <EscapeToClose onClose={() => setOpen(false)} />

            <div className="flex shrink-0 items-center gap-3 border-b border-white/[0.06] px-4 py-3">
              <div className="grid h-11 w-11 place-items-center rounded-xl border border-white/10 bg-white/[0.04]">
                <Mascot size={36} mood={busy ? "thinking" : "idle"} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold text-white">Kilo</p>
                <p className="truncate text-[11px] text-white/40">
                  {busy ? "Sto pensando…" : "Risponde sui tuoi dati · propone, tu confermi"}
                </p>
              </div>
              {messages.length > 0 && (
                <button
                  onClick={() => {
                    setMessages([]);
                    setUsed(new Set());
                  }}
                  className="rounded-lg px-2 py-1.5 text-[11.5px] text-white/40 transition hover:bg-white/5 hover:text-white/85"
                >
                  Nuova
                </button>
              )}
              <CloseButton onClose={() => setOpen(false)} />
            </div>

            <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto overscroll-contain px-4 py-4">
              {messages.length === 0 && (
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    <Mascot size={42} mood="happy" className="shrink-0" />
                    <p className="text-[13px] leading-relaxed text-white/60">
                      Ciao, sono Kilo! Conosco il tuo profilo, la tua scheda, il diario di oggi e i tuoi
                      target. Chiedimi pure: se serve fare qualcosa te lo propongo, e tu
                      confermi con un clic.
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    {SUGGERIMENTI[section].map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="block w-full rounded-lg border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-left text-[12.5px] text-white/65 transition hover:border-iris-400/30 hover:bg-iris-400/[0.07] hover:text-white"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={m.role === "user" ? "flex justify-end" : "flex items-start gap-2"}
                >
                  {m.role === "assistant" && <Mascot size={24} className="mt-1 shrink-0" />}
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[85%] rounded-2xl rounded-br-md border border-iris-400/25 bg-iris-400/[0.14] px-3.5 py-2.5 text-[13px] leading-relaxed text-white/90"
                        : "min-w-0 max-w-[90%] space-y-2"
                    }
                  >
                    <p
                      className={
                        m.role === "assistant"
                          ? "whitespace-pre-line rounded-2xl rounded-tl-md border border-white/[0.07] bg-white/[0.04] px-3.5 py-2.5 text-[13px] leading-relaxed text-white/80"
                          : ""
                      }
                    >
                      {m.content}
                    </p>

                    {m.actions && m.actions.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="flex flex-wrap gap-1.5">
                          {m.actions.map((a, k) => {
                            const key = `${i}-${k}`;
                            const fatto = used.has(key);
                            return (
                              <button
                                key={key}
                                disabled={fatto}
                                onClick={() => runAction(a, key)}
                                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition ${
                                  fatto
                                    ? "border-white/10 text-white/35"
                                    : "border-lime-400/30 bg-lime-400/[0.08] text-lime-200 hover:-translate-y-px hover:bg-lime-400/[0.16]"
                                }`}
                              >
                                {fatto ? (
                                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                                    <path d="m9.5 16.2-4-4L4 13.7l5.5 5.5L20 8.7l-1.5-1.5-9 9Z" />
                                  </svg>
                                ) : (
                                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                                    <path d="M5 11h11.2l-4.6-4.6L13 5l7 7-7 7-1.4-1.4 4.6-4.6H5v-2Z" />
                                  </svg>
                                )}
                                {actionLabel(a)}
                              </button>
                            );
                          })}
                        </div>
                        <p className="text-[10.5px] text-white/30">Partono solo se le clicchi.</p>
                      </div>
                    )}

                    {m.tags && m.tags.length > 0 && <SourceTags tags={m.tags} />}
                  </div>
                </motion.div>
              ))}

              {busy && (
                <div className="flex items-center gap-2 pl-1">
                  <Mascot size={24} mood="thinking" />
                  <div className="flex gap-1.5 rounded-2xl border border-white/[0.07] bg-white/[0.04] px-3.5 py-3">
                    {[0, 1, 2].map((i) => (
                      <motion.span
                        key={i}
                        className="h-1.5 w-1.5 rounded-full bg-white/50"
                        animate={{ opacity: [0.25, 1, 0.25] }}
                        transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.18 }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="shrink-0 border-t border-white/[0.06] p-3"
            >
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  className="input py-2 text-[13px]"
                  placeholder="Scrivi a Kilo…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || busy}
                  aria-label="Invia"
                  className="btn-primary shrink-0 px-3 py-2"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                    <path d="M3 20v-6l8-2-8-2V4l19 8-19 8Z" />
                  </svg>
                </button>
              </div>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
