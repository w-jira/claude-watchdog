import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "bin" / "claude-tele-watchdog"
UUID_OLD = "11111111-1111-4111-8111-111111111111.jsonl"
UUID_NEW = "22222222-2222-4222-8222-222222222222.jsonl"


def write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def watchdog_env(tmp_path: Path, **overrides: str) -> tuple[dict[str, str], Path, Path]:
    home = tmp_path / "home"
    state = home / ".claude" / "channels" / "telegram"
    fake_bin = tmp_path / "bin"
    state.mkdir(parents=True)
    fake_bin.mkdir(parents=True)
    write_executable(fake_bin / "logger", "#!/bin/sh\nexit 0\n")
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "WATCHDOG_SOURCE_ONLY": "1",
            "WATCHDOG_WARMUP": "0",
        }
    )
    env.update(overrides)
    return env, home, fake_bin


def transcript_dir(home: Path) -> Path:
    workdir = home / ".claude" / "channels" / "telegram" / "workdir"
    slug = str(workdir).replace("/", "-").replace(".", "-")
    path = home / ".claude" / "projects" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def assistant_usage(input_tokens=0, cache_creation=0, cache_read=0) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        },
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def run_function(env: dict[str, str], body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", 'source "$1"; shift; eval "$*"', "bash", str(WATCHDOG), body],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


def test_meter_present_parse(tmp_path: Path) -> None:
    env, _, _ = watchdog_env(tmp_path)
    result = run_function(env, "extract_pct $'workdir █████░░░ 37%\\n❯'")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37"


def test_meter_absent_falls_back_to_transcript(tmp_path: Path) -> None:
    env, home, _ = watchdog_env(tmp_path)
    write_jsonl(transcript_dir(home) / UUID_NEW, [assistant_usage(100_000, 50_000, 100_000)])

    result = run_function(env, "current_context_signal 'plain pane without meter'")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "25 transcript"


def test_newest_uuid_transcript_is_selected(tmp_path: Path) -> None:
    env, home, _ = watchdog_env(tmp_path)
    directory = transcript_dir(home)
    old = directory / UUID_OLD
    new = directory / UUID_NEW
    ignored = directory / "not-a-uuid.jsonl"
    write_jsonl(old, [assistant_usage(900_000)])
    write_jsonl(new, [assistant_usage(300_000)])
    write_jsonl(ignored, [assistant_usage(990_000)])
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))
    os.utime(ignored, (300, 300))

    result = run_function(env, "transcript_pct")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "30"


def test_usage_math_honors_context_tokens_override_and_last_parseable_usage(tmp_path: Path) -> None:
    env, home, _ = watchdog_env(tmp_path, WATCHDOG_CONTEXT_TOKENS="500000")
    write_jsonl(
        transcript_dir(home) / UUID_NEW,
        [
            assistant_usage(10_000),
            {"type": "assistant", "message": {"role": "assistant"}},
            assistant_usage(100_000, 50_000, 100_001),
            {"type": "assistant", "message": {"role": "assistant", "usage": None}},
        ],
    )

    result = run_function(env, "transcript_pct")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "51"


def test_both_sources_empty_warns_and_is_rate_limited(tmp_path: Path) -> None:
    env, _, fake_bin = watchdog_env(tmp_path)
    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "if [ \"$1\" = capture-pane ]; then printf '❯\\n'; exit 0; fi\n"
        "exit 0\n",
    )

    result = run_function(env, "check_context_compaction; check_context_compaction")

    message = "no context signal (meter absent, transcript unreadable) — compaction cannot fire"
    assert result.returncode == 0, result.stderr
    assert result.stdout.count(message) == 1
    state = Path(env["HOME"]) / ".claude" / "channels" / "telegram" / "watchdog.state"
    assert "context_source=unavailable" in state.read_text(encoding="utf-8")


def test_threshold_crossing_sends_compact(tmp_path: Path) -> None:
    tmux_log = tmp_path / "tmux.log"
    env, _, fake_bin = watchdog_env(
        tmp_path,
        WATCHDOG_THRESHOLD="25",
        WATCHDOG_COOLDOWN="0",
        WATCHDOG_VERIFY_AFTER="0",
        CLAUDE_TELE_DISABLE_E2E_INJECTION_GATE="1",
        TMUX_LOG=str(tmux_log),
    )
    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$TMUX_LOG\"\n"
        "if [ \"$1\" = capture-pane ]; then printf 'workdir █████░░░ 30%%\\n❯\\n'; fi\n"
        "exit 0\n",
    )

    result = run_function(env, "check_context_compaction; wait")

    assert result.returncode == 0, result.stderr
    assert "send-keys -t telegram-claude -- /compact Enter" in tmux_log.read_text(encoding="utf-8")
    state = Path(env["HOME"]) / ".claude" / "channels" / "telegram" / "watchdog.state"
    state_text = state.read_text(encoding="utf-8")
    assert "context_pct=30" in state_text
    assert "context_source=meter" in state_text
    assert "last_compact=0" not in state_text


def test_failed_capture_is_unknown_and_never_authorizes_compaction(tmp_path: Path) -> None:
    tmux_log = tmp_path / "tmux.log"
    env, home, fake_bin = watchdog_env(
        tmp_path,
        WATCHDOG_THRESHOLD="25",
        WATCHDOG_COOLDOWN="0",
        CLAUDE_TELE_DISABLE_E2E_INJECTION_GATE="1",
        TMUX_LOG=str(tmux_log),
    )
    write_jsonl(transcript_dir(home) / UUID_NEW, [assistant_usage(800_000)])
    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$TMUX_LOG\"\n"
        "if [ \"$1\" = capture-pane ]; then exit 1; fi\n"
        "exit 0\n",
    )

    result = run_function(env, "check_context_compaction")

    assert result.returncode == 0, result.stderr
    assert "pane state unknown" in result.stdout
    assert "send-keys" not in tmux_log.read_text(encoding="utf-8")
