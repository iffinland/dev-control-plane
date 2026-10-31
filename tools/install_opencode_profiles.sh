#!/usr/bin/env bash
# Install the control-plane OpenCode agent profiles into the owner's user config.
# This is a user-level file copy only: no system package, service, timer or
# listener is created. Existing different files are backed up, never silently
# overwritten.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$repo_root/adapters/opencode/agents"
target_dir="${OPENCODE_AGENT_DIR:-$HOME/.config/opencode/agents}"
dry_run=0

usage() {
  cat <<'EOF'
usage: install_opencode_profiles.sh [--dry-run] [--target DIR]

Copies/synchronises the control-plane agent profiles into the OpenCode user
config directory (default: ~/.config/opencode/agents, or $OPENCODE_AGENT_DIR).
It does not edit opencode.jsonc, create services or require root.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --target)
      if [ "$#" -lt 2 ]; then
        echo "install_opencode_profiles: --target needs a directory" >&2
        exit 2
      fi
      target_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install_opencode_profiles: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

profiles=(
  "opencode-unattended.md"
  "opencode-development.md"
)

if [ ! -d "$source_dir" ]; then
  echo "install_opencode_profiles: source directory missing: $source_dir" >&2
  exit 1
fi

if [ "$dry_run" -eq 0 ]; then
  mkdir -p "$target_dir"
fi

for name in "${profiles[@]}"; do
  source_file="$source_dir/$name"
  target_file="$target_dir/$name"
  if [ ! -f "$source_file" ]; then
    echo "install_opencode_profiles: missing source profile: $source_file" >&2
    exit 1
  fi
  if [ -f "$target_file" ] && cmp -s "$source_file" "$target_file"; then
    echo "unchanged: $target_file"
    continue
  fi
  if [ "$dry_run" -eq 1 ]; then
    echo "would install: $source_file -> $target_file"
    continue
  fi
  if [ -f "$target_file" ]; then
    backup="$target_file.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p "$target_file" "$backup"
    echo "backup:    $backup"
  fi
  install -m 0644 "$source_file" "$target_file"
  echo "installed: $target_file"
done

if [ "$dry_run" -eq 0 ]; then
  echo ""
  echo "Restart OpenCode so the profiles load."
  echo "Verify with: opencode debug agent opencode-development"
fi
