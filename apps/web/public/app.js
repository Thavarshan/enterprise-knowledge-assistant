const state = {
  token: "",
  identity: null,
  sessions: [],
  currentSessionId: "",
  busy: false,
};

const elements = Object.fromEntries(
  [
    "runtime-status",
    "signout-button",
    "login-panel",
    "login-form",
    "login-error",
    "username",
    "password",
    "account-panel",
    "new-session-button",
    "session-list",
    "account-avatar",
    "account-name",
    "account-role",
    "welcome-panel",
    "conversation-panel",
    "conversation-title",
    "model-badge",
    "transcript",
    "activity-list",
    "release-sha",
    "prompt-form",
    "prompt-input",
    "global-error",
  ].map((id) => [id.replaceAll("-", "_"), document.getElementById(id)]),
);

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const payload = await response.json();
      message = payload.detail?.message
        || payload.detail
        || payload.error?.message
        || message;
    } catch {
      // Keep the status-only message when the API response is not JSON.
    }
    const errorMessage = typeof message === "string"
      ? message
      : `Request failed (${response.status}).`;
    throw new Error(errorMessage);
  }
  if (response.status === 204) return null;
  return response.json();
}

function setError(element, message) {
  element.textContent = message;
  element.hidden = !message;
}

function setSignedIn(signedIn) {
  elements.login_panel.hidden = signedIn;
  elements.account_panel.hidden = !signedIn;
  elements.signout_button.hidden = !signedIn;
  elements.welcome_panel.hidden = signedIn;
  elements.conversation_panel.hidden = !signedIn;
}

function renderAccount() {
  const identity = state.identity || {};
  elements.account_name.textContent = identity.user_id || "Signed in";
  elements.account_role.textContent = identity.role || "Role";
  elements.account_avatar.textContent = (identity.user_id || "V")
    .slice(0, 1)
    .toUpperCase();
}

function renderSessions() {
  elements.session_list.replaceChildren();
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.className = "session-item";
    button.type = "button";
    button.classList.toggle(
      "active",
      session.session_id === state.currentSessionId,
    );
    button.title = session.title || "Conversation";

    const marker = document.createElement("span");
    marker.className = "session-marker";
    marker.setAttribute("aria-hidden", "true");
    const copy = document.createElement("span");
    copy.className = "session-copy";
    const title = document.createElement("strong");
    title.textContent = session.title || "New conversation";
    const date = document.createElement("small");
    date.textContent = formatDate(session.created_at);
    copy.append(title, date);
    button.append(marker, copy);
    button.addEventListener("click", () => selectSession(session.session_id));
    elements.session_list.append(button);
  }
  const current = state.sessions.find(
    (item) => item.session_id === state.currentSessionId,
  );
  elements.conversation_title.textContent =
    current?.title || "New conversation";
}

function formatDate(value) {
  if (!value) return "Conversation";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "Conversation"
    : date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });
}

function appendMessage(role, content, { pending = false } = {}) {
  const article = document.createElement("article");
  article.className = `message message-${role}`;
  if (pending) article.classList.add("message-pending");
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user"
    ? (state.identity?.user_id || "U").slice(0, 1).toUpperCase()
    : "V";
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user"
    ? state.identity?.user_id || "You"
    : "Viridian";
  const text = document.createElement("div");
  text.className = "message-content";
  text.textContent = content;
  body.append(label, text);
  article.append(avatar, body);
  elements.transcript.append(article);
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
  return text;
}

function appendActivity(event) {
  const empty = elements.activity_list.querySelector(".activity-empty");
  if (empty) empty.remove();
  const item = document.createElement("div");
  item.className = "activity-item";
  const point = document.createElement("span");
  point.className = "activity-point";
  point.setAttribute("aria-hidden", "true");
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = [event.agent, event.node]
    .filter(Boolean)
    .join(" · ") || "Agent";
  const detail = document.createElement("span");
  detail.textContent = event.message || event.event_type || "Working";
  copy.append(title, detail);
  item.append(point, copy);
  elements.activity_list.prepend(item);
  while (elements.activity_list.children.length > 12) {
    elements.activity_list.lastElementChild.remove();
  }
}

async function loadSessions() {
  state.sessions = await request("/api/v1/chat/sessions");
  if (!state.sessions.some(
    (item) => item.session_id === state.currentSessionId,
  )) {
    state.currentSessionId = state.sessions[0]?.session_id || "";
  }
  renderSessions();
  if (!state.currentSessionId) await createSession();
  else await loadHistory(state.currentSessionId);
}

async function createSession() {
  const session = await request("/api/v1/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title: "New conversation" }),
  });
  state.sessions.unshift(session);
  state.currentSessionId = session.session_id;
  renderSessions();
  renderHistory([]);
}

async function selectSession(sessionId) {
  if (state.busy || sessionId === state.currentSessionId) return;
  state.currentSessionId = sessionId;
  renderSessions();
  await loadHistory(sessionId);
}

async function loadHistory(sessionId) {
  try {
    const session = await request(
      `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`,
    );
    renderHistory(session.messages || []);
  } catch (error) {
    showGlobalError(error.message);
  }
}

