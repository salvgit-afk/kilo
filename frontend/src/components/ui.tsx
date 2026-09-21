"use client";

/**
 * Componenti visivi condivisi.
 *
 * Due scelte ricorrenti in tutta l'interfaccia:
 *
 *  - le **avvertenze** dell'agente hanno un trattamento grafico distinto e
 *    non vengono mai compresse in testo secondario: fanno parte del
 *    consiglio, non sono una nota a piè di pagina;
 *  - ogni consiglio mostra **da quali documenti** proviene, perché
 *    l'ispezionabilità è un requisito del progetto e non un dettaglio.
 */

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { EVIDENCE_LABELS, TAG_LABELS } from "@/lib/api";

export function Card({
  children,
  className = "",
  hover = false,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  delay?: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
      className={`glass sheen ${hover ? "glass-hover" : ""} ${className}`}
    >
      {children}
    </motion.section>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 border-b border-white/[0.06] px-4 py-4 sm:px-5">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-tight text-white">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[12.5px] text-white/45">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/** Anello di progresso: comunica "quanto manca" meglio di una barra piatta. */
export function ProgressRing({
  value,
  size = 116,
  stroke = 9,
  label,
  sublabel,
  tone = "lime",
}: {
  value: number;
  size?: number;
  stroke?: number;
  label: string;
  sublabel?: string;
  tone?: "lime" | "iris" | "amber";
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(value, 1.25));
  const offset = circumference * (1 - Math.min(clamped, 1));
  const over = clamped > 1.02;

  const colors = {
    lime: ["#aed44a", "#7ea82a"],
    iris: ["#948cd8", "#6f66b8"],
    amber: ["#e0a93a", "#c68a1e"],
  }[over ? "amber" : tone];

  const gradientId = `ring-${tone}-${over ? "over" : "ok"}-${size}`;

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={colors[0]} />
            <stop offset="100%" stopColor={colors[1]} />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className="absolute grid place-items-center text-center">
        <span className="text-[19px] font-semibold leading-none tracking-tight text-white">
          {label}
        </span>
        {sublabel && <span className="mt-1 text-[10.5px] text-white/40">{sublabel}</span>}
      </div>
    </div>
  );
}

export function StatBar({
  label,
  value,
  target,
  unit = "g",
  tone = "iris",
}: {
  label: string;
  value: number;
  target: number;
  unit?: string;
  tone?: "lime" | "iris" | "amber" | "rose";
}) {
  const pct = target > 0 ? value / target : 0;
  const over = pct > 1.02;
  const colors = {
    lime: "from-lime-400 to-lime-500",
    iris: "from-iris-400 to-iris-500",
    amber: "from-amber-300 to-amber-500",
    rose: "from-rose-400 to-rose-500",
  }[over ? "amber" : tone];

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-[12px] text-white/55">{label}</span>
        <span className="font-mono text-[12px] tabular-nums text-white/80">
          {Math.round(value)}
          <span className="text-white/30">
            /{Math.round(target)}
            {unit}
          </span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className={`h-full rounded-full bg-gradient-to-r ${colors}`}
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(pct, 1) * 100}%` }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
}

/** Avvertenza dell'agente: deve restare visivamente distinta dal consiglio. */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice">
      <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0 fill-amber-300/90">
        <path d="M12 2 1 21h22L12 2Zm0 6 6.5 11h-13L12 8Zm-1 3v4h2v-4h-2Zm0 5v2h2v-2h-2Z" />
      </svg>
      <p>{children}</p>
    </div>
  );
}

/** Le fonti che hanno prodotto un consiglio. */
export function SourceTags({ tags }: { tags: string[] }) {
  if (!tags.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10.5px] uppercase tracking-wider text-white/25">Fonti</span>
      {tags.map((t) => (
        <span key={t} className="pill border border-white/10 bg-white/[0.05] text-white/55">
          {TAG_LABELS[t] ?? t}
        </span>
      ))}
    </div>
  );
}

const EVIDENCE_STYLES: Record<string, string> = {
  strong: "border-lime-400/25 bg-lime-400/10 text-lime-200",
  moderate: "border-iris-400/25 bg-iris-400/10 text-iris-200",
  weak: "border-amber-300/25 bg-amber-300/10 text-amber-100",
  unknown: "border-white/12 bg-white/[0.05] text-white/50",
};

export function EvidenceBadge({ evidence }: { evidence: string }) {
  const dots = { strong: 3, moderate: 2, weak: 1, unknown: 0 }[evidence] ?? 0;
  return (
    <span className={`pill border ${EVIDENCE_STYLES[evidence] ?? EVIDENCE_STYLES.unknown}`}>
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-1.5 rounded-full ${
              i < dots ? "bg-current" : "bg-current opacity-25"
            }`}
          />
        ))}
      </span>
      {EVIDENCE_LABELS[evidence] ?? evidence}
    </span>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="grid place-items-center px-6 py-14 text-center">
      <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.03]">
        <svg viewBox="0 0 24 24" className="h-5 w-5 fill-white/25">
          <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 15h-2v-2h2v2Zm0-4h-2V7h2v6Z" />
        </svg>
      </div>
      <p className="text-sm text-white/60">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-[12.5px] text-white/35">{hint}</p>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 px-6 py-10 text-white/45">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/15 border-t-lime-400" />
      {label && <span className="text-[13px]">{label}</span>}
    </div>
  );
}
