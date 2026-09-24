# Knowledge base — allenamento e nutrizione

Questi file sono la **fonte di verità numerica** per l'agente. Le schede di
allenamento e i piani alimentari **non vengono inventati dall'LLM**: l'LLM
personalizza e spiega, ma i range/parametri (serie a settimana, g/kg di
proteine, dosaggio creatina, ecc.) vengono letti da qui.

## Perché esiste questa cartella

Un LLM generico rischia di riproporre nozioni datate o "bro-science" prese
dal suo addestramento. Mettendo i parametri in file separati, versionati e
con fonte citata:

- il ragionamento dell'agente è **ispezionabile** (si può controllare *da
  dove* viene un numero);
- **aggiornare la scienza è modificare un file**, non riscrivere codice o
  sperare che il modello "sappia" qualcosa di più recente;
- si può segnalare onestamente quando una fonte non è freschissima (es.
  LARN 2014) invece di spacciarla per attuale.

## Formato di ogni file

Ogni documento inizia con un blocco di metadati:

```yaml
argomento: ...
fonte: ...           # nome ente/società + titolo esatto del documento
url: ...
data_pubblicazione: ...
data_verifica: ...    # quando è stato controllato/inserito in questo progetto
affidabilità: alta | media | da_verificare_sul_testo_integrale
note_di_onestà: ...    # limiti noti della fonte o dell'estrazione
```

seguito dal contenuto in prosa che l'agente usa come contesto.

## Elenco documenti e tag

