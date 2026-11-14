"""Collect adapters used by the Streamlit presentation layer.

These adapters isolate HTTP details from widget code. They communicate with
the FastAPI boundary and do not access application storage directly.
"""
