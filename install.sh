#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HOME}/.claude/channels/telegram"
WORKDIR="${STATE_DIR}/workdir"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

need claude
need tmux
need systemctl
need python3

mkdir -p "${HOME}/bin" "${STATE_DIR}" "${WORKDIR}" "${SYSTEMD_DIR}"
chmod 700 "${STATE_DIR}" "${WORKDIR}"

install -m 700 "${ROOT}/bin/claude-tele" "${HOME}/bin/claude-tele"
install -m 700 "${ROOT}/bin/claude-tele-watchdog" "${HOME}/bin/claude-tele-watchdog"
install -m 700 "${ROOT}/bin/claude-tele-patch-telegram-plugin" "${HOME}/bin/claude-tele-patch-telegram-plugin"
install -m 700 "${ROOT}/bin/claude-tele-replay-missed" "${HOME}/bin/claude-tele-replay-missed"
install -m 700 "${ROOT}/bin/claude-tele-control-mcp.py" "${HOME}/bin/claude-tele-control-mcp.py"
install -m 600 "${ROOT}/systemd/user/telegram-claude.service" "${SYSTEMD_DIR}/telegram-claude.service"
install -m 600 "${ROOT}/systemd/user/telegram-claude-watchdog.service" "${SYSTEMD_DIR}/telegram-claude-watchdog.service"

if [ ! -f "${STATE_DIR}/.env" ]; then
  install -m 600 "${ROOT}/config/env.example" "${STATE_DIR}/.env"
  echo "created ${STATE_DIR}/.env — edit TELEGRAM_BOT_TOKEN before starting"
fi

if [ ! -f "${STATE_DIR}/access.json" ]; then
  install -m 600 "${ROOT}/config/access.example.json" "${STATE_DIR}/access.json"
  echo "created ${STATE_DIR}/access.json — add your Telegram user ID before starting"
fi

systemctl --user daemon-reload

echo "installed. Next:"
echo "  1. edit ${STATE_DIR}/.env"
echo "  2. edit ${STATE_DIR}/access.json"
echo "  3. claude-tele doctor"
echo "  4. claude-tele start"
