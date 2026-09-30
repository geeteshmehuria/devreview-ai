# DevReview AI — Code Review Report

**Scope:** every tracked source, config, test, migration, Docker/CI and doc file in the repo (~95 files; `package-lock.json` and screenshots excluded). No code was changed.
**Date:** 2026-09-30 · **Branch:** `main` @ `3452c19`

## Summary

| Severity | Count | Meaning |
|---|---|---|
| 🔴 **Critical** | 4 | Security holes that leak data or secrets, or core features that are broken in the normal path |
| 🟠 **High** | 14 | Security weaknesses, crashes, or data bugs that users will hit |
| 🟡 **Medium** | 26 | Correctness, robustness, and UX problems, and misleading behavior |
| 🔵 **Low** | 28 | Code quality, polish, and minor inconsistencies |
| ♻️ **Redundant** | — | Dead code, unused dependencies, and empty or placeholder files (separate section) |

**Top priorities:** C1–C4, then H1–H4 (security), then H5–H8 (broken core flows).

> Verification note: runtime checks were blocked by the local shell policy, so these findings come from static reading. Items marked *(likely)* should be confirmed by running them. Every other item follows directly from the code as written.

---

## 🔴 Critical

### C1. Repository analysis follows symlinks, so any cloned repo can exfiltrate server files and secrets
- **File:** `backend/app/services/repository_service.py:232-260` (`_extract_repo_content`)
- **Problem:** The code clones a user-supplied repo, then calls `path.exists()` / `path.read_text()` on `README.md`, `Dockerfile`, `.env.example`, and every `*.py`/`*.js`/… file. Both calls **follow symlinks**. A repo that contains `README.md -> /proc/self/environ` or `app.py -> /app/.env` makes the server read its own environment, including `JWT_SECRET_KEY`, the AI keys, `GITHUB_CLIENT_SECRET`, and `DATABASE_URL`. That content goes to the LLM, and the AI summary is returned to the attacker.
- **Impact:** Full secret disclosure, followed by forged JWTs for any user and takeover of the AI and GitHub accounts.
- **Fix:** Skip symlinks (`path.is_symlink()`), resolve each path and check `resolved.is_relative_to(root)`, and clone with `-c core.symlinks=false`.

### C2. The PR review cache is global and is checked before GitHub authorization, which leaks private PR reviews across users
- **File:** `backend/app/routers/pull_requests.py:46-50`
- **Problem:** The cache key is `owner/repo/number` with no user ID. The cache lookup happens **before** the GitHub call that proves the caller can see the repo. If user A reviews a PR in a private repo, user B gets A's AI summary, scores, and title by submitting the same URL, even without access to the repo.
- **Fix:** Verify access with the caller's token first, or include `user_id` in the cache key. Ideally do both.

### C3. Code and file reviews crash whenever the AI returns any performance finding
- **File:** `backend/app/services/review_service.py:123-133`
- **Problem:** `PerformanceFinding(..., code_snippet=f.code_snippet, ...)` is called, but the `PerformanceFinding` model (`models/review.py`) and the migration have **no `code_snippet` column**. The SQLAlchemy declarative constructor raises `TypeError: 'code_snippet' is an invalid keyword argument`. The prompt asks for performance findings, so most real reviews hit this and return 500.
- **Fix:** Remove the kwarg, or add the column and a migration.

### C4. PR review fails for any repo the user hasn't imported, after the AI call has already been paid for
- **Files:** `backend/app/routers/pull_requests.py:95-111`, `backend/app/models/pull_request.py` (`repository_id nullable=False`), migration `62dbbb99701e:100`
- **Problem:** `repository_id=linked_repo.id if linked_repo else None` is written to a NOT NULL column, so the insert raises `IntegrityError` and the request returns 500. The UI tells users to paste *any* PR URL, so this is the common path.
- **Fix:** Make `pull_requests.repository_id` nullable (model and migration), or auto-import the repo first. Persist before calling the AI, or fail fast before spending tokens.

---

## 🟠 High

### H1. Hard-coded default secrets with no production guard
- **File:** `backend/app/core/config.py:24-25, 81`
- **Problem:** `JWT_SECRET_KEY="change-me-in-production-jwt-secret"` and `DEBUG=True` are the defaults. Any deployment that forgets to set the key (for example Docker Compose with a copied `.env.example`) accepts JWTs forged by anyone who has read this public repo. Render generates the key, but nothing enforces it.
- **Fix:** Add a validator that refuses to start when `APP_ENV=production` and either secret is a default or shorter than 32 bytes. Default `DEBUG=False`. (`SECRET_KEY` is unused; see R-section.)

