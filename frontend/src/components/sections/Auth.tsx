"use client";

/**
 * Registrazione e accesso.
 *
 * La password non viene mai inviata in chiaro al database: il backend ne
 * salva solo l'hash Argon2. In caso di credenziali errate il messaggio è
 * volutamente identico per email inesistente e password sbagliata —
 * distinguerli permetterebbe di scoprire quali email sono registrate.
 */

import { motion } from "framer-motion";
import { useState } from "react";
import { api, session, type AuthSession } from "@/lib/api";
import { BrandMark } from "@/components/Mascot";

export function Auth({ onAuthenticated }: { onAuthenticated: (s: AuthSession) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = email.includes("@") && password.length >= 8;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<AuthSession>(`/auth/${mode}`, { email, password });
      session.set(res.token);
      onAuthenticated(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Qualcosa non ha funzionato");
      setBusy(false);
    }
  }

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
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`relative flex-1 px-5 py-3.5 text-[13px] font-medium transition-colors ${
                mode === m ? "text-white" : "text-white/35 hover:text-white/60"
              }`}
            >
              {m === "login" ? "Accedi" : "Crea account"}
              {mode === m && (
                <motion.span
                  layoutId="auth-underline"
                  className="absolute inset-x-8 bottom-0 h-px bg-lime-400"
                />
              )}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-4 p-5">
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
          </div>

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
              {busy ? "Un attimo…" : mode === "login" ? "Accedi" : "Crea il mio account"}
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
        </form>
      </motion.div>

      <p className="mt-5 text-center text-[11.5px] leading-relaxed text-white/25">
        I tuoi dati restano nel tuo database. L'agente propone e spiega: non
        sostituisce un medico né un professionista della nutrizione.
      </p>
    </div>
  );
}
