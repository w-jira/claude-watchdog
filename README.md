# claude-watchdog

One-stop installer and watchdog for running Claude Code as an always-on Telegram bot.

`claude-watchdog` installs a user-systemd managed Claude Code Telegram session, keeps it alive, auto-compacts high-context sessions, and recovers common Telegram bridge failures.

## What it does

- Runs one Claude Code Telegram channel in `tmux` + `systemd --user`.
- Installs service files and helper scripts into the current user account.
- Optionally installs supported dependencies like `tmux`, `curl`, `unzip`, `git`, and a pinned Bun release.
- Keeps Telegram transcripts isolated in `~/.claude/channels/telegram/workdir`.
- Prevents/reports missing Telegram plugin bridge (`bun`) failures.
- Auto-compacts when context usage is high and Claude appears idle.
- Journals allowed inbound Telegram messages before MCP delivery.
- Replays journaled Telegram texts that are absent from Claude transcripts after restart.
- Optional least-privilege MCP helper can request only `/compact`.

## Requirements

Required before the bot can run:

- Linux with `systemd --user`
- Claude Code CLI installed and authenticated
- Telegram bot token from BotFather
- Your numeric Telegram user ID for the allowlist

The installer can handle these on Debian/Ubuntu when run with `--install-deps`:

- `tmux`
- `python3`
- `curl`
- `unzip`
- `git`
- `bun` pinned to `bun-v1.3.14` by default

Optional:

- `msmtp` for watchdog circuit-breaker email alerts
- `mcp` Python package if you want to run `bin/claude-tele-control-mcp.py`

## Fast path

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
TELEGRAM_BOT_TOKEN='replace-with-botfather-token' \
TELEGRAM_USER_ID='123456789' \
  ./install.sh --install-deps --start --yes
```

Then check:

```bash
claude-tele status
claude-tele logs
```

## Agent-friendly setup

If an AI agent is helping you install this, give it only these values:

- Telegram bot token
- Telegram user ID
- whether it may run `sudo apt-get install` for missing OS packages

Recommended agent command:

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install.sh --install-deps --start --yes
```

The installer is idempotent: re-running it updates scripts/services and preserves existing config unless token/user ID are explicitly provided.

## Manual setup

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
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

## Installer options

```bash
./install.sh --help
```

Options:

- `--install-deps`: install missing supported dependencies.
- `--token TOKEN`: write Telegram bot token.
- `--telegram-user-id ID`: write allowlist config.
- `--start`: start the bot after install.
- `--yes`: non-interactive yes for supported install steps.

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

Public HTTPS clone needs no GitHub login:

```bash
git clone https://github.com/w-jira/claude-watchdog.git
```

Or avoid GitHub entirely by copying a tarball over SSH:

```bash
tar -czf claude-watchdog.tar.gz claude-watchdog
scp claude-watchdog.tar.gz user@your-vm:~/
ssh user@your-vm 'tar -xzf claude-watchdog.tar.gz && cd claude-watchdog && ./install.sh'
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
