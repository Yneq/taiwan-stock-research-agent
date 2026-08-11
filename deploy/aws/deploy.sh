#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE_DIR="$(cd "$AGENT_DIR/.." && pwd)"
STOCKTRACKER_DIR="$WORKSPACE_DIR/StockTracker"
ENV_FILE="$SCRIPT_DIR/.env.aws"

if [[ ! -d "$STOCKTRACKER_DIR/.git" ]]; then
  echo "Missing sibling repository: $STOCKTRACKER_DIR" >&2
  echo "Clone https://github.com/Yneq/StockTracker.git there first." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  echo "Copy .env.aws.example to .env.aws and fill in the secrets." >&2
  exit 1
fi

git -C "$STOCKTRACKER_DIR" pull --ff-only
git -C "$AGENT_DIR" pull --ff-only

docker compose \
  --env-file "$ENV_FILE" \
  --file "$SCRIPT_DIR/compose.yaml" \
  up --detach --build --remove-orphans

docker compose \
  --env-file "$ENV_FILE" \
  --file "$SCRIPT_DIR/compose.yaml" \
  ps
