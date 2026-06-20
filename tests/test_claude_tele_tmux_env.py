import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_TELE = ROOT / "bin" / "claude-tele"


def write_executable(path: Path, body: str):
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_status_ignores_inherited_tmux_environment(tmp_path):
    fake_bin = tmp_path / "bin"
    home = tmp_path / "home"
    fake_bin.mkdir()
    (home / ".local" / "bin").mkdir(parents=True)

    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "if [ -n \"${TMUX:-}\" ]; then echo inherited TMUX >&2; exit 42; fi\n"
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
