# Background jobs and live updates

Repository **indexing** (for chat) and repository **analysis** take from seconds to several
minutes: they clone the repo, call Gemini, and write to Postgres. They run as background jobs on
an [ARQ](https://github.com/python-arq/arq) worker, and the browser learns about results from a
live event stream instead of polling.

```
 Browser                      API (FastAPI)                     Redis                 ARQ worker
 ───────                      ─────────────                     ─────                 ──────────
 POST /repositories/{id}/index
                    ──────▶  status = indexing, commit
                             enqueue "index:{repo_id}" ──────▶  queue
 ◀────── 200 {indexing}
                                                                 queue  ──────────▶  index_repository_job
                                                                                     (clone, chunk, embed, save)
                                                                 PUBLISH  ◀────────  status saved to Postgres,
                                                                 events:{user}       event published
 GET /events (SSE, open)  ◀──  relays the user's channel  ◀──────  subscriber
 cache updated, UI flips to "Indexed"
```

Code: `backend/app/jobs/` (queue, tasks, worker, events), `backend/app/routers/events.py`,
`frontend/lib/api/events.ts`, `frontend/components/providers/live-events-provider.tsx`.

## Why a job queue (and not FastAPI `BackgroundTasks`)

`BackgroundTasks` runs the job inside the web process after the response is sent. That was
simple, but:

| Problem with in-process tasks | With ARQ |
|---|---|
| A deploy, crash or free-tier sleep kills the job half-way | The job stays in Redis; ARQ re-queues a cut-off run and the next worker resumes it (up to `JOB_MAX_TRIES`) |
| No limit on parallel jobs — three indexing runs on a 512 MB instance can OOM it | `WORKER_MAX_JOBS` caps concurrency |
| Double-clicking "Index" could start two runs | One job id per repo and kind (`index:{repo_id}`); ARQ ignores a duplicate while one is queued or running |
| The worker can't move off the web service | `WORKER_MODE=external` runs the same worker as its own process — config only |

Retry policy: ARQ only re-runs a job that was **cut off** (cancelled by a shutdown). A job that
fails normally (bad repo, Gemini error, timeout) saves a readable `failed` state and is not retried
automatically — the user retries from the UI. That stops a broken repo from burning the embedding
quota in a loop. Both jobs are idempotent: indexing replaces all chunks in one transaction, and
analysis overwrites its snapshot.

Timeouts: each job enforces `JOB_TIMEOUT_SECONDS` itself, so it can save "took too long" for the
user. ARQ's own timeout is set 60s higher as a backstop.

Why ARQ: it is asyncio-native (the app is fully async), uses the Redis the app already has, and
jobs are plain `async def` functions. It is in maintenance-only mode (bug fixes, no new features);
all queue code sits in `app/jobs/`, so swapping to Taskiq or similar touches one package.

## Why SSE (and not WebSockets)

Updates only flow server → browser, so a one-way stream is enough. SSE is plain HTTP — it works
through Render's proxy, needs no extra protocol handling, and the frontend already parses SSE for
chat answers. The stream:

- authenticates with the normal Bearer token when it opens (`fetch`, not `EventSource`, because
  `EventSource` can't send headers). Every reconnect authenticates again; an open stream outliving
  a 15-minute access token only ever carries this user's own job results.
- sends `ready` once subscribed, then `job` events, and a `: ping` comment every 20s so proxies
  don't close an idle connection.
- uses one Redis pub/sub channel per user (`devreview:events:{user_id}`), so users never see each
  other's events.

Pub/sub is fire-and-forget: a browser that isn't connected misses events. That is safe because
every event describes state already saved in Postgres. On every (re)connect the frontend refetches
in-flight queries, and screens keep a **slow** fallback poll (60s) while a job runs — or their old
fast poll (3–5s) if the stream is down. The stream is closed in background tabs and reopened on
return.

## Running it

| Setup | How | Notes |
|---|---|---|
| Local (default) | `docker compose up` | API runs the worker in-process (`WORKER_MODE=embedded`) |
| Local, separate worker | `make up-worker` | `WORKER_MODE=external` + `worker` container |
| Render free (current) | `render.yaml` | Embedded worker; Redis on Upstash free; `WORKER_POLL_DELAY_SECONDS=15` |
| Render paid | add a `type: worker` service | Starter $7/mo; set `WORKER_MODE=external` on both services |

### Settings

| Variable | Default | Meaning |
|---|---|---|
| `WORKER_MODE` | `embedded` | `embedded`: API process runs the worker. `external`: run `arq app.jobs.worker.WorkerSettings` separately |
| `WORKER_MAX_JOBS` | `2` | Jobs at once (Render free uses `1`: 512 MB) |
| `WORKER_POLL_DELAY_SECONDS` | `0.5` | Seconds between queue checks — one Redis command each |
| `JOB_TIMEOUT_SECONDS` | `1800` | A job running longer is stopped and saved as failed |
| `JOB_MAX_TRIES` | `3` | Runs of a job that keeps being cut off by restarts |

### Redis command budget (Upstash free: 500K commands/month)

The worker sends one command per poll even when idle. At `0.5s` that is ~5M commands/month — far
over the free tier. At `15s` it is ~173K/month even if the service never sleeps (on Render free it
sleeps after 15 idle minutes, and then sends nothing). Open event streams send **no** commands
while idle (no Redis health-check pings), and each job costs a few dozen commands. The trade-off of
`15s`: a new job may wait up to 15 seconds to start; the UI already shows "Indexing…" immediately.

## Restarts and stale states

On startup (API lifespan; worker startup in `external` mode) `reconcile_stale_jobs()` looks for
repos marked `indexing`/`analyzing`:

- job still in Redis (queued or running) → left alone; the worker resumes it;
- job gone (Redis lost its data, or max tries reached) → marked `failed` with a readable message,
  so the UI never spins forever.

The older 30-minute "stuck job" rule for `POST /index` still applies as a last resort.

## Failure modes

| What breaks | What the user sees |
|---|---|
| Redis down when starting a job | `503 Background jobs are unavailable right now`; the repo's status is restored |
| Redis down while the app runs | Event stream reconnects with backoff (1s → 30s); screens fall back to fast polling |
| Embedded worker can't reach Redis at boot | API keeps serving; worker retries every 30s |
| Deploy/restart mid-job | Job re-queued and resumed by the next process (persistent Redis) |
| Job error / timeout | `failed` with a readable message; "Re-index"/"Re-analyse" retries |

## Not covered yet

- Code and PR reviews still run inside the request (the browser waits for the AI). Moving them
  to jobs with a pushed result is the natural next step; it changes the review page's flow.
- No progress percentage in events (only the final state). The indexer already logs batch
  progress, so a `progress` event would be a small addition.
