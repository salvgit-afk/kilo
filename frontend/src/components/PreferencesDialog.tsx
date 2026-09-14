"use client";

/**
 * Scelta degli esercizi preferiti per gruppo muscolare.
 *
 * Serve a rispondere a una richiesta concreta: *"per il petto preferisco la
 * chest press alla panca piana"*. Le preferenze pesano sulla **generazione**
 * della scheda successiva, non solo sulla sostituzione a posteriori — così
 * non bisogna ripetere la stessa correzione ogni volta.
 *
 * Ogni riga mostra l'animazione al passaggio del mouse: scegliere fra nomi
 * come "Pulley basso" e "Rematore con manubrio" è difficile senza vederli.
 */

import { useCallback, useEffect, useState } from "react";
import {
  MUSCLE_LABELS,
  api,
  exerciseName,
  formatEquipment,
  type Exercise,
  type Preference,
} from "@/lib/api";
import { Spinner } from "@/components/ui";
import { DemoAnimation, Modal, ModalHeader } from "@/components/controls";
import { ExerciseDetailHost } from "@/components/ExerciseDetail";

const GRUPPI = [
  "Chest",
  "Lats",
  "Shoulders",
  "Biceps",
  "Triceps",
  "Quads",
  "Hamstrings",
  "Glutes",
  "Calves",
  "Abs",
];

export function PreferencesDialog({
  profileId,
  onClose,
}: {
  profileId: number;
  onClose: () => void;
}) {
  const [muscle, setMuscle] = useState("Chest");
  const [exercises, setExercises] = useState<Exercise[] | null>(null);
  const [prefs, setPrefs] = useState<Record<number, boolean>>({});
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);

  const loadPrefs = useCallback(async () => {
    const righe = await api.get<Preference[]>(`/workout/preferences?profile_id=${profileId}`);
    setPrefs(Object.fromEntries(righe.map((p) => [p.exercise_id, p.is_preferred])));
  }, [profileId]);

  useEffect(() => {
    loadPrefs();
  }, [loadPrefs]);

  useEffect(() => {
    setExercises(null);
    const q = query.trim() ? `&q=${encodeURIComponent(query.trim())}` : "";
    const timer = setTimeout(() => {
      api.get<Exercise[]>(`/workout/exercises?muscle=${muscle}&limit=30${q}`).then(setExercises);
    }, 300);
    return () => clearTimeout(timer);
  }, [muscle, query]);

  async function toggle(exercise: Exercise, preferred: boolean) {
    setBusy(exercise.id);
    try {
      if (prefs[exercise.id] === preferred) {
        // Ri-cliccare la stessa scelta la annulla: torna "nessuna preferenza".
        await api.del(`/workout/preferences/${exercise.id}?profile_id=${profileId}`);
      } else {
        await api.post(`/workout/preferences?profile_id=${profileId}`, {
          exercise_id: exercise.id,
          is_preferred: preferred,
        });
      }
      await loadPrefs();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Modal onClose={onClose} className="max-w-2xl">
        <ModalHeader
          title="I tuoi esercizi preferiti"
          subtitle="Valgono già dalla prossima scheda che genero"
          onClose={onClose}
        />

        <div className="shrink-0 space-y-3 border-b border-white/[0.06] p-4">
          <div className="flex flex-wrap gap-1.5">
            {GRUPPI.map((m) => (
              <button
                key={m}
                onClick={() => setMuscle(m)}
                className={`rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition ${
                  muscle === m
                    ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
                    : "border-white/[0.08] bg-white/[0.025] text-white/50 hover:bg-white/[0.06] hover:text-white/80"
                }`}
              >
                {MUSCLE_LABELS[m] ?? m}
              </button>
            ))}
          </div>
          <input
            className="input py-2 text-[13px]"
            placeholder="Cerca per nome — es. panca, chest press, lat machine"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
          {!exercises ? (
            <Spinner />
          ) : exercises.length === 0 ? (
            <p className="px-4 py-8 text-center text-[13px] text-white/35">
              Nessun esercizio trovato per questo filtro.
            </p>
          ) : (
            exercises.map((ex) => {
              const stato = prefs[ex.id];
              const nome = exerciseName(ex);
              return (
                <div
                  key={ex.id}
                  className="mb-1 flex items-center gap-3 rounded-xl px-2.5 py-2 transition hover:bg-white/[0.035]"
                >
                  <button
                    onClick={() => setDetailId(ex.id)}
                    title="Vedi come si esegue"
                    className="shrink-0"
                  >
                    <DemoAnimation
                      images={ex.demo_images ?? (ex.image_url ? [ex.image_url] : [])}
                      alt={nome}
                      mode="hover"
                      fit="contain"
                      className="h-12 w-16 rounded-lg border border-white/10"
                    />
                  </button>
                  <button onClick={() => setDetailId(ex.id)} className="min-w-0 flex-1 text-left">
                    <p className="truncate text-[13.5px] text-white/85 hover:text-white">{nome}</p>
                    <p className="truncate text-[11px] text-white/35">
                      {ex.is_compound ? "multi-articolare" : "isolamento"} ·{" "}
                      {formatEquipment(ex.equipment)}
                    </p>
                  </button>
                  <div className="flex shrink-0 gap-1.5">
                    <button
                      disabled={busy === ex.id}
                      onClick={() => toggle(ex, true)}
                      title="Preferiscilo"
                      aria-label="Preferiscilo"
                      className={`grid h-9 w-9 place-items-center rounded-lg border transition ${
                        stato === true
                          ? "border-lime-400/40 bg-lime-400/15 text-lime-300"
                          : "border-white/[0.08] bg-white/[0.03] text-white/35 hover:border-lime-400/25 hover:text-lime-200"
                      }`}
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                        <path d="M2 21h4V9H2v12Zm20-11a2 2 0 0 0-2-2h-6.3l.95-4.57.03-.32a1.5 1.5 0 0 0-.44-1.06L13.17 1 7.6 6.59A2 2 0 0 0 7 8v11a2 2 0 0 0 2 2h9a2 2 0 0 0 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2Z" />
                      </svg>
                    </button>
                    <button
                      disabled={busy === ex.id}
                      onClick={() => toggle(ex, false)}
                      title="Non propormelo"
                      aria-label="Non propormelo"
                      className={`grid h-9 w-9 place-items-center rounded-lg border transition ${
                        stato === false
                          ? "border-amber-300/40 bg-amber-300/15 text-amber-200"
                          : "border-white/[0.08] bg-white/[0.03] text-white/35 hover:border-amber-300/25 hover:text-amber-100"
                      }`}
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                        <path d="M22 3h-4v12h4V3ZM2 14a2 2 0 0 0 2 2h6.3l-.95 4.57-.03.32c0 .41.17.79.44 1.06L10.83 23l5.58-5.59c.36-.36.59-.86.59-1.41V5a2 2 0 0 0-2-2H6a2 2 0 0 0-1.84 1.22L1.14 11.27c-.09.23-.14.47-.14.73v2Z" />
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="shrink-0 border-t border-white/[0.06] p-4">
          <p className="mb-3 text-[11.5px] leading-relaxed text-white/35">
            Gli esercizi da evitare non ti vengono più proposti; quelli preferiti vengono
            scelti per primi. Clicca di nuovo sulla stessa icona per togliere la
            preferenza.
          </p>
          <button className="btn-primary w-full" onClick={onClose}>
            Fatto
          </button>
        </div>
      </Modal>

      <ExerciseDetailHost
        exerciseId={detailId}
        profileId={profileId}
        onClose={() => setDetailId(null)}
        onPreferenceChanged={loadPrefs}
      />
    </>
  );
}
