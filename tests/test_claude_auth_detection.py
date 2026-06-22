import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_TELE = ROOT / "bin" / "claude-tele"
WATCHDOG = ROOT / "bin" / "claude-tele-watchdog"


def write_executable(path: Path, body: str):
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def base_env(tmp_path: Path, pane_text: str = "❯\n", has_session: bool = True):
    fake_bin = tmp_path / "bin"
    home = tmp_path / "home"
    state = home / ".claude" / "channels" / "telegram"
    fake_bin.mkdir()
    (home / ".local" / "bin").mkdir(parents=True)
    state.mkdir(parents=True)
    (state / ".env").write_text("TELEGRAM_BOT_TOKEN_ENCRYPTED=0\n", encoding="utf-8")
    (state / "access.json").write_text("{}\n", encoding="utf-8")
    (state / "plugin-health.json").write_text("{}\n", encoding="utf-8")
    (state / "bot.pid").write_text("999999\n", encoding="utf-8")
    (home / ".claude" / "plugins" / "cache" / "x" / "telegram").mkdir(parents=True)

    write_executable(home / ".local" / "bin" / "claude", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "flock", "#!/bin/sh\nexec /usr/bin/flock \"$@\"\n")
    write_executable(fake_bin / "bun", "#!/bin/sh\necho 1.0.0\n")
    write_executable(fake_bin / "loginctl", "#!/bin/sh\necho Linger=yes\n")
    write_executable(fake_bin / "logger", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "systemctl",
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--user\" ] && [ \"$2\" = \"is-active\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"--user\" ] && [ \"$2\" = \"is-enabled\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"--user\" ] && [ \"$2\" = \"restart\" ]; then echo restart >> \"$HOME/restarts.log\"; exit 0; fi\n"
        "exit 0\n",
    )
    tmux_has_session = "exit 0" if has_session else "exit 1"
    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        f"  has-session) {tmux_has_session} ;;\n"
        "  list-panes) echo 12345; exit 0 ;;\n"
        f"  capture-pane) printf '%s\\n' {pane_text!r}; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )

    env = os.environ.copy()
    env.update({"HOME": str(home), "PATH": f"{fake_bin}:{env['PATH']}"})
    return env, home, state


def test_status_flags_claude_auth_401_from_pane(tmp_path):
    env, _, _ = base_env(
        tmp_path,
        "Please run /login · API Error: 401 Invalid authentication credentials\n❯\n",
    )

    result = subprocess.run(
        [str(CLAUDE_TELE), "status"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "claude auth: expired / API 401" in result.stdout
    assert "run /login" in result.stdout


def test_status_flags_claude_auth_401_from_health(tmp_path):
    env, _, state = base_env(tmp_path, has_session=False)
    (state / "plugin-health.json").write_text(
        json.dumps({"last_claude_auth_error_at": 200, "last_claude_auth_ok_at": 100}) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(CLAUDE_TELE), "status"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "claude auth: expired / API 401" in result.stdout


def test_status_ignores_stale_transcript_auth_error_after_later_success(tmp_path):
    env, home, _ = base_env(tmp_path)
    workdir = home / ".claude" / "channels" / "telegram" / "workdir"
    slug = str(workdir).replace("/", "-").replace(".", "-")
    transcript_dir = home / ".claude" / "projects" / slug
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "session.jsonl").write_text(
        "\n".join([
            json.dumps({
                "timestamp": "2026-06-22T00:00:00.000Z",
                "message": {
                    "role": "assistant",
                    "model": "<synthetic>",
                    "content": [{"type": "text", "text": "Please run /login · API Error: 401 Invalid authentication credentials"}],
                },
            }),
            json.dumps({
                "timestamp": "2026-06-22T00:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-opus-4-8",
                    "content": [{"type": "text", "text": "auth restored"}],
                },
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(CLAUDE_TELE), "status"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "claude auth: no 401/login prompt detected" in result.stdout


def run_watchdog_once(env):
    return subprocess.run(
        ["timeout", "3", str(WATCHDOG)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def watchdog_env(env):
    env.update({
        "WATCHDOG_WARMUP": "0",
        "WATCHDOG_INTERVAL": "1",
        "WATCHDOG_GETME_EVERY": "999",
        "WATCHDOG_CLAUDE_AUTH_ALERT_COOLDOWN": "0",
    })
    return env


def test_watchdog_auth_failure_alerts_but_does_not_restart(tmp_path):
    env, home, state = base_env(
        tmp_path,
        "Please run /login · API Error: 401 Invalid authentication credentials\n❯\n",
    )

    run_watchdog_once(watchdog_env(env))

    health = json.loads((state / "plugin-health.json").read_text(encoding="utf-8"))
    assert health["last_error"] == "Claude auth expired: API Error 401; run /login"
    assert not (home / "restarts.log").exists()


def test_watchdog_health_auth_failure_suppresses_tmux_missing_heal(tmp_path):
    env, home, state = base_env(tmp_path, has_session=False)
    (state / "plugin-health.json").write_text(
        json.dumps({"last_claude_auth_error_at": 200, "last_claude_auth_ok_at": 100}) + "\n",
        encoding="utf-8",
    )

    run_watchdog_once(watchdog_env(env))

    health = json.loads((state / "plugin-health.json").read_text(encoding="utf-8"))
    assert health["last_error"] == "Claude auth expired: API Error 401; run /login"
    assert not (home / "restarts.log").exists()
