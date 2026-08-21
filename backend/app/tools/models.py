"""Tool metadata exposed to the router without exposing implementation details."""

from typing import Any, Callable, Dict

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class RegisteredTool:
    """Internal pairing of router-visible metadata with a deterministic callable."""

    def __init__(self, definition: ToolDefinition, handler: Callable[..., Dict[str, Any]]) -> None:
        self.definition = definition
        self.handler = handler
