"""Structured contracts shared by routing and orchestration."""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """The only valid route decisions produced by the router."""

    action: Literal["tool", "text_to_sql", "clarify"]
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    clarification_question: Optional[str] = None
    reason: Optional[str] = None


class SQLGeneration(BaseModel):
    """Ollama's constrained Text-to-SQL and repair response contract."""

    sql: Optional[str] = None


class ChatResult(BaseModel):
    """API-safe state returned by the first orchestration skeleton."""

    status: Literal["success", "clarification_required", "requires_human_review", "error"]
    route: Optional[Literal["tool", "text_to_sql"]] = None
    tool_name: Optional[str] = None
    sql: Optional[str] = None
    data: Any = Field(default_factory=list)
    message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