### H2. No rate limiting at all, even though the README claims it
- **File:** `backend/app/main.py:39, 84`
- **Problem:** A `slowapi.Limiter` is created and registered, but no route uses `@limiter.limit(...)` and `SlowAPIMiddleware` is not added, so nothing is limited. Every `/reviews/*`, `/pull-requests/review`, and `/repositories` call costs AI tokens or runs a `git clone`. On Render the limiter would also key on the proxy IP (`get_remote_address`), not the client.
- **Fix:** Add per-user limits on AI and clone endpoints, and use a forwarded-for-aware key function.

### H3. GitHub OAuth tokens are stored in plaintext and use the broadest scope
- **Files:** `backend/app/models/user.py:36` (comment: "encrypted at rest ideally"), `backend/app/routers/auth.py:36`
- **Problem:** The `repo` scope grants full **read/write** access to all of the user's public and private repositories. The token sits unencrypted in `users.github_access_token`, so a DB leak or backup leak equals write access to every user's code.
- **Fix:** Encrypt the column (Fernet/KMS; `cryptography` is already a dependency). Request the minimum scope, or use a GitHub App with read-only contents and pull-request permissions.

### H4. The OAuth `state` (CSRF) check can be bypassed
- **Files:** `frontend/app/(auth)/callback/page.tsx:46`, `backend/app/routers/auth.py:44-51`
- **Problem:** The frontend only checks state `if (expectedState && ...)`. On a victim who never started a login, `sessionStorage` is empty, so the check is skipped. The backend generates `state` but never validates it (`GitHubOAuthRequest.state` is unused). This is a classic login CSRF: an attacker can sign the victim into the attacker's account.
- **Fix:** Reject the callback when there's no stored state. Better: have the backend bind state to a short-lived signed cookie and verify it server-side.

### H5. "Failed" status is never saved, so repos stay stuck in pending and failed reviews disappear
- **Files:** `backend/app/services/repository_service.py:183-186` with `backend/app/routers/repositories.py:136-146`; `backend/app/services/review_service.py:175-179` with `core/database.py:52-57`
- **Problem:** The code sets `status = FAILED` and then re-raises. The caller (the background wrapper or `get_db`) then **rolls back**, which discards the status and the error message. Repos stay `pending` forever and the UI spinner never ends. Failed reviews vanish from history, even though the History page says "nothing is ever lost".
- **Fix:** Commit the failure status in its own transaction before re-raising, or don't re-raise.

### H6. `last_analyzed_at` is set to a random UUID, which crashes the Repositories page
- **Files:** `backend/app/services/repository_service.py:171` (`repo.last_analyzed_at = str(uuid.uuid4())  # placeholder`), `frontend/app/(dashboard)/repositories/page.tsx:177`, `frontend/lib/utils/index.ts:38-63`
- **Problem:** After the first successful analysis, `formatRelativeTime("<uuid>")` falls through to `formatDate`, and `Intl.DateTimeFormat.format(Invalid Date)` **throws `RangeError`**. That takes down the whole Repositories page.
- **Fix:** Store `datetime.now(UTC)` in a `DateTime(timezone=True)` column (with a migration). Also make `formatDate` guard against `isNaN(date)`.

### H7. *(likely)* Review endpoints lazy-load relationships in async code, causing a 500 after a successful review
- **File:** `backend/app/routers/reviews.py:47-48, 84-85`
- **Problem:** `await db.refresh(review)` reloads only the columns. `_review_to_out` then reads `review.results`, `review.security_findings`, and the other relationships, which are unloaded lazy relationships on an `AsyncSession`. This normally raises `MissingGreenlet`, so the user pays for the AI call and gets a 500. It's not covered by any test.
- **Fix:** Return `await get_review(db, review.id, user_id)`, which already uses `selectinload`, or use `lazy="selectin"` or `AsyncAttrs`.

### H8. Repository and PR prompts never include the JSON schema they ask for
- **File:** `backend/app/ai/prompts.py:150-187`
- **Problem:** Both prompts say "Respond with the standard review JSON schema" but never include it. Only the code-review prompt has it. The model has to guess the keys, so `format_response` silently falls back to defaults (score 50, empty findings) or to the "Failed to parse" response. Repo health scores are therefore mostly noise.
- **Fix:** Share one schema block across all three builders, and use JSON mode or structured output where the provider supports it.

