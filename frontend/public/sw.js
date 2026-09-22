/*
 * Service worker di Kilo.
 *
 * Fa solo tre cose, di proposito:
 *  1. se manca la rete, al posto della pagina d'errore del browser mostra
 *     /offline.html (i dati stanno sul server: offline non c'è altro da fare);
 *  2. riceve i promemoria push e li mostra come notifica;
 *  3. al tocco sulla notifica apre Kilo sulla sezione giusta.
 *
 * Nessuna cache delle pagine o dell'API: ogni deploy su Vercel arriva subito
 * e i dati personali non restano salvati sul telefono.
 */

const CACHE = "kilo-offline-v1";
const OFFLINE_URL = "/offline.html";
const OFFLINE_ASSETS = [OFFLINE_URL, "/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(OFFLINE_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Kilo", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-96.png",
      lang: "it",
      // Un promemoria nuovo sostituisce quello vecchio invece di accumularsi.
      tag: "kilo-promemoria",
      renotify: true,
      data: { section: data.section || "oggi" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const section = (event.notification.data && event.notification.data.section) || "oggi";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const aperta = windows.find((w) => new URL(w.url).origin === self.location.origin);
      if (aperta) {
        aperta.postMessage({ type: "kilo:open-section", section });
        return aperta.focus();
      }
      return self.clients.openWindow(`/?sezione=${encodeURIComponent(section)}`);
    })
  );
});
