from app.db.sql_validator import validate_sql


ALLOWED_TABLES = {"Sales.Customer", "Sales.SalesOrderHeader"}


def test_accepts_cte_over_an_allowed_physical_table() -> None:
    result = validate_sql(
        """
        WITH orders AS (
            SELECT SalesOrderID, CustomerID FROM Sales.SalesOrderHeader
        )
        SELECT * FROM orders
        """,
        ALLOWED_TABLES,
    )

    assert result.valid is True


def test_rejects_disallowed_physical_table_inside_cte() -> None:
    result = validate_sql(
        "WITH cards AS (SELECT CardNumber FROM Sales.CreditCard) SELECT * FROM cards",
        ALLOWED_TABLES,
    )

    assert result.valid is False
    assert result.errors == ["Table Sales.CreditCard is not in the allowed semantic schema."]


def test_rejects_unqualified_physical_table_that_is_not_a_cte_alias() -> None:
    result = validate_sql("SELECT * FROM SalesOrderHeader", ALLOWED_TABLES)

    assert result.valid is False
    assert result.errors == ["Table SalesOrderHeader must be fully qualified with the Sales schema."]


def test_accepts_multiple_ctes_and_validates_their_underlying_tables() -> None:
    result = validate_sql(
        """
        WITH customers AS (SELECT CustomerID FROM Sales.Customer),
        orders AS (SELECT CustomerID FROM Sales.SalesOrderHeader)
        SELECT c.CustomerID FROM customers AS c JOIN orders AS o ON o.CustomerID = c.CustomerID
        """,
        ALLOWED_TABLES,
    )

    assert result.valid is True
