```yaml
argomento: fabbisogno proteico giornaliero per persone attive
fonte: "International Society of Sports Nutrition (ISSN) Position Stand: protein and exercise"
url: https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/
data_pubblicazione: "2017 (position stand); range aggiornato con letteratura 2024-2025"
data_verifica: "2026-09-08"
affidabilità: media
note_di_onestà: >
  Estratto da riassunti/citazioni secondarie del position stand, non dal PDF
  integrale (bloccato da pagina anti-bot su PMC e Springer). I numeri sono
  corroborati da più fonti indipendenti che citano lo stesso documento.
```

## Range raccomandati

| Obiettivo | g di proteine per kg di peso corporeo al giorno |
|---|---|
| Mantenimento, attività generica | 1,4 - 2,0 |
| Ipertrofia (costruzione massa muscolare) | 1,6 - 2,4 |
| Deficit calorico (preservare massa magra durante il dimagrimento) | fino a 2,2 |

Il range 1,4-2,0 g/kg è quello del position stand ISSN 2017 originale;
1,6-2,4 g/kg e il valore "fino a 2,2 g/kg in deficit" riflettono letteratura
più recente (2024-2025) che tende verso l'estremo superiore del range
storico, non lo contraddice.

## Distribuzione nella giornata

- Dose per pasto: **20-40 g** di proteine ad alto valore biologico.
- Frequenza: distribuire **ogni 3-4 ore** circa, non concentrare tutto in
  1-2 pasti — questo massimizza la sintesi proteica muscolare nell'arco
  della giornata.

## Come tradurlo in logica applicativa

1. Calcolare il target proteico giornaliero: `peso_kg × fattore_obiettivo`
   (usando la tabella sopra in base all'obiettivo dichiarato dall'utente).
2. Distribuire il target su 3-5 pasti/spuntini rispettando il range
   20-40 g a pasto.
3. **Se l'utente dichiara l'uso di proteine in polvere**: sommarle al
   totale giornaliero, non trattarle come "extra" separato — l'obiettivo è
   il totale proteico giornaliero, non massimizzare l'integratore. Se il
   totale da cibo + integratore supera ampiamente il range utile (es. oltre
   2,4-2,5 g/kg senza motivo clinico), segnalarlo come probabilmente
   superfluo, non dannoso di per sé ma senza beneficio aggiuntivo dimostrato
   a quei livelli.

## Segnali di uso scorretto da evitare nell'agente

- Non spingere automaticamente verso il range alto (2,4 g/kg) per chiunque:
  è indicato per ipertrofia attivamente perseguita, non un default.
- Non ignorare l'apporto da cibo quando l'utente usa proteine in polvere:
  vanno sommate, il target resta uno solo.
