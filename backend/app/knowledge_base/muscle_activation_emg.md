```yaml
argomento: elettromiografia di superficie, attivazione muscolare e connessione mente-muscolo
fonte: "Vigotsky AD, Halperin I, Lehman GJ, Trajano GS, Vieira TM - Interpreting Signal Amplitudes in Surface Electromyography Studies in Sport and Rehabilitation Sciences (Frontiers in Physiology 2018;8:985); Vigotsky AD, Beardsley C, Contreras B, Steele J, Ogborn D, Phillips SM - Greater electromyographic responses do not imply greater motor unit recruitment and 'hypertrophic potential' cannot be inferred (J Strength Cond Res 2017;31(1):e1-e4); Vigotsky AD, Ogborn D, Phillips SM - Motor unit recruitment cannot be inferred from surface EMG amplitude and basic reporting standards must be adhered to (Eur J Appl Physiol 2016;116(3):657-658); Schoenfeld BJ, Grgic J, Ogborn D, Krieger JW - Strength and Hypertrophy Adaptations Between Low- vs. High-Load Resistance Training: A Systematic Review and Meta-analysis (J Strength Cond Res 2017;31(12):3508-3523); Haun CT, et al. - Molecular, neuromuscular, and recovery responses to light versus heavy resistance exercise in young men (Physiol Rep 2017;5(18):e13457); Schoenfeld BJ, Vigotsky A, Contreras B, et al. - Differential effects of attentional focus strategies during long-term resistance training (Eur J Sport Sci 2018;18(5):705-712); Sevilmis E, Atalag O, Baytas E, Henselmans M, Balyan M, Binboga E - The Disconnect Between Soccer Players' Perceived and Actual Electromyographic-Measured Muscle Activation (Percept Mot Skills 2024;131(5):1834-1860); Kim D, et al. - Effects of Mind-Muscle Connection on Muscle Activity During Machine-Based Shoulder Press in Untrained Individuals (J Clin Med 2026;15(10):3925); Wernbom M, Aagaard P - Muscle fibre activation and fatigue with low-load blood flow restricted resistance exercise: An integrative physiology review (Acta Physiol 2020;228(1):e13302)"
url: https://pmc.ncbi.nlm.nih.gov/articles/PMC5758546/ ; https://pubmed.ncbi.nlm.nih.gov/26670996/ ; https://pubmed.ncbi.nlm.nih.gov/26705245/ ; https://pubmed.ncbi.nlm.nih.gov/28834797/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC5617935/ ; https://pubmed.ncbi.nlm.nih.gov/29533715/ ; https://pubmed.ncbi.nlm.nih.gov/39214526/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC13207441/ ; https://pubmed.ncbi.nlm.nih.gov/31108025/
data_pubblicazione: "2016-2026"
data_verifica: "2026-09-24"
affidabilità: media
note_di_onestà: >
  Numeri e conclusioni presi dagli abstract integrali recuperati dalle API
  E-utilities di NCBI. Tre delle fonti metodologiche (Vigotsky 2016 e 2017)
  sono **lettere all'editore e commenti**, non articoli originali: sono
  autorevoli e molto citate, ma è corretto presentarle come argomentazione
  metodologica, non come dati sperimentali. Lo studio di Schoenfeld 2018 sul
  focus attentivo è su **30 uomini non allenati** e dura 8 settimane: è
  l'unico studio longitudinale disponibile sul tema e non basta a concludere
  nulla di definitivo. Lo studio coreano del 2026 sulla connessione
  mente-muscolo è **acuto** (una sola sessione) e gli autori stessi dicono che
  servono studi per sapere se si traduce in risultati a lungo termine. **Non ho
  trovato** nessuno studio che verifichi direttamente se l'ampiezza dell'EMG
  misurata durante un esercizio predice la crescita prodotta da quell'esercizio
  nel tempo: l'argomento qui è di tipo metodologico e indiretto, e va
  presentato come tale.
```

## Perché questo file esiste

"Questo esercizio attiva di più il muscolo, quindi lo fa crescere di più" è
una delle frasi più comuni in palestra, ed è anche il tipo di affermazione che
un LLM generico riproduce con facilità, perché compare ovunque nei contenuti
fitness. Questo documento serve a impedire che Kilo la ripeta.

