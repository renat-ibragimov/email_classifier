# Email Classifier

A REST API service that ingests `.eml` files, classifies them with an LLM, and persists the result in PostgreSQL.

Each email is assigned one of six categories (**spam**, **phishing**, **newsletter**, **transactional**, **personal**, or **automated**) together with a confidence score, plain-language reasoning, and a list of supporting signals.

## Features

- `POST /classify/` - upload an `.eml` file and get a classification back
- `GET /classify/{id}/` - fetch a previously classified record by ID
- **Deduplication** by SHA-256 of raw `.eml` bytes; the same file uploaded twice returns the cached result with `200` instead of re-running the LLM
- **Two-pass classification**: a stricter "senior analyst" review runs when first-pass confidence is below the threshold (`reviewed=true` in the response)
- **OpenAI tool use** is forced via `tool_choice` so the model can only return a valid category from the enum
- **Concurrent-safe**: uploads with the same content racing in parallel are coalesced via a unique constraint and a `IntegrityError` retry; only one classification runs

## Tech stack

- Python 3.12, FastAPI (async)
- PostgreSQL 16, SQLAlchemy 2.x async, asyncpg, Alembic
- OpenAI Python SDK (forced `tool_choice` on a `classify_email` function)
- pytest + pytest-asyncio + pytest-cov, httpx for ASGI in-process tests
- ruff for lint, Docker Compose for everything

## Quick start

You need Docker and Docker Compose. Then:

```bash
# 1. Create .env with your OpenAI key
echo "OPENAI_API_KEY=sk-..." > .env

# 2. Bring up the stack (Postgres + app, migrations run on app startup)
make run
# or:
docker compose up --build
```

The API is then reachable at `http://localhost:8000`.

