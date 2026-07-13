import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_TELE = ROOT / "bin" / "claude-tele"


def write_executable(path: Path, body: str):
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def shell_function(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def run_pane_idle(pane: str) -> subprocess.CompletedProcess[str]:
    body = shell_function(CLAUDE_TELE, "pane_idle")
    return subprocess.run(
        ["bash", "-c", f'{body}\npane_idle "$1"', "bash", pane],
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


def test_pane_idle_requires_prompt_as_final_nonblank_line_and_fails_closed():
    idle = run_pane_idle("status\n❯\n\n")
    status_below = run_pane_idle("status\n❯\nWorking…\n")
    empty = run_pane_idle("  \n\t\n")

    assert idle.returncode == 0, idle.stderr
    assert status_below.returncode != 0
    assert empty.returncode != 0


def test_startup_wait_keeps_broader_prompt_scan():
    text = CLAUDE_TELE.read_text(encoding="utf-8")

    assert "printf '%s\\n' \"$pane\" | tail -6 | grep -qE '^❯[[:space:]]*$'" in text
