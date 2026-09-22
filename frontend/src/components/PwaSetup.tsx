"use client";

/**
 * Kilo come app: registra il service worker e, su iPhone da Safari, spiega
 * una volta come aggiungerlo alla schermata Home (iOS non ha il pulsante
 * «Installa» di Android).
 */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { isIos, isStandalone } from "@/lib/push";

const HINT_KEY = "kilo-install-ios-nascosto";

function readHint(): string | null {
  try {
    return localStorage.getItem(HINT_KEY);
  } catch {
    return null;
  }
}

export function PwaSetup() {
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
      // Tocco su una notifica con l'app già aperta: il service worker dice
      // quale sezione mostrare, la pagina la apre.
      const onMessage = (e: MessageEvent) => {
        if (e.data?.type === "kilo:open-section") {
          window.dispatchEvent(new CustomEvent("kilo:open-section", { detail: e.data.section }));
        }
      };
      navigator.serviceWorker.addEventListener("message", onMessage);
      return () => navigator.serviceWorker.removeEventListener("message", onMessage);
    }
  }, []);

  useEffect(() => {
    if (!isIos() || isStandalone() || readHint()) return;
    // Solo Safari può aggiungere alla Home: Chrome e gli altri su iPhone no.
    const safari = !/CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
    if (!safari) return;
    const t = setTimeout(() => setIosHint(true), 2500);
    return () => clearTimeout(t);
  }, []);

  function close() {
    setIosHint(false);
    try {
      localStorage.setItem(HINT_KEY, "1");
    } catch {
      /* navigazione privata: ricomparirà, pazienza */
    }
  }

  return (
    <AnimatePresence>
      {iosHint && (
        <motion.div
          role="dialog"
          aria-label="Installa Kilo sull'iPhone"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ type: "spring", stiffness: 320, damping: 30 }}
          className="fixed inset-x-3 z-[60] mx-auto max-w-md rounded-3xl border border-white/10 bg-ink-800/95 p-4 shadow-2xl shadow-black/50 backdrop-blur-xl"
          style={{ bottom: "calc(env(safe-area-inset-bottom) + 96px)" }}
        >
          <div className="flex items-start gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/icons/icon-192.png" alt="" className="h-11 w-11 shrink-0 rounded-xl" />
            <div className="min-w-0 flex-1">
              <p className="text-[14px] font-semibold text-white">Usa Kilo come un&apos;app</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-white/60">
                Tocca{" "}
                <span className="inline-flex translate-y-[3px] items-center text-sky-300" aria-label="Condividi">
                  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-current">
                    <path d="M12 2 7.5 6.5l1.4 1.4L11 5.8V15h2V5.8l2.1 2.1 1.4-1.4L12 2Zm-7 9v10h14V11h-4v2h2v6H7v-6h2v-2H5Z" />
                  </svg>
                </span>{" "}
                <span className="font-medium text-white/80">Condividi</span> in basso, poi{" "}
                <span className="font-medium text-white/80">«Aggiungi alla schermata Home»</span>. Si apre a
                tutto schermo e può mandarti i promemoria.
              </p>
            </div>
            <button
              onClick={close}
              aria-label="Chiudi"
              className="-mr-1 -mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full text-white/45 transition hover:bg-white/[0.06] hover:text-white"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                <path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3 1.4 1.4Z" />
              </svg>
            </button>
          </div>
          <button onClick={close} className="btn-ghost mt-3 w-full justify-center py-2.5 text-[13px]">
            Ho capito
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
