import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "bin" / "claude-tele-watchdog"
UUID_OLD = "11111111-1111-4111-8111-111111111111.jsonl"
UUID_NEW = "22222222-2222-4222-8222-222222222222.jsonl"
UUID_OLDEST = "00000000-0000-4000-8000-000000000000.jsonl"


def write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def watchdog_env(tmp_path: Path, **overrides: str) -> tuple[dict[str, str], Path, Path]:
    home = tmp_path / "home"
    state = home / ".claude" / "channels" / "telegram"
    fake_bin = tmp_path / "bin"
    runtime = tmp_path / "run"
    state.mkdir(parents=True, exist_ok=True)
    fake_bin.mkdir(parents=True)
    runtime.mkdir()
    write_executable(fake_bin / "logger", "#!/bin/sh\nexit 0\n")
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "XDG_RUNTIME_DIR": str(runtime),
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


def assistant_usage(input_tokens=0, cache_creation=0, cache_read=0, output_tokens=0) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tokens,
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


def run_compaction_case(
    tmp_path: Path,
    pane: str,
    *,
    threshold: str = "25",
    hard_ceiling: str = "45",
    **env_overrides: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    tmux_log = tmp_path / "tmux.log"
    pane_file = tmp_path / "pane.txt"
    pane_file.write_text(pane, encoding="utf-8")
    env, _, fake_bin = watchdog_env(
        tmp_path,
        WATCHDOG_THRESHOLD=threshold,
        WATCHDOG_HARD_CEILING=hard_ceiling,
        WATCHDOG_COOLDOWN="0",
        WATCHDOG_VERIFY_AFTER="0",
        CLAUDE_TELE_DISABLE_E2E_INJECTION_GATE="1",
        TMUX_LOG=str(tmux_log),
        PANE_FILE=str(pane_file),
        **env_overrides,
    )
    write_executable(
        fake_bin / "tmux",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$TMUX_LOG\"\n"
        "if [ \"$1\" = capture-pane ]; then cat \"$PANE_FILE\"; fi\n"
        "exit 0\n",
    )

    result = run_function(env, "check_context_compaction; wait")
    return result, tmux_log.read_text(encoding="utf-8")


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
            assistant_usage(100_000, 50_000, 100_001, 49_999),
            {"type": "assistant", "message": {"role": "assistant", "usage": None}},
        ],
    )

    result = run_function(env, "transcript_pct")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "60"


def test_empty_newest_transcript_falls_back_to_previous_session(tmp_path: Path) -> None:
    env, home, _ = watchdog_env(tmp_path)
    directory = transcript_dir(home)
    old = directory / UUID_OLD
    new = directory / UUID_NEW
    write_jsonl(old, [assistant_usage(300_000)])
    new.write_text("", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))

    result = run_function(env, "transcript_pct")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "30"


def test_transcript_scan_does_not_reach_third_newest_candidate(tmp_path: Path) -> None:
    env, home, _ = watchdog_env(tmp_path)
    directory = transcript_dir(home)
    oldest = directory / UUID_OLDEST
    middle = directory / UUID_OLD
    newest = directory / UUID_NEW
    write_jsonl(oldest, [assistant_usage(700_000)])
    middle.write_text("", encoding="utf-8")
    newest.write_text("", encoding="utf-8")
    os.utime(oldest, (100, 100))
    os.utime(middle, (200, 200))
    os.utime(newest, (300, 300))

    result = run_function(env, "transcript_pct")

    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_transcript_scan_is_bounded_when_usage_is_far_from_tail(tmp_path: Path) -> None:
    env, home, _ = watchdog_env(tmp_path)
    path = transcript_dir(home) / UUID_NEW
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(assistant_usage(900_000)) + "\n")
        handle.write(json.dumps({"type": "user", "padding": "x" * (5 * 1024 * 1024)}) + "\n")

    result = run_function(env, "transcript_pct")

    assert result.returncode != 0
    assert result.stdout.strip() == ""


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


def test_pane_idle_keys_on_turn_timer_not_footer(tmp_path: Path) -> None:
    env, _, _ = watchdog_env(tmp_path)
    idle = run_function(env, "pane_idle $'status\\n❯\\302\\240\\nshortcuts footer\\n'")
    # The standing footer (background tasks) must NOT read as busy: main prompt idle.
    idle_bg = run_function(
        env,
        "pane_idle $'❯\\302\\240\\n⏵⏵ auto mode on · 1 shell · esc to interrupt · ← for agents\\n'",
    )
    # A live main turn shows the elapsed-timer parenthetical — that IS busy.
    busy = run_function(env, "pane_idle $'✻ Working… (33s · ↓ 1.1k tokens)\\n❯\\302\\240\\n'")
    empty = run_function(env, "pane_idle $'  \\n\\t\\n'")

    assert idle.returncode == 0, idle.stderr
    assert idle_bg.returncode == 0, idle_bg.stderr
    assert busy.returncode != 0
    assert empty.returncode != 0


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


