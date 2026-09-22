"use client";

/**
 * Controlli condivisi dall'intera interfaccia.
 *
 *  - `Modal`: tutti gli overlay hanno la stessa struttura — intestazione e
 *    piè di pagina fissi, contenuto che scorre. È ciò che mancava al pannello
 *    del diario, dove il pulsante "Aggiungi" finiva fuori dallo schermo.
 *  - `CloseButton`: 40 px di area cliccabile (la X da 16 px era difficile da
 *    centrare) e chiusura anche con Esc — solo dell'overlay più in alto.
 *  - `NumberField`: sostituisce le freccette native di `type=number`, che
 *    producevano "065" digitando su un campo con 0 e passi da 0,1 sul peso.
 *  - `ModalBody`, `ModalFooter`, `Field`, `Stepper`, `OptionGroup`, `Toggle`:
 *    i mattoni comuni di pannelli e form (vedi la sezione più sotto).
 *  - `DemoAnimation`: alterna i fotogrammi di partenza e arrivo di un
 *    esercizio.
 */

import { motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { askCoach } from "@/lib/coach";
import { Mascot } from "@/components/Mascot";

// --- Esc: chiude solo l'overlay più in alto -----------------------------------------

const escapeStack: { current: () => void }[] = [];

if (typeof window !== "undefined" && !(window as unknown as { __escBound?: boolean }).__escBound) {
  (window as unknown as { __escBound?: boolean }).__escBound = true;
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && escapeStack.length) {
      escapeStack[escapeStack.length - 1].current();
    }
  });
}

export function useEscape(onClose: () => void) {
  const ref = useRef(onClose);
  ref.current = onClose;
  useEffect(() => {
    const entry = ref;
    escapeStack.push(entry);
    return () => {
      const i = escapeStack.lastIndexOf(entry);
      if (i >= 0) escapeStack.splice(i, 1);
    };
  }, []);
}

// --- Overlay ---------------------------------------------------------------------------

export function Modal({
  onClose,
  children,
  className = "max-w-xl",
  z = "z-[80]",
  align = "center",
}: {
  onClose: () => void;
  children: ReactNode;
  className?: string;
  z?: string;
  align?: "center" | "top";
}) {
  useEscape(onClose);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      role="dialog"
      aria-modal="true"
      // mousedown e non click: trascinare una selezione di testo fuori dal
      // pannello non deve chiuderlo.
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      // Margini con le zone sicure: nell'app sulla Home dell'iPhone la barra
      // di stato e l'indicatore home stanno sopra la pagina.
      className={`fixed inset-0 ${z} flex justify-center bg-black/75 px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-[calc(0.75rem+env(safe-area-inset-top))] backdrop-blur-sm sm:p-6 ${
        align === "top" ? "items-start sm:pt-[7vh]" : "items-center"
      }`}
    >
      <motion.div
        initial={{ scale: 0.96, y: 14 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.97, opacity: 0 }}
        transition={{ type: "spring", stiffness: 330, damping: 30 }}
        // Un solo limite di altezza per breakpoint: con due classi `sm:max-h`
        // vinceva quella sbagliata e il pulsante in fondo usciva dallo schermo.
        // In alto il margine è 7dvh sopra e 1.5rem sotto.
        className={`glass flex max-h-[calc(100dvh-1.5rem-env(safe-area-inset-top)-env(safe-area-inset-bottom))] w-full flex-col overflow-hidden ${
          align === "top" ? "sm:max-h-[calc(93dvh-1.5rem)]" : "sm:max-h-[calc(100dvh-3rem)]"
        } ${className}`}
      >
        {children}
      </motion.div>
    </motion.div>
  );
}

export function ModalHeader({
  title,
  subtitle,
  eyebrow,
  onClose,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: string;
  onClose: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="flex shrink-0 items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
      <div className="min-w-0 flex-1">
        {eyebrow && (
          <p className="mb-0.5 text-[10.5px] font-medium uppercase tracking-[0.14em] text-lime-400/75">
            {eyebrow}
          </p>
        )}
        <h2 className="text-[16px] font-semibold leading-tight tracking-tight text-white">{title}</h2>
        {subtitle && <p className="mt-1 text-[12.5px] leading-snug text-white/45">{subtitle}</p>}
        {children}
      </div>
      <CloseButton onClose={onClose} />
    </div>
  );
}

