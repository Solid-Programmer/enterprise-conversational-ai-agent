import os
from pathlib import Path
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
    AUTH0_DOMAIN: str
    AUTH0_AUDIENCE: str
    REQUEST_TIMEOUT_SECONDS: float = 120
    ROUTER_TIMEOUT_SECONDS: float = 15
    TEXT_TO_SQL_TIMEOUT_SECONDS: float = 30
    SQL_REPAIR_TIMEOUT_SECONDS: float = 30
    ANSWER_GENERATION_TIMEOUT_SECONDS: float = 30
    RETRIEVAL_TIMEOUT_SECONDS: float = 30
    TOOL_TIMEOUT_SECONDS: float = 20
    SQL_EXECUTION_TIMEOUT_SECONDS: float = 15

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
