"""Test agent addressing, trace visibility, and async trace integration.

All unit tests use synthetic data and stub the LangSmith network client.
"""

from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast
from uuid import uuid4

from langsmith import AgentAddress, Client, agent_address
from scripts.verify_langsmith import _http_status, _run_verification

from enterprise_assistant.chat import service as chat_service_module
from enterprise_assistant.chat.service import ChatService
from enterprise_assistant.config.settings import Settings
from enterprise_assistant.memory.interfaces import SessionStore
from enterprise_assistant.memory.models import ChatMessage
from enterprise_assistant.observability import langsmith
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.security.authentication import AuthenticatedUser
from enterprise_assistant.security.authorization import Role
from enterprise_assistant.tools.registry import ToolRegistry


def _settings(**overrides: Any) -> Settings:
    """Build isolated LangSmith settings for one test.

    Args:
        overrides: Settings fields that differ from safe defaults.

    Returns:
        Settings instance that does not read the developer's `.env` file.
    """
    values: dict[str, Any] = {
        "_env_file": None,
        "langsmith_tracing": True,
        "langsmith_api_key": "synthetic-test-key",
        "langsmith_endpoint": "https://api.smith.langchain.com",
        "langsmith_agent_id": "viridian",
        "langsmith_agent_environment": "local",
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_load_agent_configuration_from_environment(
    monkeypatch,
) -> None:
    """Load agent routing fields without including the secret in repr.

    Environment values take precedence over the application defaults.
    """
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-test-key")
    monkeypatch.setenv(
        "LANGSMITH_ENDPOINT",
        "https://api.smith.langchain.com",
    )
    monkeypatch.setenv(
        "LANGSMITH_AGENT_ID",
        "viridian",
    )
    monkeypatch.setenv("LANGSMITH_AGENT_ENVIRONMENT", "local")

    settings = Settings(_env_file=None)

    assert settings.langsmith_tracing
    assert settings.langsmith_endpoint == "https://api.smith.langchain.com"
    assert settings.langsmith_agent_id == "viridian"
    assert settings.langsmith_agent_environment == "local"
    assert "synthetic-test-key" not in repr(settings)


def test_disabled_tracing_clears_credential_and_legacy_destinations(
    monkeypatch,
) -> None:
    """Disable export and remove conflicting project-based destinations.

    The SDK must not inherit stale project selectors from the shell.
    """
    for name in (
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_SESSION",
    ):
        monkeypatch.setenv(name, "synthetic-test-value")

    assert not langsmith.configure_langsmith(
        Settings(_env_file=None, langsmith_tracing=False)
    )

    assert langsmith.os.environ["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_API_KEY" not in langsmith.os.environ
    for name in (
        "LANGSMITH_PROJECT",
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_SESSION",
    ):
        assert name not in langsmith.os.environ
    assert langsmith.os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert langsmith.os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"
    assert langsmith.os.environ["LANGSMITH_HIDE_METADATA"] == "true"


def test_client_uses_agent_address_and_informative_payload_processing(
    monkeypatch,
) -> None:
    """Configure the endpoint, agent, secret filter, and error callback.

    A stub captures the settings without making a network connection.
    """
    captured: dict[str, Any] = {}

    class ClientStub:
        """Capture client options without making a network connection."""

        def __init__(self, **kwargs: Any) -> None:
            """Store constructor fields for assertions.

            Args:
                kwargs: LangSmith SDK client settings.
            """
            captured.update(kwargs)

    monkeypatch.setattr(langsmith, "Client", ClientStub)
    settings = _settings()

    client = langsmith.create_langsmith_client(settings)

    assert isinstance(client, ClientStub)
    assert captured["api_url"] == settings.langsmith_endpoint
    assert captured["api_key"] == settings.langsmith_api_key
    assert captured["hide_inputs"] is False
    assert captured["hide_outputs"] is False
    assert captured["hide_metadata"] is False
    assert captured["anonymizer"] is langsmith.sanitize_trace_payload
    assert captured["omit_traced_runtime_info"] is False
    assert langsmith.os.environ["LANGSMITH_AGENT_ID"] == (
        settings.langsmith_agent_id
    )
    assert langsmith.os.environ["LANGSMITH_AGENT_ENVIRONMENT"] == "local"
    assert langsmith.os.environ["LANGSMITH_TRACING"] == "true"
    assert langsmith.os.environ["LANGSMITH_HIDE_INPUTS"] == "false"
    assert langsmith.os.environ["LANGSMITH_HIDE_OUTPUTS"] == "false"
    assert langsmith.os.environ["LANGSMITH_HIDE_METADATA"] == "false"


def test_sdk_client_keeps_content_and_anonymizes_credentials() -> None:
    """Exercise LangSmith's installed secret filter on every trace field."""
    fake_key = f"sk-proj-{'A' * 32}"
    client = Client(
        api_key="synthetic-test-key",
        hide_inputs=False,
        hide_outputs=False,
        hide_metadata=False,
        anonymizer=langsmith.sanitize_trace_payload,
    )
    try:
        assert client._hide_run_inputs(
            {
                "question": "visible synthetic prompt",
                "api_key": fake_key,
            }
        ) == {
            "question": "visible synthetic prompt",
            "api_key": "[SECRET_DETECTED]",
        }
        assert client._hide_run_outputs(
            {"response": "visible synthetic answer"}
        ) == {"response": "visible synthetic answer"}
        assert client._hide_run_metadata(
            {
                "agent_id": "viridian",
                "diagnostic_detail": "visible metadata",
                "api_key": fake_key,
            }
        ) == {
            "agent_id": "viridian",
            "diagnostic_detail": "visible metadata",
            "api_key": "[SECRET_DETECTED]",
        }
        assert client._hide_run_error(
            f"provider rejected credential {fake_key}"
        ) == "provider rejected credential [SECRET_DETECTED]"
    finally:
        client.close(timeout=1)


def test_missing_api_key_is_reported_and_keeps_app_tracing_off(
    monkeypatch,
    caplog,
) -> None:
    """Report opt-in with a missing key without logging secrets.

    An unavailable optional integration leaves API request handling usable.
    """
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    settings = _settings(langsmith_api_key="")

    assert langsmith.create_langsmith_client(settings) is None

    assert caplog.records[-1].missing_settings == "LANGSMITH_API_KEY"
    assert langsmith.os.environ["LANGSMITH_TRACING"] == "false"
    assert "synthetic-test-key" not in caplog.text


def test_trace_payload_preserves_diagnostics_and_scrubs_secrets() -> None:
    """Preserve nested trace content while anonymizing credential patterns."""
    fake_key = f"sk-proj-{'B' * 32}"
    payload = {
        "question": "synthetic visible prompt",
        "document": {"text": "synthetic visible evidence"},
        "answer": "synthetic visible answer",
        "metadata": {"future_field": "visible diagnostic metadata"},
        "error": f"synthetic visible provider detail: {fake_key}",
    }

    assert langsmith.sanitize_trace_payload(payload) == {
        "question": "synthetic visible prompt",
        "document": {"text": "synthetic visible evidence"},
        "answer": "synthetic visible answer",
        "metadata": {"future_field": "visible diagnostic metadata"},
        "error": "synthetic visible provider detail: [SECRET_DETECTED]",
    }


def test_client_initialization_error_is_safe_and_nonfatal(
    monkeypatch,
    caplog,
) -> None:
    """Log setup failure by exception type and disable environment tracing.

    A credential-like exception message must not reach the logs.
    """

    class FailingClient:
        """Raise a credential-like message to check it is never logged.

        The client constructor failure simulates a rejected SDK setup.
        """

        def __init__(self, **_kwargs: Any) -> None:
            """Simulate SDK construction failure.

            Args:
                _kwargs: Client arguments, not used in the failure case.
            """
            raise RuntimeError("synthetic-test-key must stay private")

    monkeypatch.setattr(langsmith, "Client", FailingClient)

    assert langsmith.create_langsmith_client(_settings()) is None

    assert "LangSmith client initialization failed" in caplog.text
    assert "synthetic-test-key" not in caplog.text
    assert langsmith.os.environ["LANGSMITH_TRACING"] == "false"


def test_nested_probe_operations_execute_without_external_credentials(
    monkeypatch,
) -> None:
    """Run the synthetic parent and child functions without export.

    This exercises the exact decorated operations used by the CLI check.
    """
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    result = _run_verification(
        "Why did payment incident PAY-504 occur?",
        "PAY-504",
    )

    assert result.startswith("PAY-504:")
    assert "fictional gateway retry policy" in result


def test_verifier_retries_langsmith_not_found_responses() -> None:
    """Recognize LangSmith's custom 404 exception for eventual readback.

    The client uses a named exception without exposing an HTTP response.
    """
    error_type = type("LangSmithNotFoundError", (Exception,), {})

    assert _http_status(error_type()) == 404


async def test_chat_service_propagates_agent_context_across_graph(
    monkeypatch,
) -> None:
    """Run an async graph under a stubbed parent agent trace context.

    The stub captures the agent address passed by the real ChatService.
    """
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    captured: dict[str, Any] = {}

    class TraceRunStub:
        """Record mutable parent metadata for this local integration test.

        The test asserts that the service marks the run successful.
        """

        def __init__(self) -> None:
            """Initialize safe synthetic trace metadata.

            No SDK objects or network connections are required.
            """
            self.metadata: dict[str, str] = {}
            self.outputs: dict[str, Any] = {}

        def end(self, *, outputs: dict[str, Any] | None = None) -> None:
            """Capture the parent-span output for the local graph check.

            Args:
                outputs: Final synthetic chat answer and citation count.
            """
            if outputs is not None:
                self.outputs.update(outputs)

    class MemoryStub:
        """Store assistant output without opening SQLite.

        No persistent developer data is touched by this test.
        """

        def __init__(self) -> None:
            """Start with no persisted assistant messages.

            Messages are retained only in this local list.
            """
            self.messages: list[tuple[str, str, str]] = []

        async def list_messages(
            self,
            session_id: str,
            owner_id: str,
        ) -> list[ChatMessage] | None:
            """Return no prior history for this isolated test session.

            Args:
                session_id: Synthetic session identifier.
                owner_id: Synthetic authenticated owner.

            Returns:
                An empty history without reading external storage.
            """
            del session_id, owner_id
            return []

        async def append_message(
            self,
            session_id: str,
            user_id: str,
            role: str,
            content: str,
        ) -> None:
            """Record the assistant turn for assertions.

            Args:
                session_id: Synthetic conversation identifier.
                user_id: Synthetic authenticated account identifier.
                role: Message role selected by ChatService.
                content: Deterministic assistant response.
            """
            self.messages.append((session_id, role, content))

    trace_run = TraceRunStub()

    def fake_trace(
        **kwargs: Any,
    ) -> AbstractContextManager[TraceRunStub]:
        """Capture trace settings and yield a local parent-run stub.

        Args:
            kwargs: Values passed to LangSmith's trace context manager.

        Returns:
            Context manager yielding the synthetic trace run.
        """
        captured.update(kwargs)
        return nullcontext(trace_run)

    monkeypatch.setattr(chat_service_module, "trace", fake_trace)
    address: AgentAddress = agent_address(
        "viridian",
        "local",
    )
    memory = MemoryStub()
    service = ChatService(
        InMemoryRetriever([]),
        cast(SessionStore, memory),
        ToolRegistry(),
        langsmith_client=cast(Client, object()),
        langsmith_address=address,
    )
    request_id = str(uuid4())
    session_id = str(uuid4())
    user = AuthenticatedUser(user_id="viewer", role=Role.VIEWER)

    events = [
        event
        async for event in service.stream_turn(
            request_id=request_id,
            session_id=session_id,
            question="Synthetic local graph question",
            user=user,
        )
    ]

    assert any(event.event_type == "completed" for event in events)
    assert memory.messages
    assert captured["name"] == "chat_request"
    assert captured["address"] == address
    assert captured["client"] is not None
    assert captured["inputs"]["question"] == "Synthetic local graph question"
    assert captured["inputs"]["role"] == Role.VIEWER.value
    assert captured["inputs"]["history"] == []
    assert captured["metadata"]["request_id"] == request_id
    assert trace_run.metadata["status"] == "success"
    assert trace_run.outputs["response"] == memory.messages[-1][2]
    assert isinstance(trace_run.outputs["citation_count"], int)
    assert isinstance(trace_run.outputs["citations"], list)
