```yaml
argomento: volume di allenamento settimanale per ipertrofia
fonte: "Pelland JC, Remmert JF, Robinson ZP, Hinson SR, Zourdos MC - The Resistance Training Dose Response: Meta-Regressions Exploring the Effects of Weekly Volume and Frequency on Muscle Hypertrophy and Strength Gains (Sports Medicine, 2026)"
url: https://pubmed.ncbi.nlm.nih.gov/41343037/
doi: 10.1007/s40279-025-02344-w
data_pubblicazione: "2026 (accettato a ottobre 2025; preprint SportRxiv 2024)"
data_verifica: "2026-09-15"
affidabilità: alta
note_di_onestà: >
  Aggiornato il 2026-09-15 alla versione pubblicata, letta sul testo
  integrale da una copia PDF non ufficiale (l'articolo non è open access).
  La versione precedente del file si basava sull'abstract del preprint: ho
  tolto due affermazioni che venivano da lì e non ho ricontrollato sul testo
  (guadagni sostanziali con ≤4 serie; peggioramento ad alti volumi secondo
  Baz-Valle 2022). Gli autori dichiarano di essere coach e autori di
  contenuti nel settore fitness. Per la soglia di ~10 serie vedi anche
  `hypertrophy_prescription.md` (IUSCA) e `resistance_training_acsm.md`
  (ACSM 2026).
```

## Cosa dice la ricerca attuale (Pelland et al. 2026)

- **Base**: 67 studi, 2058 partecipanti (79% uomini, età media ~25 anni),
  modelli corretti per durata dell'intervento e livello di allenamento.
- **Serie dirette e indirette**: il modello che predice meglio i risultati
  conta **1** ogni serie che allena direttamente il muscolo e **0,5** ogni
  serie in cui lavora da secondario (es. la panca per i tricipiti).
- **Volume e ipertrofia**: più serie producono più crescita, con **rendimenti
  decrescenti**; **nessun plateau chiaro**, ma l'incertezza aumenta ai volumi
  alti.
- **Volume e forza**: rendimenti decrescenti molto più marcati, fino a un
  plateau funzionale.
- **Frequenza e ipertrofia**: a parità di volume l'effetto è
  **trascurabile**: la frequenza per muscolo si sceglie per preferenza e
  organizzazione.
- **Frequenza e forza**: effetto positivo, con rendimenti decrescenti.
- **Contesto storico**: Schoenfeld et al. 2017 trovava effetti più ampi con
  ≥9 serie/settimana per muscolo (ES 0,46) che con <9 (ES 0,32), differenza
  non significativa (p = 0,076).
- Non esiste un numero "giusto per tutti": la forma della curva resta incerta
  e la capacità di recupero, il sonno e lo stress variano da persona a
  persona.
- **Nota su Kilo**: il generatore conta solo le serie degli esercizi con
  quel muscolo come primario. Con il metodo "frazionario" il volume reale è
  un po' più alto (es. le distensioni aggiungono mezze serie ai tricipiti).

## Come tradurlo in parametri per la generazione di una scheda

Obiettivi diversi dalla massa muscolare (definizione, forza, mantenimento,
salute generale):

| Profilo utente | Range (serie/settimana/gruppo muscolare) | Partenza |
|---|---|---|
| Principiante (< 6 mesi di allenamento continuativo) | 4-8 | 5 |
| Intermedio | 8-14 | 10 |
| Avanzato, buon recupero dichiarato | 12-20, con attenzione ai segnali di sovraccarico | 14 |

Obiettivo massa muscolare, allineato a `hypertrophy_prescription.md` (IUSCA:
~10 serie a settimana come minimo per ottimizzare) e
`resistance_training_acsm.md` (ACSM 2026: ≥10 serie, rendimenti decrescenti
oltre ~18-20):

| Profilo utente | Range | Partenza |
|---|---|---|
| Principiante | 6-14 | 10 |
| Intermedio | 8-16 | 12 |
| Avanzato | 10-20 | 14 |

Nel range, il minimo è il pavimento dell'autoregolazione (sotto non si
scende: si guardano sonno e alimentazione) e il massimo il tetto oltre cui
non si aggiungono serie. Gli aumenti sono al massimo del **20%** per volta,
dopo almeno 4 settimane (IUSCA). Oltre ~10 serie per muscolo nella stessa
seduta la scheda suggerisce di distribuirle su più giorni.

Questi range **non sono nelle fonti in questa forma tabellare**: la soglia di
~10 serie, il tetto di ~18-20 e il limite del 20% sì, i singoli valori sono
una traduzione operativa pensata per un algoritmo di generazione scheda.
Vanno trattati come punto
di partenza regolabile, non come regola rigida, e l'agente dovrebbe sempre
lasciare margine di aggiustamento in base al feedback dell'utente (DOMS
eccessivo, stanchezza persistente → ridurre; progressi assenti con buon
recupero → valutare incremento).

## Segnali di uso scorretto da evitare nell'agente

- Non proporre sempre lo stesso schema fisso (es. "3x10 per tutti") —
  la fonte primaria mostra che il range efficace è ampio e dipende dal
  profilo.
- Non trattare il volume più alto come sempre "meglio": va bilanciato con il
  recupero dichiarato dall'utente (sonno, stress, giorni di allenamento
  disponibili).
