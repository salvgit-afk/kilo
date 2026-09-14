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
import type { ReactNode } from "react";
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

      <main className="min-w-0 flex-1 pb-24 lg:pb-4">
        {/* Sotto i 1024px la barra laterale sparisce: il logo resta visibile qui. */}
        <div className="mb-4 flex items-center gap-2.5 lg:hidden">
          <BrandMark size={36} />
          <p className="text-[17px] font-bold tracking-tight text-white">Kilo</p>
        </div>
        {children}
      </main>

      {/* Navigazione mobile: le stesse sezioni, raggiungibili col pollice. */}
      <nav className="glass fixed inset-x-3 bottom-3 z-50 flex justify-between px-1.5 py-1.5 lg:hidden">
        {/* Tutte le sezioni, Profilo incluso: escluderlo lo rendeva
            irraggiungibile sotto i 1024px, dove la barra laterale sparisce. */}
        {SECTIONS.map((s) => {
          const isActive = s.id === active;
          return (
            <button
              key={s.id}
              onClick={() => onNavigate(s.id)}
              className={`relative flex flex-1 flex-col items-center gap-0.5 rounded-lg px-0.5 py-2 ${
                isActive ? "text-lime-400" : "text-white/45"
              }`}
            >
              <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current">
                {s.icon}
              </svg>
              <span className="text-[9px] font-medium leading-none">{s.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
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
