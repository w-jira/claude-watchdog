# claude-tele

Always-on Claude Code Telegram channel lifecycle tooling.

`claude-tele` runs a single managed Claude Code Telegram session under user-systemd, watches for common failure modes, auto-compacts when context is high, and can replay journaled Telegram messages missed during restarts.

## What it does

- Runs one Claude Code Telegram channel in `tmux` + `systemd --user`.
- Keeps Telegram transcripts isolated in `~/.claude/channels/telegram/workdir`.
- Prevents/reports missing Telegram plugin bridge (`bun`) failures.
- Auto-compacts when context usage is high and Claude appears idle.
- Journals allowed inbound Telegram messages before MCP delivery.
- Replays journaled Telegram texts that are absent from Claude transcripts after restart.
- Optional least-privilege MCP helper can request only `/compact`.

## Requirements

- Linux with `systemd --user`
- `claude` CLI installed and authenticated
- `tmux`
- Python 3.11+
- Telegram bot token from BotFather
- Claude Telegram channel plugin: `plugin:telegram@claude-plugins-official`

Optional:

- `msmtp` for watchdog circuit-breaker email alerts
- `mcp` Python package if you want to run `bin/claude-tele-control-mcp.py`

## Quick start

```bash
git clone https://github.com/YOUR_USER/claude-tele.git
cd claude-tele
./install.sh
```

Then edit:

```bash
nano ~/.claude/channels/telegram/.env
nano ~/.claude/channels/telegram/access.json
```

Example `.env`:

```bash
TELEGRAM_BOT_TOKEN=replace-with-botfather-token
```

Example `access.json`:

```json
{
  "dmPolicy": "allowlist",
  "allowFrom": ["123456789"],
  "groups": {},
  "pending": {},
  "ackReaction": "👀",
  "replyToMode": "first",
  "textChunkLimit": 4096,
  "chunkMode": "newline"
}
```

Start it:

```bash
claude-tele doctor
claude-tele start
claude-tele status
```

## Commands

```bash
claude-tele start
claude-tele stop
claude-tele restart
claude-tele status
claude-tele attach
claude-tele logs [-f]
claude-tele heal
claude-tele compact [--json] [--force]
claude-tele replay-missed [--dry-run]
claude-tele doctor
```

## No GitHub login on the VM

If this repo is public, the VM does not need GitHub authentication:

```bash
git clone https://github.com/YOUR_USER/claude-tele.git
```

Or avoid GitHub entirely by copying a tarball over SSH:

```bash
tar -czf claude-tele.tar.gz claude-tele
scp claude-tele.tar.gz user@your-vm:~/
ssh user@your-vm 'tar -xzf claude-tele.tar.gz && cd claude-tele && ./install.sh'
```

## Safety rules

- Never run another `claude --channels plugin:telegram@claude-plugins-official` poller with the same bot token.
- Do not commit `.env`, `access.json`, transcripts, `inbox/`, PID/lock files, or Claude plugin cache contents.
- Keep the service `WorkingDirectory` stable unless intentionally starting a new transcript lineage.
- Use a dedicated Telegram bot token for this service.

## Watchdog tuning

Edit `~/.config/systemd/user/telegram-claude-watchdog.service`, then run:

```bash
systemctl --user daemon-reload
claude-tele restart
```

Useful environment variables:

```ini
Environment=WATCHDOG_THRESHOLD=40
Environment=WATCHDOG_INTERVAL=300
Environment=WATCHDOG_GETME_EVERY=3
Environment=WATCHDOG_WARMUP=60
Environment=WATCHDOG_ALERT_EMAIL=you@example.com
Environment=WATCHDOG_ALERT_FROM=claude-tele-watchdog@example.com
Environment=WATCHDOG_MSMTP_ACCOUNT=default
```

Email alerts are disabled unless `WATCHDOG_ALERT_EMAIL` is set.

## Validation

```bash
./tests/validate.sh
```

This checks shell syntax, Python syntax, user-systemd unit validity, and common secret/personal-infra leaks.
