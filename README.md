# claude-watchdog

Run Claude Code from Telegram without babysitting a terminal.

`claude-watchdog` sets up one always-on Claude Code session, connected through Anthropic's official Telegram plugin. It installs the service, keeps your Claude session alive, auto-heals when it breaks, protects setup from common token leaks, and gives you a small CLI for day-to-day operations.

```bash
curl -fsSLo /tmp/claude-watchdog-bootstrap.sh https://raw.githubusercontent.com/w-jira/claude-watchdog/main/bootstrap.sh
bash /tmp/claude-watchdog-bootstrap.sh
```

Prefer to inspect before running? Use the manual path:

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

- keeps one private Claude Code session running from Telegram
- keeps your Claude session alive and auto-heals when it breaks
- checks the common stuff that causes silent failures:
  - Claude Code is installed and logged in
  - the Telegram plugin and Bun bridge are working
  - the bot token, allowlist, and Telegram health checks are fresh
- catches up missed Telegram messages after a bridge hiccup, once Telegram health is proven again
- isolates Telegram work from your normal Claude session
- gives you a secure setup wizard, demo-safe output, and simple `dog` commands

## Recommended setup

For the smoothest always-on setup, run this on a small Linux VM/VPS such as Ubuntu on AWS Lightsail, EC2, DigitalOcean, Hetzner, or similar. Cloud providers often offer introductory credits or free-tier trials for eligible accounts; terms change, so verify the current offer before relying on it.

If you are new to servers, start with the beginner walkthrough:

- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

Use the CLI wizard. It keeps the bot token out of shell history and command arguments.

Fast path:

```bash
curl -fsSLo /tmp/claude-watchdog-bootstrap.sh https://raw.githubusercontent.com/w-jira/claude-watchdog/main/bootstrap.sh
bash /tmp/claude-watchdog-bootstrap.sh
```

That command clones or updates the repo under `~/.local/share/claude-watchdog/repo`, then launches `dog setup`. You can run it from any directory.

Manual path:

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
- whether to install missing system dependencies (Bun + OS packages) — it never installs Node.js or Claude Code for you
- whether to start the bot immediately

By default, `dog setup` encrypts the Telegram token at rest when OpenSSL is available. The runtime service decrypts it only when starting Claude and passes it through the process environment, where the official plugin can read it. If OpenSSL is missing, setup falls back to a private `0600` `.env` file and prints a warning.

The Linux/macOS encryption key is stored in the same private state directory as the encrypted token. This removes the token from `.env` and casual text exposure, but it does not protect against malware, a compromised OS account, or backups that include both `.token.enc` and `.token.key`.

## Daily commands

```bash
dog help       # friendly command menu
dog setup      # guided setup or reconfiguration (--config-only writes config only)
dog preflight  # check this machine is ready (Claude Code, deps, systemd)
dog tell "status?" # send a health-gated local note to the live Claude session
dog status     # service + bot status
dog start      # start the bot
dog stop       # stop the bot
dog restart    # restart the bot
dog doctor     # diagnostics
dog logs       # logs; blocked in demo mode unless raw is requested
dog uninstall  # remove service + binaries (--purge also removes config + token)
```

`dog tell` sends a quick local note to the already-running Claude session. Use it for quick steering, status checks, or handoffs from another local agent. For example, you can tell Hermes, OpenClaw, or a shell script to run `dog tell "check status"` without starting a second Telegram bot connection. It is intentionally gated on fresh Telegram health so local control does not hide a broken Telegram path. Do not send secrets through it.

Break-glass override: `CLAUDE_TELE_DISABLE_E2E_INJECTION_GATE=1` disables that gate for local emergency recovery only. Prefer fixing Telegram health first; the override can reintroduce replay/local-control loops if used casually.

`dog start` enables and starts the user services so the bot remains always-on across user-service restarts.

`dog` wraps an engine called `claude-tele`. Linux also exposes that engine directly for power users:

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

- Claude Code CLI installed and authenticated — you install it yourself (`npm install -g @anthropic-ai/claude-code`, then run `claude` to log in). `dog setup` checks for it and won't proceed without it; it never installs Node.js or Claude Code for you. See https://docs.anthropic.com/en/docs/claude-code
- a Telegram bot token from BotFather
- your Telegram user ID; `dog setup` can detect it automatically from a one-time test message

Linux full mode also needs `systemd --user`, plus `tmux`, `python3`, `git`, `openssl`, `curl`, and `unzip`. On Debian/Ubuntu, `dog setup` can install these system dependencies (and a pinned, checksum-verified Bun) when you approve it — but never Node.js or Claude Code.

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
