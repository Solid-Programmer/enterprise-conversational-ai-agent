from threading import Lock
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from app.core.config import settings


_engine: Engine | None = None
_engine_lock = Lock()


def _odbc_server_target(server: str, port: int | None) -> str:
    """Return an explicit TCP server target without duplicating configured ports.

    Without ``DB_PORT``, ODBC resolves the configured server or named instance.
    """
    normalized_server = server.strip()
    if not normalized_server:
        raise ValueError("DB_SERVER must not be empty.")
    if port is None or "," in normalized_server or "\\" in normalized_server:
        return normalized_server
    return f"tcp:{normalized_server},{port}"


def _odbc_connection_string() -> str:
    """Build the driver-native string used by the pooled SQLAlchemy engine."""
    server_target = _odbc_server_target(settings.DB_SERVER, settings.DB_PORT)
    if not settings.DB_TRUSTED_CONNECTION and settings.DB_USER and settings.DB_PASSWORD:
        return (
            f"DRIVER={{{settings.DB_DRIVER}}};"
            f"SERVER={server_target};"
            f"DATABASE={settings.DB_NAME};"
            f"UID={settings.DB_USER};"
            f"PWD={settings.DB_PASSWORD};"
            f"Encrypt={'yes' if settings.DB_ENCRYPT else 'no'};"
            f"TrustServerCertificate={'yes' if settings.DB_TRUST_SERVER_CERTIFICATE else 'no'};"
        )
    else:
        return (
            f"DRIVER={{{settings.DB_DRIVER}}};"
            f"SERVER={server_target};"
            f"DATABASE={settings.DB_NAME};"
            f"Trusted_Connection={'yes' if settings.DB_TRUSTED_CONNECTION else 'no'};"
            f"Encrypt={'yes' if settings.DB_ENCRYPT else 'no'};"
            f"TrustServerCertificate={'yes' if settings.DB_TRUST_SERVER_CERTIFICATE else 'no'};"
        )


def get_db_engine() -> Engine:
    """Return the process-scoped, pre-pinged SQL Server connection pool."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = create_engine(
                    f"mssql+pyodbc:///?odbc_connect={quote_plus(_odbc_connection_string())}",
                    poolclass=QueuePool,
                    pool_size=settings.DB_POOL_SIZE,
                    max_overflow=settings.DB_MAX_OVERFLOW,
                    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
                    pool_pre_ping=True,
                )
    return _engine


def get_db_connection():
    """Check out one DB-API connection from the process-scoped pool."""
    return get_db_engine().raw_connection()


def dispose_db_engine() -> None:
    """Close all idle pooled connections during application shutdown."""
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None
