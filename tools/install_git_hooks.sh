#!/usr/bin/env bash
set -euo pipefail

repo="${1:-}"
if [ -z "$repo" ]; then
  repo="$(git rev-parse --show-toplevel)"
fi

if [ ! -d "$repo/.githooks" ]; then
  echo "install_git_hooks: $repo/.githooks is missing" >&2
  exit 1
fi

git -C "$repo" config --local core.hooksPath .githooks
echo "Installed Git security hooks for $repo (core.hooksPath=.githooks)."
