"""Test LangSmith configuration and mandatory payload redaction.

These tests avoid external API calls and use only synthetic configuration.
"""

import uuid
from typing import Any

from scripts.check_langsmith import _trace_is_redacted

from enterprise_assistant.config.settings import Settings
from enterprise_assistant.observability import langsmith


def test_configure_langsmith_always_hides_payload_fields(monkeypatch) -> None:
    """Keep redaction flags enabled even when tracing itself is disabled.

    This prevents environment-based tracing from sending raw graph payloads.
    """
    for name in (
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_WORKSPACE_ID",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None, langsmith_tracing=False)

    assert not langsmith.configure_langsmith(settings)

    assert langsmith.os.environ["LANGSMITH_TRACING"] == "false"
    assert langsmith.os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert langsmith.os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"
    assert langsmith.os.environ["LANGSMITH_HIDE_METADATA"] == "true"
    assert "LANGSMITH_API_KEY" not in langsmith.os.environ


def test_invalid_workspace_id_disables_tracing(monkeypatch) -> None:
    """Reject workspace display names instead of passing them as IDs.

    Invalid selectors turn off both explicit and native tracing.
    """
    for name in (
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_WORKSPACE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key="test-key",
        langsmith_workspace_id="Workspace 1",
    )

    assert langsmith.create_langsmith_client(settings) is None

    assert langsmith.os.environ["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_API_KEY" not in langsmith.os.environ
    assert "LANGSMITH_WORKSPACE_ID" not in langsmith.os.environ


def test_langsmith_client_enforces_full_payload_redaction(monkeypatch) -> None:
    """Construct the SDK client with redaction enabled for every payload.

    A stub captures options without contacting LangSmith.
    """
    captured: dict[str, object] = {}

    class ClientStub:
        """Capture client settings without opening a network connection.

        The test inspects the redaction options after construction.
        """

        def __init__(self, **kwargs: object) -> None:
            """Save arguments for policy assertions.

            Args:
                kwargs: Client options supplied by the production factory.
            """
            captured.update(kwargs)

    for name in (
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_WORKSPACE_ID",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(langsmith, "Client", ClientStub)
    settings = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key="test-key",
        langsmith_workspace_id=str(uuid.uuid4()),
    )

    client = langsmith.create_langsmith_client(settings)

    assert isinstance(client, ClientStub)
    assert langsmith.os.environ["LANGSMITH_TRACING"] == "false"
    assert captured["hide_inputs"] is True
    assert captured["hide_outputs"] is True
    assert captured["hide_metadata"] is True
    assert captured["omit_traced_runtime_info"] is True
    anonymizer = captured["anonymizer"]
    assert callable(anonymizer)
    assert anonymizer({"error": "sensitive", "body": "private"}) == {
        "error": "[REDACTED]",
        "body": "[REDACTED]",
    }


def test_trace_check_rejects_any_exported_payload() -> None:
    """Require matching trace runs to contain no input or output data.

    The sentinel check also catches payloads hidden in serialized metadata.
    """
    trace_id = uuid.uuid4()
    sentinel = "SYNTHETIC_REDACTION_SENTINEL"

    class RunStub:
        """Provide the run fields read by the smoke check.

        The serialized payload mirrors the SDK fields relevant to redaction.
        """

        def __init__(
            self,
            inputs: dict[str, Any],
            outputs: dict[str, Any],
        ) -> None:
            """Store synthetic trace payload fields.

            Args:
                inputs: Run input mapping.
                outputs: Run output mapping.
            """
            self.id = trace_id
            self.error = None
            self.inputs = inputs
            self.outputs = outputs

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            """Serialize the fields the verifier scans for the sentinel.

            Args:
                mode: Pydantic serialization mode supplied by the verifier.

            Returns:
                A serialized representation of this stub trace run.
            """
            assert mode == "json"
            return {
                "id": str(self.id),
                "inputs": self.inputs,
                "outputs": self.outputs,
            }

    redacted = RunStub(inputs={}, outputs={})
    leaked = RunStub(inputs={"question": sentinel}, outputs={})

    assert _trace_is_redacted(
        [redacted], root_id=trace_id, sentinel=sentinel
    )
    assert not _trace_is_redacted([leaked], root_id=trace_id, sentinel=sentinel)
