"""Pydantic request/response schemas for answer-service."""
from pydantic import BaseModel


class AnswerRequest(BaseModel):
    question: str
    sql: str
    rows: list
