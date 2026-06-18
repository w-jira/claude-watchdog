# Operations

> Low-level / engine reference. Day-to-day, use the `dog` CLI (`dog status`, `dog restart`,
> `dog doctor`, …). `claude-tele` is the underlying binary `dog` wraps; the direct `claude-tele`
> and `install -m 700` commands below are for manual deploys and debugging.

## Validate

```bash
tests/validate.sh
```

`tests/validate.sh` runs shell syntax checks, Python compile checks, replay health-gate regression tests, and user-systemd unit verification. It requires `pytest` for the regression tests.

## Deploy to current VPS layout

```bash
install -m 700 bin/dog ~/bin/dog
install -m 700 bin/claude-tele ~/bin/claude-tele
install -m 700 bin/claude-tele-watchdog ~/bin/claude-tele-watchdog
install -m 700 bin/claude-tele-patch-telegram-plugin ~/bin/claude-tele-patch-telegram-plugin
install -m 700 bin/claude-tele-replay-missed ~/bin/claude-tele-replay-missed
install -m 600 systemd/user/telegram-claude.service ~/.config/systemd/user/telegram-claude.service
install -m 600 systemd/user/telegram-claude-watchdog.service ~/.config/systemd/user/telegram-claude-watchdog.service
systemctl --user daemon-reload
claude-tele restart
```

## Check health

```bash
dog status
claude-tele replay-missed --dry-run   # engine-only power-user command
journalctl --user -u telegram-claude.service -u telegram-claude-watchdog.service -n 100 --no-pager
```
