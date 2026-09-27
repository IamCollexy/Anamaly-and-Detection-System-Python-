from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Validated config, comparable to NestJS ConfigService but executable at runtime."""
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FINOPS_", extra="ignore")
    database_url: str = "sqlite:///./finops.db"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    upload_dir: Path = Path("/tmp/finops-uploads")
    celery_eager: bool = False

settings = Settings()
