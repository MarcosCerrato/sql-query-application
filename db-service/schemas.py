"""Pydantic request/response schemas for db-service."""
from pydantic import BaseModel


class QueryRequest(BaseModel):
    sql: str


class QueryResponse(BaseModel):
    rows: list[dict]
    count: int
