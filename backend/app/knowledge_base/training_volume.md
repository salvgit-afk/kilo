```yaml
argomento: volume di allenamento settimanale per ipertrofia
fonte: "The Resistance Training Dose-Response: Meta-Regressions Exploring the Effects of Weekly Volume and Frequency on Muscle Hypertrophy and Strength Gain"
url: https://sportrxiv.org/index.php/server/preprint/view/460
data_pubblicazione: "2025/2026 (meta-regressione più recente reperita)"
data_verifica: "2026-09-08"
affidabilità: media
note_di_onestà: >
  Estratto da abstract/riassunti di ricerca, non dal testo integrale.
  Corrobora e aggiorna risultati più vecchi e molto citati (Schoenfeld et
  al. 2017; Baz-Valle et al. 2022) che vanno nella stessa direzione.
  Da rivedere se emergono meta-analisi più recenti.
```

## Cosa dice la ricerca attuale

- Esiste una **relazione dose-risposta graduale**: più serie settimanali per
  gruppo muscolare, maggiore ipertrofia — ma **non linearmente all'infinito**.
- **≤4 serie/settimana per gruppo muscolare** producono già guadagni
  sostanziali — utile come punto di partenza per principianti o utenti a
  basso tempo disponibile, non da liquidare come "troppo poco".
- L'effetto più marcato si osserva nel range **5-10+ serie/settimana** per
  gruppo muscolare (Schoenfeld et al. 2017, ancora il riferimento più citato
  su questo range specifico).
- Oltre una certa soglia (variabile per individuo, capacità di recupero,
  esperienza) si osservano **rendimenti decrescenti**, e in alcuni studi
  controllati un peggioramento, plausibilmente per accumulo di fatica e
  minore qualità di esecuzione per serie (Baz-Valle et al. 2022).
- Non esiste un singolo numero "giusto per tutti": la soglia di rendimenti
  decrescenti dipende da capacità di recupero, sonno, stress, esperienza di
  allenamento e altre variabili individuali.

## Come tradurlo in parametri per la generazione di una scheda

| Profilo utente | Range di partenza (serie/settimana/gruppo muscolare) |
|---|---|
| Principiante (< 6 mesi di allenamento continuativo) | 4-8 |
| Intermedio | 8-14 |
| Avanzato, buon recupero dichiarato | 12-20, con attenzione ai segnali di sovraccarico |

Questi range **non sono nella fonte citata in questa forma tabellare** — sono
una traduzione operativa ragionevole dei risultati sopra, pensata per essere
applicabile a un algoritmo di generazione scheda. Vanno trattati come punto
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
