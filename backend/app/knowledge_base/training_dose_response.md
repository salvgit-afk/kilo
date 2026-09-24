```yaml
argomento: relazione dose-risposta fra volume settimanale, frequenza, ipertrofia e forza
fonte: "Pelland JC, Remmert JF, Robinson ZP, Hinson SR, Zourdos MC - The Resistance Training Dose Response: Meta-Regressions Exploring the Effects of Weekly Volume and Frequency on Muscle Hypertrophy and Strength Gains (Sports Medicine, 2026;56(2):481-505)"
url: https://pubmed.ncbi.nlm.nih.gov/41343037/
doi: 10.1007/s40279-025-02344-w
data_pubblicazione: "2026-02 (fascicolo di febbraio 2026; pubblicato online il 2025-12-04)"
data_verifica: "2026-09-24"
affidabilità: alta
note_di_onestà: >
  Letto l'abstract strutturato integrale della versione pubblicata, recuperato
  dalle API E-utilities di NCBI (l'articolo non è open access e il testo
  completo su Springer resta dietro autenticazione). Tutti i numeri di questo
  file vengono da lì. Limite importante da dichiarare all'utente: questo
  abstract **non fornisce una soglia numerica di serie ottimale né un punto di
  plateau**; dice solo la forma qualitativa della curva. I numeri di serie che
  Kilo usa vengono da `hypertrophy_prescription.md` (IUSCA) e
  `resistance_training_acsm.md` (ACSM 2026), non da questa fonte. Gli autori
  dichiarano di non avere conflitti specifici su questo articolo ma di essere
  coach e autori di contenuti nel settore fitness. Campione fortemente
  sbilanciato verso uomini giovani.
```

## Che cosa ha misurato questo lavoro

È una serie di **meta-regressioni multilivello** — non un semplice confronto
fra due gruppi — su **67 studi** e **2058 partecipanti** (79,1% uomini, 20,9%
donne; età media 25,16 ± 5,22 anni). Tutti i modelli sono corretti per la
**durata dell'intervento** e per il **livello di allenamento** dei
partecipanti.

L'obiettivo non era trovare "il numero giusto di serie", ma descrivere la
**forma della curva**: come cambiano ipertrofia e forza man mano che il volume
o la frequenza aumentano.

## Come sono state contate le serie (la parte più pratica)

Prima di analizzare i dati, ogni serie degli studi è stata classificata come
**diretta** o **indiretta** rispetto alla misura di ipertrofia o forza
considerata. Poi il volume (e la frequenza) delle serie **indirette** è stato
quantificato in tre modi alternativi:

| Metodo | Quanto vale una serie indiretta |
|---|---|
| `total` | 1 |
| `fractional` (frazionario) | 0,5 |
| `direct` | 0 |

Il metodo **frazionario** è quello con il supporto relativo più forte nei
dati, ed è quello usato per i modelli principali. In pratica: una serie in cui
il muscolo lavora da secondario (i tricipiti nelle distensioni su panca) conta
**mezza serie**, non zero e non una intera.

Gli autori concludono che distinguere serie dirette e indirette è
**essenziale** per prevedere gli adattamenti a un programma: è il risultato
metodologico principale dell'articolo.

## Volume: più serie, più risultati, ma con rendimenti decrescenti

- La probabilità a posteriori che la pendenza marginale sia **maggiore di
  zero** è del **100%** sia per l'ipertrofia sia per la forza: aumentando il
  volume, aumentano sia la dimensione del muscolo sia la forza.
- Entrambi i modelli migliori mostrano **rendimenti decrescenti**: ogni serie
  in più rende meno della precedente.
- I rendimenti decrescenti sono **molto più marcati per la forza** che per
  l'ipertrofia. Detto altrimenti: per diventare più grossi il volume continua a
  contare più a lungo; per diventare più forti smette di contare prima.
- L'abstract **non indica un numero di serie oltre il quale l'effetto si
  annulla o si inverte**. Non va quindi detto all'utente che "oltre N serie è
  inutile o dannoso" citando questa fonte.

