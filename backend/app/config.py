"""Settings loaded from environment variables or backend/.env (see .env.example)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = REPO_ROOT / "data" / "datarescue.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite by default so the demo runs without a database server.
    # Point this at PostgreSQL (postgresql+psycopg://...) when Docker Compose is available.
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
    seed: int = 42
    # Comma-separated list. Both spellings of the Vite dev origin are allowed by default.
    cors_origin: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origin.split(",") if o.strip()]

    # Optional AI investigator. The Anthropic SDK reads ANTHROPIC_API_KEY itself; we only
    # look at it to decide whether to call the model at all.
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"


settings = Settings()
