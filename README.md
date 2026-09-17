# 🏋️ Kilo — allenamento e nutrizione

Kilo è un coach personale che genera **schede di allenamento** e **target
nutrizionali** su misura, ti segue nell'esecuzione e misura i progressi. La
mascotte è un kettlebell verde lime e dà il nome all'agente, che in chat si
presenta come Kilo.

> **Principio fondamentale: i numeri non li inventa l'LLM.** Serie,
> ripetizioni, RIR, recuperi, grammi di proteine e dosaggi sono calcolati in
> modo deterministico dai documenti della [knowledge base](backend/app/knowledge_base/README.md),
> che citano fonti ufficiali (ISSN, EFSA, WHO, IOC, Academy of Nutrition and
> Dietetics). L'LLM **spiega e personalizza**. Se non è configurato, l'app
> funziona lo stesso, solo senza testo discorsivo.
>
> Kilo propone e spiega, **non sostituisce un medico o un nutrizionista**.

---

## Cosa fa

- **Account e profilo**: registrazione con email e password. Onboarding con
  età, peso, stile di vita, obiettivo, giorni disponibili e attrezzatura.
  Questionario di **screening** (PAR-Q+): se rispondi «sì» ad almeno una
  domanda, il volume della scheda parte dal minimo e Kilo consiglia di far
  valutare il piano da un medico.
- **Scheda di allenamento**: split automatico o scelto dall'utente, volume
  settimanale per gruppo muscolare, range di ripetizioni mirati (es. 2×6-8,
  3×6-8), RIR e recuperi presi dalla letteratura. Nomi, descrizioni e
  immagini dell'esecuzione sono **in italiano**.
- **Sostituzione esercizi**: alternative con lo stesso muscolo primario e la
  stessa tipologia (multi-articolare o isolamento), più le preferenze
  personali salvate.
- **Autoregolazione**: se riferisci DOMS che durano troppo o nessun
  miglioramento, Kilo propone di **ridurre il volume** invece di aumentarlo.
- **Target nutrizionali**: TDEE con Mifflin-St Jeor, calorie in base
  all'obiettivo, proteine in g/kg (ISSN), poi grassi e carboidrati (EFSA).
- **Diario alimentare** in stile contacalorie: cerchi un alimento (USDA per i
  prodotti grezzi, Open Food Facts via wger per quelli confezionati), lo pesi
  e lo aggiungi al pasto. Con **«Cosa mi manca oggi?»** Kilo propone alimenti e
  grammi per chiudere le proteine senza sforare le calorie. Non aggiunge nulla
  senza la tua conferma.
- **Ricette fit**: ricette da TheMealDB ordinate in base a quanto ti
  avvicinano ai target rimasti. I macro sono calcolati sommando gli
  ingredienti reali, e le ricette con dati insufficienti vengono scartate.
- **Integratori (facoltativi)**: Kilo non li propone mai di sua iniziativa.
  Se dichiari cosa assumi, ne valuta evidenze, dosaggio e rischi di qualità
  del prodotto. Tra quelli trattati ci sono creatina, caffeina, beta-alanina,
  HMB, BCAA, citrullina, glutammina, vitamina D, omega-3, moringa e
  ashwagandha. Nel **diario delle assunzioni** segni ogni giorno cosa hai
  preso (anche dose per dose, per esempio in una fase di carico) e vedi i
  giorni totali, la serie in corso e i giorni saltati nelle ultime 4
  settimane.
- **Note di Kilo**: in cima alle sezioni la mascotte segnala di sua
  iniziativa ciò che conta in quel momento: scorte di creatina piene dopo 28
  giorni (senza pause obbligate), fase di carico finita, 4-6 settimane con la
  stessa scheda (momento di fare il punto), carichi fermi, calo di peso
  troppo rapido, proteine sotto target nella settimana. Ogni nota è una
  regola scritta sulle fonti, con i documenti citati: non consuma la quota
  dell'LLM e non inventa. «Approfondisci» apre la chat sulla domanda, «Ho
  capito» la chiude su tutti i dispositivi, e un pallino sul pulsante della
  chat segnala le note nuove.
