"use client";

/**
 * La forma dell'app mentre si carica.
 *
 * Render gratuito si addormenta: la prima richiesta dopo una pausa può
 * impiegare fino a un minuto. Invece di una rotellina su uno schermo vuoto si
 * mostra lo scheletro di ciò che sta arrivando (intestazione, card, barra in
 * basso), come fanno le app moderne: l'attesa sembra più corta e, quando i
 * dati arrivano, niente salta di posto. Se l'attesa si allunga, una riga
 * spiega il perché.
 */

import { useEffect, useState } from "react";

function Bone({ className = "" }: { className?: string }) {
  return <div className={`skeleton rounded-xl ${className}`} />;
}

export function AppSkeleton() {
  // La spiegazione compare solo se l'attesa è lunga: a server sveglio lo
  // scheletro dura un attimo e una scritta lampeggiante sarebbe rumore.
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 2500);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      role="status"
      aria-label="Caricamento di Kilo"
      className="mx-auto flex min-h-screen w-full max-w-[1400px] gap-6 px-4 pb-5 pt-[calc(1.25rem+env(safe-area-inset-top))] lg:px-7"
    >
      <aside className="hidden w-[236px] shrink-0 flex-col gap-3 lg:flex">
        <div className="flex items-center gap-3 px-2 pb-4">
          <Bone className="h-11 w-11 rounded-2xl" />
          <Bone className="h-5 w-20" />
        </div>
        {Array.from({ length: 7 }).map((_, i) => (
          <Bone key={i} className="h-10 w-full" />
        ))}
      </aside>

      <main className="min-w-0 flex-1 space-y-4 pb-[calc(6.5rem+env(safe-area-inset-bottom))]">
        <div className="flex items-center gap-3 lg:hidden">
          <Bone className="h-11 w-11 rounded-2xl" />
          <Bone className="h-5 w-20" />
        </div>
        <div className="space-y-3 pt-1">
          <Bone className="h-3 w-32" />
          <Bone className="h-8 w-64 max-w-full" />
          <Bone className="h-4 w-48 max-w-full" />
        </div>
        <div className="glass space-y-3 p-4">
          <Bone className="h-5 w-40" />
          <Bone className="h-3 w-full" />
          <Bone className="h-3 w-5/6" />
          <div className="flex gap-2 pt-1">
            <Bone className="h-9 w-24 rounded-full" />
            <Bone className="h-9 w-24 rounded-full" />
          </div>
        </div>
        <div className="glass space-y-3 p-4">
          <div className="flex items-center gap-3">
            <Bone className="h-10 w-10 rounded-2xl" />
            <div className="flex-1 space-y-2">
              <Bone className="h-4 w-1/2" />
              <Bone className="h-3 w-1/3" />
            </div>
          </div>
          <Bone className="h-14 w-full" />
          <Bone className="h-14 w-full" />
        </div>
        <p
          className={`pt-1 text-center text-[12px] text-white/40 transition-opacity duration-500 ${
            slow ? "opacity-100" : "opacity-0"
          }`}
        >
          Sveglio il server: a volte serve fino a un minuto…
        </p>
      </main>

      <div className="glass fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-50 flex justify-around rounded-[30px] px-2 py-3 lg:hidden">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="flex flex-col items-center gap-1.5">
            <Bone className="h-6 w-6 rounded-lg" />
            <Bone className="h-2 w-9 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}
