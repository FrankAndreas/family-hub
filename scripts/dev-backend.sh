#!/bin/bash
# Start the backend locally on port 8000 (Vite forwards /api there), with its database in backend/data.
set -euo pipefail
cd "$(dirname "$0")/../backend"
export INITIAL_ADMIN_PIN="${INITIAL_ADMIN_PIN:-1111}"
exec ../venv/bin/uvicorn app.main:app --reload "$@"
