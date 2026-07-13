from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
WATCHDOG_UNIT = ROOT / "systemd" / "user" / "telegram-claude-watchdog.service"


def test_bun_install_refuses_missing_sha256sum() -> None:
    text = INSTALL.read_text(encoding="utf-8")

    assert 'has sha256sum || die "sha256sum is required to verify the Bun download' in text
    assert "cannot verify bun download integrity; proceeding" not in text


def test_watchdog_unit_has_canonical_threshold_and_transcript_mount() -> None:
    text = WATCHDOG_UNIT.read_text(encoding="utf-8")

    assert "Environment=WATCHDOG_THRESHOLD=25" in text
    assert "BindReadOnlyPaths=%h/bin %h/.local/bin %h/.claude/projects" in text
