#!/usr/bin/env python3
"""SessionStart hook: inject the local work snapshot into the session.

Fires on startup, resume, /clear and after compaction (see matcher in
.claude/settings.json), so the snapshot survives a compacted context.

Injects, as factual statements (not imperative instructions):
  - .claude/memory/active.md (local, gitignored: one per checkout/worktree)
  - how old it is: when it was last written and how many commits landed since
  - how many files are uncommitted right now

The other memory files are read on demand (see the table in CLAUDE.md).
Stdlib only: no jq, no pip installs.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_CHARS = 9000  # Claude Code caps additionalContext at 10,000 chars


def git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()


def age(root: Path, path: Path) -> str:
    mtime = int(path.stat().st_mtime)
    when = dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    count = git(root, "rev-list", "--count", f"--since=@{mtime}", "HEAD")
    if count is None:
        return f"It was last written {when}."
    return f"It was last written {when}; {count} commit(s) have landed since then."


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    mem = root / ".claude" / "memory"
    if not mem.is_dir():
        return 0  # project not initialised with the memory bank; stay silent

    # Short facts first, the snapshot last: if truncation is needed, it cuts the snapshot's tail.
    parts: list[str] = []
    if payload.get("source") == "compact":
        parts.append("This context was just compacted; the snapshot below was re-injected from disk.")

    status = git(root, "status", "--porcelain")
    if status:
        parts.append(f"The working tree has {len(status.splitlines())} uncommitted change(s) (see `git status`).")

    active = mem / "active.md"
    if active.is_file():
        parts.append(
            "## Work in progress (.claude/memory/active.md)\n"
            f"{age(root, active)} Claims in it may be outdated; the code is the source of truth.\n\n"
            f"{strip_comments(active.read_text(encoding='utf-8'))}"
        )
    else:
        parts.append("No work in progress is recorded (.claude/memory/active.md does not exist).")

    context = "\n\n".join(parts)
    if len(context) > MAX_CHARS:
        context = context[:MAX_CHARS] + "\n\n[truncated: active.md exceeds the injection budget; run /memory-audit]"

    json.dump(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
