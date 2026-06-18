#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

bash -n bin/dog bin/claude-tele bin/claude-tele-watchdog bin/claude-tele-macos install.sh install-macos.sh
python3 -m py_compile \
  bin/claude-tele-patch-telegram-plugin \
  bin/claude-tele-replay-missed \
  bin/claude-tele-control-mcp.py
python3 -m pytest tests/test_replay_health_gate.py -q
systemd-analyze --user verify \
  systemd/user/telegram-claude.service \
  systemd/user/telegram-claude-watchdog.service

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
