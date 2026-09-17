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
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
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

          <button type="submit" className="btn-primary w-full" disabled={!canSubmit || busy}>
            {busy
              ? "Un attimo…"
              : mode === "login"
                ? "Accedi"
                : "Crea il mio account"}
          </button>
        </form>
      </motion.div>

      <p className="mt-5 text-center text-[11.5px] leading-relaxed text-white/25">
        I tuoi dati restano nel tuo database. L'agente propone e spiega: non
        sostituisce un medico né un professionista della nutrizione.
      </p>
    </div>
  );
}
