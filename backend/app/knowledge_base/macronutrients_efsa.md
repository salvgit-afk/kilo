```yaml
argomento: range di riferimento macronutrienti (popolazione generale)
fonte: "EFSA (European Food Safety Authority) - Summary of Dietary Reference Values, versione 4 (September 2017), pareri scientifici su carboidrati/fibra (2010), grassi (2010), proteine (2012)"
url: https://www.efsa.europa.eu/sites/default/files/assets/DRV_Summary_tables_jan_17.pdf
data_pubblicazione: "2010-2012 (pareri originali); riassunto versione 4, settembre 2017"
data_verifica: "2026-09-10"
affidabilità: alta
note_di_onestà: >
  **Verificato sul PDF ufficiale originale il 2026-09-10** (Tabelle 2 e 3
  del "Summary of Dietary Reference Values" EFSA) — non più solo da fonti
  secondarie. Tutti i numeri sotto sono letti direttamente dalle tabelle
  EFSA. Questi sono valori per la **popolazione generale**, non per atleti —
  per le proteine in un contesto di allenamento vedi protein_intake.md
  (ISSN), che resta la fonte da usare per utenti attivi.
```

## Range di riferimento (adulti)

| Macronutriente | Range EFSA |
|---|---|
| Carboidrati | 45-60% dell'energia totale giornaliera |
| Grassi totali | 20-35% dell'energia totale giornaliera |
| Grassi saturi | il più basso possibile nell'ambito di una dieta nutrizionalmente adeguata (indicativamente <10% dell'energia) |
| Fibra alimentare | 25 g/giorno (adulti) |
| Proteine (PRI, popolazione generale, 18-59 anni) | 0,83 g/kg/giorno (AR: 0,66 g/kg/giorno) |
| Zuccheri liberi | sotto il 10% dell'energia totale (OMS/EFSA), idealmente sotto il 5% (raccomandazione condizionale OMS) |
| Acido linoleico (omega-6) | 4% dell'energia (Adequate Intake) |
| Acido alfa-linolenico / ALA (omega-3) | 0,5% dell'energia (AI) |
| EPA+DHA (omega-3 a catena lunga) | 250 mg/giorno (AI, adulti) |
| Acqua totale (bevande + alimenti) | 2,5 L/giorno uomini, 2,0 L/giorno donne (AI, adulti ≥18) |

Per "zuccheri liberi" si intendono zuccheri aggiunti da produttore/cuoco/
consumatore, più quelli naturalmente presenti in miele, sciroppi, succhi e
concentrati di frutta — non gli zuccheri intrinseci alla frutta intera o al
latte.

L'acqua totale EFSA (2,5 L/2,0 L) è il fabbisogno **giornaliero di base**
della popolazione generale, comprensivo dell'acqua negli alimenti — è un
valore diverso e complementare rispetto alle indicazioni **specifiche per
l'allenamento** in `hydration.md` (ACSM), che riguardano il liquido
aggiuntivo da bere attorno alla sessione di esercizio.

## Nota importante sul valore proteico EFSA

Il valore EFSA di 0,83 g/kg/giorno è calcolato per la **popolazione generale
sedentaria**, non per chi si allena — è un valore di adeguatezza minima, non
un target ottimale per l'ipertrofia. La fonte EFSA stessa nota che assunzioni
fino al **doppio della PRI (~1,66 g/kg)** sono regolarmente consumate da
adulti sani e fisicamente attivi in Europa e sono considerate sicure — un
dato che si allinea bene con (e rinforza la sicurezza di) i range più alti
raccomandati da ISSN per chi si allena (`protein_intake.md`).

**Uso pratico nell'app**: per le proteine, usare sempre `protein_intake.md`
(ISSN) come target operativo per utenti che si allenano — questo file EFSA
serve da riferimento per carboidrati, grassi e fibra, e come conferma di
sicurezza per i range proteici più alti.

## Come tradurlo in logica applicativa

1. Target calorico totale (da formula TDEE) → distribuire in carboidrati
   (45-60%) e grassi (20-35%) secondo questi range.
2. Le proteine si calcolano **separatamente** da `protein_intake.md`
   (obiettivo-specifiche), non dal range EFSA generico.
3. Verificare che la fibra giornaliera pianificata nei pasti raggiunga
   almeno 25 g/giorno.
4. Nelle ricette/pasti suggeriti, segnalare se gli zuccheri liberi superano
   il 10% dell'energia giornaliera — non vietare, ma rendere visibile,
   specie nei piani orientati alla definizione.
