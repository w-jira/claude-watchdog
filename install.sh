#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HOME}/.claude/channels/telegram"
WORKDIR="${STATE_DIR}/workdir"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
BUN_VERSION="${BUN_VERSION:-bun-v1.3.14}"
INSTALL_DEPS=0
START_SERVICE=0
YES=0
MENU=0
DEMO_MODE="${CLAUDE_WATCHDOG_DEMO:-0}"
PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-bypassPermissions}"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_USER_ID="${TELEGRAM_USER_ID:-}"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

One-stop installer for claude-watchdog.

Options:
  --install-deps              Install missing OS/user deps where supported.
  --token TOKEN               Write Telegram bot token to ~/.claude/channels/telegram/.env.
  --telegram-user-id ID       Allow this Telegram user ID in access.json.
  --permission-mode MODE       Claude permission mode: default, plan, acceptEdits, auto, dontAsk, bypassPermissions.
  --demo                      Hide sensitive status/log details for demos.
  --menu                      Run the interactive setup wizard (same as ./bin/cwd setup).
  --start                     Start the systemd user service after install.
  -y, --yes                   Non-interactive yes for supported install steps.
  -h, --help                  Show this help.

Agent-friendly example:
  TELEGRAM_BOT_TOKEN='123:abc' TELEGRAM_USER_ID='123456789' \
    ./install.sh --install-deps --start --yes

Notes:
  - Claude Code CLI must be installed and authenticated before the bot can run.
  - If bun is missing and --install-deps is set, this installs a pinned Bun release
    into ~/.bun/bin and symlinks it into ~/bin.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    --start) START_SERVICE=1 ;;
    --menu) MENU=1 ;;
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

confirm() {
  local prompt="$1"
  [ "$YES" = "1" ] && return 0
  printf '%s [y/N] ' "$prompt"
  read -r ans
  case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

validate_permission_mode() {
  case "$PERMISSION_MODE" in
    default|plan|acceptEdits|auto|dontAsk|bypassPermissions) return 0 ;;
    *) die "invalid permission mode: ${PERMISSION_MODE}" ;;
  esac
}


install_apt_deps() {
  local missing=()
  for cmd in tmux python3 curl unzip git; do
    has "$cmd" || missing+=("$cmd")
  done
  [ "${#missing[@]}" -gt 0 ] || return 0
  has apt-get || die "missing commands (${missing[*]}) and this installer only auto-installs OS deps with apt-get"
  confirm "Install OS packages with sudo apt-get: ${missing[*]}?" || die "dependency install declined"
  sudo apt-get update
  sudo apt-get install -y tmux python3 curl unzip git ca-certificates
}

install_bun() {
  # Verify bun actually *runs*, not just that it's on PATH. A bun built for a
  # CPU feature this host lacks (e.g. AVX2) is present but crashes with SIGILL,
  # so `has bun` would wrongly skip the (re)install. `bun --version` catches it.
  if bun --version >/dev/null 2>&1; then
    return 0
  fi
  [ "$INSTALL_DEPS" = "1" ] || return 0
  has curl || die "curl is required to install bun"
  has unzip || die "unzip is required to install bun"

  local arch asset tmp zipdir
  case "$(uname -m)" in
    x86_64|amd64)
      # The default bun x64 build requires AVX2. VirtualBox/QEMU guests, older
      # CPUs, and some cloud instances lack it — there, bun SIGILLs on every
      # invocation and the Telegram bridge silently never starts. Fall back to
      # the baseline build (no AVX2 required) when AVX2 is absent.
      if grep -qm1 avx2 /proc/cpuinfo 2>/dev/null; then
        arch="x64"
      else
        arch="x64-baseline"
        log "CPU has no AVX2 — using bun baseline build (bun-linux-x64-baseline)"
      fi ;;
    aarch64|arm64) arch="aarch64" ;;
    *) die "unsupported architecture for bundled bun install: $(uname -m)" ;;
  esac
  asset="bun-linux-${arch}.zip"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  log "installing ${BUN_VERSION} to ~/.bun/bin"
  curl -fL --proto '=https' --tlsv1.2 \
    "https://github.com/oven-sh/bun/releases/download/${BUN_VERSION}/${asset}" \
    -o "${tmp}/${asset}"
  unzip -q "${tmp}/${asset}" -d "$tmp"
  zipdir="${tmp}/bun-linux-${arch}"
  install -d -m 700 "${HOME}/.bun/bin" "${HOME}/bin"
  install -m 700 "${zipdir}/bun" "${HOME}/.bun/bin/bun"
  ln -sfn "${HOME}/.bun/bin/bun" "${HOME}/bin/bun"
}

ensure_claude_symlink() {
  # claude-tele expects ${HOME}/.local/bin/claude (also on the service's PATH).
  # Many installs place claude at /usr/local/bin or behind a version manager,
  # which makes the hardcoded path — and the service — fail to find it. Symlink
  # the resolved binary so both the expected path and the service PATH work.
  [ -x "${HOME}/.local/bin/claude" ] && return 0
  local resolved
  resolved="$(command -v claude 2>/dev/null || true)"
  [ -n "$resolved" ] || return 0
  install -d -m 755 "${HOME}/.local/bin"
  ln -sfn "$resolved" "${HOME}/.local/bin/claude"
  log "linked ${HOME}/.local/bin/claude -> ${resolved}"
}

