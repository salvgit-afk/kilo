"use client";

/**
 * Struttura dell'applicazione: barra laterale con le sezioni.
 *
 * L'ordine non è casuale — riflette la frequenza d'uso reale: il diario si
 * apre ogni giorno, la scheda a ogni allenamento, i progressi ogni tanto.
 * **Integratori** sta in fondo ed è dichiarato come facoltativo: è una
 * sezione a cui si accede, non un consiglio che arriva da solo.
 */

import { motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { BrandMark } from "@/components/Mascot";

export type SectionId =
  | "oggi"
  | "scheda"
  | "diario"
  | "ricette"
  | "progressi"
  | "integratori"
  | "profilo";

const SECTIONS: {
  id: SectionId;
  label: string;
  hint: string;
  icon: ReactNode;
  optional?: boolean;
}[] = [
  {
    id: "oggi",
    label: "Oggi",
    hint: "Riepilogo della giornata",
    icon: <path d="M4 5h16v3H4V5Zm0 5h16v9H4v-9Zm2 2v5h5v-5H6Z" />,
  },
  {
    id: "scheda",
    label: "Scheda",
    hint: "Il tuo allenamento",
    icon: <path d="M4 9h2v6H4V9Zm14 0h2v6h-2V9ZM7 7h2v10H7V7Zm8 0h2v10h-2V7Zm-5 4h4v2h-4v-2Z" />,
  },
  {
    id: "diario",
    label: "Diario",
    hint: "Conta calorie e macro",
    icon: <path d="M5 3h11l4 4v14H5V3Zm2 2v14h10V8h-3V5H7Zm2 5h6v2H9v-2Zm0 4h6v2H9v-2Z" />,
  },
  {
    id: "ricette",
    label: "Ricette",
    hint: "Idee per i tuoi target",
    icon: <path d="M7 2v8a3 3 0 0 0 2 2.8V22h2V12.8A3 3 0 0 0 13 10V2h-2v7H9V2H7Zm10 0c-1.7 0-3 2.2-3 5v5h2v10h2V2h-1Z" />,
  },
  {
    id: "progressi",
    label: "Progressi",
    hint: "Carichi e peso nel tempo",
    icon: <path d="M4 19h16v2H4v-2Zm2-6h3v5H6v-5Zm5-5h3v10h-3V8Zm5-5h3v15h-3V3Z" />,
  },
  {
    id: "integratori",
    label: "Integratori",
    hint: "Solo se ne usi",
    optional: true,
    icon: <path d="M8.5 2a5.5 5.5 0 0 0-3.9 9.4l8 8A5.5 5.5 0 0 0 20.4 11.6l-8-8A5.5 5.5 0 0 0 8.5 2Zm-2.5 8 4-4 4 4-4 4-4-4Z" />,
  },
  {
    id: "profilo",
    label: "Profilo",
    hint: "Dati e sicurezza",
    icon: <path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0 2c-5 0-9 2.5-9 5.5V22h18v-2.5c0-3-4-5.5-9-5.5Z" />,
  },
];

/** Ordine delle sezioni: è anche l'ordine in cui le sfoglia lo swipe. */
export const SECTION_ORDER: SectionId[] = SECTIONS.map((s) => s.id);

const vibrate = () => {
  try {
    navigator.vibrate?.(8);
  } catch {
    /* vibrazione non supportata */
  }
};

// --- Swipe sul contenuto (solo mobile) -----------------------------------------

/** Un gesto orizzontale partito da qui non deve cambiare sezione. */
function swipeBlocked(target: EventTarget | null, root: HTMLElement): boolean {
  if (document.querySelector('[aria-modal="true"]')) return true;
  let el = target instanceof Element ? target : null;
  if (el?.closest("input, textarea, select, [contenteditable=true], [data-no-swipe]")) return true;
  // Contenitori che scorrono in orizzontale: lo swipe serve a loro.
  while (el && el !== root) {
    if (
      el.scrollWidth > el.clientWidth + 2 &&
      /(auto|scroll)/.test(getComputedStyle(el).overflowX)
    ) {
      return true;
    }
    el = el.parentElement;
  }
  return false;
}

/**
 * Swipe a destra o a sinistra sul contenuto: passa alla sezione accanto.
 *
 * Il contenuto segue il dito (con più resistenza se non c'è una sezione in
 * quella direzione) e torna al suo posto se il gesto è troppo corto. Il
 * gesto si "aggancia" al primo movimento: se è verticale resta uno
 * scorrimento normale della pagina.
 *
 * La trasformazione viene tolta del tutto a fine gesto: un `transform`
 * rimasto sul contenitore farebbe posizionare i pannelli `fixed` (gli
 * overlay) rispetto a lui invece che allo schermo.
 */
function useSwipeNavigation(
  ref: RefObject<HTMLDivElement | null>,
  active: SectionId,
  onNavigate: (id: SectionId) => void
) {
  const activeRef = useRef(active);
  activeRef.current = active;
  const navigateRef = useRef(onNavigate);
  navigateRef.current = onNavigate;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const mobile = window.matchMedia("(max-width: 1023px)");

    let start: { x: number; y: number; t: number } | null = null;
    let lock: "x" | "y" | null = null;
    let dx = 0;

    const neighbor = (dir: number) => {
      const i = SECTION_ORDER.indexOf(activeRef.current) + dir;
      return SECTION_ORDER[i] ?? null;
    };

    const reset = (animated: boolean) => {
      el.style.transition = animated
        ? "transform 320ms cubic-bezier(0.22, 1, 0.36, 1), opacity 320ms ease"
        : "";
      el.style.transform = "";
      el.style.opacity = "";
    };

    const onStart = (e: TouchEvent) => {
      start = null;
      lock = null;
      dx = 0;
      if (!mobile.matches || e.touches.length !== 1) return;
      const t = e.touches[0];
      // Vicino ai bordi c'è il gesto "indietro" del sistema.
      if (t.clientX < 18 || t.clientX > window.innerWidth - 18) return;
      if (swipeBlocked(e.target, el)) return;
      start = { x: t.clientX, y: t.clientY, t: e.timeStamp };
    };

    const onMove = (e: TouchEvent) => {
      if (!start || e.touches.length !== 1) return;
      const t = e.touches[0];
      const mx = t.clientX - start.x;
      const my = t.clientY - start.y;
      if (!lock) {
        if (Math.abs(mx) < 10 && Math.abs(my) < 10) return;
        lock = Math.abs(mx) > Math.abs(my) * 1.2 ? "x" : "y";
      }
      if (lock !== "x") return;
      e.preventDefault(); // niente scorrimento verticale durante lo swipe
      dx = mx;
      const resistenza = neighbor(mx < 0 ? 1 : -1) ? 0.45 : 0.12;
      const shift = mx * resistenza;
      el.style.transition = "none";
      el.style.transform = `translate3d(${shift}px, 0, 0)`;
      el.style.opacity = String(1 - Math.min(Math.abs(shift) / 420, 0.35));
    };

    const onEnd = (e: TouchEvent) => {
      if (!start || lock !== "x") {
        start = null;
        return;
      }
      const velocita = Math.abs(dx) / Math.max(e.timeStamp - start.t, 1);
      const target = neighbor(dx < 0 ? 1 : -1);
      start = null;
      if (target && (Math.abs(dx) > 90 || (Math.abs(dx) > 40 && velocita > 0.5))) {
        reset(false);
        vibrate();
        navigateRef.current(target);
      } else {
        reset(true);
      }
    };

    const onCancel = () => {
      start = null;
      reset(true);
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd);
    el.addEventListener("touchcancel", onCancel);
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onCancel);
    };
  }, [ref]);
}

