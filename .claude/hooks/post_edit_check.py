#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): run fast checks on the file Claude just edited.

This is the "enforce by machine, not by prose" layer. Checks are configured
per project in .claude/checks.json (copy .claude/checks.example.json):

  {
    "checks": [
      {"glob": "**/*.py", "command": "ruff check {file}"},
      {"glob": "src/**/*.ts", "command": "npx eslint {file}"}
    ]
  }

On failure the hook exits 2: Claude Code shows stderr to Claude (the edit
already happened, so this is feedback, not a block) and Claude fixes it.
No config file → no-op. Keep checks fast (single-file lint/typecheck);
full test suites belong in CI or a Stop/pre-commit gate, not per edit.
"""
from __future__ import annotations

import fnmatch
import json
import re
import os
import shlex
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 60
MAX_OUTPUT = 3000


def expand_braces(pattern: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    head, tail = pattern[: m.start()], pattern[m.end() :]
    return [p for alt in m.group(1).split(",") for p in expand_braces(head + alt + tail)]


def glob_match(rel: str, pattern: str) -> bool:
    """Glob with {a,b} braces; a leading **/ also matches files at the root."""
    for pat in expand_braces(pattern):
        candidates = [pat, pat[3:]] if pat.startswith("**/") else [pat]
        if any(fnmatch.fnmatchcase(rel, c) for c in candidates):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".").resolve()
    config_path = root / ".claude" / "checks.json"
    if not config_path.is_file():
        return 0
    try:
        checks = json.loads(config_path.read_text()).get("checks", [])
    except (json.JSONDecodeError, OSError) as exc:
        print(f"post_edit_check: cannot read {config_path}: {exc}", file=sys.stderr)
        return 1  # non-blocking: a broken config should not stall Claude

    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0
    path = Path(file_path)
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return 0  # outside the project

    failures: list[str] = []
    for check in checks:
        if not glob_match(rel, check.get("glob", "")):
            continue
        cmd = check["command"].replace("{file}", shlex.quote(rel))
        try:
            res = subprocess.run(
                cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            failures.append(f"$ {cmd}\n(timed out after {TIMEOUT_S}s)")
            continue
        if res.returncode != 0:
            out = (res.stdout + res.stderr).strip()
            failures.append(f"$ {cmd}\n{out[:MAX_OUTPUT]}")

    if failures:
        print(f"Checks failed for {rel}:\n\n" + "\n\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
