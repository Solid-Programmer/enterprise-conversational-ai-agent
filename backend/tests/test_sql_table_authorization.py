from app.db.sql_validator import authorize_sql_tables


USER_TABLES = {
    "Sales.Customer",
    "Sales.SalesOrderHeader",
    "Sales.SalesTerritory",
}


def test_authorizes_an_allowed_sales_table() -> None:
    result = authorize_sql_tables(
        "SELECT TerritoryID, SUM(SubTotal) FROM Sales.SalesOrderHeader GROUP BY TerritoryID",
        USER_TABLES,
    )

    assert result.authorized is True
    assert result.requested_tables == ["Sales.SalesOrderHeader"]
    assert result.unauthorized_tables == []


def test_denies_restricted_table() -> None:
    result = authorize_sql_tables("SELECT CardNumber FROM Sales.CreditCard", USER_TABLES)

    assert result.authorized is False
    assert result.unauthorized_tables == ["Sales.CreditCard"]


def test_authorizes_allowed_join() -> None:
    result = authorize_sql_tables(
        """
        SELECT c.CustomerID, SUM(h.SubTotal)
        FROM Sales.Customer AS c
        JOIN Sales.SalesOrderHeader AS h ON h.CustomerID = c.CustomerID
        GROUP BY c.CustomerID
        """,
        USER_TABLES,
    )

    assert result.authorized is True
    assert result.requested_tables == ["Sales.Customer", "Sales.SalesOrderHeader"]


def test_ignores_cte_alias_and_authorizes_its_physical_table() -> None:
    result = authorize_sql_tables(
        """
        WITH orders AS (
            SELECT * FROM Sales.SalesOrderHeader
        )
        SELECT * FROM orders
        """,
        USER_TABLES,
    )

    assert result.authorized is True
    assert result.requested_tables == ["Sales.SalesOrderHeader"]


def test_denies_mixed_allowed_and_restricted_tables() -> None:
    result = authorize_sql_tables(
        """
        SELECT c.CustomerID, cc.CardNumber
        FROM Sales.Customer AS c
        JOIN Sales.PersonCreditCard AS pcc ON pcc.BusinessEntityID = c.PersonID
        JOIN Sales.CreditCard AS cc ON cc.CreditCardID = pcc.CreditCardID
        """,
        USER_TABLES,
    )

    assert result.authorized is False
    assert result.unauthorized_tables == ["Sales.CreditCard", "Sales.PersonCreditCard"]
