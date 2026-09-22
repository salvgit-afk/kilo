"use client";

/**
 * Promemoria sul telefono: attivazione, ora e notifica di prova.
 *
 * Il permesso si chiede solo dal tocco sull'interruttore, mai all'apertura
 * della pagina: un popup non richiesto viene negato, e dopo un «no» il
 * browser non permette di chiederlo di nuovo.
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { Stepper, Toggle } from "@/components/controls";
import { Notice } from "@/components/ui";
import {
  DEFAULT_HOUR,
  HOURS,
  disablePush,
  enablePush,
  pushState,
  sendTestPush,
  setPushHour,
  type PushState,
} from "@/lib/push";

const SPIEGAZIONI: Partial<Record<PushState, string>> = {
  unsupported: "Questo browser non supporta le notifiche. Su Android usa Chrome, su iPhone Safari.",
  "needs-install":
    "Su iPhone le notifiche arrivano solo dall'app: in Safari tocca Condividi → «Aggiungi alla schermata Home», poi apri Kilo dall'icona e torna qui.",
  "server-off": "Le notifiche non sono ancora attive sul server.",
  denied:
    "Hai bloccato le notifiche per Kilo. Riattivale dalle impostazioni del telefono (o del sito, nel browser) e torna qui.",
};

export function PushSettings() {
  const [state, setState] = useState<PushState | null>(null);
  const [hour, setHour] = useState(DEFAULT_HOUR);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    pushState()
      .then((s) => {
        setState(s.state);
        setHour(s.hour);
      })
      .catch(() => setState("unsupported"));
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function toggle(on: boolean) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (on) {
        const s = await enablePush(hour);
        setState(s);
        if (s === "on") setMessage("Fatto: ti scrivo solo se a quell'ora manca qualcosa.");
      } else {
        await disablePush();
        setState("off");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Non sono riuscito ad attivare le notifiche.");
    } finally {
      setBusy(false);
    }
  }

  function changeHour(h: number) {
    setHour(h);
    setMessage(null);
    // Si salva quando si smette di toccare, non a ogni tocco.
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setPushHour(h).catch(() => setError("Non sono riuscito a salvare l'ora: riprova."));
    }, 700);
  }

  async function test() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await sendTestPush();
      setMessage("Inviata: dovrebbe arrivare entro qualche secondo.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 410) setState("off");
      setError(e instanceof Error ? e.message : "Invio non riuscito.");
    } finally {
      setBusy(false);
    }
  }

  if (state === null) {
    return <p className="text-[12.5px] text-white/40">Controllo le notifiche…</p>;
  }

  const spiegazione = SPIEGAZIONI[state];
  if (spiegazione) {
    return <p className="text-[12.5px] leading-relaxed text-white/55">{spiegazione}</p>;
  }

  const on = state === "on";
  return (
    <div className="space-y-3">
      <Toggle
        checked={on}
        onChange={(v) => !busy && toggle(v)}
        label="Promemoria della sera"
        hint="Integratori, allenamento del giorno e diario, solo se non li hai ancora segnati."
      />
      {on && (
        <>
          <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-2.5">
            <span className="text-[13.5px] font-medium text-white/85">Alle</span>
            <Stepper
              compact
              value={hour}
              onChange={changeHour}
              min={HOURS[0]}
              max={HOURS[HOURS.length - 1]}
              label="ora del promemoria"
              format={(h) => `${h}:00`}
            />
          </div>
          <button className="btn-ghost w-full justify-center" disabled={busy} onClick={test}>
            Mandami una notifica di prova
          </button>
        </>
      )}
      {message && <p className="text-[12px] leading-relaxed text-lime-200/80">{message}</p>}
      {error && <Notice>{error}</Notice>}
      <p className="text-[11.5px] leading-relaxed text-white/30">
        Vale per questo dispositivo. L&apos;orario è indicativo: il promemoria può arrivare con
        qualche minuto di ritardo.
      </p>
    </div>
  );
}
