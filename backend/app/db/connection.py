import pyodbc
from app.core.config import settings


def get_db_connection():
    """Placeholder function to establish connection to SQL Server."""
    if settings.DB_USER and settings.DB_PASSWORD:
        conn_str = (
            f"DRIVER={{{settings.DB_DRIVER}}};"
            f"SERVER={settings.DB_SERVER};"
            f"DATABASE={settings.DB_NAME};"
            f"UID={settings.DB_USER};"
            f"PWD={settings.DB_PASSWORD};"
            f"TrustServerCertificate={'yes' if settings.DB_TRUST_SERVER_CERTIFICATE else 'no'};"
        )
    else:
        conn_str = (
            f"DRIVER={{{settings.DB_DRIVER}}};"
            f"SERVER={settings.DB_SERVER};"
            f"DATABASE={settings.DB_NAME};"
            f"Trusted_Connection={'yes' if settings.DB_TRUSTED_CONNECTION else 'no'};"
            f"TrustServerCertificate={'yes' if settings.DB_TRUST_SERVER_CERTIFICATE else 'no'};"
        )
    return pyodbc.connect(conn_str)
