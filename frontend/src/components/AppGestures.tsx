"use client";

/**
 * Blocca lo zoom con due dita anche su iOS.
 *
 * Safari ignora `user-scalable=no` nel meta viewport per scelta di
 * accessibilità: l'unico modo per far restare fissa la pagina, come in
 * un'app, è annullare i gesti di pinch.
 */

import { useEffect } from "react";

export function AppGestures() {
  useEffect(() => {
    const annulla = (e: Event) => e.preventDefault();
    const pinch = (e: TouchEvent) => {
      if (e.touches.length > 1) e.preventDefault();
    };
    document.addEventListener("gesturestart", annulla);
    document.addEventListener("gesturechange", annulla);
    document.addEventListener("touchmove", pinch, { passive: false });
    return () => {
      document.removeEventListener("gesturestart", annulla);
      document.removeEventListener("gesturechange", annulla);
      document.removeEventListener("touchmove", pinch);
    };
  }, []);

  return null;
}
