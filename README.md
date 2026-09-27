# claude_memory_bank

**A memory bank for your coding agent — loaded by hooks, enforced by lint, in one command.**

Every new session, a coding agent starts from zero: no idea what you decided last week, which
patterns you settled on, what already broke and why, or where the current task stopped. You
re-explain, or the agent "remembers" wrong and quietly reinvents a decision you already made.

`claude_memory_bank` adds four small memory files to your project. The one that matters at the
start of every session (what you were in the middle of) is **injected by a hook**, so the agent
can't skip it; the others are read when the task calls for them; a **linter** keeps them all
short and pointing at code that still exists.

```
new session / /clear / resume / after compaction
              │
              ▼
   SessionStart hook injects active.md
   (its age, commits landed since, files uncommitted right now)
              │
              ▼
        you work with Claude
   Claude reads decisions.md / patterns.md / troubleshooting.md on demand
   (post_edit_check hook lints each Edit/Write, if .claude/checks.json exists)
              │
              ▼
         you say "update memory"
   active.md rewritten; durable facts move into decisions/patterns/troubleshooting.md
              │
              ▼
            git commit
   pre-commit hook warns — never blocks — if memory is stale or over budget
```

**Requirements:** `git`, `python3` (standard library only — no `pip install`, no `jq`).

