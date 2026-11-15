# Deployment Guide — DevReview AI

Backend → **Render** (FastAPI + Key Value/Redis)
Database → **Neon** (Postgres, free tier — unlike Render's free Postgres it does not expire)
Frontend → **Vercel** (Next.js)

This guide is written so you can go from a clean repo to a live app. Steps that
only you can do (creating accounts, pasting secrets, clicking Deploy) are called
out explicitly.

---

## 0. Before you start — rotate the dev secrets

The credentials in `backend/.env` are development values and must **not** be
reused in production. Treat them as compromised and regenerate:

- **GitHub OAuth**: create a **new** OAuth app for production (below). Do not
  reuse the dev client secret.
- **Gemini API key**: revoke the existing key at
  https://aistudio.google.com/apikey and issue a fresh one.
- **Database (Aiven)**: production uses a separate Neon database, so the Aiven
  URL is not used in production. Rotate its password if it was ever shared.
- **JWT_SECRET_KEY**: Render generates a new random value automatically (see
  `render.yaml`). Never carry the dev value forward — production refuses to
  start with the default or a key shorter than 32 characters. It also derives
  the key that encrypts stored GitHub tokens, so rotating it signs users out.

`.env` is gitignored and was never committed — history is clean.

---

## 1. Database on Neon

Render's free Postgres is deleted 30 days after creation, so the database lives on
[Neon](https://neon.tech) instead (free tier, no expiry).

1. Sign up at https://console.neon.tech → **New Project** (pick the region
   closest to your Render service, e.g. AWS US East / Oregon).
2. **Connect** → copy the connection string. Use the **direct** one (pooling
   toggle off): the `-pooler` host runs PgBouncer, which breaks asyncpg's
   prepared statements.
3. Paste it as-is into Render's `DATABASE_URL` (step 2.4 below). The
   `postgresql://` scheme, `sslmode=require`, and `channel_binding=require` are
   normalized automatically in `app/core/config.py`.

Tables are created by `alembic upgrade head` on the API's next boot.

### pgvector (repo chat)

Repo chat stores code embeddings in a `vector(768)` column, which needs the
[pgvector](https://github.com/pgvector/pgvector) extension. Neon includes it. The
migration `b4d8f2a61c93` runs `CREATE EXTENSION IF NOT EXISTS vector` itself, and
Neon's default project owner role is allowed to do that, so normally there is
nothing to do.

If the boot log shows `permission denied to create extension "vector"` (for example
with a restricted role), open Neon's **SQL Editor** once and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

then redeploy. Check with `SELECT extversion FROM pg_extension WHERE extname = 'vector';`.
The schema uses an HNSW index, which needs pgvector ≥ 0.5 (Neon ships newer).

## 2. Backend on Render

The repo ships a **Render Blueprint** (`render.yaml`) that provisions two
resources: the API web service and a Key Value (Redis) instance, wired together.

1. Push this repo to GitHub (see section 5 if you haven't committed yet).
2. Render Dashboard → **New → Blueprint** → connect the repo → **Apply**.
3. Render creates `devreview-api` and `devreview-redis`.
   `REDIS_URL` and `JWT_SECRET_KEY` are filled in automatically.
4. Open **devreview-api → Environment** and set the values marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Neon connection string from step 1 |
   | `GITHUB_CLIENT_ID` | from your production GitHub OAuth app |
   | `GITHUB_CLIENT_SECRET` | from your production GitHub OAuth app |
   | `GITHUB_CALLBACK_URL` | `https://<your-frontend>.vercel.app/callback` |
   | `GEMINI_API_KEY` | your fresh Gemini key |
   | `ALLOWED_ORIGINS` | `https://<your-frontend>.vercel.app` |

   You'll fill the two Vercel URLs after step 2; redeploy the service once they're set.
5. Migrations run automatically at startup (the blueprint's `startCommand` is
   `alembic upgrade head && uvicorn ...`). Free tier does not support a separate
   pre-deploy step; `alembic upgrade head` is idempotent so running it on each
   boot is safe.
6. Verify: open `https://<your-api>.onrender.com/health` → `{"status":"ok","env":"production"}`.

Notes:
- A plain `postgresql://` URL from Render is auto-rewritten to the async
  `postgresql+asyncpg://` driver in `app/core/config.py`, so no manual edit is needed.
- Free Render web services sleep after inactivity; the first request after idle
  is slow. Upgrade the plan to avoid cold starts.
- Repository analysis runs in-process as a FastAPI background task (it clones
  the repo into a temp dir), so a free instance's 512 MB limits repo size.
- uvicorn runs with `--proxy-headers` so the rate limiter sees real client IPs.

### Render free tier and repo chat indexing

Indexing for repo chat (`POST /repositories/{id}/index`) also runs as an in-process
background task. On the free plan:

- **512 MB RAM.** Indexing embeds and inserts chunks in batches of 100, so only
  ~100 vectors are in memory at a time. `RAG_MAX_CHUNKS_PER_REPO` (default 3000) and
  `RAG_MAX_FILE_CHARS` (default 100000) cap the work per repo. Lower them if the
  service gets OOM-killed on very large repos.
- **The service sleeps when idle** (~15 min). A sleeping service isn't indexing
  anything, and the first request after waking is slow.
- **A restart or redeploy kills a running indexing job.** That's safe:
  - the job replaces a repo's chunks in **one transaction**, so a killed job leaves
    the previous index untouched and chat keeps working on it;
  - a repo stuck in `indexing` for **30 minutes** is treated as dead, and the
    **Re-index** button works again;
  - re-indexing an unchanged repo is skipped (one GitHub API call compares the latest
    commit SHA), so retrying costs nothing.
- **Gemini free tier: 1000 embedded texts per day.** One chunk = one text, and each
  chat question costs one more. A medium repo (~600 chunks) uses most of a day's
  quota. When it runs out, indexing fails fast with "Gemini's daily embedding quota
  is used up" (shown in the UI), and chat questions fail the same way until the quota
  comes back. A paid Gemini key removes this limit; a full index of a medium repo
  costs a few cents.
- `GEMINI_API_KEY` is **required** for repo chat even if OpenAI/Claude are configured.
  Embeddings never fall back to another provider (vectors from different models can't
  be compared). Chat *answers* do use the normal Gemini → OpenAI → Claude fallback.

## 3. Frontend on Vercel

1. Vercel → **Add New → Project** → import the same GitHub repo.
2. **Root Directory** → set to `frontend` (this is a monorepo; Vercel needs the
   subdirectory). Framework auto-detects as Next.js.
3. Add environment variables (Production scope):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://<your-api>.onrender.com` |

4. **Deploy.** Copy the resulting `*.vercel.app` URL.
5. Go back and finish Render step 4 with this URL (`ALLOWED_ORIGINS`,
   `GITHUB_CALLBACK_URL`), then redeploy the API.

Security headers are applied via `frontend/vercel.json`.

## 4. GitHub OAuth app (production)

Create at https://github.com/settings/applications/new:

- **Homepage URL**: `https://<your-frontend>.vercel.app`
- **Authorization callback URL**: `https://<your-frontend>.vercel.app/callback`
  — this must exactly match `GITHUB_CALLBACK_URL` on the backend.

Both the client id and secret live only on the backend (Render); the frontend
gets the authorize URL from `GET /api/v1/auth/github/url`.

## 5. Deploys

Both Render and Vercel redeploy automatically on push to `main` once connected.

---

## Environment variables reference

### Backend (Render)

| Variable | Source | Notes |
|---|---|---|
| `APP_ENV` | `production` | enables HSTS and the JWT secret check |
| `DEBUG` | `false` | never `true` in prod (exposes `/api/docs`) |
| `JWT_SECRET_KEY` | Render generated | JWT signing + GitHub token encryption key |
| `DATABASE_URL` | Neon (manual) | `postgresql://` auto-normalized to asyncpg |
| `REDIS_URL` | Render Key Value | cache |
| `ALLOWED_ORIGINS` | manual | frontend origin(s), comma-separated |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | manual | production OAuth app |
| `GITHUB_CALLBACK_URL` | manual | `https://<frontend>/callback` |
| `GEMINI_API_KEY` | manual | AI provider |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | manual (optional) | runtime fallbacks |
| `AI_PRIMARY_PROVIDER` | `gemini` | |
| `GEMINI_MODEL` / `OPENAI_MODEL` / `CLAUDE_MODEL` | optional | override default model ids |

Repo chat (RAG) — all optional, defaults shown:

| Variable | Default | Notes |
|---|---|---|
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Gemini only; changing it means re-indexing every repo |
| `EMBEDDING_DIM` | `768` | fixed by the `vector(768)` column; other values are rejected at boot |
| `RAG_TOP_K` | `8` | code chunks put in the prompt per question |
| `RAG_MIN_SIMILARITY` | `0.70` | best cosine similarity below this → "low confidence" |
| `RAG_MAX_FILE_CHARS` | `100000` | larger files are skipped |
| `RAG_MAX_CHUNKS_PER_REPO` | `3000` | caps embedding cost and memory per index run |

### Frontend (Vercel)

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_API_URL` | Render backend base URL |

---

## Troubleshooting

- **CORS errors in the browser**: `ALLOWED_ORIGINS` on the backend must match the
  frontend origin exactly (scheme + host, no trailing slash). Redeploy after changes.
- **Login redirects to `/login` in a loop**: the `session` cookie isn't set because
  the callback failed. Check `GITHUB_CALLBACK_URL` (backend) == OAuth app callback
  == `<frontend>/callback`, and start the login from `/login` in the same browser
  tab (the OAuth `state` check rejects logins started elsewhere).
- **Boot fails with "JWT_SECRET_KEY must be set…"**: set a random 32+ char
  `JWT_SECRET_KEY` (Render's generated value qualifies).
- **"GitHub authorization expired. Please sign in again."**: stored GitHub tokens
  are encrypted with a key derived from `JWT_SECRET_KEY`; after rotating it (or on
  first deploy of this version) users just log in again.
- **500 on boot / DB errors**: confirm `alembic upgrade head` ran (it's the first
  half of the start command; check the service logs at boot). A `postgresql://`
  URL is normalized automatically.
- **`connect() got an unexpected keyword argument`** / **prepared statement
  errors**: use Neon's direct (non-`-pooler`) connection string.
- **`asyncio extension requires an async driver`**: means the URL wasn't
  normalized — you're on an old `config.py`; pull latest.
- **First request very slow**: free Render service cold start. Upgrade the plan.
- **Docs page 404 in prod**: intended — `/api/docs` is disabled when `DEBUG=false`.
- **`type "vector" does not exist`** / **`permission denied to create extension`**:
  enable pgvector on Neon (see "pgvector (repo chat)" above), then redeploy.
- **Index status "Failed: Gemini's daily embedding quota is used up"**: free-tier
  limit (1000 texts/day). Retry later or use a paid key; the previous index keeps working.
- **Chat says "This repository isn't indexed yet"**: press **Index repository** on the
  repo's Chat tab and wait for the status to turn "Indexed".
- **Chat answer arrives all at once instead of word by word**: a proxy is buffering
  the `text/event-stream` response. The API already sends `Cache-Control: no-cache`,
  `X-Accel-Buffering: no` and `Content-Encoding: identity`; check for any extra proxy
  or CDN in front of Render.

## Production checklist

- [ ] Dev secrets rotated (GitHub secret, Gemini key)
- [ ] Backend deployed, `/health` returns 200
- [ ] Frontend deployed
- [ ] `ALLOWED_ORIGINS` = frontend URL; API redeployed
- [ ] `GITHUB_CALLBACK_URL` == OAuth app callback == `<frontend>/callback`
- [ ] Login → dashboard works end to end
- [ ] `DEBUG=false`, `APP_ENV=production` on the backend
- [ ] pgvector enabled on Neon (`SELECT extversion FROM pg_extension WHERE extname = 'vector';`)
- [ ] A repo indexes successfully and chat answers with working citation links
