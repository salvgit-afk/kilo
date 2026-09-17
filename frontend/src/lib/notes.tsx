"use client";

/**
 * Note di Kilo condivise fra le sezioni e la chat.
 *
 * Si caricano una volta e si aggiornano quando l'utente segna qualcosa (lo
 * stesso evento dei promemoria) o cambia sezione: una nota come "fase di
 * carico finita" deve comparire subito dopo aver segnato il settimo giorno.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { REMINDERS_EVENT, api, localDate, type AgentNote } from "@/lib/api";

type NotesContext = {
  notes: AgentNote[];
  forSection: (section: string) => AgentNote[];
  dismiss: (key: string) => void;
  refresh: () => void;
};

const Ctx = createContext<NotesContext>({
  notes: [],
  forSection: () => [],
  dismiss: () => {},
  refresh: () => {},
});

export function NotesProvider({
  profileId,
  section,
  children,
}: {
  profileId: number;
  section: string;
  children: ReactNode;
}) {
  const [notes, setNotes] = useState<AgentNote[]>([]);

  const refresh = useCallback(() => {
    api
      .get<AgentNote[]>(`/profile/${profileId}/notes?today=${localDate()}`)
      .then(setNotes)
      .catch(() => {
        /* le note sono un di più: senza, l'app funziona uguale */
      });
  }, [profileId]);

  useEffect(() => {
    refresh();
  }, [refresh, section]);

  useEffect(() => {
    window.addEventListener(REMINDERS_EVENT, refresh);
    return () => window.removeEventListener(REMINDERS_EVENT, refresh);
  }, [refresh]);

  const dismiss = useCallback(
    (key: string) => {
      setNotes((prev) => prev.filter((n) => n.key !== key));
      api.post(`/profile/${profileId}/notes/dismiss`, { key }).catch(refresh);
    },
    [profileId, refresh]
  );

  const value = useMemo(
    () => ({
      notes,
      forSection: (s: string) => (s === "oggi" ? notes : notes.filter((n) => n.section === s)),
      dismiss,
      refresh,
    }),
    [notes, dismiss, refresh]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useNotes = () => useContext(Ctx);
