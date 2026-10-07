"use client";

/**
 * Scelta di un esercizio dal catalogo: per sostituirne uno della scheda, per
 * aggiungerne uno a un giorno o, durante l'allenamento, per cambiarlo al volo
 * (macchina occupata). Filtri per gruppo muscolare, attrezzatura e nome.
 */

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import {
  MUSCLE_LABELS,
  api,
  exerciseName,
  formatEquipment,
  type Alternative,
  type PlanExercise,
  type WorkoutPlan,
} from "@/lib/api";
import { DemoAnimation, Modal, ModalHeader, OptionGroup } from "@/components/controls";
import { Empty, Notice, Spinner } from "@/components/ui";

// Gruppi fra cui scegliere quando si cambia proprio il muscolo: quelli che
// la scheda allena, senza i gruppi minori. Gli adduttori il generatore non li
// programma, ma si possono aggiungere a mano.
export const GRUPPI_SOSTITUZIONE = [
  "Chest", "Lats", "Shoulders", "Trapezius", "Biceps", "Triceps",
  "Quads", "Hamstrings", "Glutes", "Adductors", "Calves", "Abs",
];

// Esercizi caricati per volta: "Mostra altri" ne aggiunge altrettanti. Un
// gruppo arriva a 150 esercizi; con un elenco fisso di 24 la maggior parte non
// si vedeva mai.
const PAGINA_ALTERNATIVE = 24;

// Filtro per attrezzatura: le chiavi sono quelle del server
// (`exercise_library.EQUIPMENT_FILTERS`).
const ATTREZZI: { value: string; label: string }[] = [
  { value: "", label: "Tutti" },
  { value: "cavi", label: "Cavi" },
  { value: "macchine", label: "Macchine" },
  { value: "manubri", label: "Manubri" },
  { value: "bilanciere", label: "Bilanciere" },
  { value: "multipower", label: "Multipower" },
  { value: "corpo_libero", label: "Corpo libero" },
  { value: "elastici", label: "Elastici" },
];

export function thumbnails(ex: PlanExercise["exercise"]) {
  return ex.demo_images?.length ? ex.demo_images : ex.image_url ? [ex.image_url] : [];
}

/**
 * Cambio o aggiunta di un esercizio: le alternative come schede con
 * l'animazione, il tipo di esercizio e il primo spunto di focus muscolare —
 * abbastanza per capire di cosa si tratta prima di sceglierlo.
 *
 * Con `item` sostituisce quell'esercizio; con `addTo` ne aggiunge uno nuovo
 * in fondo al giorno. Con `inSession` (durante l'allenamento) si sceglie se
 * il cambio vale solo per oggi o anche nella scheda.
 */
