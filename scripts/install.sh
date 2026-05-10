#!/usr/bin/env sh
set -eu

REPO_SLUG="${XUSHI_REPO_SLUG:-Polaris-d/xushi}"
VERSION="${XUSHI_VERSION:-latest}"
BIN_DIR="${XUSHI_BIN_DIR:-${XUSHI_INSTALL_DIR:-$HOME/.xushi/bin}}"
AGENT_PLUGINS="${XUSHI_INSTALL_AGENT_PLUGINS:-}"
AGENT_SKILLS="${XUSHI_INSTALL_AGENT_SKILLS:-}"
OPENCLAW_PLUGINS_DIR="${XUSHI_OPENCLAW_PLUGINS_DIR:-${OPENCLAW_PLUGINS_DIR:-}}"
OPENCLAW_SKILLS_DIR="${XUSHI_OPENCLAW_SKILLS_DIR:-${OPENCLAW_SKILLS_DIR:-}}"
HERMES_SKILLS_DIR="${XUSHI_HERMES_SKILLS_DIR:-${HERMES_SKILLS_DIR:-}}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent-skills)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for --agent-skills" >&2
        exit 1
      fi
      AGENT_SKILLS="$2"
      shift 2
      ;;
    --agent-skills=*)
      AGENT_SKILLS="${1#*=}"
      shift
      ;;
    --agent-plugins)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for --agent-plugins" >&2
        exit 1
      fi
      AGENT_PLUGINS="$2"
      shift 2
      ;;
    --agent-plugins=*)
      AGENT_PLUGINS="${1#*=}"
      shift
      ;;
    --openclaw-plugins-dir)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for --openclaw-plugins-dir" >&2
        exit 1
      fi
      OPENCLAW_PLUGINS_DIR="$2"
      shift 2
      ;;
    --openclaw-plugins-dir=*)
      OPENCLAW_PLUGINS_DIR="${1#*=}"
      shift
      ;;
    --openclaw-skills-dir)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for --openclaw-skills-dir" >&2
        exit 1
      fi
      OPENCLAW_SKILLS_DIR="$2"
      shift 2
      ;;
    --openclaw-skills-dir=*)
      OPENCLAW_SKILLS_DIR="${1#*=}"
      shift
      ;;
    --hermes-skills-dir)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for --hermes-skills-dir" >&2
        exit 1
      fi
      HERMES_SKILLS_DIR="$2"
      shift 2
      ;;
    --hermes-skills-dir=*)
      HERMES_SKILLS_DIR="${1#*=}"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

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

install_agent_plugins() {
  if [ -z "$AGENT_PLUGINS" ]; then
    return 0
  fi
  old_ifs="$IFS"
  IFS=","
  for target in $AGENT_PLUGINS; do
    target_name="$(printf '%s' "$target" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    case "$target_name" in
      openclaw)
        set -- plugins install openclaw
        if [ -n "$OPENCLAW_PLUGINS_DIR" ]; then
          set -- "$@" --openclaw-plugins-dir "$OPENCLAW_PLUGINS_DIR"
        fi
        "$BIN_DIR/xushi" "$@"
        ;;
      "")
        ;;
      *)
        echo "Unsupported XUSHI_INSTALL_AGENT_PLUGINS target: $target" >&2
        exit 1
        ;;
    esac
  done
  IFS="$old_ifs"
}

install_agent_skills() {
  if [ -z "$AGENT_SKILLS" ]; then
    return 0
  fi
  set -- skills install --targets "$AGENT_SKILLS"
  if [ -n "$OPENCLAW_SKILLS_DIR" ]; then
    set -- "$@" --openclaw-skills-dir "$OPENCLAW_SKILLS_DIR"
  fi
  if [ -n "$HERMES_SKILLS_DIR" ]; then
    set -- "$@" --hermes-skills-dir "$HERMES_SKILLS_DIR"
  fi
  "$BIN_DIR/xushi" "$@"
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
install_agent_plugins
install_agent_skills

"$BIN_DIR/xushi" init --show-token
"$BIN_DIR/xushi" doctor

echo ""
echo "xushi is installed into $BIN_DIR."
echo "Global command path has been configured for new shells."
if [ -n "$AGENT_PLUGINS" ]; then
  echo "Agent plugins installed for: $AGENT_PLUGINS"
fi
if [ -n "$AGENT_SKILLS" ]; then
  echo "Agent skills installed for: $AGENT_SKILLS"
fi
echo "Start daemon:"
echo "  xushi-daemon"
