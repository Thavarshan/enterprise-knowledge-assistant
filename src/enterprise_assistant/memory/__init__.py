"""Provide session persistence contracts and adapters.

The application depends on `SessionStore`; SQLite is the current local
adapter and applies owner filters to all session reads and writes.
"""
