#!/usr/bin/env python3
"""Regression tests for fail-closed missed-message replay injection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "bin" / "claude-tele-replay-missed"


def write_pending_journal(state_dir: Path) -> None:
  state_dir.mkdir(parents=True, exist_ok=True)
  row = {
    "journaled_at": int(time.time()) - 120,
    "content": "hello from telegram",
    "meta": {
      "chat_id": "123",
      "message_id": "456",
      "user": "Jira",
      "user_id": "789",
      "ts": "2026-06-16T00:00:00Z",
    },
  }
  (state_dir / "inbound-journal.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


def run_replay(
  tmp_path: Path,
  *,
  health: dict[str, object] | None = None,
  pane: str = "❯\n",
) -> tuple[subprocess.CompletedProcess[str], Path]:
  home = tmp_path / "home"
  state_dir = home / ".claude" / "channels" / "telegram"
  bin_dir = tmp_path / "bin"
  bin_dir.mkdir(parents=True)
  home.mkdir(parents=True)
  write_pending_journal(state_dir)
  if health is not None:
    (state_dir / "plugin-health.json").write_text(json.dumps(health), encoding="utf-8")

  tmux_log = tmp_path / "tmux.log"
  pane_file = tmp_path / "pane.txt"
  pane_file.write_text(pane, encoding="utf-8")
  fake_tmux = bin_dir / "tmux"
  fake_tmux.write_text(
    "#!/bin/sh\n"
    f"printf '%s\\n' \"$*\" >> {tmux_log}\n"
    "if [ \"$1\" = \"capture-pane\" ]; then\n"
    f"  cat {pane_file}\n"
    "fi\n"
    "exit 0\n",
    encoding="utf-8",
  )
  fake_tmux.chmod(0o755)

  env = os.environ.copy()
  env.update(
    {
      "HOME": str(home),
      "PATH": f"{bin_dir}:{env.get('PATH', '')}",
      "TELEGRAM_STATE_DIR": str(state_dir),
      "CLAUDE_TELE_REPLAY_MIN_AGE": "0",
      "CLAUDE_TELE_REPLAY_MAX": "20",
    }
  )
  result = subprocess.run(
    [sys.executable, str(REPLAY)],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
    timeout=10,
  )
  return result, tmux_log


def test_replay_skips_injection_when_telegram_health_missing(tmp_path: Path) -> None:
  result, tmux_log = run_replay(tmp_path)

  assert result.returncode == 0
  assert "replay skipped" in result.stdout
  assert "telegram e2e unhealthy" in result.stdout
  assert not tmux_log.exists(), "tmux must not be touched when Telegram health is unknown"


def test_replay_skips_injection_when_telegram_health_has_recent_error(tmp_path: Path) -> None:
  now = int(time.time())
  result, tmux_log = run_replay(
    tmp_path,
    health={
      "polling_started_at": now,
      "last_getme_ok_at": now,
      "last_mcp_notify_ok_at": now - 10,
      "last_mcp_notify_error_at": now,
      "last_error": "telegram send failed",
    },
  )

  assert result.returncode == 0
  assert "replay skipped" in result.stdout
  assert "mcp_notify_error_after_ok" in result.stdout
  assert not tmux_log.exists() or "paste-buffer" not in tmux_log.read_text(encoding="utf-8")


def test_replay_skips_injection_when_polling_started_before_service_start(tmp_path: Path) -> None:
  now = int(time.time())
  result, tmux_log = run_replay(
    tmp_path,
    health={
      "service_started_at": now,
      "polling_started_at": now - 30,
      "last_getme_ok_at": now,
      "last_mcp_notify_ok_at": now,
      "last_error": None,
    },
  )

  assert result.returncode == 0
  assert "replay skipped" in result.stdout
  assert "polling_before_service_start" in result.stdout
  assert not tmux_log.exists() or "paste-buffer" not in tmux_log.read_text(encoding="utf-8")


def test_replay_skips_injection_when_getme_success_predates_service_start(tmp_path: Path) -> None:
  now = int(time.time())
  result, tmux_log = run_replay(
    tmp_path,
    health={
      "service_started_at": now,
      "polling_started_at": now,
      "last_getme_ok_at": now - 600,
      "last_mcp_notify_ok_at": now,
      "last_error": None,
    },
  )

  assert result.returncode == 0
  assert "replay skipped" in result.stdout
  assert "getme_before_service_start" in result.stdout
  assert not tmux_log.exists() or "paste-buffer" not in tmux_log.read_text(encoding="utf-8")


def test_replay_skips_injection_when_claude_pane_is_busy(tmp_path: Path) -> None:
  now = int(time.time())
  result, tmux_log = run_replay(
    tmp_path,
    health={
      "polling_started_at": now,
      "last_getme_ok_at": now,
      "last_mcp_notify_ok_at": now,
      "last_error": None,
    },
    pane="Thinking…\nRunning tool\n",
  )

  assert result.returncode == 0
  assert "replay skipped" in result.stdout
  assert "session busy" in result.stdout
  assert not tmux_log.exists() or "paste-buffer" not in tmux_log.read_text(encoding="utf-8")


def test_replay_injects_when_telegram_health_is_recently_ok(tmp_path: Path) -> None:
  now = int(time.time())
  result, tmux_log = run_replay(
    tmp_path,
    health={
      "polling_started_at": now,
      "last_getme_ok_at": now,
      "last_mcp_notify_ok_at": now,
      "last_error": None,
    },
  )

  assert result.returncode == 0, result.stderr
  assert "replayed 1 missed Telegram message" in result.stdout
  assert tmux_log.exists()
  log = tmux_log.read_text(encoding="utf-8")
  assert "load-buffer" in log
  assert "paste-buffer" in log
  assert "send-keys" in log
