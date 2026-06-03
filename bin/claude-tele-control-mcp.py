#!/usr/bin/env python3
"""Least-privilege Claude Tele control MCP server.

Exposes only fixed, safe control actions for the always-on Telegram Claude
session. It does not execute arbitrary shell commands or expose conversation
history.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - surfaced by main
    FastMCP = None

CLAUDE_TELE = Path.home() / "bin" / "claude-tele"


def run_claude_tele(*args: str) -> dict:
    if not CLAUDE_TELE.exists():
        return {
            "ok": False,
            "status": "missing_cli",
            "message": f"claude-tele not found: {CLAUDE_TELE}",
        }
    proc = subprocess.run(
        [str(CLAUDE_TELE), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        parsed = {"raw_stdout": stdout}
    payload: dict[str, object]
    if isinstance(parsed, dict):
        payload = dict(parsed)
    else:
        payload = {"raw_stdout": stdout}
    payload.setdefault("ok", proc.returncode == 0)
    payload.setdefault("status", "ok" if proc.returncode == 0 else "failed")
    if stderr:
        payload["stderr"] = stderr[-800:]
    payload["returncode"] = proc.returncode
    return payload


def build_server():
    if FastMCP is None:
        raise RuntimeError("mcp FastMCP is not available")
    mcp = FastMCP("claude-tele-control")

    @mcp.tool()
    def compact_claude_tele_session(force: bool = False) -> str:
        """Safely request `/compact` in the running Claude Tele session.

        This tool is intentionally narrow: it can only send the fixed `/compact`
        slash command, only to the `telegram-claude` tmux session, and the
        claude-tele CLI refuses to inject while Claude appears busy or a compact
        is already in flight. `force` only bypasses the in-flight sentinel; it
        still requires an idle pane.
        """
        args = ["compact", "--json"]
        if force:
            args.append("--force")
        return json.dumps(run_claude_tele(*args), indent=2)

    @mcp.tool()
    def get_claude_tele_control_runbook() -> str:
        """Return static guidance for this least-privilege control MCP."""
        return json.dumps(
            {
                "server": "claude-tele-control",
                "tools": ["compact_claude_tele_session"],
                "security_boundaries": [
                    "Does not execute arbitrary commands.",
                    "Does not expose transcript or Telegram conversation history.",
                    "Can only request the fixed /compact slash command.",
                    "Refuses to inject while the Claude pane looks busy or modal.",
                    "Uses the same compact sentinel/cooldown state as the watchdog.",
                ],
                "when_to_use": "Call compact_claude_tele_session when Jira asks to compact the always-on Claude Tele session or when context is high and the pane is idle.",
            },
            indent=2,
        )

    return mcp


def main() -> None:
    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"claude-tele-control-mcp error: {exc}", file=sys.stderr)
        raise