export function CloseButton({
  onClose,
  className = "",
  floating = false,
}: {
  onClose: () => void;
  className?: string;
  floating?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Chiudi"
      title="Chiudi (Esc)"
      className={`group grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/[0.12] text-white/70 transition hover:border-white/25 hover:bg-white/[0.12] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 active:scale-95 ${
        floating ? "bg-black/55 backdrop-blur-md" : "bg-white/[0.05]"
      } ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-[18px] w-[18px] transition-transform duration-200 group-hover:rotate-90"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.3}
        strokeLinecap="round"
      >
        <path d="M6 6l12 12M18 6 6 18" />
      </svg>
    </button>
  );
}

// --- Mattoni dei pannelli e dei form -------------------------------------------------
//
// Ogni overlay e ogni menu di modifica usa gli stessi pezzi, così bottoni,
// forme e scelte si riconoscono ovunque:
//  - `ModalBody` / `ModalFooter`: contenuto che scorre e piede fisso, con
//    "Annulla" a sinistra e l'azione principale, più larga, a destra;
//  - `Field`: un riquadro con titolo e suggerimento per ogni valore;
//  - `Stepper`: − valore + per i numeri piccoli (serie, ripetizioni);
//  - `OptionGroup`: scelte a riquadri, la scelta attiva piena in lime come
//    le linguette;
//  - `Toggle`: interruttore al posto delle caselle di spunta.

export function ModalBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5 ${className}`}>
      {children}
    </div>
  );
}

export function ModalFooter({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex shrink-0 items-center gap-2 border-t border-white/[0.06] bg-ink-900/50 px-4 py-3 sm:px-5 ${className}`}>
      {children}
    </div>
  );
}

export function Field({
  title,
  hint,
  children,
  className = "",
  action,
}: {
  title: ReactNode;
  hint?: ReactNode;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <div className={`rounded-2xl border border-white/[0.08] bg-white/[0.03] p-3.5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] font-medium uppercase tracking-wide text-white/50">{title}</p>
          {hint && <p className="mt-0.5 text-[11.5px] leading-snug text-white/35">{hint}</p>}
        </div>
        {action}
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}

export function Stepper({
  value,
  onChange,
  min,
  max,
  step = 1,
  format = String,
  label,
  compact = false,
}: {
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  step?: number;
  format?: (n: number) => string;
  label: string;
  compact?: boolean;
}) {
  const bottone = (dir: 1 | -1) => (
    <motion.button
      type="button"
      whileTap={{ scale: 0.88 }}
      disabled={dir < 0 ? value <= min : value >= max}
      onClick={() => onChange(Math.min(max, Math.max(min, value + dir * step)))}
      aria-label={`${dir > 0 ? "Aumenta" : "Diminuisci"} ${label}`}
      className={`grid shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.05] text-white/70 transition hover:border-lime-400/40 hover:text-lime-200 disabled:opacity-25 ${
        compact ? "h-9 w-9" : "h-10 w-10"
      }`}
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round">
        {dir > 0 ? <path d="M12 5v14M5 12h14" /> : <path d="M5 12h14" />}
      </svg>
    </motion.button>
  );
  return (
    <div className="flex items-center justify-between gap-2">
      {bottone(-1)}
      <span className="min-w-0 flex-1 whitespace-nowrap text-center font-mono text-[22px] font-semibold tabular-nums text-white">
        {format(value)}
      </span>
      {bottone(1)}
    </div>
  );
}

export type Option<T> = { value: T; label: ReactNode; hint?: ReactNode };

