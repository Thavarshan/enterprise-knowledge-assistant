#!/bin/sh
set -eu

printf 'D1_SERVICE_TOKEN=%s\n' "$D1_SERVICE_TOKEN" > .dev.vars
npx wrangler d1 migrations apply eka-assessment-d1 \
  --local --persist-to /state
exec npx wrangler dev --local --persist-to /state \
  --ip 0.0.0.0 --port 8787
