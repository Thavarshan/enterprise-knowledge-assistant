"""Collect FastAPI dependency functions.

Dependencies resolve authenticated, server-owned identity for routes. They
must not accept a caller-supplied role as authorization evidence.
"""
