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

## Platform support

- **Linux:** full support via `systemd --user` + `tmux` + watchdog auto-heal/auto-compact.
- **macOS:** beta support via LaunchAgent + `tmux`. Runs the Telegram bot at login and supports `start`, `stop`, `restart`, `status`, `attach`, `logs`, `heal`, and `doctor`. Auto-compact watchdog parity is not implemented yet.
- **Windows:** beta native support via PowerShell + Scheduled Task. Runs/restarts Claude at logon and supports `start`, `stop`, `restart`, `status`, `logs`, and `doctor`. First-run Claude trust/permissions prompts may need to be accepted once interactively. Native Windows beta intentionally does not use `--continue` yet to avoid resuming an unrelated interactive Windows transcript; WSL2 remains the recommended Windows path for Linux-equivalent behavior, including full watchdog/tmux parity.

## Requirements

Required before the bot can run:

- Claude Code CLI installed and authenticated
- Telegram bot token from BotFather
- Your numeric Telegram user ID for the allowlist

Linux full mode also requires:

- Linux with `systemd --user`

The Linux installer can handle these on Debian/Ubuntu when run with `--install-deps`:

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

### Linux

Interactive setup app (recommended because the bot token is hidden and never passed as a command-line argument):

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
./bin/cwd setup
```

Agent/non-interactive:

```bash
TELEGRAM_BOT_TOKEN='replace-with-botfather-token' \
TELEGRAM_USER_ID='123456789' \
  ./install.sh --install-deps --permission-mode default --demo --start --yes
```

### macOS

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
TELEGRAM_BOT_TOKEN='replace-with-botfather-token' \
TELEGRAM_USER_ID='123456789' \
  ./install-macos.sh --install-deps --permission-mode default --demo --start --yes
```

### Windows PowerShell

```powershell
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
$env:TELEGRAM_BOT_TOKEN = "replace-with-botfather-token"
$env:TELEGRAM_USER_ID = "123456789"
.\install-windows.ps1 -InstallDeps -PermissionMode default -Demo -Start -Yes
```

On Windows, if Claude exits or hangs on a first-run trust/permissions prompt, run this once in an interactive terminal from `%USERPROFILE%\.claude\channels\telegram\workdir`, accept the prompts, then restart the task:

```powershell
claude --dangerously-skip-permissions --channels plugin:telegram@claude-plugins-official
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" restart
```

Then check:

Linux/macOS:

```bash
claude-tele status
claude-tele logs
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" status
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" logs
```

## Agent-friendly setup

If an AI agent is helping you install this, give it only these values:

- Target OS: Linux, macOS, Windows native, or Windows WSL2
- Telegram bot token
- Telegram user ID
- whether it may install missing dependencies (`sudo apt-get` on Debian/Ubuntu, Homebrew on macOS, winget on Windows)

Recommended Linux agent command:

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install.sh --install-deps --permission-mode default --demo --start --yes
```

Recommended macOS agent command:

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install-macos.sh --install-deps --permission-mode default --demo --start --yes
```

Recommended Windows PowerShell agent command:

```powershell
$env:TELEGRAM_BOT_TOKEN = "<bot-token>"
$env:TELEGRAM_USER_ID = "<telegram-user-id>"
.\install-windows.ps1 -InstallDeps -PermissionMode default -Demo -Start -Yes
```

The installers are idempotent: re-running them updates scripts/services and preserves existing config unless token/user ID are explicitly provided.

## Manual setup

Linux:

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
./install.sh
```

macOS:

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
./install-macos.sh
```

Windows PowerShell:

```powershell
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
.\install-windows.ps1
```

Then edit:

```bash
nano ~/.claude/channels/telegram/.env
nano ~/.claude/channels/telegram/access.json
```

Example `.env`:

```bash
TELEGRAM_BOT_TOKEN=replace-with-botfather-token
CLAUDE_PERMISSION_MODE=default
CLAUDE_WATCHDOG_DEMO=0
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

Linux:

```bash
./install.sh --help
```

macOS:

```bash
./install-macos.sh --help
```

Windows:

```powershell
Get-Help .\install-windows.ps1
```

Common options:

- `--install-deps` / `-InstallDeps`: install missing supported dependencies.
- `--token TOKEN` / `-Token TOKEN`: write Telegram bot token. Prefer `./bin/cwd setup` so the token is hidden and not placed in shell history or process arguments.
- `--telegram-user-id ID` / `-TelegramUserId ID`: write allowlist config.
- `--permission-mode MODE` / `-PermissionMode MODE`: choose Claude permissions (`default`, `plan`, `acceptEdits`, `auto`, `dontAsk`, or `bypassPermissions`). Use `default` for safe demos; use `bypassPermissions` only in sandboxes.
- `--demo` / `-Demo`: hide sensitive runtime details in status output and block logs unless explicitly requested raw.
- `--start` / `-Start`: start the bot after install.
- `--yes` / `-Yes`: non-interactive yes for supported install steps.

Linux/macOS also support `./bin/cwd setup`, a small interactive CLI app for token, Telegram user ID, permission level, demo mode, dependency install, and start/no-start. It reads the bot token with hidden input, writes config files with `0600` permissions, and does not pass the token as a command-line argument.

## Commands

Friendly CLI:

```bash
cwd setup
cwd status
cwd start
cwd stop
cwd restart
cwd doctor
```

Linux full mode:

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

macOS beta mode:

```bash
claude-tele start
claude-tele stop
claude-tele restart
claude-tele status
claude-tele attach
claude-tele logs [-f]
claude-tele heal
claude-tele doctor
```

Windows beta mode:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" start
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" stop
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" restart
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" status
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" logs
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" doctor
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
