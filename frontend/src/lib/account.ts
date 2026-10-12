/**
 * L'ultimo account e profilo visti, salvati sul telefono.
 *
 * Servono ad aprire l'app quando il backend non è raggiungibile (palestra
 * senza campo, Render che non risponde): il token resta quello di sempre e
 * ogni richiesta lo verifica; qui c'è solo ciò che serve a mostrare le
 * sezioni. Si cancella all'uscita dall'account.
 */

import type { AuthSession } from "@/lib/api";

const KEY = "kilo:account";

type Salvato = { user: AuthSession["user"]; profile: AuthSession["profile"] };

export function rememberAccount(dati: Salvato) {
  try {
    localStorage.setItem(KEY, JSON.stringify(dati));
  } catch {
    /* memoria piena o disattivata: solo una comodità */
  }
}

export function recallAccount(): Salvato | null {
  try {
    const dati = JSON.parse(localStorage.getItem(KEY) ?? "null") as Salvato | null;
    return dati?.user ? dati : null;
  } catch {
    return null;
  }
}

export function forgetAccount() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* niente da fare */
  }
}
