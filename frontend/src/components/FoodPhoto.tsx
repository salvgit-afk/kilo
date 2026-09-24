"use client";

/**
 * La fotocamera del diario, per quando il codice a barre non basta.
 *
 * Due strade, tenute separate perché i numeri hanno origini diverse:
 *
 *  - **Etichetta**: si fotografa la tabella nutrizionale e Kilo trascrive i
 *    valori stampati. Restano valori da confermare — la foto può essere
 *    storta, sfocata o riportare la colonna «per porzione» — quindi finiscono
 *    in un modulo modificabile e non nel diario in silenzio.
 *  - **Piatto**: Kilo riconosce gli alimenti e **stima** le quantità. La
 *    bozza è identica a quella dell'importazione di una ricetta, così il
 *    percorso «correggo i grammi e verso nel pasto» è uno solo in tutta
 *    l'app. I macro non li inventa la foto: li calcola il catalogo alimenti.
 *
 * Il codice a barre resta la via migliore quando c'è: legge il prodotto reale
 * da Open Food Facts invece di fidarsi di un'immagine. Questa schermata lo
 * dice all'utente invece di lasciarglielo scoprire.
 */

import { useRef, useState } from "react";
import {
  ApiError,
  MEAL_LABELS,
  api,
  session,
  type FoodResult,
  type LabelPhoto,
  type MealPhoto,
  type RecipeItem,
} from "@/lib/api";
import { Empty, Notice } from "@/components/ui";
import { Field, MacroGrid, NumberField } from "@/components/controls";
import { Mascot } from "@/components/Mascot";
import { DraftItems } from "@/components/DraftItems";
import { totali } from "@/components/RecipeImport";

/** Lo stesso limite del backend: qui evita un caricamento inutile. */
const MAX_BYTE = 6 * 1024 * 1024;

type Modo = "scelta" | "etichetta" | "piatto";

/**
 * Invio multipart: `api.post` manda JSON, e il `Content-Type` del multipart
 * deve scriverlo il browser perché contiene il boundary.
 */
