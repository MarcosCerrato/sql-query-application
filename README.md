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
│  LIMIT auto-inject  │   │                             │
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

### Chat-first UI design
The frontend is intentionally built as a chat interface (sidebar with conversation history + message bubbles) rather than a simple input/output form. Today each question is stateless — the model receives no context from previous turns. This is a deliberate scope decision: the chat shape is the right long-term interface for a natural language query tool, and building it now means adding conversational memory later requires only backend changes, not a UI redesign. See [Scalability → Conversational context](#6-conversational-context) for the planned evolution.

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
# Clone the repository
git clone https://github.com/MarcosCerrato/sql-query-application.git
cd sql-query-application

# Start everything (first time: downloads models ~5-10 min)
docker compose up --build

# Open the interface
open http://localhost:5173
```

On the first run, the `ollama` container downloads the model automatically before the other services start (healthchecks enforce the startup order).

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
| `not_garbled` | 10% | The response covers the key values (checked externally in eval) |

See `eval/README.md` for more detail.

---

## Scalability

### 1. Database optimization

`db-service` opens one PostgreSQL connection per request and runs every query against a single unindexed table. This is fine at the current scale (24,212 rows) but degrades predictably as data and concurrency grow.

- **Indexing:** The `sales` table has no indexes today. High-frequency filter columns (`date`, `product_name`, `waiter`) should be indexed. A composite index on `(date, product_name)` would accelerate the most common aggregation patterns — GROUP BY product over a date range. Alembic already manages schema versions, so adding indexes is a one-line migration.
- **Connection pooling with PgBouncer:** Under concurrent load, `db-service` exhausts PostgreSQL's connection limit quickly (default: 100). Adding PgBouncer in front of Postgres in transaction pooling mode multiplexes hundreds of application connections into a small pool, with no changes to application code.
- **Redis cache for frequent queries:** The current in-memory cache (`_cache` dict in `model-service/service.py`, TTL = 300 s) only covers LLM generation. Frequently repeated questions could also cache the final SQL result in Redis, skipping both the LLM call and the DB round-trip. The cache key `SHA256(question + schema)` is already collision-safe and shared-nothing, so it maps directly to a Redis key.

### 2. Load balancing and service scaling

`model-service` and `answer-service` are both stateless FastAPI containers — they hold no session state and their only shared resource is the in-memory cache dict. This makes horizontal scaling straightforward.

- **Horizontal scaling:** Deploy multiple replicas of `model-service` and `answer-service` behind nginx or Traefik. The only prerequisite is externalizing the cache (see Redis above), since each replica currently has its own isolated `_cache` dict and would bypass each other's cached results.
- **Kubernetes with autoscaling:** In a production environment, deploying the microservices on Kubernetes with Horizontal Pod Autoscaler (HPA) rules on CPU or request queue depth lets the cluster scale replicas up during traffic spikes and back down during idle periods — without manual intervention.
- **Ollama as the real bottleneck:** LLM inference (~15–30 s on CPU) dominates end-to-end latency. Scaling `model-service` replicas without also scaling Ollama shifts the bottleneck without solving it. Multiple Ollama instances behind a load balancer — each with the model loaded in memory — allow parallel inference requests.

### 3. Efficient model inference

Ollama runs `qwen2.5-coder:7b` as a single-process server with no request batching. Requests queue sequentially, so latency scales linearly with concurrent users.

- **GPU acceleration:** Moving Ollama to a machine with a GPU (e.g., A10G, 24 GB VRAM) brings inference from ~25–30 s to ~2–5 s per query — a 5–10× speedup with no code changes. The Docker Compose setup already supports the Ollama GPU runtime via the `deploy` block.
- **vLLM for production throughput:** Replace the `ollama` container with vLLM, which implements continuous batching and PagedAttention memory management. This allows multiple concurrent requests to share GPU compute rather than queue sequentially. The `call_ollama()` function in `model-service/service.py` would only need its endpoint URL updated, since vLLM exposes an OpenAI-compatible API.
- **Model distillation / smaller model for simple queries:** Not all queries need a 7B model. A lightweight router could classify incoming questions as simple (direct aggregation, single filter) or complex (multi-condition, subquery, date arithmetic) and route easy ones to a smaller, faster model (e.g., `qwen2.5-coder:3b`). Based on benchmarks from similar tasks, a 3B model handles straightforward aggregations correctly at roughly 2.5× the speed.
- **External API as overflow:** When local Ollama is saturated, `call_ollama()` in `service.py` could fall back to an external provider (OpenAI, Anthropic) based on a response-time threshold. The model call is already fully isolated in that function, so adding a fallback path requires no architectural changes.

### 4. Asynchronous processing

LLM generation (~15–30 s) makes synchronous HTTP calls fragile under load — connections time out, and users get no feedback during processing.

- **Job queue with Kafka or Celery:** Offload `call_ollama()` calls to background workers. The `/ask` endpoint would return a job ID immediately; the frontend polls a `/result/{job_id}` endpoint or connects via Server-Sent Events (SSE) for a streaming response. The React frontend already renders intermediate states ("generating…"), making this a UI-compatible change.

### 5. Logging and monitoring

The current system has no observability layer. In production, silent failures (hallucinations, slow queries, Ollama timeouts) would be invisible.

- **Prometheus + Grafana:** Instrument each FastAPI service with `prometheus-fastapi-instrumentator` to expose request latency, error rates, and queue depth as metrics. A Grafana dashboard would surface the LLM latency distribution, SQL validity rate over time, and cache hit ratio — making it straightforward to detect regressions after model or prompt changes.
- **Structured logging:** Replace plain `print` statements with structured JSON logs (e.g., via Python's `logging` module + `python-json-logger`). Each log entry would include `question_hash`, `service`, `latency_ms`, and `sql_valid` — enabling log-based alerting in tools like Loki or CloudWatch.
- **Alerting:** Set threshold alerts on error rate (e.g., >10% SQL validation failures in 5 min) and P95 latency (e.g., >45 s end-to-end). These would catch model regressions, database connectivity issues, or traffic spikes before users notice.

### 6. Conversational context

The frontend is already shaped as a chat (message history, bubbles, sidebar). What's missing is the backend treating that history as context. Today every `/ask` call is fully stateless — the model has no memory of previous turns in the same session.

- **Session-scoped conversation history:** Assign a `session_id` (UUID) to each chat session on the frontend. Include the last N question/answer pairs in the prompt sent to `call_ollama()`. This allows follow-up questions like "filter that by Monday" to resolve against the previous query without the user repeating themselves.
- **Multi-request result management:** With conversation history, the frontend can display results from multiple queries in the same session side by side or as a scrollable thread — each bubble showing its own SQL block and results table. The `MessageBubble`, `SQLBlock`, and `ResultsTable` components are already independent, making this a compositional change rather than a redesign.
- **Persistent sessions:** Store conversation history in Redis (keyed by `session_id`) with a TTL matching the user's expected session length. This makes sessions survive page refreshes and allows the backend to scale horizontally without losing context, since the state lives in a shared store rather than in-process memory.
- **Context window management:** As conversation grows, older turns must be summarized or dropped to stay within the model's context limit. A sliding window (keep last 5 turns) or a lightweight summarization step before each call would handle this transparently.

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
