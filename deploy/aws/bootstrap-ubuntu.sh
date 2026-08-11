#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script must run on the Ubuntu Lightsail instance." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y ca-certificates curl git

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

echo "Docker is installed. Sign out and reconnect once so group membership takes effect."
