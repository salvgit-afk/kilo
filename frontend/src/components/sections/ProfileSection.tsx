"use client";

/**
 * Profilo: dati che alimentano tutti i calcoli, e stato del catalogo.
 *
 * Modificare peso o obiettivo cambia TDEE e target proteico, quindi il
 * riquadro mostra i valori derivati accanto ai campi: si vede subito cosa
 * si sta spostando.
 */

import { useEffect, useState } from "react";
import {
  ACTIVITY_LABELS,
  DIET_LABELS,
  EXPERIENCE_LABELS,
  GOAL_LABELS,
  api,
  type CatalogStatus,
  type Profile,
} from "@/lib/api";
import { Card, CardHeader, Notice } from "@/components/ui";
import { NumberField } from "@/components/controls";
import { PageHeader } from "@/components/Shell";

export function ProfileSection({
  profile,
  email,
  onUpdated,
  onReset,
}: {
  profile: Profile;
  email?: string;
  onUpdated: (p: Profile) => void;
  onReset: () => void;
}) {
  const [form, setForm] = useState({
    weight_kg: profile.weight_kg,
    goal: profile.goal,
    experience_level: profile.experience_level,
    activity_level: profile.activity_level,
    training_days_per_week: profile.training_days_per_week,
    diet_type: profile.diet_type,
    available_equipment: profile.available_equipment ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<CatalogStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    api.get<CatalogStatus>("/catalog/status").then(setCatalog);
  }, []);

  const dirty =
    form.weight_kg !== profile.weight_kg ||
    form.goal !== profile.goal ||
    form.experience_level !== profile.experience_level ||
    form.activity_level !== profile.activity_level ||
    form.training_days_per_week !== profile.training_days_per_week ||
    form.diet_type !== profile.diet_type ||
    form.available_equipment !== (profile.available_equipment ?? "");

  async function save() {
    setSaving(true);
    try {
      onUpdated(
        await api.patch<Profile>(`/profile/${profile.id}`, {
          ...form,
          available_equipment: form.available_equipment.trim() || null,
        })
      );
    } finally {
      setSaving(false);
    }
  }

  async function syncCatalog() {
    setSyncing(true);
    try {
      await api.post("/catalog/sync-exercises");
      setCatalog(await api.get<CatalogStatus>("/catalog/status"));
    } finally {
      setSyncing(false);
    }
  }

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <>
      <PageHeader
        eyebrow="Profilo"
        title={profile.display_name}
        description={`${profile.age} anni · ${profile.height_cm} cm · metabolismo basale ${Math.round(
          profile.bmr ?? 0
        )} kcal · fabbisogno ${Math.round(profile.tdee ?? 0)} kcal`}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader
            title="Dati che alimentano i calcoli"
            subtitle="Cambiarli aggiorna target calorici, proteici e volume"
            action={
              dirty ? (
                <button
                  className="btn-primary px-3 py-1.5"
                  disabled={saving || !form.weight_kg}
                  onClick={save}
                >
                  {saving ? "Salvo…" : "Salva"}
                </button>
              ) : undefined
            }
          />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <div>
              <label className="label">Peso attuale</label>
              <NumberField
                value={form.weight_kg}
                onChange={(v) => set("weight_kg", v)}
                min={30}
                max={300}
                decimals={1}
                suffix="kg"
                ariaLabel="Peso attuale in chilogrammi"
              />
            </div>
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
            <div>
              <label className="label">
                Giorni a settimana — {form.training_days_per_week}
              </label>
              <input
                type="range"
                min={1}
                max={7}
                value={form.training_days_per_week}
                onChange={(e) => set("training_days_per_week", Number(e.target.value))}
                className="mt-3 w-full accent-lime-400"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Attrezzatura disponibile</label>
              <input
                className="input"
                value={form.available_equipment}
                onChange={(e) => set("available_equipment", e.target.value)}
                placeholder="vuoto = palestra attrezzata"
              />
              <p className="mt-1.5 text-[11px] text-white/30">
                Gli esercizi a corpo libero restano sempre disponibili.
              </p>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <Card delay={0.05}>
            <CardHeader title="Catalogo locale" subtitle="Esercizi e alimenti in cache" />
            <div className="space-y-3 px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[12.5px] text-white/50">Esercizi</span>
                <span className="font-mono text-[15px] tabular-nums text-white">
                  {catalog?.exercises_cached ?? "—"}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-[12.5px] text-white/50">Alimenti</span>
                <span className="font-mono text-[15px] tabular-nums text-white">
                  {catalog?.ingredients_cached ?? "—"}
                </span>
              </div>
              <p className="text-[11.5px] leading-relaxed text-white/30">
                Il catalogo esercizi unisce Everkinetic (disegni, CC BY-SA 4.0), RepDB
                (illustrazioni) e free-exercise-db (foto, pubblico dominio), senza doppioni,
                più alcuni esercizi scritti da Kilo. Sta in locale: le schede si generano anche
                quando le fonti non sono raggiungibili. Gli esercizi nuovi restano in inglese
                finché la traduzione in background non è pronta.{" "}
                <a
                  href="https://repdb.co"
                  target="_blank"
                  rel="noreferrer"
                  className="underline decoration-white/20 underline-offset-2 hover:text-white/60"
                >
                  Exercise data by RepDB (repdb.co)
                </a>
              </p>
              <button className="btn-ghost w-full" disabled={syncing} onClick={syncCatalog}>
                {syncing ? "Sincronizzo…" : "Aggiorna catalogo"}
              </button>
            </div>
          </Card>

          <Card delay={0.1}>
            <CardHeader title="Account" subtitle={email} />
            <div className="space-y-3 px-5 py-4">
              <Notice>
                L'agente propone e spiega. Non sostituisce un medico né un professionista
                della nutrizione.
              </Notice>
              <button
                onClick={onReset}
                className="w-full rounded-xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-2.5 text-[13px] text-rose-200/80 transition hover:bg-rose-400/[0.12]"
              >
                Esci dall'account
              </button>
              <p className="text-[11px] leading-relaxed text-white/25">
                I tuoi dati restano salvati nel database e li ritrovi al prossimo
                accesso: esci solo dalla sessione su questo browser.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
