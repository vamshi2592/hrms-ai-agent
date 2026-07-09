import truststore
from pydantic_settings import BaseSettings, SettingsConfigDict

# optional: only needed on corporate networks that intercept TLS (custom root CA).
# harmless otherwise - falls back to the normal public trust store.
truststore.inject_into_ssl()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    model: str = "llama-3.3-70b-versatile"
    database_url: str = "postgresql+psycopg://hrms:hrms@localhost:5432/hrms"
    jwt_secret: str = "dev-secret-change-me"


settings = Settings()
