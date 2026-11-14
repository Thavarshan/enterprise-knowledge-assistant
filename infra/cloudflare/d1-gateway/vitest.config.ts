import { fileURLToPath } from "node:url";
import path from "node:path";

import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

const root = path.dirname(fileURLToPath(import.meta.url));
process.env.D1_SERVICE_TOKEN =
  "test-service-token-not-a-secret-00000000";
const migrations = await readD1Migrations(
  path.join(root, "migrations"),
);

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: path.join(root, "wrangler.jsonc") },
      miniflare: {
        bindings: {
          D1_SERVICE_TOKEN: "test-service-token-not-a-secret-00000000",
          TEST_MIGRATIONS: migrations,
        },
      },
    }),
  ],
  test: {
    include: ["test/**/*.test.ts"],
    setupFiles: ["./test/setup.ts"],
  },
});
