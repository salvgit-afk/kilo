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
import { Field, NumberField, OptionGroup } from "@/components/controls";
import { PageHeader } from "@/components/Shell";
import { REMINDER_HOUR, reminderSettings } from "@/components/ReminderBanner";
import { PushSettings } from "@/components/PushSettings";

export function ProfileSection({
  profile,
  email,
  isAdmin = false,
  onUpdated,
  onReset,
}: {
  profile: Profile;
  email?: string;
  isAdmin?: boolean;
  onUpdated: (p: Profile) => void;
  onReset: () => void;
}) {
  const [form, setForm] = useState(() => initialForm(profile));
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<CatalogStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [reminders, setReminders] = useState(true);

  useEffect(() => {
    api.get<CatalogStatus>("/catalog/status").then(setCatalog);
    setReminders(reminderSettings.enabled());
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader
            title="Dati che alimentano i calcoli"
            subtitle="Cambiarli aggiorna target calorici, proteici e volume"
            action={
              dirty ? (
                <button className="btn-primary px-4 py-2" disabled={saving || !form.weight_kg} onClick={save}>
                  {saving ? "Salvo…" : "Salva"}
                </button>
              ) : undefined
            }
          />
          <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 sm:p-5">
            <Field title="Peso attuale">
              <NumberField
                value={form.weight_kg}
                onChange={(v) => set("weight_kg", v)}
                min={30}
                max={300}
                decimals={1}
                suffix="kg"
                ariaLabel="Peso attuale in chilogrammi"
              />
            </Field>
            <Field title="Esperienza">
              <OptionGroup
                ariaLabel="Esperienza"
                columns="grid-cols-3"
                value={form.experience_level}
                onChange={(v) => set("experience_level", v)}
                options={Object.entries(EXPERIENCE_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Field>
            <Field title="Obiettivo" className="sm:col-span-2">
              <OptionGroup
                ariaLabel="Obiettivo"
                columns="grid-cols-2 sm:grid-cols-3"
                value={form.goal}
                onChange={(v) => set("goal", v)}
                options={Object.entries(GOAL_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Field>
            <Field title="Attività fuori palestra" className="sm:col-span-2">
              <OptionGroup
                ariaLabel="Attività fuori palestra"
                columns="grid-cols-2 sm:grid-cols-3"
                value={form.activity_level}
                onChange={(v) => set("activity_level", v)}
                options={Object.entries(ACTIVITY_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Field>
            <Field title="Alimentazione">
              <OptionGroup
                ariaLabel="Alimentazione"
                columns="grid-cols-3"
                value={form.diet_type}
                onChange={(v) => set("diet_type", v)}
                options={Object.entries(DIET_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Field>
            <Field title="Giorni di allenamento a settimana">
              <OptionGroup
                ariaLabel="Giorni a settimana"
                mono
                columns="grid-cols-7"
                value={form.training_days_per_week}
                onChange={(v) => set("training_days_per_week", v)}
                options={[1, 2, 3, 4, 5, 6, 7].map((n) => ({ value: n, label: n }))}
              />
            </Field>
            <Field
              title="Attrezzatura disponibile"
              hint="Gli esercizi a corpo libero restano sempre disponibili."
              className="sm:col-span-2"
            >
              <input
                className="input"
                value={form.available_equipment}
                onChange={(e) => set("available_equipment", e.target.value)}
                placeholder="vuoto = palestra attrezzata"
              />
            </Field>
          </div>
          {/* Con qualcosa da salvare: "Salva" in alto e, in fondo, lo stesso
              piede dei pannelli. */}
          {dirty && (
            <div className="flex items-center gap-2 border-t border-white/[0.06] bg-ink-900/50 px-4 py-3 sm:px-5">
              <button className="btn-ghost flex-1 justify-center" onClick={() => setForm(initialForm(profile))} disabled={saving}>
                Annulla
              </button>
              <button className="btn-primary flex-[1.6] justify-center" disabled={saving || !form.weight_kg} onClick={save}>
                {saving ? "Salvo…" : "Salva le modifiche"}
              </button>
            </div>
          )}
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
              {/* Riservato all'amministratore: scarica le fonti e avvia la
                  traduzione di tutto il catalogo. */}
              {isAdmin && (
                <button className="btn-ghost w-full" disabled={syncing} onClick={syncCatalog}>
                  {syncing ? "Sincronizzo…" : "Aggiorna catalogo"}
                </button>
              )}
            </div>
          </Card>

          <Card delay={0.07}>
            <CardHeader title="Notifiche sul telefono" subtitle="Anche con Kilo chiuso" />
            <div className="px-5 py-4">
              <PushSettings />
            </div>
          </Card>

          <Card delay={0.08}>
            <CardHeader title="Promemoria" subtitle="Banner in cima alla pagina" />
            <div className="space-y-3 px-5 py-4">
              <label className="flex cursor-pointer items-center justify-between gap-3">
                <span className="text-[13px] text-white/75">Ricordami cosa non ho segnato</span>
                <button
                  role="switch"
                  aria-checked={reminders}
                  onClick={() => {
                    reminderSettings.setEnabled(!reminders);
                    setReminders(!reminders);
                  }}
                  className={`relative h-6 w-11 shrink-0 rounded-full border transition ${
                    reminders ? "border-lime-400/60 bg-lime-400/80" : "border-white/15 bg-white/[0.08]"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow transition-all ${
                      reminders ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
              </label>
              <p className="text-[11.5px] leading-relaxed text-white/30">
                Dalle {REMINDER_HOUR}, se non hai ancora segnato gli integratori dichiarati o i
                pasti (solo se usi il diario). La X lo nasconde fino al giorno dopo. La scelta
                vale per questo browser.
              </p>
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

function initialForm(profile: Profile) {
  return {
    weight_kg: profile.weight_kg as number | null,
    goal: profile.goal,
    experience_level: profile.experience_level,
    activity_level: profile.activity_level,
    training_days_per_week: profile.training_days_per_week,
    diet_type: profile.diet_type,
    available_equipment: profile.available_equipment ?? "",
  };
}
