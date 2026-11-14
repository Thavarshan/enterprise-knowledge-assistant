"""Submit a nested synthetic trace to the configured LangSmith agent.

The command addresses the existing agent/environment, verifies local
execution and SDK submission status, then attempts a safe remote readback.
No assessment records, live model, Pinecone index, or user data are used.
"""

import json
import sys
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from langsmith import Client, agent_address, traceable, tracing_context, uuid7

from enterprise_assistant.config.settings import Settings, get_settings
from enterprise_assistant.observability.langsmith import (
    create_langsmith_client,
    report_trace_error,
)

AGENT_NAME = "Enterprise Knowledge Assistant"
SYNTHETIC_QUESTION = "Why did payment incident PAY-504 occur?"
SYNTHETIC_INCIDENT_ID = "PAY-504"
EXPECTED_SPANS = frozenset(
    {
        "Enterprise AI Assessment - Connectivity Verification",
        "Mock Supervisor",
        "Mock Document Retrieval",
        "Mock Response Generation",
    }
)


class TraceSubmissionMonitor:
    """Record asynchronous SDK errors without retaining their contents.

    The LangSmith client reports batching and network errors through a
    callback. Only the exception class name is kept for safe status output.
    """

    def __init__(self) -> None:
        """Initialize an empty list of safe error categories.

        The monitor retains exception class names only.
        """
        self.error_types: list[str] = []

    def __call__(self, error: Exception) -> None:
        """Record an export failure and write a sanitized application log.

        Args:
            error: Exception reported by the LangSmith tracing SDK.
        """
        report_trace_error(error)
        self.error_types.append(type(error).__name__)


@traceable(name="Mock Supervisor", run_type="chain")
def _mock_supervisor(question: str, incident_id: str) -> dict[str, str]:
    """Select the deterministic retrieval workflow for the probe.

    Args:
        question: Synthetic assessment question containing no user data.
        incident_id: Fictional incident selected for the synthetic workflow.

    Returns:
        A fixed workflow and fictional incident identifier.
    """
    del question
    return {"workflow": "retrieval", "incident_id": incident_id}


@traceable(
    name="Mock Document Retrieval",
    run_type="tool",
    metadata={"tool_name": "mock_document_retrieval"},
)
def _mock_document_retrieval(incident_id: str) -> dict[str, str]:
    """Return fictional evidence for the synthetic payment incident.

    Args:
        incident_id: Synthetic identifier selected by the mock supervisor.

    Returns:
        Fictional assessment evidence, never fetched from an external store.
    """
    return {
        "incident_id": incident_id,
        "cause": (
            "A fictional gateway retry policy repeated a payment request "
            "after a delayed acknowledgement."
        ),
    }


@traceable(name="Mock Response Generation", run_type="chain")
def _mock_response_generation(
    question: str,
    evidence: dict[str, str],
) -> str:
    """Build a deterministic answer grounded in fictional evidence.

    Args:
        question: Synthetic question associated with the verification run.
        evidence: Fictional incident explanation from the mock retriever.

    Returns:
        A fixed answer suitable for verifying trace execution.
    """
    del question
    return f"{evidence['incident_id']}: {evidence['cause']}"


@traceable(
    name="Enterprise AI Assessment - Connectivity Verification",
    run_type="chain",
)
def _run_verification(question: str, incident_id: str) -> str:
    """Execute the parent pipeline and its three nested operations.

    LangSmith propagates the active run context into decorated children, so
    this parent has supervisor, retrieval, and response spans beneath it.

    Args:
        question: Synthetic question used only by this connectivity check.
        incident_id: Fictional PAY-504 identifier for mock retrieval.

    Returns:
        Deterministic response proving all nested operations ran.
    """
    route = _mock_supervisor(question, incident_id)
    evidence = _mock_document_retrieval(route["incident_id"])
    return _mock_response_generation(question, evidence)


def _missing_configuration(settings: Settings) -> list[str]:
    """List names of required settings without exposing their values.

    Args:
        settings: Configuration loaded from environment and the local file.

    Returns:
        Names of missing or invalid required LangSmith settings.
    """
    required = {
        "LANGSMITH_TRACING": settings.langsmith_tracing,
        "LANGSMITH_API_KEY": bool(settings.langsmith_api_key.strip()),
        "LANGSMITH_ENDPOINT": settings.langsmith_endpoint.startswith(
            "https://"
        ),
        "LANGSMITH_AGENT_ID": bool(settings.langsmith_agent_id.strip()),
        "LANGSMITH_AGENT_ENVIRONMENT": bool(
            settings.langsmith_agent_environment.strip()
        ),
    }
    return [name for name, available in required.items() if not available]


