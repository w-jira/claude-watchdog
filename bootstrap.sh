#!/bin/bash
set -euo pipefail

REPO_URL="${CLAUDE_WATCHDOG_REPO_URL:-https://github.com/w-jira/claude-watchdog.git}"
DEFAULT_RECOVERY_URL="https://raw.githubusercontent.com/w-jira/claude-watchdog/main/bootstrap.sh"
INSTALL_DIR="${CLAUDE_WATCHDOG_INSTALL_DIR:-${HOME}/.local/share/claude-watchdog/repo}"
SKIP_SETUP="${CLAUDE_WATCHDOG_SKIP_SETUP:-0}"

log() { printf '[claude-watchdog bootstrap] %s\n' "$*"; }
die() { printf '[claude-watchdog bootstrap] error: %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

has git || die "git is required. On Ubuntu/Debian: sudo apt-get install -y git"
has bash || die "bash is required"

parent="$(dirname "$INSTALL_DIR")"
mkdir -p "$parent"

if [ -e "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
  die "${INSTALL_DIR} exists but is not a git checkout; choose another CLAUDE_WATCHDOG_INSTALL_DIR or move it aside"
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  log "updating existing checkout at ${INSTALL_DIR}"
  git -C "$INSTALL_DIR" fetch --prune origin
  branch="$(git -C "$INSTALL_DIR" symbolic-ref --quiet --short HEAD || printf 'main')"
  git -C "$INSTALL_DIR" pull --ff-only origin "$branch"
else
  log "cloning ${REPO_URL} to ${INSTALL_DIR}"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

recovery_url="$DEFAULT_RECOVERY_URL"
case "$REPO_URL" in
  https://github.com/*)
    recovery_repo="${REPO_URL#https://github.com/}"
    recovery_repo="${recovery_repo%/}"
    recovery_repo="${recovery_repo%.git}"
    recovery_url="https://raw.githubusercontent.com/${recovery_repo}/main/bootstrap.sh"
    ;;
esac

if [ "$SKIP_SETUP" = "1" ]; then
  log "skipping setup because CLAUDE_WATCHDOG_SKIP_SETUP=1"
  exit 0
fi

log "starting guided setup"
if [ -r /dev/tty ] && [ -w /dev/tty ]; then
  exec ./bin/dog setup </dev/tty
fi

cat >&2 <<EOF
[claude-watchdog bootstrap] error: no interactive terminal is available for the setup wizard.
Run the non-piped installer instead:

  curl -fsSLo /tmp/claude-watchdog-bootstrap.sh ${recovery_url}
  bash /tmp/claude-watchdog-bootstrap.sh

EOF
exit 1
