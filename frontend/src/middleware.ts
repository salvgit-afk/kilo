/**
 * Le chiamate a /api passano da qui prima di essere inoltrate al backend
 * (`next.config.mjs`). Per Render chi si collega è Vercel: senza questo,
 * i limiti contro i tentativi di accesso conterebbero tutti gli utenti
 * insieme sotto gli indirizzi di Vercel.
 *
 * Con `PROXY_SECRET` impostato (lo stesso valore su Vercel e su Render) si
 * aggiunge l'indirizzo vero di chi si collega, firmato con il segreto: il
 * backend gli crede solo se il segreto corrisponde. Senza segreto non cambia
 * niente. Le intestazioni con lo stesso nome mandate dal browser vengono
 * sempre sovrascritte o tolte.
 */

import { NextResponse, type NextRequest } from "next/server";

export const config = { matcher: "/api/:path*" };

export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.delete("x-kilo-proxy-secret");
  headers.delete("x-kilo-client-ip");

  const segreto = process.env.PROXY_SECRET?.trim();
  // Su Vercel X-Forwarded-For lo scrive Vercel stesso, con l'indirizzo del client.
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || request.headers.get("x-real-ip");
  if (segreto && ip) {
    headers.set("x-kilo-proxy-secret", segreto);
    headers.set("x-kilo-client-ip", ip);
  }
  return NextResponse.next({ request: { headers } });
}
