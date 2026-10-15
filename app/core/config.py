from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from environment variables first, then from a .env file if present.
    # extra="ignore" skips variables we don't use here (e.g. POSTGRES_PASSWORD).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


settings = Settings()
