import type { Metadata, Viewport } from "next";
import { Analytics } from "@vercel/analytics/next";
import { AppGestures } from "@/components/AppGestures";
import { PwaSetup } from "@/components/PwaSetup";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kilo",
  description:
    "Kilo, il tuo coach di allenamento e nutrizione. Schede e piani alimentari costruiti su parametri da fonti verificate — ISSN, EFSA, WHO, IOC.",
  applicationName: "Kilo",
  // Aggiunto alla Home dell'iPhone: nome sotto l'icona e barra di stato
  // trasparente sopra lo sfondo scuro, come un'app nativa.
  appleWebApp: { capable: true, title: "Kilo", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
};

// Si comporta come un'app: niente zoom, e con `viewport-fit=cover` la barra
// in basso può tenere conto della zona dell'indicatore home dell'iPhone.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#07080d",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it">
      <body>
        <AppGestures />
        <PwaSetup />
        <div className="relative z-10">{children}</div>
        {/* Vercel Web Analytics: statistiche di visita senza cookie. In locale non invia nulla. */}
        <Analytics />
      </body>
    </html>
  );
}