export function OptionGroup<T extends string | number>({
  options,
  value,
  onChange,
  columns,
  mono = false,
  size = "md",
  ariaLabel,
}: {
  options: Option<T>[];
  value: T | null;
  onChange: (v: T) => void;
  /** Colonne della griglia; senza, le scelte si dividono la riga. */
  columns?: string;
  mono?: boolean;
  /** "sm" per le scelte rapide dentro intestazioni e piè di pagina. */
  size?: "sm" | "md";
  ariaLabel?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={columns ? `grid gap-1.5 ${columns}` : "flex flex-wrap gap-1.5"}
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <motion.button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={on}
            whileTap={{ scale: 0.95 }}
            onClick={() => onChange(o.value)}
            className={`rounded-xl border px-2 text-center transition sm:px-3 ${columns ? "" : "flex-1"} ${
              size === "sm" ? "min-h-[36px] py-1.5" : "min-h-[42px] py-2"
            } ${
              mono
                ? `font-mono font-semibold tabular-nums ${size === "sm" ? "text-[13px]" : "text-[15px]"}`
                : `font-medium ${size === "sm" ? "text-[12.5px]" : "text-[13px]"}`
            } ${
              on
                ? "border-lime-400/60 bg-gradient-to-b from-lime-400 to-lime-500 text-ink-900 shadow-[0_6px_16px_-10px_rgba(174,212,74,0.9)]"
                : "border-white/10 bg-white/[0.03] text-white/65 hover:border-white/20 hover:text-white"
            }`}
          >
            <span className="block leading-tight">{o.label}</span>
            {o.hint && (
              <span className={`mt-0.5 block text-[11px] font-normal leading-snug ${on ? "text-ink-900/70" : "text-white/35"}`}>
                {o.hint}
              </span>
            )}
          </motion.button>
        );
      })}
    </div>
  );
}

/** Calorie e macro in quattro colonne: la stessa riga in diario, ricette e importazione. */
export function MacroGrid({ items, note }: { items: [string, ReactNode][]; note?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-2 py-3">
      <div className="grid grid-cols-4 gap-2">
        {items.map(([label, value]) => (
          <div key={label} className="text-center">
            <p className="font-mono text-[15px] font-semibold tabular-nums text-white">{value}</p>
            <p className="mt-0.5 text-[10.5px] uppercase tracking-wide text-white/35">{label}</p>
          </div>
        ))}
      </div>
      {note && <p className="mt-2 text-center text-[11px] text-white/35">{note}</p>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-3 text-left transition hover:border-white/15"
    >
      <span className="min-w-0">
        <span className="block text-[13.5px] font-medium text-white/85">{label}</span>
        {hint && <span className="mt-0.5 block text-[11.5px] leading-snug text-white/40">{hint}</span>}
      </span>
      <span
        className={`relative h-7 w-12 shrink-0 rounded-full border transition-colors ${
          checked ? "border-lime-400/60 bg-lime-400" : "border-white/15 bg-white/[0.06]"
        }`}
      >
        <motion.span
          layout
          transition={{ type: "spring", stiffness: 500, damping: 34 }}
          className={`absolute top-[3px] h-5 w-5 rounded-full shadow ${checked ? "right-[3px] bg-ink-900" : "left-[3px] bg-white/70"}`}
        />
      </span>
    </button>
  );
}

// --- Campo numerico ------------------------------------------------------------------

function formatNumber(value: number | null, decimals: number) {
  if (value === null || Number.isNaN(value)) return "";
  return decimals > 0
    ? String(Number(value.toFixed(decimals))).replace(".", ",")
    : String(Math.round(value));
}

function parseNumber(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text.replace(",", "."));
  return Number.isNaN(n) ? null : n;
}

