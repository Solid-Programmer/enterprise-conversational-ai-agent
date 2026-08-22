"""Deterministic masking for the explicitly approved sensitive SQL result fields."""

from typing import Any


_SENSITIVE_COLUMNS = {
    "CardNumber",
    "ExpMonth",
    "ExpYear",
    "CreditCardApprovalCode",
}


def _mask_value(column_name: str, value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if column_name == "CardNumber":
        return "*" * max(len(text) - 4, 0) + text[-4:]
    return "*" * len(text)


def mask_sensitive_result(data: Any, column_metadata: Any = None) -> Any:
    """Return a copy of result data with only exact sensitive column names masked.

    ``column_metadata`` is intentionally accepted for future qualified-column
    support; current SQL execution exposes returned column names only.
    """
    del column_metadata
    if isinstance(data, list):
        return [mask_sensitive_result(item) for item in data]
    if isinstance(data, dict):
        return {
            key: _mask_value(key, value) if key in _SENSITIVE_COLUMNS else mask_sensitive_result(value)
            for key, value in data.items()
        }
    return data
