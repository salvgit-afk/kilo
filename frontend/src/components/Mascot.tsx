"use client";

/**
 * Mascotte e logo della piattaforma: un kettlebell con la fascia da
 * allenamento.
 *
 * Disegnata in SVG e non come immagine, così resta nitida da 15 px (dentro
 * un pulsante) a 96 px (schermata di accesso) e può cambiare espressione.
 *
 * Due livelli di dettaglio:
 *  - **da 24 px in su**, resa "soft 3D": luce in alto a sinistra, ombra al
 *    suolo, bordo che riflette il viola dell'interfaccia, maniglia tubolare,
 *    occhi lucidi;
 *  - **sotto i 24 px**, la versione semplice: i dettagli a quella misura si
 *    impasterebbero.
 *
 * Stati (`mood`), legati a ciò che succede nell'app:
 *  - `idle`: respira, sbatte le palpebre e si guarda intorno;
 *  - `thinking`: ondeggia con i puntini, mentre la chat risponde;
 *  - `happy`: un saltello, poi torna a respirare;
 *  - `goal`: obiettivo raggiunto, salta con le scintille (tre volte, poi si calma);
 *  - `remind`: qualcosa da guardare, dà una scossa alla fascia ogni tanto.
 *
 * Con `interactive` reagisce al passaggio del mouse (saltello) e al tocco
 * (si schiaccia). Le animazioni sono in `globals.css`, partono solo dai
 * 28 px in su e rispettano "riduci movimento" del sistema.
 */

import { useId, useRef } from "react";

export type MascotMood = "idle" | "thinking" | "happy" | "goal" | "remind";

const DETAIL_MIN_SIZE = 24;
const ANIMATION_MIN_SIZE = 28;

const MOUTHS: Record<MascotMood, { d: string; filled: boolean }> = {
  idle: { d: "M53 94.2c3.6 4.4 10.4 4.4 14 0", filled: false },
  happy: { d: "M51 92.5c4.5 7 13.5 7 18 0Z", filled: true },
  goal: { d: "M50 91.5c5 8.5 15 8.5 20 0Z", filled: true },
  thinking: { d: "M55 96h10", filled: false },
  remind: { d: "M57.2 95.4a2.8 3.2 0 1 0 5.6 0a2.8 3.2 0 1 0-5.6 0Z", filled: true },
};

