"""Render the Streamlit chat and graph activity interface.

The UI keeps the bearer token, selected conversation, and identity in
Streamlit session state. It calls FastAPI through `AssistantApiClient` for
login, session history, and SSE chat updates; roles always come from the API.

The sidebar renders coarse graph activity and validation outcomes. It does
not expose LangGraph's internal state or model chain-of-thought.
"""

import os
from typing import Any

import httpx
import streamlit as st

from apps.ui.services.api_client import AssistantApiClient

st.set_page_config(page_title="Enterprise Knowledge Assistant", layout="wide")
st.title("Enterprise Knowledge Assistant")
st.caption(
    "Deterministic mock mode · synthetic documents · LangGraph activity stream")

base_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
if "access_token" not in st.session_state:
    st.session_state.access_token = ""
if "session_ids" not in st.session_state:
    st.session_state.session_ids = []
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = ""

with st.sidebar:
    st.header("Demo access")
    st.caption(
        "Choose a server-configured demo user; the backend assigns the role.")
    if not st.session_state.access_token:
        username = st.selectbox("User", ["viewer", "analyst", "admin"])
        password = st.text_input("Password", type="password")
        if st.button("Sign in", type="primary"):
            try:
                token = AssistantApiClient(base_url).login(username, password)
                st.session_state.access_token = token
                signed_in_client = AssistantApiClient(base_url, token)
                identity = signed_in_client.get_identity()
                st.session_state.identity = identity
                session = signed_in_client.create_session()
                st.session_state.session_ids = []
                st.session_state.session_ids.append(session["session_id"])
                st.session_state.current_session_id = session["session_id"]
                st.rerun()
            except httpx.HTTPError as exc:
                st.error(f"Sign in failed: {exc}")
    else:
        identity = st.session_state.get("identity", {})
        st.write(f"Signed in as **{identity.get('user_id', 'user')}**")
        st.write(f"Backend role: **{identity.get('role', 'unknown')}**")
        if st.button("Sign out"):
            st.session_state.access_token = ""
            st.session_state.identity = {}
            st.session_state.session_ids = []
            st.session_state.current_session_id = ""
            st.rerun()

        sidebar_client = AssistantApiClient(
            base_url, st.session_state.access_token)
        if st.button("New session"):
            try:
                session = sidebar_client.create_session()
                st.session_state.session_ids.append(session["session_id"])
                st.session_state.current_session_id = session["session_id"]
                st.rerun()
            except httpx.HTTPError as exc:
                st.error(f"Could not create a session: {exc}")

        if st.session_state.session_ids:
            current = st.session_state.current_session_id
            selected = st.selectbox(
                "Conversation session",
                st.session_state.session_ids,
                index=(
                    st.session_state.session_ids.index(current)
                    if current in st.session_state.session_ids
                    else 0
                ),
            )
            st.session_state.current_session_id = selected
            st.caption(f"Session ID: `{selected}`")

st.sidebar.subheader("Agent activity")
st.sidebar.caption(
    "Current graph node, retrieval, tools, validation, and errors.")
activity_placeholder = st.sidebar.empty()
activity_placeholder.info("Activity will appear while a chat turn is running.")

st.subheader("Conversation")
client = (
    AssistantApiClient(base_url, st.session_state.access_token)
    if st.session_state.access_token
    else None
)
history: list[dict[str, Any]] = []
session_id = st.session_state.current_session_id
if client and session_id:
    try:
        history = client.get_session(session_id).get("messages", [])
    except httpx.HTTPError as exc:
        st.warning(f"Could not load session history: {exc}")

for message in history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input(
    "Ask about a payment incident, runbook, policy, or system…",
    disabled=not client or not session_id,
)
if prompt and client and session_id:
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        answer_parts: list[str] = []
        activity: list[str] = []
        current_agent = "Waiting"
        current_node = "-"
        try:
            for event in client.stream_chat(session_id, prompt):
                event_type = event.get("event_type", "")
                agent = event.get("agent") or "system"
                node = event.get("node") or "-"
                current_agent, current_node = agent, node
                event_message = str(event.get("message", ""))
                if event_type == "response_chunk":
                    answer_parts.append(event_message)
                    answer_placeholder.markdown("".join(answer_parts))
                elif event_type == "failure":
                    st.error(event_message)
                if event_type == "retrieval":
                    sources = event.get("metadata", {}).get("sources", [])
                    source_titles = ", ".join(source.get(
                        "title", "source") for source in sources)
                    activity.append(
                        f"**Retrieval:** {len(sources)} source(s) "
                        f"{source_titles}"
                    )
                elif event_type == "tool_execution":
                    tool = event.get("metadata", {}).get("tool", "tool")
                    activity.append(f"**Tool:** {tool} completed")
                elif event_type == "validation":
                    valid = event.get("metadata", {}).get("valid", False)
                    activity.append(
                        f"**Validation:** {'passed' if valid else 'failed'}")
                elif event_type == "agent_transition":
                    activity.append(
                        f"**{agent.title()} · {node}:** {event_message}")
                elif event_type == "failure":
                    activity.append(f"**Error:** {event_message}")
                activity_placeholder.markdown(
                    f"**Current agent/node:** {current_agent} / "
                    f"{current_node}\n\n"
                    + "\n\n".join(activity[-12:])
                )
            if not answer_parts:
                answer_placeholder.info("The stream ended without a response.")
        except httpx.HTTPStatusError as exc:
            detail = (
                exc.response.json()
                .get("error", {})
                .get("message", "Request failed.")
            )
            st.error(detail)
        except httpx.HTTPError as exc:
            st.error(f"Could not reach the assistant API: {exc}")
