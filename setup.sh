#!/usr/bin/env bash
# One-command bootstrap: .env, then the stack.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill it in before continuing:"
  echo "  VONK_KEY     (required; the app will not start without it)"
  echo "  DB_PASSWORD  (and the matching password inside DATABASE_URL)"
  echo "  APP_DOMAIN / API_DOMAIN / CADDY_NETWORK"
  exit 1
fi

# Fail early and legibly rather than halfway through a container start.
missing=()
for var in VONK_KEY DB_PASSWORD APP_DOMAIN CADDY_NETWORK; do
  value="$(grep -E "^${var}=" .env | cut -d= -f2- || true)"
  [ -z "$value" ] && missing+=("$var")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "These are still blank in .env: ${missing[*]}"
  exit 1
fi

CADDY_NETWORK="$(grep -E '^CADDY_NETWORK=' .env | cut -d= -f2-)"
if ! docker network inspect "$CADDY_NETWORK" >/dev/null 2>&1; then
  echo "Docker network '$CADDY_NETWORK' does not exist (is Caddy running?)."
  exit 1
fi

docker compose up --build -d
echo
echo "Up. Frontend: https://$(grep -E '^APP_DOMAIN=' .env | cut -d= -f2-)"
echo "    API:      https://$(grep -E '^API_DOMAIN=' .env | cut -d= -f2-)/api/health"