- **La tua settimana**: in Oggi, il riepilogo della settimana conclusa
  (allenamenti fatti su quelli previsti, peso medio rispetto alla settimana
  prima, proteine sul target, costanza con gli integratori) e una sola cosa
  su cui concentrarsi. «Commentala con Kilo» chiede il commento alla chat.
- **Promemoria**: dalle 12 un banner discreto ricorda cosa non hai ancora
  segnato oggi: gli integratori dichiarati, che si segnano direttamente da
  lì, e i pasti, ma solo se usi il diario. Si chiude con un clic fino al
  giorno dopo, e dal Profilo si spegne del tutto.
- **Progressi**: peso corporeo confrontato su **medie mobili di 7 giorni**,
  forza sul **massimale stimato**, aderenza e rilevamento dei plateau.
- **Chat con Kilo**: risponde usando i tuoi dati reali e i documenti
  pertinenti della knowledge base. **Non può modificare nulla**: se chiedi un
  cambiamento, ti porta nella sezione giusta e decidi tu.

---

## Stack

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.11+, **FastAPI**, SQLAlchemy 2, **Alembic** |
| Database | **PostgreSQL su [Neon](https://neon.tech)** (piano free), driver `psycopg` |
| Autenticazione | Password con **Argon2** (`pwdlib`), sessioni **JWT** |
| LLM | **Google Gemini** (piano gratuito), solo spiegazioni e traduzioni |
| Esercizi | [Everkinetic](https://github.com/everkinetic/data) (disegni, CC BY-SA 4.0), [RepDB](https://github.com/RepDB/exercise-dataset) (illustrazioni, free tier con attribuzione), [free-exercise-db](https://github.com/yuhonas/free-exercise-db) (foto, pubblico dominio), più esercizi scritti a mano |
| Alimenti | **USDA FoodData Central** (chiave gratuita), **wger / Open Food Facts** |
| Ricette | **TheMealDB** (senza chiave) |
| Frontend | **Next.js 15**, React 18, TypeScript, Tailwind, Framer Motion, Recharts |

Tutte le integrazioni sono **gratuite**.

---

## Struttura del progetto

```
kilo/
├── backend/
│   ├── app/
│   │   ├── main.py              # entry point FastAPI + /health
│   │   ├── config.py            # lettura .env (pydantic-settings)
│   │   ├── database.py          # engine/sessione SQLAlchemy (Neon)
│   │   ├── models.py            # schema DB
│   │   ├── schemas.py           # modelli Pydantic (I/O API)
│   │   ├── knowledge_base/      # ⭐ documenti con fonti: la verità numerica
│   │   ├── routers/             # auth · profile · workout · nutrition ·
│   │   │                        # supplements · progress
│   │   └── services/
│   │       ├── workout_generator.py   # ⭐ schede deterministiche
│   │       ├── autoregulation.py      # riduzione volume da feedback
│   │       ├── exercise_library.py    # catalogo esercizi con immagini
│   │       ├── exercise_swap.py       # alternative agli esercizi
│   │       ├── nutrition_targets.py   # ⭐ TDEE, calorie, macro
│   │       ├── food_diary.py · gap_filler.py
│   │       ├── meal_suggestions.py · recipe_analyzer.py
│   │       ├── supplements.py
│   │       ├── progress_report.py
│   │       ├── chat_agent.py          # la chat con Kilo
│   │       ├── knowledge_base.py      # retrieval dei documenti per tag
│   │       ├── llm_client.py · translation.py
│   │       └── wger_client.py · usda_client.py · themealdb_client.py
│   ├── alembic/                 # migrazioni schema
│   ├── tests/                   # 266 test
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/                 # layout, pagina, icon.svg, apple-icon.png
│   │   ├── components/
│   │   │   ├── Shell.tsx        # barra laterale / navigazione mobile
│   │   │   ├── Mascot.tsx · ChatBubble.tsx · ExerciseDetail.tsx
│   │   │   └── sections/        # Auth · Onboarding · Today · Workout · Diary ·
│   │   │                        # Recipes · Progress · Supplements · ProfileSection
│   │   └── lib/                 # api.ts (client) · coach.ts (azioni del coach)
│   ├── next.config.mjs          # proxy /api/* → backend
│   └── package.json
└── README.md
```

---

## Prerequisiti

- **Python 3.11+** e **Node 18.18+**
- Un account gratuito su **Neon**. Consigliate, ma facoltative, le chiavi
  gratuite di **Google Gemini** e **USDA**.

## 1) Database gratuito su Neon

1. Registrati su **https://neon.tech** (free tier, nessuna carta richiesta) e
   crea un **Project**.
2. In **Connection Details** copia la connection string *pooled*.
3. Incollala in `DATABASE_URL`. Va bene anche il formato `postgresql://…`
   fornito da Neon: il driver `psycopg` viene aggiunto automaticamente. Deve
   finire con `?sslmode=require`.

## 2) Chiavi gratuite (facoltative)

| Chiave | Dove | A cosa serve | Senza |
|---|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | Spiegazioni delle schede, chat con Kilo, traduzioni in italiano | Schede e target funzionano, ma senza testi e senza chat |
| `USDA_API_KEY` | https://fdc.nal.usda.gov/api-key-signup | Alimenti grezzi precisi (pollo, uova, legumi…) | Il diario usa solo wger / Open Food Facts |

wger e TheMealDB non richiedono alcuna registrazione.

---

## 3) Backend

```bash
cd backend

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# apri .env e compila almeno DATABASE_URL e SECRET_KEY. Per generare SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(48))"

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- Documentazione API interattiva: **http://localhost:8000/docs**
- Health check: **http://localhost:8000/health**, che mostra quali
  integrazioni sono configurate

> Se sposti o rinomini la cartella del progetto, il `.venv` smette di
> funzionare (`bad interpreter`): i suoi script contengono il percorso
> assoluto. Il modo più semplice per sistemarlo è ricrearlo:
> `rm -rf .venv` e poi ripetere i primi tre comandi.

### Migrazioni Alembic

- Applicare le migrazioni: `alembic upgrade head`
- Tornare indietro di una: `alembic downgrade -1`
- Nuova migrazione dopo aver cambiato `models.py`:
  `alembic revision --autogenerate -m "descrizione"`

L'URL del DB non è scritto in `alembic.ini`: viene letto da `.env`.

## 4) Frontend

```bash
cd frontend
npm install
npm run dev
```

Apri **http://localhost:3000**.

Il browser chiama sempre `/api/*` e Next inoltra le richieste al backend
(vedi `next.config.mjs`), quindi non servono CORS né URL assoluti. Se il
backend non è su `127.0.0.1:8000`, avvia il frontend con
`BACKEND_URL=http://host:porta npm run dev`.

---

## Primo avvio

1. **Crea un account** e completa l'onboarding: nome, dati fisici, obiettivo,
   giorni e attrezzatura.
2. **Importa il catalogo esercizi**: in **Profilo** avvia la sincronizzazione
   (`POST /catalog/sync-exercises`). Importa i tre cataloghi e gli esercizi
   scritti a mano, toglie i doppioni e traduce nomi e descrizioni in italiano
   in background. Serve Gemini per le traduzioni: finché non sono pronte, gli
   esercizi mostrano il nome originale.
3. In **Scheda** scegli il tipo di split e clicca **Genera scheda**.
4. In **Diario** registra i pasti. In **Ricette** chiedi idee in base a ciò
   che ti manca.
5. Registra sessioni e pesate: **Progressi** si riempie col tempo.
6. Scrivi a Kilo dal fumetto della chat, per esempio: *"i DOMS mi durano
   troppo"*.

Le sezioni sono **Oggi · Scheda · Diario · Ricette · Progressi · Integratori
· Profilo**.

---

## Deploy online

Backend su **Render** (configurato da [`render.yaml`](render.yaml)), frontend
su **Vercel**, database su Neon, tutto con piani gratuiti. La guida passo
passo è in **[DEPLOY.md](DEPLOY.md)**.

---

## Test

```bash
cd backend
source .venv/bin/activate
pytest -q
```

I test coprono generazione delle schede, autoregolazione, target
nutrizionali e formule, diario, report di progressione, integratori,
knowledge base, client esterni (con risposte simulate) e sicurezza: ogni
rotta senza accesso deve rispondere 401, e i dati di un utente non devono
essere raggiungibili da un altro.

Controllo delle dipendenze (in un ambiente separato, per non aggiungere lo
strumento al progetto):

```bash
python3 -m venv /tmp/audit && /tmp/audit/bin/pip install pip-audit
/tmp/audit/bin/pip-audit -r backend/requirements.txt
cd frontend && npm audit
```

---

## Principali endpoint API

| Metodo & path | Descrizione |
|---|---|
| `POST /auth/register` · `POST /auth/login` · `GET /auth/me` | Account e sessione |
| `POST /profile` · `GET/PATCH /profile/{id}` | Profilo utente |
| `POST/GET /profile/{id}/screening` | Screening PAR-Q+ |
| `POST/GET /profile/{id}/weight` | Pesate |
| `POST /workout/plans/generate` · `GET /workout/plans/active` | Generazione e scheda attiva |
| `POST /workout/plan-exercises/{id}/swap` | Sostituisci un esercizio |
| `POST/GET /workout/sessions` | Sessioni svolte e serie registrate |
| `POST /workout/feedback` | Feedback (DOMS, progressi) → raccomandazione sul volume |
| `GET /workout/exercises` · `GET/POST/DELETE /workout/preferences` | Catalogo e preferenze |
| `POST /workout/chat` | Chat con Kilo |
| `GET /nutrition/targets` · `POST /nutrition/targets/save` | Target nutrizionali |
| `GET /nutrition/foods/search` | Ricerca alimenti (USDA + Open Food Facts) |
| `GET /nutrition/diary` · `POST/PATCH/DELETE /nutrition/diary/items` | Diario alimentare |
| `GET /nutrition/diary/fill-gap` | «Cosa mi manca oggi?» |
| `GET /nutrition/recipes/suggest` | Ricette in base ai target rimasti |
| `GET/POST/DELETE /supplements` · `GET /supplements/catalog` | Integratori dichiarati e schede informative |
| `GET /supplements/intake` · `PUT /supplements/{id}/intake` | Diario delle assunzioni |
| `GET /profile/{id}/reminders` | Cosa non è ancora segnato oggi |
| `GET /profile/{id}/notes` · `POST /profile/{id}/notes/dismiss` | Note di Kilo |
| `GET /profile/{id}/weekly-summary` | Riepilogo della settimana conclusa |
| `GET /progress/report` | Report di progressione |
| `GET /catalog/status` · `POST /catalog/sync-exercises` | Stato e importazione del catalogo esercizi |

---

## Knowledge base e affidabilità

La cartella [`backend/app/knowledge_base/`](backend/app/knowledge_base/README.md)
contiene un documento per argomento: volume, RIR e cedimento, DOMS, scelta
degli esercizi, proteine, macro e micronutrienti EFSA, timing dei pasti,
idratazione, RED-S, dieta vegetariana e vegana, singoli integratori e
screening. Ogni file dichiara **fonte, URL, data di pubblicazione, data di
verifica e livello di affidabilità**.

- **Retrieval per tag, non vettoriale**: ogni richiesta carica solo i
  documenti pertinenti. Si può sempre dire da quali fonti è nato un
  consiglio.
- **Aggiornare la scienza significa modificare un file**, non riscrivere
  codice.
- `evidence_conduct.md` viene allegato **sempre**: impedisce all'agente di
  validare acriticamente un integratore o inventare un dosaggio non coperto.
- **Manutenzione**: rivedere ogni documento ogni 12-18 mesi, o quando esce
  una nuova revisione della fonte.

---

## Guardrail e sicurezza

- **Nessuna azione automatica**: la chat non modifica schede, target o
  diario. Ogni cambiamento è un'azione esplicita dell'utente.
- **Screening di sicurezza**: con almeno un «sì» al PAR-Q+ il volume viene
  fissato al minimo del range e la scheda riporta l'avviso di consultare un
  medico prima di aumentarlo.
- **Integratori mai proposti di iniziativa**: la sezione è facoltativa, e
  nessuna scheda o piano cambia perché non assumi qualcosa.
- **Password**: solo hash Argon2, mai salvate né scritte nei log. Token JWT
  con scadenza, firmati con `SECRET_KEY`.
- **Ogni dato è accessibile solo al suo proprietario**: tutte le rotte, tranne
  accesso, registrazione e `/health`, richiedono il token, e ogni profilo o
  risorsa (integratore, alimento del diario, scheda) viene verificata contro
  l'account che chiama; se non è sua risponde 404, senza rivelare che esiste.
  Un test scorre tutte le rotte dell'app e fallisce se una resta scoperta.
- **Limiti contro gli abusi**: tentativi di accesso falliti per email e
  richieste per IP, registrazioni per IP, e quote giornaliere per account
  sulle funzioni che usano Gemini (chat, traduzioni, generazione schede).
  «Aggiorna catalogo» è riservato alle email in `ADMIN_EMAILS`.
- **Input della chat trattato come dato**: domanda, storico e schermata
  stanno fra tag nel prompt, con l'istruzione di non eseguirli; lo storico ha
  ruoli ammessi e lunghezze massime.
- **Documentazione dell'API spenta in produzione** (`DOCS_ENABLED`).
- **Intestazioni di sicurezza**: il frontend invia una Content-Security-Policy
  (script, connessioni e immagini solo dai domini previsti), blocca
  l'inserimento in iframe e forza HTTPS; le risposte dell'API non vengono
  memorizzate da browser o proxy (`Cache-Control: no-store`).
- **Dipendenze controllate**: `npm audit` e `pip-audit` senza vulnerabilità
  note al momento dell'ultimo aggiornamento.
- **Chiamate a Gemini robuste e misurate**: nuovi tentativi sugli errori
  temporanei, regole della chat nel prompt di sistema separate dal testo
  dell'utente, token consumati registrati nei log per ogni chiamata. Al
  modello non arrivano nome né email dell'utente.
- **Trasparenza**: nella chat è indicato che le risposte sono scritte da un
  modello di intelligenza artificiale e possono contenere errori.
- **Nessun segreto nel repo**: chiavi e `DATABASE_URL` stanno solo in `.env`
  (git-ignorato). Nel repo c'è solo `.env.example`.
- **Errori esterni gestiti**: se Gemini, USDA, wger o TheMealDB non
  rispondono, l'app degrada in modo controllato senza crashare. Traduzioni e
  risposte LLM sono salvate in cache nel database.

---

## Catalogo esercizi e crediti

Il catalogo unisce tre fonti aperte e alcuni esercizi scritti a mano (circa
1000 esercizi dopo aver tolto i doppioni):

- **[Everkinetic](https://github.com/everkinetic/data)** — disegni al tratto,
  licenza CC BY-SA 4.0.
- **[RepDB](https://github.com/RepDB/exercise-dataset)** — illustrazioni flat.
  **Exercise data by RepDB ([repdb.co](https://repdb.co))**. Il free tier
  permette l'uso dentro l'app con attribuzione e vieta di ridistribuire il
  dataset: nel repository non ci sono né i dati né le immagini RepDB, che
  vengono importati nel database dell'app.
- **[free-exercise-db](https://github.com/yuhonas/free-exercise-db)** — foto,
  pubblico dominio.
- **Kilo** (`backend/app/services/manual_exercises.py`) — varianti che nessuna
  fonte contiene (Bayesian curl, alzate laterali al cavo dietro la schiena,
  croci ai cavi dal basso, pendulum squat), senza immagini.

Lo stesso esercizio compare spesso in più fonti con nomi diversi: i doppioni,
verificati a mano, sono in `backend/app/data/exercise_duplicates.json`. Se ne
tiene uno solo, preferendo disegni, poi illustrazioni, poi foto. La
sincronizzazione da **Profilo** importa tutte le fonti e traduce in background
gli esercizi nuovi, che nel frattempo compaiono in inglese.

---

## Origine del progetto

Kilo nasce riutilizzando la base del precedente *"Cacciatore di Abbonamenti e
Spese Fantasma"*: backend FastAPI, Neon, Alembic e il client Gemini con
output JSON vincolato. Il dominio è stato poi completamente sostituito con
allenamento e nutrizione.