def test_ambiguous_nonempty_pane_without_prompt_never_authorizes_compaction(tmp_path: Path) -> None:
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
        "if [ \"$1\" = capture-pane ]; then printf 'Unrecognized active renderer\\n'; fi\n"
        "exit 0\n",
    )

    result = run_function(env, "check_context_compaction")

    assert result.returncode == 0, result.stderr
    assert "session busy" in result.stdout
    assert "send-keys" not in tmux_log.read_text(encoding="utf-8")


def test_busy_session_below_hard_ceiling_does_not_send(tmp_path: Path) -> None:
    result, tmux_log = run_compaction_case(
        tmp_path,
        "workdir █████░░░ 40%\n✻ Working… (33s · ↓ 1.1k tokens)\n❯\u00a0\n",
    )

    assert result.returncode == 0, result.stderr
    assert "context high but session busy" in result.stdout
    assert "send-keys" not in tmux_log


def test_hard_ceiling_sends_when_busy_input_box_is_visible(tmp_path: Path) -> None:
    result, tmux_log = run_compaction_case(
        tmp_path,
        "workdir █████░░░ 46%\n✻ Working… (33s · ↓ 1.1k tokens)\n❯\u00a0\n",
    )

    assert result.returncode == 0, result.stderr
    assert "hard ceiling breached — compacting despite busy session" in result.stdout
    assert "ctx=46% ceiling=45%" in result.stdout
    assert "send-keys -t telegram-claude -- /compact Enter" in tmux_log


def test_hard_ceiling_does_not_send_into_modal_without_bare_prompt(tmp_path: Path) -> None:
    result, tmux_log = run_compaction_case(
        tmp_path,
        "workdir █████░░░ 46%\nPermission required\n❯ 1. Yes\n",
    )

    assert result.returncode == 0, result.stderr
    assert "context high but session busy" in result.stdout
    assert "send-keys" not in tmux_log


def test_elevated_grace_forces_compact_during_long_busy_stretch(tmp_path: Path) -> None:
    # Context has sat >= threshold (below ceiling) while busy for longer than the
    # grace window -> force at the visible input prompt.
    state = tmp_path / "home" / ".claude" / "channels" / "telegram"
    state.mkdir(parents=True)
    (state / "watchdog.elevated-since").write_text("1000000000\n", encoding="utf-8")
    result, tmux_log = run_compaction_case(
        tmp_path,
        "workdir █████░░░ 40%\n✻ Working… (33s · ↓ 1.1k tokens)\n❯\u00a0\n",
        WATCHDOG_ELEVATED_GRACE="60",
    )

    assert result.returncode == 0, result.stderr
    assert "context elevated past grace — compacting despite busy session" in result.stdout
    assert "send-keys -t telegram-claude -- /compact Enter" in tmux_log


def test_elevated_grace_zero_disables_the_force(tmp_path: Path) -> None:
    state = tmp_path / "home" / ".claude" / "channels" / "telegram"
    state.mkdir(parents=True)
    (state / "watchdog.elevated-since").write_text("1000000000\n", encoding="utf-8")
    result, tmux_log = run_compaction_case(
        tmp_path,
        "workdir █████░░░ 40%\n✻ Working… (33s · ↓ 1.1k tokens)\n❯\u00a0\n",
        WATCHDOG_ELEVATED_GRACE="0",
    )

    assert result.returncode == 0, result.stderr
    assert "context high but session busy" in result.stdout
    assert "send-keys" not in tmux_log


def test_hard_ceiling_not_above_threshold_is_disabled_with_warning(tmp_path: Path) -> None:
    result, tmux_log = run_compaction_case(
        tmp_path,
        "workdir █████░░░ 46%\n✻ Working… (33s · ↓ 1.1k tokens)\n❯\u00a0\n",
        threshold="45",
        hard_ceiling="45",
    )

    assert result.returncode == 0, result.stderr
    assert "must be greater than WATCHDOG_THRESHOLD" in result.stdout
    assert "hard-ceiling escalation disabled" in result.stdout
    assert "send-keys" not in tmux_log
