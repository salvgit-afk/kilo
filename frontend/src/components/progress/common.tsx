"use client";

/**
 * Mattoni condivisi dalle card della pagina Progressi.
 *
 * Ogni statistica ha il suo endpoint e arriva per conto suo: una che manca o
 * che risponde con un errore non deve portarsi dietro la pagina. `useEndpoint`
 * tiene insieme dato, caricamento ed errore di una sola card, così ogni card
 * mostra da sé il proprio stato.
 *
 * Qui stanno anche i tipi delle statistiche nuove: `lib/api.ts` è in mano a
 * un'altra lavorazione, quindi non lo tocchiamo.
 */

import { useEffect, useState } from "react";
import { api, type LoggedExercise } from "@/lib/api";
import { Empty, Spinner } from "@/components/ui";

// --- Tipi delle statistiche -----------------------------------------------

export type VolumeStatus = "sotto" | "dentro" | "sopra";

export type VolumeMuscle = {
  muscle: string;
  sets_per_week: number[];
  average: number;
  last: number;
  range_min: number;
  range_max: number;
  status: VolumeStatus;
};

export type VolumeResponse = {
  weeks: string[];
  muscles: VolumeMuscle[];
};

export type OneRmPoint = {
  date: string;
  one_rm: number;
  kg: number;
  reps: number;
};

export type OneRmResponse = {
  exercise_id: number;
  exercise_name: string;
  points: OneRmPoint[];
  delta_pct: number | null;
  high_rep_estimate: boolean;
};

export type ConsistencyWeek = {
  start: string;
  done: number;
  planned: number;
};

export type ConsistencyResponse = {
  weeks: ConsistencyWeek[];
  streak_weeks: number;
  best_streak_weeks: number;
  done_total: number;
  planned_total: number;
};

export type WeightTrendVerdict =
  | "in_linea"
  | "troppo_veloce"
  | "troppo_lento"
  | "pochi_dati"
  // Le fonti danno un ritmo atteso solo per il dimagrimento: per massa e
  // mantenimento il ritmo si mostra, ma senza giudizio.
  | "non_valutabile";

export type WeightTrendResponse = {
  points: { date: string; weight_kg: number; average_kg: number }[];
  weekly_rate_kg: number | null;
  expected_min: number | null;
  expected_max: number | null;
  verdict: WeightTrendVerdict;
  note: string | null;
};

export type NutritionWeek = {
  start: string;
  kcal_avg: number;
  protein_avg_g: number;
  days_logged: number;
  days_in_kcal_target: number;
  days_in_protein_target: number;
};

export type NutritionResponse = {
  weeks: NutritionWeek[];
  kcal_target: number | null;
  protein_target_g: number | null;
};

// --- Lettura di un endpoint ------------------------------------------------

export type Remote<T> = { data: T | null; loading: boolean; error: string | null };

/** Legge un endpoint e ne espone i tre stati. `null` = non c'è niente da chiedere. */
export function useEndpoint<T>(path: string | null): Remote<T> {
  const [state, setState] = useState<Remote<T>>({
    data: null,
    loading: path !== null,
    error: null,
  });

  useEffect(() => {
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let annullato = false;
    setState({ data: null, loading: true, error: null });
    api
      .get<T>(path)
      .then((d) => {
        if (!annullato) setState({ data: d, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (!annullato)
          setState({
            data: null,
            loading: false,
            error: e instanceof Error ? e.message : "statistica non disponibile",
          });
      });
    return () => {
      annullato = true;
    };
  }, [path]);

  return state;
}

/** Esercizi con carichi registrati: la stessa lista serve a due grafici. */
export function useLoggedExercises(profileId: number, weeks: number) {
  const [exercises, setExercises] = useState<LoggedExercise[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let annullato = false;
    api
      .get<LoggedExercise[]>(`/progress/loads?profile_id=${profileId}&weeks=${weeks}`)
      .then((lista) => {
        if (annullato) return;
        setExercises(lista);
        // Se l'esercizio scelto esiste ancora nel nuovo periodo resta scelto:
        // cambiare le settimane non deve far saltare la selezione.
        setSelected((attuale) =>
          attuale !== null && lista.some((e) => e.exercise_id === attuale)
            ? attuale
            : lista[0]?.exercise_id ?? null
        );
      })
      .catch(() => {
        if (!annullato) setExercises([]);
      });
    return () => {
      annullato = true;
    };
  }, [profileId, weeks]);

  return { exercises, selected, setSelected };
}

// --- Stati delle card ------------------------------------------------------

/** Caricamento o errore di una card: mai una pagina bianca, mai un crash. */
export function RemoteFallback({
  loading,
  error,
  loadingLabel,
  emptyTitle = "Statistica non disponibile",
}: {
  loading: boolean;
  error: string | null;
  loadingLabel: string;
  emptyTitle?: string;
}) {
  if (loading) return <Spinner label={loadingLabel} />;
  return (
    <Empty
      title={emptyTitle}
      hint={error ? `Riprova più tardi — ${error}` : "Riprova più tardi."}
    />
  );
}

// --- Selettore dell'esercizio ---------------------------------------------

export function ExercisePicker({
  exercises,
  selected,
  onSelect,
}: {
  exercises: LoggedExercise[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="-mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
      {exercises.map((e) => (
        <button
          key={e.exercise_id}
          onClick={() => onSelect(e.exercise_id)}
          className={`shrink-0 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition ${
            e.exercise_id === selected
              ? "border-lime-400/50 bg-lime-400/15 text-lime-100"
              : "border-white/10 bg-white/[0.03] text-white/55 hover:text-white"
          }`}
        >
          {e.exercise_name}
          <span className="ml-1.5 font-mono text-[11px] text-white/35">{e.sessions}</span>
        </button>
      ))}
    </div>
  );
}

// --- Formati ---------------------------------------------------------------

/** Numero all'italiana: virgola decimale. */
export function num(value: number, decimals = 1) {
  return value.toLocaleString("it-IT", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Numero col segno; il meno è quello tipografico, non il trattino. */
export function signed(value: number, decimals = 1) {
  const segno = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${segno}${num(Math.abs(value), decimals)}`;
}

export function shortDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

/** Stile del tooltip dei grafici: uguale in tutta la pagina. */
export const tooltipStyle = {
  contentStyle: {
    background: "rgba(12,14,22,0.96)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 12,
    fontSize: 12,
  },
  labelStyle: { color: "rgba(255,255,255,0.5)" },
} as const;

export const axisTick = { fill: "rgba(255,255,255,0.3)", fontSize: 11 } as const;