## Cosa misura davvero l'EMG di superficie

L'elettromiografia di superficie registra il **segnale elettrico** che arriva
agli elettrodi appoggiati sulla pelle sopra un muscolo. L'ampiezza di quel
segnale è il risultato di molte cose insieme, non solo di "quanto lavora il
muscolo".

La revisione di Vigotsky e colleghi (Frontiers in Physiology 2018) è dedicata
esattamente al problema: confrontare l'ampiezza dell'EMG fra muscoli diversi,
fra esercizi diversi, fra tecniche o carichi diversi, e poi trarne conclusioni
sui meccanismi neurofisiologici della produzione di forza o **ipotizzare
adattamenti a lungo termine come forza e ipertrofia**. La conclusione degli
autori è netta: conclusioni di quel tipo sono **spesso infondate e non
giustificate**.

I due punti metodologici da tenere fermi:

1. **Il reclutamento delle unità motorie non si può dedurre dall'ampiezza
   dell'EMG di superficie** (Vigotsky, Ogborn & Phillips 2016). È un'inferenza
   che il segnale non consente.
2. **Una risposta elettromiografica maggiore non implica un maggiore
   reclutamento, e il "potenziale ipertrofico" non si può dedurre**
   (Vigotsky et al. 2017). Il titolo di quel commento è letteralmente questa
   frase.

Una conferma indiretta ma istruttiva viene da un campo vicino: nella revisione
sull'allenamento con restrizione del flusso sanguigno, l'attivazione delle
fibre di tipo II è stata finora dedotta soprattutto con metodi **indiretti**
come l'EMG, e solo raramente con metodi diretti (glicogeno e fosfocreatina
nelle fibre); resta perciò un'incertezza considerevole su quali fibre lavorino
davvero (Wernbom & Aagaard, Acta Physiol 2020).

## La dissociazione più chiara: carichi leggeri contro carichi pesanti

È il caso che mostra meglio perché l'EMG non predice la crescita.

- **Cosa dice l'EMG**: in un confronto diretto su soggetti allenati, quattro
  serie di leg extension al 30% e all'80% del massimale, entrambe fino a
  cedimento, l'**ampiezza dell'EMG era significativamente maggiore con il
  carico pesante** (p ≤ 0,01). Le risposte molecolari legate all'ipertrofia
  (mRNA e fosfoproteine), invece, erano **simili** fra le due condizioni
  (Haun 2017).
- **Cosa succede davvero nel tempo**: la meta-analisi su 21 studi che hanno
  confrontato carichi bassi (≤60% 1RM) e alti (>60% 1RM), tutti portati a
  cedimento muscolare momentaneo, per almeno 6 settimane, trova che i
  guadagni di **1RM sono maggiori con i carichi alti**, ma le variazioni di
  **ipertrofia sono simili** fra le due condizioni (Schoenfeld 2017).

Quindi: l'EMG è più alto con il carico pesante, la crescita è la stessa. Se
l'EMG predicesse l'ipertrofia, questo risultato non esisterebbe.

## Connessione mente-muscolo: cosa mostrano gli studi

Qui il quadro è più sfumato e va raccontato per intero, senza né liquidarlo né
gonfiarlo.

**Effetto acuto sull'attivazione: documentato.** Trentuno giovani adulti senza
esperienza di allenamento hanno eseguito una shoulder press alla macchina al
40% del massimale in tre condizioni: senza focus, concentrandosi sul deltoide,
concentrandosi sul tricipite. L'attività del deltoide è risultata maggiore
nella condizione "deltoide" e quella del tricipite nella condizione
"tricipite" (p < 0,001), mentre il trapezio superiore non è cambiato
(p > 0,05). Gli autori concludono che il focus attentivo può selezionare
l'attivazione del muscolo bersaglio — e che **servono studi per sapere se
questo si traduce in risultati a lungo termine** (Kim 2026).

