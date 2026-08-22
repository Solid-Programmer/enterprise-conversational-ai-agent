"""Deterministic SQLGlot validation for generated Text-to-SQL statements."""

import json
from pathlib import Path
from typing import List, Optional, Set

from pydantic import BaseModel, Field
from sqlglot import exp, parse
from app.observability.tracing import mark_span_error_message, set_span_attributes, set_span_output, traced_span


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sales" / "schema" / "sales_schema.json"
FORBIDDEN_NODE_NAMES = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "COMMAND", "EXECUTE", "EXEC", "INTO",
}


class SQLValidationResult(BaseModel):
    valid: bool
    normalized_sql: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class SQLTableAuthorizationResult(BaseModel):
    """Result of comparing parsed physical table references with RBAC permissions."""

    authorized: bool
    requested_tables: List[str] = Field(default_factory=list)
    unauthorized_tables: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


def _allowed_tables() -> Set[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return {table["qualified_name"] for table in schema.get("tables", [])}


def validate_sql(sql: str, allowed_tables: Optional[Set[str]] = None) -> SQLValidationResult:
    """Validate one read-only Sales T-SQL statement before it reaches the executor."""
    with traced_span("sql.validate", {}, span_kind="CHAIN", input_value=sql) as span:
        result = _validate_sql(sql, allowed_tables)
        set_span_attributes(span, {
            "sql.valid": result.valid,
            "sql.normalized": result.normalized_sql,
            "sql.validation_errors": " | ".join(result.errors) if result.errors else None,
        })
        set_span_output(span, {
            "valid": result.valid,
            "normalized_sql": result.normalized_sql,
            "errors": result.errors,
        }, mime_type="application/json")
        if not result.valid:
            mark_span_error_message(span, "; ".join(result.errors))
        return result


def authorize_sql_tables(
    sql: str,
    allowed_tables: Set[str],
    role: Optional[str] = None,
) -> SQLTableAuthorizationResult:
    """Authorize every physical T-SQL table reference against an RBAC table allow-list.

    CTE aliases are excluded: only actual schema-qualified database tables are
    compared. Any parsing or qualification uncertainty denies execution.
    """
    with traced_span("sql.authorize", {}, span_kind="CHAIN", input_value=sql) as span:
        try:
            statements = parse(sql, dialect="tsql")
            if len(statements) != 1:
                raise ValueError("Exactly one SQL statement is required for authorization.")
            statement = statements[0]
            cte_aliases = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE) if cte.alias_or_name}
            requested_tables: Set[str] = set()
            errors: List[str] = []
            for table in statement.find_all(exp.Table):
                table_name = table.name
                if not table.db and table_name.lower() in cte_aliases:
                    continue
                if not table.db:
                    errors.append(f"Table {table_name} is not schema-qualified.")
                    continue
                requested_tables.add(f"{table.db}.{table_name}")
        except Exception as exc:
            result = SQLTableAuthorizationResult(
                authorized=False,
                errors=[f"Unable to safely extract SQL table references: {exc}"],
            )
        else:
            requested = sorted(requested_tables)
            denied = sorted(set(requested).difference(allowed_tables))
            result = SQLTableAuthorizationResult(
                authorized=not errors and not denied,
                requested_tables=requested,
                unauthorized_tables=denied,
                errors=errors,
            )

        set_span_attributes(span, {
            "authorization.allowed": result.authorized,
            "authorization.role": role,
            "authorization.tables_requested": result.requested_tables,
            "authorization.tables_denied": result.unauthorized_tables,
            "authorization.errors": " | ".join(result.errors) if result.errors else None,
        })
        set_span_output(span, result.model_dump(), mime_type="application/json")
        if not result.authorized:
            mark_span_error_message(span, "; ".join(result.errors) or "Unauthorized SQL table access")
        return result


def _validate_sql(sql: str, allowed_tables: Optional[Set[str]] = None) -> SQLValidationResult:
    """Perform the parser-based validation, isolated so the span remains small."""
    if not sql or not sql.strip():
        return SQLValidationResult(valid=False, errors=["SQL is empty."])
    try:
        statements = parse(sql, dialect="tsql")
    except Exception as exc:
        return SQLValidationResult(valid=False, errors=[f"T-SQL parse error: {exc}"])
    if len(statements) != 1:
        return SQLValidationResult(valid=False, errors=["Exactly one SQL statement is required."])
    statement = statements[0]
    node_names = {node.__class__.__name__.upper() for node in statement.walk()}
    forbidden = sorted(FORBIDDEN_NODE_NAMES.intersection(node_names))
    if forbidden:
        return SQLValidationResult(valid=False, errors=[f"Read-only SELECT only; forbidden SQL operation(s): {', '.join(forbidden)}."])
    if not isinstance(statement, (exp.Select, exp.Union, exp.Subquery)) or statement.find(exp.Select) is None:
        return SQLValidationResult(valid=False, errors=["SQL must be a SELECT statement or CTE leading to SELECT."])

    permitted = allowed_tables or _allowed_tables()
    errors: List[str] = []
    for table in statement.find_all(exp.Table):
        schema_name = table.db
        table_name = table.name
        qualified_name = f"{schema_name}.{table_name}" if schema_name else table_name
        if not schema_name:
            errors.append(f"Table {table_name} must be fully qualified with the Sales schema.")
        elif schema_name != "Sales":
            errors.append(f"Schema {schema_name} is not allowed.")
        elif qualified_name not in permitted:
            errors.append(f"Table {qualified_name} is not in the allowed semantic schema.")
    if errors:
        return SQLValidationResult(valid=False, errors=errors)
    return SQLValidationResult(valid=True, normalized_sql=statement.sql(dialect="tsql"))
