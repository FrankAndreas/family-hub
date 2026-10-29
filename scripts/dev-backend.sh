#!/bin/bash
# Start the backend locally on port 8000 (Vite forwards /api there), with its database in backend/data.
set -euo pipefail
cd "$(dirname "$0")/../backend"
export INITIAL_ADMIN_PIN="${INITIAL_ADMIN_PIN:-1111}"
# Plain http on this machine: a Secure cookie would never come back
export COOKIE_INSECURE="${COOKIE_INSECURE:-1}"
exec ../venv/bin/uvicorn app.main:app --reload "$@"
