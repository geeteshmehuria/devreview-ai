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