export function AlternativesDialog({
  item,
  addTo,
  inSession,
  profileId,
  onClose,
  onSwapped,
  onOpenDetail,
}: {
  item?: PlanExercise;
  addTo?: { planId: number; day: string };
  /** Durante l'allenamento: `onPick` riceve l'esercizio scelto e se vale anche per la scheda. */
  inSession?: { onPick: (exercise: Alternative["exercise"], alsoInPlan: boolean) => void };
  profileId: number;
  onClose: () => void;
  onSwapped: (plan: WorkoutPlan) => void;
  onOpenDetail: (id: number) => void;
}) {
  const [alts, setAlts] = useState<Alternative[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [quanti, setQuanti] = useState(PAGINA_ALTERNATIVE);
  const [attrezzo, setAttrezzo] = useState("");
  // Durante l'allenamento: di base il cambio vale solo per oggi (macchina
  // occupata), la scheda resta com'è.
  const [ancheScheda, setAncheScheda] = useState(false);
  const originale = item?.exercise.primary_muscle ?? "";
  // Il gruppo da cui pescare: di base lo stesso, ma si può cambiare proprio
  // il muscolo allenato da questo esercizio.
  const [muscle, setMuscle] = useState(originale || GRUPPI_SOSTITUZIONE[0]);
  const cambiaMuscolo = !!item && muscle !== originale;

  useEffect(() => {
    // "Mostra altri" tiene a vista quelli già caricati; una nuova ricerca o
    // un altro gruppo ripartono dallo spinner.
    if (quanti === PAGINA_ALTERNATIVE) setAlts(null);
    setError(null);
    const q = query.trim() ? `&q=${encodeURIComponent(query.trim())}` : "";
    const m = cambiaMuscolo ? `&muscle=${encodeURIComponent(muscle)}` : "";
    const a = attrezzo ? `&equipment=${attrezzo}` : "";
    // Durante la ricerca si aspetta che l'utente smetta di scrivere.
    const timer = setTimeout(
      () => {
        api
          .get<Alternative[]>(
            addTo
              ? // Esclusi solo quelli già in questo giorno: lo stesso esercizio può stare nel Pull A e nel Pull B.
                `/workout/plans/${addTo.planId}/candidates?profile_id=${profileId}&limit=${quanti}&muscle=${encodeURIComponent(muscle)}&day=${encodeURIComponent(addTo.day)}${q}${a}`
              : `/workout/plan-exercises/${item!.id}/alternatives?profile_id=${profileId}&limit=${quanti}${q}${m}${a}`
          )
          .then(setAlts)
          .catch((e) => {
            setAlts([]);
            setError(e instanceof Error ? e.message : "Alternative non disponibili");
          });
      },
      query ? 300 : 0
    );
    return () => clearTimeout(timer);
  }, [item, addTo, profileId, query, muscle, cambiaMuscolo, quanti, attrezzo]);

  async function swap(exerciseId: number) {
    setBusy(exerciseId);
    setError(null);
    try {
      if (inSession && !ancheScheda) {
        // Solo per oggi: la scheda non cambia e nessuna preferenza viene toccata.
        const scelto = alts?.find((x) => x.exercise.id === exerciseId)?.exercise;
        if (scelto) inSession.onPick(scelto, false);
        onClose();
        return;
      }
      if (addTo) {
        onSwapped(
          await api.post<WorkoutPlan>(`/workout/plans/${addTo.planId}/exercises?profile_id=${profileId}`, {
            exercise_id: exerciseId,
            day_label: addTo.day,
          })
        );
        onClose();
        return;
      }
      const updated = await api.post<WorkoutPlan>(
        `/workout/plan-exercises/${item!.id}/swap?profile_id=${profileId}`,
        // Cambiare non vuol dire che l'esercizio tolto non piace (si varia, la
        // macchina è scomoda in quella palestra...): segnarlo sgradito lo faceva
        // sparire dalle scelte. Lo sgradito si dice dalla scheda dell'esercizio.
        { replacement_exercise_id: exerciseId, allow_muscle_change: cambiaMuscolo }
      );
      onSwapped(updated);
      if (inSession) {
        const nuovo = updated.exercises.find((e) => e.id === item!.id)?.exercise;
        if (nuovo) inSession.onPick(nuovo, true);
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sostituzione non riuscita");
    } finally {
      setBusy(null);
    }
  }

  const attuale = item?.exercise;
  const nomeMuscolo = (m: string) => MUSCLE_LABELS[m] ?? m;
  const parametri = item ? `${item.target_sets} × ${item.target_reps_min}-${item.target_reps_max} a RIR ${item.target_rir}` : "";
  const giorno = addTo ? (addTo.day.length <= 2 ? `giorno ${addTo.day}` : addTo.day) : "";

  return (
    <Modal onClose={onClose} className="max-w-3xl">
      <ModalHeader
        eyebrow={`${addTo ? "Aggiungi esercizio" : "Cambia esercizio"} · ${nomeMuscolo(muscle)}`}
        title={attuale ? `Al posto di «${exerciseName(attuale)}»` : `Nuovo esercizio per ${giorno}`}
        subtitle={
          addTo
            ? "Entra in fondo al giorno con 3 serie e ripetizioni, RIR e recupero delle fonti per quel tipo di esercizio: poi li cambi come gli altri."
            : cambiaMuscolo
            ? `Cambi gruppo: da ${nomeMuscolo(originale).toLowerCase()} a ${nomeMuscolo(muscle).toLowerCase()}. Restano ${parametri}; le serie settimanali si spostano sul nuovo muscolo.`
            : `Stesso muscolo principale: restano ${parametri}. Scegli quello in cui senti meglio il muscolo e che esegui volentieri.`
        }
        onClose={onClose}
      />

      <div className="shrink-0 space-y-2.5 border-b border-white/[0.06] px-4 py-3">
        <input
          className="input py-2 text-[13px]"
          placeholder={addTo ? "Cerca un esercizio — es. cavi, manubri, macchina, hammer" : "Cerca fra le alternative — es. cavi, manubri, macchina, hammer"}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setQuanti(PAGINA_ALTERNATIVE);
          }}
        />
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none]" role="radiogroup" aria-label="Gruppo muscolare">
          {GRUPPI_SOSTITUZIONE.map((m) => {
            const scelto = m === muscle;
            return (
              <button
                key={m}
                role="radio"
                aria-checked={scelto}
                onClick={() => {
                  setMuscle(m);
                  setQuanti(PAGINA_ALTERNATIVE);
                }}
                // Niente layoutId qui: un'animazione condivisa dentro un
                // pannello che si chiude ne blocca l'uscita.
                className={`relative shrink-0 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors duration-200 ${
                  scelto
                    ? "border-lime-400/60 bg-gradient-to-b from-lime-400 to-lime-500 text-ink-900"
                    : "border-white/10 text-white/60 hover:border-white/25 hover:text-white"
                }`}
              >
                <span className="relative">
                  {nomeMuscolo(m)}
                  {item && m === originale && !scelto && <span className="ml-1 text-white/35">· attuale</span>}
                </span>
              </button>
            );
          })}
        </div>
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none]" role="radiogroup" aria-label="Attrezzatura">
          {ATTREZZI.map((t) => {
            const scelto = t.value === attrezzo;
            return (
              <button
                key={t.value || "tutti"}
                role="radio"
                aria-checked={scelto}
                onClick={() => {
                  setAttrezzo(t.value);
                  setQuanti(PAGINA_ALTERNATIVE);
                }}
                className={`shrink-0 rounded-full border px-2.5 py-1 text-[12px] transition-colors duration-200 ${
                  scelto
                    ? "border-iris-400/60 bg-iris-400/25 text-white"
                    : "border-white/10 text-white/50 hover:border-white/25 hover:text-white"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        {inSession && (
          <OptionGroup
            ariaLabel="Dove vale il cambio"
            columns="grid-cols-2"
            value={ancheScheda ? "scheda" : "oggi"}
            onChange={(v) => setAncheScheda(v === "scheda")}
            options={[
              { value: "oggi", label: "Solo oggi", hint: "La scheda resta com'è" },
              { value: "scheda", label: "Anche nella scheda", hint: "Da qui in avanti" },
            ]}
          />
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {error && (
          <div className="mb-3">
            <Notice>{error}</Notice>
          </div>
        )}
        {!alts ? (
          <Spinner label="Cerco le alternative…" />
        ) : alts.length === 0 ? (
          !error && (
            <Empty
              title={
                query.trim()
                  ? "Nessuna alternativa con questo nome"
                  : "Nessuna alternativa disponibile con la tua attrezzatura"
              }
            />
          )
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {alts.map((a, i) => {
              const ex = a.exercise;
              const nome = exerciseName(ex);
              return (
                <motion.div
                  key={ex.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  // Solo le prime entrano una dopo l'altra: con "Mostra altri"
                  // l'ultima comparirebbe dopo secondi.
                  transition={{ delay: (i % PAGINA_ALTERNATIVE) < 8 ? (i % PAGINA_ALTERNATIVE) * 0.05 : 0.4 }}
                  className="flex flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.025] transition hover:border-lime-400/30"
                >
                  <button
                    onClick={() => onOpenDetail(ex.id)}
                    className="group relative block"
                    title="Come si esegue"
                  >
                    {/* "contain": i disegni interi, non ritagliati */}
                    <DemoAnimation images={thumbnails(ex)} alt={nome} fit="contain" className="aspect-[16/10] w-full" />
                    <div className="absolute left-2 top-2 flex flex-wrap gap-1">
                      {a.already_preferred && (
                        <span className="pill bg-lime-400 text-ink-900">tra i preferiti</span>
                      )}
                      {a.avoided && (
                        <span
                          className="pill bg-black/65 text-amber-200 backdrop-blur-md"
                          title="Sceglierlo di nuovo lo rimette fra quelli graditi"
                        >
                          {a.avoided === "replaced" ? "sostituito in passato" : "segnato da evitare"}
                        </span>
                      )}
                      {a.preserves_stimulus && (
                        <span
                          className="pill bg-black/65 text-lime-200 backdrop-blur-md"
                          title="Stessa tipologia: anche il recupero resta uguale"
                        >
                          stessa tipologia
                        </span>
                      )}
                    </div>
                    <span className="absolute bottom-2 right-2 rounded-full bg-black/65 px-2.5 py-1 text-[10.5px] text-white/90 opacity-0 backdrop-blur-md transition group-hover:opacity-100">
                      Come si esegue →
                    </span>
                  </button>
                  <div className="flex flex-1 flex-col gap-1.5 p-3.5">
                    <p className="text-[14px] font-medium leading-snug text-white">{nome}</p>
                    <p className="text-[11.5px] text-white/40">
                      {ex.is_compound ? "Multi-articolare" : "Isolamento"} ·{" "}
                      {formatEquipment(ex.equipment)}
                    </p>
                    {ex.focus_it?.[0] && (
                      <p className="text-[12px] leading-snug text-white/55">
                        <span className="text-lime-300/80">Focus:</span> {ex.focus_it[0]}
                      </p>
                    )}
                    <div className="mt-auto flex gap-2 pt-2">
                      <button
                        className="btn-ghost flex-1 px-3 py-2 text-[12.5px]"
                        onClick={() => onOpenDetail(ex.id)}
                      >
                        Esecuzione
                      </button>
                      <button
                        className="btn-primary flex-1 px-3 py-2 text-[12.5px]"
                        disabled={busy !== null}
                        onClick={() => swap(ex.id)}
                      >
                        {busy === ex.id ? (addTo ? "Aggiungo…" : "Cambio…") : addTo ? "Aggiungi" : "Scegli questo"}
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
        {/* Il server ne ha restituiti quanti chiesti: probabilmente ce ne sono altri. */}
        {alts && alts.length >= quanti && (
          <button
            onClick={() => setQuanti((n) => n + PAGINA_ALTERNATIVE)}
            className="mt-4 w-full rounded-2xl border border-white/10 bg-white/[0.03] py-3 text-[13px] font-semibold text-white/70 transition hover:border-lime-400/40 hover:text-lime-200"
          >
            Mostra altri esercizi
          </button>
        )}
      </div>

      <p className="shrink-0 border-t border-white/[0.06] px-5 py-3 text-[11.5px] leading-snug text-white/35">
        {inSession && !ancheScheda
          ? "Le serie di oggi si segnano sull'esercizio scelto; la scheda e le preferenze non cambiano."
          : addTo
          ? "Quello che aggiungi diventa un preferito: le prossime schede lo propongono per primo."
          : cambiaMuscolo
          ? "L'esercizio tolto resta disponibile per le prossime schede; quello che scegli diventa un preferito."
          : "L'esercizio sostituito non ti verrà più proposto nelle prossime schede; quello che scegli diventa un preferito."}
      </p>
    </Modal>
  );
}
