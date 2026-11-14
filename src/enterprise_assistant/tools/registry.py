"""Enforce backend role policy before dispatching an async tool handler.

The registry maps known tool names to allowed roles, rejects unknown tools
and missing handlers, then awaits an injected handler. Analytics and MCP
policies exist, but the graph currently wires only knowledge search.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from enterprise_assistant.security.authorization import Role

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolAuthorizationError(PermissionError):
    """Reject a tool request made by a disallowed role.

    The graph or API boundary should convert this policy failure into a
    safe response without exposing protected tool output.
    """


class ToolNotFoundError(LookupError):
    """Report an unknown tool or a missing executable handler.

    A policy entry alone does not imply that an implementation is installed.
    """


@dataclass(frozen=True)
class ToolPolicy:
    """Describe which authenticated roles may use one named tool.

    Attributes:
        name: Stable registry key for the tool.
        allowed_roles: Immutable set checked before handler dispatch.
    """
    name: str
    allowed_roles: frozenset[Role]


class ToolRegistry:
    """Centralize backend role checks for named tool handlers.

    Knowledge search is allowed to all roles. Analytics and MCP policy
    entries allow analysts and administrators, but the graph currently
    installs only knowledge search. Prompt instructions are not a substitute
    for this server-side check.

    Notes:
        Policies and handlers are separate: authorize can succeed while
        execute still fails because no handler is supplied.
    """

    def __init__(self) -> None:
        """Install the current role policy table.

        Viewer access covers knowledge search. Analyst and administrator
        roles are allowed by policy for analytics and MCP scaffolds.
        """
        all_roles = frozenset(Role)
        analyst_roles = frozenset({Role.ANALYST, Role.ADMINISTRATOR})
        self._policies = {
            "knowledge_search": ToolPolicy("knowledge_search", all_roles),
            "python_analysis": ToolPolicy("python_analysis", analyst_roles),
            "mcp": ToolPolicy("mcp", analyst_roles),
        }

    def authorize(self, tool_name: str, role: Role) -> ToolPolicy:
        """Find a tool policy and reject disallowed roles.

        Args:
            tool_name: Stable name from the registry.
            role: Authenticated role resolved by the API.

        Returns:
            Matching policy when the role is allowed.

        Raises:
            ToolNotFoundError: No policy exists for the name.
            ToolAuthorizationError: The role is excluded by policy.
        """
        policy = self._policies.get(tool_name)
        if policy is None:
            raise ToolNotFoundError(tool_name)
        if role not in policy.allowed_roles:
            raise ToolAuthorizationError(
                f"Role '{role.value}' cannot use '{tool_name}'.")
        return policy

    async def execute(
        self,
        tool_name: str,
        role: Role,
        arguments: dict[str, Any],
        handlers: dict[str, ToolHandler],
    ) -> Any:
        """Authorize the caller before awaiting its handler.

        Authorization runs before handler lookup and invocation. The handler
        receives only the arguments passed by the caller; input validation
        remains the tool's responsibility.

        Args:
            tool_name: Registered policy name.
            role: Authenticated role to check.
            arguments: Validated tool-specific input mapping.
            handlers: Per-execution map of installed async handlers.

        Returns:
            The awaited handler result.

        Raises:
            ToolAuthorizationError: Role is not permitted.
            ToolNotFoundError: Policy or executable handler is absent.
            Exception: Handler failures propagate to the graph boundary.
        """
        self.authorize(tool_name, role)
        handler = handlers.get(tool_name)
        if handler is None:
            raise ToolNotFoundError(tool_name)
        return await handler(arguments)