plugin_installed() {
  compgen -G "${HOME}/.claude/plugins/cache/*/telegram" >/dev/null
}

install_plugin() {
  # The Telegram channel depends on the official telegram plugin. Without this
  # the bridge silently never starts on a clean machine. Idempotent: both the
  # marketplace add and the install are safe to repeat.
  local claude_bin
  claude_bin="$(command -v claude 2>/dev/null || true)"
  if [ -z "$claude_bin" ] && [ -x "${HOME}/.local/bin/claude" ]; then
    claude_bin="${HOME}/.local/bin/claude"
  fi
  [ -n "$claude_bin" ] || { warn "claude not found; skipping telegram plugin install — install/authenticate Claude Code, then re-run"; return 0; }

  "$claude_bin" plugin marketplace add anthropics/claude-plugins-official >/dev/null 2>&1 || true
  if "$claude_bin" plugin install telegram@claude-plugins-official >/dev/null 2>&1 || plugin_installed; then
    log "installed plugin telegram@claude-plugins-official"
  else
    warn "could not auto-install the telegram plugin — run: claude plugin install telegram@claude-plugins-official"
  fi
}

set_env_key() {
  local key="$1" value="$2" file="${STATE_DIR}/.env" tmp
  tmp="$(mktemp)"
  if [ -f "$file" ]; then
    grep -v "^${key}=" "$file" > "$tmp" || true
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  install -m 600 "$tmp" "$file"
  rm -f "$tmp"
}

write_env() {
  validate_permission_mode
  if [ -n "$BOT_TOKEN" ]; then
    [[ "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]] || die "Telegram bot token should look like '<bot-id>:<secret>'"
    umask 077
    {
      printf 'TELEGRAM_BOT_TOKEN=%s\n' "$BOT_TOKEN"
      printf 'CLAUDE_PERMISSION_MODE=%s\n' "$PERMISSION_MODE"
      printf 'CLAUDE_WATCHDOG_DEMO=%s\n' "$DEMO_MODE"
    } > "${STATE_DIR}/.env"
    chmod 600 "${STATE_DIR}/.env"
    log "wrote ${STATE_DIR}/.env"
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
payload = {
    "dmPolicy": "allowlist",
    "allowFrom": [user_id],
    "groups": {},
    "pending": {},
    "ackReaction": "👀",
    "replyToMode": "first",
    "textChunkLimit": 4096,
    "chunkMode": "newline",
}
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

[ "$MENU" = "1" ] && exec "${ROOT}/bin/cwd" setup

if [ "$INSTALL_DEPS" = "1" ]; then
  install_apt_deps
  install_bun
fi

mkdir -p "${HOME}/bin" "${STATE_DIR}" "${WORKDIR}" "${SYSTEMD_DIR}"
chmod 700 "${STATE_DIR}" "${WORKDIR}"

install -m 700 "${ROOT}/bin/claude-tele" "${HOME}/bin/claude-tele"
install -m 700 "${ROOT}/bin/cwd" "${HOME}/bin/cwd"
install -m 700 "${ROOT}/bin/claude-tele-watchdog" "${HOME}/bin/claude-tele-watchdog"
install -m 700 "${ROOT}/bin/claude-tele-patch-telegram-plugin" "${HOME}/bin/claude-tele-patch-telegram-plugin"
install -m 700 "${ROOT}/bin/claude-tele-replay-missed" "${HOME}/bin/claude-tele-replay-missed"
install -m 700 "${ROOT}/bin/claude-tele-control-mcp.py" "${HOME}/bin/claude-tele-control-mcp.py"
install -m 600 "${ROOT}/systemd/user/telegram-claude.service" "${SYSTEMD_DIR}/telegram-claude.service"
install -m 600 "${ROOT}/systemd/user/telegram-claude-watchdog.service" "${SYSTEMD_DIR}/telegram-claude-watchdog.service"

ensure_claude_symlink
install_plugin

write_env
write_access

systemctl --user daemon-reload
loginctl enable-linger "${USER}" >/dev/null 2>&1 || warn "could not enable linger; service may stop after logout"

missing=()
for cmd in claude tmux python3 systemctl bun; do
  has "$cmd" || missing+=("$cmd")
done
if [ "${#missing[@]}" -gt 0 ]; then
  warn "missing commands: ${missing[*]}"
  warn "run again with --install-deps for supported deps; install/authenticate Claude Code separately"
fi

if [ "$START_SERVICE" = "1" ]; then
  has claude || [ -x "${HOME}/.local/bin/claude" ] || die "claude CLI is missing; install and authenticate it before --start"
  plugin_installed || die "telegram plugin is not installed; run: claude plugin marketplace add anthropics/claude-plugins-official && claude plugin install telegram@claude-plugins-official"
  [ -s "${STATE_DIR}/.env" ] || die "missing ${STATE_DIR}/.env"
  [ -s "${STATE_DIR}/access.json" ] || die "missing ${STATE_DIR}/access.json"
  "${HOME}/bin/claude-tele" start
fi

log "installed"
log "next: claude-tele doctor"
[ "$START_SERVICE" = "1" ] || log "then: claude-tele start"
