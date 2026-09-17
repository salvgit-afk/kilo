"use client";

/**
 * Overlay con l'esecuzione di un esercizio.
 *
 * - **Animazione**: i fotogrammi di partenza e arrivo di free-exercise-db,
 *   alternati. Non è un video e il pannello lo dichiara: le fonti video
 *   gratuite verificate non erano utilizzabili (vedi `exercise_library.py`).
 * - **Esecuzione**: traduzione italiana dei passaggi della fonte, numerati.
 * - **Focus muscolare**: indicazioni per sentire lavorare il muscolo
 *   principale. La nota sotto dipende dal muscolo (`exercise_guidance.py`):
 *   sui bicipiti lo studio ha misurato un beneficio, sui quadricipiti no, e
 *   per gli altri muscoli non è stato misurato. Prima era una frase unica,
 *   uguale anche per lo squat.
 * - **Come si muove il corpo**: articolazioni, azioni articolari, piano di
 *   movimento e indicazioni di forma, calcolati dallo schema di movimento.
 */

import { AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import {
  MUSCLE_LABELS,
  api,
  exerciseName,
  formatEquipment,
  type Exercise,
  type ExerciseGuidance,
} from "@/lib/api";
import { SourceTags, Spinner } from "@/components/ui";
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
  const guida = exercise.guidance ?? null;
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
              {exercise.source === "repdb" ? (
                <>
                  Illustrazioni di partenza e arrivo.{" "}
                  <a
                    href="https://repdb.co"
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-white/20 underline-offset-2 hover:text-white/60"
                  >
                    Exercise data by RepDB (repdb.co)
                  </a>
                </>
              ) : exercise.source === "kilo" ? (
                "Esercizio aggiunto da Kilo: nessun catalogo aperto lo contiene, quindi per ora non ha immagini. L'esecuzione è descritta qui accanto."
              ) : fotogrammi.length > 1 && exercise.source === "everkinetic" ? (
                "Disegni di Everkinetic (licenza CC BY-SA 4.0): posizione di partenza e di arrivo. Metti in pausa per osservarle."
              ) : fotogrammi.length > 1 ? (
                "Foto di partenza e arrivo (free-exercise-db, pubblico dominio). Metti in pausa per osservare le due posizioni."
              ) : fotogrammi.length === 1 ? (
                "Immagine dal catalogo wger."
              ) : (
                "Per questo esercizio la fonte non ha immagini."
              )}
            </p>

            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="w-20 text-[10.5px] uppercase tracking-wider text-white/30">Primario</span>
                <span className="pill border border-lime-400/30 bg-lime-400/10 text-lime-200">
                  {primario}
                </span>
              </div>
              {secondari.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="w-20 text-[10.5px] uppercase tracking-wider text-white/30">Secondari</span>
                  {secondari.map((m) => (
                    <span key={m} className="pill border border-white/10 bg-white/[0.05] text-white/55">
                      {m}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Info label="Tipo" value={exercise.is_compound ? "Multi-articolare" : "Isolamento"} />
              <Info label="Attrezzatura" value={formatEquipment(exercise.equipment)} />
            </div>

            {guida && <Biomechanics guida={guida} />}
          </div>

          <div className="space-y-5">
            {(exercise.focus_it?.length || guida) && (
              <div className="rounded-2xl border border-lime-400/20 bg-lime-400/[0.06] p-4">
                <p className="mb-2.5 text-[11px] font-medium uppercase tracking-wider text-lime-300/85">
                  Dove concentrarti · {primario}
                </p>
                {exercise.focus_it && exercise.focus_it.length > 0 && (
                  <ul className="space-y-2">
                    {exercise.focus_it.map((f, i) => (
                      <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug text-white/85">
                        <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-lime-400" />
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
                {guida && (
                  <div
                    className={`flex gap-2 text-[12px] leading-snug text-white/55 ${
                      exercise.focus_it?.length ? "mt-3 border-t border-lime-400/10 pt-3" : ""
                    }`}
                  >
                    <span
                      className={`mt-[3px] shrink-0 rounded px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wide ${FOCUS_BADGE[guida.focus_evidence].className}`}
                    >
                      {FOCUS_BADGE[guida.focus_evidence].label}
                    </span>
                    <span>{guida.focus_note}</span>
                  </div>
                )}
                {guida?.lengthened_note && (
                  <p className="mt-2.5 rounded-lg border border-white/[0.06] bg-black/15 px-2.5 py-2 text-[12px] leading-snug text-white/60">
                    <span className="font-medium text-white/80">In allungamento: </span>
                    {guida.lengthened_note}
                  </p>
                )}
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

const FOCUS_BADGE: Record<ExerciseGuidance["focus_evidence"], { label: string; className: string }> = {
  supported: { label: "Misurato", className: "bg-lime-400/20 text-lime-200" },
  not_shown: { label: "Nessuna differenza", className: "bg-amber-300/15 text-amber-100" },
  untested: { label: "Non misurato", className: "bg-white/10 text-white/55" },
};

/** Come si muove il corpo: articolazioni, azioni, piano e indicazioni di forma. */
function Biomechanics({ guida }: { guida: ExerciseGuidance }) {
  return (
    <div className="rounded-2xl border border-iris-400/20 bg-iris-400/[0.05] p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-iris-200/80">
        Come si muove il corpo
      </p>
      <p className="mt-1 text-[14px] font-semibold text-white">{guida.movement}</p>

      <div className="mt-3 space-y-2.5">
        {guida.joints.length > 0 && (
          <div>
            <p className="text-[10.5px] uppercase tracking-wider text-white/30">Articolazioni</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {guida.joints.map((j) => (
                <span key={j} className="pill border border-iris-400/25 bg-iris-400/10 text-iris-100">
                  {j}
                </span>
              ))}
            </div>
          </div>
        )}
        <div>
          <p className="text-[10.5px] uppercase tracking-wider text-white/30">Movimento articolare</p>
          <p className="mt-0.5 text-[13px] leading-snug text-white/75">{guida.actions.join(" · ")}</p>
        </div>
        <div>
          <p className="text-[10.5px] uppercase tracking-wider text-white/30">Piano di movimento</p>
          <p className="mt-0.5 text-[13px] leading-snug text-white/75">
            <span className="capitalize">{guida.plane}</span>
            <span className="text-white/40"> — {guida.plane_hint}</span>
          </p>
        </div>
      </div>

      {guida.cues.length > 0 && (
        <div className="mt-3.5 border-t border-white/[0.06] pt-3">
          <p className="mb-1.5 text-[10.5px] uppercase tracking-wider text-white/30">Forma corretta</p>
          <ul className="space-y-1.5">
            {guida.cues.map((c, i) => (
              <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-white/75">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-iris-300" />
                {c}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10.5px] leading-snug text-white/30">
            Indicazioni di anatomia e biomeccanica applicate: aiutano a muoversi bene, ma
            raramente sono state confrontate in studi sulla crescita muscolare.
          </p>
        </div>
      )}
      <div className="mt-3">
        <SourceTags tags={guida.knowledge_tags} />
      </div>
    </div>
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
