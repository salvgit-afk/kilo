"use client";

/**
 * Creazione profilo e screening di sicurezza.
 *
 * Lo screening PAR-Q+ non è un modulo burocratico da saltare: un "sì" rende
 * più prudente ogni piano generato dopo. Per questo viene presentato subito
 * dopo i dati anagrafici e con una spiegazione del perché, invece di essere
 * nascosto nelle impostazioni.
 */

import { motion } from "framer-motion";
import { useState } from "react";
import {
  ACTIVITY_LABELS,
  DIET_LABELS,
  EXPERIENCE_LABELS,
  GOAL_LABELS,
  api,
  type Profile,
} from "@/lib/api";
import { Card, Notice } from "@/components/ui";
import { NumberField } from "@/components/controls";
import { BrandMark } from "@/components/Mascot";

const SCREENING_QUESTIONS: { key: string; text: string }[] = [
  { key: "heart_condition", text: "Un medico ti ha mai detto che hai un problema cardiaco?" },
  { key: "chest_pain", text: "Provi dolore al petto a riposo o durante le attività quotidiane?" },
  {
    key: "dizziness_loss_consciousness",
    text: "Hai perso l'equilibrio per vertigini o conoscenza negli ultimi 12 mesi?",
  },
  { key: "chronic_condition", text: "Hai una diagnosi di condizione cronica (diabete, malattia renale…)?" },
  { key: "blood_pressure_heart_medication", text: "Assumi farmaci per la pressione o per il cuore?" },
  {
    key: "bone_joint_problem",
    text: "Hai un problema osseo o articolare che potrebbe peggiorare con l'attività fisica?",
  },
  { key: "pregnant_or_postpartum", text: "Sei incinta o hai partorito da poco?" },
  { key: "eating_disorder_history", text: "Hai avuto una storia di disturbi alimentari?" },
];

