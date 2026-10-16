from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from environment variables first, then from a .env file if present.
    # extra="ignore" skips variables we don't use here (e.g. POSTGRES_PASSWORD).
    # hide_input_in_errors keeps values (which include secrets) out of the
    # error message when a setting is missing or invalid.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    jwt_secret_key: str
    jwt_expire_minutes: int = 30

    store_name: str = "ShopAssist"

    ai_provider: str = "openrouter"
    ai_model: str
    ai_base_url: str = "https://openrouter.ai/api/v1"
    # Optional here so the app (and tests) can start without it;
    # the AI service fails cleanly if it's missing when a reply is needed.
    openrouter_api_key: str | None = None
    ai_timeout_seconds: float = 30
    ai_max_tokens: int = 500

    embedding_model: str = "nvidia/nemotron-3-embed-1b:free"
    # Must match the size of the chunks.embedding column, which is fixed
    # by the migration. Changing it also needs a new migration.
    embedding_dimensions: int = 2048

    # Knowledge base retrieval: at most this many chunks per question...
    rag_top_k: int = 4
    # ...and only those at least this similar (cosine similarity, -1 to 1).
    # Starting value; tuned with the retrieval quality check.
    rag_min_similarity: float = 0.35

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        # Hosts such as Neon give URLs starting with postgresql:// (or postgres://).
        # SQLAlchemy reads that as "use psycopg2", which isn't installed, so switch
        # it to psycopg (version 3). Options such as ?sslmode=require are kept and
        # passed on to the database driver unchanged.
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


settings = Settings()