function renderHistory(messages) {
  elements.transcript.replaceChildren();
  for (const message of messages) appendMessage(message.role, message.content);
  if (!messages.length) {
    const hint = document.createElement("div");
    hint.className = "empty-conversation";
    hint.innerHTML = [
      '<span class="empty-icon">✦</span>',
      "<strong>Start with a question</strong>",
      "<span>Try asking what caused a payment incident or how a runbook "
        + "handles retries.</span>",
    ].join("");
    elements.transcript.append(hint);
  }
}

async function signIn(event) {
  event.preventDefault();
  setError(elements.login_error, "");
  const button = elements.login_form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Signing in…";
  try {
    const payload = await request("/api/v1/auth/token", {
      method: "POST",
      body: JSON.stringify({
        username: elements.username.value,
        password: elements.password.value,
      }),
    });
    state.token = payload.access_token;
    state.identity = await request("/api/v1/me");
    setSignedIn(true);
    renderAccount();
    await loadSessions();
    elements.password.value = "";
  } catch (error) {
    state.token = "";
    state.identity = null;
    setError(
      elements.login_error,
      "Sign-in failed. Check the account and password, then retry.",
    );
  } finally {
    button.disabled = false;
    button.innerHTML = 'Sign in <span aria-hidden="true">→</span>';
  }
}

function signOut() {
  state.token = "";
  state.identity = null;
  state.sessions = [];
  state.currentSessionId = "";
  elements.password.value = "";
  elements.session_list.replaceChildren();
  elements.transcript.replaceChildren();
  elements.activity_list.innerHTML =
    '<p class="activity-empty">Activity appears here as Viridian works.</p>';
  setSignedIn(false);
  setError(elements.global_error, "");
}

async function streamChat(event) {
  event.preventDefault();
  const message = elements.prompt_input.value.trim();
  if (!message || !state.currentSessionId || state.busy) return;
  elements.prompt_input.value = "";
  elements.prompt_input.style.height = "auto";
  elements.activity_list.replaceChildren();
  appendMessage("user", message);
  const answer = appendMessage("assistant", "");
  state.busy = true;
  setComposerBusy(true);
  try {
    const response = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${state.token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ session_id: state.currentSessionId, message }),
      cache: "no-store",
    });
    if (!response.ok || !response.body) {
      throw new Error(`Chat failed (${response.status}).`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || "";
      for (const frame of frames) handleFrame(frame, answer);
      if (done) break;
    }
    if (buffer.trim()) handleFrame(buffer, answer);
    await loadSessions();
  } catch (error) {
    appendActivity({
      agent: "System",
      node: "Connection",
      message: "The assistant could not complete this turn.",
    });
    if (!answer.textContent) {
      answer.textContent =
        "I couldn't complete that request. Please try again.";
    }
  } finally {
    state.busy = false;
    setComposerBusy(false);
    elements.transcript.scrollTop = elements.transcript.scrollHeight;
  }
}

function handleFrame(frame, answer) {
  for (const line of frame.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const data = line.slice(5).trim();
    if (!data) continue;
    try {
      const event = JSON.parse(data);
      if (event.event_type === "response_chunk") {
        answer.textContent += event.message || "";
        elements.transcript.scrollTop = elements.transcript.scrollHeight;
      } else {
        appendActivity(event);
      }
    } catch {
      appendActivity({
        agent: "System",
        node: "Stream",
        message: "Received an unreadable activity event.",
      });
    }
  }
}

function setComposerBusy(busy) {
  elements.prompt_input.disabled = busy;
  elements.prompt_form.querySelector("button[type=submit]").disabled =
    busy;
  elements.prompt_form.classList.toggle("is-busy", busy);
}

function showGlobalError(message) {
  elements.global_error.textContent = message;
  elements.global_error.hidden = !message;
}

async function loadRuntimeInfo() {
  try {
    const [health, version] = await Promise.all([
      request("/health"),
      request("/version"),
    ]);
    elements.runtime_status.textContent = health.status === "ok"
      ? "Cloudflare edge · online"
      : "Service unavailable";
    elements.runtime_status.classList.add("is-online");
    elements.release_sha.textContent = version.release_sha === "unknown"
      ? "local"
      : version.release_sha.slice(0, 12);
    elements.model_badge.textContent = version.mode === "mock"
      ? "Free demo mode"
      : `${version.provider} · ${version.model}`;
  } catch {
    elements.runtime_status.textContent = "Waiting for API";
    elements.runtime_status.classList.remove("is-online");
    elements.release_sha.textContent = "—";
  }
}

elements.login_form.addEventListener("submit", signIn);
elements.signout_button.addEventListener("click", signOut);
elements.new_session_button.addEventListener("click", async () => {
  try {
    await createSession();
  } catch (error) {
    showGlobalError(error.message);
  }
});
elements.prompt_form.addEventListener("submit", streamChat);
elements.prompt_input.addEventListener("input", () => {
  elements.prompt_input.style.height = "auto";
  elements.prompt_input.style.height = `${Math.min(
    elements.prompt_input.scrollHeight,
    180,
  )}px`;
});
elements.prompt_input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.prompt_form.requestSubmit();
  }
});

setSignedIn(false);
loadRuntimeInfo();
