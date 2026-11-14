import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";

import worker, { type Env } from "../src/index";

const serviceToken = "test-service-token-not-a-secret-00000000";
const workerEnv = env as unknown as Env;

function request(
  path: string,
  token: string,
  owner = "analyst",
  body?: Record<string, unknown>,
): Request {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (owner) headers.set("X-Owner-ID", owner);
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  return new Request(`https://worker.test${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

describe("D1 gateway unit behavior", () => {
  it("exposes liveness and the running release SHA without auth", async () => {
    const response = await worker.fetch(
      request("/health", "", ""),
      workerEnv,
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      release_sha: "local",
    });
  });

  it("rejects missing and invalid service tokens", async () => {
    const missing = await worker.fetch(
      request("/internal/ready", ""),
      workerEnv,
    );
    const invalid = await worker.fetch(
      request("/internal/ready", "invalid-token"),
      workerEnv,
    );

    expect(missing.status).toBe(401);
    expect(invalid.status).toBe(401);
  });

  it("rejects invalid owners before accessing session storage", async () => {
    const response = await worker.fetch(
      request("/v1/sessions", serviceToken, "invalid owner", {}),
      workerEnv,
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid_owner" });
  });
});
