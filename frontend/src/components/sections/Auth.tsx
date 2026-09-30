"use client";

/**
 * Registrazione e accesso.
 *
 * La password non viene mai inviata in chiaro al database: il backend ne
 * salva solo l'hash Argon2. In caso di credenziali errate il messaggio è
 * volutamente identico per email inesistente e password sbagliata —
 * distinguerli permetterebbe di scoprire quali email sono registrate.
 *
 * La registrazione ha due passi: email e password, poi il codice di 6 cifre
 * mandato all'indirizzo, che dimostra che la casella è vera. Con lo stesso
 * codice si sceglie una password nuova da «Password dimenticata?». Se sul
 * server l'invio delle email è spento, la registrazione salta il codice.
 *
 * Mentre Render si sveglia (fino a 40 secondi dopo una pausa) si può già
 * scrivere: l'accesso parte appena il server risponde (`lib/wake.ts`).
 */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, session, type AuthSession } from "@/lib/api";
import { useBackendWake, wakeBackend } from "@/lib/wake";
import { BrandMark } from "@/components/Mascot";

type Mode = "login" | "register" | "reset";
type Step = "form" | "code";

type EmailCode = { sent: boolean; required: boolean; expires_in_minutes: number; resend_after_seconds: number };

export function Auth({ onAuthenticated }: { onAuthenticated: (s: AuthSession) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [step, setStep] = useState<Step>("form");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Secondi prima di poter chiedere un nuovo codice.
  const [resendIn, setResendIn] = useState(0);
  const wake = useBackendWake();

  useEffect(() => {
    if (resendIn <= 0) return;
    const t = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  const emailOk = email.includes("@");
  const passwordOk = password.length >= 8;
  const canSubmit =
    step === "code"
      ? code.length === 6 && (mode !== "reset" || passwordOk)
      : mode === "reset"
        ? emailOk
        : emailOk && passwordOk;

  function go(next: Mode) {
    setMode(next);
    setStep("form");
    setCode("");
    setError(null);
    if (next === "reset") setPassword("");
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await wakeBackend();
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Qualcosa non ha funzionato");
      // Un codice sbagliato si riscrive da capo.
      if (step === "code") setCode("");
    } finally {
      setBusy(false);
    }
  }

  function enter(res: AuthSession) {
    session.set(res.token);
    onAuthenticated(res);
  }

  /** Chiede il codice. Restituisce falso se il server non lo richiede. */
  async function requestCode(): Promise<boolean> {
    const r = await api.post<EmailCode>("/auth/email-code", {
      email,
      purpose: mode === "reset" ? "reset" : "register",
    });
    if (!r.required) return false;
    setStep("code");
    setCode("");
    setResendIn(r.resend_after_seconds || 60);
    return true;
  }

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!canSubmit || busy) return;
    run(async () => {
      if (mode === "login") {
        enter(await api.post<AuthSession>("/auth/login", { email, password }));
      } else if (mode === "register" && step === "form") {
        // Invio email spento sul server: si registra direttamente.
        if (!(await requestCode())) enter(await api.post<AuthSession>("/auth/register", { email, password }));
      } else if (mode === "register") {
        enter(await api.post<AuthSession>("/auth/register", { email, password, code }));
      } else if (step === "form") {
        await requestCode();
      } else {
        enter(await api.post<AuthSession>("/auth/reset-password", { email, code, password }));
      }
    });
  }

  // Alla sesta cifra la registrazione parte da sola: non c'è altro da scrivere.
  useEffect(() => {
    if (mode === "register" && step === "code" && code.length === 6 && !busy) submit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const label =
    wake !== "ready" && busy
      ? "In attesa del server…"
      : busy
        ? "Un attimo…"
        : mode === "login"
          ? "Accedi"
          : step === "form"
            ? "Mandami il codice"
            : mode === "register"
              ? "Crea il mio account"
              : "Cambia password ed entra";

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 pb-10 pt-[calc(2.5rem+env(safe-area-inset-top))]">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="mb-8 text-center"
      >
        <div className="mx-auto mb-4 w-fit">
          <BrandMark size={78} mood="happy" interactive />
        </div>
        <h1 className="text-[26px] font-semibold tracking-tight text-white">
          Kilo
        </h1>
        <p className="mt-1 text-[13.5px] font-medium text-lime-300/80">Allenamento e nutrizione</p>
        <p className="mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-white/45">
          Schede e piani costruiti su parametri presi da fonti verificate — ISSN, EFSA,
          WHO, IOC.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.08 }}
        className="glass overflow-hidden"
      >
        <div className="flex border-b border-white/[0.06]">
          {(["login", "register"] as const).map((m) => {
            const attivo = mode === m || (m === "login" && mode === "reset");
            return (
              <button
                key={m}
                onClick={() => go(m)}
                className={`relative flex-1 px-5 py-3.5 text-[13px] font-medium transition-colors ${
                  attivo ? "text-white" : "text-white/35 hover:text-white/60"
                }`}
              >
                {m === "login" ? "Accedi" : "Crea account"}
                {attivo && (
                  <motion.span
                    layoutId="auth-underline"
                    className="absolute inset-x-8 bottom-0 h-px bg-lime-400"
                  />
                )}
              </button>
            );
          })}
        </div>

        <form onSubmit={submit} className="space-y-4 p-5">
          {mode === "register" && <Steps step={step} />}

          {mode === "reset" && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => (step === "code" ? setStep("form") : go("login"))}
                aria-label="Indietro"
                className="grid h-8 w-8 place-items-center rounded-full bg-white/[0.06] text-white/60 transition hover:text-white"
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.4}>
                  <path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <p className="text-[15px] font-semibold text-white">
                {step === "form" ? "Password dimenticata" : "Nuova password"}
              </p>
            </div>
          )}

          {step === "form" ? (
            <>
              {mode === "reset" && (
                <p className="text-[12.5px] leading-snug text-white/50">
                  Scrivi l&apos;email del tuo account: ti mandiamo un codice per scegliere una password nuova.
                </p>
              )}
              <div>
                <label className="label">Email</label>
                <input
                  type="email"
                  className="input"
                  value={email}
                  autoComplete="email"
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@esempio.it"
                />
              </div>

              {mode !== "reset" && (
                <div>
                  <label className="label">Password</label>
                  <input
                    type="password"
                    className="input"
                    value={password}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="almeno 8 caratteri"
                  />
                  {mode === "register" && password.length > 0 && password.length < 8 && (
                    <p className="mt-1.5 text-[11.5px] text-amber-200/70">
                      Servono almeno 8 caratteri
                    </p>
                  )}
                  {mode === "login" && (
                    <div className="mt-2 text-right">
                      <button
                        type="button"
                        onClick={() => go("reset")}
                        className="text-[12px] text-white/45 underline decoration-white/20 underline-offset-4 transition hover:text-white/75"
                      >
                        Password dimenticata?
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              <div>
                {mode === "register" && <p className="text-[15px] font-semibold text-white">Controlla la tua email</p>}
                <p className="mt-1 text-[12.5px] leading-snug text-white/50">
                  Abbiamo mandato un codice di 6 cifre a{" "}
                  <b className="font-semibold text-white/80">{email.trim().toLowerCase()}</b>. Vale 10 minuti; se non
                  lo trovi, guarda nello spam.
                </p>
              </div>
              <CodeInput value={code} onChange={setCode} error={!!error} />
              <div className="flex items-center justify-between gap-3 text-[12px]">
                {resendIn > 0 ? (
                  <span className="text-white/45">
                    Nuovo codice tra{" "}
                    <b className="font-mono text-white/70">
                      {Math.floor(resendIn / 60)}:{String(resendIn % 60).padStart(2, "0")}
                    </b>
                  </span>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => run(async () => void (await requestCode()))}
                    className="font-medium text-lime-200/85 transition hover:text-lime-100"
                  >
                    Mandami un nuovo codice
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setStep("form");
                    setCode("");
                    setError(null);
                  }}
                  className="text-lime-200/80 underline decoration-lime-400/40 underline-offset-4"
                >
                  Cambia email
                </button>
              </div>
              {mode === "reset" && (
                <div>
                  <label className="label">Password nuova</label>
                  <input
                    type="password"
                    className="input"
                    value={password}
                    autoComplete="new-password"
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="almeno 8 caratteri"
                  />
                  {password.length > 0 && password.length < 8 && (
                    <p className="mt-1.5 text-[11.5px] text-amber-200/70">Servono almeno 8 caratteri</p>
                  )}
                </div>
              )}
            </>
          )}

          {error && (
            <p className="rounded-xl border border-rose-400/20 bg-rose-400/[0.08] px-3.5 py-2.5 text-[12.5px] text-rose-200">
              {error}
            </p>
          )}

          {/* Pulsante compatto e centrato, con la freccia che invita ad
              andare avanti: una barra a tutta larghezza sembrava un campo. */}
          <div className="flex justify-center pt-1">
            <motion.button
              type="submit"
              whileTap={{ scale: 0.96 }}
              className="btn-primary group h-12 rounded-full pl-7 pr-2 text-[14.5px] shadow-[0_10px_30px_-12px_rgba(174,212,74,0.65)]"
              disabled={!canSubmit || busy}
            >
              {label}
              <span className="ml-1 grid h-8 w-8 place-items-center rounded-full bg-ink-900/90 text-lime-300 transition-transform duration-300 group-hover:translate-x-0.5">
                {busy ? (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.6}>
                    <path d="M5 12h13m-5-6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </span>
            </motion.button>
          </div>

          <AnimatePresence>{wake === "waking" && <WakeNotice />}</AnimatePresence>
        </form>
      </motion.div>

      <p className="mt-5 text-center text-[11.5px] leading-relaxed text-white/25">
        I tuoi dati restano nel tuo database. L'agente propone e spiega: non
        sostituisce un medico né un professionista della nutrizione.
      </p>
    </div>
  );
}

function Steps({ step }: { step: Step }) {
  const dot = (attivo: boolean, fatto: boolean, n: ReactNode) => (
    <span
      className={`grid h-5 w-5 place-items-center rounded-full text-[10.5px] font-semibold ${
        attivo ? "bg-lime-400 text-ink-900" : fatto ? "bg-lime-400/20 text-lime-200" : "bg-white/10 text-white/50"
      }`}
    >
      {n}
    </span>
  );
  return (
    <div className="flex items-center gap-2 text-[11.5px] text-white/40">
      {dot(step === "form", step === "code", step === "code" ? "✓" : "1")}
      <span className={step === "form" ? "text-white/80" : ""}>Email e password</span>
      <span className="h-px w-5 bg-white/15" />
      {dot(step === "code", false, "2")}
      <span className={step === "code" ? "text-white/80" : ""}>Codice via email</span>
    </div>
  );
}

/**
 * Sei caselle per il codice. Sotto c'è un solo campo vero, trasparente:
 * così il codice si incolla tutto insieme e iOS lo propone dalla email
 * (`one-time-code`).
 */
function CodeInput({ value, onChange, error }: { value: string; onChange: (v: string) => void; error: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [focus, setFocus] = useState(false);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <div className="relative" onClick={() => ref.current?.focus()}>
      <div className="flex justify-between gap-2" aria-hidden>
        {Array.from({ length: 6 }, (_, i) => {
          const d = value[i];
          const attivo = focus && i === Math.min(value.length, 5);
          return (
            <span
              key={i}
              className={`grid h-14 flex-1 place-items-center rounded-2xl border font-mono text-[24px] font-semibold tabular-nums transition ${
                error && !value
                  ? "border-rose-400/50 bg-rose-400/[0.06]"
                  : attivo
                    ? "border-lime-400/70 bg-lime-400/[0.06] text-white shadow-[0_0_0_3px_rgba(174,212,74,0.15)]"
                    : d
                      ? "border-white/15 bg-black/30 text-white"
                      : "border-white/10 bg-black/20"
              }`}
            >
              {d ?? (attivo ? <span className="h-6 w-px animate-pulse bg-lime-300" /> : "")}
            </span>
          );
        })}
      </div>
      <input
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        inputMode="numeric"
        autoComplete="one-time-code"
        aria-label="Codice di 6 cifre"
        maxLength={6}
        className="absolute inset-0 h-full w-full cursor-text bg-transparent text-[16px] text-transparent caret-transparent outline-none"
      />
    </div>
  );
}

function WakeNotice() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      role="status"
      className="flex items-start gap-3 rounded-2xl border border-iris-400/25 bg-iris-400/[0.07] px-3.5 py-3"
    >
      <span className="relative mt-0.5 grid h-8 w-8 shrink-0 place-items-center">
        <span className="absolute inset-0 animate-ping rounded-full bg-iris-400/20" />
        <span className="h-3 w-3 rounded-full bg-iris-300" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-white">Kilo si sta svegliando…</p>
        <p className="mt-0.5 text-[12px] leading-snug text-white/55">
          Dopo un po&apos; di pausa il server riparte: di solito 20-40 secondi. Puoi già scrivere, l&apos;accesso parte
          appena è pronto.
        </p>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.08]">
          <motion.div
            className="h-full w-1/3 rounded-full bg-gradient-to-r from-iris-400 to-lime-400"
            animate={{ x: ["-100%", "300%"] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          />
        </div>
      </div>
    </motion.div>
  );
}
