# claude-watchdog

Run Claude Code from Telegram without babysitting a terminal.

`claude-watchdog` sets up one always-on Claude Code session, connected through Anthropic's official Telegram plugin. It installs the service, keeps the bot alive, protects the setup flow from common token leaks, and gives you a small CLI for day-to-day operations.

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
./bin/dog setup
```

After install:

```bash
dog status
dog logs
dog restart
```

## Why this exists

Claude Code already has a Telegram plugin. The hard part is running it safely for more than five minutes.

This repo handles the boring production bits:

- one Telegram poller per bot token
- automatic restart after crashes
- isolated workdir so Telegram does not hijack your normal Claude session
- secure setup wizard for bot token and allowlist config
- demo mode that hides logs and local runtime details while you present
- Linux watchdog support for health checks, missed-message replay, and context compaction

## Recommended setup

Use the CLI wizard. It keeps the bot token out of shell history and command arguments.

```bash
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
./bin/dog setup
```

The wizard asks for:

- Telegram bot token from BotFather
- your Telegram user ID, which it can auto-detect by asking you to send a one-time test message to the bot
- Claude permission mode
- demo mode on/off
- whether to install missing dependencies
- whether to start the bot immediately

By default, `dog setup` encrypts the Telegram token at rest when OpenSSL is available. The runtime service decrypts it only when starting Claude and passes it through the process environment, where the official plugin can read it. If OpenSSL is missing, setup falls back to a private `0600` `.env` file and prints a warning.

The Linux/macOS encryption key is stored in the same private state directory as the encrypted token. This removes the token from `.env` and casual text exposure, but it does not protect against malware, a compromised OS account, or backups that include both `.token.enc` and `.token.key`.

## Daily commands

```bash
dog help       # friendly command menu
dog setup      # guided setup or reconfiguration
dog status     # service + bot status
dog start      # start the bot
dog stop       # stop the bot
dog restart    # restart the bot
dog doctor     # diagnostics
dog logs       # logs; blocked in demo mode unless raw is requested
```

Linux still exposes the lower-level power-user CLI:

```bash
claude-tele compact --json
claude-tele replay-missed --dry-run
claude-tele attach
```

## Platform support

- Linux: full support. Uses `systemd --user`, `tmux`, watchdog auto-heal, context compaction, and missed-message replay.
- macOS: beta. Uses LaunchAgent and `tmux`. Supports setup, start/stop/restart, status, logs, attach, heal, and doctor. The full Linux watchdog is not implemented yet.
- Windows native: beta. Uses PowerShell and a per-user Scheduled Task. Good for basic always-on operation. WSL2 is still the better Windows path if you want Linux-equivalent behavior.

## Requirements

Before the bot can run, you need:

- Claude Code CLI installed and authenticated
- a Telegram bot token from BotFather
- your Telegram user ID; `dog setup` can detect it automatically from a one-time test message

Linux full mode also needs `systemd --user`. On Debian/Ubuntu, `dog setup` can install supported dependencies when you approve it.

## Permissions

The setup wizard lets you choose how much autonomy Claude gets:

- `default`: safest default; Claude asks before tools
- `plan`: read and plan first
- `acceptEdits`: accept file edits automatically
- `auto`: let Claude decide when to ask
- `dontAsk`: fewer prompts
- `bypassPermissions`: no permission prompts; only use in a sandbox

For demos and shared machines, start with `default` plus demo mode.

## Demo mode

Demo mode reduces accidental disclosure while presenting.

It hides PIDs, local paths, and detailed runtime status. It also blocks logs unless you explicitly request raw output.

Demo mode does not erase old transcripts or logs. If you already ran the bot with sensitive prompts, clean those separately before recording or presenting.

## Agentic setup

If another AI agent is installing this for you, do not paste secrets into a chat transcript unless you trust that environment.

Use the dedicated agent setup guide instead:

- [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md)

That file contains the non-interactive commands and the security caveats. The main path for humans is still `./bin/dog setup`.

## Manual install commands

Use these only when you need non-interactive setup or are building automation around the repo.

Linux:

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install.sh --install-deps --permission-mode default --demo --start --yes
```

macOS:

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install-macos.sh --install-deps --permission-mode default --demo --start --yes
```

Windows PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN = "<bot-token>"
$env:TELEGRAM_USER_ID = "<telegram-user-id>"
.\install-windows.ps1 -InstallDeps -PermissionMode default -Demo -Start -Yes
```

These paths are useful for agents and CI, but they are less safe for humans because tokens can land in shell history or process environments. Prefer `dog setup` when you are at a terminal.

## Security model

`claude-watchdog` is designed to avoid the easy mistakes:

- token input is hidden in the setup wizard
- token is not passed to child installers as an argument
- generated config files are private (`0600` on Linux/macOS, restricted ACLs on Windows)
- `dog setup` encrypts the bot token at rest when OpenSSL is available
- Linux/macOS keep the token encryption key next to the encrypted token, so OS-account security still matters
- `.env` is parsed as data, never sourced or evaluated
- Telegram access is allowlisted by user ID
- the Claude session runs from an isolated workdir

This is not a substitute for OS account security. A process running as your user can generally read your files and process environment. Use a dedicated Telegram bot token and rotate it if it may have been exposed.

## Validate changes

```bash
./tests/validate.sh
```

Validation checks shell syntax, Python syntax, user-systemd unit validity, and common public-release leaks.

## Safety rules

- Run only one poller per Telegram bot token.
- Do not commit `.env`, `.token.enc`, `.token.key`, `access.json`, transcripts, inbox files, PID files, locks, or plugin cache contents.
- Keep the Telegram workdir stable unless you intentionally want a new transcript lineage.
- Use `dog doctor` before debugging a failed install.
