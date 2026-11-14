"""Expose the Streamlit presentation entrypoint.

The UI owns presentation state for one browser session and sends identity,
session, and chat operations to FastAPI rather than accessing backend
services or data stores directly.
"""