export function Mascot({
  size = 40,
  mood = "idle",
  interactive = false,
  className = "",
}: {
  size?: number;
  mood?: MascotMood;
  /** Reagisce a mouse e tocco: solo dove la mascotte è protagonista. */
  interactive?: boolean;
  className?: string;
}) {
  const id = useId().replace(/:/g, "");
  // Il "rimbalzo" al tocco riparte sullo stesso elemento, senza ricrearlo:
  // ricrearlo alla pressione (con una `key`) toglieva dalla pagina l'elemento
  // toccato prima del rilascio, e il browser a volte non generava il click —
  // la chat, per esempio, non si apriva.
  const body = useRef<SVGGElement>(null);
  const squish = () => {
    const el = body.current;
    if (!el) return;
    el.classList.remove("m-squish");
    void el.getBoundingClientRect(); // forza il riavvio dell'animazione
    el.classList.add("m-squish");
  };

  if (size < DETAIL_MIN_SIZE) return <FlatMascot size={size} mood={mood} className={className} />;

  const animated = size >= ANIMATION_MIN_SIZE;
  const bocca = MOUTHS[mood];
  const g = (name: string) => `url(#${id}-${name})`;

  return (
    <svg
      viewBox="0 0 120 120"
      width={size}
      height={size}
      aria-hidden="true"
      onPointerDown={interactive ? squish : undefined}
      className={`mascot mascot-${mood} ${animated ? "mascot-anim" : ""} ${
        interactive ? "mascot-interactive" : ""
      } ${className}`}
    >
      <defs>
        <radialGradient id={`${id}-body`} cx="0.34" cy="0.28" r="0.85">
          <stop offset="0" stopColor="#f1ffc2" />
          <stop offset="0.22" stopColor="#cdee6c" />
          <stop offset="0.6" stopColor="#94c02a" />
          <stop offset="1" stopColor="#4c7009" />
        </radialGradient>
        <linearGradient id={`${id}-rim`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0.55" stopColor="#8e86d6" stopOpacity="0" />
          <stop offset="1" stopColor="#a79ff0" stopOpacity="0.85" />
        </linearGradient>
        <linearGradient id={`${id}-handle`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#6b7497" />
          <stop offset="0.55" stopColor="#3a415a" />
          <stop offset="1" stopColor="#1c2030" />
        </linearGradient>
        <linearGradient id={`${id}-band`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#b3acf5" />
          <stop offset="0.5" stopColor="#7d74cf" />
          <stop offset="1" stopColor="#4f479b" />
        </linearGradient>
        <radialGradient id={`${id}-eye`} cx="0.4" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#2b3246" />
          <stop offset="1" stopColor="#05060a" />
        </radialGradient>
        <radialGradient id={`${id}-spec`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.9" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <filter id={`${id}-soft`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" />
        </filter>
        <filter id={`${id}-cheek`}>
          <feGaussianBlur stdDeviation="1" />
        </filter>
        <clipPath id={`${id}-clip`}>
          <path d={BODY} />
        </clipPath>
      </defs>

      {/* ombra al suolo: resta ferma mentre il corpo salta */}
      <ellipse className="m-shadow" cx="60" cy="110" rx="30" ry="5.5" fill="#000" opacity="0.45" filter={g("soft")} />

      <g
        ref={body}
        className="m-body"
        onAnimationEnd={(e) => e.animationName === "mascot-squish" && e.currentTarget.classList.remove("m-squish")}
      >
        {/* maniglia tubolare con il riflesso */}
        <path d="M39 52C33 20 87 20 81 52" fill="none" stroke={g("handle")} strokeWidth="12.5" strokeLinecap="round" />
        <path d="M39.5 48C35 25 85 25 80.5 48" fill="none" stroke="#9aa3c7" strokeOpacity="0.45" strokeWidth="2.4" strokeLinecap="round" />
        {/* corpo, bordo viola riflesso e ombra sotto la fascia */}
        <path d={BODY} fill={g("body")} />
        <g clipPath={g("clip")}>
          <path d={BODY} fill="none" stroke={g("rim")} strokeWidth="5" />
          <path d="M20 70c12-5 26-8 40-8s28 3 40 8v14c-12-5-26-8-40-8s-28 3-40 8Z" fill="#23380a" opacity="0.35" filter={g("soft")} />
        </g>
        {/* fascia con il nodo che sventola */}
        <path d="M24.8 63.8c10.6-5.1 22.6-7.7 35.2-7.7s24.6 2.6 35.2 7.7l.7 8.8C85 67.4 73 64.8 60 64.8S35 67.4 24.1 72.6l.7-8.8Z" fill={g("band")} />
        <path d="M25.4 64.6c10.4-4.8 22.2-7.3 34.6-7.3s24.2 2.5 34.6 7.3" fill="none" stroke="#d6d1ff" strokeOpacity="0.55" strokeWidth="1.1" />
        <g className="m-knot">
          <path d="M94.5 64.6 107.2 58.2l-2.7 11.8-9.2-.4Z" fill={g("band")} />
          <path d="M94.8 70.4 103.8 76.8l-9.8 1.3Z" fill="#5a52a8" />
        </g>
        {/* riflesso lucido */}
        <ellipse cx="45" cy="54" rx="13" ry="7.5" fill={g("spec")} transform="rotate(-24 45 54)" opacity="0.85" />
        <circle cx="38.5" cy="52" r="2.4" fill="#fff" opacity="0.95" />
        {/* occhi: ad arco quando è felicissimo */}
        {mood === "goal" ? (
          <g>
            <path d="M41 84c3.5-5.5 9.5-5.5 13 0" fill="none" stroke="#10131c" strokeWidth="3.4" strokeLinecap="round" />
            <path d="M66 84c3.5-5.5 9.5-5.5 13 0" fill="none" stroke="#10131c" strokeWidth="3.4" strokeLinecap="round" />
          </g>
        ) : (
          <g className="m-eyes">
            <ellipse cx="47.4" cy="83" rx="6.2" ry="7.1" fill={g("eye")} />
            <ellipse cx="72.6" cy="83" rx="6.2" ry="7.1" fill={g("eye")} />
            <circle cx="49.6" cy="80.2" r="2.3" fill="#fff" />
            <circle cx="74.8" cy="80.2" r="2.3" fill="#fff" />
            <circle cx="45.6" cy="86" r="0.9" fill="#fff" opacity="0.7" />
            <circle cx="70.8" cy="86" r="0.9" fill="#fff" opacity="0.7" />
          </g>
        )}
        <ellipse cx="37.5" cy="92.5" rx="5.3" ry="3" fill="#ff8f6b" opacity="0.55" filter={g("cheek")} />
        <ellipse cx="82.5" cy="92.5" rx="5.3" ry="3" fill="#ff8f6b" opacity="0.55" filter={g("cheek")} />
        <path
          d={bocca.d}
          fill={bocca.filled ? "#10131c" : "none"}
          stroke="#10131c"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      {mood === "thinking" && (
        <g className="m-dots" fill="#cbc6f1">
          <circle cx="92" cy="30" r="3.2" />
          <circle cx="102" cy="22" r="3.2" />
          <circle cx="112" cy="14" r="3.2" />
        </g>
      )}
      {mood === "goal" && (
        <g className="m-sparks">
          <path d="M16 30l2.5 6 6 2.5-6 2.5-2.5 6-2.5-6-6-2.5 6-2.5Z" fill="#aed44a" />
          <path d="M102 20l2 4.8 4.8 2-4.8 2-2 4.8-2-4.8-4.8-2 4.8-2Z" fill="#aed44a" />
          <path d="M100 96l1.6 3.8 3.8 1.6-3.8 1.6-1.6 3.8-1.6-3.8-3.8-1.6 3.8-1.6Z" fill="#cbc6f1" />
        </g>
      )}
    </svg>
  );
}

const BODY =
  "M60 40c22 0 36.5 14.5 36.5 34.5 0 20-15 33-36.5 33s-36.5-13-36.5-33C23.5 54.5 38 40 60 40Z";

/** Versione semplice per i formati piccoli (pulsanti, etichette). */
function FlatMascot({ size, mood, className }: { size: number; mood: MascotMood; className: string }) {
  const id = useId().replace(/:/g, "");
  const felice = mood === "happy" || mood === "goal";
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={`mascot ${className}`} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-body`} x1="0.2" y1="0" x2="0.55" y2="1">
          <stop offset="0%" stopColor="#cbeb73" />
          <stop offset="100%" stopColor="#7aa81c" />
        </linearGradient>
        <linearGradient id={`${id}-handle`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4a5270" />
          <stop offset="100%" stopColor="#262b3b" />
        </linearGradient>
      </defs>
      <path d="M21 27C18.5 11.5 45.5 11.5 43 27" fill="none" stroke={`url(#${id}-handle)`} strokeWidth="6.5" strokeLinecap="round" />
      <path
        d="M32 21.5c11.8 0 19.5 7.7 19.5 18.4C51.5 50.6 43.5 57.5 32 57.5S12.5 50.6 12.5 39.9C12.5 29.2 20.2 21.5 32 21.5Z"
        fill={`url(#${id}-body)`}
      />
      <path
        d="M13.2 34.2c5.6-2.7 12-4.1 18.8-4.1s13.2 1.4 18.8 4.1l.4 4.7c-5.8-2.8-12.2-4.2-19.2-4.2s-13.4 1.4-19.2 4.2l.4-4.7Z"
        fill="#6f66b8"
      />
      <path d="M50.4 34.6 57 31.2l-1.4 6.3-4.9-.2Z" fill="#8e86d6" />
      <ellipse cx="25.3" cy="44.2" rx="3.2" ry="3.7" fill="#10131c" />
      <ellipse cx="38.7" cy="44.2" rx="3.2" ry="3.7" fill="#10131c" />
      <path
        d={felice ? "M27.6 49.6c2 3.4 6.8 3.4 8.8 0Z" : "M28.2 50.2c1.9 2.4 5.7 2.4 7.6 0"}
        fill={felice ? "#10131c" : "none"}
        stroke="#10131c"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Il logo: la mascotte su una piastrella scura, come icona dell'app. */
export function BrandMark({
  size = 40,
  mood = "idle",
  interactive = false,
}: {
  size?: number;
  mood?: MascotMood;
  interactive?: boolean;
}) {
  return (
    <div
      className="relative grid shrink-0 place-items-center rounded-[28%] border border-white/10 bg-gradient-to-b from-ink-600 to-ink-800 shadow-lift"
      style={{ width: size, height: size }}
    >
      <Mascot size={Math.round(size * 0.86)} mood={mood} interactive={interactive} />
    </div>
  );
}