export function NumberField({
  value,
  onChange,
  step = 1,
  min,
  max,
  decimals = 0,
  suffix,
  placeholder,
  ariaLabel,
  size = "md",
  className = "",
  inputRef,
  onEnter,
  steppers = "always",
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  step?: number;
  min?: number;
  max?: number;
  decimals?: number;
  suffix?: string;
  placeholder?: string;
  ariaLabel?: string;
  size?: "sm" | "md";
  className?: string;
  inputRef?: React.Ref<HTMLInputElement>;
  onEnter?: () => void;
  /** "sm": pulsanti +/− solo da tablet in su; sul telefono si digita, con il
   * tastierino numerico, e i campi di una riga ci stanno affiancati. */
  steppers?: "always" | "sm";
}) {
  // Il testo è separato dal numero: mentre si digita "65" il campo deve
  // mostrare esattamente ciò che si scrive, non una rilettura del numero.
  const [text, setText] = useState(() => formatNumber(value, decimals));
  const [focused, setFocused] = useState(false);
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    if (!focused) setText(formatNumber(value, decimals));
  }, [value, decimals, focused]);

  const clamp = (n: number) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, n));

  function bump(direction: 1 | -1) {
    const base = valueRef.current ?? min ?? 0;
    const next = clamp(Number((base + direction * step).toFixed(Math.max(decimals, 2))));
    valueRef.current = next;
    onChange(next);
    setText(formatNumber(next, decimals));
  }

  // Tenendo premuto il pulsante il valore continua a scorrere.
  const hold = useRef<{ t?: ReturnType<typeof setTimeout>; i?: ReturnType<typeof setInterval> }>({});
  const stopHold = () => {
    clearTimeout(hold.current.t);
    clearInterval(hold.current.i);
  };
  const startHold = (direction: 1 | -1) => {
    stopHold();
    bump(direction);
    hold.current.t = setTimeout(() => {
      hold.current.i = setInterval(() => bump(direction), 75);
    }, 420);
  };
  useEffect(() => stopHold, []);

  const pattern = decimals > 0 ? /^\d*([.,]\d*)?$/ : /^\d*$/;
  const atMin = value !== null && min !== undefined && value <= min;
  const atMax = value !== null && max !== undefined && value >= max;
  const height = size === "sm" ? "h-9" : "h-[42px]";

  const stepButton = (direction: 1 | -1, disabled: boolean) => (
    <button
      type="button"
      tabIndex={-1}
      disabled={disabled}
      aria-label={direction > 0 ? "Aumenta" : "Diminuisci"}
      onPointerDown={(e) => {
        e.preventDefault();
        startHold(direction);
      }}
      onPointerUp={stopHold}
      onPointerLeave={stopHold}
      onPointerCancel={stopHold}
      className={`${steppers === "sm" ? "hidden sm:grid" : "grid"} w-9 shrink-0 place-items-center text-white/45 transition hover:bg-lime-400/10 hover:text-lime-300 active:bg-lime-400/20 disabled:pointer-events-none disabled:opacity-25 ${
        direction > 0 ? "border-l" : "border-r"
      } border-white/[0.07]`}
    >
      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round">
        {direction > 0 ? <path d="M12 5v14M5 12h14" /> : <path d="M5 12h14" />}
      </svg>
    </button>
  );

  return (
    <div
      className={`flex items-stretch overflow-hidden rounded-xl border border-white/10 bg-black/30 transition focus-within:border-lime-400/50 focus-within:ring-2 focus-within:ring-lime-400/15 ${height} ${className}`}
    >
      {stepButton(-1, atMin)}
      <div className="flex min-w-0 flex-1 items-center">
        <input
          ref={inputRef}
          type="text"
          inputMode={decimals > 0 ? "decimal" : "numeric"}
          aria-label={ariaLabel}
          placeholder={placeholder}
          value={text}
          onFocus={(e) => {
            setFocused(true);
            e.target.select();
          }}
          onBlur={() => {
            setFocused(false);
            const n = parseNumber(text);
            const normalized = n === null ? null : clamp(Number(n.toFixed(decimals)));
            onChange(normalized);
            setText(formatNumber(normalized, decimals));
          }}
          onChange={(e) => {
            const t = e.target.value;
            if (!pattern.test(t)) return;
            setText(t);
            // Niente limiti mentre si digita: con un minimo di 30, il "6" di
            // "65" verrebbe corretto in 30 prima di poter scrivere il "5".
            const n = parseNumber(t);
            if (n !== null) onChange(n);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowUp") {
              e.preventDefault();
              bump(1);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              bump(-1);
            } else if (e.key === "Enter") {
              onEnter?.();
            }
          }}
          className={`w-full min-w-0 bg-transparent text-center font-mono tabular-nums text-white outline-none placeholder:text-white/25 ${
            size === "sm" ? "text-[13px]" : "text-sm"
          }`}
        />
        {suffix && (
          <span className="pointer-events-none pr-2.5 text-[11px] text-white/35">{suffix}</span>
        )}
      </div>
      {stepButton(1, atMax)}
    </div>
  );
}

