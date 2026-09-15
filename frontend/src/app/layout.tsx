import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kilo",
  description:
    "Kilo, il tuo coach di allenamento e nutrizione. Schede e piani alimentari costruiti su parametri da fonti verificate — ISSN, EFSA, WHO, IOC.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it">
      <body>
        <div className="relative z-10">{children}</div>
        {/* Vercel Web Analytics: statistiche di visita senza cookie. In locale non invia nulla. */}
        <Analytics />
      </body>
    </html>
  );
}
