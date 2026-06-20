import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap.sh"


def run(cmd, cwd=None, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def make_source_repo(tmp_path):
    src = tmp_path / "source"
    (src / "bin").mkdir(parents=True)
    (src / "bin" / "dog").write_text("#!/bin/bash\nprintf 'setup-ran\\n' > \"$1\"\n", encoding="utf-8")
    (src / "bin" / "dog").chmod(0o700)
    run(["git", "init"], cwd=src)
    run(["git", "config", "user.email", "test@example.invalid"], cwd=src)
    run(["git", "config", "user.name", "Test User"], cwd=src)
    run(["git", "add", "."], cwd=src)
    run(["git", "commit", "-m", "initial"], cwd=src)
    return src


def test_bootstrap_clones_repo_and_can_skip_setup_for_ci(tmp_path):
    src = make_source_repo(tmp_path)
    install_dir = tmp_path / "install"

    result = run([
        "bash",
        str(BOOTSTRAP),
    ], env={
        "CLAUDE_WATCHDOG_REPO_URL": str(src),
        "CLAUDE_WATCHDOG_INSTALL_DIR": str(install_dir),
        "CLAUDE_WATCHDOG_SKIP_SETUP": "1",
    })

    assert (install_dir / ".git").is_dir()
    assert (install_dir / "bin" / "dog").is_file()
    assert "skipping setup" in result.stdout


def test_bootstrap_refuses_non_git_install_dir(tmp_path):
    src = make_source_repo(tmp_path)
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / "note.txt").write_text("not a repo", encoding="utf-8")

    result = subprocess.run([
        "bash",
        str(BOOTSTRAP),
    ], env={
        **os.environ,
        "CLAUDE_WATCHDOG_REPO_URL": str(src),
        "CLAUDE_WATCHDOG_INSTALL_DIR": str(install_dir),
    }, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    assert result.returncode != 0
    assert "exists but is not a git checkout" in result.stderr
