#!/usr/bin/env sh
set -eu

REPO_SLUG="${XUSHI_REPO_SLUG:-Polaris-d/xushi}"
VERSION="${XUSHI_VERSION:-latest}"
BIN_DIR="${XUSHI_BIN_DIR:-${XUSHI_INSTALL_DIR:-$HOME/.xushi/bin}}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

platform_tag() {
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m | tr '[:upper:]' '[:lower:]')"

  case "$os" in
    darwin) os="macos" ;;
    linux) os="linux" ;;
    *)
      echo "Unsupported operating system: $os" >&2
      exit 1
      ;;
  esac

  case "$arch" in
    amd64|x86_64) arch="x64" ;;
    arm64|aarch64) arch="arm64" ;;
    *)
      echo "Unsupported CPU architecture: $arch" >&2
      exit 1
      ;;
  esac

  printf '%s-%s' "$os" "$arch"
}

release_url() {
  asset="$1"
  if [ "$VERSION" = "latest" ]; then
    printf 'https://github.com/%s/releases/latest/download/%s' "$REPO_SLUG" "$asset"
  else
    printf 'https://github.com/%s/releases/download/%s/%s' "$REPO_SLUG" "$VERSION" "$asset"
  fi
}

install_binary() {
  name="$1"
  tag="$2"
  asset="$name-$tag"
  url="$(release_url "$asset")"
  target="$BIN_DIR/$name"
  temp="$target.download"

  echo "Downloading $asset"
  curl -fL --retry 3 --connect-timeout 15 -o "$temp" "$url"
  chmod 755 "$temp"
  mv "$temp" "$target"
}

profile_path() {
  shell_name="$(basename "${SHELL:-}")"
  if [ "$shell_name" = "zsh" ]; then
    printf '%s/.zshrc' "$HOME"
  elif [ "$shell_name" = "bash" ]; then
    printf '%s/.bashrc' "$HOME"
  else
    printf '%s/.profile' "$HOME"
  fi
}

ensure_path_config() {
  case ":$PATH:" in
    *":$BIN_DIR:"*) return 0 ;;
  esac

  profile="$(profile_path)"
  mkdir -p "$(dirname "$profile")"
  touch "$profile"
  if ! grep -F "$BIN_DIR" "$profile" >/dev/null 2>&1; then
    {
      echo ""
      echo "# xushi global command"
      echo "case \":\$PATH:\" in"
      echo "  *\":$BIN_DIR:\"*) ;;"
      echo "  *) export PATH=\"$BIN_DIR:\$PATH\" ;;"
      echo "esac"
    } >> "$profile"
  fi
}

require_cmd curl

tag="$(platform_tag)"
mkdir -p "$BIN_DIR"

install_binary "xushi" "$tag"
install_binary "xushi-daemon" "$tag"
ensure_path_config

"$BIN_DIR/xushi" init --show-token
"$BIN_DIR/xushi" doctor

echo ""
echo "xushi is installed into $BIN_DIR."
echo "Global command path has been configured for new shells."
echo "Start daemon:"
echo "  xushi-daemon"