| File | Tag | Quando viene caricato |
|---|---|---|
| `screening_and_red_flags.md` | `screening` | **Sempre**, prima di ogni prima generazione scheda/piano per un utente |
| `energy_availability_reds.md` | `deficit_calorico`, `reds` | Generazione piano alimentare con deficit, specie se combinato con volume alto |
| `who_physical_activity.md` | `attivita_generale` | Utenti con obiettivo salute generale, non solo ipertrofia; sempre per over 65 |
| `training_volume.md` | `volume_allenamento` | Generazione/modifica scheda allenamento |
| `rest_periods_and_rir.md` | `recupero`, `intensità` | Generazione scheda allenamento |
| `proximity_to_failure.md` | `cedimento` | Domande su cedimento/RIR, volume già al massimo |
| `doms_and_autoregulation.md` | `doms`, `autoregolazione` | L'utente riferisce dolori o assenza di progressi |
| `exercise_choice_and_focus.md` | `scelta_esercizi`, `focus_attentivo` | Sostituzione esercizi, preferenze dell'utente |
| `hypertrophy_prescription.md` | `ipertrofia`, `tecniche_avanzate`, `cardio` | Scheda con obiettivo massa muscolare; domande su ripetizioni, drop set/superserie, cardio insieme ai pesi |
| `biomechanics_technique.md` | `biomeccanica`, `tecnica_esecuzione`, `ampiezza_movimento` | Domande su tecnica, ampiezza di movimento, allungamento, cadenza, stretching; motiva la preferenza di generatore e sostituzioni per leg curl da seduti ed estensioni dei tricipiti sopra la testa |
| `resistance_training_acsm.md` | `progressione`, `forza`, `frequenza_allenamento`, `periodizzazione` | **Ogni** generazione scheda; domande su carichi, frequenza, progressione, livello di esperienza |
| `training_dose_response.md` | `dose_risposta`, `volume_settimanale` | Domande su quante serie/quante volte a settimana; forma della curva dose-risposta di volume e frequenza (Pelland 2026). Approfondisce `training_volume.md` |
| `stretch_mediated_hypertrophy.md` | `allungamento`, `parziali` | Domande su allenamento in allungamento, ripetizioni parziali, scelta fra varianti di uno stesso esercizio; è la fonte del campo `lengthened_note` di `exercise_guidance.py` |
| `advanced_techniques_efficiency.md` | `tecniche_intensita`, `allenamento_breve` | Domande su drop set, rest-pause, myo-reps, cluster set, rest-redistribution; utente che dichiara di avere poco tempo |
| `detraining_and_return.md` | `pausa_allenamento`, `ripresa` | Utente fermo da un periodo, di ritorno dopo una pausa, o che sa di doversi fermare (viaggio, infortunio) |
| `muscle_activation_emg.md` | `attivazione_muscolare`, `emg` | Domande su "quale esercizio attiva di più", studi EMG, connessione mente-muscolo, "non sento il muscolo" |
| `calorie_and_1rm_formulas.md` | `calorie`, `1rm` | Calcolo target calorico, report progressione |
| `protein_intake.md` | `proteine` | Piano alimentare, valutazione integratore proteico |
| `diets_body_composition.md` | `composizione_corporea`, `surplus_calorico`, `tipi_dieta` | Target con obiettivo massa o definizione; domande su surplus, keto/low-carb, digiuno intermittente |
| `macronutrients_efsa.md` | `macronutrienti`, `zuccheri` | Piano alimentare, generazione/valutazione ricette |
| `micronutrients_efsa.md` | `micronutrienti` | Piano alimentare, in particolare per utenti vegetariani/vegani |
| `nutrient_timing.md` | `timing_pasti` | Piano alimentare attorno alle sessioni di allenamento |
| `hydration.md` | `idratazione` | Consigli durante/dopo allenamento |
| `standard_portions.md` | `porzioni` | Porzioni standard italiane (LARN 2024), pesi di cucchiai e cucchiaini |
| `creatine.md` | `creatina` | Utente dichiara uso creatina |
| `caffeine.md` | `caffeina` | Utente dichiara uso caffeina/pre-workout |
| `glutamine.md` | `glutammina` | Utente dichiara uso glutammina |
| `beta_alanine.md` | `beta_alanina` | Utente dichiara uso beta-alanina |
| `hmb.md` | `hmb` | Utente dichiara uso HMB |
| `bcaa.md` | `bcaa` | Utente dichiara uso BCAA |
| `citrulline_malate.md` | `citrullina` | Utente dichiara uso citrullina malato |
| `vitamin_d_omega3_supplementation.md` | `vitamina_d`, `omega3` | Utente dichiara integrazione vitamina D o omega-3/olio di pesce/alghe |
| `supplement_evidence_categories.md` | `categorie_integratori` | Domande generiche sugli integratori o su integratori senza file dedicato (tribulus, arginina, carnitina, bicarbonato, nitrati…) |
| `supplement_quality_safety.md` | `qualita_prodotto` | **Sempre insieme** a qualunque integratore dichiarato (creatina, proteine, ecc.) — rischio da contaminazione/etichettatura, non da dosaggio |
| `vegetarian_vegan_nutrition.md` | `vegetariano`, `vegano` | Piano alimentare/ricette per utenti che dichiarano dieta vegetariana o vegana |
| `sleep_and_recovery.md` | `sonno`, `recupero_notturno` | Utente che riferisce di dormire poco o male; domande su recupero notturno, stanchezza, ore di sonno |
| `women_training_menstrual_cycle.md` | `donne`, `ciclo_mestruale` | Domande su allenamento e nutrizione nelle donne, periodizzazione sul ciclo, pillola, menopausa |
| `evidence_conduct.md` | *(nessuno — regola trasversale)* | **Sempre** in ogni prompt di generazione, indipendentemente dal topic |

## Come li usa l'agente (meccanismo)

Non serve un vero motore RAG/vettoriale per iniziare: l'insieme di argomenti
è piccolo e noto in anticipo. Basta un **retrieval per tag**:

1. Ogni richiesta (genera scheda / genera piano pasti / valuta un
   integratore dichiarato) è associata a 1-3 tag dalla tabella sopra.
2. Il backend carica il/i file corrispondenti e li inietta nel prompt come
   contesto, insieme al profilo utente.
