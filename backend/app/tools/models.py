"""Tool metadata exposed to the router without exposing implementation details."""

from typing import Any, Callable, Dict, FrozenSet

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class RegisteredTool:
    """Internal pairing of router-visible metadata with a deterministic callable."""

    def __init__(
        self,
        definition: ToolDefinition,
        handler: Callable[..., Dict[str, Any]],
        required_tables: FrozenSet[str],
    ) -> None:
        self.definition = definition
        self.handler = handler
        # This is deliberately internal. The router needs a business-level tool
        # contract, while authorization needs the exact physical table boundary.
        self.required_tables = required_tables
