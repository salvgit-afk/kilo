"use client";

/**
 * Sezione integratori — facoltativa.
 *
 * L'agente non propone integratori. Qui fa tre cose, separate anche
 * visivamente:
 *  - **Diario**: l'utente segna le assunzioni di ogni giorno e vede da
 *    quanti giorni prende ciascun integratore e se ne ha saltato qualcuno;
 *  - **I tuoi**: valuta ciò che l'utente dichiara, e la valutazione si
 *    aggiorna *mentre* si scrive la dose, senza dover salvare per scoprire
 *    che è fuori range;
 *  - **Cosa dicono le fonti**: consultazione, integratore per integratore ed
 *    esito per esito, anche quando l'evidenza è debole o assente. Nessuna
 *    voce viene evidenziata come "da prendere".
 *
 * L'evidenza viene mostrata **per esito** e non come etichetta unica: la
 * glutammina non fa crescere il muscolo e riduce marcatori intestinali ad
 * alte dosi, e riportarne solo metà darebbe un'immagine falsa.
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  SUPPLEMENT_LABELS,
  api,
  notifyLogged,
  type Supplement,
  type SupplementInfo,
} from "@/lib/api";
import { Card, EvidenceBadge, Notice, SourceTags, Spinner } from "@/components/ui";
import { PageHeader } from "@/components/Shell";
import { AskCoachButton, Modal, ModalHeader, NumberField } from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { SupplementDiary } from "@/components/SupplementDiary";
import { KiloNote } from "@/components/KiloNote";

const EVIDENCE_DOT: Record<string, string> = {
  strong: "bg-lime-400",
  moderate: "bg-iris-400",
  weak: "bg-amber-400",
  unknown: "bg-white/25",
};

const label = (kind: string) => SUPPLEMENT_LABELS[kind] ?? kind;

function doseText(s: Supplement) {
  return s.dose_amount
    ? `${s.dose_amount.toLocaleString("it-IT")} ${s.dose_unit ?? ""} × ${s.doses_per_day}/giorno`
    : "dose non indicata";
}

export function Supplements({ profileId }: { profileId: number }) {
  const [tab, setTab] = useState<"diary" | "mine" | "explore">("diary");
  const [items, setItems] = useState<Supplement[] | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [coffee, setCoffee] = useState<number | null>(0);
  const [removing, setRemoving] = useState<number | null>(null);

  const load = useCallback(async () => {
    setItems(
      await api.get<Supplement[]>(
        `/supplements?profile_id=${profileId}&other_caffeine_mg=${coffee ?? 0}`
      )
    );
  }, [profileId, coffee]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="Facoltativo"
        title="Integratori"
        description="Se ne usi, li valuto rispetto alle fonti e li sommo ai tuoi totali. Se non ne usi, va benissimo così."
        action={
          <button className="btn-primary" onClick={() => setAdding("")}>
            Dichiara integratore
          </button>
        }
      />

      <KiloNote section="integratori" />

      <div className="mb-4 inline-flex rounded-xl border border-white/10 bg-white/[0.03] p-1">
        {(
          [
            ["diary", "Diario"],
            ["mine", `I tuoi${items ? ` · ${items.length}` : ""}`],
            ["explore", "Cosa dicono le fonti"],
          ] as const
        ).map(([id, text]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`relative rounded-lg px-3.5 py-2 text-[12.5px] font-medium transition ${
              tab === id ? "text-ink-900" : "text-white/55 hover:text-white"
            }`}
          >
            {tab === id && (
              <motion.span
                layoutId="supp-tab"
                className="absolute inset-0 rounded-lg bg-gradient-to-b from-lime-400 to-lime-500"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <span className="relative">{text}</span>
          </button>
        ))}
      </div>

      {tab === "explore" ? (
        <Explorer profileId={profileId} onDeclare={(kind) => setAdding(kind)} />
      ) : !items ? (
        <Spinner label="Carico…" />
      ) : items.length === 0 ? (
        <Card>
          <div className="grid place-items-center px-6 py-12 text-center">
            <Mascot size={58} interactive />
            <p className="mt-3 text-[14px] text-white/75">Non hai dichiarato integratori</p>
            <p className="mt-1.5 max-w-md text-[12.5px] leading-relaxed text-white/40">
              E non te ne suggerisco: nessun piano cambia perché non ne prendi. Se invece ne
              usi, dichiararli mi permette di sommarli ai totali e di dirti se le dosi sono nei
              range delle fonti.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <button className="btn-primary" onClick={() => setAdding("")}>
                Ne uso uno: valutalo
              </button>
              <button className="btn-ghost" onClick={() => setTab("explore")}>
                Leggi cosa dicono le fonti
              </button>
            </div>
          </div>
        </Card>
      ) : tab === "diary" ? (
        <SupplementDiary profileId={profileId} />
      ) : (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-center gap-3 px-5 py-3.5">
              <span className="text-[12.5px] text-white/60">Caffeina da caffè e bevande oggi</span>
              <NumberField
                value={coffee}
                onChange={setCoffee}
                min={0}
                max={2000}
                step={50}
                suffix="mg"
                size="sm"
                ariaLabel="Caffeina da altre fonti"
                className="w-36"
              />
              <span className="text-[12px] text-white/35">
                un espresso ne ha circa 60-80: valutare solo il pre-workout ignorerebbe spesso la
                parte più grossa del totale
              </span>
            </div>
          </Card>

          {items.map((s, i) => (
            <motion.div
              key={s.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              className="glass sheen overflow-hidden"
            >
              <div className="flex items-start justify-between gap-4 border-b border-white/[0.06] px-5 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[15px] font-semibold text-white">{label(s.kind)}</h3>
                    <EvidenceBadge evidence={s.evidence} />
                    {s.dose_in_range === true && (
                      <span className="pill border border-lime-400/20 bg-lime-400/10 text-lime-200">
                        dose nel range
                      </span>
                    )}
                    {s.dose_in_range === false && (
                      <span className="pill border border-amber-300/20 bg-amber-300/10 text-amber-100">
                        dose fuori range
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[12px] text-white/35">
                    {s.product_name ? `${s.product_name} · ` : ""}
                    {doseText(s)}
                  </p>
                </div>
                <button
                  onClick={() => setRemoving(s.id)}
                  aria-label="Rimuovi"
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-white/30 transition hover:bg-rose-400/10 hover:text-rose-300"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                    <path d="M7 6V4h10v2h4v2h-2v12H5V8H3V6h4Zm2 4v8h2v-8H9Zm4 0v8h2v-8h-2Z" />
                  </svg>
                </button>
              </div>

              {/* Rimuovere cancella anche lo storico del diario: si chiede conferma. */}
              {removing === s.id && (
                <div className="flex flex-wrap items-center gap-2.5 border-b border-rose-400/15 bg-rose-400/[0.05] px-5 py-3">
                  <p className="flex-1 text-[12.5px] text-rose-100/80">
                    Rimuovo {label(s.kind)} e i giorni segnati nel diario?
                  </p>
                  <button className="btn-ghost px-3 py-1.5 text-[12px]" onClick={() => setRemoving(null)}>
                    Annulla
                  </button>
                  <button
                    className="rounded-lg border border-rose-400/30 bg-rose-400/15 px-3 py-1.5 text-[12px] font-medium text-rose-100 transition hover:bg-rose-400/25"
                    onClick={async () => {
                      await api.del(`/supplements/${s.id}`);
                      setRemoving(null);
                      notifyLogged();
                      load();
                    }}
                  >
                    Rimuovi
                  </button>
                </div>
              )}

              <div className="space-y-3.5 px-5 py-4">
                {s.safety_flag && <Notice>Attenzione: {s.safety_flag}.</Notice>}
                <p className="text-[13px] leading-relaxed text-white/70">{s.message}</p>
                {s.benefits.length > 0 && <Benefits items={s.benefits} />}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <SourceTags tags={s.knowledge_tags} />
                  <AskCoachButton
                    size="sm"
                    question={`Assumo ${label(s.kind)} (${doseText(s)}). Per il mio obiettivo ha senso? Cosa dicono le fonti sul dosaggio?`}
                    context="Sezione Integratori"
                  />
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {adding !== null && (
          <AddDialog
            profileId={profileId}
            initialKind={adding}
            otherCaffeine={coffee ?? 0}
            onClose={() => setAdding(null)}
            onAdded={() => {
              setAdding(null);
              setTab("mine");
              notifyLogged();
              load();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function Benefits({ items, highlight }: { items: SupplementInfo["benefits"]; highlight?: string | null }) {
  return (
    <div>
      <p className="label">Evidenza per esito</p>
      <div className="space-y-1.5">
        {items.map((b) => (
          <div
            key={b.domain}
            className={`flex items-start gap-2.5 rounded-lg border px-3 py-2 ${
              highlight === b.domain
                ? "border-lime-400/30 bg-lime-400/[0.06]"
                : "border-white/[0.06] bg-white/[0.02]"
            }`}
          >
            <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${EVIDENCE_DOT[b.evidence]}`} />
            <div className="min-w-0">
              <p className="text-[12.5px] font-medium text-white/80">{b.domain}</p>
              <p className="text-[12px] leading-snug text-white/45">{b.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Explorer({
  profileId,
  onDeclare,
}: {
  profileId: number;
  onDeclare: (kind: string) => void;
}) {
  const [catalog, setCatalog] = useState<SupplementInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<SupplementInfo[]>(`/supplements/catalog?profile_id=${profileId}`)
      .then(setCatalog)
      .catch((e) => setError(e instanceof Error ? e.message : "Fonti non disponibili"));
  }, [profileId]);

  const domains = useMemo(
    () => [...new Set((catalog ?? []).flatMap((s) => s.benefits.map((b) => b.domain)))],
    [catalog]
  );

  if (error) return <Notice>{error}</Notice>;
  if (!catalog) return <Spinner label="Raccolgo le fonti…" />;

  // Ordine alfabetico, non per evidenza: una classifica suonerebbe come un consiglio.
  const visibili = (domain ? catalog.filter((s) => s.benefits.some((b) => b.domain === domain)) : catalog)
    .slice()
    .sort((a, b) => label(a.kind).localeCompare(label(b.kind), "it"));

  return (
    <>
      <Card className="mb-4">
        <div className="flex items-start gap-3 px-4 py-4">
          <Mascot size={38} />
          <p className="text-[13px] leading-relaxed text-white/60">
            Qui trovi cosa dicono le fonti della mia knowledge base, esito per esito — anche
            quando l'evidenza è debole o assente. È consultazione: non ti sto suggerendo di
            prenderne nessuno. Scegli cosa ti interessa capire:
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 border-t border-white/[0.06] px-4 py-3">
          {[null, ...domains].map((d) => (
            <button
              key={d ?? "tutti"}
              onClick={() => setDomain(d)}
              className={`rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition ${
                domain === d
                  ? "border-lime-400/40 bg-lime-400/10 text-lime-200"
                  : "border-white/[0.08] text-white/50 hover:bg-white/[0.05] hover:text-white/85"
              }`}
            >
              {d ?? "Tutti"}
            </button>
          ))}
        </div>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        {visibili.map((s, i) => {
          const isOpen = open === s.kind;
          const inEvidenza = domain ? s.benefits.find((b) => b.domain === domain) : null;
          return (
            <motion.div
              key={s.kind}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              className="glass sheen self-start overflow-hidden"
            >
              <button
                onClick={() => setOpen(isOpen ? null : s.kind)}
                className="flex w-full items-start justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-white/[0.02]"
              >
                <div className="min-w-0">
                  <h3 className="text-[14.5px] font-semibold text-white">{label(s.kind)}</h3>
                  <div className="mt-1.5">
                    <EvidenceBadge evidence={s.evidence} />
                  </div>
                </div>
                <svg
                  viewBox="0 0 24 24"
                  className={`mt-1 h-5 w-5 shrink-0 fill-white/40 transition-transform ${isOpen ? "rotate-180" : ""}`}
                >
                  <path d="m12 15.4-6-6L7.4 8l4.6 4.6L16.6 8 18 9.4l-6 6Z" />
                </svg>
              </button>

              {inEvidenza && !isOpen && (
                <div className="px-4 pb-3.5">
                  <div className="flex items-start gap-2.5 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${EVIDENCE_DOT[inEvidenza.evidence]}`} />
                    <p className="text-[12px] leading-snug text-white/55">{inEvidenza.detail}</p>
                  </div>
                </div>
              )}

              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="space-y-3.5 border-t border-white/[0.06] px-4 py-4">
                      <p className="text-[13px] leading-relaxed text-white/70">{s.message}</p>
                      {s.benefits.length > 0 && <Benefits items={s.benefits} highlight={domain} />}
                      <SourceTags tags={s.knowledge_tags} />
                      <div className="flex flex-wrap gap-2">
                        <AskCoachButton
                          size="sm"
                          question={`Cosa dicono le fonti su ${label(s.kind)}${domain ? ` per ${domain}` : ""}? Nel mio caso avrebbe senso?`}
                          context="Sezione Integratori · Cosa dicono le fonti"
                        />
                        <button
                          className="btn-ghost px-3 py-1.5 text-[12px]"
                          onClick={() => onDeclare(s.kind)}
                        >
                          Lo uso già: valuta la mia dose
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>
    </>
  );
}

function AddDialog({
  profileId,
  initialKind,
  otherCaffeine,
  onClose,
  onAdded,
}: {
  profileId: number;
  initialKind: string;
  otherCaffeine: number;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [kinds, setKinds] = useState<string[]>([]);
  const [kind, setKind] = useState(initialKind || "creatine");
  const [productName, setProductName] = useState("");
  // Nessuna dose precompilata: sarebbe un suggerimento travestito da default.
  const [dose, setDose] = useState<number | null>(null);
  const [unit, setUnit] = useState("g");
  const [perDay, setPerDay] = useState<number | null>(1);
  const [proteinPerDose, setProteinPerDose] = useState<number | null>(null);
  const [preview, setPreview] = useState<Supplement | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<string[]>("/supplements/kinds").then(setKinds);
  }, []);

  useEffect(() => {
    // Unità in cui si misura di solito ciascun integratore.
    setUnit(
      kind === "caffeine" || kind === "ashwagandha"
        ? "mg"
        : kind === "vitamin_d"
          ? "mcg"
          : "g"
    );
  }, [kind]);

  const payload = useMemo(
    () => ({
      kind,
      product_name: productName.trim() || null,
      dose_amount: dose,
      dose_unit: unit,
      doses_per_day: perDay ?? 1,
      protein_g_per_dose: kind === "protein_powder" ? proteinPerDose : null,
    }),
    [kind, productName, dose, unit, perDay, proteinPerDose]
  );

  // Valutazione in tempo reale, senza salvare nulla.
  useEffect(() => {
    let annullata = false;
    setPreviewing(true);
    const t = setTimeout(async () => {
      try {
        const p = await api.post<Supplement>(
          `/supplements/preview?profile_id=${profileId}&other_caffeine_mg=${otherCaffeine}`,
          payload
        );
        if (!annullata) setPreview(p);
      } catch {
        if (!annullata) setPreview(null);
      } finally {
        if (!annullata) setPreviewing(false);
      }
    }, 350);
    return () => {
      annullata = true;
      clearTimeout(t);
    };
  }, [payload, profileId, otherCaffeine]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/supplements?profile_id=${profileId}`, payload);
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Salvataggio non riuscito");
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose} className="max-w-3xl">
      <ModalHeader
        title="Dichiara un integratore"
        subtitle="Valuto solo ciò che usi già — la valutazione si aggiorna mentre scrivi"
        onClose={onClose}
      />

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="grid gap-5 p-5 md:grid-cols-2">
          <div className="space-y-3.5">
            <div>
              <label className="label">Quale</label>
              <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
                {kinds.map((k) => (
                  <option key={k} value={k}>
                    {label(k)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label">Nome del prodotto (facoltativo)</label>
              <input
                className="input"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="es. Creatina monoidrato Xyz"
              />
            </div>

            <div className="grid grid-cols-[1fr_92px] gap-3">
              <div>
                <label className="label">La tua dose</label>
                <NumberField
                  value={dose}
                  onChange={setDose}
                  min={0}
                  max={100000}
                  step={unit === "g" ? 1 : unit === "mg" ? 50 : 5}
                  decimals={1}
                  placeholder="—"
                  ariaLabel="Dose"
                />
              </div>
              <div>
                <label className="label">Unità</label>
                <select className="input" value={unit} onChange={(e) => setUnit(e.target.value)}>
                  <option value="g">g</option>
                  <option value="mg">mg</option>
                  <option value="mcg">µg</option>
                </select>
              </div>
            </div>

            <div>
              <label className="label">Volte al giorno</label>
              <NumberField
                value={perDay}
                onChange={setPerDay}
                min={1}
                max={10}
                ariaLabel="Volte al giorno"
                className="w-40"
              />
            </div>

            {kind === "protein_powder" && (
              <div>
                <label className="label">Proteine per dose (g)</label>
                <NumberField
                  value={proteinPerDose}
                  onChange={setProteinPerDose}
                  min={0}
                  max={200}
                  suffix="g"
                  placeholder="dall'etichetta"
                  ariaLabel="Proteine per dose"
                  className="w-44"
                />
                <p className="mt-1.5 text-[11px] text-white/30">
                  Le sommo al totale proteico giornaliero: non sono un extra fuori conteggio.
                </p>
              </div>
            )}

            {kind === "other" && (
              <p className="text-[11.5px] leading-snug text-amber-200/60">
                Per ciò che è fuori dalla mia base di conoscenza ti dirò onestamente che non ho
                una fonte verificata, invece di inventare un dosaggio.
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-white/[0.08] bg-black/20 p-4">
            <div className="mb-3 flex items-center gap-2.5">
              <Mascot size={30} mood={previewing ? "thinking" : "idle"} />
              <p className="text-[11px] font-medium uppercase tracking-wider text-white/40">
                Valutazione in tempo reale
              </p>
            </div>
            {!preview ? (
              <Spinner />
            ) : (
              <div className={`space-y-3 transition-opacity ${previewing ? "opacity-60" : ""}`}>
                <div className="flex flex-wrap gap-1.5">
                  <EvidenceBadge evidence={preview.evidence} />
                  {preview.dose_in_range === true && (
                    <span className="pill border border-lime-400/20 bg-lime-400/10 text-lime-200">
                      dose nel range
                    </span>
                  )}
                  {preview.dose_in_range === false && (
                    <span className="pill border border-amber-300/20 bg-amber-300/10 text-amber-100">
                      dose fuori range
                    </span>
                  )}
                </div>
                {preview.safety_flag && <Notice>Attenzione: {preview.safety_flag}.</Notice>}
                <p className="text-[12.5px] leading-relaxed text-white/70">{preview.message}</p>
                {preview.benefits.length > 0 && <Benefits items={preview.benefits.slice(0, 4)} />}
                <SourceTags tags={preview.knowledge_tags} />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex shrink-0 flex-col gap-2 border-t border-white/[0.06] p-4 sm:flex-row">
        {error && <p className="flex-1 self-center text-[12px] text-rose-200/80">{error}</p>}
        <div className="flex gap-2.5 sm:ml-auto">
          <button className="btn-ghost" onClick={onClose}>
            Annulla
          </button>
          <button className="btn-primary" disabled={saving} onClick={save}>
            {saving ? "Salvo…" : "Aggiungi ai miei integratori"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
