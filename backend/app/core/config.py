import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Enterprise Conversational AI Agent"
    DB_SERVER: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "AdventureWorks2022"
    DB_USER: str = "sa"
    DB_PASSWORD: str = ""
    DB_TRUSTED_CONNECTION: bool = True
    DB_TRUST_SERVER_CERTIFICATE: bool = True
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    QDRANT_URL: str = "http://localhost:6333"
    PHOENIX_ENDPOINT: str = "http://localhost:6006/v1/traces"
    PHOENIX_PROJECT_NAME: str = "enterprise-conversational-agent"
    TRACE_RESULT_PREVIEW_ROWS: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
