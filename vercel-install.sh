#!/usr/bin/env bash
set -Eeuo pipefail

uv sync --frozen --no-default-groups \
  --extra agents \
  --extra providers
