#!/usr/bin/env sh
set -eu

REPO="${XUSHI_REPO:-https://github.com/Polaris-d/xushi.git}"
INSTALL_DIR="${XUSHI_INSTALL_DIR:-$HOME/.xushi/app}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd git
require_cmd uv

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Updating xushi in $INSTALL_DIR"
  cd "$INSTALL_DIR"
  git pull --ff-only
elif [ -e "$INSTALL_DIR" ]; then
  echo "Install directory exists but is not a git repository: $INSTALL_DIR" >&2
  exit 1
else
  echo "Installing xushi into $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone "$REPO" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

uv sync
uv run xushi init --show-token
uv run xushi doctor

echo ""
echo "xushi is installed."
echo "Start daemon:"
echo "  cd \"$INSTALL_DIR\""
echo "  uv run xushi-daemon"
