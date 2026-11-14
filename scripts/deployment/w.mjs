import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const modules = {
  config: "scripts.deployment.render_wrangler_config",
  list: "scripts.deployment.list_remote_migrations",
  migrate: "scripts.deployment.apply_remote_migrations",
  deploy: "scripts.deployment.deploy_cloudflare",
};
const moduleName = modules[process.argv[2]];

if (!moduleName) {
  console.error("Choose config, list, migrate, or deploy.");
  process.exit(2);
}

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const result = spawnSync(
  "python3",
  ["-m", moduleName],
  { cwd: repositoryRoot, stdio: "inherit" },
);

if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
