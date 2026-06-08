# Security Policy

## Sensitive files

Never commit:

- `~/.claude/channels/telegram/.env`
- `~/.claude/channels/telegram/.token.enc`
- `~/.claude/channels/telegram/.token.key`
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
dog status
dog doctor
```

before recovery work. (`dog` is the user-facing CLI; `claude-tele` is the engine it wraps.)

`dog tell` sends local text directly into the running Claude terminal through tmux. It avoids
starting a second Telegram poller, but it is not an encrypted secret channel and it bypasses
Telegram allowlist checks. Do not send tokens, passwords, `.env` contents, or other secrets
through it.

## Token at rest

When OpenSSL is available, `dog setup` stores the bot token AES-256-CBC-encrypted in
`.token.enc` and writes `TELEGRAM_BOT_TOKEN_ENCRYPTED=1` to `.env` (no plaintext token in `.env`).

Understand the threat model honestly: the decryption key (`.token.key`) lives in the **same
`0700` state directory** as the ciphertext, readable by the same user the bot runs as. This
protects against *accidental disclosure* — pasting `.env` into a chat/issue, casual `grep`, a
backup that captures `.env` but not the key files. It does **not** protect against malware, a
compromised user account, or a backup that includes both `.token.enc` and `.token.key`. Treat
the whole state directory as a secret and rotate the token in BotFather if it may have leaked.

## Public-release checks

Before publishing changes:

```bash
./tests/validate.sh
git status --short
git log --oneline --decorate --max-count=10
```

Do not publish if validation reports secrets, personal infrastructure strings, runtime files, or local-only paths.