def _walk_runs(root: Any) -> Iterator[Any]:
    """Yield a remotely loaded root run and every loaded descendant.

    Args:
        root: LangSmith run returned by ``Client.read_run``.

    Yields:
        Root and nested run objects present in the response.
    """
    yield root
    for child in root.child_runs or []:
        yield from _walk_runs(child)


def _run_metadata(run: Any) -> dict[str, Any]:
    """Read a run's metadata from the SDK's serialized extra field.

    Args:
        run: LangSmith run returned by the remote read API.

    Returns:
        Run metadata when present, otherwise an empty mapping.
    """
    extra = run.extra or {}
    metadata = extra.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _http_status(error: Exception) -> int | None:
    """Extract an HTTP status code without exposing response content.

    Args:
        error: Exception raised during remote readback.

    Returns:
        HTTP status code when the SDK exception exposes one.
    """
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status is None:
        status = getattr(error, "status_code", None)
    if status is None and type(error).__name__ == "LangSmithNotFoundError":
        return 404
    return status if isinstance(status, int) else None


def _verify_remote_trace(
    client: Client,
    *,
    verification_id: Any,
    agent_id: str,
    environment: str,
    sentinel: str,
    expected_spans: frozenset[str] = EXPECTED_SPANS,
    expected_parent_spans: dict[str, str] | None = None,
    forbidden_spans: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """Read back the submitted run and confirm its address and hierarchy.

    A tracing-only key can submit successfully without read permission. Such
    a case returns BLOCKED, rather than being misreported as a failure.

    Args:
        client: Redacting LangSmith SDK client.
        verification_id: Unique root run ID assigned before execution.
        agent_id: Expected registered agent ID.
        environment: Expected agent environment.
        sentinel: Synthetic marker that must not appear in remote payloads.
        expected_spans: Span names that must occur in the trace tree.
        expected_parent_spans: Child span names and their required parent.
        forbidden_spans: Span names that must not occur in the trace tree.

    Returns:
        A remote verification status and a safe explanation.
    """
    for attempt in range(8):
        try:
            root = client.read_run(verification_id, load_child_runs=True)
            break
        except Exception as exc:
            status = _http_status(exc)
            if status in {401, 403}:
                return "BLOCKED", "remote read permission is unavailable"
            if status == 404 and attempt < 7:
                time.sleep(1)
                continue
            if status == 404:
                return (
                    "BLOCKED",
                    "remote run was not visible after bounded retries",
                )
            return (
                "BLOCKED",
                f"remote readback unavailable ({type(exc).__name__})",
            )
    else:
        return "BLOCKED", "remote run was not queryable before timeout"

    try:
        expected_id = UUID(str(verification_id))
    except ValueError:
        return "FAILED", "local verification run identifier is invalid"
    runs = list(_walk_runs(root))
    if root.id != expected_id:
        return "FAILED", "remote read returned a different run identifier"

    serialized = json.dumps(
        [run.model_dump(mode="json") for run in runs],
        sort_keys=True,
    )
    payloads_are_hidden = all(
        run.inputs in (None, {}) and run.outputs in (None, {})
        for run in runs
    )
    if sentinel in serialized or not payloads_are_hidden:
        return "FAILED", "remote trace payload redaction check failed"

    root_metadata = _run_metadata(root)
    address_is_confirmed = (
        root_metadata.get("agent_id") == agent_id
        and root_metadata.get("agent_environment", "").lower()
        == environment.lower()
    )
    observed_spans = {run.name for run in runs}
    if observed_spans.intersection(forbidden_spans):
        return "FAILED", "a forbidden operation appeared in the trace tree"
    hierarchy_is_confirmed = expected_spans <= observed_spans
    if expected_parent_spans:
        runs_by_id = {run.id: run for run in runs}
        hierarchy_is_confirmed = hierarchy_is_confirmed and all(
            child_name in observed_spans
            and parent_name in observed_spans
            and any(
                run.name == child_name
                and run.parent_run_id == parent.id
                for run in runs
                for parent in runs_by_id.values()
                if parent.name == parent_name
            )
            for child_name, parent_name in expected_parent_spans.items()
        )
    if address_is_confirmed and hierarchy_is_confirmed:
        return "VERIFIED", "remote agent, environment, and span tree match"
    return (
        "FAILED",
        "remote run exists; destination or child hierarchy did not match",
    )


def _print_configuration(settings: Settings) -> None:
    """Print safe destination settings for the verification report.

    Args:
        settings: Validated LangSmith destination settings.
    """
    print(f"Agent: {AGENT_NAME}")
    print(f"Agent ID: {settings.langsmith_agent_id}")
    print(f"Environment: {settings.langsmith_agent_environment}")
    print(f"Endpoint: {settings.langsmith_endpoint}")


def main() -> int:
    """Run the nested probe and return a result suitable for Make/CI.

    Returns:
        Zero for VERIFIED; one for FAILED; two for BLOCKED.
    """
    settings = get_settings()
    print("LangSmith Connectivity Verification\n")
    _print_configuration(settings)

    missing = _missing_configuration(settings)
    if missing:
        print(f"\nConfiguration: BLOCKED ({', '.join(missing)})")
        print("Result: BLOCKED")
        return 2

    monitor = TraceSubmissionMonitor()
    client = create_langsmith_client(
        settings,
        tracing_error_callback=monitor,
    )
    if client is None:
        print("\nConfiguration: FAILED (LangSmith client unavailable)")
        print("Result: BLOCKED")
        return 2

    verification_id = uuid7()
    verification_text = str(verification_id)
    sentinel = f"LANGSMITH_SYNTHETIC_{verification_text}"
    trace_execution_passed = False
    submission_passed = False
    remote_status = "BLOCKED"
    remote_detail = "remote readback was not attempted"
    trace_failure_type = ""
    try:
        address = agent_address(
            settings.langsmith_agent_id,
            settings.langsmith_agent_environment,
        )
        with tracing_context(
            client=client,
            address=address,
            enabled=True,
            tags=["connectivity-verification"],
            metadata={
                "agent_id": settings.langsmith_agent_id,
                "agent_environment": settings.langsmith_agent_environment,
                "agent_name": AGENT_NAME,
                "verification_id": verification_text,
                "workflow": "connectivity-verification",
                "status": "running",
            },
        ):
            answer = _run_verification(
                f"{SYNTHETIC_QUESTION} {sentinel}",
                SYNTHETIC_INCIDENT_ID,
                langsmith_extra={"run_id": verification_id},
            )
        trace_execution_passed = answer.startswith("PAY-504:")
        if not trace_execution_passed:
            raise RuntimeError("Synthetic trace operations returned no answer")
        print("\nConfiguration: PASS")
        print("Trace execution: PASS")

        client.flush(timeout=20)
        pending_runs = getattr(client.tracing_queue, "unfinished_tasks", 0)
        submission_passed = not monitor.error_types and pending_runs == 0
        if not submission_passed:
            trace_failure_type = (
                monitor.error_types[0]
                if monitor.error_types
                else "Timeout"
            )
            print(f"Trace submission: FAILED ({trace_failure_type})")
        else:
            print("Authentication: PASS")
            print("Trace submission: PASS (flush completed without SDK errors)")
            remote_status, remote_detail = _verify_remote_trace(
                client,
                verification_id=verification_id,
                agent_id=settings.langsmith_agent_id,
                environment=settings.langsmith_agent_environment,
                sentinel=sentinel,
            )
            print(f"Remote verification: {remote_status} ({remote_detail})")
    except Exception as exc:
        trace_failure_type = type(exc).__name__
        if not trace_execution_passed:
            print("\nConfiguration: PASS")
            print(f"Trace execution: FAILED ({trace_failure_type})")
        elif not submission_passed:
            print(f"Trace submission: FAILED ({trace_failure_type})")
        else:
            remote_status = "BLOCKED"
            remote_detail = (
                "remote readback unavailable "
                f"({trace_failure_type})"
            )
            print(f"Remote verification: {remote_status} ({remote_detail})")
    finally:
        client.close(timeout=5)

    print(f"Verification ID: {verification_text}")
    if remote_status == "FAILED":
        print("Result: FAILED")
        return 1
    if not submission_passed:
        print("Result: FAILED")
        return 1
    print(f"Result: {remote_status}")
    return 0 if remote_status == "VERIFIED" else 2


if __name__ == "__main__":
    sys.exit(main())
