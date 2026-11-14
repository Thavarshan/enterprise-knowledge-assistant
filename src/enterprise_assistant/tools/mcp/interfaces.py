"""Specify the asynchronous contract for an MCP tool client.

Implementations must invoke a named tool with validated arguments and return
a result. The protocol has no implementation or permission policy of its
own; callers must authorize tool use before invocation.
"""

from typing import Any, Protocol


class MCPClient(Protocol):
    """Define the asynchronous boundary for a future MCP client.

    The protocol has no network implementation, credential handling, or
    approval flow. A caller must validate arguments and authorize the tool
    before invoking an implementation.
    """

    async def invoke(self, tool_name: str,
                     arguments: dict[str, Any]) -> Any:
        """Invoke a named remote tool with validated arguments.

        Args:
            tool_name: Tool identifier exposed by the MCP server.
            arguments: JSON-compatible arguments accepted by that tool.

        Returns:
            Provider-defined tool result.
        """
        ...
