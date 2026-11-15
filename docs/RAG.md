# RAG "Chat with your repo"

This document explains, phase by phase, how DevReview AI answers questions about an imported
GitHub repository using **Retrieval-Augmented Generation (RAG)**: instead of asking an LLM to
remember a codebase, we *retrieve* the few most relevant pieces of the repo and the saved review
findings, put them in the prompt, and ask the LLM to answer only from them, with `file:line`
citations.

---

## Phase 1 — Database and migration

### What was built

One new Alembic migration (`b4d8f2a61c93_add_rag_chat.py`) and three new SQLAlchemy models.

| Table | What a row is | Key columns |
|---|---|---|
| `code_chunks` | One searchable piece of a repo: a function, a class, or a window of lines | `file_path`, `start_line`, `end_line`, `symbol_name`, `content`, `commit_sha`, `embedding vector(768)`, `search_text tsvector` |
| `chat_sessions` | One conversation about one repo, owned by one user | `user_id`, `repository_id`, `title` |
| `chat_messages` | One question or answer in a session | `role` (`user`/`assistant`), `content`, `citations` (JSON), `provider`, `model`, token counts |

`repositories` gained the index state the UI shows: `index_status`
(`not_indexed` / `indexing` / `indexed` / `failed`), `indexed_commit_sha`, `indexed_at`,
`index_error`, `chunk_count`.

Indexes on `code_chunks`:
- **HNSW on `embedding` with `vector_cosine_ops`**: makes "find the nearest vectors" fast
  (approximate nearest-neighbour search) instead of comparing the question with every row.
- **GIN on `search_text`**: makes keyword (full-text) search fast.
- **B-tree on `repository_id`**: every query is filtered to one repository.

### Why these choices

- **pgvector inside Postgres instead of a separate vector database** (Pinecone, Qdrant…). We already
  run Postgres (Neon in production supports pgvector). One database means one backup, one
  connection, and, most importantly, vector search and ownership checks happen in the same SQL
  query (`JOIN repositories … WHERE owner_id = :user`). No data to keep in sync between two systems.
- **768 dimensions.** Gemini's embedding model can output up to 3072 dimensions, but pgvector's
  HNSW index supports at most 2000. 768 is one of the sizes the model is trained to be truncated to,
  is 4× smaller to store than 3072, and loses very little quality.
- **Cosine distance.** Embeddings are compared by direction, not length. We also normalise vectors
  to length 1, so cosine and dot product give the same ranking.
- **`tsvector` column stored, not computed at query time,** for chunks: there can be thousands of
  chunks per repo and the GIN index needs a stored value.
- **`commit_sha` on every chunk** so a citation can link to the exact version of the file that was
  indexed (`/blob/<sha>/path#L10-L42`), even after the repo moves on.
- **`content` stores the *redacted* text.** It is what gets sent to the chat LLM, so secrets must be
  removed before storing, not only before embedding.
- **`ON DELETE CASCADE`** everywhere: deleting a repository removes its chunks, sessions and
  messages in the database. The ORM relationships use `passive_deletes=True`, like the existing
  ones, so SQLAlchemy lets the database do it instead of loading every child row.
- **Index status lives on `repositories`,** separate from the existing analysis `status`, because
  indexing and analysis are independent jobs.

### Making it work on SQLite tests

Tests run on in-memory SQLite, which has no `vector` or `tsvector` types. Same trick as the existing
`JSONType`:

```python
VectorType   = Text().with_variant(Vector(768), "postgresql")
TSVectorType = Text().with_variant(TSVECTOR(), "postgresql")
```

On Postgres the real types are used; on SQLite the columns are plain `Text`, so
`Base.metadata.create_all` still works. The HNSW/GIN index options are Postgres-only keyword
arguments that SQLite ignores. Any SQL that really needs Postgres (vector search, full-text search)
will be kept inside the retriever (Phase 3) and mocked in tests.
`test_rag_models.py` checks that all new tables build and round-trip on SQLite.

### Trade-offs

- **The embedding size is fixed by the column type.** Switching model or dimension means a new
  migration and re-indexing every repository. This is deliberate: vectors from different models
  are not comparable anyway.
- **HNSW is approximate.** It can, rarely, miss a true nearest neighbour. For a few thousand chunks
  per repo, exact search would also be fast, but HNSW keeps it fast as the table grows across many
  repos.
- **The `pgvector` Python package pulls in `numpy`.** It adds some install size and memory on the
  512 MB Render instance. It's still the official, well-tested way to map the `vector` type in
  SQLAlchemy.
- **Downgrade drops the `vector` extension.** Nothing else uses it today; if something does later,
  remove that line from the downgrade.
