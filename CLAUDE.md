<!--
  Always loaded, every session. Budget: <= 100 lines (checked by scripts/memory-lint.py).
  HTML comments like this one are stripped before Claude sees the file: use them
  for notes to human maintainers, they cost zero context.
  Put here only what Claude cannot infer from the code or git log.
-->

## Overview
<!-- 1-2 sentences: what this project is for and who uses it. -->
- Goal: <...>
- Stack: <language/runtime, framework, database>
<!-- Architecture: 3-5 lines on main modules and data flow. Delete if the
     directory structure already makes it obvious. -->
- Architecture: <...>

## Commands
<!-- Exact commands. In a monorepo, put per-module commands in <module>/CLAUDE.md. -->
- Install: `...`
- Test (all): `...`
- Test (one file): `...`
- Lint/format: `...`
- Run local: `...`

## Gotchas
<!-- Highest-value section. Traps a new engineer would fall into:
     invariants, generated files, public APIs that must not change,
     things that look wrong but are intentional. One line each. -->
- <...>

## Project memory
`.claude/memory/` holds what the code and git log can't tell you. Read a file when its row applies:

| File | Read when |
| --- | --- |
| `active.md` (local, gitignored) | Injected at session start. A subagent without it in context: read it if the current task is unclear |
| `decisions.md` | Before a design choice, a public-interface change or a new dependency |
| `patterns.md` | Before implementing a feature, module or test |
| `troubleshooting.md` | When a bug or failure has no obvious cause |

- An `active` decision is a constraint: if a change contradicts one, stop and tell the user which one and why.
- Memory can be stale: when it disagrees with the code, trust the code and point out the stale entry.
- Project facts go here, not in Claude's auto memory (which holds personal preferences only).
- When compacting, preserve: the list of modified files and the test commands run with their results.