3. L'LLM genera output vincolato a quei numeri, non a piacere.
4. `screening_and_red_flags.md` è un caso speciale: non è solo "contesto
   per generare meglio". Se lo screening ha almeno un «sì», il generatore
   fissa il volume al minimo del range e avvisa di consultare un medico
   prima di aumentarlo.

Se in futuro la knowledge base cresce molto, questo stesso schema regge
un passaggio a un vero store con embedding — ma non serve adesso.

## Manutenzione

Ogni file ha una `data_verifica`. **Va rivista periodicamente** (indicativamente
ogni 12-18 mesi, o prima se esce una nuova revisione della fonte citata):
la scienza dell'allenamento e della nutrizione evolve, e questo meccanismo
non si aggiorna da solo.

## Importante: come sono stati estratti questi contenuti

**Aggiornamento 2026-09-10**: `poppler-utils` è stato installato
sull'ambiente, il che ha permesso di leggere direttamente PDF ufficiali
(scaricati sia in precedenza sia appositamente per questo aggiornamento) e
**passare da `affidabilità: media` (riassunti secondari) ad `affidabilità:
alta` (testo primario verificato)**:

- `macronutrients_efsa.md` e `micronutrients_efsa.md` — confermati sul PDF
  ufficiale EFSA ("Summary of Dietary Reference Values", versione 4, 2017).
  Tutti i numeri sui macronutrienti erano già corretti; aggiunti dati non
  ancora presenti (omega-3/6, acqua, minerali, vitamine).
- `vegetarian_vegan_nutrition.md` — confermato sul PDF ufficiale Academy of
  Nutrition and Dietetics (Position Paper 2025, in vigore fino al 2032).
  Corretto un dettaglio: lo zinco non è nella lista ufficiale dei nutrienti
  critici di questa fonte (la colina invece sì, ed era assente dalla
  versione precedente del file); aggiunta una soglia proteica specifica
  (≥1,5 g/kg/giorno) per non compromettere gli adattamenti muscolari su
  dieta vegetale.
- `who_physical_activity.md` (nuovo) — dal PDF ufficiale WHO "Guidelines on
  Physical Activity and Sedentary Behaviour: at a glance" (2020).
