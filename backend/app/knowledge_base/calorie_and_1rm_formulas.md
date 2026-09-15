```yaml
argomento: formule di calcolo - fabbisogno calorico (TDEE) e stima del massimale (1RM)
fonte: "Mifflin MD, St Jeor ST, et al. (1990) - equazione BMR; formula di Epley per stima 1RM (uso consolidato in letteratura sulla forza)"
url: "formule matematiche di dominio pubblico, ampiamente validate e citate"
data_pubblicazione: "1990 (Mifflin-St Jeor); Epley non ha una data di pubblicazione formale unica, è uso consolidato"
data_verifica: "2026-09-08"
affidabilità: alta
note_di_onestà: >
  A differenza degli altri file, questo non riporta i risultati di uno
  studio ma formule matematiche standard, tra le più validate in assoluto
  nel loro campo (Mifflin-St Jeor è considerata più accurata della più
  vecchia formula di Harris-Benedict nella maggior parte delle popolazioni).
```

## BMR — Metabolismo Basale (equazione di Mifflin-St Jeor)

```
Uomini:  BMR = 10 × peso(kg) + 6,25 × altezza(cm) − 5 × età(anni) + 5
Donne:   BMR = 10 × peso(kg) + 6,25 × altezza(cm) − 5 × età(anni) − 161
```

## TDEE — Fabbisogno calorico totale giornaliero

```
TDEE = BMR × fattore_attività
```

| Livello di attività | Fattore |
|---|---|
| Sedentario (poco/nessun esercizio) | 1,2 |
| Leggermente attivo (1-3 giorni/settimana) | 1,375 |
| Moderatamente attivo (3-5 giorni/settimana) | 1,55 |
| Molto attivo (6-7 giorni/settimana) | 1,725 |
| Estremamente attivo (lavoro fisico + allenamento intenso) | 1,9 |

## Target calorico per obiettivo

| Obiettivo | Target calorico |
|---|---|
| Mantenimento | TDEE |
| Definizione (perdita grasso) | TDEE − 15/20% (deficit moderato, non aggressivo) |
| Ipertrofia/aumento massa | TDEE + 10/15% (surplus moderato): +15% principiante, +12% intermedio, +10% avanzato, perché l'ISSN indica surplus più ampi per chi inizia e più contenuti per chi è già allenato (`diets_body_composition.md`) |

Un deficit/surplus moderato è preferibile a uno aggressivo: preserva massa
magra in deficit e limita l'accumulo di grasso in surplus. Deficit molto
aggressivi (>25%), specie se combinati con alto volume di allenamento,
sono un fattore di rischio reale per REDs (vedi `energy_availability_reds.md`,
fonte IOC) — non solo una scelta più lenta/veloce di definizione. Vanno
segnalati come da valutare con un professionista, specie se combinati con
un "sì" nello screening
(`screening_and_red_flags.md`).

## Stima del massimale (1RM) — formula di Epley

```
1RM stimato = peso_sollevato × (1 + ripetizioni / 30)
```

Usata per stimare il massimale senza doverlo testare direttamente (test che
comporta rischio di infortunio, specie per principianti). Attendibile
soprattutto per ripetizioni **basse-moderate** (fino a ~10-12); con
ripetizioni molto alte la stima perde precisione.

## Come tradurlo in logica applicativa

1. TDEE è la base per tutti i calcoli di `macronutrients_efsa.md` e
   `protein_intake.md` (che poi affina la quota proteica rispetto al TDEE).
2. Il 1RM stimato (non richiesto come test reale) alimenta i report di
   progressione: confronto tra 1RM stimato a inizio e fine percorso per lo
   stesso esercizio, usando sempre la stessa formula per coerenza.
3. Non proporre mai un test di 1RM reale (massimale vero) a un principiante
   senza supervisione — usare sempre la stima da ripetizioni sub-massimali.
