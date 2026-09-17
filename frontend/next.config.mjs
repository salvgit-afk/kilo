/** @type {import('next').NextConfig} */

const isDev = process.env.NODE_ENV !== "production";

/**
 * Content-Security-Policy: il browser carica solo ciò che è elencato qui.
 * Se un giorno una falla permettesse di iniettare HTML, lo script iniettato
 * non potrebbe caricare codice da altri domini né spedire altrove il token
 * di sessione (che sta in localStorage).
 *
 * - `'unsafe-inline'` negli script serve a Next per i dati di avvio della
 *   pagina; in sviluppo serve anche `'unsafe-eval'` per il ricaricamento.
 * - Le immagini arrivano dai cataloghi: esercizi (GitHub), ricette
 *   (TheMealDB) e wger.
 */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval' https://va.vercel-scripts.com" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://raw.githubusercontent.com https://www.themealdb.com https://wger.de",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: https://va.vercel-scripts.com" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  // Nessun sito può mostrare Kilo dentro un iframe (clickjacking).
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig = {
  async rewrites() {
    // Il browser chiama /api/*, Next inoltra al backend FastAPI: così non
    // servono CORS né URL assoluti sparsi nei componenti.
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/:path*`,
      },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};
export default nextConfig;
