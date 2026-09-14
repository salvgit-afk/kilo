# 🚀 Deploy di Kilo

- **Backend** (FastAPI) su **Render**, configurato da [`render.yaml`](render.yaml)
- **Frontend** (Next.js) su **Vercel**
- **Database** su **Neon**, che esiste già

```
Browser ──► Vercel (Next.js) ──/api/*──► Render (FastAPI) ──► Neon (PostgreSQL)
```

Il browser parla solo con Vercel. Next inoltra `/api/*` al backend
(`frontend/next.config.mjs`), quindi **non serve configurare il CORS**.

L'ordine conta: prima il backend, perché il frontend ha bisogno del suo
indirizzo al momento del build.

---

## Perché il backend non va su Vercel

- **Richieste lunghe**: generare una scheda con la spiegazione di Gemini
  richiede decine di secondi, e le funzioni serverless hanno un tempo
  massimo per richiesta.
- **Lavoro in background**: le traduzioni del catalogo esercizi partono dopo
  la risposta (`BackgroundTasks`), e in serverless il processo può essere
  fermato prima di finire.
- **Nessuna modifica al codice**: su Render gira lo stesso `uvicorn` che usi in
  locale.

---

## Prima di iniziare

1. Il repository `salvgit-afk/kilo` deve essere aggiornato su GitHub, con
   `render.yaml` incluso.
2. Tieni a portata di mano:
   - `DATABASE_URL`, la stessa del tuo `backend/.env`
   - `GEMINI_API_KEY` (facoltativa)
   - `USDA_API_KEY` (facoltativa)

> **Database condiviso con lo sviluppo.** Se usi la stessa `DATABASE_URL` del
> tuo PC, produzione e sviluppo leggono e scrivono gli **stessi dati**. Per
> un progetto personale va bene. Per tenerli separati, su Neon crea un
> **branch** (es. `production`) e usa la sua connection string.

---

## 1) Backend su Render

1. Vai su **https://dashboard.render.com** e accedi con GitHub.
2. Clicca **New → Blueprint** e collega il repository `salvgit-afk/kilo`. Se
   non compare, da **Configure GitHub App** dai a Render l'accesso al repo.
3. Render legge `render.yaml` e propone il servizio **`kilo-backend`**.
   Compila le variabili richieste:

   | Variabile | Valore |
   |---|---|
   | `DATABASE_URL` | la connection string Neon *pooled*, con `?sslmode=require` |
   | `GEMINI_API_KEY` | la tua chiave, oppure lascia vuoto |
   | `USDA_API_KEY` | la tua chiave, oppure lascia vuoto |

   `SECRET_KEY` viene generata da Render, `PYTHON_VERSION` e `GEMINI_MODEL`
   sono già impostate.

4. Clicca **Apply**. Il primo deploy impiega qualche minuto. All'avvio esegue
   `alembic upgrade head`: se lo schema su Neon è già aggiornato, non fa
   nulla.
5. Copia l'indirizzo del servizio, del tipo
   `https://kilo-backend-xxxx.onrender.com`.
6. **Verifica**: apri `https://kilo-backend-xxxx.onrender.com/health`. Deve
   rispondere `"status": "ok"` e mostrare `gemini_configured` e
   `usda_configured` come ti aspetti.

## 2) Frontend su Vercel

1. Vai su **https://vercel.com/new** e accedi con GitHub.
2. Importa il repository `salvgit-afk/kilo`.
3. Alla voce **Root Directory** clicca **Edit** e seleziona **`frontend`**.
   Il framework Next.js viene riconosciuto da solo.
4. In **Environment Variables** aggiungi:

   | Variabile | Valore |
   |---|---|
   | `BACKEND_URL` | l'indirizzo Render del passo 1, **senza `/` finale** |

5. Clicca **Deploy**.
6. **Verifica**: apri l'indirizzo Vercel (es. `https://kilo-xxxx.vercel.app`),
   crea un account e completa l'onboarding.

> ⚠️ `BACKEND_URL` viene letta **durante il build**. Se la aggiungi o la cambi
> dopo, devi rifare il deploy: **Deployments → ⋯ → Redeploy**. Senza questa
> variabile il proxy punta a `127.0.0.1:8000` e ogni chiamata fallisce.

## 3) Primo avvio in produzione

1. Accedi e vai in **Profilo**.
2. Avvia l'**importazione del catalogo esercizi**. Le traduzioni in italiano
   continuano in background per qualche minuto.
3. Genera la prima scheda.

Se il database Neon è lo stesso dello sviluppo, il catalogo c'è già e questo
passo non serve.

---

## Aggiornamenti

Ogni `git push` su `main` rideploya **entrambi** i servizi da soli: Render
per `backend/`, Vercel per `frontend/`.

Se modifichi `models.py`, crea la migrazione in locale
(`alembic revision --autogenerate -m "…"`) e mettila in commit. Render la
applica al prossimo avvio.

---

## Limiti del piano gratuito e rimedi

| Limite | Effetto | Rimedio |
|---|---|---|
| Render spegne il servizio dopo **15 minuti** senza richieste | La prima richiesta dopo una pausa impiega **circa un minuto** e può andare in errore | Apri prima `/health` e attendi; oppure un ping ogni 10-14 min su `/health` con [cron-job.org](https://cron-job.org); oppure il piano a pagamento |
| **750 ore/mese** gratuite per workspace | Bastano per un servizio acceso tutto il mese | Non tenere altri servizi free sempre accesi nello stesso workspace |
| Nessun disco persistente | I file scritti dal backend si perdono a ogni riavvio | Kilo salva tutto su Neon, quindi non è un problema |
| Neon free va in sospensione quando inattivo | Leggera latenza sulla prima query | Già gestito: `pool_pre_ping=True` in `app/database.py` |

Un ping continuo tiene il servizio sempre acceso e consuma circa 730 ore al
mese, quindi rientra nelle 750.

---

## Problemi comuni

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| Il frontend si apre ma accesso e dati non funzionano | `BACKEND_URL` mancante o aggiunta dopo il build | Impostala su Vercel e fai **Redeploy** |
| Errore 500 su registrazione/accesso | `SECRET_KEY` assente o più corta di 32 caratteri | Controlla le variabili del servizio su Render |
| Il deploy Render fallisce all'avvio | `DATABASE_URL` errata o migrazione fallita | Guarda i **Logs** del servizio: l'errore di Alembic o psycopg è lì |
| La prima richiesta dopo una pausa va in errore | Il servizio Render si stava riaccendendo | Riprova dopo un minuto, oppure attiva il ping |
| `/health` mostra `gemini_configured: false` | Chiave non inserita | Aggiungi `GEMINI_API_KEY` su Render; il servizio si riavvia da solo |
| Esercizi con nomi in inglese | Traduzioni ancora in corso o Gemini non configurato | Attendi qualche minuto o configura la chiave |
