"""Central backend registry that checks role policy before tool invocation."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from enterprise_assistant.security.authorization import Role

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolAuthorizationError(PermissionError):
    """Raised when the authenticated role cannot use a requested tool."""


class ToolNotFoundError(LookupError):
    """Raised when a tool is not registered or has no installed handler."""


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    allowed_roles: frozenset[Role]


class ToolRegistry:
    def __init__(self) -> None:
        all_roles = frozenset(Role)
        analyst_roles = frozenset({Role.ANALYST, Role.ADMINISTRATOR})
        self._policies = {
            "knowledge_search": ToolPolicy("knowledge_search", all_roles),
            "python_analysis": ToolPolicy("python_analysis", analyst_roles),
            "mcp": ToolPolicy("mcp", analyst_roles),
        }

    def authorize(self, tool_name: str, role: Role) -> ToolPolicy:
        policy = self._policies.get(tool_name)
        if policy is None:
            raise ToolNotFoundError(tool_name)
        if role not in policy.allowed_roles:
            raise ToolAuthorizationError(f"Role '{role.value}' cannot use '{tool_name}'.")
        return policy

    async def execute(
        self,
        tool_name: str,
        role: Role,
        arguments: dict[str, Any],
        handlers: dict[str, ToolHandler],
    ) -> Any:
        """Authorize centrally, then call the registered async handler."""
        self.authorize(tool_name, role)
        handler = handlers.get(tool_name)
        if handler is None:
            raise ToolNotFoundError(tool_name)
        return await handler(arguments)