// --- Animazione dell'esecuzione --------------------------------------------------------

const FIT = { cover: "object-cover", contain: "object-contain" } as const;

export function DemoAnimation({
  images,
  alt,
  className = "",
  fit = "cover",
  mode = "auto",
  controls = false,
  interval = 950,
}: {
  images: (string | null | undefined)[] | null | undefined;
  alt: string;
  className?: string;
  fit?: keyof typeof FIT;
  /** auto = sempre in movimento; hover = si muove al passaggio del mouse. */
  mode?: "auto" | "hover";
  controls?: boolean;
  interval?: number;
}) {
  const frames = (images ?? []).filter((x): x is string => !!x);
  const [frame, setFrame] = useState(0);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const playing = frames.length > 1 && !paused && (mode === "auto" || hovered);

  useEffect(() => {
    if (!playing) {
      if (mode === "hover") setFrame(0);
      return;
    }
    const id = setInterval(() => setFrame((f) => (f + 1) % frames.length), interval);
    return () => clearInterval(id);
  }, [playing, frames.length, interval, mode]);

  if (!frames.length) {
    return (
      <div className={`grid place-items-center bg-white/[0.03] ${className}`}>
        <svg viewBox="0 0 24 24" className="h-1/3 max-h-10 w-1/3 max-w-10 fill-white/15">
          <path d="M4 9h2v6H4V9Zm14 0h2v6h-2V9ZM7 7h2v10H7V7Zm8 0h2v10h-2V7Zm-5 4h4v2h-4v-2Z" />
        </svg>
      </div>
    );
  }

  return (
    <div
      className={`relative overflow-hidden bg-white ${className}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {frames.map((src, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={src}
          src={src}
          alt={i === 0 ? alt : ""}
          loading="lazy"
          draggable={false}
          className={`absolute inset-0 h-full w-full ${FIT[fit]} transition-opacity duration-300 ${
            i === frame ? "opacity-100" : "opacity-0"
          }`}
        />
      ))}

      {controls && frames.length > 1 && (
        <div className="absolute inset-x-2 bottom-2 flex items-center justify-between gap-2">
          <div className="flex gap-1 rounded-full bg-black/60 p-1 backdrop-blur-md">
            {frames.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  setPaused(true);
                  setFrame(i);
                }}
                className={`rounded-full px-2.5 py-1 text-[10.5px] font-medium transition ${
                  i === frame ? "bg-lime-400 text-ink-900" : "text-white/70 hover:text-white"
                }`}
              >
                {i === 0 ? "Partenza" : i === frames.length - 1 ? "Arrivo" : `Fase ${i + 1}`}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            aria-label={paused ? "Riproduci" : "Metti in pausa"}
            className="grid h-8 w-8 place-items-center rounded-full bg-black/60 text-white/85 backdrop-blur-md transition hover:bg-black/75"
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
              {paused ? <path d="M8 5v14l11-7L8 5Z" /> : <path d="M7 5h4v14H7V5Zm6 0h4v14h-4V5Z" />}
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

// --- Domanda al coach --------------------------------------------------------------

export function AskCoachButton({
  question,
  context,
  label = "Chiedi a Kilo",
  className = "",
  size = "md",
}: {
  question: string;
  context?: string;
  label?: string;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <button
      type="button"
      onClick={() => askCoach(question, context)}
      className={`group inline-flex items-center gap-2 rounded-xl border border-iris-400/25 bg-iris-400/[0.08] font-medium text-iris-100 transition hover:-translate-y-px hover:border-iris-400/50 hover:bg-iris-400/[0.16] ${
        size === "sm" ? "px-2.5 py-1.5 text-[12px]" : "px-3 py-2 text-[12.5px]"
      } ${className}`}
    >
      <Mascot size={size === "sm" ? 16 : 19} className="transition-transform group-hover:-rotate-6" />
      {label}
    </button>
  );
}
