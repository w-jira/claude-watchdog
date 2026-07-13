from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
WATCHDOG_UNIT = ROOT / "systemd" / "user" / "telegram-claude-watchdog.service"
CLAUDE_UNIT = ROOT / "systemd" / "user" / "telegram-claude.service"
CLAUDE_TELE = ROOT / "bin" / "claude-tele"
WATCHDOG = ROOT / "bin" / "claude-tele-watchdog"
REPLAY = ROOT / "bin" / "claude-tele-replay-missed"


def test_bun_install_refuses_missing_sha256sum() -> None:
    text = INSTALL.read_text(encoding="utf-8")

    assert 'has sha256sum || die "sha256sum is required to verify the Bun download' in text
    assert "cannot verify bun download integrity; proceeding" not in text


def test_watchdog_unit_has_canonical_threshold_and_transcript_mount() -> None:
    text = WATCHDOG_UNIT.read_text(encoding="utf-8")

    assert "Environment=WATCHDOG_THRESHOLD=25" in text
    assert "BindReadOnlyPaths=%h/bin %h/.local/bin %h/.claude/projects" in text


def test_units_share_tmux_runtime_and_watchdog_can_reach_user_bus() -> None:
    watchdog = WATCHDOG_UNIT.read_text(encoding="utf-8")
    claude = CLAUDE_UNIT.read_text(encoding="utf-8")

    assert "RuntimeDirectory=claude-tele" in claude
    assert "RuntimeDirectory=claude-tele" not in watchdog
    assert "BindReadOnlyPaths=%t/bus" in watchdog
    assert "BindPaths=" in watchdog and "%t/claude-tele" in watchdog


def test_all_tmux_clients_use_the_dedicated_runtime() -> None:
    assert "TMUX_TMPDIR" in CLAUDE_TELE.read_text(encoding="utf-8")
    assert "TMUX_TMPDIR" in WATCHDOG.read_text(encoding="utf-8")
    assert "TMUX_TMPDIR" in REPLAY.read_text(encoding="utf-8")
