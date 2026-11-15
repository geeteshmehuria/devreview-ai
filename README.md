<div align="center">

# DevReview AI

**AI-powered code reviews in seconds.**

Analyse repositories, review pull requests, detect security vulnerabilities, and track technical debt — powered by Google Gemini with OpenAI and Claude fallbacks.

[**Live Demo**](https://devreview-ai-mu.vercel.app) · [Features](#features) · [Screenshots](#screenshots) · [Architecture](#architecture) · [Setup](#setup) · [Deployment](#deployment)

[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)

<br/>

<img src="docs/screenshots/dashboard.png" alt="DevReview AI dashboard" width="900"/>

</div>

---

## Overview

**DevReview AI** turns code review into a 30-second operation. Sign in with GitHub, then paste a snippet, upload a file, import a repository, or drop in a pull-request URL — and get a structured AI review: per-category scores, severity-ranked security findings with CWE tags, performance issues, code smells, and technical-debt estimates, each with a concrete fix.

**The problem it solves:** manual review is slow, inconsistent, and easy to skip under deadline pressure. DevReview AI gives every developer an instant, repeatable second pair of eyes — before code reaches a human reviewer.

Under the hood it is a production-grade full-stack application demonstrating:

- **Frontend Engineering** — Next.js 15 App Router, React 19, TypeScript, Tailwind CSS v4
- **Backend Engineering** — FastAPI with layered architecture (routers → services → models)
- **AI Integration** — Provider abstraction layer (Gemini primary, OpenAI + Claude runtime fallbacks)
- **Database Design** — PostgreSQL with 10-table relational schema, UUID PKs, JSONB columns
- **System Design** — Redis caching, background analysis tasks, token refresh rotation
- **Security** — GitHub OAuth with signed state, encrypted GitHub tokens, JWT refresh rotation, rate limiting
- **Performance** — Query caching, lazy loading, dynamic imports, connection pooling
- **Testing** — Vitest + RTL (frontend), Pytest (backend), Playwright E2E
- **DevOps** — Docker Compose, multi-stage Dockerfiles, health checks

---

## Features

| Feature | Description |
|---|---|
| **AI Code Review** | Paste or upload code — get security, performance, readability, maintainability, architecture, and best-practices scores |
| **Pull Request Review** | Enter a GitHub PR URL — AI analyses the diff and produces risk score + findings |
| **Repository Analysis** | Import a GitHub repo — clone, scan, and generate full architecture + health report |
| **Repository Health** | 0–100 score with radar chart and historical trend graph |
| **Technical Debt** | Severity-ranked debt items with estimated remediation hours |
| **Review History** | Every review stored — paginated timeline, previous findings, never lost |
| **GitHub OAuth** | Secure sign-in with JWT access/refresh tokens and server-side route protection |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER                                 │
│  Next.js 15 (App Router)                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │  Auth    │ │  Review  │ │  Repos   │ │  History / Health │  │
│  │  Pages   │ │  Editor  │ │  Manager │ │  Dashboards       │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  Zustand (auth state) │ TanStack Query (server state)           │
│  Framer Motion │ Recharts │ Monaco Editor                       │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS / JSON
┌────────────────────────▼────────────────────────────────────────┐
│                       FASTAPI                                   │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────┐  │
│  │  Auth   │ │ Reviews  │ │   Repos    │ │   Pull Requests  │  │
│  │ Router  │ │  Router  │ │   Router   │ │      Router      │  │
│  └─────────┘ └──────────┘ └────────────┘ └──────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Service Layer                              │   │
│  │  AuthService │ ReviewService │ RepositoryService        │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │                                       │
│  ┌──────────────────────▼──────────────────────────────────┐   │
│  │              AI Provider Layer                          │   │
│  │  AIProvider (abstract)                                  │   │
│  │  ├── GeminiProvider (primary)                           │   │
│  │  ├── OpenAIProvider (fallback)                          │   │
│  │  └── ClaudeProvider (fallback)                          │   │
│  │  PromptBuilder → Provider → ResponseFormatter           │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────┬──────────────────────────────┬───────────────────────┘
           │                              │
    ┌──────▼──────┐               ┌───────▼──────┐
    │ PostgreSQL  │               │    Redis     │
    │  (primary)  │               │   (cache +   │
    │             │               │   sessions)  │
    └─────────────┘               └──────────────┘
```

---

## Database Schema

```sql
users                   -- GitHub OAuth users (encrypted GitHub token, hashed refresh token)
repositories            -- Imported GitHub repos with metadata + status
repository_health       -- Timestamped health snapshots (enables trends)
pull_requests           -- GitHub PR metadata + risk scores
reviews                 -- Root record for each AI analysis run
review_results          -- Per-category scores (security: 72, perf: 88...)
security_findings       -- OWASP/CWE vulnerabilities with severity
performance_findings    -- Performance issues with impact estimates
code_smells             -- Refactoring opportunities
technical_debt          -- Debt items with estimated remediation hours
```

**Design decisions:**
- UUID primary keys (prevent enumeration attacks)
- JSONB columns for flexible AI response evolution without migrations
- `repository_health` stores snapshots, not updates — enables trend graphs
- `reviews` as aggregate root — efficient pagination without joining all child tables
- Indexes on `user_id`, `review_type`, `severity`, `created_at` for common query patterns

---

## AI Provider Architecture

```python
AIProvider (abstract)
  ├── GeminiProvider    → GEMINI_MODEL  (default gemini-2.5-flash, primary)
  ├── OpenAIProvider    → OPENAI_MODEL  (default gpt-4o-mini, fallback)
  └── ClaudeProvider    → CLAUDE_MODEL  (default claude-haiku-4-5, fallback)

run_review(request, preferred) → tries each configured provider in order and falls
back on a missing key, an API error, or unreadable output
```

**Key design choices:**
- Business logic never imports concrete providers — only `AIProvider`
- `PromptBuilder` is separate from providers — prompts can be A/B tested independently
- `ResponseFormatter` normalises JSON output — handles markdown fences, partial JSON, etc.
- `tenacity` retry with exponential backoff on all provider calls
- Provider instances are cached after first successful init

---

## Tech Stack

### Frontend
| Layer | Technology |
|---|---|
| Framework | Next.js 15 (App Router) + React 19 |
| Language | TypeScript 5.7 |
| Styling | Tailwind CSS v4 (+ typography plugin) |
| State | Zustand (auth) + TanStack Query (server) |
| Charts | Recharts |
| Animations | Framer Motion |
| Editor | Monaco Editor |
| Notifications | Sonner |
| Markdown | react-markdown + remark-gfm |

### Backend
| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 |
| Language | Python 3.12 |
| Database | PostgreSQL 16 (asyncpg driver) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache | Redis 7 |
| Auth | GitHub OAuth + JWT (PyJWT), Fernet-encrypted GitHub tokens |
| AI | google-genai / openai / anthropic |
| Logging | structlog |
| Rate Limiting | slowapi |

### Infrastructure
| Component | Technology |
|---|---|
| Containerisation | Docker + Docker Compose |
| Background Jobs | FastAPI BackgroundTasks (repository analysis) |
| CI | GitHub Actions (configured) |

---

## Project Structure

```
devreview-ai/
├── frontend/                   # Next.js 15 application
│   ├── app/
│   │   ├── (auth)/             # Login + OAuth callback
│   │   ├── (dashboard)/        # Protected dashboard routes
│   │   │   ├── dashboard/      # Overview
│   │   │   ├── review/         # Code review (paste / upload)
│   │   │   ├── repositories/   # Repository management
│   │   │   ├── pull-requests/  # PR review
│   │   │   ├── history/        # Review history + detail
│   │   │   ├── health/         # Repository health dashboard
│   │   │   ├── debt/           # Technical debt tracker
│   │   │   └── settings/       # User settings
│   │   └── layout.tsx
│   ├── components/
│   │   ├── layout/             # Sidebar, Header
│   │   ├── providers/          # Query, Auth providers
│   │   ├── review/             # ReviewResultPanel with tabs
│   │   └── shared/             # ScoreRing, Skeleton, etc.
│   ├── lib/
│   │   ├── api/                # Typed API client (axios)
│   │   ├── stores/             # Zustand stores
│   │   └── utils/              # Formatters, colour helpers
│   ├── types/                  # TypeScript interfaces
│   ├── middleware.ts            # Edge auth guard (no dashboard flash)
│   └── tests/                  # Vitest unit + Playwright E2E
│
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py             # FastAPI app + middleware
│   │   ├── routers/            # auth, reviews, repositories, pull_requests
│   │   ├── services/           # auth_service, review_service, repository_service
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── ai/                 # Provider abstraction layer
│   │   │   ├── base.py         # Abstract AIProvider + dataclasses
│   │   │   ├── factory.py      # run_review() with runtime fallback chain
│   │   │   ├── prompts.py      # PromptBuilder (provider-agnostic)
│   │   │   ├── response_formatter.py
│   │   │   └── providers/      # GeminiProvider, OpenAIProvider, ClaudeProvider
│   │   ├── core/               # config, database, redis, security, exceptions
│   │   ├── middleware/         # JWT auth dependency
│   │   └── tests/              # Pytest tests
│   ├── alembic/                # DB migrations
│   ├── Dockerfile
│   ├── requirements.txt        # runtime dependencies
│   └── requirements-dev.txt    # + test dependencies
│
├── docker-compose.yml
└── README.md
```

---

## Setup

### Prerequisites

- Docker + Docker Compose
- GitHub OAuth App ([create one here](https://github.com/settings/applications/new))
- Google Gemini API key ([get one here](https://aistudio.google.com/apikey))

### 1. Clone the repository

```bash
git clone https://github.com/geeteshmehuria/devreview-ai.git
cd devreview-ai
```

### 2. Create a GitHub OAuth App

1. Go to **GitHub → Settings → Developer Settings → OAuth Apps → New OAuth App**
2. Set **Homepage URL**: `http://localhost:3000`
3. Set **Authorization callback URL**: `http://localhost:3000/callback`
4. Copy **Client ID** and **Client Secret**

### 3. Configure environment variables

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env — set:
# GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
# GEMINI_API_KEY
# JWT_SECRET_KEY (any 32+ char random string)

# Frontend (only NEXT_PUBLIC_API_URL, defaults to http://localhost:8000)
cp frontend/.env.example frontend/.env.local
```

### 4. Start with Docker Compose

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, the FastAPI backend (which runs `alembic upgrade head`
on start) and the Next.js frontend. All ports are bound to `127.0.0.1`.

### 5. Open the app

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/api/docs (only when `DEBUG=true`)

---

## Deployment

Production deploys to **Render** (backend + Postgres + Redis) and **Vercel**
(frontend). The repo ships a Render Blueprint (`render.yaml`) and Vercel config
(`frontend/vercel.json`). See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for the full
step-by-step guide, environment variable reference, and troubleshooting.

Production URLs:

- **Frontend**: [https://devreview-ai-mu.vercel.app](https://devreview-ai-mu.vercel.app)
- **Backend API**: `https://devreview-api.onrender.com` (Render free tier — the instance sleeps when idle, so the first request can take ~50s)

---

## Running Tests

### Frontend (Vitest)
```bash
cd frontend
npm install
npm test
```

### Backend (Pytest)
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

### E2E (Playwright)
```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

---

## API Documentation

With `DEBUG=true` the FastAPI app serves interactive docs at `/api/docs` (Swagger UI) and `/api/redoc`.
Endpoints that call the AI or clone repositories are rate limited to 10 requests/minute per client.

### Key endpoints

```
GET    /api/v1/auth/github/url         GitHub authorize URL + signed OAuth state
POST   /api/v1/auth/github/callback    Exchange GitHub code (+ state) for JWT tokens
POST   /api/v1/auth/refresh            Rotate refresh token
GET    /api/v1/auth/me                 Get current user
DELETE /api/v1/auth/me                 Delete account and all its data

POST   /api/v1/reviews/code            Review pasted code snippet
POST   /api/v1/reviews/file            Review uploaded file (max 100 KB)
GET    /api/v1/reviews                 List review history (paginated)
GET    /api/v1/reviews/debt            Technical-debt items across all reviews
GET    /api/v1/reviews/{id}            Get review detail + findings

POST   /api/v1/repositories            Import a GitHub repository (analysis runs in background)
GET    /api/v1/repositories            List user's repositories
POST   /api/v1/repositories/{id}/analyze  Trigger re-analysis
DELETE /api/v1/repositories/{id}       Remove a repository

POST   /api/v1/pull-requests/review    Review a GitHub PR by URL
```

---

## Design Decisions & Tradeoffs

**Why UUID primary keys?**
Sequential integer IDs expose record counts and enable enumeration attacks. UUIDs eliminate both issues with negligible performance cost at portfolio scale.

**Why JSONB for AI responses?**
AI output schema evolves frequently. JSONB lets us iterate on the response format without constant migrations, while still indexing specific keys when needed.

**What code is stored?**
Pasted and uploaded code (max 100,000 characters) is kept with the review so history is complete. PR diffs and cloned repositories are not stored — clones are deleted right after sampling. Deleting the account removes everything.

**Why refresh token rotation?**
Stolen refresh tokens are immediately invalidated on next use. The previous refresh token hash is overwritten, forcing re-authentication.

**Why Gemini as the primary provider?**
Gemini has the most generous free tier, making portfolio demos cost-free. The provider abstraction means swapping to GPT-4o or Claude is a one-line config change.

**Why background tasks for repository analysis?**
Cloning and analysing a repository takes 30–120 seconds. FastAPI's `BackgroundTasks` returns the HTTP response immediately while analysis runs, keeping the API responsive.

---

## Screenshots

> UI captures from the current build (populated with sample data).

| Landing | Login |
|---|---|
| ![Landing page](docs/screenshots/landing.png) | ![Login](docs/screenshots/login.png) |

| Dashboard | Repositories |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Repositories](docs/screenshots/repositories.png) |

| AI Code Review — Overview | Security Findings |
|---|---|
| ![Code review overview](docs/screenshots/review.png) | ![Security findings](docs/screenshots/security.png) |

| Pull Request Review | Repository Health |
|---|---|
| ![PR review](docs/screenshots/pr.png) | ![Repo health](docs/screenshots/health.png) |

| Review History |
|---|
| ![Review history](docs/screenshots/history.png) |

---

## Contributing

Contributions are welcome. Fork the repo, create a feature branch, and open a pull request:

```bash
git checkout -b feat/your-feature
# make your changes, add tests
git commit -m "feat: describe your change"
```

Please run the test suites (`npm test`, `pytest`) before submitting, and keep PRs focused on a single change.

---

## Author

**Geetesh Mehuria** — [GitHub](https://github.com/geeteshmehuria) · [Email](mailto:geeteshmaihuria@gmail.com)

---

## License

MIT
