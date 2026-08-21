"""Registry for the fixed, deterministic AdventureWorks Sales tools."""

from typing import Any, Dict, List

from app.sales.sales_tools import (
    get_currency_sales_analysis,
    get_customer_analysis,
    get_promotion_performance,
    get_sales_performance,
    get_salesperson_performance,
)
from app.tools.models import RegisteredTool, ToolDefinition


_OPTIONAL_DATE = {"type": ["string", "null"], "format": "date"}


def _definition(name: str, description: str, id_name: str, id_description: str, id_type: str = "integer") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {
                id_name: {"type": [id_type, "null"], "description": id_description},
                "start_date": {**_OPTIONAL_DATE, "description": "Inclusive ISO-8601 period start."},
                "end_date": {**_OPTIONAL_DATE, "description": "Inclusive ISO-8601 period end."},
            },
            "additionalProperties": False,
        },
    )


_TOOLS: Dict[str, RegisteredTool] = {
    "get_sales_performance": RegisteredTool(
        _definition("get_sales_performance", "Overall sales, channel, territory, and monthly performance analysis.", "territory_id", "Optional SalesTerritory integer ID."),
        get_sales_performance,
    ),
    "get_customer_analysis": RegisteredTool(
        _definition("get_customer_analysis", "Customer purchasing behavior, rankings, reasons, and payment-type analysis.", "customer_id", "Optional Customer integer ID."),
        get_customer_analysis,
    ),
    "get_salesperson_performance": RegisteredTool(
        _definition("get_salesperson_performance", "Salesperson revenue, quota, territory, and trend analysis.", "salesperson_id", "Optional SalesPerson BusinessEntity integer ID."),
        get_salesperson_performance,
    ),
    "get_promotion_performance": RegisteredTool(
        _definition("get_promotion_performance", "Special-offer revenue, units, discount, and ranking analysis.", "special_offer_id", "Optional SpecialOffer integer ID."),
        get_promotion_performance,
    ),
    "get_currency_sales_analysis": RegisteredTool(
        _definition("get_currency_sales_analysis", "Territory, country, local-currency, and recorded-rate analysis.", "country_region_code", "Optional country/region code, for example US or FR.", id_type="string"),
        get_currency_sales_analysis,
    ),
}


def list_tool_definitions() -> List[ToolDefinition]:
    """Return router-safe metadata only."""
    return [tool.definition for tool in _TOOLS.values()]


def get_registered_tool(name: str) -> RegisteredTool | None:
    """Return an internal registered tool by its exact public name."""
    return _TOOLS.get(name)


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one allow-listed deterministic tool with router-supplied arguments."""
    tool = get_registered_tool(name)
    if tool is None:
        raise ValueError(f"Unknown deterministic tool: {name}")
    return tool.handler(**arguments)
