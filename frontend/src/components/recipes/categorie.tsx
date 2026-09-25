/**
 * Colore e icona di una ricetta, per la copertina e per le pillole di ricerca.
 *
 * Le Ricette Kilo non hanno foto: senza un'identità visiva sarebbero tutte
 * uguali. La categoria si ricava dal campo `category` (in italiano per le
 * Ricette Kilo, tradotta o in inglese per le altre) e, se non dice nulla, dalle
 * parole del nome.
 *
 * La tavolozza è quella dell'app: lime, iris, amber, rose e bianchi. Le
 * categorie sono più dei colori, quindi alcune usano una sfumatura tra due.
 */

import type { RecipeSuggestion } from "@/lib/api";

export type CategoriaId =
  | "carne"
  | "pesce"
  | "colazione"
  | "legumi"
  | "verdure"
  | "dolci"
  | "pasta"
  | "altro";

export type Categoria = {
  nome: string;
  /** Classi della sfumatura (da/a), da usare con `bg-gradient-to-br`. */
  sfondo: string;
  testo: string;
  icona: string;
};

export const ICONE = {
  coscia:
    "M14.5 3a6.5 6.5 0 0 1 4.6 11.1c-1.8 1.8-4.4 2.3-6.6 1.5l-2.9 2.9a2.5 2.5 0 1 1-3.4 2.4 2.5 2.5 0 1 1 2.4-3.4l2.9-2.9C8.7 12 8.5 7.4 10 5.3A6.5 6.5 0 0 1 14.5 3Z",
  pesce: "M3 12c3-5 9-6 13-3l5-3-1 6 1 6-5-3c-4 3-10 2-13-3Zm12-1a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z",
  sole: "M12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10Zm0-5 1 3h-2l1-3Zm0 20-1-3h2l-1 3ZM2 12l3-1v2l-3-1Zm20 0-3 1v-2l3 1ZM4.9 4.9l2.8 1.4-1.4 1.4-1.4-2.8Zm14.2 14.2-2.8-1.4 1.4-1.4 1.4 2.8Zm0-14.2-1.4 2.8-1.4-1.4 2.8-1.4ZM4.9 19.1l1.4-2.8 1.4 1.4-2.8 1.4Z",
  fagiolo:
    "M9 3.5c2.6 0 4.2 1.9 4.4 4 .1 1.3.9 2 2.2 2.2 2.6.4 4.4 2.3 4.4 5 0 3.2-2.8 5.8-6.9 5.8C7.2 20.5 3 16 3 10.2 3 6.4 5.6 3.5 9 3.5Z",
  foglia:
    "M20 3c-8.5 0-15 3.8-15 11 0 1.6.4 3 1.1 4.2L3.3 21l1.4 1.4 2.8-2.8c1.2.7 2.6 1.1 4.2 1.1 7.2 0 9.3-8.2 8.3-17.7ZM8.9 16.5l-1.4-1.4c2.6-2.8 5.7-5 9.2-6.4l.7 1.8c-3.2 1.3-6.1 3.4-8.5 6Z",
  mela: "M13 3c1.5 0 3 .8 3 2.5-1 .1-2.2-.3-3-1V3Zm-1 3c3.2-1.3 7 .5 7 5.5 0 4.6-3.2 9.5-5.5 9.5-.8 0-1-.4-1.5-.4s-.7.4-1.5.4C8.2 21 5 16.1 5 11.5 5 6.5 8.8 4.7 12 6Z",
  ciotola: "M3 11h18a9 9 0 0 1-18 0Zm2-3h14l-1 2H6L5 8Zm4-5h2v4H9V3Zm4 0h2v4h-2V3Z",
  posate: "M6 2h1.5v6H9V2h1.5v6H12V2h1.5v7a3 3 0 0 1-2.5 3v10H8.5V12A3 3 0 0 1 6 9V2Zm11 0c1.7 0 3 2.2 3 6v5h-2v9h-2V2h1Z",
  uovo: "M12 2.5c3.6 0 7 6.1 7 11.1 0 4.3-3 7.9-7 7.9s-7-3.6-7-7.9c0-5 3.4-11.1 7-11.1Z",
  orologio:
    "M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20Zm0 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm1 3v5.4l3.6 2.1-1 1.7L11 13.5V7h2Z",
} as const;

