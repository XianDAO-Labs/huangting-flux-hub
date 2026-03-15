"""
app/core/config.py
==================
Application configuration using Pydantic Settings.
All values can be overridden via environment variables or a .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Application ---
    APP_NAME: str = "Huangting-Flux Hub"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "The central API hub for the Huangting-Flux Agent Network."
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # --- CORS ---
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "https://huangting.ai",
        "https://www.huangting.ai",
        "https://flux.huangting.ai",
    ]

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/huangting_flux"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/huangting_flux"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- WebSocket ---
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds

    # --- Network Stats ---
    STATS_CACHE_TTL: int = 10  # seconds, for /network/stats endpoint

    # --- Rate Limiting ---
    RATE_LIMIT_REGISTER: str = "10/minute"
    RATE_LIMIT_BROADCAST: str = "60/minute"
    RATE_LIMIT_SUBSCRIBE: str = "120/minute"


settings = Settings()