This is the memory-bank layer only. If you also want spec-first planning for large features and
tickets you can delegate across Claude, Codex, and Antigravity, see
[claude_ticket_workflow](https://github.com/TranThanh96/claude_ticket_workflow) — install this
repo first, that one on top. Using Claude Code and want both installed together with a guided
`/init-agent` command? See [claude_init_setup](https://github.com/TranThanh96/claude_init_setup).

---

## Install

```sh
git clone https://github.com/TranThanh96/claude_memory_bank.git ~/workspace/claude_memory_bank
~/workspace/claude_memory_bank/install.sh path/to/project
```

- Files that don't exist in the target are copied as-is; existing files are never overwritten.
- If the target already has a `CLAUDE.md` or `.claude/settings.json`, the template is staged as
  `<file>.template` next to it, with a merge prompt printed for your coding agent.
- `.claude/memory/active.md` (the local work snapshot) is added to `.gitignore`.
- A `git pre-commit` hook is installed (unless one already exists), warning — never blocking — on
  memory drift.
- An older layout (v1: `CLAUDE-*.md` in the project root; v2: `.claude/memory/tasks/`,
  `project-state.md`, `decisions/`) is detected and a migration prompt is printed. Nothing old is
  moved or deleted automatically.

Then:

1. Fill in `CLAUDE.md`'s Overview / Commands / Gotchas from your project's actual code, build
   files, and CI — Gotchas (traps a new engineer would hit) is the highest-value section.
2. Optionally copy `.claude/checks.example.json` to `.claude/checks.json` so the `PostToolUse`
   hook lints each edit with linters your project already uses.
3. Run `python3 scripts/memory-lint.py` and fix anything it reports.
4. Commit.

**Upgrade** an existing install: `install.sh --upgrade path/to/project`. Template-owned files
(hooks, scripts, the memory-bank skills, `memory-files.md`, `checks.example.json`) are replaced
with the new version — unless you have uncommitted changes in them, in which case they're listed
and left alone. Your own files (`CLAUDE.md`, `settings.json`, `core-rules.md`,
`coding-guidelines.md`, everything in `.claude/memory/`) are never overwritten.

## Check that it works

Open a **new** Claude Code session in the project:

- `/hooks` lists **SessionStart** and **PostToolUse** from *Project Settings*.
- `/context` lists each `.claude/rules/*.md` file once under Memory files.
- Ask Claude to "update memory", start another session, and ask "what was I working on?" —
  it should answer from `active.md` without reading anything.

## The everyday workflow

| When | You do | Happens automatically |
| --- | --- | --- |
| Start a session (also `/clear`, resume, after compaction) | Nothing | The hook shows Claude `active.md`, when it was written, how many commits landed since, and how many files are uncommitted |
| While working | Nothing | Claude reads `decisions.md` before design choices, `patterns.md` before implementing, `troubleshooting.md` when debugging — the table in `CLAUDE.md` tells it when. Edits are linted if you set up `checks.json` |
| You stop, or reach a milestone | Say **"update memory"** (or `/update-memory-bank`) | Claude rewrites `active.md` and records any new decision, pattern or tricky fix; review `git diff -- .claude/memory/` |
| You commit | Nothing | The pre-commit hook **warns, never blocks**, if a memory file is over budget, cites a path that no longer exists, or memory hasn't been updated for a while |
| The task is done | Say "update memory" | Durable knowledge moves to the committed files; `active.md` is deleted |
| Every ~2 weeks | `/memory-audit` | Re-checks only entries whose cited files changed since the last audit, and proposes fixes for you to approve |

What `active.md` looks like — Claude writes it; you rarely edit it by hand:

```markdown
# Task: rate-limit the public API
## Goal & done criteria
- 429 after 100 req/min per key; `tests/test_ratelimit.py` passes
## Status
- [x] Token bucket in `src/api/ratelimit.py`
- [ ] Wire into `src/api/app.py` middleware  ← resume here
## Key references
- `src/api/app.py:40-75` — middleware order matters (auth must run first)
## Learnings / dead ends
- Redis INCR+EXPIRE races under load; switched to a Lua script
```

### What goes where

| You just… | Record it in | Shared? |
| --- | --- | --- |
| stopped mid-task | `.claude/memory/active.md` | No — local to this checkout |
| made a design choice others must follow | `.claude/memory/decisions.md` | Yes, committed |
| settled on "how we do X here" | `.claude/memory/patterns.md` | Yes |
| fixed a bug whose cause wasn't obvious | `.claude/memory/troubleshooting.md` | Yes |
| learned something true for one module only | `.claude/rules/<module>.md` with `paths:` | Yes — loads only when that module is touched |
| found a trap anyone would hit | the **Gotchas** section of `CLAUDE.md` | Yes — loaded every session |

You normally don't pick the file yourself: "update memory" does. Record only what the code and
git log can't tell you, and cite code as paths (`src/x.py:10`) rather than pasting it. The full
rules are in [`.claude/rules/memory-files.md`](.claude/rules/memory-files.md).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| New session says "No work in progress is recorded" | Normal until the first "update memory", and after a task is finished |
| Claude doesn't know where the task stopped | `active.md` wasn't updated at the end of the last session. Say "update memory" before you stop |
| Pre-commit warns "N file(s) changed across M commit(s) since .claude/memory/ was last updated" | Say "update memory". Tune with `MEMORY_NUDGE_MIN_FILES` (default 3) and `MEMORY_NUDGE_MIN_COMMITS` (default 5); `0` turns a signal off |
| Pre-commit or lint reports "`src/…` does not exist" | A memory entry cites a moved or deleted file. Update the entry, or run `/memory-audit` |
| `active.md` disappeared | It's gitignored: `git clean -fdx` and removing the worktree delete it, and it doesn't sync across machines. Use `git clean -fd` to keep ignored files |
| Two sessions overwrite each other's `active.md` | They share one checkout. Give each parallel session its own `git worktree` |
| `/hooks` doesn't list the project hooks | Start a new session after installing; check `.claude/settings.json` is valid JSON |

## Mechanics reference

| What | Where | How it reaches the agent |
| --- | --- | --- |
| Overview, commands, gotchas, memory map | `CLAUDE.md` | Loaded every session, subagents included |
| Behaviour rules | `.claude/rules/*.md` | Loaded every session (no `@import` needed) |
| Rules for editing memory | `.claude/rules/memory-files.md` | Only when a memory file is read (`paths:`) |
| Work in progress | `.claude/memory/active.md` — local, gitignored | **SessionStart hook**, with its age and the uncommitted-file count |
| Decisions, patterns, known issues | `.claude/memory/{decisions,patterns,troubleshooting}.md` | Read on demand, per the "Read when" table in `CLAUDE.md` |
| Memory drift, over-budget files, dead references | `scripts/pre_commit_memory_check.py` | **git pre-commit hook**: warns, for any tool and any developer |
| Lint/type errors in edited files | `.claude/checks.json` | **PostToolUse hook** feeds failures back to Claude |
| Secrets, force-push, hard reset | `.claude/settings.json` | `permissions.deny` |
| Memory stays small and true | `scripts/memory-lint.py` | Size budgets, cited paths exist, every entry cites a file |

**Only one thing is forced into context.** Knowing what you were in the middle of can't be
optional, so a hook delivers it. Everything else is read on demand, so the default context stays
small as the project grows.

**Why `active.md` is local.** It's a snapshot of *this checkout's* work, not project knowledge.
Each worktree gets its own, so parallel sessions in separate worktrees never collide, and there's
nothing to merge or clean up in a PR. What's worth keeping moves to the committed files.

**Memory can be wrong; the code can't.** The injected snapshot says how old it is, the linter
flags citations of files that are gone, and `/memory-audit` re-checks entries whose code changed.
When memory and code disagree, Claude is told to trust the code.

### Optional: CI and pre-commit framework

In CI: `python3 scripts/memory-lint.py --strict` (warnings fail too).
With the [pre-commit](https://pre-commit.com) framework, add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: memory-lint
      name: memory-lint
      entry: python3 scripts/memory-lint.py
      language: system
      pass_filenames: false
      files: ^(CLAUDE\.md|\.claude/)
```

## Developing this template

```
python3 -m unittest discover -s tests -v   # end-to-end tests, stdlib only
python3 scripts/memory-lint.py
```

Every file here, `CLAUDE.md` and `.claude/memory/` included, is the template that `install.sh`
copies into other projects. Don't record this repo's own decisions, patterns, or fixes there:
they would ship to every installed project. Rationale belongs in this README and in commit
messages; `.claude/memory/active.md` is gitignored, so it is safe to use while working here.

## Credits

- Flat memory-bank layout and the "read when" map from [centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup).
- `coding-guidelines.md` from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (MIT).
- Handoff snapshot inspired by HumanLayer's `create_handoff` / `resume_handoff` commands.
- Re-injecting context on `SessionStart` (including after compaction) follows the pattern used by [obra/superpowers](https://github.com/obra/superpowers).
