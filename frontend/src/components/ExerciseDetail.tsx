"use client";

/**
 * Overlay con l'esecuzione di un esercizio.
 *
 * - **Animazione**: i fotogrammi di partenza e arrivo di free-exercise-db,
 *   alternati. Non è un video e il pannello lo dichiara: le fonti video
 *   gratuite verificate non erano utilizzabili (vedi `exercise_library.py`).
 * - **Esecuzione**: traduzione italiana dei passaggi della fonte, numerati.
 * - **Focus muscolare**: indicazioni per sentire lavorare il muscolo
 *   principale, ricavate dal movimento. La nota sotto riporta ciò che dice
 *   davvero lo studio in `exercise_choice_and_focus.md`: beneficio osservato
 *   sui bicipiti, nessuna differenza sui quadricipiti.
 */

import { AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import { MUSCLE_LABELS, api, exerciseName, formatEquipment, type Exercise } from "@/lib/api";
import { Spinner } from "@/components/ui";
import { AskCoachButton, DemoAnimation, Modal, ModalHeader } from "@/components/controls";

export function ExerciseDetail({
  exerciseId,
  profileId,
  onClose,
  onPreferenceChanged,
}: {
  exerciseId: number;
  profileId?: number;
  onClose: () => void;
  onPreferenceChanged?: () => void;
}) {
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .get<Exercise>(`/workout/exercises/${exerciseId}`)
      .then(setExercise)
      .catch((e) => setError(e instanceof Error ? e.message : "Esercizio non disponibile"));
  }, [exerciseId]);

  async function setPreference(preferred: boolean) {
    if (!profileId) return;
    setSaving(true);
    try {
      await api.post(`/workout/preferences?profile_id=${profileId}`, {
        exercise_id: exerciseId,
        is_preferred: preferred,
      });
      setSaved(preferred);
      onPreferenceChanged?.();
    } finally {
      setSaving(false);
    }
  }

  if (!exercise) {
    return (
      <Modal onClose={onClose} z="z-[90]" className="max-w-md">
        <ModalHeader title="Esercizio" onClose={onClose} />
        {error ? (
          <p className="px-5 py-8 text-center text-[13px] text-rose-200/80">{error}</p>
        ) : (
          <Spinner label="Carico l'esercizio…" />
        )}
      </Modal>
    );
  }

  const nome = exerciseName(exercise);
  const primario = MUSCLE_LABELS[exercise.primary_muscle ?? ""] ?? exercise.primary_muscle ?? "";
  const secondari = (exercise.secondary_muscles ?? "")
    .split(",")
    .map((m) => MUSCLE_LABELS[m.trim()] ?? m.trim())
    .filter(Boolean);
  const tradotto = !!exercise.instructions_it?.length;
  const passi = tradotto
    ? exercise.instructions_it!
    : (exercise.description ?? "").split("\n").map((s) => s.trim()).filter(Boolean);
  const fotogrammi = exercise.demo_images?.length
    ? exercise.demo_images
    : exercise.image_url
      ? [exercise.image_url]
      : [];

  return (
    <Modal onClose={onClose} z="z-[90]" className="max-w-4xl">
      <ModalHeader
        eyebrow="Come si esegue"
        title={nome}
        subtitle={exercise.name_it && exercise.name_it !== exercise.name ? exercise.name : undefined}
        onClose={onClose}
      />

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="grid gap-5 p-5 md:grid-cols-[1.05fr_1fr]">
          <div className="space-y-3">
            <DemoAnimation
              images={fotogrammi}
              alt={nome}
              fit="contain"
              controls
              className="aspect-[4/3] w-full rounded-2xl border border-white/10"
            />
            <p className="text-[11px] leading-snug text-white/30">
              {fotogrammi.length > 1 && exercise.source === "everkinetic"
                ? "Disegni di Everkinetic (licenza CC BY-SA 4.0): posizione di partenza e di arrivo. Metti in pausa per osservarle."
                : fotogrammi.length > 1
                ? "Animazione ricavata dai fotogrammi di partenza e arrivo (free-exercise-db, pubblico dominio). Metti in pausa per osservare le due posizioni."
                : fotogrammi.length === 1
                  ? "Immagine dal catalogo wger."
                  : "Per questo esercizio la fonte non ha immagini."}
            </p>

            <div className="flex flex-wrap gap-1.5">
              <span className="pill border border-lime-400/30 bg-lime-400/10 text-lime-200">
                {primario}
              </span>
              {secondari.map((m) => (
                <span key={m} className="pill border border-white/10 bg-white/[0.05] text-white/55">
                  {m}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Info label="Tipo" value={exercise.is_compound ? "Multi-articolare" : "Isolamento"} />
              <Info label="Attrezzatura" value={formatEquipment(exercise.equipment)} />
            </div>
          </div>

          <div className="space-y-5">
            {exercise.focus_it && exercise.focus_it.length > 0 && (
              <div className="rounded-2xl border border-lime-400/20 bg-lime-400/[0.06] p-4">
                <p className="mb-2.5 text-[11px] font-medium uppercase tracking-wider text-lime-300/85">
                  Dove concentrarti · {primario}
                </p>
                <ul className="space-y-2">
                  {exercise.focus_it.map((f, i) => (
                    <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug text-white/85">
                      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-lime-400" />
                      {f}
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[11px] leading-snug text-white/35">
                  Nello studio riportato dalle fonti, concentrarsi sul muscolo ha dato più
                  crescita sui bicipiti e nessuna differenza sui quadricipiti: è un aiuto,
                  non una regola.
                </p>
              </div>
            )}

            <div>
              <p className="label">Esecuzione</p>
              {passi.length > 0 ? (
                <ol className="space-y-2.5">
                  {passi.map((p, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg border border-white/10 bg-white/[0.05] font-mono text-[11px] text-white/60">
                        {i + 1}
                      </span>
                      <span className="pt-0.5 text-[13.5px] leading-relaxed text-white/75">{p}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-[13px] italic leading-relaxed text-white/35">
                  La fonte non riporta una descrizione per questo esercizio. Chiedi a Kilo
                  oppure scegline uno alternativo dalla scheda.
                </p>
              )}
              {!tradotto && passi.length > 0 && (
                <p className="mt-2 text-[11px] text-amber-200/55">
                  Traduzione non ancora pronta: per ora vedi il testo originale.
                </p>
              )}
            </div>

            {exercise.tips_it && exercise.tips_it.length > 0 && (
              <div>
                <p className="label">Consigli</p>
                <ul className="space-y-1.5">
                  {exercise.tips_it.map((t, i) => (
                    <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-white/70">
                      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-iris-400" />
                      {t}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <AskCoachButton
              question={`Nell'esercizio «${nome}» come faccio a sentire lavorare di più ${primario.toLowerCase()}? Quali errori evitare?`}
              context={`Overlay esercizio: ${nome} (muscolo principale: ${primario})`}
              label="Chiedi a Kilo su questo esercizio"
            />

            {profileId && (
              <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
                <p className="mb-1 text-[13px] font-medium text-white/80">Ti piace questo esercizio?</p>
                <p className="mb-3 text-[12px] leading-relaxed text-white/40">
                  La risposta pesa già sulla prossima scheda: un esercizio che ti piace lo
                  esegui, uno che ti annoia lo salti.
                </p>
                <div className="flex gap-2">
                  <button
                    disabled={saving}
                    onClick={() => setPreference(true)}
                    className={`btn flex-1 border text-[13px] ${
                      saved === true
                        ? "border-lime-400/40 bg-lime-400/15 text-lime-200"
                        : "border-white/10 bg-white/[0.04] text-white/70 hover:bg-white/[0.08]"
                    }`}
                  >
                    Preferiscilo
                  </button>
                  <button
                    disabled={saving}
                    onClick={() => setPreference(false)}
                    className={`btn flex-1 border text-[13px] ${
                      saved === false
                        ? "border-amber-300/40 bg-amber-300/15 text-amber-100"
                        : "border-white/10 bg-white/[0.04] text-white/70 hover:bg-white/[0.08]"
                    }`}
                  >
                    Evitalo
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-white/30">{label}</p>
      <p className="text-[12.5px] text-white/75">{value}</p>
    </div>
  );
}

/** Wrapper con animazione di uscita, per l'uso nelle sezioni. */
export function ExerciseDetailHost({
  exerciseId,
  profileId,
  onClose,
  onPreferenceChanged,
}: {
  exerciseId: number | null;
  profileId?: number;
  onClose: () => void;
  onPreferenceChanged?: () => void;
}) {
  return (
    <AnimatePresence>
      {exerciseId !== null && (
        <ExerciseDetail
          key={exerciseId}
          exerciseId={exerciseId}
          profileId={profileId}
          onClose={onClose}
          onPreferenceChanged={onPreferenceChanged}
        />
      )}
    </AnimatePresence>
  );
}
