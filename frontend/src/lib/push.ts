/**
 * Promemoria sul telefono (Web Push) e installazione come app.
 *
 * Il browser si iscrive con la chiave pubblica del server; il backend salva
 * l'iscrizione e ogni sera, all'ora scelta, manda una notifica solo se oggi
 * manca qualcosa. Vedi `backend/app/services/push_notifications.py`.
 */

import { api } from "@/lib/api";

export type PushState =
  | "unsupported" // browser senza Web Push
  | "needs-install" // iPhone: le notifiche esistono solo nell'app sulla Home
  | "server-off" // chiavi non configurate sul server
  | "denied" // permesso negato nelle impostazioni
  | "off"
  | "on";

export const DEFAULT_HOUR = 20;
export const HOURS = Array.from({ length: 16 }, (_, i) => i + 7); // 7-22

export function isIos(): boolean {
  if (typeof navigator === "undefined") return false;
  // iPadOS si presenta come Mac: lo tradisce il touch.
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready);
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  return (await registration()).pushManager.getSubscription();
}

type Config = { enabled: boolean; public_key: string | null };
type SubOut = { endpoint: string; reminder_hour: number };

export async function pushState(): Promise<{ state: PushState; hour: number }> {
  // Su iPhone il Web Push esiste solo nell'app aggiunta alla Home.
  if (isIos() && !isStandalone()) return { state: "needs-install", hour: DEFAULT_HOUR };
  if (!pushSupported()) return { state: "unsupported", hour: DEFAULT_HOUR };
  const config = await api.get<Config>("/push/config");
  if (!config.enabled) return { state: "server-off", hour: DEFAULT_HOUR };
  if (Notification.permission === "denied") return { state: "denied", hour: DEFAULT_HOUR };
  const sub = await currentSubscription();
  if (!sub) return { state: "off", hour: DEFAULT_HOUR };
  const mie = await api.get<SubOut[]>("/push/subscriptions");
  const questa = mie.find((s) => s.endpoint === sub.endpoint);
  // Iscritto nel browser ma non sul server (per esempio con un altro account).
  return questa ? { state: "on", hour: questa.reminder_hour } : { state: "off", hour: DEFAULT_HOUR };
}

function keyToBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function save(sub: PushSubscription, hour: number) {
  const json = sub.toJSON();
  await api.post("/push/subscriptions", { endpoint: json.endpoint, keys: json.keys, reminder_hour: hour });
}

/** Chiede il permesso (va chiamata da un tocco dell'utente) e iscrive. */
export async function enablePush(hour: number): Promise<PushState> {
  const permesso = await Notification.requestPermission();
  if (permesso !== "granted") return permesso === "denied" ? "denied" : "off";
  const config = await api.get<Config>("/push/config");
  if (!config.enabled || !config.public_key) return "server-off";
  const reg = await registration();
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(config.public_key) });
  }
  await save(sub, hour);
  return "on";
}

export async function setPushHour(hour: number) {
  const sub = await currentSubscription();
  if (sub) await save(sub, hour);
}

export async function disablePush() {
  const sub = await currentSubscription();
  if (!sub) return;
  await api.post("/push/subscriptions/remove", { endpoint: sub.endpoint }).catch(() => undefined);
  await sub.unsubscribe();
}

export async function sendTestPush() {
  const sub = await currentSubscription();
  if (!sub) throw new Error("Questo dispositivo non è iscritto.");
  await api.post("/push/test", { endpoint: sub.endpoint });
}
