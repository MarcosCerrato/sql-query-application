"""Centralised configuration via pydantic-settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    db_service_url: str = "http://db-service:8000"
    answer_service_url: str = "http://answer-service:8002"
    use_few_shots: bool = False


settings = Settings()
