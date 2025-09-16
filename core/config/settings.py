from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env."""

    app_name: str = "Lead Enricher AI"
    app_description: str = "AI for lead enrichment services"
    app_version: str = "1.0.0"

    mongo_uri: str = "mongodb://localhost:27019/lead_enricher"
    mongo_db_name: str = "lead_enricher"

    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5434/postgres"

    openai_api_key: str
    linkedin_email: str 
    linkedin_password: str 
    perplexity_api_key : str 
    youtube_api_key: str 

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def log_path(self) -> Path:
        """Return the full path to the rotating log file."""
        return Path(self.log_directory) / self.log_filename


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()
