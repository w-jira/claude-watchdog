import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOG = ROOT / "bin" / "dog"


def write_executable(path: Path, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_dog_status_prefers_installed_home_engine_over_stale_path(tmp_path):
    home = tmp_path / "home"
    stale = tmp_path / "stale" / "bin"
    home_bin = home / "bin"

    write_executable(
        stale / "claude-tele",
        "#!/bin/sh\necho stale-engine\nexit 0\n",
    )
    write_executable(
        home_bin / "claude-tele",
        "#!/bin/sh\necho home-engine \"$@\"\nexit 0\n",
    )

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "PATH": f"{stale}:{home_bin}:{env['PATH']}",
    })
    result = subprocess.run(
        [str(DOG), "status"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "home-engine status" in result.stdout
    assert "stale-engine" not in result.stdout


def test_dog_status_reports_watchdog_context_state(tmp_path):
    home = tmp_path / "home"
    home_bin = home / "bin"
    state = home / ".claude" / "channels" / "telegram"
    state.mkdir(parents=True)
    write_executable(home_bin / "claude-tele", "#!/bin/sh\necho engine-status\n")
    (state / "watchdog.state").write_text(
        "context_pct=42\ncontext_source=transcript\nlast_compact=1000000000\nupdated_at=1000000001\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"HOME": str(home), "PATH": f"{home_bin}:{env['PATH']}"})

    result = subprocess.run(
        [str(DOG), "status"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "watchdog context: 42% (source: transcript)" in result.stdout
    assert "watchdog last compact:" in result.stdout
