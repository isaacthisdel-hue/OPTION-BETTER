# Deploy — GitHub + Railway + Vercel

You'll push the repo to GitHub, deploy the backend (API + worker + Postgres) on
Railway, and the frontend on Vercel. **You set all secrets yourself in each
dashboard — no keys ever go into the repo.**

---

## 1. Push to GitHub

```bash
cd servision-reversal
git init
git add .
git commit -m "Reversal research tool: backend + frontend"
# create an empty repo on github.com first, then:
git remote add origin https://github.com/<you>/<repo>.git
git branch -M main
git push -u origin main
```

`.gitignore` already excludes `.env` files, `node_modules`, and `.next`. Confirm
no `.env` got committed:

```bash
git ls-files | grep -i env    # should show only *.env.example
```

---

## 2. Railway — Postgres, API, worker

### 2a. Create the project + database
1. https://railway.app → **New Project** → **Deploy from GitHub repo** → pick your repo.
2. In the project, **New** → **Database** → **PostgreSQL**. Railway provisions it
   and exposes a `DATABASE_URL` variable.

### 2b. API service
1. Railway will create a service from your repo. Open it → **Settings** →
   set **Root Directory** to `servision-reversal/backend`.
2. **Variables** tab → add:
   - `DATABASE_URL` → click "Add Reference" → select the Postgres `DATABASE_URL`.
   - `FINNHUB_API_KEY` → your key
   - `FMP_API_KEY` → your key
   - `PROVIDER` → `finnhub`
   - `CORS_ORIGINS` → your Vercel URL (add after step 3; e.g. `https://your-app.vercel.app`)
   - `WATCHLIST` → optional, e.g. `AAPL,MSFT,NVDA`
3. The included `start.sh` runs `alembic upgrade head` then boots uvicorn.
   Healthcheck path `/health` is already configured in `railway.json`.
4. Deploy. When it's live, open `https://<your-api>.up.railway.app/health`.

### 2c. Worker service (optional but recommended)
1. In the same project: **New** → **Empty Service** → connect the same repo.
2. **Settings** → Root Directory `servision-reversal/backend`; **Start Command**: `python -m app.worker`.
3. **Variables**: add the same variables as the API (reference the same
   `DATABASE_URL`, same API keys).
4. Deploy. This process scans on an interval during market hours and resolves
   open paper trades. (No healthcheck needed — it's not an HTTP service.)

> Cost note: the worker runs continuously. If you want to keep Railway usage
> minimal at first, skip the worker and just press **RUN SCAN** manually in the
> UI, or run the worker locally.

---

## 3. Vercel — frontend

1. https://vercel.com → **Add New** → **Project** → import your GitHub repo.
2. **Root Directory**: `servision-reversal/frontend`.
3. **Environment Variables**: add
   - `NEXT_PUBLIC_API_BASE` → your Railway API URL (e.g. `https://<your-api>.up.railway.app`), no trailing slash.
4. Deploy. Vercel auto-detects Next.js.
5. Copy your Vercel URL and go back to Railway → API service → `CORS_ORIGINS` →
   set it to that URL (comma-separate if you have several). Redeploy the API.

---

## 4. Verify

- `GET https://<api>/health` → `{"status":"ok"}`
- Open the Vercel URL → **Scanner** → **RUN SCAN** (set a `WATCHLIST` if the
  market is closed) → candidates render.
- **Backtest** → **RUN BACKTEST** → metrics render (synthetic sample).

---

## 5. Wiring real backtest data (later)

The backtester is real; only its input is synthetic right now. To backtest on
real history, write a loader that builds `HistoricalEvent` objects
(`backend/app/backtesting/engine.py`) from your data source:

- For each past earnings event: fetch that day's 1-min bars, the prior close,
  the earnings surprise, and the fundamentals **as they were on that date**.
- Set `fundamentals_available_at` to the epoch the earnings became public — the
  engine refuses to use them before that time (this is the no-look-ahead guard).
- Replace the `synthetic_events()` call in the `/api/backtest` route with your
  loader.

Free intraday history is thin. When you're ready, a paid provider
(Massive/Polygon, FMP Premium) gives clean historical bars; add a provider
subclass and set `PROVIDER` accordingly — no scoring code changes.

---

## Security reminders

- Never commit `.env`. Keys live only in Railway/Vercel dashboards.
- If a key ever lands in git history, rotate it immediately at the provider.
- This tool never connects to a brokerage and never places orders. Keep it that
  way — it's a research instrument.
