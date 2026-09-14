```yaml
argomento: nutrizione vegetariana/vegana per persone attive - proteine, combinazione, nutrienti critici
fonte: "Academy of Nutrition and Dietetics - Position Paper: Vegetarian Dietary Patterns for Adults (J Acad Nutr Diet, 2025)"
url: https://www.jandonline.org/article/S2212-2672(25)00042-5/abstract
data_pubblicazione: "approvata gennaio 2025, in vigore fino a dicembre 2032"
data_verifica: "2026-09-10"
affidabilità: alta
note_di_onestà: >
  **Verificato sul PDF ufficiale originale il 2026-09-10** — non più da
  fonti secondarie. È la revisione più recente possibile di questa
  posizione (2025, valida fino al 2032), basata su 27 revisioni
  sistematiche/RCT. Sostituisce completamente la versione precedente di
  questo file, che si basava su riassunti secondari.
```

## Il mito da correggere: "combinare le proteine ad ogni pasto"

Confermato dal testo integrale: **"there is considerable variation in amino
acid composition among protein-rich plant foods allowing for adequate
consumption of all EAAs over the course of a day in a varied diet"** — non
serve combinare fonti proteiche complementari (es. legumi + cereali)
**nello stesso pasto**. Basta varietà nell'arco della giornata, con apporto
calorico adeguato. I termini "proteina completa/incompleta" applicati ai
vegetali sono esplicitamente definiti fuorvianti in letteratura recente.

**Diete vegetariane e vegane, se pianificate correttamente, sono
nutrizionalmente adeguate e possono offrire benefici per la salute a lungo
termine** (posizione ufficiale dell'Academy, gennaio 2025).

## Soglia proteica per non perdere massa/forza su dieta vegetale

Dato specifico e concreto dalla fonte: per adulti attivi/atleti che
desiderano guadagni di massa e/o forza, **non c'è evidenza di uno svantaggio
in sintesi proteica muscolare, ipertrofia o forza quando l'apporto proteico
da fonti vegetali raggiunge almeno 1,5 g/kg/giorno**. Questo è più alto del
limite inferiore ISSN generico (1,4 g/kg, vedi `protein_intake.md`) — per
utenti vegani/vegetariani con obiettivo ipertrofia, l'agente dovrebbe
puntare a **1,6-2,4 g/kg** come per onnivori, ma con un'attenzione in più a
non scendere mai sotto 1,5 g/kg.

## Qualità proteica: proteina di soia come riferimento pratico

La soia (tofu, tempeh, edamame, soymilk) è definita **proteina di alta
qualità**, con pattern di aminoacidi essenziali (EAA) che si avvicina alla
proteina animale e digeribilità comparabile — utile come riferimento
pratico quando si suggerisce una singola fonte proteica vegetale forte in
una ricetta, oltre alla varietà giornaliera generale.

## Nutrienti da monitorare attivamente — lista ufficiale aggiornata

**Correzione rispetto alla versione precedente di questo file**: la fonte
primaria elenca esplicitamente questi nutrienti di attenzione — **vitamina
B12, iodio, ferro, colina e vitamina D**; il **calcio** è un'attenzione
aggiuntiva specifica per i vegani. Lo zinco, spesso citato in fonti
generiche, **non compare in questa lista ufficiale specifica** — resta
comunque prudente non ignorarlo del tutto (vedi `micronutrients_efsa.md`
per i valori di riferimento), ma non va presentato come "il" nutriente
critico quanto B12/iodio/ferro/colina/D secondo questa fonte.

| Nutriente | Perché è critico | Come coprirlo (dalla fonte) |
|---|---|---|
| **Vitamina B12** | Assente nei vegetali | Integrazione o alimenti fortificati — non opzionale per vegani stretti |
| **Iodio** | Spesso sottostimato | Sale iodato; attenzione a non eccedere con le alghe |
| **Ferro** | Ferro non-eme, assorbimento inferiore | Vitamina C nello stesso pasto |
| **Colina** | Intake spesso sotto l'adeguato nei vegani/vegetariani | Frutta a guscio, legumi, prodotti di soia, cereali e germe di grano **quotidianamente** |
| **Vitamina D** | Critico con bassa esposizione solare | Integrazione |
| Calcio (specifico vegani) | Intake significativamente più basso nei vegani (meta-analisi recente) | Almeno **2-3 porzioni/giorno** di alimenti ricchi di calcio ad alta biodisponibilità: soymilk/bevande vegetali fortificate al calcio, verdure a foglia verde scura (es. cavolo), tofu preparato con calcio, succo d'arancia fortificato. Attenzione: fitati/ossalati riducono la biodisponibilità |

## Omega-3: valori concreti e la via pratica per EPA/DHA

- AI per ALA (omega-3 vegetale, es. semi di lino/noci/olio di canola):
  **1,1 g/giorno donne, 1,6 g/giorno uomini** (in linea con quanto in
  `macronutrients_efsa.md`, che riporta 0,5% dell'energia — valori
  complementari, ordine di grandezza coerente).
- **Non esiste un valore di riferimento (DRI) specifico per EPA/DHA.** La
  conversione di ALA in EPA/DHA nell'organismo è limitata e variabile
  (dipende da enzimi, genetica, composizione della dieta) — non è garantito
  che assumere molto ALA copra il fabbisogno di EPA/DHA.
- **Via pratica diretta per i vegani**: integratori di olio algale (fonte
  vegana diretta di EPA/DHA, non mediata dalla conversione da ALA) —
  dosaggi fino a 5 g/giorno generalmente considerati sicuri in letteratura
  su oli di pesce/alghe.

## Come tradurlo in logica applicativa (generazione ricette/piani)

1. **Non forzare la combinazione proteica nello stesso pasto** — pianificare
   varietà a livello di giornata, non di singolo piatto.
2. Per utenti vegani/vegetariani con obiettivo ipertrofia: target proteico
   1,6-2,4 g/kg come da `protein_intake.md`, con un **minimo assoluto di
   1,5 g/kg** per non compromettere gli adattamenti muscolari.
3. Generando più giorni di piano, verificare che B12, iodio, ferro, colina
   e vitamina D non siano strutturalmente scoperti — B12 sempre come
   integrazione raccomandata di base per i vegani stretti, non opzionale.
4. Per i vegani, includere esplicitamente 2-3 porzioni/giorno di fonti di
   calcio ad alta biodisponibilità nelle ricette generate, e almeno una
   fonte quotidiana di colina (legumi, frutta a guscio, soia, cereali).
5. Se l'utente vegano non menziona un integratore di omega-3 algale,
   segnalarlo come opzione da valutare, spiegando il limite della
   conversione ALA→EPA/DHA.
6. Per le ricette con proteine in polvere: la soia è la proteina vegetale
   isolata di riferimento per qualità; proteine pisello+riso combinate sono
   un'alternativa valida per chi evita la soia.

## Segnali di uso scorretto da evitare nell'agente

- Non generare consigli tipo "devi mangiare riso e fagioli insieme per fare
  proteina completa" — è la nozione datata che questa fonte corregge
  esplicitamente.
- Non trattare la B12 come "consigliata se vuoi" per un vegano stretto: è
  strutturalmente assente dalla dieta, l'integrazione è la norma.
- Non dimenticare la colina: è meno nota di B12/ferro ma è nella lista
  ufficiale dei nutrienti di attenzione, mentre lo zinco (più spesso citato
  in fonti generiche) non lo è in questa fonte specifica — non invertire le
  priorità.
