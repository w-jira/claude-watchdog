# Operations

> Low-level / engine reference. Day-to-day, use the `dog` CLI (`dog status`, `dog restart`,
> `dog doctor`, …). `claude-tele` is the underlying binary `dog` wraps; the direct `claude-tele`
> and installer details below are for deploys and debugging.

## Validate

```bash
tests/validate.sh
```

`tests/validate.sh` runs shell syntax checks, Python compile checks, replay health-gate regression tests, and user-systemd unit verification. It requires `pytest` for the regression tests.

## Update an existing install

```bash
git pull --ff-only
./install.sh --update
dog restart
```

Use the installer update path instead of copying individual repository files over deployed files. It refreshes the complete binary and unit set together while preserving the existing token, access policy, and other configuration.

The hardened watchdog unit uses `ProtectHome=tmpfs`, so transcript-based context estimation requires `BindReadOnlyPaths=%h/.claude/projects`. The repository unit includes that read-only mount; after updating, confirm the deployed `telegram-claude-watchdog.service` still has it before expecting compaction to fire.

## Check health

```bash
dog status
claude-tele replay-missed --dry-run   # engine-only power-user command
journalctl --user -u telegram-claude.service -u telegram-claude-watchdog.service -n 100 --no-pager
```
