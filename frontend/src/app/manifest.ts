import type { MetadataRoute } from "next";

/**
 * Manifest della PWA: con questo il telefono tratta Kilo come un'app
 * (icona sulla Home, schermo intero, nome sotto l'icona). Next lo pubblica
 * su /manifest.webmanifest e lo collega da solo nell'<head>.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Kilo — allenamento e nutrizione",
    short_name: "Kilo",
    description: "Il tuo coach di allenamento e nutrizione, con parametri da fonti verificate.",
    lang: "it",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#07080d",
    theme_color: "#07080d",
    categories: ["health", "fitness", "lifestyle"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
