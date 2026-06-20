# Beginner setup: Claude Code on Telegram

This guide is for someone who wants an always-on Claude Code bot but has not set up a Linux server before.

## Recommended place to run it

Use a small Linux VM or VPS, not your everyday laptop. Ubuntu on AWS Lightsail, EC2, DigitalOcean, Hetzner, or a similar provider is a good fit. A VM/VPS keeps the bot online when your computer is off and isolates the Telegram Claude session from your personal machine.

Many cloud providers offer introductory credits or free-tier trials for eligible new accounts. AWS free-tier and Lightsail trial terms change over time; check the current provider page before assuming it is free.

A tiny VM is enough for this project. Start small, then resize later if Claude Code or your workload needs more.

## What you need

- An Ubuntu VM/VPS you can SSH into.
- A Telegram account.
- A new Telegram bot token from [BotFather](https://t.me/BotFather).
- A Claude Code login/subscription or other valid Claude Code authentication path.
- GitHub access only if you are cloning a private fork. Public cloning does not require GitHub login.

## 1. SSH into the server

From your computer:

```bash
ssh ubuntu@YOUR_SERVER_IP
```

Use the username/IP your cloud provider gave you.

## 2. Install Node.js, Claude Code, and the system tools

System packages:

```bash
sudo apt-get update
sudo apt-get install -y git curl unzip tmux python3 ca-certificates openssl
```

claude-watchdog never installs Node.js or Claude Code for you — that keeps it conservative and avoids surprising changes to your machine. Install a current Node.js LTS using a trusted method (NodeSource, nvm, or Volta), then install and log in to Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
claude            # complete the login, then exit
```

Prefer no global npm writes? Use a user-scoped prefix:

```bash
mkdir -p "$HOME/.npm-global"
npm install -g --prefix "$HOME/.npm-global" @anthropic-ai/claude-code
export PATH="$HOME/.npm-global/bin:$PATH"
claude
```

Official Claude Code docs: https://docs.anthropic.com/en/docs/claude-code

## 3. Install and run the guided setup

Fast path, from any directory:

```bash
npm install -g @wjira/claude-watchdog
dog setup
```

That installs the `dog` command, then launches the setup wizard from anywhere. It does not install Node.js or Claude Code for you.

Prefer to inspect the repo first? Use the manual path:

```bash
cd ~
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
./bin/dog setup
```

The wizard will ask for your Telegram bot token. Paste it into the SSH terminal only. Do not paste it into chats, issues, screenshots, or logs.

`dog setup` first checks that Claude Code is installed and logged in. If it isn't, setup stops and tells you exactly what to run (you handled this in step 2). When asked whether to install missing system dependencies, answer `y` to let it install Bun and any missing OS packages — it will not install Node.js or Claude Code.

## 5. If `claude` isn't found

You installed and logged in to Claude Code in step 2. If `dog setup` still can't find `claude`, check:

```bash
~/.local/bin/claude --version
```

Then either re-open your SSH session or add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$HOME/bin:$PATH"
```

## 6. Start and verify

```bash
dog start
dog doctor
dog status
```

Send a message to your Telegram bot from the account you allowlisted during setup.

You can also steer the local Claude session directly from SSH without going through Telegram:

```bash
dog tell "status?"
```

That is useful for quick checks while you are already on the server. It pastes into the running Claude terminal, so do not use it for secrets.

## Common choices during setup

- Permission mode: choose `default` for your first install.
- Demo mode: choose `y` if you plan to record or show the setup.
- Start after setup: choose `n` if Claude Code is not authenticated yet; authenticate first, then run `dog start`.

## Safety notes

- Use a dedicated Telegram bot token for this service.
- Only one running service should poll a Telegram bot token at a time.
- The setup wizard hides the token and encrypts it at rest when OpenSSL is available.
- The encryption key lives next to the encrypted token, so a compromised OS user account can still decrypt it.
- Rotate the BotFather token if you ever paste it into the wrong place.
