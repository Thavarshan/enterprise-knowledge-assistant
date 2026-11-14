"""Collect typed request and response models for HTTP routes.

Pydantic validation rejects unexpected fields and malformed payloads before
route logic executes. These schemas do not establish user identity.
"""