export const CATEGORIE: Record<CategoriaId, Categoria> = {
  carne: { nome: "Pollo e carne", sfondo: "from-lime-400/35 to-lime-500/10", testo: "text-lime-200", icona: ICONE.coscia },
  pesce: { nome: "Pesce", sfondo: "from-iris-400/40 to-iris-500/10", testo: "text-iris-100", icona: ICONE.pesce },
  colazione: { nome: "Colazione", sfondo: "from-amber-300/35 to-amber-500/10", testo: "text-amber-100", icona: ICONE.sole },
  legumi: { nome: "Legumi", sfondo: "from-lime-400/30 to-amber-300/10", testo: "text-lime-200", icona: ICONE.fagiolo },
  verdure: { nome: "Verdure", sfondo: "from-lime-400/25 to-iris-400/10", testo: "text-lime-200", icona: ICONE.foglia },
  dolci: { nome: "Dolci e spuntini", sfondo: "from-rose-400/35 to-rose-500/10", testo: "text-rose-200", icona: ICONE.mela },
  pasta: { nome: "Pasta e cereali", sfondo: "from-amber-300/30 to-rose-400/10", testo: "text-amber-100", icona: ICONE.ciotola },
  altro: { nome: "Altro", sfondo: "from-white/[0.14] to-white/[0.03]", testo: "text-white/70", icona: ICONE.posate },
};

// L'ordine conta: "Pollo allo yogurt" è carne, non colazione, e "Pasta e ceci"
// è legumi, non pasta. Le radici vanno a inizio parola ("poll" non trova "cipolla").
const REGOLE: [CategoriaId, RegExp, RegExp][] = [
  [
    "pesce",
    /\b(pesce|frutti di mare|seafood|fish)/,
    /\b(pesce|salmon|tonn|tuna|merluzz|cod\b|gamber|shrimp|prawn|orata|branzin|sgombr|baccal|cozz|vongol|calamar|polp[oi]\b|sardin|acciug|alic|seafood|fish)/,
  ],
  [
    "carne",
    /\b(poll|tacchin|carne|manz|maial|agnell|capra|vitell|chicken|beef|pork|lamb|goat)/,
    /\b(poll|tacchin|manz|maial|vitell|agnell|polpett|bistecc|burger|hamburger|prosciut|salsicc|carne|straccett|chicken|turkey|beef|pork|lamb|steak|meatball|sausage|bacon)/,
  ],
  ["legumi", /\blegum/, /\b(lenticch|cec[ei]\b|fagiol|pisell|hummus|tofu|tempeh|edamame|lentil|chickpea|bean|dal\b|dahl)/],
  [
    "colazione",
    /\b(colazion|breakfast)/,
    /\b(porridge|pancake|overnight|oats|avena|granola|muesli|yogurt|colazion|breakfast)/,
  ],
  [
    "dolci",
    /\b(spuntin|merend|dolc|dessert|snack)/,
    /\b(torta|biscott|muffin|budin|cioccolat|barrett|dolce|tiramis|crostat|gelat|brownie|cake|cookie|pudding|dessert|snack|spuntin|merend)/,
  ],
  [
    "pasta",
    /\b(pasta|cereal|riso)/,
    /\b(pasta|riso|risott|spaghett|penne|fusill|rigaton|tagliatell|lasagn|gnocch|cous|quinoa|farro|orzo|noodle|ramen|rice|polenta|pizza|pane\b|bread)/,
  ],
  [
    "verdure",
    /\b(vegetar|vegan|verdur|contorn|side|insalat)/,
    /\b(insalat|verdur|zucchin|melanzan|spinac|broccol|cavol|zupp|minestr|vellutat|fungh|peperon|salad|vegetable|vegan|vegetar|soup)/,
  ],
];

export function categoriaDi(r: Pick<RecipeSuggestion, "category" | "name" | "original_name">): Categoria {
  const categoria = (r.category ?? "").toLowerCase();
  const nome = `${r.name} ${r.original_name ?? ""}`.toLowerCase();
  const trovata =
    (categoria && REGOLE.find(([, perCategoria]) => perCategoria.test(categoria))) ||
    REGOLE.find(([, , perNome]) => perNome.test(nome));
  return CATEGORIE[trovata ? trovata[0] : "altro"];
}

export function Icona({ d, className = "h-4 w-4" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={`${className} shrink-0 fill-current`}>
      <path d={d} />
    </svg>
  );
}

/**
 * Livello di adattezza a oggi, a partire da `fit_score`.
 *
 * Il punteggio (vedi `score_fit` nel backend) va da 0 a circa 11,5: 10 meno
 * lo scostamento da kcal e proteine rimaste, più 1,5 se le proteine sono tra
 * 20 e 40 g e 0,5 se c'è molta fibra. Non è una percentuale di copertura,
 * quindi non lo si mostra come tale: tre livelli, con soglie scelte sul
 * calcolo (sopra 8,5 servono kcal vicine a quelle rimaste e proteine giuste).
 */
export function adattezza(score: number): { livello: 1 | 2 | 3; etichetta: string } {
  if (score >= 8.5) return { livello: 3, etichetta: "Molto adatta a oggi" };
  if (score >= 5.5) return { livello: 2, etichetta: "Adatta" };
  return { livello: 1, etichetta: "Poco adatta" };
}
