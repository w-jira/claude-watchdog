import json
import os
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = ROOT / "package.json"


def run(cmd, cwd=ROOT, env=None):
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


def test_package_json_exposes_dog_cli_without_install_scripts():
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert pkg["name"] == "@wjira/claude-watchdog"
    assert pkg["bin"] == {"dog": "bin/dog"}
    assert "preinstall" not in pkg.get("scripts", {})
    assert "postinstall" not in pkg.get("scripts", {})
    assert pkg["files"] == [
        "bin/",
        "!bin/__pycache__/",
        "!**/*.pyc",
        "config/",
        "systemd/",
        "install.sh",
        "install-macos.sh",
        "README.md",
        "docs/",
        "SECURITY.md",
        "LICENSE",
    ]


def test_npm_pack_contains_runtime_assets_and_no_runtime_state(tmp_path):
    result = run(["npm", "pack", "--json", "--pack-destination", str(tmp_path)])
    pack_info = json.loads(result.stdout)[0]
    tarball = tmp_path / pack_info["filename"]

    with tarfile.open(tarball) as tf:
        names = set(tf.getnames())

    required = {
        "package/package.json",
        "package/bin/dog",
        "package/bin/claude-tele",
        "package/bin/claude-tele-watchdog",
        "package/install.sh",
        "package/systemd/user/telegram-claude.service",
        "package/systemd/user/telegram-claude-watchdog.service",
        "package/config/env.example",
        "package/config/access.example.json",
    }
    assert required <= names

    forbidden_suffixes = (
        ".env",
        ".token.enc",
        ".token.key",
        ".pyc",
        "access.json",
        "inbound-journal.jsonl",
        "replayed-inbound.jsonl",
    )
    assert not any(name.endswith(forbidden_suffixes) for name in names)
    assert not any("__pycache__" in name for name in names)
