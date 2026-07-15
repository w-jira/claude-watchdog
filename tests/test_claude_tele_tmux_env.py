import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_TELE = ROOT / "bin" / "claude-tele"
WATCHDOG = ROOT / "bin" / "claude-tele-watchdog"
FIXTURES = ROOT / "tests" / "fixtures"


def write_executable(path: Path, body: str):
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def shell_function(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def run_pane_idle(path: Path, pane: str, locale: str) -> subprocess.CompletedProcess[str]:
    body = "\n".join(
        shell_function(path, name)
        for name in ("pane_normalize", "pane_has_bare_prompt", "pane_idle")
    )
    env = os.environ.copy()
    env.update({"LANG": locale, "LC_ALL": locale})
    return subprocess.run(
        ["bash", "-c", f'{body}\npane_idle "$1"', "bash", pane],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_status_ignores_inherited_tmux_environment(tmp_path):
    fake_bin = tmp_path / "bin"
    home = tmp_path / "home"
    runtime = tmp_path / "run"
    fake_bin.mkdir()
    runtime.mkdir()
    (home / ".local" / "bin").mkdir(parents=True)

    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "if [ -n \"${TMUX:-}\" ]; then echo inherited TMUX >&2; exit 42; fi\n"
        "if [ \"${TMUX_TMPDIR:-}\" != \"${EXPECTED_TMUX_TMPDIR:-}\" ]; then echo wrong TMUX_TMPDIR >&2; exit 43; fi\n"
        "if [ ! -d \"${TMUX_TMPDIR:-/missing}\" ]; then echo missing TMUX_TMPDIR >&2; exit 44; fi\n"
        "case \"$1\" in\n"
        "  has-session) exit 0 ;;\n"
        "  list-panes) echo 12345; exit 0 ;;\n"
        "  capture-pane) exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )
    write_executable(
        fake_bin / "systemctl",
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--user\" ] && [ \"$2\" = \"is-active\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"--user\" ] && [ \"$2\" = \"is-enabled\" ]; then exit 0; fi\n"
        "exit 0\n",
    )
    write_executable(fake_bin / "flock", "#!/bin/sh\nexit 0\n")
    write_executable(home / ".local" / "bin" / "claude", "#!/bin/sh\nexit 0\n")

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "PATH": f"{fake_bin}:{env['PATH']}",
        "TMUX": "/tmp/not-the-watchdog-socket",
        "XDG_RUNTIME_DIR": str(runtime),
        "EXPECTED_TMUX_TMPDIR": str(runtime / "claude-tele"),
    })
    result = subprocess.run(
        [str(CLAUDE_TELE), "status"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "tmux:     'telegram-claude' present" in result.stdout
    assert "inherited TMUX" not in result.stderr


@pytest.mark.parametrize("path", [CLAUDE_TELE, WATCHDOG], ids=["claude-tele", "watchdog"])
@pytest.mark.parametrize("locale", ["en_US.UTF-8", "C"])
def test_pane_idle_normalizes_real_prompt_and_fails_closed(path: Path, locale: str):
    busy = (FIXTURES / "pane_busy_real.txt").read_text(encoding="utf-8")
    idle = (FIXTURES / "pane_idle_real.txt").read_text(encoding="utf-8")
    cases = [
        (busy, False),
        (idle, True),
        ("❯\n", True),
        ("permission required\n❯ 1. Yes\n", False),
        ("❯ some text\n", False),
        ("", False),
    ]

    for pane, expected_idle in cases:
        result = run_pane_idle(path, pane, locale)
        assert (result.returncode == 0) is expected_idle, (
            f"{path.name} under {locale} returned {result.returncode} for {pane!r}: "
            f"{result.stderr}"
        )


def test_startup_wait_uses_nbsp_aware_prompt_scan():
    text = CLAUDE_TELE.read_text(encoding="utf-8")

    assert 'if pane_has_bare_prompt "$pane"; then' in text
