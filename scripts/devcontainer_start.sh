#!/bin/sh
set -eu

exec streamlit run apps/ui/main.py \
    --server.enableCORS false \
    --server.enableXsrfProtection false
