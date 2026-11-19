#!/usr/bin/env bash
set -Eeuo pipefail

uv sync --frozen --no-default-groups --python 3.12 \
  --extra agents \
  --extra providers