**Swagger UI** is at [`http://localhost:8000/docs`](http://localhost:8000/docs) — the easiest way to upload a sample `.eml` and try the endpoints.
**ReDoc** is at [`http://localhost:8000/redoc`](http://localhost:8000/redoc).

Stop with:

```bash
make stop
```

## Configuration

`.env` is loaded by `pydantic-settings`. Required and optional variables:

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | yes | — | App refuses to start without it (pydantic `ValidationError`) |
| `DATABASE_URL` | no | `postgresql+asyncpg://postgres:postgres@db:5432/email_classifier` | Override for local dev, e.g. when running uvicorn on host against dockerized DB use `localhost:5432` |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | |
| `CONFIDENCE_THRESHOLD` | no | `0.85` | First-pass confidence `<=` this value triggers a second review pass |

## Trying the API

Sample `.eml` files for manual testing live in [`tests/fixtures/`](tests/fixtures/):

- Category samples: `spam.eml`, `newsletter.eml`, `transactional.eml`, `personal.eml`, `automated.eml`, `test.eml` (phishing, initial test file)
- "Hard" samples designed to trigger the second-pass review: `hard_p.eml` (subtle phishing), `hard_s.eml` (subtle spam)
- Edge cases: `no_from.eml` (422), `oversized.eml` (422), `invalid.eml` (422), `wrong_extension.elm` (422)

### Via Swagger UI

1. Open `http://localhost:8000/docs`
2. Expand **POST `/classify/`**, click **Try it out**, upload one of the sample files, click **Execute**
3. Note the `id` field in the response
4. Expand **GET `/classify/{record_id}/`**, paste the id, click **Execute**

### Via curl

```bash
# Classify
curl -X POST http://localhost:8000/classify/ \
     -F "file=@tests/fixtures/spam.eml"

# Fetch by ID
curl http://localhost:8000/classify/<record-id>/
```

### Response codes

| Endpoint | Status | When |
| --- | --- | --- |
| `POST /classify/` | `201 Created` | New file, classification performed |
| | `200 OK` | Duplicate of an already-classified file |
| | `422 Unprocessable Content` | Wrong extension, file > 10 MB, or missing `From` header |
| | `500 Internal Server Error` | LLM call failed; record is persisted with `status=failed` and can be retried by re-uploading |
| `GET /classify/{id}/` | `200 OK` | Record found |
| | `404 Not Found` | Unknown ID |
| | `422 Unprocessable Content` | Invalid UUID |

## Architecture

Layered FastAPI service. Request flow: `routers/classify.py` → `ClassificationService.classify()` → parser → classifier (OpenAI) → repository → DB.

```
app/
├── routers/         HTTP handlers (POST /classify/, GET /classify/{id}/)
├── services/
│   ├── classification_service.py   Orchestration: dedup, parse-then-classify-then-persist
│   ├── classifier.py               OpenAI tool-use, two-pass review logic
│   ├── parser.py                   .eml → ParsedEmail DTO
│   └── hasher.py                   SHA-256 over raw bytes
├── repositories/
│   └── classification.py           DB access + IntegrityError race handling
├── models/                         SQLAlchemy ORM
├── schemas/                        Pydantic response models
├── helpers/                        DTOs, enums (StrEnum with PG-compatible values)
├── database/                       Async engine + session factory
└── config.py                       pydantic-settings
```

### Design notes worth highlighting

- **Parse before DB.** `parse_email` runs first in `classify()`. An invalid `.eml` raises before any row is created, so no orphan `PENDING` records are left behind.
- **PENDING is committed before the LLM call.** The unique-index lock on `content_hash` is released as soon as the row is inserted, so concurrent uploads of the same file don't block on each other during the multi-second OpenAI call.
- **Race handling lives in the repository.** When two requests for the same hash race past the initial lookup, the loser hits `IntegrityError` on flush; the repository rolls back and re-fetches the winner's row, returning `(record, is_new=False)`.
- **Re-classification on non-terminal status.** Records in `PENDING` or `FAILED` are re-classified on a subsequent upload; only `CLASSIFIED` is treated as a terminal hit.
- **HTML body is kept.** `_extract_body` flattens `text/plain` then `text/html` parts because phishing signals (suspicious links, hidden URLs) often live in the HTML.
- **Enums are PostgreSQL-native.** `classification_status` and `email_category` are `CREATE TYPE` enums, owned by the Alembic migration. SQLAlchemy column definitions use `create_type=False` — the migration is the single source of truth.

## Development workflow

All dev tasks run in Docker via `make`:

```bash
make help              # list all targets
make run               # clean + build + bring up the stack
make stop              # stop containers
make clean             # full cleanup, including caches and containers

make ruff_check        # lint
make ruff_fix          # lint with --fix (auto-applies safe fixes back to the host)

make test              # ruff (soft) + run all tests
make test k=hasher     # run only tests matching "hasher"
make cov               # ruff (soft) + tests with coverage report; always rebuilds the test image
```

`test`/`cov` print ruff errors but don't block on them — the lint stage is informational during test runs. Use `make ruff_check` for a strict pass (e.g. in CI).

## Testing

Tests run in a dedicated Docker Compose stack (`docker-compose-test.yml`) with a separate `email_classifier_test` PostgreSQL database. Alembic migrations are applied once per session, and each test truncates the `classification_record` table.

- **Unit-level**: `hasher`, `parser`, `classifier` (with mocked `AsyncOpenAI`), `classification_service` (with mocked repo + classifier), helper DTOs and enums.
- **Repository integration**: real async sessions against `test_db`, covers `find_by_id`, `find_by_hash`, `create` (including the `IntegrityError` race and the defensive `RuntimeError` guard for the impossible "row disappeared" state), and `save`.
- **Router integration**: ASGI in-process via `httpx.AsyncClient` + `ASGITransport`. Tests exercise the full DI chain (`get_session` → `get_repo` → service → repo) so the `AsyncSession` lifecycle is covered without overrides; only `classify_email` is patched to avoid real OpenAI calls.

```bash
make cov
```

Current coverage: **100%** across 22 modules (239 statements).
