"""Centralised configuration via pydantic-settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_answer_model: str = ""

    @property
    def model(self) -> str:
        return self.ollama_answer_model or self.ollama_model


settings = Settings()
