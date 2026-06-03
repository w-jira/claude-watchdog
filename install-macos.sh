#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HOME}/.claude/channels/telegram"
WORKDIR="${STATE_DIR}/workdir"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_USER_ID="${TELEGRAM_USER_ID:-}"
START_SERVICE=0
INSTALL_DEPS=0
YES=0

usage() {
  cat <<'EOF'
Usage: ./install-macos.sh [options]

macOS installer for claude-watchdog. Installs a LaunchAgent + tmux runner.

Options:
  --install-deps              Install missing deps with Homebrew where available.
  --token TOKEN               Write Telegram bot token to ~/.claude/channels/telegram/.env.
  --telegram-user-id ID       Allow this Telegram user ID in access.json.
  --start                     Start the launchd service after install.
  -y, --yes                   Non-interactive yes for supported install steps.
  -h, --help                  Show this help.

Example:
  TELEGRAM_BOT_TOKEN='123:abc' TELEGRAM_USER_ID='123456789' \
    ./install-macos.sh --install-deps --start --yes

Notes:
  - Claude Code CLI must be installed and authenticated first.
  - Homebrew is used only when --install-deps is set.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    --start) START_SERVICE=1 ;;
    -y|--yes) YES=1 ;;
    --token) shift; BOT_TOKEN="${1:-}" ;;
    --telegram-user-id) shift; TELEGRAM_USER_ID="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() { printf '[claude-watchdog] %s\n' "$*"; }
warn() { printf '[claude-watchdog] warning: %s\n' "$*" >&2; }
die() { printf '[claude-watchdog] error: %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }
confirm() { [ "$YES" = "1" ] && return 0; printf '%s [y/N] ' "$1"; read -r ans; case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac; }

[ "$(uname -s)" = "Darwin" ] || die "install-macos.sh must be run on macOS"

install_deps() {
  local missing=()
  for cmd in tmux python3 curl unzip git bun; do
    has "$cmd" || missing+=("$cmd")
  done
  [ "${#missing[@]}" -eq 0 ] && return 0
  [ "$INSTALL_DEPS" = "1" ] || return 0
  has brew || die "Homebrew is required for --install-deps on macOS: https://brew.sh"
  confirm "Install missing Homebrew packages: ${missing[*]}?" || die "dependency install declined"
  for pkg in "${missing[@]}"; do
    case "$pkg" in
      python3) brew install python ;;
      *) brew install "$pkg" ;;
    esac
  done
}

resolve_claude() {
  if [ -x "${HOME}/.local/bin/claude" ]; then
    echo "${HOME}/.local/bin/claude"
  else
    command -v claude 2>/dev/null || true
  fi
}

ensure_claude_symlink() {
  [ -x "${HOME}/.local/bin/claude" ] && return 0
  local resolved
  resolved="$(command -v claude 2>/dev/null || true)"
  [ -n "$resolved" ] || return 0
  install -d -m 755 "${HOME}/.local/bin"
  ln -sfn "$resolved" "${HOME}/.local/bin/claude"
  log "linked ${HOME}/.local/bin/claude -> ${resolved}"
}

plugin_installed() { compgen -G "${HOME}/.claude/plugins/cache/*/telegram" >/dev/null; }

install_plugin() {
  local claude_bin
  claude_bin="$(resolve_claude)"
  [ -n "$claude_bin" ] || { warn "claude not found; skipping plugin install — install/authenticate Claude Code, then re-run"; return 0; }
  "$claude_bin" plugin marketplace add anthropics/claude-plugins-official >/dev/null 2>&1 || true
  if "$claude_bin" plugin install telegram@claude-plugins-official >/dev/null 2>&1 || plugin_installed; then
    log "installed plugin telegram@claude-plugins-official"
  else
    warn "could not auto-install telegram plugin — run: claude plugin install telegram@claude-plugins-official"
  fi
}

write_env() {
  if [ -n "$BOT_TOKEN" ]; then
    case "$BOT_TOKEN" in *:*) ;; *) die "Telegram bot token should look like '<bot-id>:<secret>'" ;; esac
    umask 077
    printf 'TELEGRAM_BOT_TOKEN=%s\n' "$BOT_TOKEN" > "${STATE_DIR}/.env"
    chmod 600 "${STATE_DIR}/.env"
    log "wrote ${STATE_DIR}/.env"
  elif [ ! -f "${STATE_DIR}/.env" ]; then
    install -m 600 "${ROOT}/config/env.example" "${STATE_DIR}/.env"
    warn "created ${STATE_DIR}/.env — edit TELEGRAM_BOT_TOKEN before starting"
  fi
}

write_access() {
  if [ -n "$TELEGRAM_USER_ID" ]; then
    [[ "$TELEGRAM_USER_ID" =~ ^[0-9]+$ ]] || die "Telegram user ID must be numeric"
    python3 - "$TELEGRAM_USER_ID" "${STATE_DIR}/access.json" <<'PY'
import json, sys
user_id, path = sys.argv[1], sys.argv[2]
payload = {"dmPolicy":"allowlist","allowFrom":[user_id],"groups":{},"pending":{},"ackReaction":"👀","replyToMode":"first","textChunkLimit":4096,"chunkMode":"newline"}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
    chmod 600 "${STATE_DIR}/access.json"
    log "wrote ${STATE_DIR}/access.json"
  elif [ ! -f "${STATE_DIR}/access.json" ]; then
    install -m 600 "${ROOT}/config/access.example.json" "${STATE_DIR}/access.json"
    warn "created ${STATE_DIR}/access.json — add your Telegram user ID before starting"
  fi
}

install_deps
mkdir -p "${HOME}/bin" "${STATE_DIR}" "${WORKDIR}"
chmod 700 "${STATE_DIR}" "${WORKDIR}"
install -m 700 "${ROOT}/bin/claude-tele-macos" "${HOME}/bin/claude-tele"
ensure_claude_symlink
install_plugin
write_env
write_access

missing=()
for cmd in claude tmux python3 bun; do
  if [ "$cmd" = "claude" ]; then
    has claude || [ -x "${HOME}/.local/bin/claude" ] || missing+=("$cmd")
  else
    has "$cmd" || missing+=("$cmd")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  warn "missing commands: ${missing[*]}"
  warn "run again with --install-deps for supported deps; install/authenticate Claude Code separately"
fi

if [ "$START_SERVICE" = "1" ]; then
  [ -n "$(resolve_claude)" ] || die "claude CLI is missing; install and authenticate it before --start"
  plugin_installed || die "telegram plugin is not installed; run: claude plugin marketplace add anthropics/claude-plugins-official && claude plugin install telegram@claude-plugins-official"
  "${HOME}/bin/claude-tele" start
fi

log "installed"
log "next: claude-tele doctor"
[ "$START_SERVICE" = "1" ] || log "then: claude-tele start"
