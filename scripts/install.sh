#!/usr/bin/env sh
set -eu

REPO_SLUG="${XUSHI_REPO_SLUG:-Polaris-d/xushi}"
VERSION="${XUSHI_VERSION:-latest}"
BIN_DIR="${XUSHI_BIN_DIR:-${XUSHI_INSTALL_DIR:-$HOME/.xushi/bin}}"
AGENT_SKILLS="${XUSHI_INSTALL_AGENT_SKILLS:-}"
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

install_xushi_skills_package() {
  require_cmd unzip
  target_name="$1"
  skills_dir="$2"
  target="$skills_dir/xushi-skills"
  temp_dir="$skills_dir/.xushi-skills-download"
  archive="$skills_dir/xushi-skills.zip"
  url="$(release_url "xushi-skills.zip")"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

  echo "Installing xushi-skills for $target_name"
  mkdir -p "$skills_dir"
  rm -rf "$temp_dir"
  mkdir -p "$temp_dir"
  curl -fL --retry 3 --connect-timeout 15 -o "$archive" "$url"
  unzip -q "$archive" -d "$temp_dir"
  if [ ! -f "$temp_dir/xushi-skills/SKILL.md" ]; then
    echo "Invalid xushi-skills archive: missing SKILL.md" >&2
    exit 1
  fi
  if [ -e "$target" ]; then
    mv "$target" "$skills_dir/xushi-skills.backup-$timestamp"
  fi
  mv "$temp_dir/xushi-skills" "$target"
  rm -rf "$temp_dir" "$archive"
}

install_xushi_skills_for_openclaw() {
  skills_dir="$OPENCLAW_SKILLS_DIR"
  if [ -z "$skills_dir" ]; then
    skills_dir="${OPENCLAW_HOME:-$HOME/.openclaw}/skills"
  fi
  install_xushi_skills_package "OpenClaw" "$skills_dir"
}

install_xushi_skills_for_hermes() {
  skills_dir="$HERMES_SKILLS_DIR"
  if [ -z "$skills_dir" ]; then
    skills_dir="${HERMES_HOME:-$HOME/.hermes}/skills"
  fi
  install_xushi_skills_package "Hermes" "$skills_dir"
}

install_agent_skills() {
  if [ -z "$AGENT_SKILLS" ]; then
    return 0
  fi
  old_ifs="$IFS"
  IFS=","
  for target in $AGENT_SKILLS; do
    target_name="$(printf '%s' "$target" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    case "$target_name" in
      openclaw) install_xushi_skills_for_openclaw ;;
      hermes) install_xushi_skills_for_hermes ;;
      "")
        ;;
      *)
        echo "Unsupported XUSHI_INSTALL_AGENT_SKILLS target: $target" >&2
        exit 1
        ;;
    esac
  done
  IFS="$old_ifs"
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
install_agent_skills

"$BIN_DIR/xushi" init --show-token
"$BIN_DIR/xushi" doctor

echo ""
echo "xushi is installed into $BIN_DIR."
echo "Global command path has been configured for new shells."
if [ -n "$AGENT_SKILLS" ]; then
  echo "Agent skills installed for: $AGENT_SKILLS"
fi
echo "Start daemon:"
echo "  xushi-daemon"
