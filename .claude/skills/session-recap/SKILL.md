---
name: session-recap
description: Summarize current project progress -- what's done, what's in progress, what's recommended next -- from active.md, decisions.md, the ticket board (if present), and recent commits. Use after the user agrees to a recap at the start of an unclear session, or when they ask "tóm tắt tiến độ" / "what's the status" / "catch me up" / "where did we leave off".
---

# Session recap

Goal: give a new session -- possibly on a different machine, where `active.md` never
travelled -- the same situational awareness as the one that left off, without the user
re-explaining anything.

## 1. Gather facts
- `.claude/memory/active.md` if present (local snapshot; may not exist on this machine --
  that's expected, not an error).
- The last few entries of `.claude/memory/decisions.md` (recent ones, not the whole file).
- `git log --oneline -10` and `git status --short` -- what actually landed vs. what's
  uncommitted right now.
- If `.claude/tasks/` exists: run `python3 scripts/tasks_status.py` (ticket-workflow tier) for
  counts by status and which tickets are `ready` (the frontier) or `blocked`. If the directory
  or script doesn't exist, skip this silently -- it just means that tier isn't installed.

## 2. Report three short sections
- **Done** -- what's landed, from commits and resolved decisions.
- **In progress** -- from `active.md`'s Status section if present, otherwise inferred from
  uncommitted changes or `in_progress` tickets.
- **Next** -- the concrete next step: `active.md`'s "resume here" marker, or the ticket
  frontier, or ask the user if neither gives a clear answer.

Report only what a file or commit actually backs -- don't invent progress. If every source is
empty (fresh project, nothing recorded yet), say so plainly instead of padding the report.
