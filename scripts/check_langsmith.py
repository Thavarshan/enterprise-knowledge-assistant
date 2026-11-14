"""Send one synthetic, redacted graph trace to the configured LangSmith.

The command exits successfully only after querying the exact exported trace
and confirming that inputs, outputs, and the synthetic marker were hidden.
"""

import asyncio
import json
import sys
import time
import uuid
from typing import Any

from langsmith import Client, tracing_context

from enterprise_assistant.agents.graph import build_graph
from enterprise_assistant.agents.state import AgentState
from enterprise_assistant.config.settings import get_settings
from enterprise_assistant.observability.langsmith import (
    create_langsmith_client,
)
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.registry import ToolRegistry


async def _run_probe(
    client: Client,
    project_name: str,
    run_id: uuid.UUID,
    sentinel: str,
) -> None:
    """Run the actual graph with synthetic state inside a trace context.

    Args:
        client: Redacting LangSmith SDK client.
        project_name: Destination project configured for the application.
        run_id: Trace ID used to locate the exact exported graph run.
        sentinel: Synthetic marker used to verify content was not exported.
    """
    graph = build_graph(InMemoryRetriever([]), ToolRegistry())
    state: AgentState = {
        "request_id": str(run_id),
        "session_id": str(uuid.uuid4()),
        "user_id": "langsmith-smoke-check",
        "role": Role.VIEWER.value,
        "question": f"Synthetic redaction check {sentinel}",
        "events": [],
    }
    with tracing_context(
        client=client,
        project_name=project_name,
        enabled=True,
    ):
        async for _update in graph.astream(
            state,
            stream_mode="updates",
            config={
                "run_id": run_id,
                "configurable": {"thread_id": state["session_id"]},
            },
        ):
            pass


def _trace_is_redacted(
    runs: list[Any],
    *,
    root_id: uuid.UUID,
    sentinel: str,
) -> bool:
    """Check that the root trace exists and all serialized data is hidden.

    Args:
        runs: Runs returned for the unique root trace ID.
        root_id: Expected LangGraph root run ID.
        sentinel: Synthetic marker that must not occur in exported data.

    Returns:
        True when the root run exists and no inputs or outputs were exported.
    """
    root = next((run for run in runs if run.id == root_id), None)
    if root is None or root.error:
        return False
    if any(run.inputs not in (None, {}) for run in runs):
        return False
    if any(run.outputs not in (None, {}) for run in runs):
        return False
    serialized = json.dumps(
        [run.model_dump(mode="json") for run in runs],
        sort_keys=True,
    )
    return sentinel not in serialized


def _find_trace(
    client: Client,
    run_id: uuid.UUID,
) -> list[Any]:
    """Wait briefly for the exported trace to become queryable.

    Args:
        client: Redacting LangSmith SDK client.
        run_id: Unique trace root ID.

    Returns:
        Runs belonging to the matching trace, or an empty list on timeout.
    """
    for attempt in range(10):
        runs = list(client.list_runs(trace_id=run_id, limit=100))
        if runs:
            return runs
        if attempt < 9:
            time.sleep(1)
    return []


def main() -> int:
    """Submit a synthetic trace and verify delivery plus payload hiding.

    Returns:
        Zero when the exact trace is visible and redacted; otherwise one.
    """
    settings = get_settings()
    client = create_langsmith_client(settings)
    if client is None:
        print(
            "LangSmith check unavailable: enable tracing, provide an API "
            "key, and use a UUID for LANGSMITH_WORKSPACE_ID when set."
        )
        return 1

    run_id = uuid.uuid4()
    sentinel = f"LANGSMITH_REDACTION_PROBE_{run_id.hex}"
    try:
        asyncio.run(
            _run_probe(
                client,
                settings.langsmith_project,
                run_id,
                sentinel,
            )
        )
        client.flush(timeout=20)
        runs = _find_trace(client, run_id)
        if not _trace_is_redacted(
            runs,
            root_id=run_id,
            sentinel=sentinel,
        ):
            print(
                "LangSmith check failed: no matching successful trace was "
                "confirmed with redacted inputs and outputs."
            )
            return 1
        print(f"LangSmith trace verified with redaction: run_id={run_id}")
        return 0
    except Exception as exc:
        print(
            "LangSmith check failed before trace confirmation "
            f"({type(exc).__name__})."
        )
        return 1
    finally:
        client.close(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
