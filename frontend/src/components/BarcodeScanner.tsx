"use client";

/**
 * Scanner del codice a barre con la fotocamera posteriore.
 *
 * - Dove esiste (Chrome, Android) usa l'API nativa `BarcodeDetector`: niente
 *   librerie da scaricare.
 * - Altrove (Safari su iPhone) carica ZXing solo al momento, con un import
 *   dinamico: chi non scansiona non scarica nulla.
 * - Sempre disponibile il campo per digitare il codice: su computer senza
 *   fotocamera, o se il codice è rovinato.
 *
 * Si cercano solo i formati dei prodotti alimentari (EAN-13, EAN-8, UPC).
 */

import { useEffect, useRef, useState } from "react";

type Detector = { detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]> };
type DetectorCtor = new (options: { formats: string[] }) => Detector;

const FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];

function cameraError(e: unknown): string {
  const nome = e instanceof DOMException ? e.name : "";
  if (nome === "NotAllowedError") {
    return "Permesso della fotocamera negato: abilitalo nelle impostazioni del browser, oppure digita il codice qui sotto.";
  }
  if (nome === "NotFoundError" || nome === "OverconstrainedError") {
    return "Nessuna fotocamera disponibile su questo dispositivo: digita il codice qui sotto.";
  }
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "La fotocamera funziona solo su una connessione sicura (https).";
  }
  return "Non riesco ad aprire la fotocamera: digita il codice qui sotto.";
}

export function BarcodeScanner({
  onDetected,
  busy = false,
}: {
  onDetected: (code: string) => void;
  busy?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [typed, setTyped] = useState("");
  const detectedRef = useRef(onDetected);
  detectedRef.current = onDetected;

  useEffect(() => {
    let stopped = false;
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    let zxingControls: { stop: () => void } | null = null;

    const found = (code: string) => {
      if (stopped) return;
      stopped = true;
      try {
        navigator.vibrate?.(40);
      } catch {
        /* vibrazione non supportata */
      }
      detectedRef.current(code);
    };

    async function start() {
      const video = videoRef.current;
      if (!video) return;
      if (!navigator.mediaDevices?.getUserMedia) {
        setError(cameraError(null));
        return;
      }
      const Native = (window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector;
      try {
        if (Native) {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: false,
          });
          if (stopped) return;
          video.srcObject = stream;
          await video.play();
          setReady(true);
          const detector = new Native({ formats: FORMATS });
          timer = setInterval(async () => {
            if (stopped || video.readyState < 2) return;
            try {
              const codes = await detector.detect(video);
              if (codes[0]?.rawValue) found(codes[0].rawValue);
            } catch {
              /* fotogramma non leggibile: si riprova al prossimo */
            }
          }, 250);
        } else {
          const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([
            import("@zxing/browser"),
            import("@zxing/library"),
          ]);
          if (stopped) return;
          const hints = new Map();
          hints.set(DecodeHintType.POSSIBLE_FORMATS, [
            BarcodeFormat.EAN_13,
            BarcodeFormat.EAN_8,
            BarcodeFormat.UPC_A,
            BarcodeFormat.UPC_E,
          ]);
          const reader = new BrowserMultiFormatReader(hints, { delayBetweenScanAttempts: 200 });
          zxingControls = await reader.decodeFromConstraints(
            { video: { facingMode: { ideal: "environment" } }, audio: false },
            video,
            (result) => {
              if (result) found(result.getText());
            }
          );
          if (stopped) zxingControls.stop();
          else setReady(true);
        }
      } catch (e) {
        if (!stopped) setError(cameraError(e));
      }
    }

    start();
    return () => {
      stopped = true;
      if (timer) clearInterval(timer);
      zxingControls?.stop();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const digits = typed.replace(/\D/g, "");

  return (
    <div className="space-y-3">
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-2xl border border-white/10 bg-black/60">
        <video ref={videoRef} playsInline muted className="h-full w-full object-cover" />
        {!error && (
          <>
            {/* Riquadro di mira: il codice va tenuto orizzontale al centro. */}
            <div className="pointer-events-none absolute inset-x-[12%] top-1/2 h-[34%] -translate-y-1/2 rounded-xl border-2 border-lime-400/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]">
              <div className="absolute inset-x-3 top-1/2 h-px -translate-y-1/2 animate-pulse bg-lime-400/80" />
            </div>
            <p className="absolute inset-x-0 bottom-3 text-center text-[12px] text-white/80">
              {busy ? "Cerco il prodotto…" : ready ? "Inquadra il codice a barre" : "Apro la fotocamera…"}
            </p>
          </>
        )}
        {error && (
          <div className="absolute inset-0 grid place-items-center p-6 text-center">
            <p className="text-[13px] leading-relaxed text-white/70">{error}</p>
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (digits.length >= 8) onDetected(digits);
        }}
        className="flex gap-2"
      >
        <input
          className="input font-mono tracking-wider"
          inputMode="numeric"
          placeholder="Oppure digita il codice (8-14 cifre)"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <button type="submit" className="btn-primary shrink-0 px-4" disabled={busy || digits.length < 8}>
          Cerca
        </button>
      </form>
    </div>
  );
}
