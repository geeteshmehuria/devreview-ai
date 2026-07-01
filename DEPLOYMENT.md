# Deployment Guide — DevReview AI

Backend → **Render** (FastAPI + Postgres + Key Value/Redis)
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
- **Database (Aiven)**: the app provisions a fresh Render Postgres, so the Aiven
  URL is not used in production. Rotate its password if it was ever shared.
- **SECRET_KEY / JWT_SECRET_KEY**: Render generates new random values
  automatically (see `render.yaml`). Never carry the dev values forward.

`.env` is gitignored and was never committed — history is clean.

---

## 1. Backend on Render

The repo ships a **Render Blueprint** (`render.yaml`) that provisions three
resources: the API web service, a Postgres database, and a Key Value (Redis)
instance, all wired together.

1. Push this repo to GitHub (see section 4 if you haven't committed yet).
2. Render Dashboard → **New → Blueprint** → connect the repo → **Apply**.
3. Render creates `devreview-api`, `devreview-db`, `devreview-redis`.
   `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `JWT_SECRET_KEY` are filled in
   automatically.
4. Open **devreview-api → Environment** and set the values marked `sync: false`:

   | Variable | Value |
   |---|---|
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
- A Celery worker is **not** part of this blueprint. If background review jobs
  are enabled, add a Render **Background Worker** using the same repo with start
  command `celery -A app.jobs worker` and the same env group.

## 2. Frontend on Vercel

1. Vercel → **Add New → Project** → import the same GitHub repo.
2. **Root Directory** → set to `frontend` (this is a monorepo; Vercel needs the
   subdirectory). Framework auto-detects as Next.js.
3. Add environment variables (Production scope):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://<your-api>.onrender.com` |
   | `NEXT_PUBLIC_APP_URL` | `https://<your-frontend>.vercel.app` |
   | `NEXT_PUBLIC_GITHUB_CLIENT_ID` | production GitHub OAuth client id |

4. **Deploy.** Copy the resulting `*.vercel.app` URL.
5. Go back and finish Render step 4 with this URL (`ALLOWED_ORIGINS`,
   `GITHUB_CALLBACK_URL`), then redeploy the API.

Security headers are applied via `frontend/vercel.json`.

## 3. GitHub OAuth app (production)

Create at https://github.com/settings/applications/new:

- **Homepage URL**: `https://<your-frontend>.vercel.app`
- **Authorization callback URL**: `https://<your-frontend>.vercel.app/callback`
  — this must exactly match `GITHUB_CALLBACK_URL` on the backend.

The client **secret** lives only on the backend (Render). The client **id** is
public and also goes in the frontend as `NEXT_PUBLIC_GITHUB_CLIENT_ID`.

## 4. Commit and push

Environment note: the current session's sandbox has a read-only-ish mount that
blocks git writes, so the commit was left for you to run locally:

```bash
git add -A
git commit -m "chore: production hardening + Render/Vercel deploy configs"
git push origin main
```

Both Render and Vercel redeploy automatically on push to `main` once connected.

---

## Environment variables reference

### Backend (Render)

| Variable | Source | Notes |
|---|---|---|
| `APP_ENV` | `production` | disables `/api/docs`, enables HSTS |
| `DEBUG` | `false` | never `true` in prod |
| `SECRET_KEY` | Render generated | app signing key |
| `JWT_SECRET_KEY` | Render generated | JWT signing key |
| `DATABASE_URL` | Render Postgres | `postgresql://` auto-normalized to asyncpg |
| `REDIS_URL` | Render Key Value | cache |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Render Key Value | for optional worker |
| `ALLOWED_ORIGINS` | manual | frontend origin(s), comma-separated |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | manual | production OAuth app |
| `GITHUB_CALLBACK_URL` | manual | `https://<frontend>/callback` |
| `GEMINI_API_KEY` | manual | AI provider |
| `AI_PRIMARY_PROVIDER` | `gemini` | |

### Frontend (Vercel)

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_API_URL` | Render backend base URL |
| `NEXT_PUBLIC_APP_URL` | this site's URL |
| `NEXT_PUBLIC_GITHUB_CLIENT_ID` | public client id |

---

## Troubleshooting

- **CORS errors in the browser**: `ALLOWED_ORIGINS` on the backend must match the
  frontend origin exactly (scheme + host, no trailing slash). Redeploy after changes.
- **Login redirects to `/login` in a loop**: the callback cookie isn't set. Check
  `GITHUB_CALLBACK_URL` (backend) == OAuth app callback == `<frontend>/callback`.
- **500 on boot / DB errors**: confirm `alembic upgrade head` ran (it's the first
  half of the start command; check the service logs at boot). A `postgresql://`
  URL is normalized automatically.
- **`asyncio extension requires an async driver`**: means the URL wasn't
  normalized — you're on an old `config.py`; pull latest.
- **First request very slow**: free Render service cold start. Upgrade the plan.
- **Docs page 404 in prod**: intended — `/api/docs` is disabled when `DEBUG=false`.

## Production checklist

- [ ] Dev secrets rotated (GitHub secret, Gemini key)
- [ ] Backend deployed, `/health` returns 200
- [ ] Frontend deployed
- [ ] `ALLOWED_ORIGINS` = frontend URL; API redeployed
- [ ] `GITHUB_CALLBACK_URL` == OAuth app callback == `<frontend>/callback`
- [ ] Login → dashboard works end to end
- [ ] `DEBUG=false`, `APP_ENV=production` on the backend
