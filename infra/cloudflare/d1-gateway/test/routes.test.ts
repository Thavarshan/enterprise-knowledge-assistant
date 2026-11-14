import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";

import worker, { type Env } from "../src/index";

const serviceToken = "test-service-token-not-a-secret-00000000";
const ownerId = "analyst";
const workerEnv = env as unknown as Env;

function request(
  path: string,
  options: {
    method?: string;
    owner?: string;
    token?: string;
    body?: Record<string, unknown>;
  } = {},
): Request {
  const headers = new Headers();
  if (options.token !== "") {
    headers.set(
      "Authorization",
      `Bearer ${options.token ?? serviceToken}`,
    );
  }
  if (options.owner !== "") {
    headers.set("X-Owner-ID", options.owner ?? ownerId);
  }
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  return new Request(`https://worker.test${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined
      ? undefined
      : JSON.stringify(options.body),
  });
}

describe("D1 gateway", () => {
  it("requires its service credential before storage routes", async () => {
    const missing = await worker.fetch(
      request("/internal/ready", { token: "" }),
      workerEnv,
    );
    const wrong = await worker.fetch(
      request("/v1/sessions", {
        method: "POST",
        token: "incorrect-token",
        body: {},
      }),
      workerEnv,
    );

    expect(missing.status).toBe(401);
    expect(wrong.status).toBe(401);
    expect(await missing.json()).toEqual({ error: "unauthorized" });
  });

  it("creates sessions and scopes reads and writes to the owner", async () => {
    const created = await worker.fetch(
      request("/v1/sessions", {
        method: "POST",
        body: { title: "Payment incidents" },
      }),
      workerEnv,
    );
    const session = await created.json() as {
      session_id: string;
      owner_id: string;
    };
    const messageResponse = await worker.fetch(
      request(`/v1/sessions/${session.session_id}/messages`, {
        method: "POST",
        body: { role: "user", content: "What happened?" },
      }),
      workerEnv,
    );
    const foreignRead = await worker.fetch(
      request(`/v1/sessions/${session.session_id}`, { owner: "viewer" }),
      workerEnv,
    );
    const foreignHistory = await worker.fetch(
      request(`/v1/sessions/${session.session_id}/messages`, {
        owner: "viewer",
      }),
      workerEnv,
    );
    const foreignWrite = await worker.fetch(
      request(`/v1/sessions/${session.session_id}/messages`, {
        method: "POST",
        owner: "viewer",
        body: { role: "assistant", content: "forged" },
      }),
      workerEnv,
    );
    const owned = await worker.fetch(
      request(`/v1/sessions/${session.session_id}/messages`),
      workerEnv,
    );

    expect(created.status).toBe(201);
    expect(session.owner_id).toBe(ownerId);
    expect(messageResponse.status).toBe(201);
    expect(foreignRead.status).toBe(404);
    expect(foreignHistory.status).toBe(404);
    expect(foreignWrite.status).toBe(404);
    expect(await owned.json()).toMatchObject({
      messages: [{ role: "user", content: "What happened?" }],
    });
  });

  it("returns messages in persistence order", async () => {
    const created = await worker.fetch(
      request("/v1/sessions", { method: "POST", body: {} }),
      workerEnv,
    );
    const session = await created.json() as { session_id: string };
    for (const content of ["first", "second", "third"]) {
      await worker.fetch(
        request(`/v1/sessions/${session.session_id}/messages`, {
          method: "POST",
          body: { role: "user", content },
        }),
        workerEnv,
      );
    }
    const response = await worker.fetch(
      request(`/v1/sessions/${session.session_id}/messages`),
      workerEnv,
    );
    const body = await response.json() as {
      messages: { content: string }[];
    };

    expect(body.messages.map((message) => message.content)).toEqual([
      "first",
      "second",
      "third",
    ]);
  });

  it("rejects malformed data and keeps SQL-looking text inert", async () => {
    const extraField = await worker.fetch(
      request("/v1/sessions", {
        method: "POST",
        body: { title: "ok", owner_id: "viewer" },
      }),
      workerEnv,
    );
    const invalidId = await worker.fetch(
      request("/v1/sessions/not-a-uuid"),
      workerEnv,
    );
    const created = await worker.fetch(
      request("/v1/sessions", {
        method: "POST",
        body: { title: "'); DROP TABLE sessions;--" },
      }),
      workerEnv,
    );
    const ready = await worker.fetch(
      request("/internal/ready"),
      workerEnv,
    );

    expect(extraField.status).toBe(400);
    expect(invalidId.status).toBe(404);
    expect(created.status).toBe(201);
    expect(ready.status).toBe(200);
  });

  it(
    "requires a valid role, bounded text, and an owner identifier",
    async () => {
      const created = await worker.fetch(
        request("/v1/sessions", { method: "POST", body: {} }),
        workerEnv,
      );
      const session = await created.json() as { session_id: string };
      const invalidRole = await worker.fetch(
        request(`/v1/sessions/${session.session_id}/messages`, {
          method: "POST",
          body: { role: "admin", content: "hello" },
        }),
        workerEnv,
      );
      const tooLong = await worker.fetch(
        request(`/v1/sessions/${session.session_id}/messages`, {
          method: "POST",
          body: { role: "user", content: "x".repeat(40_001) },
        }),
        workerEnv,
      );
      const invalidOwner = await worker.fetch(
        request("/v1/sessions", {
          method: "POST",
          owner: "invalid owner / !",
          body: {},
        }),
        workerEnv,
      );

      expect(invalidRole.status).toBe(400);
      expect(tooLong.status).toBe(400);
      expect(invalidOwner.status).toBe(400);
    },
  );
});
