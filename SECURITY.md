# Security Policy

## Sensitive files

Never commit:

- `~/.claude/channels/telegram/.env`
- `~/.claude/channels/telegram/access.json`
- `~/.claude/channels/telegram/inbox/`
- `~/.claude/channels/telegram/*.jsonl`
- Claude transcripts under `~/.claude/projects/`
- Runtime PID, lock, heartbeat, compact, and watchdog state files
- Claude plugin cache directories

## Operational constraints

Telegram Bot API allows one active long-polling consumer per bot token. A second Claude Telegram channel can terminate or steal the managed poller.

Use:

```bash
claude-tele status
claude-tele doctor
```

before recovery work.

## Public-release checks

Before publishing changes:

```bash
./tests/validate.sh
git status --short
git log --oneline --decorate --max-count=10
```

Do not publish if validation reports secrets, personal infrastructure strings, runtime files, or local-only paths.
