"""Structured API errors with stable client-facing codes."""

from dataclasses import dataclass


@dataclass
class APIError(Exception):
    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message