## Frequenza: conta per la forza, quasi nulla per l'ipertrofia

- **Ipertrofia**: la probabilità a posteriori che la pendenza superi zero è
  **inferiore al 100%**, cioè i dati sono **compatibili con effetti
  trascurabili**. A parità di volume settimanale, spalmare le serie su più
  sedute non è un fattore determinante per la crescita.
- **Forza**: la probabilità è **100%**, con rendimenti decrescenti. Allenare
  più spesso aiuta la forza, ma sempre meno man mano che la frequenza sale.

La conclusione degli autori è che volume e frequenza hanno curve
dose-risposta **distinte** per ipertrofia e per forza, e che non si possono
trattare come la stessa cosa.

## Rapporto con `training_volume.md`

`training_volume.md` è il file che il generatore di schede usa davvero per
scegliere le serie. Ecco cosa questo documento **conferma** e cosa
**andrebbe rivisto**.

**Resta valido:**

1. Il **conteggio frazionario a 0,5** per le serie in cui il muscolo lavora da
   secondario: è esattamente il metodo che questa meta-regressione trova
   meglio supportato dai dati.
2. La scelta di **non usare la frequenza come leva per l'ipertrofia**: a parità
   di volume l'effetto è compatibile con zero, quindi la frequenza per muscolo
   si sceglie per comodità di organizzazione, non per crescere di più.
3. I **rendimenti decrescenti** come principio: aggiungere serie ha senso, ma
   ogni serie in più vale meno.
4. La distinzione fra obiettivo forza e obiettivo massa: qui è documentata
   direttamente, con curve diverse per i due esiti.

**Andrebbe rivisto / va detto con più onestà:**

1. `training_volume.md` presenta dei **tetti** (per esempio 12-20 o 10-20 serie
   a settimana). Questa fonte **non identifica alcun plateau** per
   l'ipertrofia: il tetto di Kilo è una scelta prudenziale legata a recupero,
   tempo disponibile e rischio di sovraccarico, **non** un limite dimostrato
   dai dati. Va presentato come tale.
2. Per l'obiettivo **forza**, l'idea che "più volume è sempre meglio" è ancora
   meno difendibile: i rendimenti decrescenti sono molto più marcati. Per chi
   punta alla forza conviene spostare la leva sulla **frequenza**, che qui ha
   un effetto positivo consistente, invece che accumulare serie.
3. La frase di `training_volume.md` secondo cui il generatore conta "solo le
   serie degli esercizi con quel muscolo come primario" resta una
   semplificazione che **sottostima** il volume reale. Con il metodo
   frazionario il volume effettivo è più alto, e nei profili con molti
   multi-articolari la differenza non è piccola.

## Uso in Kilo

- **Quando l'utente chiede "quante serie devo fare?"**: rispondere che più
  volume dà più risultati con rendimenti decrescenti, e che non esiste un
  numero unico. I range concreti vengono da `training_volume.md`,
  `hypertrophy_prescription.md` e `resistance_training_acsm.md`, non da qui.
- **Quando l'utente chiede "quante volte a settimana devo allenare un
  muscolo?"**: se l'obiettivo è la massa, rispondere che a parità di serie
  totali la frequenza cambia poco e si sceglie per organizzazione; se
  l'obiettivo è la forza, rispondere che allenare più spesso aiuta, con
  rendimenti decrescenti.
- **Quando l'utente dice "faccio già panca, i tricipiti sono a posto?"**:
  spiegare il conteggio frazionario — quelle serie contano circa la metà per i
  tricipiti, non zero e non una intera.
- **Mai** citare questa fonte per affermare che esiste un numero massimo di
  serie oltre il quale si peggiora: l'abstract non lo dice.

**Traduzione operativa dichiarata**: il valore 0,5 per le serie indirette è
nella fonte; l'applicazione di quel valore ai gruppi muscolari del catalogo di
Kilo e l'uso dei tetti presenti in `training_volume.md` sono scelte di
progetto, non risultati di questa meta-regressione.
