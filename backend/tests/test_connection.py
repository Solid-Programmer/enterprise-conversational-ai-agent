"""Tests for deterministic SQL Server connection-string and pool construction."""

from app.db import connection


def test_connection_uses_default_tcp_port_for_sql_authentication(monkeypatch) -> None:
    monkeypatch.setattr(connection.settings, "DB_SERVER", "sql.example.internal")
    monkeypatch.setattr(connection.settings, "DB_PORT", 1433)
    monkeypatch.setattr(connection.settings, "DB_USER", "agent")
    monkeypatch.setattr(connection.settings, "DB_PASSWORD", "secret")
    monkeypatch.setattr(connection.settings, "DB_ENCRYPT", False)
    value = connection._odbc_connection_string()
    assert "SERVER=tcp:sql.example.internal,1433;" in value
    assert "Encrypt=no;" in value


def test_connection_does_not_duplicate_an_explicit_server_port(monkeypatch) -> None:
    monkeypatch.setattr(connection.settings, "DB_SERVER", "sql.example.internal,1444")
    monkeypatch.setattr(connection.settings, "DB_PORT", 1433)
    monkeypatch.setattr(connection.settings, "DB_USER", "agent")
    monkeypatch.setattr(connection.settings, "DB_PASSWORD", "secret")
    assert "SERVER=sql.example.internal,1444;" in connection._odbc_connection_string()


def test_engine_is_process_scoped_and_uses_a_bounded_pool(monkeypatch) -> None:
    created = []

    class FakeEngine:
        pass

    def fake_create_engine(*args, **kwargs):
        created.append((args, kwargs))
        return FakeEngine()

    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(connection, "create_engine", fake_create_engine)
    monkeypatch.setattr(connection.settings, "DB_POOL_SIZE", 3)
    monkeypatch.setattr(connection.settings, "DB_MAX_OVERFLOW", 2)

    assert connection.get_db_engine() is connection.get_db_engine()

    assert len(created) == 1
    assert created[0][1]["pool_size"] == 3
    assert created[0][1]["max_overflow"] == 2
