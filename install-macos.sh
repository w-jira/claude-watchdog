#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HOME}/.claude/channels/telegram"
WORKDIR="${STATE_DIR}/workdir"
TOKEN_KEY_FILE="${STATE_DIR}/.token.key"
TOKEN_ENC_FILE="${STATE_DIR}/.token.enc"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_USER_ID="${TELEGRAM_USER_ID:-}"
DEMO_MODE="${CLAUDE_WATCHDOG_DEMO:-0}"
PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-bypassPermissions}"
START_SERVICE=0
INSTALL_DEPS=0
YES=0
CLAUDE_INSTALLED_THIS_RUN=0

usage() {
  cat <<'EOF'
Usage: ./install-macos.sh [options]

macOS installer for claude-watchdog. Installs a LaunchAgent + tmux runner.

Options:
  --install-deps              Install missing deps with Homebrew where available.
  --token TOKEN               Write Telegram bot token to ~/.claude/channels/telegram/.env.
  --telegram-user-id ID       Allow this Telegram user ID in access.json.
  --permission-mode MODE       Claude permission mode: default, plan, acceptEdits, auto, dontAsk, bypassPermissions.
  --demo                      Hide sensitive status/log details for demos.
  --start                     Start the launchd service after install.
  -y, --yes                   Non-interactive yes for supported install steps.
  -h, --help                  Show this help.

Example:
  TELEGRAM_BOT_TOKEN='123:abc' TELEGRAM_USER_ID='123456789' \
    ./install-macos.sh --install-deps --start --yes

Notes:
  - If Claude Code is missing and npm is available, --install-deps installs it
    into ~/.npm-global/bin and symlinks it into ~/.local/bin.
  - Homebrew is used only when --install-deps is set.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    --start) START_SERVICE=1 ;;
    --demo) DEMO_MODE=1 ;;
    -y|--yes) YES=1 ;;
    --token) shift; BOT_TOKEN="${1:-}" ;;
    --telegram-user-id) shift; TELEGRAM_USER_ID="${1:-}" ;;
    --permission-mode) shift; PERMISSION_MODE="${1:-}" ;;
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
validate_permission_mode() { case "$PERMISSION_MODE" in default|plan|acceptEdits|auto|dontAsk|bypassPermissions) return 0 ;; *) die "invalid permission mode: ${PERMISSION_MODE}" ;; esac; }
set_env_key() {
  local key="$1" value="$2" file="${STATE_DIR}/.env" tmp
  tmp="$(mktemp)"
  [ -f "$file" ] && grep -v "^${key}=" "$file" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  install -m 600 "$tmp" "$file"
  rm -f "$tmp"
}

[ "$(uname -s)" = "Darwin" ] || die "install-macos.sh must be run on macOS"

install_deps() {
  local missing=()
  for cmd in tmux python3 curl unzip git bun npm; do
    has "$cmd" || missing+=("$cmd")
  done
  [ "${#missing[@]}" -eq 0 ] && return 0
  [ "$INSTALL_DEPS" = "1" ] || return 0
  has brew || die "Homebrew is required for --install-deps on macOS: https://brew.sh"
  confirm "Install missing Homebrew packages: ${missing[*]}?" || die "dependency install declined"
  for pkg in "${missing[@]}"; do
    case "$pkg" in
      python3) brew install python ;;
      npm) brew install node ;;
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

install_claude_code() {
  if [ -n "$(resolve_claude)" ]; then
    return 0
  fi
  [ "$INSTALL_DEPS" = "1" ] || return 0
  if ! has npm; then
    warn "npm is missing; install a current Node.js LTS/npm, then re-run dog setup to install Claude Code"
    return 0
  fi

  install -d -m 755 "${HOME}/.npm-global/bin" "${HOME}/.local/bin"
  export PATH="${HOME}/.npm-global/bin:${PATH}"
  log "installing Claude Code CLI with npm into ~/.npm-global"
  npm install -g --prefix "${HOME}/.npm-global" @anthropic-ai/claude-code
  if [ -x "${HOME}/.npm-global/bin/claude" ]; then
    ln -sfn "${HOME}/.npm-global/bin/claude" "${HOME}/.local/bin/claude"
    log "linked ${HOME}/.local/bin/claude -> ${HOME}/.npm-global/bin/claude"
    CLAUDE_INSTALLED_THIS_RUN=1
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
    warn "could not auto-install telegram plugin — run: claude to authenticate, then run: claude plugin install telegram@claude-plugins-official"
  fi
}

