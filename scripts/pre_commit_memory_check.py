#!/usr/bin/env python3
"""Git pre-commit hook: warn when memory is over budget or has drifted from the code.

Not a Claude Code hook -- a plain git hook, installed at .git/hooks/pre-commit
by init_agent.sh, so it fires for every commit, from any tool, by any
developer, whether or not they're using Claude Code.

Two checks, both warnings to stderr, never blocking (exit 0 always):
  - memory-lint errors (size budgets etc.), so an oversized memory file is
    seen on every commit, not only where CI or checks.json runs the linter.
  - drift: files and commits since memory was last updated -- the later of
    the last commit that touched .claude/memory/ and the last write of the
    gitignored active.md (which never shows up in git log). Tune with MEMORY_NUDGE_MIN_FILES
    (default 3) and MEMORY_NUDGE_MIN_COMMITS (default 5); either crossing its
    threshold warns, both 0 disables this check.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MEMORY_PREFIX = ".claude/memory/"


def git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_lines(*args: str) -> list[str]:
    out = git(*args)
    return [line for line in out.splitlines() if line.strip()] if out else []


def memory_baseline() -> str | None:
    """Commit at which memory was last updated, or None if it never was."""
    last = git("log", "-1", "--format=%H", "--", ".claude/memory") or None
    active = Path(".claude/memory/active.md")
    if not active.is_file():
        return last
    # Last commit made before active.md was written: the snapshot covers it.
    at = git("rev-list", "-1", f"--before=@{int(active.stat().st_mtime)}", "HEAD") or None
    if last is None or at is None:
        return at or last
    return at if git("merge-base", "--is-ancestor", last, at) is not None else last


def lint_errors() -> list[str]:
    script = Path("scripts/memory-lint.py")
    if not script.is_file():
        return []
    try:
        out = subprocess.run([sys.executable, str(script), "--quiet"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line for line in out.stdout.splitlines() if line.startswith("ERROR")]


def main() -> int:
    if not Path(".claude/memory").is_dir():
        return 0  # project not initialised with the memory bank

    for line in lint_errors():
        print(f"pre-commit: memory-lint {line}", file=sys.stderr)

    file_threshold = int(os.environ.get("MEMORY_NUDGE_MIN_FILES", "3"))
    commit_threshold = int(os.environ.get("MEMORY_NUDGE_MIN_COMMITS", "5"))
    if file_threshold <= 0 and commit_threshold <= 0:
        return 0

    staged = git_lines("diff", "--cached", "--name-only")
    if any(p.startswith(MEMORY_PREFIX) for p in staged):
        return 0  # this commit updates memory

    last = memory_baseline()
    if not last:
        return 0  # no baseline yet

    changed = set(git_lines("diff", "--name-only", f"{last}..HEAD")) | set(staged)
    n_files = len(changed)
    commits_str = git("rev-list", "--count", f"{last}..HEAD")
    n_commits = int(commits_str) if commits_str else 0

    over_files = file_threshold > 0 and n_files >= file_threshold
    over_commits = commit_threshold > 0 and n_commits >= commit_threshold
    if not (over_files or over_commits):
        return 0

    print(
        f"pre-commit: {n_files} file(s) changed across {n_commits} commit(s) since "
        f".claude/memory/ was last updated (at {last[:7]}). Consider /update-memory-bank "
        f"before this commit, or after, if the task isn't done yet.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
