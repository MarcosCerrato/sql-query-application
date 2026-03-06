# SQL Natural Language Query Application

A Dockerized system that lets you query an Argentine bakery sales database using natural language. The user types a question and receives: a conversational answer, the generated SQL, and the results table.

---

## Table of contents

1. [Architecture](#architecture)
2. [Tech stack](#tech-stack)
3. [Design decisions](#design-decisions)
4. [Query flow](#query-flow)
5. [How to run the system](#how-to-run-the-system)
6. [Project structure](#project-structure)
7. [API endpoints](#api-endpoints)
8. [Dataset](#dataset)
9. [Tests](#tests)
10. [Model evaluation](#model-evaluation)
11. [Scalability](#scalability)
12. [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│              Frontend React (Vite + Tailwind)        │
│                      Port 5173                       │
└────────────────────────┬─────────────────────────────┘
                         │ POST /ask
                         ▼
┌──────────────────────────────────────────────────────┐
│             model-service  (Orchestrator)            │
│                      Port 8001                       │
│  • Generates SQL with Ollama (qwen2.5-coder:7b)      │
│  • SHA256 cache with 5 min TTL                       │
│  • Retry with error context (up to 2 retries)        │
└────────────┬─────────────────────────┬───────────────┘
             │ POST /query             │ POST /answer
             ▼                         ▼
┌─────────────────────┐   ┌─────────────────────────────┐
│    db-service       │   │       answer-service        │
│     Port 8000       │   │         Port 8002           │
│  SQL execution      │   │  Natural language response  │
│  SELECT-only        │   │  (qwen2.5-coder:7b)         │
│  LIMIT auto-inject  │   │  Deterministic fallback     │
└────────┬────────────┘   └──────────────┬──────────────┘
         │                               │
         ▼                               ▼
┌─────────────────────┐   ┌─────────────────────────────┐
│   PostgreSQL 16     │   │       Ollama (local)        │
│    Port 5432        │   │        Port 11434           │
│  sales table        │   │  qwen2.5-coder:7b (SQL)     │
│  24,212 rows        │   │  qwen2.5-coder:7b (SQL+NL)  │
└─────────────────────┘   └─────────────────────────────┘
```

| Service         | Port | Responsibility                                      |
|-----------------|------|-----------------------------------------------------|
| frontend-react  | 5173 | Chat interface (React SPA)                          |
| model-service   | 8001 | Orchestrator: NL → SQL → execution → NL response   |
| db-service      | 8000 | Safe SQL execution against PostgreSQL               |
| answer-service  | 8002 | Converts SQL results to a natural language answer   |
| postgres        | —    | Sales database (24,212 records)                     |
| ollama          | —    | Local LLM (one model, no external API)              |

---

## Tech stack

| Technology | Usage | Why chosen |
|------------|-------|------------|
| **FastAPI** | Backend for all services | Native async, Pydantic typing, ideal for ML APIs |
| **SQLAlchemy + Alembic** | ORM and migrations | Reproducible schema, versioned migrations |
| **Ollama** | Local LLM server | No API costs, no network latency, model swap via env var |
| **qwen2.5-coder:7b** | SQL generation + NL answers | Single model for both tasks: precise enough for SQL, more than capable for paraphrasing results |
| **PostgreSQL 16** | Database | Robust, native DATE support, easy to migrate with Alembic |
| **React 19 + Vite 7** | Frontend | Fast builds, modern ecosystem |
| **Tailwind CSS 4** | Styling | Utility-first, no custom CSS, visual consistency |
| **Docker Compose** | Orchestration | Brings up the full stack with a single command |
| **httpx** | Async HTTP client | Compatible with FastAPI async, better than requests for I/O |
| **Poetry** | Dependency management | Reproducible lock file, dev/prod separation |

---

## Design decisions

### Local LLM (Ollama)
Ollama was chosen over external APIs (OpenAI, Anthropic) to eliminate network dependencies, per-token costs, and variable latency. The model is configured via environment variable, allowing swaps without touching code.

### Single model for both tasks
**qwen2.5-coder:7b** handles both SQL generation and natural language answers. NL answer generation is a simpler task (paraphrasing results), well within the capabilities of a 7B code model. Using one model simplifies the setup and avoids downloading a second ~1.3 GB model for a task that doesn't require it.

### Central orchestrator (model-service)
The frontend makes a single call (`POST /ask`) and model-service coordinates the full pipeline internally. This keeps the frontend simple and centralizes retry and cache logic.

### SHA256 cache + 5 min TTL
The cache key is `SHA256(question + schema columns)`. If the schema changes (via `/refresh-schema`), the cache is automatically invalidated. Avoids redundant LLM calls for repeated questions.

### Few-shots in YAML
16 examples (question → SQL) stored in `few_shots.yaml`. model-service selects the 4 most relevant by keyword overlap. Adjustable without touching Python code.

### Retry with error context
If the generated SQL fails in db-service, model-service forwards the PostgreSQL error to the LLM and requests a correction. Up to 2 retries before returning an error to the user.

### SELECT-only in db-service
db-service rejects any query that is not a SELECT (regex whitelist). Protects the database from accidental or malicious modifications.

### Automatic LIMIT
If the SQL does not include LIMIT, db-service injects `LIMIT 1000` before executing. Protects against queries that would return millions of rows.

### Deterministic fallback in answer-service
If the answer LLM produces a hallucination (an invented number) or garbled output (doesn't cover the key values), the response is discarded and a deterministic bullet-point format is used with the real data.

---

## Query flow

Example: *"What is the best-selling product?"*

```
1. User types in the chat → Frontend

2. Frontend → POST /ask {question} → model-service

3. model-service:
   a. Checks cache (miss on first query)
   b. Fetches schema from db-service with sample values
   c. Selects 4 relevant few-shots from the 16 available
   d. Builds prompt and calls Ollama (qwen2.5-coder:7b)
   e. Extracts SQL from the response (handles ```sql code fences)
   f. Saves to cache

4. model-service → POST /query {sql} → db-service
   db-service executes against PostgreSQL → rows JSON

   (If it fails: model-service forwards the error to the LLM and retries)

5. model-service → POST /answer {question, sql, rows} → answer-service
   answer-service calls Ollama (qwen2.5-coder:7b) → natural text
   (If hallucination or garbled: fallback to bullet-points)

6. model-service → Frontend: {answer, sql, rows}

7. Frontend displays: conversational answer + SQL + table
```

---

## How to run the system

### Requirements

- Docker + Docker Compose v2
- ~5 GB of free disk space (qwen2.5-coder:7b ≈ 4.7 GB)
- No GPU required (CPU inference with Ollama)

### First start

```bash
# Clone the repository and enter the directory
cd "Take-Home Assignment_ SQL Query Application"

# Start everything (first time: downloads models ~5-10 min)
docker compose up --build

# Open the interface
open http://localhost:5173
```

On the first run, the `ollama` container downloads both models automatically before the other services start (healthchecks enforce the startup order).

### Verify all services are healthy

```bash
docker compose ps
# All services should show "healthy"
```

### Changing models

```bash
# Use a different model for SQL
OLLAMA_MODEL=codellama:7b docker compose up

# Change both models
OLLAMA_MODEL=qwen2.5-coder:14b OLLAMA_ANSWER_MODEL=qwen2.5-coder:14b docker compose up
```

### Running without Docker (development)

Each service can be run with Poetry:

```bash
cd db-service
poetry install
poetry run uvicorn main:app --reload --port 8000
```

---

## Project structure

```
.
├── docker-compose.yml          # Full stack orchestration
├── .env                        # OLLAMA_MODEL, OLLAMA_ANSWER_MODEL
├── data.csv                    # Sales dataset (24,212 rows)
│
├── db-service/                 # SQL execution + schema export
│   ├── main.py                 # FastAPI app (endpoints /query, /schema, /health)
│   ├── models.py               # SQLAlchemy model (sales table)
│   ├── config.py               # Settings (DATABASE_URL, QUERY_LIMIT)
│   ├── init_db.py              # Loads CSV into PostgreSQL on startup
│   └── alembic/versions/       # Migrations: create table + date migration
│
├── model-service/              # Text-to-SQL orchestrator
│   ├── main.py                 # FastAPI app factory
│   ├── router.py               # Endpoints: /ask, /text-to-sql, /refresh-schema
│   ├── service.py              # Core logic: prompt, cache, retry, Ollama calls
│   ├── config.py               # Settings (OLLAMA_MODEL, DB_SERVICE_URL, ...)
│   └── few_shots.yaml          # 16 question→SQL examples for few-shot prompting
│
├── answer-service/             # Natural language answer generation
│   └── main.py                 # FastAPI app (endpoint /answer, LLM output validation)
│
├── frontend-react/             # Chat interface
│   ├── src/
│   │   ├── App.jsx             # Main layout (sidebar + chat)
│   │   └── components/         # ChatWindow, ChatInput, MessageBubble, ResultsTable, SQLBlock
│   ├── Dockerfile              # 2-stage build: Vite → nginx
│   └── vite.config.js          # Vite + Tailwind + React
│
└── eval/                       # Model evaluation framework
    ├── questions.yaml          # 16 questions with expected SQL and metrics
    ├── run_eval.py             # Evaluation orchestrator
    ├── judge.py                # Comparison logic
    └── score.py                # Score calculation (100 pts per question)
```

---

## API endpoints

### model-service (port 8001)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ask` | POST | Full pipeline: NL → SQL → execution → NL response |
| `/text-to-sql` | POST | SQL generation only (without executing) |
| `/text-to-sql-with-feedback` | POST | Regenerates SQL with a PostgreSQL error as context |
| `/refresh-schema` | POST | Invalidates cache and re-fetches schema from db-service |
| `/health` | GET | Service status |

### db-service (port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/query` | POST | Executes SQL and returns `{"rows": [...], "count": N}` |
| `/schema` | GET | Returns columns, types, and sample values |
| `/health` | GET | Service status + PostgreSQL connection |

### answer-service (port 8002)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/answer` | POST | Receives `{question, sql, rows}`, returns a natural language response |
| `/health` | GET | Service status |

---

## Dataset

Sales records from an Argentine bakery. **24,212 records** loaded from `data.csv`.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | INTEGER | PK auto-increment | 1 |
| `date` | DATE | Sale date | 2024-10-04 |
| `week_day` | VARCHAR | Day of the week | Monday |
| `hour` | VARCHAR | Time HH:MM | 11:31 |
| `ticket_number` | VARCHAR | Cash register ticket ID | FCB 0003-000024735 |
| `waiter` | INTEGER | Numeric waiter ID | 51 |
| `product_name` | VARCHAR | Product name | Alfajor Super DDL x un |
| `quantity` | INTEGER | Units sold | 2 |
| `unitary_price` | NUMERIC(10,2) | Price per unit | 2700.00 |
| `total` | NUMERIC(10,2) | Line total | 5400.00 |

The `date` column was migrated from VARCHAR to DATE in Alembic migration `0002`.

---

## Tests

Each service has tests with pytest (backend) or vitest (frontend).

```bash
# db-service
cd db-service && poetry run pytest

# model-service
cd model-service && poetry run pytest

# answer-service
cd answer-service && poetry run pytest

# frontend
cd frontend-react && npm test
```

Backend tests use mocks for Ollama and an in-memory SQLite database to isolate external dependencies.

---

## Model evaluation

The `eval/` directory contains a framework to measure end-to-end system quality.

```bash
cd eval
python run_eval.py  # Runs the 16 questions against the live system
```

**Scoring per question (100 points):**

| Metric | Weight | Description |
|--------|--------|-------------|
| `sql_valid` | 30% | The endpoint returns no error |
| `columns_match` | 25% | Returned columns match the expected ones |
| `row_count_match` | 20% | Row count is exact |
| `no_hallucination` | 15% | The response does not invent numbers |
| `not_garbled` | 10% | The response covers the key values |

See `eval/README.md` for more detail.

---

## Scalability

### 1. Larger schemas and more tables

**Current bottleneck:** The entire DB schema (column names, types, 5 sample values) is injected verbatim into every prompt via `fetch_schema` in `model-service/service.py`. With multiple tables or dozens of columns, the prompt grows beyond model context limits and degrades SQL quality.

**Recommendations:**

- **Schema-aware retrieval (RAG):** Embed table and column descriptions with a vector model (e.g. `nomic-embed-text` via Ollama). On each query, retrieve only the relevant tables using pgvector or Qdrant. The `fetch_schema` function in `model-service/service.py` would be replaced by a semantic lookup, keeping prompt size constant regardless of schema growth.
- **Semantic few-shot selection:** Replace the current keyword-overlap selection (`select_few_shots` in `service.py`) with cosine similarity over embedded question vectors. This scales to hundreds of examples without degrading prompt quality — the current keyword approach breaks down as the example set grows.
- **Business metadata layer:** Extend `few_shots.yaml` with per-column natural language descriptions and join hints. Allows the LLM to reason across foreign keys without seeing all rows.

### 2. High frontend traffic

**Current bottleneck:** `model-service` runs as a single container with an in-memory Python dict as cache (`_cache` in `service.py`, TTL = 300 s). Under concurrent load, LLM calls are sequential (Ollama processes one request at a time by default) and the cache is not shared across replicas.

**Recommendations:**

- **Horizontal scaling + load balancer:** Deploy multiple replicas of `model-service` and `answer-service` behind nginx or Traefik. Both services are stateless (no local DB, no state beyond the in-memory cache dict) so scaling out is straightforward once the cache is externalized.
- **Distributed cache (Redis):** Replace the `_cache` dict in `service.py` with Redis. The cache key is already `SHA256(question + schema)`, so it is safe to share across replicas. TTL behavior is preserved with Redis `SETEX`.
- **Async LLM job queue:** Wrap Ollama calls in Celery or RQ. The `/ask` endpoint returns a job ID immediately; the frontend polls or listens via SSE for the result. This prevents timeouts under load and gives users real-time "generating…" feedback — the UI already renders intermediate states.
- **PostgreSQL connection pooling:** Add PgBouncer in front of Postgres. `db-service` opens one connection per request; under high load this exhausts the connection pool. PgBouncer multiplexes connections transparently with no application-level changes.

### 3. LLM layer

**Current bottleneck:** Ollama is single-process with no request batching. Concurrent LLM calls queue sequentially, so latency grows linearly with traffic. There is also no overflow path when the local model is saturated.

**Recommendations:**

- **vLLM for production:** Replace the `ollama` container with vLLM, which supports continuous batching and PagedAttention. The Ollama API interface (`/api/generate`) can be swapped for vLLM's OpenAI-compatible endpoint with minimal changes to `call_ollama()` in `service.py`.
- **GPU in cloud:** For production, a single A10G (24 GB VRAM) can serve `qwen2.5-coder:7b` at ~200 tokens/s — roughly 10× faster than CPU inference. The local Docker Compose setup remains unchanged for development.
- **OpenAI/Anthropic as overflow:** Route to an external API when local Ollama is saturated (response time > threshold). This is already supported by the architecture since all model calls are isolated in `call_ollama()` in `service.py`.
- **Domain fine-tuning:** Use validated (question, SQL) pairs from the `eval/` framework to fine-tune `qwen2.5-coder:7b`. A fine-tuned 7B model typically outperforms a generic 70B on a specific schema, with lower latency and memory footprint.

---

## Troubleshooting

**Services take a long time to start on first run**
Normal. Ollama downloads ~6 GB of models. Healthchecks wait up to 10 minutes.

**The frontend doesn't load**
```bash
docker compose ps  # Check that all services show "healthy"
docker compose logs model-service  # View specific errors
```

**The model returns invalid SQL**
Retry the question. The system has automatic retry with error feedback. For complex questions, be more specific (mention the exact column or value).

**Port already in use**
Make sure ports 5173, 8000, 8001, and 8002 are free before starting.
