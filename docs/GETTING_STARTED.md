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

## 2. Install the basic tools

```bash
sudo apt-get update
sudo apt-get install -y git curl unzip tmux python3 ca-certificates openssl npm
```

If your Ubuntu image has an old Node.js/npm version, install a current Node.js LTS release from your preferred trusted source, then continue.

## 3. Clone this repo

```bash
cd ~
git clone https://github.com/w-jira/claude-watchdog.git
cd claude-watchdog
```

## 4. Run the guided setup

```bash
./bin/dog setup
```

The wizard will ask for your Telegram bot token. Paste it into the SSH terminal only. Do not paste it into chats, issues, screenshots, or logs.

When asked whether to install missing supported dependencies, answer `y` if you want the installer to install Bun and Claude Code where possible. Claude Code installs through npm into your user directory (`~/.npm-global`), not with `sudo npm install -g`.

## 5. Authenticate Claude Code

If Claude Code was just installed, authenticate it before starting the bot:

```bash
claude
```

Follow the login instructions, then exit Claude.

If `claude` is not found after setup, check:

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
