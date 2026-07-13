import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
WATCHDOG_UNIT = ROOT / "systemd" / "user" / "telegram-claude-watchdog.service"
CLAUDE_UNIT = ROOT / "systemd" / "user" / "telegram-claude.service"
CLAUDE_TELE = ROOT / "bin" / "claude-tele"
WATCHDOG = ROOT / "bin" / "claude-tele-watchdog"
REPLAY = ROOT / "bin" / "claude-tele-replay-missed"


def shell_function(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n", text)
    assert match is not None
    return match.group(0)


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def run_legacy_detection(tmp_path: Path, systemctl_body: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake_bin = tmp_path / "bin"
    probe_log = tmp_path / "probes.log"
    fake_bin.mkdir()
    write_executable(fake_bin / "id", "#!/bin/sh\n[ \"$1\" = \"-u\" ] && echo 424242\n")
    write_executable(fake_bin / "systemctl", systemctl_body)
    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "printf '%s|%s\\n' \"$*\" \"${TMUX+x}\" >> \"$PROBE_LOG\"\n"
        "[ \"${2:-}\" = \"${LEGACY_SOCKET:-/never}\" ]\n",
    )
    install_text = INSTALL.read_text(encoding="utf-8")
    function = shell_function(install_text, "detect_legacy_tmux_socket")
    script = "set -euo pipefail\nexport DETECTOR_PID=$$\nwarn() { printf 'warning: %s\\n' \"$*\" >&2; }\n" + function + "\ndetect_legacy_tmux_socket\n"
    env = os.environ.copy()
    env.pop("XDG_RUNTIME_DIR", None)
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "LEGACY_SOCKET": "/tmp/tmux-424242/default",
            "PROBE_LOG": str(probe_log),
            "TMUX": "/tmp/inherited-client,1,2",
        }
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    probes = probe_log.read_text(encoding="utf-8").splitlines()
    return result, probes


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
    assert "Wants=telegram-claude-watchdog.service" in claude


def test_all_tmux_clients_use_the_dedicated_runtime() -> None:
    assert "TMUX_TMPDIR" in CLAUDE_TELE.read_text(encoding="utf-8")
    assert "TMUX_TMPDIR" in WATCHDOG.read_text(encoding="utf-8")
    assert "TMUX_TMPDIR" in REPLAY.read_text(encoding="utf-8")


def test_legacy_tmux_detection_is_early_explicit_and_read_only() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    function = shell_function(text, "detect_legacy_tmux_socket")
    function_end = text.index(function) + len(function)
    call_index = text.index("\ndetect_legacy_tmux_socket\n", function_end)
    binary_install_index = text.index('if [ "$NPM_PACKAGE_INSTALL" = "1" ]')

    assert call_index < binary_install_index
    assert not re.search(r"\b(?:kill|stop|rm)\b", function)
    assert function.count('env -u TMUX tmux -S "$') == 3
    assert "tmux has-session" not in function
    assert 'new_socket="${runtime_dir}/tmux-${uid}/default"' in function
    assert 'host_socket="/tmp/tmux-${uid}/default"' in function
    assert 'namespace_socket="/proc/${main_pid}/root/tmp/tmux-${uid}/default"' in function
    assert "claude-tele/default" not in function


def test_legacy_tmux_detection_noops_when_service_is_not_installed(tmp_path: Path) -> None:
    result, probes = run_legacy_detection(tmp_path, "#!/bin/sh\nexit 1\n")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert probes == ["-S /run/user/424242/claude-tele/tmux-424242/default has-session -t telegram-claude|"]


def test_legacy_tmux_detection_warns_for_host_socket_and_skips_unreadable_proc_root(tmp_path: Path) -> None:
    result, probes = run_legacy_detection(
        tmp_path,
        "#!/bin/sh\n"
        "case \"${2:-}\" in\n"
        "  cat) exit 0 ;;\n"
        "  show) echo \"$DETECTOR_PID\"; exit 0 ;;\n"
        "esac\n"
        "exit 1\n",
    )

    assert result.returncode == 0, result.stderr
    assert "LEGACY-SOCKET SESSION DETECTED at /tmp/tmux-424242/default" in result.stderr
    assert "Migrating a legacy-socket session" in result.stderr
    assert len(probes) == 2
    assert probes[0] == "-S /run/user/424242/claude-tele/tmux-424242/default has-session -t telegram-claude|"
    assert probes[1] == "-S /tmp/tmux-424242/default has-session -t telegram-claude|"