export function Onboarding({ onCreated }: { onCreated: (p: Profile) => void }) {
  const [step, setStep] = useState<1 | 2>(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    display_name: "",
    birth_date: "1996-01-01",
    sex: "male",
    height_cm: 175,
    weight_kg: 75,
    goal: "hypertrophy",
    experience_level: "beginner",
    activity_level: "moderately_active",
    training_days_per_week: 3,
    diet_type: "omnivore",
    available_equipment: "",
  });

  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const anyYes = Object.values(answers).some(Boolean);

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    setSaving(true);
    setError(null);
    try {
      const profile = await api.post<Profile>("/profile", {
        ...form,
        available_equipment: form.available_equipment.trim() || null,
      });
      await api.post(`/profile/${profile.id}/screening`, answers);
      onCreated(profile);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore durante il salvataggio");
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-10">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-7 text-center"
      >
        <div className="mx-auto mb-4 w-fit">
          <BrandMark size={68} mood="happy" />
        </div>
        <h1 className="text-[28px] font-semibold tracking-tight text-white">
          Creiamo il tuo profilo
        </h1>
        <p className="mx-auto mt-2 max-w-lg text-[13.5px] leading-relaxed text-white/45">
          Sono i dati da cui calcolo target calorici, fabbisogno proteico e volume di
          allenamento. Puoi modificarli quando vuoi.
        </p>
      </motion.div>

      <Card className="overflow-hidden">
        <div className="flex border-b border-white/[0.06]">
          {[
            { n: 1, label: "I tuoi dati" },
            { n: 2, label: "Sicurezza" },
          ].map((s) => (
            <div
              key={s.n}
              className={`relative flex-1 px-5 py-3.5 text-center text-[12.5px] font-medium ${
                step === s.n ? "text-white" : "text-white/35"
              }`}
            >
              <span className="mr-2 inline-grid h-5 w-5 place-items-center rounded-full text-[10px] ring-1 ring-white/15">
                {s.n}
              </span>
              {s.label}
              {step === s.n && (
                <motion.span
                  layoutId="step-underline"
                  className="absolute inset-x-6 bottom-0 h-px bg-lime-400"
                />
              )}
            </div>
          ))}
        </div>

        {step === 1 ? (
          <div className="space-y-4 p-5">
            <div>
              <label className="label">Come ti chiami</label>
              <input
                className="input"
                value={form.display_name}
                onChange={(e) => set("display_name", e.target.value)}
                placeholder="Il tuo nome"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Data di nascita</label>
                <input
                  type="date"
                  className="input"
                  value={form.birth_date}
                  onChange={(e) => set("birth_date", e.target.value)}
                />
              </div>
              <div>
                <label className="label">Sesso biologico</label>
                <select
                  className="input"
                  value={form.sex}
                  onChange={(e) => set("sex", e.target.value)}
                >
                  <option value="male">Uomo</option>
                  <option value="female">Donna</option>
                </select>
                <p className="mt-1 text-[10.5px] text-white/25">
                  Serve alla formula del metabolismo basale
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Altezza</label>
                <NumberField
                  value={form.height_cm}
                  onChange={(v) => set("height_cm", v)}
                  min={120}
                  max={230}
                  suffix="cm"
                  ariaLabel="Altezza in centimetri"
                />
              </div>
              <div>
                <label className="label">Peso</label>
                <NumberField
                  value={form.weight_kg}
                  onChange={(v) => set("weight_kg", v)}
                  min={30}
                  max={300}
                  decimals={1}
                  suffix="kg"
                  ariaLabel="Peso in chilogrammi"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Obiettivo</label>
                <select
                  className="input"
                  value={form.goal}
                  onChange={(e) => set("goal", e.target.value)}
                >
                  {Object.entries(GOAL_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Esperienza</label>
                <select
                  className="input"
                  value={form.experience_level}
                  onChange={(e) => set("experience_level", e.target.value)}
                >
                  {Object.entries(EXPERIENCE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Attività fuori palestra</label>
                <select
                  className="input"
                  value={form.activity_level}
                  onChange={(e) => set("activity_level", e.target.value)}
                >
                  {Object.entries(ACTIVITY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Alimentazione</label>
                <select
                  className="input"
                  value={form.diet_type}
                  onChange={(e) => set("diet_type", e.target.value)}
                >
                  {Object.entries(DIET_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="label">
                Giorni di allenamento a settimana — {form.training_days_per_week}
              </label>
              <input
                type="range"
                min={1}
                max={7}
                value={form.training_days_per_week}
                onChange={(e) => set("training_days_per_week", Number(e.target.value))}
                className="w-full accent-lime-400"
              />
            </div>

            <div>
              <label className="label">Attrezzatura disponibile (facoltativo)</label>
              <input
                className="input"
                value={form.available_equipment}
                onChange={(e) => set("available_equipment", e.target.value)}
                placeholder="es. manubri, panca — vuoto = palestra attrezzata"
              />
            </div>

            <button
              className="btn-primary w-full"
              disabled={!form.display_name.trim() || !form.height_cm || !form.weight_kg}
              onClick={() => setStep(2)}
            >
              Continua
            </button>
          </div>
        ) : (
          <div className="space-y-4 p-5">
            <p className="text-[13px] leading-relaxed text-white/55">
              Sono le domande del <strong className="text-white/80">PAR-Q+</strong>, lo
              strumento standard di screening prima di iniziare a allenarsi. Rispondere
              «sì» non ti blocca: rende più prudenti i piani che genero.
            </p>

            <div className="space-y-1.5">
              {SCREENING_QUESTIONS.map((q) => (
                <label
                  key={q.key}
                  className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3.5 py-3 transition ${
                    answers[q.key]
                      ? "border-amber-300/25 bg-amber-300/[0.07]"
                      : "border-white/[0.07] bg-white/[0.02] hover:bg-white/[0.045]"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 shrink-0 accent-amber-400"
                    checked={!!answers[q.key]}
                    onChange={(e) =>
                      setAnswers((a) => ({ ...a, [q.key]: e.target.checked }))
                    }
                  />
                  <span className="text-[13px] leading-snug text-white/75">{q.text}</span>
                </label>
              ))}
            </div>

            {anyYes && (
              <Notice>
                Hai risposto «sì» ad almeno una domanda. I piani che genero partiranno dal
                volume più basso previsto per il tuo livello, e ti consiglio di far
                valutare il programma da un medico prima di aumentarlo.
              </Notice>
            )}

            {error && (
              <p className="rounded-xl border border-rose-400/25 bg-rose-400/10 px-3.5 py-2.5 text-[12.5px] text-rose-200">
                {error}
              </p>
            )}

            <div className="flex gap-2.5">
              <button className="btn-ghost flex-1" onClick={() => setStep(1)}>
                Indietro
              </button>
              <button className="btn-primary flex-[2]" disabled={saving} onClick={submit}>
                {saving ? "Creo il profilo…" : "Inizia"}
              </button>
            </div>
          </div>
        )}
      </Card>

      <p className="mt-5 text-center text-[11.5px] leading-relaxed text-white/25">
        L'agente propone e spiega. Non sostituisce un medico né un professionista della
        nutrizione.
      </p>
    </div>
  );
}
