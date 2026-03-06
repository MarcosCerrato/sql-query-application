"""DB service: execute read-only SQL and expose table schema."""
import logging
import re
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

import init_db
from config import settings
from database import engine
from schemas import QueryRequest, QueryResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    init_db.init()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)



@app.post("/query", response_model=QueryResponse)
def run_query(req: QueryRequest):
    sql = req.sql.strip().rstrip(";")

    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

    # Inject a row limit if the query does not already have one
    if not _LIMIT_RE.search(sql):
        sql = f"{sql} LIMIT {settings.query_row_limit}"

    logger.info("Executing query: %.200s", sql)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = [dict(row._mapping) for row in result]
        logger.info("Query returned %d rows", len(rows))
        return QueryResponse(rows=rows, count=len(rows))
    except ProgrammingError as e:
        detail = str(e.orig) if e.orig else str(e)
        logger.warning("Invalid SQL query: %s", detail)
        raise HTTPException(status_code=400, detail=f"Invalid SQL query: {detail}")
    except Exception:
        logger.exception("Unexpected error executing query")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/schema")
def get_schema():
    inspector = inspect(engine)
    raw_columns = inspector.get_columns(settings.table_name)
    with engine.connect() as conn:
        columns = []
        for col in raw_columns:
            col_name = col["name"]
            col_type = str(col["type"])
            try:
                sample_rows = conn.execute(
                    text(
                        f"SELECT DISTINCT {col_name} FROM {settings.table_name}"  # noqa: S608
                        f" WHERE {col_name} IS NOT NULL LIMIT 5"
                    )
                )
                sample_values = [str(row[0]) for row in sample_rows]
            except Exception:
                sample_values = []
            columns.append({"name": col_name, "type": col_type, "sample_values": sample_values})
    return {"table": settings.table_name, "columns": columns}


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        logger.exception("Health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")
