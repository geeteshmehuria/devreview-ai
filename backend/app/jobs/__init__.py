"""
Background jobs (ARQ) and live job events.

    API request ──enqueue──▶ Redis queue ──▶ ARQ worker runs the job
                                                  │ publish when done
    browser ◀── SSE  GET /api/v1/events ◀── Redis pub/sub (one channel per user)

- queue.py   — enqueue helpers and job ids (one id per repo+job kind, so duplicates are ignored)
- tasks.py   — the job functions: repository indexing and repository analysis
- worker.py  — ARQ WorkerSettings; runs inside the API (WORKER_MODE=embedded) or on its own
- events.py  — publish/subscribe of per-user events, SSE formatting
"""
