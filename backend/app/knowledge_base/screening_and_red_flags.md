```yaml
argomento: screening di sicurezza pre-allenamento e condizioni che richiedono un medico
fonte: "PAR-Q+ (Physical Activity Readiness Questionnaire for Everyone), versione 2023 - eparmedx.com, strumento raccomandato da ACSM"
url: https://eparmedx.com/
data_pubblicazione: "2023"
data_verifica: "2026-09-08"
affidabilità: alta
note_di_onestà: >
  Il PAR-Q+ è uno strumento di screening standardizzato, non una fonte di
  parametri numerici come gli altri file. Va usato come base per un
  questionario obbligatorio PRIMA di generare qualsiasi scheda con carichi
  progressivi. Questo file è il guardrail di sicurezza più importante di
  tutta la knowledge base.
```

## Perché questo file viene prima di tutti gli altri

Nessuna scheda di allenamento o piano nutrizionale con obiettivi aggressivi
(deficit calorico marcato, carichi progressivi) dovrebbe essere generata
**senza prima passare da questo screening**. È il guardrail per la salute
fisica: Kilo propone, non agisce mai da solo.

## Domande di screening (adattate da PAR-Q+) da porre nell'interfaccia

Prima di generare la prima scheda, l'utente deve rispondere a:

1. Un medico ti ha mai detto che hai un problema cardiaco e che dovresti
   fare attività fisica solo sotto controllo medico?
2. Provi dolore al petto a riposo o durante le attività quotidiane?
3. Hai perso l'equilibrio a causa di vertigini o hai perso conoscenza negli
   ultimi 12 mesi?
4. Hai una diagnosi di un'altra condizione cronica (diabete, malattia
   renale, ecc.)?
5. Stai assumendo farmaci per la pressione o per il cuore?
6. Hai un problema osseo o articolare che potrebbe peggiorare con l'attività
   fisica (es. infortunio recente, protesi, ernia)?
7. Sei incinta o hai partorito nelle ultime settimane?
8. Hai avuto una storia di disturbi alimentari?

**Qualsiasi risposta "sì"** non blocca l'uso dell'app, ma **deve**:
- disattivare la generazione automatica di piani con deficit calorico
  aggressivo o progressione di carico standard,
- mostrare un messaggio esplicito che raccomanda una valutazione medica
  prima di procedere,
- registrare la condizione dichiarata per adattare (non ignorare) i
  consigli successivi (es. sostituire esercizi ad alto impatto in caso di
  problemi articolari).

## Età: attenzione separata

- **Minorenni**: la generazione di piani con carichi progressivi e deficit
  calorico va gestita con cautela molto maggiore o esclusa dall'MVP — le
  linee guida per adolescenti in accrescimento sono un ambito diverso da
  quello coperto dalle fonti ISSN/EFSA in questa knowledge base, pensate per
  adulti.
- **Over 65**: nessuna esclusione, ma la progressione di carico dovrebbe
  partire più conservativa (coerente col range "principiante" di
  `training_volume.md` anche per chi è avanzato in altri sport, se nuovo
  alla sala pesi).

## Come tradurlo in logica applicativa

1. Il PAR-Q+ è un **gate**, non un dettaglio opzionale del profilo: va
   completato prima che l'agente generi la prima scheda.
2. Ogni "sì" produce un flag salvato sul profilo utente, non solo un
   messaggio una tantum — deve influenzare ogni generazione successiva.
3. L'agente non diagnostica né sostituisce il parere medico: comunica
   sempre in termini di "ti consiglio di verificare con un medico prima",
   mai "puoi procedere comunque perché...".
