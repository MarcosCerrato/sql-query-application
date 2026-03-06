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

### Separate answer-service
Both tasks use the same model (`qwen2.5-coder:7b`), but keeping answer generation in its own service means it can be scaled or replaced independently — swapping the local Ollama call for an external API, or running a different model, without touching the orchestration logic in model-service.

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

Model selection was informed by an offline evaluation across multiple model combinations (different SQL generation and answer models), scored against a fixed set of 26 questions covering aggregations, filters, date/time queries, and multi-language input. Each question was scored on SQL validity, column match, row count accuracy, and answer quality.

`qwen2.5-coder:7b` was chosen for both tasks based on those results — it consistently produced valid SQL and handled Spanish and English questions correctly. The eval framework lives in `eval/` and can be rerun against a live stack.

---

## Scalability

### 1. Database optimization

`db-service` opens one connection per request against a single unindexed table — fine at 24k rows but degrades under load.

- **Indexing:** Columns like `date`, `product_name`, and `waiter` are common filters with no indexes today. A one-line Alembic migration fixes this.
- **Connection pooling:** PgBouncer in front of Postgres would multiplex concurrent connections without touching application code.
- **Redis cache:** The current in-memory cache covers LLM generation only. Moving it to Redis would also cache SQL results, and naturally supports horizontal scaling since the cache becomes shared across replicas.

### 2. Load balancing and service scaling

`model-service` and `answer-service` are stateless — the only prerequisite for running multiple replicas is externalizing the in-memory cache (see Redis above). The real bottleneck is Ollama: LLM inference (~15–30 s on CPU) means scaling the API replicas without scaling Ollama just shifts the queue elsewhere.

### 3. Efficient model inference

Ollama runs as a single-process server with no request batching — latency scales linearly with concurrent users (~25–30 s on CPU).

- **GPU acceleration:** An NVIDIA GPU (e.g., A10G) brings inference to ~2–5 s with no code changes. Docker Compose already supports the Ollama GPU runtime via the `deploy` block.
- **vLLM:** Replacing Ollama with vLLM enables continuous batching and PagedAttention, allowing concurrent requests to share GPU compute. The switch requires only updating the endpoint URL in `model-service/service.py`, since vLLM exposes an OpenAI-compatible API.
- **Model routing:** Not every query needs a 7B model. A simple classifier could route straightforward aggregations to a faster 3B model and reserve the 7B for complex multi-condition queries.
- **External API fallback:** When Ollama is saturated, `generate_sql()` in `service.py` could fall back to an external provider (OpenAI, Anthropic). The LLM call is already isolated in that function, so adding a fallback requires minimal changes.

### 4. Asynchronous processing

LLM generation (~15–30 s) makes synchronous requests fragile under load — connections time out and users get no feedback.

- **Job queue (Celery/Kafka):** The `/ask` endpoint could return a job ID immediately and let the frontend poll or receive results via SSE. The frontend already renders a loading state, so this would be a backend-only change.

### 5. Logging and monitoring

The system currently has no observability layer — slow queries, Ollama timeouts, and SQL failures are invisible in production.

- **Prometheus + Grafana:** `prometheus-fastapi-instrumentator` exposes latency and error rate metrics per service with minimal setup.
- **Structured logging:** Replacing the current `log_event()` print-based approach with JSON logs (e.g., `python-json-logger`) would make entries queryable in Loki or CloudWatch — each log already includes `question`, `sql`, and `latency_ms`.
- **Alerting:** Thresholds on SQL error rate (>10% in 5 min) and P95 latency (>45 s) would catch model regressions and infrastructure issues before users notice.

### 6. Conversational context

Every `/ask` call is stateless — the model has no memory of previous turns. The chat UI already supports the right shape for multi-turn interaction; what's missing is the backend.

- **Session history in the prompt:** Attach a `session_id` to each chat and include the last N question/answer pairs in the LLM prompt. This enables follow-up questions like "filter that by Monday" without the user repeating context.
- **Persistent sessions in Redis:** Store conversation history keyed by `session_id` with a TTL. Sessions survive page refreshes and the approach works across multiple `model-service` replicas.
- **Context window management:** As conversations grow, a sliding window (last 5 turns) or lightweight summarization step prevents the prompt from exceeding the model's context limit.

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
