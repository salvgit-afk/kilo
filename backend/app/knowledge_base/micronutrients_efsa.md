```yaml
argomento: valori di riferimento per micronutrienti critici (ferro, zinco, calcio, iodio, B12, vitamina D)
fonte: "EFSA - Summary of Dietary Reference Values, versione 4 (September 2017), Tabelle 5, 7, 9, 11"
url: https://www.efsa.europa.eu/sites/default/files/assets/DRV_Summary_tables_jan_17.pdf
data_pubblicazione: "settembre 2017 (riassunto di pareri 2013-2015 sui singoli micronutrienti)"
data_verifica: "2026-09-10"
affidabilità: alta
note_di_onestà: >
  Letto direttamente dal PDF ufficiale EFSA. Questo file esiste soprattutto
  per dare numeri concreti a `vegetarian_vegan_nutrition.md`, che segnalava
  questi nutrienti come "da monitorare" senza valori di riferimento precisi.
```

## Valori di riferimento (adulti, PRI salvo dove indicato)

| Nutriente | Uomini (≥18) | Donne (≥18) | Note |
|---|---|---|---|
| Calcio | 950 mg/d (≥25) / 1000 mg/d (18-24) | uguale agli uomini | |
| Ferro | 11 mg/d | 16 mg/d (premenopausa) / 11 mg/d (postmenopausa) | Il fabbisogno femminile in età fertile è molto più alto — rilevante per dieta vegana con solo ferro non-eme |
| Zinco | 7,5-16,3 mg/d | 6,2-12,7 mg/d | **Dipende dal livello di fitati nella dieta** (LPI: basso/medio/alto) — più fitati (tipico di diete ricche di legumi/cereali integrali) = fabbisogno più alto nel range |
| Iodio | 150 μg/d | 150 μg/d | |
| Vitamina B12 (cobalamina) | 4,0 μg/d | 4,0 μg/d | Assente dai vegetali: per i vegani va da integrazione o alimenti fortificati |
| Vitamina D | 15 μg/d | 15 μg/d | Valore valido assumendo **sintesi cutanea minima** — con buona esposizione solare il fabbisogno dietetico può essere inferiore |

## Perché lo zinco ha un range e non un numero fisso

L'EFSA lega il fabbisogno di zinco al livello di fitati nella dieta (i
fitati, presenti in legumi/cereali integrali/frutta a guscio, riducono
l'assorbimento dello zinco). Questo è rilevante in modo specifico per diete
vegetariane/vegane, tipicamente più ricche di fitati: il fabbisogno reale
tende verso l'estremo alto del range, non quello basso.

## Come tradurlo in logica applicativa

1. Per un piano alimentare vegano, usare il **ferro femminile in
   premenopausa (16 mg/d)** come riferimento prudente quando applicabile,
   dato che il ferro non-eme si assorbe meno — coerente con
   `vegetarian_vegan_nutrition.md` che raccomanda di abbinare vitamina C.
2. Per lo zinco in diete ricche di legumi/cereali integrali, puntare
   all'estremo alto del range indicato.
3. La B12 non ha "cibi vegetali ricchi" reali da suggerire nelle ricette:
   l'agente deve indicare integrazione o alimenti fortificati come via
   primaria per i vegani, non cercare fonti vegetali naturali che non
   esistono in forma biodisponibile affidabile.
4. Il valore di iodio (150 μg/d) è facile da sottostimare in diete che
   escludono sale iodato e pesce — segnalarlo esplicitamente nei piani
   vegani/vegetariani.
