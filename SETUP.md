# Quick Setup Guide

## Push to GitHub (one-time)

```bash
# Replace YOUR_PAT with your GitHub Personal Access Token
git remote set-url origin https://YOUR_PAT@github.com/geeteshmehuria/devreview_ai.git
git push -u origin main
```

**Create a PAT:** https://github.com/settings/tokens/new → check `repo` scope

---

## Local Development Setup

### 1. Copy environment files

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### 2. Fill in these required values in `backend/.env`

```env
GITHUB_CLIENT_ID=        # From GitHub OAuth App
GITHUB_CLIENT_SECRET=    # From GitHub OAuth App
GEMINI_API_KEY=          # From https://aistudio.google.com/apikey
SECRET_KEY=              # Any random 32+ character string
JWT_SECRET_KEY=          # Any random 32+ character string
```

### 3. Fill in `frontend/.env.local`

```env
NEXT_PUBLIC_GITHUB_CLIENT_ID=  # Same as GITHUB_CLIENT_ID above
```

### 4. Create GitHub OAuth App

1. Go to: https://github.com/settings/applications/new
2. Homepage URL: `http://localhost:3000`
3. Callback URL: `http://localhost:3000/auth/callback`
4. Copy Client ID + Secret into `backend/.env`

### 5. Start everything

```bash
docker compose up --build
```

### 6. Run migrations (first time only)

```bash
docker compose exec backend alembic upgrade head
```

### 7. Open

- App: http://localhost:3000
- API Docs: http://localhost:8000/api/docs

---

## Running Tests

```bash
# Frontend unit tests
cd frontend && npm install && npm test

# Backend tests  
cd backend && pip install -r requirements.txt && pytest

# E2E tests (requires app running)
cd frontend && npx playwright install chromium && npm run test:e2e
```
