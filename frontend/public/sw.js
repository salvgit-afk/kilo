/*
 * Service worker di Kilo.
 *
 * Fa quattro cose:
 *  1. tiene sul telefono il guscio dell'app (la pagina e i suoi file
 *     statici), così Kilo si apre anche senza rete, per esempio in una
 *     palestra senza campo dopo che iOS l'ha chiusa: lì l'allenamento si
 *     segna nella coda e parte quando torna la rete;
 *  2. se manca anche quello (primo avvio senza rete), mostra /offline.html;
 *  3. riceve i promemoria push e li mostra come notifica;
 *  4. al tocco sulla notifica apre Kilo sulla sezione giusta.
 *
 * La pagina va sempre prima in rete: con la connessione ogni deploy arriva
 * subito, la copia serve solo quando la rete non risponde. Le risposte
 * dell'API non passano mai di qui: i dati personali che restano sul
 * telefono sono solo quelli che l'app sceglie di tenere (vedi lib/localData).
 */

const OFFLINE_CACHE = "kilo-offline-v1";
const SHELL_CACHE = "kilo-shell-v1";
const STATIC_CACHE = "kilo-static-v1";
const CACHES = [OFFLINE_CACHE, SHELL_CACHE, STATIC_CACHE];
const OFFLINE_URL = "/offline.html";
const OFFLINE_ASSETS = [OFFLINE_URL, "/icons/icon-192.png"];
// Con un segnale debole la rete può non rispondere né fallire: dopo questo
// tempo si apre la copia (la pagina vera arriva al prossimo avvio).
const NAVIGATION_TIMEOUT_MS = 5000;
// I file statici hanno il contenuto nel nome: quelli dei deploy vecchi non
// servono più, se ne tengono al massimo tanti così.
const MAX_STATIC = 200;

self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([
      caches.open(OFFLINE_CACHE).then((cache) => cache.addAll(OFFLINE_ASSETS)),
      // Il guscio subito, senza aspettare la prossima apertura.
      caches.open(SHELL_CACHE).then((cache) => cache.add("/").catch(() => undefined)),
    ])
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !CACHES.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function navigation(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const rete = fetch(request);
    const tempo = new Promise((_, reject) => setTimeout(() => reject(new Error("lenta")), NAVIGATION_TIMEOUT_MS));
    const response = await Promise.race([rete, tempo]);
    // L'app è una pagina sola ("/" con eventuali parametri): una copia basta.
    if (response.ok && new URL(request.url).pathname === "/") {
      cache.put("/", response.clone()).catch(() => undefined);
    }
    return response;
  } catch {
    return (await cache.match("/")) || (await caches.match(OFFLINE_URL)) || Response.error();
  }
}

async function staticFile(request) {
  const cache = await caches.open(STATIC_CACHE);
  const copia = await cache.match(request);
  if (copia) return copia;
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone()).catch(() => undefined);
    const chiavi = await cache.keys();
    for (const vecchia of chiavi.slice(0, Math.max(0, chiavi.length - MAX_STATIC))) await cache.delete(vecchia);
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === "navigate") {
    event.respondWith(navigation(request));
  } else if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(staticFile(request));
  }
  // Tutto il resto, API comprese, va in rete come sempre.
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
