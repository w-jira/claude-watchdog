#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

tmp_units=""
scan_output=""
npm_cache="$(mktemp -d)"
trap 'rm -rf "$npm_cache"; [ -z "$tmp_units" ] || rm -rf "$tmp_units"; [ -z "$scan_output" ] || rm -f "$scan_output"' EXIT
export NPM_CONFIG_CACHE="$npm_cache"

bash -n bootstrap.sh bin/dog bin/claude-tele bin/claude-tele-watchdog install.sh
python3 -m py_compile \
  bin/claude-tele-patch-telegram-plugin \
  bin/claude-tele-replay-missed \
  bin/claude-tele-control-mcp.py
python3 -m pytest tests/test_replay_health_gate.py tests/test_bootstrap.py tests/test_npm_package.py tests/test_claude_tele_tmux_env.py tests/test_dog_engine_resolution.py tests/test_claude_auth_detection.py tests/test_watchdog_context.py tests/test_install.py -q
tmp_units="$(mktemp -d)"
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

scan_output="$(mktemp)"
scan_tracked() {
  local rule="$1" pattern="$2" file lines line excluded
  shift 2
  while IFS= read -r -d '' file; do
    for excluded in "$@"; do
      [ "$file" = "$excluded" ] && continue 2
    done
    [ -f "$file" ] || continue
    lines=$(grep -nE "$pattern" -- "$file" 2>/dev/null | cut -d: -f1 || true)
    while IFS= read -r line; do
      [ -n "$line" ] && printf '%s:%s: %s\n' "$file" "$line" "$rule" >> "$scan_output"
    done <<< "$lines"
  done < <(git ls-files -z)
}

secret_pattern='TELEGRAM_BOT_TOKEN=[0-9]+:|BEGIN (OPENSSH|RSA|EC|PRIVATE) KEY|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}'
scan_tracked "possible secret/runtime file" "$secret_pattern" "config/env.example" "config/access.example.json"

# Reserved documentation fixtures exercise the personal-infrastructure rule
# without embedding fragments from any real operator or host.
fixture_domain='private-fixture'"\\."'example'"\\."'com'
fixture_mailbox='fixture-alerts'"@"'example'"\\."'com'
fixture_home='/home/'"example-user"
fixture_ip='203'"\\."'0'"\\."'113'"\\."'77'
fixture_telegram='(^|[^0-9])1000'"00000"'([^0-9]|$)'
personal_pattern="${fixture_domain}|${fixture_mailbox}|${fixture_home}|${fixture_ip}|${fixture_telegram}"
scan_tracked "synthetic personal-infrastructure fixture" "$personal_pattern"

if [ -s "$scan_output" ]; then
  cat "$scan_output" >&2
  exit 1
fi

echo "ok"
