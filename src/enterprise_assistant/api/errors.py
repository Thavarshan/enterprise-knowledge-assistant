"""Define stable structured errors for the HTTP boundary.

`APIError` carries a status, machine-readable code, and safe client message.
The application exception handler serializes these values without exposing
provider exceptions or internal tracebacks.
"""

from dataclasses import dataclass


@dataclass
class APIError(Exception):
    """Carry a client-safe error across application layers.

    The API exception handler serializes these fields into a stable JSON
    shape. Callers should keep provider details and secrets out of message.

    Attributes:
        status_code: HTTP status returned to the caller.
        code: Stable machine-readable error identifier.
        message: Safe explanation suitable for the client.
    """
    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        """Return the safe message used by standard exception formatting.

        Returns:
            The client-safe error message.
        """
        return self.message
