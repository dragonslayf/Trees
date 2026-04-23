#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/Trees"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-7000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-4173}"

PYTHON_BIN_DEFAULT="/home/xty/miniconda3/envs/tree_env_new/bin/python"
PYTHON_BIN="${PYTHON_BIN:-$PYTHON_BIN_DEFAULT}"

usage() {
  cat <<'EOF'
Usage:
  ./run.sh api
  ./run.sh build-web
  ./run.sh web

Environment variables:
  API_HOST            FastAPI host (default: 127.0.0.1)
  API_PORT            FastAPI port (default: 7000)
  WEB_HOST            Frontend preview host (default: 127.0.0.1)
  WEB_PORT            Frontend preview port (default: 4173)
  PYTHON_BIN          Python executable for backend
  VITE_API_BASE_URL   Frontend API base URL for build
  CORS_ALLOW_ORIGINS  Comma-separated backend CORS allowlist

Examples:
  CORS_ALLOW_ORIGINS="https://app.example.com" ./run.sh api
  VITE_API_BASE_URL="https://api.example.com" ./run.sh build-web
EOF
}

run_api() {
  echo "Starting FastAPI at http://${API_HOST}:${API_PORT}"
  cd "$BACKEND_DIR"
  exec "$PYTHON_BIN" -m uvicorn fastapi_example:app --host "$API_HOST" --port "$API_PORT"
}

build_web() {
  echo "Building frontend in $FRONTEND_DIR"
  cd "$FRONTEND_DIR"
  npm install
  npm run build
}

run_web() {
  echo "Starting frontend preview at http://${WEB_HOST}:${WEB_PORT}"
  cd "$FRONTEND_DIR"
  exec npm run preview -- --host "$WEB_HOST" --port "$WEB_PORT" --strictPort
}

cmd="${1:-}"
case "$cmd" in
  api)
    run_api
    ;;
  build-web)
    build_web
    ;;
  web)
    run_web
    ;;
  *)
    usage
    exit 1
    ;;
esac