- **Local Docker image changed** from `postgres:16-alpine` to `pgvector/pgvector:pg16` (Debian).
  Alpine and Debian sort text differently (musl vs glibc collations), so an old local volume must be
  recreated (`make clean`), not reused.

### Decisions recorded for later phases

- **Findings search uses a query-time `tsvector`.** The review findings tables
  (`security_findings`, `performance_findings`, `code_smells`, `technical_debt`) were not changed.
  The retriever will compute `to_tsvector('simple', title || ' ' || description)` when it searches.
  *Trade-off:* no index, so each search scans that repository's findings. That's fine because a
  repo has tens or hundreds of findings, not millions. If it grows, add a stored generated column
  plus a GIN index in a new migration.
- **Stuck-job rule (30 minutes).** On Render's free tier, a restart can kill a background indexing
  job and leave `index_status = indexing` forever. `POST /index` will be allowed again when the
  status is `failed`, or when it is `indexing` and the repository row hasn't been updated for
  30 minutes. *Trade-off:* a genuinely slow job older than 30 minutes could get a second job
  started next to it. That is safe because re-indexing replaces all chunks in one transaction,
  but it wastes embedding quota. 30 minutes is far longer than a normal index run.

---

## Phase 2 — Indexing pipeline (`backend/app/rag/`)

### What was built

```
POST /repositories/{id}/index ──► set index_status=indexing, commit ──► BackgroundTask
                                                                          │
  GitHub API: HEAD sha == indexed_commit_sha? ── yes ──► done (no clone, no embedding cost)
                                                                          │ no
  cloned_repo()  (shared with repo analysis: token in header, symlinks off, temp dir deleted)
        │
  walk files ─► should_index_path ─► read (≤ RAG_MAX_FILE_CHARS) ─► should_index_content
        │
  redact_secrets ─► chunk_file ─► Chunk(file, start_line, end_line, symbol, language, content)
        │
  one transaction:  DELETE old chunks
                    for each batch of 100: embed (Gemini) ─► INSERT with to_tsvector('simple', …)
                    UPDATE repositories SET index_status=indexed, chunk_count, indexed_commit_sha
                    COMMIT
```

| File | Job |
|---|---|
| `sanitize.py` | Which files may be indexed, and secret redaction |
| `chunker.py` | Code-aware chunking with exact line numbers |
| `embedder.py` | Gemini embedding client (batching, retries, normalisation) |
| `indexer.py` | The pipeline above, plus the stuck-job rule and search-text builder |
| `routers/repositories.py` | `POST /repositories/{id}/index` and `GET /repositories/{id}/index-status` |

`repository_service.py` was changed minimally. Its clone code moved into an async context manager,
`cloned_repo()`, so analysis and indexing share the same safe clone instead of having two copies.
A small `fetch_head_sha()` asks GitHub for the default branch's latest commit.

### Chunking — why "code-aware"

Retrieval returns chunks, and the LLM answers from them. If a chunk is half a function, the answer
is built on half the facts. So we split along the code's own structure:

- **Python** uses the standard library's `ast` module. It gives exact `lineno`/`end_lineno` for every
  top-level function and class, so a function is never cut in half. Decorators are included. Big
  classes (over ~1200 tokens) are split into one chunk per method (`Service.run`). The code *between*
  definitions (module docstring, imports, constants, `app = FastAPI()`) becomes its own chunk, so
  every line of the file is in some chunk.