### H9. Blocking synchronous I/O inside async handlers freezes the whole server
- **Files:** `backend/app/services/repository_service.py:56-57` and `218-263`; `backend/app/routers/pull_requests.py:55-62`
- **Problem:** PyGithub (`get_repo`, `get_pull`, `list(get_files())`) makes blocking HTTP calls, and `_extract_repo_content` does a blocking `rglob` and file reads, all on the event loop. One slow GitHub call or large repo stalls every other request in the (single-worker) process.
- **Fix:** Wrap them in `await asyncio.to_thread(...)`, or use `httpx.AsyncClient` against the GitHub REST API.

### H10. The frontend's 30-second timeout is shorter than the AI calls it makes
- **File:** `frontend/lib/api/client.ts:13`
- **Problem:** LLM reviews with up to 3 tenacity retries (2–10 s backoff) plus large inputs routinely take longer than 30 s. The browser shows "timeout of 30000ms exceeded" while the server keeps going and still bills tokens.
- **Fix:** Use a per-request timeout for review endpoints (for example 120 s), or better, move reviews to an async job with polling.

### H11. The auth cookie expires after 15 minutes and is never refreshed, so users get bounced to login
- **Files:** `frontend/app/(auth)/callback/page.tsx:63`, `frontend/lib/api/client.ts:74-80`, `frontend/lib/stores/auth-store.ts:66-74`
- **Problem:** The middleware gates pages on the `access_token` cookie, which has `max-age=expires_in` (900 s). Token refresh updates `localStorage` but never updates the cookie, so after 15 minutes any full navigation or reload redirects a logged-in user to `/login`. Also, `logout()` clears `localStorage` but **not the cookie**, and it doesn't redirect, so the user stays on the dashboard.
- **Fix:** Update the cookie on refresh and clear it on logout, then redirect. Better: let the backend set an HttpOnly session or refresh cookie.

### H12. The Health page shows fabricated scores to real users
- **File:** `frontend/app/(dashboard)/health/page.tsx:80-82, 109, 125-131`
- **Problem:** The Security, Performance, and Maintainability bars are `Math.random()` values, and the "Health Trend" chart is `generateMockTrend()`. They change on every render. For a security tool, showing invented security scores as if they were real is actively misleading. The real values already exist in `repository_health` (the `GET /repositories/{id}` snapshots).
- **Fix:** Use `health_snapshots`, or show "not available".

### H13. The backend Docker image bakes in `.env`, virtualenvs, and caches
- **File:** `backend/Dockerfile:17` (`COPY . .`). There is no `backend/.dockerignore`.
- **Problem:** The local `backend/.env` (real secrets), `.venv/`, `.testvenv/`, `.coverage`, and `__pycache__/` are copied into the image layer. Anyone who pulls the image gets the secrets.
- **Fix:** Add a `.dockerignore` excluding `.env*`, `.venv`, `.testvenv`, `__pycache__`, `.pytest_cache`, and `.coverage`.

### H14. The primary AI model and SDK are deprecated or unstable, and a runtime failure never falls back
- **Files:** `backend/app/ai/providers/gemini.py:6, 20`, `backend/app/ai/providers/claude_provider.py:17`, `backend/app/ai/factory.py:36-59`
- **Problem:** The default provider uses `gemini-2.0-flash-exp`. Experimental Gemini models are routinely removed. It also uses the `google-generativeai` SDK, which has been superseded by `google-genai`. The Claude fallback pins `claude-3-5-haiku-20241022`, a model that has been retired. The factory only falls back when a key is *missing*, not on API errors, although its docstring claims otherwise. So if the Gemini model 404s, every review fails.
- **Fix:** Use stable model IDs from config, migrate to `google-genai`, and fall back inside `review()` on provider errors.

---

## 🟡 Medium