export function Shell({
  active,
  onNavigate,
  profileName,
  children,
}: {
  active: SectionId;
  onNavigate: (id: SectionId) => void;
  profileName?: string;
  children: ReactNode;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  useSwipeNavigation(contentRef, active, onNavigate);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1400px] gap-6 px-4 py-5 lg:px-7">
      <aside className="sticky top-5 hidden h-[calc(100vh-2.5rem)] w-[236px] shrink-0 flex-col lg:flex">
        <div className="glass sheen flex h-full flex-col p-3.5">
          <div className="mb-6 flex items-center gap-3 px-1.5 pt-1.5">
            <BrandMark size={42} />
            <div className="min-w-0">
              <p className="truncate text-[17px] font-bold leading-tight tracking-tight text-white">
                Kilo
              </p>
              <p className="truncate text-[11px] text-white/40">allenamento e nutrizione</p>
            </div>
          </div>

          <nav className="flex flex-1 flex-col gap-1">
            {SECTIONS.map((s) => {
              const isActive = s.id === active;
              return (
                <button
                  key={s.id}
                  onClick={() => onNavigate(s.id)}
                  // Al passaggio del mouse la voce si ingrandisce appena e si
                  // illumina: il bersaglio del clic diventa evidente.
                  className={`group relative flex origin-left items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-[transform,color,background-color,filter] duration-200 ease-out hover:scale-[1.04] ${
                    isActive
                      ? "text-white"
                      : "text-white/50 hover:bg-white/[0.055] hover:text-white hover:brightness-125"
                  }`}
                >
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-xl border border-white/10 bg-white/[0.07]"
                      transition={{ type: "spring", stiffness: 380, damping: 32 }}
                    />
                  )}
                  <svg
                    viewBox="0 0 24 24"
                    className={`relative h-[18px] w-[18px] shrink-0 transition duration-200 ${
                      isActive
                        ? "fill-lime-400 drop-shadow-[0_0_6px_rgba(174,212,74,0.45)]"
                        : "fill-current opacity-70 group-hover:fill-lime-300 group-hover:opacity-100 group-hover:drop-shadow-[0_0_8px_rgba(174,212,74,0.65)]"
                    }`}
                  >
                    {s.icon}
                  </svg>
                  <span className="relative min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="text-[13.5px] font-medium">{s.label}</span>
                      {s.optional && (
                        <span className="rounded px-1 py-px text-[9px] uppercase tracking-wide text-white/30 ring-1 ring-white/10">
                          opz
                        </span>
                      )}
                    </span>
                    <span className="block truncate text-[11px] text-white/30">{s.hint}</span>
                  </span>
                </button>
              );
            })}
          </nav>

          {profileName && (
            <div className="mt-3 flex items-center gap-2.5 rounded-xl border border-white/[0.07] bg-black/25 px-3 py-2.5">
              <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-iris-400 to-iris-500 text-[13px] font-bold text-white">
                {profileName.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="truncate text-[12.5px] font-medium text-white/85">{profileName}</p>
                <p className="text-[10.5px] text-white/35">profilo attivo</p>
              </div>
            </div>
          )}
        </div>
      </aside>

      <main className="min-w-0 flex-1 pb-[calc(6.5rem+env(safe-area-inset-bottom))] lg:pb-4">
        {/* Sotto i 1024px la barra laterale sparisce: il logo resta visibile qui. */}
        <div className="mb-4 flex items-center gap-2.5 lg:hidden">
          <BrandMark size={36} />
          <p className="text-[17px] font-bold tracking-tight text-white">Kilo</p>
        </div>
        <div ref={contentRef}>{children}</div>
      </main>

      <MobileNav active={active} onNavigate={onNavigate} />
    </div>
  );
}

