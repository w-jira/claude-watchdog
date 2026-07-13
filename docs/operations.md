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

## Migrating a legacy-socket session

Older installs may still have `telegram-claude` on tmux's default socket instead of the shared runtime socket. The installer only detects and warns about this state; it does not interrupt the live session. Perform this supervised cutover with a second shell or console available because it briefly drops the live session.

First identify which legacy socket the installer reported. If it reported a namespace-hidden path under `/proc/$MainPID/root/tmp`, save the main PID before proceeding:

```bash
MainPID=$(systemctl --user show -p MainPID --value telegram-claude.service)
```

For either socket location, stop both units and confirm each reports `inactive` or `failed`:

```bash
systemctl --user stop telegram-claude telegram-claude-watchdog
systemctl --user is-active telegram-claude telegram-claude-watchdog
```

Then complete the branch matching the reported location:

- Namespace-hidden legacy socket (`/proc/$MainPID/root/tmp/tmux-$(id -u)/default`): stopping the service destroys its `PrivateTmp` namespace, so no `kill-session` is possible or needed. Verify the socket is gone:

  ```bash
  test ! -e "/proc/$MainPID/root/tmp/tmux-$(id -u)/default" && echo "namespace socket gone"
  ```

- Host legacy socket (`/tmp/tmux-$(id -u)/default`): this socket survives the service stop. After confirming both units are inactive, remove only the named legacy session (ignore `can't find session`):

  ```bash
  env -u TMUX tmux -S "/tmp/tmux-$(id -u)/default" kill-session -t telegram-claude || true
  ```

Finally reload the units, start through `dog`, and verify both the service status and the exact new socket:

```bash
systemctl --user daemon-reload
dog start
dog status
new_socket="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/claude-tele/tmux-$(id -u)/default"
env -u TMUX tmux -S "$new_socket" has-session -t telegram-claude && echo "session on $new_socket"
```

An automated `dog migrate-socket` or `install.sh --migrate-legacy-socket` flow is intentionally deferred. A future implementation must confirm both units are inactive before any destructive action and verify the new session after startup.

## Check health

```bash
dog status
claude-tele replay-missed --dry-run   # engine-only power-user command
journalctl --user -u telegram-claude.service -u telegram-claude-watchdog.service -n 100 --no-pager
```
