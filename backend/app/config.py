"""Runtime configuration, loaded from environment variables (or a .env file)."""
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


# Export .env into the process environment too: provider SDKs (Cohere, Groq, OpenAI) and the
# agent/ module read their API keys from os.environ, not from Settings.
load_dotenv(".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Storage
    database_url: str = "sqlite:///./data/app.db"
    checkpoint_path: str = "./data/checkpoints.db"  # used when DATABASE_URL is sqlite
    upload_dir: str = "./data/uploads"
    public_base_url: str = "http://localhost:8000"

    # LLM: "<provider>:<model>", e.g. "openai:gpt-4o-mini" or "anthropic:claude-sonnet-5-5".
    # Empty -> deterministic offline fallbacks (useful for dev and tests).
    llm_model: str = ""
    vision_model: str = ""  # defaults to llm_model
    embedding_model: str = ""  # e.g. "openai:text-embedding-3-small"; empty -> hashing embedder

    # Outside services
    tavily_api_key: str = ""
    google_maps_api_key: str = ""  # optional; Nominatim is used when empty
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    http_user_agent: str = "eco311-app/0.1"
    open311_endpoints: dict[str, str] = {}  # jurisdiction_id -> GeoReport v2 base URL

    # Email: "console" (log only) or "ses"
    email_backend: str = "console"
    email_from: str = "reports@example.org"

    # Object storage: "local" or "s3"
    storage_backend: str = "local"
    s3_bucket: str = ""
    aws_region: str = "us-east-1"

    # Auth: empty secret -> dev mode (X-User-Id header, default "demo")
    jwt_secret: str = ""
    jwt_audience: str = ""

    # Pin lifecycle
    followup_days: int = 7
    gone_votes_to_resolve: int = 2
    nearby_radius_m: int = 150

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