- **JS/TS** uses no parser (we didn't want a new dependency). A top-level declaration
  (`function`, `class`, `const x =`, `interface`, `type`, `export default`) starts at column 0, and
  a chunk runs until the next one starts. The JSDoc/comment lines directly above a declaration are
  pulled into it. *Limits:* this depends on conventional formatting (Prettier output). A line at
  column 0 inside a multi-line template string could be taken for a declaration, and nested
  functions stay inside their parent. We deliberately avoided brace counting, because braces
  inside strings, regexes and JSX break it in subtle ways.
- **Everything else**, and any symbol that is too big, uses a **sliding window**: ~400 tokens per
  chunk with ~50 tokens of overlap, always cut at line boundaries. The overlap means a sentence or
  statement that falls on a boundary still appears whole in at least one chunk.
- **Header.** The text that gets embedded is prefixed with
  `File: <path> | Symbol: <name> | Language: <lang>`. A function body alone often doesn't say what
  it's about. The path and name (`services/auth_service.py`, `get_github_token`) carry much of the
  meaning a question will match.
- **Tokens are estimated as characters ÷ 4** (no tokenizer dependency). `gemini-embedding-001`
  accepts 2048 tokens, and our largest chunk targets ~1200, which leaves headroom for the estimate
  being off.

### Embeddings — `embedder.py`

- `gemini-embedding-001`, `output_dimensionality=768`.
- **Two task types.** Chunks are embedded as `RETRIEVAL_DOCUMENT`; questions (Phase 3) as
  `CODE_RETRIEVAL_QUERY`. Gemini trains these as a pair: a natural-language question and the code
  that answers it land close together, even though they share few words.
- **Normalised to length 1.** Per the Gemini docs, only the full 3072-dimension output is already
  normalised. A truncated 768 vector isn't, so we divide by its length ourselves.
- **Batches of 100, sent one after another,** with tenacity retrying rate limits (HTTP 429) and
  server errors (5xx): up to 6 attempts with exponential backoff (4 s → 60 s). Bad requests (4xx)
  are not retried, because retrying won't fix them.
- **No fallback to OpenAI/Claude.** Different models produce vectors in different "spaces", so a
  question embedded by model B can't be compared with chunks embedded by model A. A silent fallback
  would make search return nonsense with no error. Failing loudly is better: the job is marked
  `failed`, and the user can retry.
- Google has since released `gemini-embedding-2` (auto-normalised, 8k-token input, task given as a
  prompt prefix instead of `task_type`). Moving to it would mean re-indexing every repo. That's
  possible later; `001` was the fixed decision for this project.

### Security

- **Never read:** `.env*`, `id_rsa*`, key/cert files (`.pem .key .p12 .pfx .crt …`), lock files,
  `*.min.*`, source maps, anything in `SKIP_DIRS` (`node_modules`, `.git`, `dist`…), files over
  `RAG_MAX_FILE_CHARS`, binaries (contain a NUL byte), and minified files (any line over 1000
  characters).
- **Allow-list, not deny-list,** for everything else: only known code/doc/config extensions are
  indexed (the existing analysis list plus Markdown, YAML, TOML, JSON, SQL, shell, Dockerfile,
  Makefile).
- **Redaction** runs before chunking. Whatever is stored, embedded or later sent to the chat LLM has
  already been cleaned. It catches PEM private-key blocks, AWS/GitHub/Google/OpenAI/Anthropic/
  Stripe/Slack token formats, JWTs, credentials inside URLs, and quoted values assigned to names
  like `password`, `secret`, `token` or `api_key`. Calls like `get_password()` aren't touched.
  **Redaction keeps the number of lines the same,** so citations still point at the right lines.
- Reading reuses `_read_sample()` (rejects symlinks and anything outside the clone), and cloning
  reuses the existing safe clone.
- Background-job errors: only our own `AppException` messages are saved to `index_error` and shown
  in the UI. Anything else becomes a generic message, so internals don't leak.

### Full-text search text

Postgres' `to_tsvector('simple', …)` lowercases and splits on punctuation, but
`getGithubToken` stays one word, and a path like `lib/api/client.ts` is kept as one "file" token.
So before indexing we append identifiers split on camelCase/snake_case (`get github token`) and
the path's parts (`lib api client ts`). Then a question that says "github token" matches the
function `getGithubToken`.
We use `simple`, not `english`: the English configuration stems words and drops stop words, which
mangles code identifiers.

### Transactions and memory

- **Delete + insert + status update happen in one transaction.** If embedding fails halfway, the
  rollback leaves the previous index untouched, and readers keep seeing the old chunks until the
  commit. A retry is always safe.
- **Embed and insert batch by batch,** so only ~100 vectors (≈ 2.5 MB as Python floats) are in memory
  at once instead of all of them. This matters on Render's 512 MB instance. *Trade-off:* the
  transaction stays open while Gemini is called, which can take a few minutes for a large repo.
  That's acceptable here because only that repo's chunk rows are locked.
- **Skip unchanged repos** with one GitHub API call (`HEAD sha == indexed_commit_sha`), before any
  clone or embedding cost.
- `RAG_MAX_CHUNKS_PER_REPO` (default 3000) caps cost and memory. *Shortcut:* files are walked in
  alphabetical order, so the cap drops whatever comes last. Ranking files (source before tests)
  would be better if real repos hit the cap.
- `content_hash` is stored for a future improvement: incremental re-indexing that only re-embeds
  chunks whose content changed. Today every re-index embeds everything again.

### Known limits

- Only the default branch is indexed.
- Notebooks, and languages other than Python/JS/TS, use window chunking (no symbol names).
- Indexing runs in FastAPI `BackgroundTasks` inside the web process. A restart kills it; the
  30-minute rule and the safe retry handle that. A real job queue would be the next step at scale.
