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
  readPushSettings,
  savePushSettings,
  sendTestPush,
  setPushHour,
  type PushSettings as Settings,
  type PushState,
} from "@/lib/push";

/** Le categorie, nell'ordine in cui si incontrano nell'app. */
const CATEGORIE: { campo: keyof Settings; label: string; hint: string }[] = [
  { campo: "training", label: "Allenamento", hint: "Ora di allenarsi, carichi da aumentare, scheda da variare" },
  { campo: "supplements", label: "Integratori", hint: "Al momento giusto: dopo l'allenamento o con un pasto" },
  { campo: "diary", label: "Diario", hint: "Se smetti di segnare i pasti, e le proteine fuori range" },
  { campo: "recipes", label: "Ricette", hint: "Idee quando ti mancano proteine, e ricette salvate e mai provate" },
  { campo: "progress", label: "Progressi", hint: "Il lunedì, com'è andata la settimana" },
];

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
  const [settings, setSettings] = useState<Settings | null>(null);

  useEffect(() => {
    pushState()
      .then((s) => {
        setState(s.state);
        setHour(s.hour);
        if (s.state === "on") readPushSettings().then(setSettings).catch(() => undefined);
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
        if (s === "on") {
          setMessage("Fatto: ti scrivo solo quando serve, al massimo tre volte al giorno.");
          setSettings(await readPushSettings());
        }
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

  async function aggiorna(cambio: Partial<Settings>) {
    if (!settings) return;
    const nuove = { ...settings, ...cambio };
    setSettings(nuove);
    setMessage(null);
    try {
      // `effective_gym_hour` la calcola il server: si manda solo ciò che si sceglie.
      setSettings(
        await savePushSettings({
          training: nuove.training,
          supplements: nuove.supplements,
          diary: nuove.diary,
          recipes: nuove.recipes,
          progress: nuove.progress,
          meal_prep: nuove.meal_prep,
          gym_hour: nuove.gym_hour,
        })
      );
    } catch {
      setError("Non sono riuscito a salvare la scelta: riprova.");
      setSettings(settings);
    }
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
      {on && settings && (
        <>
          <div className="space-y-2">
            <p className="text-[11px] uppercase tracking-wider text-white/35">Cosa ti mando</p>
            {CATEGORIE.map((c) => (
              <Toggle
                key={c.campo}
                checked={Boolean(settings[c.campo])}
                onChange={(v) => aggiorna({ [c.campo]: v } as Partial<Settings>)}
                label={c.label}
                hint={c.hint}
              />
            ))}
            <Toggle
              checked={settings.meal_prep}
              onChange={(v) => aggiorna({ meal_prep: v })}
              label="Ricette della domenica"
              hint="Due ricette da cucinare in anticipo per la settimana"
            />
          </div>

          {settings.training && (
            <div className="space-y-2 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-medium text-white/85">Promemoria dell'allenamento</p>
                  <p className="mt-0.5 text-[11.5px] leading-snug text-white/40">
                    {settings.gym_hour === null
                      ? `Alle ${settings.effective_gym_hour}:00, l'ora in cui ti alleni di solito`
                      : "Ora scelta da te"}
                  </p>
                </div>
                {settings.gym_hour === null ? (
                  <button
                    className="btn-ghost shrink-0 px-3 py-2 text-[12.5px]"
                    onClick={() => aggiorna({ gym_hour: settings.effective_gym_hour })}
                  >
                    Scegli tu
                  </button>
                ) : (
                  <button
                    className="btn-ghost shrink-0 px-3 py-2 text-[12.5px]"
                    onClick={() => aggiorna({ gym_hour: null })}
                  >
                    Automatico
                  </button>
                )}
              </div>
              {settings.gym_hour !== null && (
                <Stepper
                  compact
                  value={settings.gym_hour}
                  onChange={(h) => aggiorna({ gym_hour: h })}
                  min={HOURS[0]}
                  max={HOURS[HOURS.length - 1]}
                  label="ora dell'allenamento"
                  format={(h) => `${h}:00`}
                />
              )}
            </div>
          )}

          <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-2.5">
            <span className="text-[13.5px] font-medium text-white/85">Riepilogo della sera</span>
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
        L&apos;interruttore vale per questo dispositivo, le scelte qui sotto per il tuo account.
        Al massimo tre notifiche al giorno, e gli orari sono indicativi: possono arrivare con
        qualche minuto di ritardo.
      </p>
    </div>
  );
}
