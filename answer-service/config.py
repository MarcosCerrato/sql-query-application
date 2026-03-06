"""Centralised configuration via pydantic-settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5-coder:7b"


settings = Settings()
