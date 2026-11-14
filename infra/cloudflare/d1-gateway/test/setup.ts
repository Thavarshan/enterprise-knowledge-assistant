import {
  applyD1Migrations,
  env,
  type D1Migration,
} from "cloudflare:test";
import { beforeAll, beforeEach } from "vitest";

import type { Env } from "../src/index";

interface TestBindings {
  DB: Env["DB"];
  TEST_MIGRATIONS: D1Migration[];
}

const testEnv = env as unknown as TestBindings;

beforeAll(async () => {
  await applyD1Migrations(testEnv.DB, testEnv.TEST_MIGRATIONS);
});

beforeEach(async () => {
  await testEnv.DB.exec("DELETE FROM messages; DELETE FROM sessions;");
});
