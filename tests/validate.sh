#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

bash -n bootstrap.sh bin/dog bin/claude-tele bin/claude-tele-watchdog bin/claude-tele-macos install.sh install-macos.sh
python3 -m py_compile \
  bin/claude-tele-patch-telegram-plugin \
  bin/claude-tele-replay-missed \
  bin/claude-tele-control-mcp.py
python3 -m pytest tests/test_replay_health_gate.py tests/test_bootstrap.py tests/test_npm_package.py tests/test_claude_tele_tmux_env.py tests/test_dog_engine_resolution.py -q
tmp_units="$(mktemp -d)"
trap 'rm -rf "$tmp_units"' EXIT
python3 - "$tmp_units" <<'PY'
from pathlib import Path
import sys
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for source, target in (
    ("telegram-claude.service", "cwd-validate-telegram-claude.service"),
    ("telegram-claude-watchdog.service", "cwd-validate-telegram-claude-watchdog.service"),
):
    text = Path("systemd/user", source).read_text(encoding="utf-8")
    # `systemd-analyze verify` checks ExecStart binaries against this machine and
    # may merge same-named installed user units. Validate syntax through uniquely
    # named temporary units without requiring claude-watchdog to already be installed.
    text = text.replace("ExecStart=%h/bin/claude-tele __exec-start", "ExecStart=/bin/true")
    text = text.replace("ExecStop=%h/bin/claude-tele __exec-stop", "ExecStop=/bin/true")
    text = text.replace("ExecStart=%h/bin/claude-tele-watchdog", "ExecStart=/bin/true")
    text = text.replace("BindsTo=telegram-claude.service", "BindsTo=cwd-validate-telegram-claude.service")
    (out / target).write_text(text, encoding="utf-8")
PY
systemd-analyze --user verify \
  "$tmp_units/cwd-validate-telegram-claude.service" \
  "$tmp_units/cwd-validate-telegram-claude-watchdog.service"

secret_pattern='TELEGRAM_BOT_TOKEN=[0-9]+:|BEGIN (OPENSSH|RSA|EC|PRIVATE) KEY|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}'
if grep -R --line-number -E "$secret_pattern" . \
  --exclude-dir=.git \
  --exclude-dir=.claude \
  --exclude-dir=__pycache__ \
  --exclude='env.example' \
  --exclude='access.example.json'; then
  echo "possible secret/runtime file found" >&2
  exit 1
fi

# Split local/private examples so this public file does not itself contain them.
domain_one='remails'"\\."'me'
domain_two='wjira'"\\."'com'
mail_one='server-noti'"fications"
mail_two='alerts'"@"
user_home='/home/'"ubuntu"
zt_prefix='10'"\\."'152'"\\."
public_prefix='44'"\\."'239'"\\."
telegram_id='7524'"762580"
personal_pattern="${domain_one}|${domain_two}|${mail_one}|${mail_two}|${user_home}|${zt_prefix}|${public_prefix}|${telegram_id}"
if grep -R --line-number -E "$personal_pattern" . \
  --exclude-dir=.git \
  --exclude-dir=.claude \
  --exclude-dir=__pycache__; then
  echo "personal infrastructure string found" >&2
  exit 1
fi

echo "ok"
