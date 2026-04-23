#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/.run-logs"
mkdir -p "$LOG_DIR"

# Domain defaults for current deployment
APP_DOMAIN="${APP_DOMAIN:-hugetreesegmentation.click}"
API_DOMAIN="${API_DOMAIN:-api.hugetreesegmentation.click}"
TUNNEL_NAME="${TUNNEL_NAME:-trees}"
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-https://${APP_DOMAIN},http://${APP_DOMAIN},https://www.${APP_DOMAIN},http://www.${APP_DOMAIN}}"
SESSION_COOKIE_SAMESITE="${SESSION_COOKIE_SAMESITE:-none}"
SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-true}"
# 允许主域及子域共享 Cookie（用于 https://hugetreesegmentation.click 与 https://api.hugetreesegmentation.click）
SESSION_COOKIE_DOMAIN="${SESSION_COOKIE_DOMAIN:-.${APP_DOMAIN#www.}}"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-7000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-4173}"

API_LOG="$LOG_DIR/api.log"
WEB_LOG="$LOG_DIR/web.log"
TUNNEL_LOG="$LOG_DIR/tunnel.log"

port_in_use() {
  local host="$1"
  local port="$2"
  ss -ltn | rg -q "(${host}:${port}|0.0.0.0:${port}|\\[::\\]:${port})"
}

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "ERROR: cloudflared not found in PATH."
  echo "Install cloudflared first, then run again."
  exit 1
fi

if port_in_use "$API_HOST" "$API_PORT"; then
  echo "ERROR: API port ${API_HOST}:${API_PORT} is already in use."
  echo "Stop old process first, then re-run start-all.sh."
  exit 1
fi

if port_in_use "$WEB_HOST" "$WEB_PORT"; then
  echo "ERROR: Web port ${WEB_HOST}:${WEB_PORT} is already in use."
  echo "Stop old process first, then re-run start-all.sh."
  exit 1
fi

cleanup() {
  local code="$?"
  echo
  echo "Stopping services..."
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" >/dev/null 2>&1 || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" >/dev/null 2>&1 || true
  [[ -n "${TUNNEL_PID:-}" ]] && kill "$TUNNEL_PID" >/dev/null 2>&1 || true
  wait >/dev/null 2>&1 || true
  echo "Stopped."
  exit "$code"
}
trap cleanup INT TERM EXIT

echo "Building frontend with VITE_API_BASE_URL=https://${API_DOMAIN}"
(
  cd "$ROOT_DIR"
  VITE_API_BASE_URL="https://${API_DOMAIN}" bash ./run.sh build-web
) | tee "$LOG_DIR/build.log"

echo "Starting API on http://${API_HOST}:${API_PORT}"
(
  cd "$ROOT_DIR"
  CORS_ALLOW_ORIGINS="$CORS_ALLOW_ORIGINS" \
    SESSION_COOKIE_SAMESITE="$SESSION_COOKIE_SAMESITE" \
    SESSION_COOKIE_SECURE="$SESSION_COOKIE_SECURE" \
    SESSION_COOKIE_DOMAIN="$SESSION_COOKIE_DOMAIN" \
    API_HOST="$API_HOST" \
    API_PORT="$API_PORT" \
    bash ./run.sh api
) >"$API_LOG" 2>&1 &
API_PID="$!"

echo "Starting Web on http://${WEB_HOST}:${WEB_PORT}"
(
  cd "$ROOT_DIR"
  WEB_HOST="$WEB_HOST" \
    WEB_PORT="$WEB_PORT" \
    bash ./run.sh web
) >"$WEB_LOG" 2>&1 &
WEB_PID="$!"

echo "Starting Cloudflare Tunnel: ${TUNNEL_NAME}"
cloudflared tunnel run "$TUNNEL_NAME" >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID="$!"

sleep 2
if ! kill -0 "$API_PID" >/dev/null 2>&1; then
  echo "ERROR: API failed to start. See $API_LOG"
  exit 1
fi
if ! kill -0 "$WEB_PID" >/dev/null 2>&1; then
  echo "ERROR: Web failed to start. See $WEB_LOG"
  exit 1
fi
if ! kill -0 "$TUNNEL_PID" >/dev/null 2>&1; then
  echo "ERROR: Tunnel failed to start. See $TUNNEL_LOG"
  exit 1
fi

echo
echo "All services are running:"
echo "  App URL: https://${APP_DOMAIN}"
echo "  API URL: https://${API_DOMAIN}"
echo "  API log: $API_LOG"
echo "  Web log: $WEB_LOG"
echo "  Tunnel log: $TUNNEL_LOG"
echo
echo "Press Ctrl+C to stop all services."

# Keep script in foreground while any child is alive
wait -n "$API_PID" "$WEB_PID" "$TUNNEL_PID"
echo "One service exited unexpectedly. Check logs in $LOG_DIR"
exit 1
