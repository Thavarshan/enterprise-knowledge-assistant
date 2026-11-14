/** Serve authenticated, owner-scoped conversation persistence routes. */

export interface Env {
  DB: D1Database;
  D1_SERVICE_TOKEN: string;
  APP_RELEASE_SHA: string;
}

interface SessionRow {
  session_id: string;
  owner_id: string;
  title: string;
  created_at: string;
}

interface MessageRow {
  message_id: number;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

const MAX_BODY_BYTES = 48_000;
const MAX_MESSAGE_LENGTH = 40_000;
const MAX_HISTORY = 1_000;
const SESSION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const OWNER_ID_PATTERN = /^[A-Za-z0-9._@+-]{1,128}$/;
const encoder = new TextEncoder();

function jsonResponse(
  body: object,
  status = 200,
): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

async function constantTimeTokenMatch(
  supplied: string,
  expected: string,
): Promise<boolean> {
  if (!expected || supplied.length > 512) return false;
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(supplied)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const actual = new Uint8Array(left);
  const wanted = new Uint8Array(right);
  let difference = 0;
  for (let index = 0; index < actual.length; index += 1) {
    difference |= actual[index] ^ wanted[index];
  }
  return difference === 0;
}

async function isAuthorized(
  request: Request,
  env: Env,
): Promise<boolean> {
  const authorization = request.headers.get("Authorization") ?? "";
  const match = /^Bearer ([^\s]+)$/.exec(authorization);
  return match !== null && constantTimeTokenMatch(
    match[1],
    env.D1_SERVICE_TOKEN,
  );
}

function getOwner(request: Request): string | null {
  const ownerId = request.headers.get("X-Owner-ID") ?? "";
  return OWNER_ID_PATTERN.test(ownerId) ? ownerId : null;
}

async function readJson(
  request: Request,
): Promise<Record<string, unknown> | null> {
  const contentLength = Number(request.headers.get("Content-Length") ?? 0);
  if (contentLength > MAX_BODY_BYTES || !request.body) return null;

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    totalBytes += value.byteLength;
    if (totalBytes > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    const value: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  } catch {
    return null;
  }
}

function hasOnlyKeys(
  value: Record<string, unknown>,
  expected: string[],
): boolean {
  return Object.keys(value).every((key) => expected.includes(key));
}

function validSessionId(sessionId: string): boolean {
  return SESSION_ID_PATTERN.test(sessionId);
}

async function ready(env: Env): Promise<Response> {
  const result = await env.DB.prepare(
    "SELECT COUNT(*) AS table_count FROM sqlite_schema " +
      "WHERE type = 'table' AND name IN ('sessions', 'messages')",
  ).first<{ table_count: number }>();
  if (result?.table_count !== 2) {
    return jsonResponse({ error: "database_not_ready" }, 503);
  }
  return jsonResponse({ status: "ready" });
}

async function createSession(
  request: Request,
  env: Env,
  ownerId: string,
): Promise<Response> {
  const body = await readJson(request);
  if (
    !body ||
    !hasOnlyKeys(body, ["title"]) ||
    (body.title !== undefined &&
      (typeof body.title !== "string" || body.title.length > 120))
  ) {
    return jsonResponse({ error: "invalid_payload" }, 400);
  }
  const session: SessionRow = {
    session_id: crypto.randomUUID(),
    owner_id: ownerId,
    title: typeof body.title === "string" && body.title.trim()
      ? body.title.trim()
      : "New conversation",
    created_at: new Date().toISOString(),
  };
  await env.DB.prepare(
    "INSERT INTO sessions(session_id, owner_id, title, created_at) " +
      "VALUES (?, ?, ?, ?)",
  ).bind(
    session.session_id,
    session.owner_id,
    session.title,
    session.created_at,
  ).run();
  return jsonResponse(session, 201);
}

async function getSession(
  sessionId: string,
  ownerId: string,
  env: Env,
): Promise<Response> {
  const session = await env.DB.prepare(
    "SELECT session_id, owner_id, title, created_at FROM sessions " +
      "WHERE session_id = ? AND owner_id = ?",
  ).bind(sessionId, ownerId).first<SessionRow>();
  return session
    ? jsonResponse(session)
    : jsonResponse({ error: "not_found" }, 404);
}

async function listMessages(
  sessionId: string,
  ownerId: string,
  env: Env,
): Promise<Response> {
  const session = await env.DB.prepare(
    "SELECT 1 FROM sessions WHERE session_id = ? AND owner_id = ?",
  ).bind(sessionId, ownerId).first();
  if (!session) return jsonResponse({ error: "not_found" }, 404);

  const result = await env.DB.prepare(
    "SELECT m.message_id, m.session_id, m.role, m.content, m.created_at " +
      "FROM messages AS m JOIN sessions AS s " +
      "ON s.session_id = m.session_id " +
      "WHERE s.session_id = ? AND s.owner_id = ? " +
      "ORDER BY m.message_id DESC LIMIT ?",
  ).bind(sessionId, ownerId, MAX_HISTORY).all<MessageRow>();
  if (!result.success) {
    return jsonResponse({ error: "storage_unavailable" }, 503);
  }
  return jsonResponse({ messages: result.results.reverse() });
}

async function appendMessage(
  request: Request,
  sessionId: string,
  ownerId: string,
  env: Env,
): Promise<Response> {
  const body = await readJson(request);
  if (
    !body ||
    !hasOnlyKeys(body, ["role", "content"]) ||
    (body.role !== "user" && body.role !== "assistant") ||
    typeof body.content !== "string" ||
    body.content.length > MAX_MESSAGE_LENGTH
  ) {
    return jsonResponse({ error: "invalid_payload" }, 400);
  }
  const createdAt = new Date().toISOString();
  const message = await env.DB.prepare(
    "INSERT INTO messages(session_id, role, content, created_at) " +
      "SELECT ?, ?, ?, ? FROM sessions " +
      "WHERE session_id = ? AND owner_id = ? " +
      "RETURNING message_id, session_id, role, content, created_at",
  ).bind(
    sessionId,
    body.role,
    body.content,
    createdAt,
    sessionId,
    ownerId,
  ).first<MessageRow>();
  return message
    ? jsonResponse(message, 201)
    : jsonResponse({ error: "not_found" }, 404);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (url.pathname === "/health" && request.method === "GET") {
        return jsonResponse({
          status: "ok",
          release_sha: env.APP_RELEASE_SHA,
        });
      }
      if (!(await isAuthorized(request, env))) {
        return jsonResponse({ error: "unauthorized" }, 401);
      }
      if (url.pathname === "/internal/ready" && request.method === "GET") {
        return await ready(env);
      }
      const ownerId = getOwner(request);
      if (!ownerId) {
        return jsonResponse({ error: "invalid_owner" }, 400);
      }
      if (url.pathname === "/v1/sessions" && request.method === "POST") {
        return await createSession(request, env, ownerId);
      }
      const match = /^\/v1\/sessions\/([^/]+)(?:\/(messages))?$/.exec(
        url.pathname,
      );
      if (!match || !validSessionId(match[1])) {
        return jsonResponse({ error: "not_found" }, 404);
      }
      const sessionId = match[1];
      if (match[2] === "messages" && request.method === "GET") {
        return await listMessages(sessionId, ownerId, env);
      }
      if (match[2] === "messages" && request.method === "POST") {
        return await appendMessage(request, sessionId, ownerId, env);
      }
      if (!match[2] && request.method === "GET") {
        return await getSession(sessionId, ownerId, env);
      }
      return jsonResponse({ error: "not_found" }, 404);
    } catch {
      return jsonResponse({ error: "storage_unavailable" }, 503);
    }
  },
};
