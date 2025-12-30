"""Application configuration using Pydantic settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "Market Data Service"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "127.0.0.1"  # Use HOST=0.0.0.0 in Docker/production
    port: int = 8000
    log_level: str = "INFO"

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    # Cache duration for metadata (1 month in seconds, as metadata rarely changes)
    cache_expire_seconds: int = 60 * 60 * 24 * 30


settings = Settings()
