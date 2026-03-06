"""Pure business logic: prompts, few-shots, SQL generation, cache, Ollama."""
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx
import yaml
from fastapi import HTTPException

from config import settings

# ── Structured JSON logging ────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra"):
            data.update(record.extra)
        return json.dumps(data, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)


def log_event(level: str, msg: str, **kwargs):
    record = logging.LogRecord(
        name=__name__, level=getattr(logging, level),
        pathname="", lineno=0, msg=msg, args=(), exc_info=None,
    )
    record.extra = kwargs
    logger.handle(record)


# ── Few-shots loaded from YAML ─────────────────────────────────────────────────

_FEW_SHOTS_PATH = Path(__file__).parent / "few_shots.yaml"


def load_few_shots() -> list[dict]:
    if not settings.use_few_shots:
        return []
    with open(_FEW_SHOTS_PATH) as f:
        return yaml.safe_load(f)


def select_few_shots(question: str, all_shots: list[dict], n: int = 4) -> list[dict]:
    """Pick the n most keyword-relevant few-shots for the given question."""
    q_words = set(re.findall(r"\w+", question.lower()))
    scored = []
    for shot in all_shots:
        s_words = set(re.findall(r"\w+", shot["question"].lower()))
        score = len(q_words & s_words)
        scored.append((score, shot))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:n]]


# ── Schema → prompt helpers ────────────────────────────────────────────────────

COLUMN_DESCRIPTIONS = {
    "waiter": "numeric employee ID (not a name)",
    "week_day": "day of the week in English (Monday, Tuesday, …)",
    "hour": "time of sale (PostgreSQL TIME type)",
}


def format_schema(schema: dict) -> str:
    lines = []
    for col in schema.get("columns", []):
        samples = col.get("sample_values", [])
        sample_str = f": {', '.join(samples)}" if samples else ""
        desc = COLUMN_DESCRIPTIONS.get(col["name"], "")
        desc_str = f"  # {desc}" if desc else ""
        lines.append(f"  {col['name']} ({col['type']}){sample_str}{desc_str}")
    return "\n".join(lines)


def build_prompt(question: str, schema: dict, few_shots: list[dict],
                 error_context: Optional[str] = None) -> str:
    schema_text = format_schema(schema)
    shots_text = "\n\n".join(
        f"Q: {s['question']}\nA: {s['sql']}" for s in few_shots
    )
    error_section = ""
    if error_context:
        error_section = (
            f"\nCRITICAL: Your previous query failed with this PostgreSQL error:\n"
            f"{error_context}\n"
            f"You MUST fix this error. Common fixes:\n"
            f"- If the error mentions GROUP BY: add GROUP BY for every non-aggregate column in SELECT\n"
            f"- If the error mentions a missing column: check column names against the schema\n"
            f"- If the error mentions syntax: rewrite the query from scratch\n"
        )

    return f"""You are an expert SQL assistant for a restaurant sales database.

Generate a single PostgreSQL SELECT query for the question below.
Return ONLY the SQL query — no explanations, no markdown, no code fences.
{error_section}
BUSINESS CONTEXT:
This is a restaurant POS database. Each row is a line item in a receipt — "ticket_number" groups line items into transactions, so counting receipts means COUNT(DISTINCT ticket_number). Revenue or income means SUM(total); "best-selling" or "most popular" by volume means SUM(quantity). Day names are in English; weekend means week_day IN ('Saturday', 'Sunday'). The hour column is TIME — to group or filter by hour of day use EXTRACT(HOUR FROM hour).

IMPORTANT RULES:
- The `hour` column is PostgreSQL TIME type. Use direct comparisons: hour < '12:00' or hour >= '16:00'
- Never use SPLIT_PART or CAST on the hour column
- Always include GROUP BY for every non-aggregate column in SELECT
- If a WHERE condition references a name or value that doesn't match the column type (e.g. a person's name for a numeric waiter ID), write the literal value directly — never substitute with a subquery
- If the question is NOT related to the sales data, output ONLY the word: NOT_APPLICABLE

Table: {schema.get('table', 'sales')}
Columns (with sample values):
{schema_text}

Few-shot examples:
{shots_text}
Question: {question}
SQL:"""


# ── SQL extraction / validation ────────────────────────────────────────────────

def extract_sql(text: str) -> str:
    text = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE).strip("` \n")
    text = text.replace(";", "").strip()
    return text + ";"


def looks_like_sql(text: str) -> bool:
    return text.upper().lstrip().startswith(("SELECT", "WITH"))


# ── Query cache ────────────────────────────────────────────────────────────────

_CACHE_TTL = 300  # seconds
_cache: dict[str, tuple[float, str]] = {}  # key -> (timestamp, sql)


def _cache_key(question: str, schema: dict) -> str:
    schema_sig = json.dumps(schema.get("columns", []), sort_keys=True)
    return hashlib.sha256(f"{question}|{schema_sig}".encode()).hexdigest()


def cache_get(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    if entry:
        del _cache[key]
    return None


def cache_set(key: str, sql: str):
    _cache[key] = (time.time(), sql)


def cache_clear():
    _cache.clear()


# ── Ollama call ────────────────────────────────────────────────────────────────

async def call_ollama(client: httpx.AsyncClient, prompt: str) -> str:
    resp = await client.post(
        f"{settings.ollama_url}/api/generate",
        json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


# ── Core SQL generation with retry ────────────────────────────────────────────

async def generate_sql(
    client: httpx.AsyncClient,
    question: str,
    schema: dict,
    few_shots: list[dict],
    error_context: Optional[str] = None,
    max_attempts: int = 3,
) -> str:
    """Call Ollama up to max_attempts times, retrying on non-SQL output."""
    last_error = error_context
    for attempt in range(1, max_attempts + 1):
        prompt = build_prompt(question, schema, few_shots, last_error)
        raw = await call_ollama(client, prompt)
        sql = extract_sql(raw)
        if sql.rstrip(";").strip() == "NOT_APPLICABLE":
            log_event("INFO", "out_of_scope", question=question)
            raise HTTPException(status_code=422, detail="NOT_APPLICABLE")
        if looks_like_sql(sql):
            log_event("INFO", "sql_generated",
                      question=question, sql=sql, attempt=attempt)
            return sql
        last_error = f"Previous attempt returned non-SQL output: {raw[:200]!r}. Return ONLY a SELECT query."
        log_event("WARNING", "non_sql_output",
                  question=question, attempt=attempt, raw=raw[:200])
    raise HTTPException(status_code=422, detail="Model did not return a valid SELECT query")


# ── Schema fetch ───────────────────────────────────────────────────────────────

async def fetch_schema(client: httpx.AsyncClient) -> dict:
    resp = await client.get(f"{settings.db_service_url}/schema")
    resp.raise_for_status()
    return resp.json()
