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
