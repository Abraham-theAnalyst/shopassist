from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from environment variables first, then from a .env file if present.
    # extra="ignore" skips variables we don't use here (e.g. POSTGRES_PASSWORD).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret_key: str
    jwt_expire_minutes: int = 30


settings = Settings()
