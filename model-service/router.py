"""HTTP layer: Pydantic models and all API endpoints."""
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config import settings
from service import (
    cache_clear,
    _cache_key,
    cache_get,
    cache_set,
    generate_sql,
    log_event,
    select_few_shots,
    fetch_schema,
)

router = APIRouter()

# ── Request / response models ──────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    question: str


class TextToSQLResponse(BaseModel):
    sql: str
    cached: bool = False


class FeedbackRequest(BaseModel):
    question: str
    pg_error: str  # error returned by db-service on previous attempt


class AskResponse(BaseModel):
    answer: str
    sql: str
    rows: list


# ── Private helpers ────────────────────────────────────────────────────────────

async def call_db_query(client: httpx.AsyncClient, sql: str) -> httpx.Response:
    return await client.post(
        f"{settings.db_service_url}/query",
        json={"sql": sql},
        timeout=30,
    )


async def call_answer_service(
    client: httpx.AsyncClient, question: str, sql: str, rows: list
) -> str:
    resp = await client.post(
        f"{settings.answer_service_url}/answer",
        json={"question": question, "sql": sql, "rows": rows},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["answer"]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/text-to-sql", response_model=TextToSQLResponse)
async def text_to_sql(req: QuestionRequest, request: Request):
    schema = request.app.state.schema
    few_shots = request.app.state.few_shots
    client: httpx.AsyncClient = request.app.state.http_client

    key = _cache_key(req.question, schema)
    if cached_sql := cache_get(key):
        log_event("INFO", "cache_hit", question=req.question, sql=cached_sql)
        return TextToSQLResponse(sql=cached_sql, cached=True)

    t0 = time.time()
    relevant_shots = select_few_shots(req.question, few_shots)

    try:
        sql = await generate_sql(client, req.question, schema, relevant_shots)
    except httpx.HTTPStatusError as e:
        log_event("ERROR", "ollama_error", detail=e.response.text)
        raise HTTPException(status_code=502, detail="Ollama error")
    except httpx.RequestError:
        log_event("ERROR", "ollama_unreachable")
        raise HTTPException(status_code=502, detail="Ollama unreachable")

    latency_ms = int((time.time() - t0) * 1000)
    log_event("INFO", "text_to_sql_ok",
              question=req.question, sql=sql, latency_ms=latency_ms)
    cache_set(key, sql)
    return TextToSQLResponse(sql=sql)


@router.post("/text-to-sql-with-feedback", response_model=TextToSQLResponse)
async def text_to_sql_with_feedback(req: FeedbackRequest, request: Request):
    """Re-generate SQL given a PostgreSQL execution error from a previous attempt."""
    schema = request.app.state.schema
    few_shots = request.app.state.few_shots
    client: httpx.AsyncClient = request.app.state.http_client
    relevant_shots = select_few_shots(req.question, few_shots)

    t0 = time.time()
    log_event("INFO", "text_to_sql_feedback",
              question=req.question, pg_error=req.pg_error)

    try:
        sql = await generate_sql(
            client, req.question, schema, relevant_shots,
            error_context=f"The query failed with: {req.pg_error}",
        )
    except httpx.HTTPStatusError as e:
        log_event("ERROR", "ollama_error", detail=e.response.text)
        raise HTTPException(status_code=502, detail="Ollama error")
    except httpx.RequestError:
        log_event("ERROR", "ollama_unreachable")
        raise HTTPException(status_code=502, detail="Ollama unreachable")

    latency_ms = int((time.time() - t0) * 1000)
    log_event("INFO", "text_to_sql_feedback_ok",
              question=req.question, sql=sql, latency_ms=latency_ms)
    return TextToSQLResponse(sql=sql)


@router.post("/refresh-schema", status_code=200)
async def refresh_schema(request: Request):
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        request.app.state.schema = await fetch_schema(client)
        cache_clear()
        log_event("INFO", "schema_refreshed")
        return {"status": "ok"}
    except Exception:
        log_event("ERROR", "schema_refresh_failed")
        raise HTTPException(status_code=502, detail="Could not reach db-service")


@router.post("/ask", response_model=AskResponse)
async def ask(req: QuestionRequest, request: Request):
    schema = request.app.state.schema
    few_shots = request.app.state.few_shots
    client: httpx.AsyncClient = request.app.state.http_client
    relevant_shots = select_few_shots(req.question, few_shots)

    t0 = time.time()
    try:
        sql = await generate_sql(client, req.question, schema, relevant_shots)
    except HTTPException as e:
        if e.detail == "NOT_APPLICABLE":
            return AskResponse(
                answer="I can only answer questions about the available sales data.",
                sql="",
                rows=[],
            )
        raise

    try:
        result = await call_db_query(client, sql)
        max_db_retries = 2
        for attempt in range(max_db_retries):
            if result.status_code != 400:
                break
            pg_error = result.json().get("detail", "")
            log_event("INFO", "ask_retry", question=req.question,
                      pg_error=pg_error, attempt=attempt + 1)
            sql = await generate_sql(
                client, req.question, schema, relevant_shots,
                error_context=pg_error,
            )
            result = await call_db_query(client, sql)

        if result.status_code == 400:
            pg_error = result.json().get("detail", "Unknown DB error")
            log_event("ERROR", "ask_db_retries_exhausted",
                      question=req.question, pg_error=pg_error)
            raise HTTPException(status_code=422,
                                detail=f"Could not generate a valid query after {max_db_retries} retries: {pg_error}")
        result.raise_for_status()

        rows = result.json()["rows"]
        answer = await call_answer_service(client, req.question, sql, rows)

    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        log_event("ERROR", "ask_upstream_error", detail=e.response.text)
        raise HTTPException(status_code=502, detail="Upstream service error")
    except httpx.RequestError as e:
        log_event("ERROR", "ask_request_error", detail=str(e))
        raise HTTPException(status_code=502, detail="Upstream service unreachable")

    latency_ms = int((time.time() - t0) * 1000)
    log_event("INFO", "ask_ok", question=req.question, sql=sql, latency_ms=latency_ms)
    return AskResponse(answer=answer, sql=sql, rows=rows)


@router.get("/health")
async def health(request: Request):
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        resp = await client.head(f"{settings.ollama_url}/")
        resp.raise_for_status()
        return {"status": "ok"}
    except Exception:
        log_event("ERROR", "health_check_failed")
        raise HTTPException(status_code=503, detail="Ollama unavailable")
