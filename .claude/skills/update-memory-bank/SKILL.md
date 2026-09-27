---
name: update-memory-bank
description: Save the current work state and durable learnings to .claude/memory/ so the next session can continue. Use when the user asks to update memory, hand off, or wrap up, or when a task reaches a milestone.
---

# Update the memory bank

Goal: the next session, starting from a clean context, can continue this work without
re-discovering anything. The rules for each file are in `.claude/rules/memory-files.md`
(it loads when you read a memory file).

## 1. Gather facts (don't rely on conversation memory alone)
`git status --short`, `git diff --stat`, `git log --oneline -10`.

## 2. Work snapshot: `.claude/memory/active.md`
Overwrite it with these sections, ≤40 lines in total:

```
# <task in one line>
## Goal & done criteria      — verifiable: tests / behaviour
## Status                    — done steps; the next step marked "← resume here"
## Key references            — 2-5 `file:line` refs or plan/spec docs to read first
## Learnings / dead ends     — approaches that failed and why (the most valuable section)
```

If the task is finished, delete `active.md` after step 3 instead.

## 3. Durable knowledge (only if this session produced some)
- Decision made or replaced → `decisions.md`
- Tricky bug fixed → `troubleshooting.md`
- Recurring pattern established → `patterns.md`
- A pattern or decision for one module only → that module's path-scoped rule (see memory-files.md)

## 4. Archive finished tickets (if any)
Run `python3 scripts/tasks_status.py`. If a feature folder under `.claude/tasks/` has every ticket at
`status: done`, `git mv` that whole folder in one move to `.claude/tasks/_archive/<feature-slug>/`.

## 5. Verify and report
- Run `python3 scripts/memory-lint.py`; fix every error.
- Show the user `git diff -- .claude/memory/` and the new `active.md` (it is gitignored, so it
  isn't in the diff). Summarise in 3-5 lines what was recorded and where.
