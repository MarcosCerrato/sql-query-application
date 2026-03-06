"""Centralised configuration via pydantic-settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    table_name: str = "sales"
    query_row_limit: int = 1000


settings = Settings()