| # | Issue | Location | Details / Fix |
|---|---|---|---|
| M1 | Invalid UUID in path → **500** instead of 404/422 | `routers/repositories.py:76,99,124`, `services/review_service.py:195` | `uuid.UUID(repo_id)` raises `ValueError`. Type the path params as `uuid.UUID` so FastAPI validates them. |
| M2 | Background analysis races the request's commit, and gets a closed Redis client | `routers/repositories.py:36-41, 107-111` | The repo is flushed but only committed in the `get_db` teardown, so the background task's new session may not see it yet. The Redis client comes from a request-scoped dependency that `aclose()`s it. The `db` argument is passed but unused. Commit explicitly, and open Redis inside the task. |
| M3 | `git clone` hardening | `services/repository_service.py:191-215` | The token is embedded in the URL (visible in `ps` and possibly in stderr, which is stored and logged). There's no repo size limit, so the disk can fill. On `wait_for` timeout the process isn't killed, and `rmtree` runs while git is still writing. It also runs inside the web process (512 MB on Render free). Use `GIT_ASKPASS` or a credential header, `--filter=blob:limit`, `proc.kill()` on timeout, and a job worker. |
| M4 | DB transaction and connection held open during 30–90 s AI calls | `services/review_service.py:69-83`, `routers/pull_requests.py` | `flush()` before the AI call keeps a transaction open, and the pool (10+20) is exhausted under modest load. Call the AI first, or commit and reopen. |
| M5 | `format_response` claims "never raises" but can | `ai/response_formatter.py:94-109` | `float("high")`, a non-dict item in findings, or a top-level JSON array all raise. A parse failure is saved as a **COMPLETED** review with score 0 and risk 100, which looks like a real (terrible) result. Validate with a Pydantic model and mark the review FAILED. |
| M6 | AI output written to the DB unvalidated | `services/review_service.py:97-158` | `severity` goes into `String(20)` and `line_number` into `Integer`. A string `"42-45"` or a long severity causes a Postgres error, so the whole review is lost. Coerce and clamp values, and clamp scores to 0–100. |
| M7 | Code-review cache semantics | `services/review_service.py:49-55, 243-264` | The key is the content hash only, ignoring language, detail level, and provider. A cache hit creates a review with **no findings or category scores**, so the second user sees empty tabs. `force_refresh` isn't a field on `CodeReviewRequest`, so it's dead code. |
| M8 | File upload edge cases | `routers/reviews.py:62-76` | The upload limit is 1 MB, but `CodeReviewRequest.content` has `max_length=100_000` and `min_length=10`, so the manually built model raises a Pydantic `ValidationError` and the endpoint returns 500. `language or _detect_language(...)` never detects anything because the form default is the truthy `"auto"`. |
| M9 | Vulnerable or unmaintained dependencies | `backend/requirements.txt:16` | `python-jose 3.3.0` is unmaintained and has known CVEs (algorithm confusion, JWE DoS). Switch to `PyJWT`. Many pins are about two years old (FastAPI/Starlette, httpx/h11, etc.). Add `pip-audit` and `npm audit` to CI. |
| M10 | Tokens are readable by JavaScript | `lib/api/client.ts:20,64`, `lib/stores/auth-store.ts`, `callback/page.tsx:63` | Access and refresh tokens are in `localStorage`, and the JWT is in a non-HttpOnly cookie. Any XSS steals a 30-day refresh token. Prefer HttpOnly, Secure, SameSite cookies set by the API. |
| M11 | Refresh token model | `services/auth_service.py:125-160` | There's one `refresh_token_hash` per user, so logging in on a second device logs out the first. Two tabs refreshing at once means one gets revoked and the user is force-logged-out. `is_active` isn't checked on refresh. Logout doesn't invalidate the current access token (15 min). Use a per-session token table with a reuse grace window. |
| M12 | Non-functional UI presented as working | `settings/page.tsx`, `debt/page.tsx`, `dashboard/page.tsx:40`, `components/layout/header.tsx` | The provider radio buttons and notification toggles don't save (there's no API, and `UserSettings` is never read). **"Delete Account" does nothing** (no endpoint, which is also a GDPR concern). The Debt page ignores the data it fetches, and its severity filter does nothing. "Issues Found" is hard-coded to "—". The bell button is dead. |
| M13 | PR and repo reviews lose their findings | `routers/pull_requests.py:113-147`, `services/repository_service.py` | PR review stores only counts, so `/history/{id}` shows empty tabs. Repository analysis never creates a `Review` row, so the History "Repositories" filter is always empty. |
| M14 | Privacy claim is false | `frontend/app/(auth)/login/page.tsx:72` vs `services/review_service.py:64,260` | The login page says "We never store your code permanently", but up to 50 k chars of source are stored indefinitely in `reviews.source_code`. Change the copy, or add retention and deletion. |
| M15 | Broken links to a page that doesn't exist | `repositories/page.tsx:156`, `dashboard/page.tsx:166` | These link to `/repositories/{id}`, but there's no `repositories/[id]/page.tsx`, so users get a 404. (`repositoriesApi.get` and the `RepositoryDetail` types are unused as a result.) |
| M16 | No status polling for analysis | `repositories/page.tsx` | The status stays "pending" or "analyzing" until a manual reload (`staleTime` 60 s). Add `refetchInterval` while any repo is pending or analyzing. |
| M17 | Markdown styling and fonts not applied | `components/review/review-result-panel.tsx:149`, `pull-requests/page.tsx:141`, `app/globals.css:32` | `prose` classes are used, but `@tailwindcss/typography` isn't installed or registered, so AI summaries render unstyled. `--font-sans: "Inter"` doesn't match next/font's hashed family, so it should use `var(--font-inter)`. JetBrains Mono is never loaded. |
| M18 | SQL echo logs secrets when `DEBUG=true` | `core/database.py:27` | `echo=settings.DEBUG` (default True) logs bound parameters, including GitHub tokens and refresh hashes on `UPDATE users`. |
| M19 | docker-compose exposes the DB and Redis | `docker-compose.yml` | Postgres and Redis are bound to all host interfaces with default passwords. The Redis password is visible in the healthcheck args. Migrations never run. The `repo_clones:/tmp/repos` volume is unused (clones go to `mkdtemp`). Compose fails if `frontend/.env.local` is missing. |
| M20 | Fragile GitHub URL parsing | `services/repository_service.py:50-53` | `.../repo.git` becomes the repo name `repo.git`, and `.../repo/tree/main` becomes owner `tree` and repo `main`. `github.com.evil.com` passes the schema regex. Parse with `urllib.parse` and a strict regex. |
| M21 | Frontend production image build breaks | `frontend/Dockerfile:29`, no `frontend/.dockerignore` | `COPY --from=builder /app/public` fails because no `public/` directory is tracked in git. `COPY . .` copies `node_modules`, `.next`, and `.env.local` into the build context and image. |
| M22 | Unique `github_login` can block logins | `models/user.py:32` | If user A renames and user B takes A's old login, B's first login violates the unique index, causing a 500 until A logs in again. Drop the uniqueness (`github_id` is the real key). |
| M23 | Error messages hidden from users | all `onError` handlers in the frontend | `e.message` is Axios's generic "Request failed with status code 502", so the backend's `detail` is never shown. Extract `error.response?.data?.detail`. |
| M24 | Tests miss every business flow, and CI is misconfigured | `backend/app/tests/*`, `.github/workflows/ci.yml` | There are no tests for reviews, repos, PRs, or the OAuth callback, which is how C3, C4, and H7 shipped. CI starts a Postgres service the tests never use (they use SQLite) and no Redis. There's no backend lint or type check (ruff or mypy), and Playwright never runs in CI. The custom `event_loop` fixture is deprecated in pytest-asyncio ≥0.23. |
| M25 | Docs describe features that don't exist | `README.md:43,122,183,189`, `DEPLOYMENT.md:63-65` | Rate limiting, Celery background jobs, the audit trail, the "routers → services → **repositories**" layering, Radix UI, and RHF + Zod are all claimed but not implemented or used. `celery -A app.jobs worker` would fail because `app/jobs` is empty. |
| M26 | Health sub-scores are mislabeled | `services/repository_service.py:148-152` | `documentation_score` is filled from `best_practices` and `complexity_score` from `architecture`. The prompt never asks for documentation or complexity. |