**Effetto a lungo termine: un solo studio, su principianti.** Trenta uomini
non allenati, 8 settimane, 3 sedute a settimana, 4 serie da 8-12 ripetizioni
per esercizio, assegnati a focus **interno** (concentrarsi sul muscolo che
lavora) o **esterno** (concentrarsi sul risultato dell'alzata). Lo spessore
dei flessori del gomito è aumentato significativamente di più nel gruppo a
focus interno: **+12,4% contro +6,9%**; cambiamenti simili nel quadricipite.
Sulla forza isometrica i risultati sono andati in direzioni opposte (gomito a
favore del focus interno, ginocchio a favore di quello esterno) ma **nessuno
dei due ha raggiunto la significatività statistica** (Schoenfeld 2018).

Un solo studio, su trenta principianti, otto settimane: è un indizio, non una
prova. Va citato come tale.

**Quello che le persone percepiscono non corrisponde all'EMG.** Tredici
calciatori sub-elite hanno eseguito sei esercizi per la parte alta del corpo a
carichi da 4-6 RM e poi hanno valutato su una scala da 1 a 10 quanto
sentivano lavorare tre muscoli per esercizio; in una sessione successiva la
stessa attività è stata misurata con l'EMG su otto muscoli. Risultato:
**nessuna correlazione significativa** fra attivazione percepita e
attivazione misurata, in nessuno degli esercizi. Gli autori parlano di scarsa
consapevolezza interocettiva dei muscoli e avvertono contro l'uso della
sensazione percepita come unico indicatore (Sevilmiş 2024).

Nello stesso studio, un dettaglio che smonta un'altra convinzione comune: in
tutti gli esercizi esaminati **non c'era differenza di attività fra i muscoli
primari e quelli sinergici**.

## Le tre frasi da non dire mai

1. **"Questo esercizio attiva di più il muscolo, quindi lo fa crescere di
   più."** Il potenziale ipertrofico non si deduce dall'EMG, e nel caso più
   studiato (carichi leggeri contro pesanti) l'EMG e la crescita vanno in
   direzioni diverse.
2. **"Se non lo senti, non lo stai allenando."** La sensazione di attivazione
   non correla con l'attivazione misurata.
3. **"L'EMG dimostra che questo muscolo viene reclutato al 90%."** Dall'EMG di
   superficie non si deduce il reclutamento delle unità motorie, e
   l'ampiezza normalizzata non è una percentuale di fibre.

## Uso in Kilo

- **Quando l'utente cita uno studio EMG** ("ho letto che il pullover attiva il
  gran dorsale più delle trazioni"): spiegare con calma che l'EMG misura il
  segnale elettrico in superficie e che da lì non si può dedurre né il
  reclutamento né la crescita futura. Non liquidare l'utente: è una
  convinzione ragionevole e diffusissima.
- **Quando l'utente chiede "qual è l'esercizio che attiva di più X?"**:
  riformulare la domanda. I criteri con cui Kilo sceglie gli esercizi sono
  quelli di `exercise_choice_and_focus.md`, `biomechanics_technique.md` e
  `stretch_mediated_hypertrophy.md` — schema di movimento, ampiezza,
  posizione allungata, sostenibilità — non l'ampiezza dell'EMG.
- **Quando l'utente chiede della connessione mente-muscolo**: dire che
  l'effetto acuto sull'attivazione è documentato, che l'unico studio
  longitudinale (su principianti, 8 settimane) ha mostrato più crescita ai
  flessori del gomito con il focus interno, e che è troppo poco per
  prescriverlo come regola. Non è dannoso e non costa nulla provarlo: è una
  preferenza personale legittima.
- **Quando l'utente dice di non "sentire" un muscolo**: non trattarlo come un
  problema tecnico grave. La percezione non corrisponde all'attivazione
  misurata. Guardare piuttosto ampiezza di movimento, carico e progressione.
- Questo file lavora insieme a `evidence_conduct.md`, punto 5 della gerarchia:
  la tradizione da palestra va **riconosciuta e corretta**, spiegando perché
  la fonte più solida dice altro.

**Traduzione operativa dichiarata**: l'elenco delle "tre frasi da non dire" è
una regola di condotta di progetto, non una raccomandazione delle fonti. Le
fonti forniscono l'argomento metodologico; la scelta di vietare quelle
formulazioni nell'agente è nostra.
