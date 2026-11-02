#!/bin/sh
# End-to-end tests on a throwaway stack with made-up mock receipts. It has its own
# database and ports, and is deleted afterwards. Your local data is never touched.
set -eu
cd "$(dirname "$0")/../.."
export EXTRACTION_BACKEND=mock AUTH_MODE=local WEB_PORT=5183 API_PORT=8010 DB_PORT=5443
COMPOSE="docker compose -p tabby-e2e --env-file /dev/null"

trap '$COMPOSE down -v >/dev/null 2>&1' EXIT
$COMPOSE up --build -d >/dev/null 2>&1

tries=0
until curl -sf -o /dev/null http://127.0.0.1:5183/api/status; do
  tries=$((tries + 1))
  [ "$tries" -lt 60 ] || { echo "The test stack didn't start."; exit 1; }
  sleep 1
done

cd web
npx playwright test "$@"
