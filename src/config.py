"""Configuration and environment settings for the News Processing System."""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'news.db'}"

    # LLM Settings (OpenAI / DeepSeek / Ollama / vLLM compatible)
    LLM_API_KEY: str = "ollama"  # or OpenAI / DeepSeek key
    LLM_BASE_URL: str = "http://localhost:11434/v1"  # Default Ollama, change to https://api.openai.com/v1 or https://api.deepseek.com/v1
    LLM_MODEL: str = "qwen2.5:7b"  # or gpt-4o-mini, deepseek-chat, etc.
    LLM_TEMPERATURE: float = 0.0

    # Pipeline Thresholds
    SIMILARITY_THRESHOLD: float = 0.78  # Cosine similarity for deduplication
    AD_FILTER_THRESHOLD: float = 0.40  # Garbage score threshold

    # Telegram (Optional: for Telethon / Pyrogram scrapers)
    TELEGRAM_API_ID: Optional[int] = None
    TELEGRAM_API_HASH: Optional[str] = None
    TELEGRAM_SESSION_NAME: str = "news_session"


settings = Settings()

