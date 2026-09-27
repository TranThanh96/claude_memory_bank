---
name: memory-audit
description: Audit .claude/memory/ against the codebase — re-check only entries whose cited files changed since the last audit, then propose fixes.
disable-model-invocation: true
---

# Memory audit (every ~2 weeks, or after a major refactor / model upgrade)

Incremental: never read the whole codebase. Read only diffs of files that memory cites.
Do steps 2-3 in an Explore subagent so this session's context stays small.

## 1. Mechanical checks
Run `python3 scripts/memory-lint.py`. It reports budgets, cited paths that no longer exist or
lines past a file's end, entries that cite no file, and an `active.md` that isn't gitignored.

## 2. Find what changed since the last audit
- Base: `git log -1 --format=%H --grep='^memory-audit:'`. None → first audit: every entry is in scope.
- Changed files: `git diff --name-only <base>..HEAD`.

## 3. Re-check only affected entries
Sources: `decisions.md` (active entries), `patterns.md`, `troubleshooting.md`, `active.md`, and the
`.claude/rules/*.md` files that have `paths:` frontmatter.
- An entry is affected when a path it cites (or its decision `Scope`) matches a changed file,
  or is a directory containing one. Skip every other entry.
- For an affected entry, read `git diff <base>..HEAD -- <cited files>`; open a whole file only if
  the diff is not enough. Does the entry still describe the code? Is a troubleshooting entry
  obsolete because the cause was fixed?
- `active.md`: is it about work that has already landed?

## 4. Review always-loaded context
`CLAUDE.md` and `.claude/rules/*.md` without `paths`: is every line still needed?
Test: "if I delete this line, would Claude make a mistake?" If not, propose deleting it.

## 5. Report, then record the audit
- Present a table: file · entry · problem · proposed action (update / delete / supersede), plus
  the entries lint flagged as citing no file. Apply only what the user approves.
- Commit with a message starting `memory-audit:` (use `--allow-empty` if nothing changed): the
  next audit uses this commit as its base.
