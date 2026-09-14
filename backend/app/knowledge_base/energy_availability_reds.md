```yaml
argomento: bassa disponibilità energetica e REDs (Relative Energy Deficiency in Sport) - rischio del deficit calorico aggressivo combinato con allenamento intenso
fonte: "2023 International Olympic Committee's (IOC) consensus statement on Relative Energy Deficiency in Sport (REDs) - Br J Sports Med 2024;57:1073-1098"
url: https://stillmed.olympics.com/media/Documents/Athletes/Medical-Scientific/Consensus-Statements/REDs/BJSM-IOC-consensus-statement-on-Relative-Energy-Deficiency-in-Sport-REDs.pdf
data_pubblicazione: "2023 (aggiornamento del consensus 2014/2018)"
data_verifica: "2026-09-10"
affidabilità: alta
note_di_onestà: >
  **Letto direttamente dal PDF ufficiale** (26 pagine, consultate le prime
  6 in dettaglio). È la fonte più autorevole possibile su questo tema (IOC,
  144 dichiarazioni votate da un panel internazionale di 17 esperti). Questo
  file esiste per collegare un rischio reale al `calorie_and_1rm_formulas.md`,
  che menzionava il "deficit aggressivo" senza una fonte dedicata.
```

## Perché questo file è importante per l'agente

`calorie_and_1rm_formulas.md` segnala già che un deficit calorico >25%
andrebbe "valutato con un professionista". Questo file spiega **perché**,
con una fonte seria: un deficit calorico aggressivo **combinato con
allenamento intenso** è esattamente lo scenario che porta a REDs — non è un
rischio teorico, è il meccanismo centrale descritto dal consensus IOC.

## Cos'è la Disponibilità Energetica (EA) — formula applicabile

```
EA (kcal/kg FFM/giorno) = (Intake calorico - Dispendio energetico da esercizio) / Massa magra (kg)
```

FFM = Fat-Free Mass, massa magra (peso corporeo meno massa grassa). Non è
lo stesso concetto del semplice "deficit calorico" (TDEE - intake): qui il
denominatore è la massa magra, non il peso totale, e si sottrae solo
l'energia spesa nell'esercizio, non il TDEE completo.

## Il continuum: LEA adattabile vs problematica

- **LEA adattabile**: riduzione di disponibilità energetica lieve,
  transitoria, con effetti benigni e reversibili (es. periodo di definizione
  ben gestito, monitorato, di durata limitata).
- **LEA problematica**: esposizione prolungata/severa, porta a **REDs** —
  compromissione di più sistemi corporei simultaneamente.
- Non esiste una soglia universale netta (il valore storico di riferimento
  ~30 kcal/kg FFM/giorno come "a rischio" nelle donne è dibattuto nella
  fonte stessa), ma il principio guida è chiaro: **più il deficit è
  prolungato/severo e combinato con alto volume di allenamento, più il
  rischio cresce**.

## Segnali di allarme (da entrambi i sessi)

La fonte elenca sistemi corporei multipli potenzialmente colpiti da REDs:
funzione riproduttiva, salute ossea, funzione immunitaria, cardiovascolare,
ematologica, crescita/sviluppo, metabolismo energetico, salute mentale,
disturbi del sonno, funzione neurocognitiva, funzione muscolo-scheletrica.

Segnali pratici più riconoscibili per un'interfaccia utente (non
esaustivi, non diagnostici):
- **Donne**: cicli mestruali irregolari o assenti.
- **Uomini**: calo della libido, riduzione delle erezioni mattutine
  (segnalati esplicitamente dalla fonte come conseguenze fisiologiche
  osservabili della bassa disponibilità energetica maschile).
- Entrambi i sessi: affaticamento persistente non giustificato, infortuni
  o malattie ricorrenti, recupero scarso nonostante il riposo, calo di
  performance non spiegato da altre cause, comportamenti alimentari
  restrittivi o compulsivi.

## Come tradurlo in logica applicativa

1. **Non trattare un deficit aggressivo come "solo" una scelta di
   definizione più rapida** — è un fattore di rischio reale quando combinato
   con volume di allenamento alto, non un semplice trade-off tempo/risultato.
2. Se l'utente combina **deficit calorico marcato (>20-25%) E alto volume
   settimanale di allenamento (fascia alta di `training_volume.md`) E**
   una o più risposte affermative allo screening (`screening_and_red_flags.md`,
   in particolare storia di disturbi alimentari): l'agente dovrebbe
   **moderare attivamente** il piano proposto (deficit meno aggressivo,
   volume non massimale) invece di generare comunque la combinazione più
   estrema richiesta.
3. Se emergono segnali come cicli irregolari, calo di libido persistente,
   o affaticamento/infortuni ricorrenti in un contesto di deficit
   prolungato: l'agente deve raccomandare esplicitamente una valutazione
   medica, non provare a "risolvere" il problema con un aggiustamento di
   macro.
4. L'agente **non diagnostica REDs** — non è uno strumento clinico. Il suo
   ruolo è riconoscere il pattern di rischio (deficit + volume alto +
   segnali) e indirizzare, esattamente come per `screening_and_red_flags.md`.

## Segnali di uso scorretto da evitare nell'agente

- Non generare piani con deficit molto aggressivo "perché l'utente lo ha
  chiesto" senza mai segnalare il rischio, specie se combinato con alto
  volume di allenamento.
- Non minimizzare segnali come amenorrea come "normale quando ci si
  allena tanto" — è uno dei segnali che la fonte associa esplicitamente a
  possibile LEA problematica.
