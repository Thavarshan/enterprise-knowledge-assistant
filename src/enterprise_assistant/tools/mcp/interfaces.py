"""Typed future MCP client interface."""

from typing import Any, Protocol


class MCPClient(Protocol):
    async def invoke(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...
