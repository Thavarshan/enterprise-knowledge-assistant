"""Verify login, chat streaming, activity, D1 persistence, and ownership.

The browser smoke sends one explicitly authorized synthetic live prompt and
checks its stored history through a separate authenticated API request.
"""

import os
import re
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from scripts.deployment.smoke_http import (
    SmokeCheckError,
    https_origin,
    request_json,
    write_summary,
)
from scripts.deployment.smoke_vercel import _login

SESSION_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
CHAT_PROMPT = "What does the payment gateway timeout runbook say?"
CHAT_PLACEHOLDER = "Ask about a payment incident, runbook, policy, or system…"


def _session_id_from_page(page: object) -> str:
    """Find the active session UUID rendered in the Streamlit sidebar.

    Args:
        page: Playwright page after successful login.

    Returns:
        Session ID visible in the UI.

    Raises:
        SmokeCheckError: No valid session ID appears after authentication.
    """
    codes = page.locator("code")
    for index in range(codes.count()):
        value = codes.nth(index).inner_text().strip()
        if SESSION_ID_PATTERN.fullmatch(value):
            return value
    raise SmokeCheckError("The signed-in UI did not show a conversation ID.")


def run_smoke() -> None:
    """Complete one live synthetic conversation through the browser UI.

    The workflow must explicitly enable one bounded live model-backed turn.
    The test uses a synthetic Analyst and Viewer, then reads persisted
    history through a separate API request and checks owner isolation.

    Raises:
        SmokeCheckError: A UI, API, model, or persistence check fails.
    """
    ui_origin = https_origin(
        os.environ.get("STREAMLIT_URL", ""),
        "STREAMLIT_URL",
    )
    api_origin = https_origin(
        os.environ.get("VERCEL_PRODUCTION_URL", ""),
        "VERCEL_PRODUCTION_URL",
    )
    expected_sha = os.environ.get("RELEASE_SHA", "").lower()
    analyst_password = os.environ.get("SMOKE_ANALYST_PASSWORD", "")
    viewer_password = os.environ.get("SMOKE_VIEWER_PASSWORD", "")
    if not expected_sha or not analyst_password or not viewer_password:
        raise SmokeCheckError(
            "Release metadata or synthetic credentials missing."
        )

    analyst_token = ""
    session_id = ""
    answer = ""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            response = page.goto(
                ui_origin,
                wait_until="domcontentloaded",
                timeout=90_000,
            )
            if response is None or response.status >= 400:
                raise SmokeCheckError("Streamlit did not return a page.")
            page.get_by_text(
                f"Application release: {expected_sha}",
                exact=True,
            ).wait_for(timeout=90_000)
            user_picker = page.get_by_role("combobox").first
            user_picker.click()
            page.get_by_role(
                "option",
                name="analyst",
                exact=True,
            ).click()
            page.get_by_label("Password").fill(analyst_password)
            page.get_by_role("button", name="Sign in").click()
            page.get_by_text("Backend role: analyst").wait_for(
                timeout=30_000
            )
            session_id = _session_id_from_page(page)
            chat_input = page.get_by_placeholder(CHAT_PLACEHOLDER)
            chat_input.fill(CHAT_PROMPT)
            chat_input.press("Enter")
            page.get_by_text("Validation: passed").wait_for(timeout=65_000)
            page.get_by_text("Current agent/node:").wait_for(timeout=10_000)
            messages = page.locator('[data-testid="stChatMessage"]')
            if messages.count() < 2:
                raise SmokeCheckError(
                    "The UI did not render an assistant reply."
                )
            answer = messages.nth(messages.count() - 1).inner_text().strip()
            if len(answer) < 20 or "could not complete" in answer.lower():
                raise SmokeCheckError(
                    "The UI displayed no usable assistant reply."
                )
            expected_citation = (
                "doc-runbook-gateway-timeout#"
                "doc-runbook-gateway-timeout-001"
            )
            if (
                expected_citation not in answer
                or "regional" not in answer.lower()
                or "idempotency" not in answer.lower()
            ):
                raise SmokeCheckError(
                    "The live reply did not cite the expected runbook "
                    "evidence."
                )
            browser.close()
    except PlaywrightTimeoutError as exc:
        raise SmokeCheckError(
            "The Streamlit login, chat, or activity display timed out."
        ) from exc

    _, version = request_json(f"{api_origin}/version")
    _, ready = request_json(f"{api_origin}/ready")
    if version.get("release_sha") != expected_sha:
        raise SmokeCheckError("The production API serves a different SHA.")
    if version.get("mode") != "live" or ready.get("status") != "ready":
        raise SmokeCheckError("The production API is not live and ready.")

    analyst_token = _login(api_origin, "analyst", analyst_password)
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    _, history = request_json(
        f"{api_origin}/api/v1/chat/sessions/{session_id}",
        headers=analyst_headers,
    )
    messages = history.get("messages", [])
    if not any(
        item.get("role") == "user" and item.get("content") == CHAT_PROMPT
        for item in messages
    ):
        raise SmokeCheckError("The user turn was not persisted in D1 history.")
    if not any(
        item.get("role") == "assistant"
        and isinstance(item.get("content"), str)
        and len(item["content"].strip()) >= 20
        for item in messages
    ):
        raise SmokeCheckError(
            "A usable assistant answer was not persisted in D1."
        )

    viewer_token = _login(api_origin, "viewer", viewer_password)
    _, denied = request_json(
        f"{api_origin}/api/v1/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
        expected_status=404,
    )
    if denied.get("detail") != "Session not found.":
        raise SmokeCheckError(
            "Another user could access the smoke conversation."
        )

    write_summary(
        "Full-stack end-to-end",
        [
            f"Release: {expected_sha}",
            f"Streamlit: {ui_origin}",
            f"Vercel API: {api_origin}",
            "Analyst login, one live chat turn, and activity display passed.",
            "Conversation history persisted through D1 across API requests.",
            "Viewer access to the Analyst session was denied.",
        ],
    )
    print("Full-stack login, chat, activity, D1, and RBAC smoke passed.")


def main() -> int:
    """Run one bounded live end-to-end deployment smoke test.

    Returns:
        Zero only after browser, API, persistence, and RBAC checks pass.
    """
    try:
        run_smoke()
    except SmokeCheckError as exc:
        write_summary("Full-stack end-to-end FAILED", [str(exc)])
        print(f"Full-stack smoke failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