/**
 * Barra di navigazione mobile, nello stile delle app (Instagram, WhatsApp):
 * vetro più sfocato, bordi molto arrotondati, e la sezione attiva indicata
 * da una capsula con il contorno intorno all'icona, che scivola da una voce
 * all'altra.
 *
 * Oltre al tocco, si può far scorrere il dito lungo la barra: la capsula
 * segue il dito e la sezione si apre quando lo si solleva. Così si evita di
 * caricare ogni sezione attraversata.
 */
function MobileNav({
  active,
  onNavigate,
}: {
  active: SectionId;
  onNavigate: (id: SectionId) => void;
}) {
  const navRef = useRef<HTMLElement>(null);
  const [preview, setPreview] = useState<SectionId | null>(null);
  const shown = preview ?? active;

  function sectionAt(clientX: number): SectionId {
    const rect = navRef.current!.getBoundingClientRect();
    const i = Math.floor(((clientX - rect.left) / rect.width) * SECTION_ORDER.length);
    return SECTION_ORDER[Math.min(Math.max(i, 0), SECTION_ORDER.length - 1)];
  }

  function track(clientX: number) {
    const id = sectionAt(clientX);
    if (id !== (preview ?? active)) vibrate();
    setPreview(id);
  }

  return (
    <nav
      ref={navRef}
      data-no-swipe
      // Il dito sulla barra non deve far scorrere né ingrandire la pagina.
      style={{ touchAction: "none" }}
      onTouchStart={(e) => setPreview(sectionAt(e.touches[0].clientX))}
      onTouchMove={(e) => track(e.touches[0].clientX)}
      onTouchEnd={(e) => {
        e.preventDefault(); // il tocco è gestito qui: niente clic duplicato
        if (preview && preview !== active) onNavigate(preview);
        setPreview(null);
      }}
      onTouchCancel={() => setPreview(null)}
      className="glass fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-50 flex select-none rounded-[30px] border-white/[0.1] bg-ink-900/70 px-1 py-1.5 backdrop-blur-xl backdrop-saturate-150 lg:hidden"
    >
      {/* Tutte le sezioni, Profilo incluso: escluderlo lo rendeva
          irraggiungibile sotto i 1024px, dove la barra laterale sparisce. */}
      {SECTIONS.map((s) => {
        const isActive = s.id === shown;
        return (
          <button
            key={s.id}
            onClick={() => onNavigate(s.id)}
            aria-label={s.label}
            aria-current={s.id === active ? "page" : undefined}
            className={`-mx-0.5 flex min-w-0 flex-1 flex-col items-center gap-1 rounded-2xl py-1 transition-colors duration-200 ${
              isActive ? "text-white" : "text-white/45"
            }`}
          >
            <span className="relative grid h-8 w-11 place-items-center">
              {isActive && (
                <motion.span
                  layoutId="nav-mobile-active"
                  className="absolute inset-0 rounded-full border border-lime-300/35 bg-white/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.16),0_0_16px_-4px_rgba(174,212,74,0.5)] backdrop-blur-md"
                  transition={{ type: "spring", stiffness: 480, damping: 36 }}
                />
              )}
              <svg
                viewBox="0 0 24 24"
                className={`relative h-[19px] w-[19px] transition duration-200 ${
                  isActive
                    ? "scale-105 fill-lime-400 drop-shadow-[0_0_6px_rgba(174,212,74,0.45)]"
                    : "fill-current"
                }`}
              >
                {s.icon}
              </svg>
            </span>
            <span className="max-w-[calc(100%+4px)] truncate text-[10px] font-medium leading-none tracking-[-0.03em]">{s.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="mb-5 flex flex-wrap items-end justify-between gap-4"
    >
      <div>
        {eyebrow && (
          <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.16em] text-lime-400/70">
            {eyebrow}
          </p>
        )}
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-white lg:text-[30px]">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-white/45">
            {description}
          </p>
        )}
      </div>
      {action}
    </motion.header>
  );
}