- `energy_availability_reds.md` (nuovo) — dal PDF ufficiale del consensus
  IOC 2023 su REDs, scaricato direttamente dal sito dell'International
  Olympic Committee (mirror alternativo, il dominio ufficiale
  `stillmed.olympics.com` non era raggiungibile dall'ambiente).

**Aggiornamento 2026-09-15**: il testo integrale degli articoli open access
su PubMed Central si recupera senza pagine anti-bot dall'API di Europe PMC
(`ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML`). Letti sul
testo integrale:

- `hypertrophy_prescription.md` (nuovo) — position stand IUSCA 2021
  sull'ipertrofia. La "NSCA Position Statement" sull'ipertrofia richiesta
  non esiste con quel titolo: vedi le note del file.
- `resistance_training_acsm.md` (nuovo) — ACSM Position Stand 2026, che
  aggiorna il "Progression Models" 2009 (riportato anch'esso).
- `diets_body_composition.md` (nuovo) — ISSN Position Stand 2017.
- `supplement_evidence_categories.md` (nuovo) — ISSN Exercise & Sports
  Nutrition Review Update 2018.
- `biomechanics_technique.md` (nuovo) — revisioni 2023-2026 su tecnica,
  ampiezza di movimento e allenamento in allungamento, studi di Maeo sui
  femorali e tricipiti, sezioni OpenStax sull'anatomia del muscolo.
- `training_volume.md` — **da `media` ad `alta`**: dall'abstract del
  preprint alla versione pubblicata di Pelland et al. (Sports Medicine 2026).
- `creatine.md` e `nutrient_timing.md` — **da `media` ad `alta`**, con due
  correzioni: lo "0,03 g/kg" di mantenimento della creatina e la finestra
  "1 ora prima / 1-4 ore dopo" del timing non comparivano nelle fonti.

**Aggiornamento 2026-09-24**: sette documenti nuovi, tutti verificati sugli
abstract strutturati integrali recuperati dalle API E-utilities di NCBI
(`eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&...`), che
restituiscono il testo senza le pagine anti-bot di PubMed. Restano ad
`affidabilità: media` tutti tranne `training_dose_response.md` perché sono
estrazioni da abstract, non da testo integrale.

- `training_dose_response.md` (nuovo, `affidabilità: alta`) — la
  meta-regressione Pelland et al. (Sports Medicine 2026) sulla relazione
  dose-risposta di volume e frequenza, già usata in `training_volume.md` ma
  mai riportata per esteso. Documenta il metodo di conteggio "frazionario"
  (0,5 per le serie indirette) e dice quali range di `training_volume.md`
  restano sostenuti dalla fonte e quali sono scelte di progetto.
- `stretch_mediated_hypertrophy.md` (nuovo) — dà una fonte esplicita al campo
  `lengthened_note` di `app/services/exercise_guidance.py`, studio per studio.
  Include il contrappeso onesto: la meta-analisi sull'ipertrofia regionale
  (Varovic 2025) trova differenze banali, e nei soggetti allenati (Wolf 2025)
  parziali in allungamento e movimento completo danno gli stessi risultati.
- `sleep_and_recovery.md` (nuovo) — **correzione di un'aspettativa**: la
  revisione sistematica 2025 su sonno e forza (Easow, Sleep and Breathing) è
  narrativa e **non riporta alcun effect size aggregato**. L'unica cifra
  aggregata disponibile viene dalla meta-analisi di Craven (Sports Medicine
  2022): −7,56% di prestazione con perdita di sonno. Il file dichiara
  esplicitamente che una "dose di sonno per l'ipertrofia" non è prescrivibile.
- `advanced_techniques_efficiency.md` (nuovo) — meta-analisi 2026 su drop set,
  rest-pause, cluster set e rest-redistribution: a parità di volume e impegno
  l'ipertrofia è uguale, il vantaggio è il tempo (circa metà seduta, secondo
  Iversen 2021).
- `detraining_and_return.md` (nuovo) — soglia delle 4 settimane (Mujika &
  Padilla 2000), meta-analisi di Bosquet 2013, dose minima di mantenimento
  (Bickel 2011: un terzo o un nono del volume basta ai giovani, non agli
  anziani) e lo studio Halonen 2024 sulle pause programmate.
- `muscle_activation_emg.md` (nuovo) — perché l'EMG di superficie non predice
  la crescita, e cosa mostrano davvero gli studi sulla connessione
  mente-muscolo. Serve soprattutto a evitare che l'agente ripeta affermazioni
  da palestra.
- `women_training_menstrual_cycle.md` (nuovo) — le revisioni concludono che
  **non ci sono prove sufficienti** per periodizzare l'allenamento sul ciclo
  mestruale; il file lo dice apertamente e riporta solo ciò che è documentato,
  inclusi i numeri nutrizionali del position stand ISSN 2023 sulle atlete.

I restanti file (proteine ISSN, caffeina, recupero, idratazione,
beta-alanina, HMB, BCAA) restano a `affidabilità: media`. Molti sono open
access e ora recuperabili con Europe PMC: sono i prossimi candidati da
rileggere sul testo integrale. Nota storica:
il testo integrale su PubMed Central, Springer e Taylor&Francis blocca
ancora il recupero automatico con pagine anti-bot/reCAPTCHA (un problema
diverso da quello risolto con poppler-utils, che serviva solo per
renderizzare PDF già scaricati, non per aggirare i blocchi di accesso). Se
vuoi la massima precisione su questi, scaricami tu i PDF da browser
(aggirando il blocco anti-bot) e ora posso leggerli direttamente.

`screening_and_red_flags.md` (PAR-Q+), `calorie_and_1rm_formulas.md`
(formule matematiche standard) ed `evidence_conduct.md` (regole di condotta
interne) hanno `affidabilità: alta` per un motivo diverso: non dipendono da
un'estrazione di questo tipo fin dall'inizio.