---

## 🔵 Low

| # | Issue | Location |
|---|---|---|
| L1 | GitHub's raw error body is returned to clients in `detail` (`response.text`, `e.data`) | `services/auth_service.py:47,51,65`, `repository_service.py:59,211` |
| L2 | `/api/openapi.json` stays public in production while the docs UIs are hidden | `main.py:47` |
| L3 | A `UUIDMixin` with `index=True` on the primary key creates a redundant `ix_<table>_id` index on **every** table | `models/base.py:39`, migration |
| L4 | `TimestampMixin` docstring says "via DB triggers", but it's the ORM `onupdate` (raw SQL updates won't bump it) | `models/base.py` |
| L5 | `AppException.__init__(**kwargs)` swallows kwargs, and `ValidationError` shadows Pydantic's class name | `core/exceptions.py` |
| L6 | Retries fire on non-retryable errors (401, 400, bad key), wasting 2–10 s × 3 | `ai/providers/*.py` |
| L7 | Gemini: the system prompt is concatenated into the user text, `start_chat` is unnecessary, there's no `response_mime_type="application/json"`, and a blocked response makes `response.text` raise | `ai/providers/gemini.py` |
| L8 | User code containing a triple backtick (```` ``` ````) breaks out of the prompt's code fence (prompt-injection surface) | `ai/prompts.py:142-145` |
| L9 | `ai_provider` and `detail_level` aren't validated; unknown values are silently ignored | `schemas/review.py`, `ai/factory.py` |
| L10 | Dashboard average score is `NaN` when all recent reviews have null scores (division by 0) | `dashboard/page.tsx:32` |
| L11 | `review_type.replace("_", " ")` replaces only the first underscore; use `replaceAll` | `dashboard/page.tsx`, `history/page.tsx` |
| L12 | Repo delete has no confirmation. One `isPending` flag disables Analyze on **all** cards | `repositories/page.tsx` |
| L13 | Upload area says "Drop a file" but has no drag-and-drop handler | `review/page.tsx:192` |
| L14 | The `Select` component's `label` prop is accepted but never rendered, and icon-only buttons (bell, delete, re-analyze, close) have no `aria-label` | `review/page.tsx`, header, repositories, result panel |
| L15 | `ScoreRing` doesn't clamp the score to 0–100 | `components/shared/score-ring.tsx` |
| L16 | The `?redirect=` param set by middleware is never used after login, so the user always lands on `/dashboard` | `middleware.ts`, callback page |
| L17 | "By signing in you agree to our terms of service" has no link to any terms | `login/page.tsx` |
| L18 | The whole landing page is `"use client"` only for animations, which hurts SEO and the bundle. Its marketing claims are unsubstantiated ("same standard as SonarQube", "< 30s", "∞") | `app/page.tsx` |
| L19 | The PR "View on GitHub" link uses the current input value, not the reviewed URL | `pull-requests/page.tsx` |
| L20 | `next lint` is deprecated (removed in Next 16), and `.eslintrc.json` is the legacy config format with ESLint 9 | `package.json`, `.eslintrc.json` |
| L21 | `next.config.ts` `env.NEXT_PUBLIC_API_URL` is redundant (`NEXT_PUBLIC_*` is inlined automatically), and the `github.com` image pattern is unneeded | `next.config.ts` |
| L22 | `npm test` (and `make test-frontend`) runs Vitest in watch mode locally | `package.json`, `Makefile` |
| L23 | `.PHONY` is missing `up-d migration test install-* docs` | `Makefile:1` |
| L24 | `.gitignore` has duplicate entries (`build/`, `dist/`, `.DS_Store` ×3) | `.gitignore` |
| L25 | `codecov-action@v4` uses the deprecated `file:` input (use `files:`) | `ci.yml` |
| L26 | The backend Dockerfile installs `gcc` and `libpq-dev` (not needed: asyncpg ships wheels, and psycopg2 is unused), runs a single uvicorn worker, and has no `HEALTHCHECK` | `backend/Dockerfile` |
| L27 | Unused imports: `Request` (`routers/auth.py`), `secrets`, `hash_password`, `verify_password` (`auth_service.py`), `Annotated`, `uuid`, `ReviewListItem`, `FindingOut`, `CategoryScoreOut`, and in-function model imports (`routers/reviews.py`), `os`, `cache_key` variable (`repository_service.py:111`), `ReviewStatus`/`Review` usage mix in PR router | various |
| L28 | Types are inconsistent: `Repository.last_analyzed_at` is `Text`, `github_id` is `Integer` (fine today; GitHub IDs are heading toward 64-bit, so `BigInteger` is safer) | `models/repository.py:52`, `models/user.py` |

---

## ♻️ Redundant Code & Files (safe-to-remove candidates)

### Empty or placeholder files
- `backend/app/jobs/__init__.py`: an empty package. Celery is never wired up.
- `backend/app/repositories/__init__.py`: an empty package. The README's "repositories layer" doesn't exist.
- `backend/alembic/versions/.gitkeep`: not needed now that a migration exists.
- `backend/app/ai/providers/__init__.py`: eagerly imports all three SDKs, which defeats the factory's lazy imports.
- `frontend/components/providers/theme-provider.tsx` plus `next-themes`: the theme is hard-coded dark with `enableSystem={false}` and no toggle, so the wrapper does nothing.

### Unused backend code
- `core/security.py`: `hash_password`, `verify_password`, `pwd_context` (OAuth-only app, no passwords; the model docstring says so) and their tests in `test_security.py::TestPasswordHashing`.
- `core/redis.py`: `cache_delete`, `cache_exists`.
- `core/exceptions.py`: `AppException.to_http`, `ForbiddenError`, `ConflictError`, `ValidationError`, `RateLimitError`.
- `middleware/auth.py`: `get_optional_user`.
- `ai/base.py` and all providers: `health_check()` is never called.
- `schemas/review.py`: `RepoAnalysisRequest.force_refresh` is used, but `CodeReviewRequest` has no `force_refresh` (the dead `getattr` in the service).
- `core/config.py`: `SECRET_KEY`, `APP_NAME`, `REDIS_PASSWORD`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` are never read. The matching Render env vars are also unused.
- **Unused DB model and columns:** the `AuditLog` model and table are never written. `User.role` is never checked. `UserSettings` is written but never read. `Repository.analysis_job_id`, `PullRequest.status`, `.diff_content`, and `.files_changed`, `TechnicalDebt.is_resolved` and `.impact`, and `CodeSmell.line_end` are never populated.

### Unused backend dependencies (`requirements.txt`)
`psycopg2-binary`, `httpx-oauth`, `gitpython` (the code shells out to `git`), `celery` (listed **twice**), `flower`, `aiofiles`, `orjson`, `rich`, `radon`, `email-validator`, `python-dotenv` (pydantic-settings reads `.env` itself), `passlib` and `bcrypt` (see above). `httpx` is listed **twice**. Test-only packages (`pytest*`, `factory-boy`, `faker`, `aiosqlite`) ship in the production install. Move them to `requirements-dev.txt`.

### Unused frontend code
- `components/shared/skeleton.tsx`: `Skeleton` and `SkeletonText`.
- `lib/utils/index.ts`: `getScoreBg`. `truncate` is used only by its test.
- `lib/api/auth.ts`: `authApi.refresh` (the client interceptor does its own refresh).
- `lib/api/repositories.ts`: `repositoriesApi.get` (no detail page).
- `types/index.ts`: `ApiError`, `PaginatedResponse`, and effectively `RepositoryDetail`/`HealthSnapshot`.
- `app/globals.css`: the `@keyframes score-ring` rule is unused.

### Unused frontend dependencies (`package.json`, 0 imports found)
`@hookform/resolvers`, `react-hook-form`, `zod`, `class-variance-authority`, `date-fns`, `@tanstack/react-table`, **all 14 `@radix-ui/*` packages**, `@testing-library/user-event`, and `@vitest/ui` (only used by the `test:ui` script). `monaco-editor` is an optional peer: `@monaco-editor/react` loads Monaco from a CDN by default, so keep it only if you switch to local bundling.

### Redundant config
- CI's Postgres service: the tests use in-memory SQLite.
- The `repo_clones` volume in `docker-compose.yml`.

---

## ✅ What's done well
- No secrets in git history (all 13 commits checked for API-key and token patterns). `.env` files are correctly ignored.
- UUID primary keys. Ownership checks (`owner_id` / `user_id`) on every repository and review query, so there's no IDOR on those routes.
- Refresh tokens are stored hashed and rotated on use. The access and refresh `type` claim is enforced.
- Security headers middleware, HSTS only in production, and API docs disabled when `DEBUG=false`.
- A clean provider abstraction (`AIProvider` → factory → formatter) that's easy to extend.
- Async SQLAlchemy with `pool_pre_ping`, and a cross-dialect `JSONType` for tests.
- React Markdown is used without `rehype-raw`, so AI output can't inject HTML/XSS.

---

## Suggested fix order
1. **Security (this week):** C1, C2, H1, H3, H4, H13, H2, M10, M18.
2. **Make core features work:** C3, C4, H7, H5, H6, H8, H14, M1, M8, M5/M6.
3. **Robustness and scale:** H9, H10, M2, M3, M4, M11. Move repo analysis and PR review to a real job queue (or delete the Celery scaffolding).
4. **Honesty and UX:** H11, H12, M12–M17, M14, M25.
5. **Cleanup:** the whole ♻️ section, then Low items, and add tests for every flow above (M24).
