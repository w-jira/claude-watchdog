# Agent setup guide

This file is for AI agents, CI jobs, and scripted installs.

For a human at a terminal, use the safer path instead:

```bash
./bin/cwd setup
```

The wizard hides the Telegram token, encrypts it at rest when OpenSSL is available, and avoids putting secrets in command arguments.

## Information needed

Ask the user for only these values:

- target OS: Linux, macOS, Windows native, or Windows WSL2
- Telegram bot token from BotFather
- your numeric Telegram user ID, or permission to auto-detect it from a one-time test message during `cwd setup`
- whether dependency installation is allowed
- Claude permission mode, usually `default`
- whether demo mode should be enabled

Do not print, summarize, log, or commit the Telegram bot token.

## Linux

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install.sh --install-deps --permission-mode default --demo --start --yes
```

If dependency installation is not approved, remove `--install-deps`.

## macOS

```bash
TELEGRAM_BOT_TOKEN='<bot-token>' TELEGRAM_USER_ID='<telegram-user-id>' \
  ./install-macos.sh --install-deps --permission-mode default --demo --start --yes
```

If Homebrew dependency installation is not approved, remove `--install-deps`.

## Windows PowerShell

```powershell
$env:TELEGRAM_BOT_TOKEN = "<bot-token>"
$env:TELEGRAM_USER_ID = "<telegram-user-id>"
.\install-windows.ps1 -InstallDeps -PermissionMode default -Demo -Start -Yes
Remove-Item Env:TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:TELEGRAM_USER_ID -ErrorAction SilentlyContinue
```

## Verify

Linux/macOS:

```bash
cwd doctor
cwd status
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" doctor
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\claude-watchdog\claude-watchdog-windows.ps1" status
```

## Security notes for agents

- Prefer `./bin/cwd setup` when you can interact with the terminal directly.
- Non-interactive setup may expose tokens through shell history, process environments, terminal logs, or agent transcripts.
- Never use real tokens in examples, summaries, PR descriptions, or test fixtures.
- After setup, inspect only redacted output. Do not read `.env`, `.token.key`, `.token.enc`, or `access.json` unless the task explicitly requires it.
- If a token may have been exposed, rotate it in BotFather.