encrypt_token() {
  local token="$1"
  has openssl || return 1
  install -d -m 700 "$STATE_DIR"
  umask 077
  if [ ! -s "$TOKEN_KEY_FILE" ]; then
    openssl rand -base64 48 > "$TOKEN_KEY_FILE"
    chmod 600 "$TOKEN_KEY_FILE"
  fi
  printf '%s' "$token" | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:${TOKEN_KEY_FILE}" -out "$TOKEN_ENC_FILE"
  chmod 600 "$TOKEN_ENC_FILE"
}

remove_legacy_cwd() {
  local legacy="${HOME}/bin/cwd"
  [ -e "$legacy" ] || return 0
  if [ -f "$legacy" ] && grep -q "claude-watchdog setup" "$legacy" 2>/dev/null; then
    rm -f "$legacy"
    log "removed legacy ${legacy}; use dog instead"
  else
    warn "legacy ${legacy} exists but was not recognized as claude-watchdog; leaving it untouched"
  fi
}

write_env() {
  validate_permission_mode
  if [ -n "$BOT_TOKEN" ]; then
    [[ "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]] || die "Telegram bot token should look like '<bot-id>:<secret>'"
    umask 077
    if encrypt_token "$BOT_TOKEN"; then
      {
        printf 'TELEGRAM_BOT_TOKEN_ENCRYPTED=1\n'
        printf 'CLAUDE_PERMISSION_MODE=%s\n' "$PERMISSION_MODE"
        printf 'CLAUDE_WATCHDOG_DEMO=%s\n' "$DEMO_MODE"
      } > "${STATE_DIR}/.env"
      log "wrote encrypted token and ${STATE_DIR}/.env"
    else
      warn "openssl not found; storing token in private plaintext .env instead of encrypted token file"
      {
        printf 'TELEGRAM_BOT_TOKEN=%s\n' "$BOT_TOKEN"
        printf 'CLAUDE_PERMISSION_MODE=%s\n' "$PERMISSION_MODE"
        printf 'CLAUDE_WATCHDOG_DEMO=%s\n' "$DEMO_MODE"
      } > "${STATE_DIR}/.env"
      log "wrote ${STATE_DIR}/.env"
    fi
    chmod 600 "${STATE_DIR}/.env"
  elif [ ! -f "${STATE_DIR}/.env" ]; then
    install -m 600 "${ROOT}/config/env.example" "${STATE_DIR}/.env"
    set_env_key "CLAUDE_PERMISSION_MODE" "$PERMISSION_MODE"
    set_env_key "CLAUDE_WATCHDOG_DEMO" "$DEMO_MODE"
    warn "created ${STATE_DIR}/.env — edit TELEGRAM_BOT_TOKEN before starting"
  else
    set_env_key "CLAUDE_PERMISSION_MODE" "$PERMISSION_MODE"
    set_env_key "CLAUDE_WATCHDOG_DEMO" "$DEMO_MODE"
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
install_claude_code
mkdir -p "${HOME}/bin" "${STATE_DIR}" "${WORKDIR}"
chmod 700 "${STATE_DIR}" "${WORKDIR}"
install -m 700 "${ROOT}/bin/claude-tele-macos" "${HOME}/bin/claude-tele"
install -m 700 "${ROOT}/bin/dog" "${HOME}/bin/dog"
remove_legacy_cwd
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
  warn "run again with --install-deps for supported deps; authenticate Claude Code separately after install"
fi

if [ "$START_SERVICE" = "1" ] && [ "$CLAUDE_INSTALLED_THIS_RUN" = "1" ]; then
  warn "Claude Code was installed during this setup; run claude to authenticate, then run: dog start"
  START_SERVICE=0
fi

if [ "$START_SERVICE" = "1" ]; then
  [ -n "$(resolve_claude)" ] || die "claude CLI is missing; install and authenticate it before --start"
  plugin_installed || die "telegram plugin is not installed; run claude to authenticate, then run: claude plugin marketplace add anthropics/claude-plugins-official && claude plugin install telegram@claude-plugins-official"
  "${HOME}/bin/claude-tele" start
fi

log "installed"
log "next: claude-tele doctor"
[ "$START_SERVICE" = "1" ] || log "then: claude-tele start"
