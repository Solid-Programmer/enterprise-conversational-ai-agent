import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Enterprise Conversational AI Agent"
    DB_SERVER: str = "localhost"
    DB_PORT: int | None = None
    DB_NAME: str = "AdventureWorks2022"
    DB_USER: str = "sa"
    DB_PASSWORD: str = ""
    DB_TRUSTED_CONNECTION: bool = True
    DB_TRUST_SERVER_CERTIFICATE: bool = True
    DB_ENCRYPT: bool = False
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_RECYCLE_SECONDS: int = 1800

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_KEEP_ALIVE: str = "30m"
    WARM_RUNTIME_ON_STARTUP: bool = True
    WARM_GENERATION_MODEL_ON_STARTUP: bool = True
    WARM_EMBEDDING_MODEL_ON_STARTUP: bool = True
    WARMUP_TIMEOUT_SECONDS: float = 15
    CORS_ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
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
    SQL_EXECUTION_TIMEOUT_SECONDS: float = 60

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
