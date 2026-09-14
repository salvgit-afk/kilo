"use client";

/**
 * Mascotte e logo della piattaforma: un kettlebell con la fascia da
 * allenamento.
 *
 * È disegnata in SVG e non come immagine, così resta nitida da 18 px (dentro
 * un pulsante) a 96 px (schermata di accesso), e può cambiare espressione:
 * sbatte le palpebre a riposo, "ondeggia" mentre il coach sta pensando.
 * Le animazioni sono in `globals.css` e rispettano `prefers-reduced-motion`.
 */

import { useId } from "react";

export type MascotMood = "idle" | "thinking" | "happy";

export function Mascot({
  size = 40,
  mood = "idle",
  className = "",
}: {
  size?: number;
  mood?: MascotMood;
  className?: string;
}) {
  const id = useId().replace(/:/g, "");

  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={`mascot mascot-${mood} ${className}`}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`${id}-body`} x1="0.2" y1="0" x2="0.55" y2="1">
          <stop offset="0%" stopColor="#cbeb73" />
          <stop offset="100%" stopColor="#7aa81c" />
        </linearGradient>
        <radialGradient id={`${id}-shine`} cx="0.35" cy="0.3" r="0.5">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-handle`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4a5270" />
          <stop offset="100%" stopColor="#262b3b" />
        </linearGradient>
      </defs>

      <g className="mascot-body">
        {/* maniglia */}
        <path
          d="M21 27C18.5 11.5 45.5 11.5 43 27"
          fill="none"
          stroke={`url(#${id}-handle)`}
          strokeWidth="6.5"
          strokeLinecap="round"
        />
        {/* corpo */}
        <path
          d="M32 21.5c11.8 0 19.5 7.7 19.5 18.4C51.5 50.6 43.5 57.5 32 57.5S12.5 50.6 12.5 39.9C12.5 29.2 20.2 21.5 32 21.5Z"
          fill={`url(#${id}-body)`}
        />
        <ellipse cx="24.5" cy="30.5" rx="9.5" ry="6.5" fill={`url(#${id}-shine)`} />
        {/* fascia da allenamento, con il nodo che sventola a destra */}
        <path
          d="M13.2 34.2c5.6-2.7 12-4.1 18.8-4.1s13.2 1.4 18.8 4.1l.4 4.7c-5.8-2.8-12.2-4.2-19.2-4.2s-13.4 1.4-19.2 4.2l.4-4.7Z"
          fill="#6f66b8"
        />
        <path d="M50.4 34.6 57 31.2l-1.4 6.3-4.9-.2Z" fill="#8e86d6" />
        <path d="M50.6 37.6 55.4 41l-5.2.7Z" fill="#6f66b8" />
        {/* occhi */}
        <g className="mascot-eyes">
          <ellipse cx="25.3" cy="44.2" rx="3.2" ry="3.7" fill="#10131c" />
          <ellipse cx="38.7" cy="44.2" rx="3.2" ry="3.7" fill="#10131c" />
          <circle cx="26.4" cy="42.8" r="1.15" fill="#ffffff" />
          <circle cx="39.8" cy="42.8" r="1.15" fill="#ffffff" />
        </g>
        {/* guance */}
        <ellipse cx="20" cy="49.2" rx="2.7" ry="1.5" fill="#ff9a76" opacity="0.5" />
        <ellipse cx="44" cy="49.2" rx="2.7" ry="1.5" fill="#ff9a76" opacity="0.5" />
        {/* bocca */}
        {mood === "thinking" ? (
          <path d="M29.2 51.4h5.6" stroke="#10131c" strokeWidth="1.9" strokeLinecap="round" />
        ) : (
          <path
            d={mood === "happy" ? "M27.6 49.6c2 3.4 6.8 3.4 8.8 0Z" : "M28.2 50.2c1.9 2.4 5.7 2.4 7.6 0"}
            fill={mood === "happy" ? "#10131c" : "none"}
            stroke="#10131c"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
      </g>
    </svg>
  );
}

/** Il logo: la mascotte su una piastrella scura, come icona dell'app. */
export function BrandMark({ size = 40, mood = "idle" }: { size?: number; mood?: MascotMood }) {
  return (
    <div
      className="relative grid shrink-0 place-items-center rounded-[28%] border border-white/10 bg-gradient-to-b from-ink-600 to-ink-800 shadow-lift"
      style={{ width: size, height: size }}
    >
      <Mascot size={Math.round(size * 0.82)} mood={mood} />
    </div>
  );
}
