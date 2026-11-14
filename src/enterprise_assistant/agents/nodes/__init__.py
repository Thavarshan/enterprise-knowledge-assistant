"""Collect functions used as LangGraph nodes.

Each node is a small deterministic function that reads a subset of graph
state and returns an update. The graph module connects these nodes and
controls routing, state reduction, and termination.
"""
