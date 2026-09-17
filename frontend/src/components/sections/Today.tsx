"use client";

/**
 * Riepilogo della giornata: il primo schermo che si apre.
 *
 * In cima c'è **il coach per oggi**: poche indicazioni calcolate sui dati di
 * adesso (diario, scheda, pesate), ognuna con l'azione che la risolve. Non
 * servono chiamate all'LLM per dire "ti mancano 40 g di proteine": sono
 * sottrazioni, e restano istantanee e sempre coerenti con i numeri mostrati.
 */

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { GOAL_LABELS, api, type Diary, type Profile, type WorkoutPlan } from "@/lib/api";
import { askCoach } from "@/lib/coach";
import { Card, CardHeader, Notice, ProgressRing, StatBar, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import type { SectionId } from "@/components/Shell";
import { Mascot } from "@/components/Mascot";
import { KiloNote } from "@/components/KiloNote";

type WeightPoint = { date: string; weight_kg: number };

type BriefingItem = {
  key: string;
  tone: "lime" | "iris" | "amber";
  title: string;
  text: string;
  action?: { label: string; run: () => void };
};

const TONE: Record<BriefingItem["tone"], string> = {
  lime: "border-lime-400/20 bg-lime-400/[0.05]",
  iris: "border-iris-400/20 bg-iris-400/[0.06]",
  amber: "border-amber-300/20 bg-amber-300/[0.05]",
};

const DOMANDE = [
  "Cosa mangio stasera per chiudere i macro?",
  "Perché la mia scheda è fatta così?",
  "Come capisco se sto recuperando bene?",
];

const GIORNO_MS = 86_400_000;

export function Today({
  profile,
  onNavigate,
}: {
  profile: Profile;
  onNavigate: (s: SectionId) => void;
}) {
  const [diary, setDiary] = useState<Diary | null>(null);
  const [plan, setPlan] = useState<WorkoutPlan | null>(null);
  const [lastWeight, setLastWeight] = useState<WeightPoint | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<Diary>(`/nutrition/diary?profile_id=${profile.id}`),
      api.get<WorkoutPlan | null>(`/workout/plans/active?profile_id=${profile.id}`),
      api.get<WeightPoint[]>(`/profile/${profile.id}/weight?limit=1`).catch(() => []),
    ])
      .then(([d, p, w]) => {
        setDiary(d);
        setPlan(p);
        setLastWeight(w[0] ?? null);
      })
      .finally(() => setLoading(false));
  }, [profile.id]);

  if (loading) return <Spinner label="Carico la giornata…" />;

  const ora = new Date().getHours();
  const saluto = ora < 12 ? "Buongiorno" : ora < 18 ? "Buon pomeriggio" : "Buonasera";
  const days = plan ? [...new Set(plan.exercises.map((e) => e.day_label))] : [];

  // --- Il coach per oggi -----------------------------------------------------
  const briefing: BriefingItem[] = [];

  if (diary) {
    const mangiato = diary.totals.kcal ?? 0;
    const proteine = Math.round(diary.remaining.protein_g ?? 0);
    const kcal = Math.round(diary.remaining.kcal ?? 0);
    if (mangiato === 0) {
      briefing.push({
        key: "diario",
        tone: "iris",
        title: "Diario ancora vuoto",
        text: `Il target di oggi è ${Math.round(diary.targets.target_kcal)} kcal con ${Math.round(
          diary.targets.protein_g
        )} g di proteine.`,
        action: { label: "Registra un pasto", run: () => onNavigate("diario") },
      });
    } else if (proteine > 5) {
      briefing.push({
        key: "proteine",
        tone: "lime",
        title: `Mancano ${proteine} g di proteine`,
        text:
          kcal > 0
            ? `Ti restano ${kcal} kcal: nel diario trovi alimenti e porzioni calcolati per chiuderle.`
            : "Le calorie sono già al completo: domani sposta una parte verso fonti più proteiche.",
        action: { label: "Come le chiudo?", run: () => onNavigate("diario") },
      });
    } else {
      briefing.push({
        key: "proteine",
        tone: "lime",
        title: "Proteine coperte",
        text: kcal > 0 ? `Ti restano ${kcal} kcal per il resto della giornata.` : "Target di oggi raggiunto.",
      });
    }
  }

  if (!plan) {
    briefing.push({
      key: "scheda",
      tone: "amber",
      title: "Nessuna scheda attiva",
      text: "La costruisco sui tuoi giorni, la tua esperienza e gli esercizi che preferisci.",
      action: { label: "Generala", run: () => onNavigate("scheda") },
    });
  } else {
    // Il momento di "fare il punto" lo segnala la nota di Kilo in cima, con
    // la soglia delle fonti: qui resta il riepilogo della scheda.
    briefing.push({
      key: "scheda",
      tone: "lime",
      title: plan.name,
      text: `${days.length} giornate: ${days.join(", ")}.`,
      action: { label: "Apri la scheda", run: () => onNavigate("scheda") },
    });
  }

  const giorniDallaPesata = lastWeight
    ? Math.floor((Date.now() - new Date(lastWeight.date).getTime()) / GIORNO_MS)
    : null;
  if (!lastWeight || (giorniDallaPesata ?? 0) >= 4) {
    briefing.push({
      key: "peso",
      tone: "amber",
      title: lastWeight ? `Ultima pesata ${giorniDallaPesata} giorni fa` : "Nessuna pesata registrata",
      text: "Con 3-4 pesate a settimana la tendenza del peso diventa leggibile.",
      action: { label: "Registra il peso", run: () => onNavigate("progressi") },
    });
  }

  return (
    <>
      <PageHeader
        eyebrow={new Date().toLocaleDateString("it-IT", {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
        title={`${saluto}, ${profile.display_name}`}
        description={`Obiettivo: ${GOAL_LABELS[profile.goal] ?? profile.goal} · ${
          profile.training_days_per_week
        } allenamenti a settimana`}
      />

      <KiloNote section="oggi" onNavigate={onNavigate} />

      <Card className="mb-4">
        <div className="flex items-center gap-3.5 border-b border-white/[0.06] px-5 py-4">
          <Mascot size={48} mood="happy" />
          <div className="min-w-0 flex-1">
            <h2 className="text-[15.5px] font-semibold text-white">Kilo per oggi</h2>
            <p className="text-[12.5px] text-white/45">
              Calcolato adesso sui tuoi dati: diario, scheda e pesate.
            </p>
          </div>
        </div>
        <div className="grid gap-2.5 p-4 md:grid-cols-3">
          {briefing.map((item, i) => (
            <motion.div
              key={item.key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 + i * 0.06 }}
              className={`flex flex-col rounded-xl border px-3.5 py-3 ${TONE[item.tone]}`}
            >
              <p className="text-[13.5px] font-medium text-white">{item.title}</p>
              <p className="mt-1 flex-1 text-[12.5px] leading-snug text-white/55">{item.text}</p>
              {item.action && (
                <button
                  onClick={item.action.run}
                  className="mt-2.5 self-start text-[12.5px] font-medium text-lime-300 transition hover:translate-x-0.5 hover:text-lime-200"
                >
                  {item.action.label} →
                </button>
              )}
            </motion.div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.06] px-4 py-3">
          <span className="mr-1 text-[11.5px] text-white/35">Chiedimi</span>
          {DOMANDE.map((q) => (
            <button
              key={q}
              onClick={() => askCoach(q, "Sezione Oggi")}
              className="rounded-lg border border-iris-400/20 bg-iris-400/[0.06] px-2.5 py-1.5 text-[12px] text-iris-100/85 transition hover:border-iris-400/40 hover:bg-iris-400/[0.13]"
            >
              {q}
            </button>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Card hover>
          <CardHeader
            title="Nutrizione di oggi"
            action={
              <button
                onClick={() => onNavigate("diario")}
                className="text-[12.5px] text-lime-300/80 transition hover:text-lime-200"
              >
                Apri diario →
              </button>
            }
          />
          {diary && (
            <div className="flex flex-col items-center gap-5 px-5 py-5 sm:flex-row">
              <ProgressRing
                value={diary.progress.kcal ?? 0}
                size={128}
                label={`${Math.round(diary.totals.kcal ?? 0)}`}
                sublabel={`di ${Math.round(diary.targets.target_kcal)} kcal`}
              />
              <div className="w-full flex-1 space-y-3">
                <StatBar label="Proteine" value={diary.totals.protein_g ?? 0} target={diary.targets.protein_g} tone="lime" />
                <StatBar label="Carboidrati" value={diary.totals.carbs_g ?? 0} target={diary.targets.carbs_g} tone="iris" />
                <StatBar label="Grassi" value={diary.totals.fat_g ?? 0} target={diary.targets.fat_g} tone="rose" />
              </div>
            </div>
          )}
        </Card>

        <Card hover delay={0.05}>
          <CardHeader
            title="Allenamento"
            action={
              <button
                onClick={() => onNavigate("scheda")}
                className="text-[12.5px] text-lime-300/80 transition hover:text-lime-200"
              >
                Apri scheda →
              </button>
            }
          />
          {plan ? (
            <div className="px-5 py-5">
              <p className="mb-4 text-[13px] text-white/55">{plan.name}</p>
              <div className="grid grid-cols-2 gap-2.5">
                {days.map((d, i) => {
                  const count = plan.exercises.filter((e) => e.day_label === d).length;
                  return (
                    <motion.button
                      key={d}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.1 + i * 0.05 }}
                      onClick={() => onNavigate("scheda")}
                      className="group rounded-xl border border-white/[0.07] bg-white/[0.025] px-3.5 py-3 text-left transition hover:border-lime-400/25 hover:bg-lime-400/[0.05]"
                    >
                      <p className="text-[13px] font-medium text-white/85">{d}</p>
                      <p className="text-[11.5px] text-white/35">{count} esercizi</p>
                    </motion.button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="px-5 py-8 text-center">
              <p className="mb-3 text-[13px] text-white/45">Non hai ancora una scheda</p>
              <button className="btn-primary" onClick={() => onNavigate("scheda")}>
                Generane una
              </button>
            </div>
          )}
        </Card>
      </div>

      {diary && diary.targets.warnings.length > 0 && (
        <div className="mt-4 space-y-2.5">
          {diary.targets.warnings.map((w, i) => (
            <Notice key={i}>{w}</Notice>
          ))}
        </div>
      )}

      <Card className="mt-4" delay={0.15}>
        <CardHeader
          title="Perché questi numeri"
          subtitle="Calcolati dai parametri delle fonti, non dalla memoria di un modello"
        />
        <p className="px-5 py-4 text-[13px] leading-relaxed text-white/60">
          {diary?.targets.rationale}
        </p>
      </Card>
    </>
  );
}
