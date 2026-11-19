"""Define the role labels used by authentication and tool policies.

Roles are assigned by server-side development configuration. The enum is a
vocabulary for policy checks; it does not itself grant access to a route or
tool.
"""

from enum import StrEnum


class Role(StrEnum):
    """Name the three roles understood by backend authorization policy.

    The enum provides stable labels only; AuthService assigns roles from
    trusted account configuration and ToolRegistry decides tool access.

    Members:
        VIEWER: Chat and knowledge search.
        ANALYST: Viewer capabilities plus policy-allowed analytics and MCP.
        ADMINISTRATOR: All tools that are actually registered and supported.
    """

    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMINISTRATOR = "administrator"


def allowed_access_levels(role: Role) -> frozenset[str]:
    """Map a trusted role to the document access labels it can search.

    Args:
        role: Authenticated role whose retrieval scope should be resolved.

    Returns:
        Access labels permitted for the role.
    """
    return {
        Role.VIEWER: frozenset({"viewer"}),
        Role.ANALYST: frozenset({"viewer", "analyst"}),
        Role.ADMINISTRATOR: frozenset({"viewer", "analyst", "administrator"}),
    }[role]