async function inviaFoto<T>(path: string, file: File): Promise<T> {
  const token = session.get();
  const form = new FormData();
  form.append("photo", file);
  const res = await fetch(`/api${path}`, {
    method: "POST",
    body: form,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* risposta senza corpo JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function messaggioErrore(e: unknown): string {
  if (e instanceof ApiError) {
    // Il backend manda già il motivo in italiano per 422 e 429; per un guasto
    // del servizio il suo testo sarebbe tecnico, e qui serve cosa fare.
    if (e.status === 502 || e.status === 503) {
      return "La lettura delle foto non risponde in questo momento: riprova fra qualche minuto.";
    }
    return e.message;
  }
  return "Non sono riuscito a inviare la foto: controlla la connessione e riprova.";
}

export function FoodPhotoPanel({
  profileId,
  mealType,
  onAdded,
}: {
  profileId: number;
  mealType: string;
  /** Il pasto è finito nel diario: la pagina si ricarica e il pannello chiude. */
  onAdded: () => void;
}) {
  const [modo, setModo] = useState<Modo>("scelta");
  const [caricamento, setCaricamento] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);
  const [lettura, setLettura] = useState<LabelPhoto | null>(null);
  const [bozza, setBozza] = useState<MealPhoto | null>(null);
  const [versando, setVersando] = useState(false);
  const scattoRef = useRef<HTMLInputElement>(null);
  const galleriaRef = useRef<HTMLInputElement>(null);
  // Il modo va letto al momento della scelta del file, non al clic: fra i due
  // passa il selettore di sistema e uno stato potrebbe essere già vecchio.
  const modoRef = useRef<Modo>("scelta");

  function apri(m: Modo) {
    modoRef.current = m;
    setModo(m);
    setErrore(null);
    setLettura(null);
    setBozza(null);
  }

  async function carica(file: File) {
    const m = modoRef.current;
    setErrore(null);
    setLettura(null);
    setBozza(null);
    if (file.size > MAX_BYTE) {
      setErrore("La foto è troppo grande (oltre 6 MB): riprova con uno scatto meno pesante.");
      return;
    }
    setCaricamento(true);
    try {
      if (m === "etichetta") {
        setLettura(
          await inviaFoto<LabelPhoto>(`/nutrition/diary/photo/label?profile_id=${profileId}`, file)
        );
      } else {
        setBozza(
          await inviaFoto<MealPhoto>(`/nutrition/diary/photo/meal?profile_id=${profileId}`, file)
        );
      }
    } catch (e) {
      setErrore(messaggioErrore(e));
    } finally {
      setCaricamento(false);
    }
  }

  function scelta(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Azzerato subito: così riscegliere la stessa foto fa ripartire la lettura.
    e.target.value = "";
    if (file) carica(file);
  }

  async function versaPiatto() {
    if (!bozza) return;
    setVersando(true);
    setErrore(null);
    try {
      await api.post(`/nutrition/diary/recipe?profile_id=${profileId}`, {
        items: bozza.items,
        meal_type: mealType,
        date: null,
        servings: 1,
        eaten_servings: 1,
      });
      onAdded();
    } catch (e) {
      setErrore(
        e instanceof Error
          ? `Non sono riuscito ad aggiungere il pasto: ${e.message}`
          : "Non sono riuscito ad aggiungere il pasto."
      );
      setVersando(false);
    }
  }

  const t = bozza ? totali(bozza.items) : null;
  const collegati = bozza?.items.filter((i) => i.ingredient_id !== null && i.grams).length ?? 0;

  return (
    <div className="space-y-3 p-2 sm:p-3">
      <input
        ref={scattoRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={scelta}
      />
      <input ref={galleriaRef} type="file" accept="image/*" className="hidden" onChange={scelta} />

      {modo === "scelta" && (
        <>
          <p className="px-1 text-[12.5px] leading-snug text-white/45">
            Con il codice a barre i valori sono quelli reali del prodotto; dalla foto sono letti o
            stimati da Kilo e vanno controllati prima di finire nel conteggio.
          </p>
          <ScegliModo
            titolo="Etichetta"
            testo="Fotografa la tabella nutrizionale: leggo calorie e macro per 100 g. Serve quando il codice a barre non c'è o non viene letto."
            onClick={() => apri("etichetta")}
            icona={
              <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
                <path d="M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm1 2v14h14V5H5Zm2 2h10v2H7V7Zm0 4h10v2H7v-2Zm0 4h6v2H7v-2Z" />
              </svg>
            }
          />
          <ScegliModo
            titolo="Piatto"
            testo="Fotografa quello che stai mangiando: riconosco gli alimenti e stimo le quantità, che correggi tu prima di salvare."
            onClick={() => apri("piatto")}
            icona={
              <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
                <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16Zm0 3a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0 2a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z" />
              </svg>
            }
          />
        </>
      )}

      {modo !== "scelta" && (
        <>
          <div className="flex items-center gap-2">
            <button
              onClick={() => apri("scelta")}
              className="flex h-8 items-center gap-1 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 text-[12px] text-white/60 transition hover:border-white/20 hover:text-white"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 fill-current">
                <path d="M11 5 4 12l7 7v-4h9v-6h-9V5Z" />
              </svg>
              Cambia
            </button>
            <p className="text-[13px] font-medium text-white/80">
              {modo === "etichetta" ? "Foto dell'etichetta" : "Foto del piatto"}
            </p>
          </div>

          {caricamento && (
            <div className="flex items-center gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-5">
              <Mascot size={46} mood="thinking" />
              <div className="min-w-0">
                <p className="text-[14px] font-medium text-white">Sto leggendo la foto…</p>
                <p className="text-[12.5px] leading-snug text-white/45">
                  {modo === "etichetta"
                    ? "Trascrivo i numeri della tabella: non li invento e non completo quelli illeggibili."
                    : "Riconosco gli alimenti e li cerco nel catalogo. I valori nutrizionali arrivano da lì."}
                </p>
              </div>
            </div>
          )}

          {errore && !caricamento && <Notice>{errore}</Notice>}

          {!caricamento && !lettura && !bozza && (
            <div className="space-y-2">
              <p className="text-[12.5px] leading-snug text-white/45">
                {modo === "etichetta"
                  ? "Inquadra da vicino la tabella «Valori medi per 100 g», dritta e con luce sufficiente."
                  : "Inquadra il piatto dall'alto, con tutto quello che contiene nella foto."}
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  className="btn-primary flex-1 justify-center"
                  onClick={() => scattoRef.current?.click()}
                >
                  {errore ? "Riprova con un'altra foto" : "Scatta una foto"}
                </button>
                <button
                  className="btn-ghost flex-1 justify-center"
                  onClick={() => galleriaRef.current?.click()}
                >
                  Scegli dalla galleria
                </button>
              </div>
            </div>
          )}

          {!caricamento && lettura && (
            <FormEtichetta
              lettura={lettura}
              profileId={profileId}
              mealType={mealType}
              onAdded={onAdded}
              onRiprova={() => {
                setLettura(null);
                setErrore(null);
              }}
            />
          )}

          {!caricamento && bozza && t && (
            <>
              {bozza.warnings.map((w, k) => (
                <Notice key={k}>{w}</Notice>
              ))}

              {bozza.items.length === 0 ? (
                <Empty
                  title="Non ho riconosciuto niente"
                  hint="Prova con una foto del piatto dall'alto e più luce, oppure aggiungi gli alimenti con la ricerca."
                />
              ) : (
                <>
                  <p className="px-1 text-[13px] text-white/70">{bozza.name}</p>
                  <DraftItems
                    items={bozza.items}
                    onChange={(items: RecipeItem[]) => setBozza({ ...bozza, items })}
                  />
                  <MacroGrid
                    items={[
                      ["kcal", Math.round(t.kcal)],
                      ["prot.", `${Math.round(t.protein * 10) / 10}g`],
                      ["carb.", `${Math.round(t.carbs * 10) / 10}g`],
                      ["grassi", `${Math.round(t.fat * 10) / 10}g`],
                    ]}
                    note="tutto il piatto · si aggiorna mentre correggi i grammi"
                  />
                  <p className="px-1 text-[11.5px] leading-snug text-white/35">
                    Entrano {collegati} {collegati === 1 ? "alimento" : "alimenti"} come voci
                    separate: puoi correggerne o toglierne una senza rifare tutto.
                  </p>
                </>
              )}

              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  className="btn-ghost justify-center sm:flex-1"
                  onClick={() => {
                    setBozza(null);
                    setErrore(null);
                  }}
                  disabled={versando}
                >
                  Un'altra foto
                </button>
                <button
                  className="btn-primary justify-center sm:flex-[1.6]"
                  onClick={versaPiatto}
                  disabled={versando || collegati === 0}
                >
                  {versando ? "Aggiungo…" : `Aggiungi a ${MEAL_LABELS[mealType]}`}
                </button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function ScegliModo({
  titolo,
  testo,
  icona,
  onClick,
}: {
  titolo: string;
  testo: string;
  icona: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-start gap-3.5 rounded-2xl border border-iris-400/25 bg-iris-400/[0.06] p-4 text-left transition hover:border-iris-400/50 hover:bg-iris-400/[0.12]"
    >
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-iris-400/20 text-iris-100">
        {icona}
      </span>
      <span className="min-w-0">
        <span className="block text-[14px] font-semibold text-white">{titolo}</span>
        <span className="mt-0.5 block text-[12px] leading-snug text-white/50">{testo}</span>
      </span>
    </button>
  );
}

/** Un valore convertito da porzione a 100 g, senza uscire dai limiti del backend. */
function converti(valore: number | null, fattore: number, massimo: number): number | null {
  if (valore === null) return null;
  return Math.min(massimo, Math.round(valore * fattore * 10) / 10);
}

/**
 * I valori letti dall'etichetta, modificabili, e il pulsante che crea
 * l'alimento e lo mette nel pasto.
 *
 * L'alimento nasce con l'endpoint dei prodotti manuali, lo stesso che serve
 * quando il codice a barre non trova niente: resta visibile solo a chi lo
 * inserisce e la prossima volta si ritrova con la ricerca.
 */
function FormEtichetta({
  lettura,
  profileId,
  mealType,
  onAdded,
  onRiprova,
}: {
  lettura: LabelPhoto;
  profileId: number;
  mealType: string;
  onAdded: () => void;
  onRiprova: () => void;
}) {
  const [nome, setNome] = useState(lettura.name);
  const [marca, setMarca] = useState(lettura.brand ?? "");
  const [kcal, setKcal] = useState<number | null>(lettura.kcal_100g);
  const [proteine, setProteine] = useState<number | null>(lettura.protein_100g);
  const [carboidrati, setCarboidrati] = useState<number | null>(lettura.carbs_100g);
  const [grassi, setGrassi] = useState<number | null>(lettura.fat_100g);
  const [porzione, setPorzione] = useState<number | null>(lettura.serving_g ?? 100);
  // Finché i valori sono dichiarati «per porzione» non si salva: trattarli
  // come se fossero per 100 g sballerebbe il conteggio in silenzio.
  const [perPorzione, setPerPorzione] = useState(lettura.per_serving);
  const [salvo, setSalvo] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  const nomeCompleto = [nome.trim(), marca.trim()].filter(Boolean).join(" · ").slice(0, 200);
  const completo =
    nomeCompleto.length >= 2 &&
    [kcal, proteine, carboidrati, grassi].every((v) => v !== null) &&
    !!porzione &&
    porzione > 0 &&
    !perPorzione;

  function convertiTutto() {
    if (!porzione) return;
    const f = 100 / porzione;
    setKcal(converti(kcal, f, 950));
    setProteine(converti(proteine, f, 100));
    setCarboidrati(converti(carboidrati, f, 100));
    setGrassi(converti(grassi, f, 100));
    setPerPorzione(false);
  }

  async function salva() {
    if (!completo || !porzione) return;
    setSalvo(true);
    setErrore(null);
    try {
      const prodotto = await api.post<FoodResult>("/nutrition/foods/manual", {
        name: nomeCompleto,
        barcode: null,
        kcal_100g: kcal,
        protein_100g: proteine,
        carbs_100g: carboidrati,
        fat_100g: grassi,
        fiber_100g: lettura.fiber_100g,
      });
      await api.post(`/nutrition/diary/items?profile_id=${profileId}`, {
        ingredient_id: prodotto.ingredient_id,
        grams: porzione,
        meal_type: mealType,
      });
      onAdded();
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Non sono riuscito ad aggiungere l'alimento.");
      setSalvo(false);
    }
  }

  const f = (porzione ?? 0) / 100;

  return (
    <div className="space-y-3">
      {lettura.warnings.map((w, k) => (
        <Notice key={k}>{w}</Notice>
      ))}

      {perPorzione && (
        <div className="rounded-2xl border border-amber-300/30 bg-amber-300/[0.07] p-3.5">
          <p className="text-[13px] font-medium text-amber-100">Valori per porzione</p>
          <p className="mt-1 text-[12px] leading-snug text-amber-100/70">
            Sull'etichetta i numeri erano riferiti a una porzione
            {porzione ? ` di ${Math.round(porzione)} g` : ""}, non a 100 g. Posso riportarli a 100 g,
            se il peso della porzione qui sotto è giusto.
          </p>
          <div className="mt-2.5 flex flex-col gap-2 sm:flex-row">
            <button className="btn-primary flex-1 justify-center" onClick={convertiTutto} disabled={!porzione}>
              Riporta a 100 g
            </button>
            <button className="btn-ghost flex-1 justify-center" onClick={() => setPerPorzione(false)}>
              Erano già per 100 g
            </button>
          </div>
        </div>
      )}

      <Field title="Prodotto" hint="Come lo ritroverai nella ricerca del diario.">
        <div className="space-y-2">
          <input
            className="input"
            value={nome}
            maxLength={120}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome del prodotto"
            aria-label="Nome del prodotto"
          />
          <input
            className="input"
            value={marca}
            maxLength={80}
            onChange={(e) => setMarca(e.target.value)}
            placeholder="Marca (facoltativa)"
            aria-label="Marca"
          />
        </div>
      </Field>

      <Field
        title="Valori per 100 g"
        hint="Letti dalla foto: confrontali con l'etichetta e correggi quello che non torna."
      >
        <div className="grid grid-cols-2 gap-2.5">
          {(
            [
              ["Calorie", kcal, setKcal, "kcal", 950],
              ["Proteine", proteine, setProteine, "g", 100],
              ["Carboidrati", carboidrati, setCarboidrati, "g", 100],
              ["Grassi", grassi, setGrassi, "g", 100],
            ] as const
          ).map(([etichetta, valore, imposta, unita, massimo]) => (
            <div key={etichetta}>
              <p className="mb-1.5 text-[11px] text-white/45">{etichetta}</p>
              <NumberField
                value={valore}
                onChange={imposta}
                min={0}
                max={massimo}
                decimals={1}
                suffix={unita}
                steppers="sm"
                placeholder="—"
                ariaLabel={`${etichetta} per 100 g`}
              />
            </div>
          ))}
        </div>
        {lettura.fiber_100g !== null && (
          <p className="mt-2 text-[11px] leading-snug text-white/35">
            Fibra letta: {lettura.fiber_100g} g per 100 g, salvata insieme agli altri valori.
          </p>
        )}
      </Field>

      <Field title={`Quanto ne metti in ${MEAL_LABELS[mealType]}`}>
        <NumberField
          value={porzione}
          onChange={setPorzione}
          min={1}
          max={5000}
          step={10}
          suffix="g"
          ariaLabel="Grammi da aggiungere"
          className="w-40"
        />
        <div className="mt-3">
          <MacroGrid
            items={[
              ["kcal", Math.round((kcal ?? 0) * f)],
              ["prot.", `${((proteine ?? 0) * f).toFixed(1)}g`],
              ["carb.", `${((carboidrati ?? 0) * f).toFixed(1)}g`],
              ["grassi", `${((grassi ?? 0) * f).toFixed(1)}g`],
            ]}
            note="quello che finisce nel diario"
          />
        </div>
      </Field>

      {errore && <Notice>{errore}</Notice>}

      {!completo && !perPorzione && (
        <p className="px-1 text-[11.5px] leading-snug text-white/35">
          Servono nome, calorie e i tre macro: completa i campi rimasti vuoti leggendo l'etichetta.
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <button className="btn-ghost justify-center sm:flex-1" onClick={onRiprova} disabled={salvo}>
          Un'altra foto
        </button>
        <button
          className="btn-primary justify-center sm:flex-[1.6]"
          onClick={salva}
          disabled={!completo || salvo}
        >
          {salvo ? "Aggiungo…" : `Crea e aggiungi a ${MEAL_LABELS[mealType]}`}
        </button>
      </div>
    </div>
  );
}
