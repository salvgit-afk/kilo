"use client";

/**
 * I pallini sulle voci del menu: cosa c'è da segnare oggi.
 *
 * Stessa fonte del banner dei promemoria (`/profile/{id}/reminders`), quindi
 * stesse regole per non dare fastidio: integratori solo se dichiarati, diario
 * solo se usato di recente, allenamento solo nei giorni scelti per la scheda
 * e finché la sessione non è iniziata. Il valore è il testo per chi usa un
 * lettore di schermo.
 *
 * Si aggiorna quando qualcosa viene segnato (`notifyLogged`), quando si
 * torna sull'app e ogni cinque minuti, così a mezzanotte cambia giorno.
 */

import { useCallback, useEffect, useState } from "react";
import { REMINDERS_EVENT, api, localDate, type DailyReminders } from "@/lib/api";
import type { SectionId } from "@/components/Shell";

export type SectionBadges = Partial<Record<SectionId, string>>;

export function badgesFrom(r: DailyReminders): SectionBadges {
  const out: SectionBadges = {};
  if (r.supplements.length) {
    out.integratori = r.supplements.length === 1 ? "1 integratore da segnare oggi" : `${r.supplements.length} integratori da segnare oggi`;
  }
  if (r.meals_missing) out.diario = "Nessun pasto segnato oggi";
  if (r.workouts_due.length) out.scheda = "Allenamento di oggi non ancora iniziato";
  return out;
}

export function useSectionBadges(profileId: number): SectionBadges {
  const [badges, setBadges] = useState<SectionBadges>({});

  const refresh = useCallback(() => {
    api
      .get<DailyReminders>(`/profile/${profileId}/reminders?today=${localDate()}`)
      .then((r) => setBadges(badgesFrom(r)))
      .catch(() => undefined);
  }, [profileId]);

  useEffect(() => {
    refresh();
    const onVisible = () => document.visibilityState === "visible" && refresh();
    const timer = setInterval(refresh, 5 * 60 * 1000);
    window.addEventListener(REMINDERS_EVENT, refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      window.removeEventListener(REMINDERS_EVENT, refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  return badges;
}
