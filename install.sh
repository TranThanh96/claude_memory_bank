#!/usr/bin/env bash
# Scaffold the claude_memory_bank memory bank (v3) into a project.
#
# Usage:
#   install.sh [--upgrade] [target_dir]
#
# Env:
#   INIT_MEMORY_BANK_TEMPLATE  path to this template repo (default: the directory this
#                              script lives in)
#
# This is the Core layer only: active.md snapshot, decisions/patterns/troubleshooting.md,
# hooks, lint. For spec-first planning and ticket delegation on top of it, see
# https://github.com/TranThanh96/claude_ticket_workflow (its own install.sh assumes this
# layer is already installed).
#
# Behavior:
#   - Files that don't exist in the target are copied as-is.
#   - Files that already exist are never overwritten, except with --upgrade:
#     template-owned files (hooks, scripts, the memory-bank skills, memory-files.md,
#     checks.example.json) are replaced by the template's version when they have no
#     uncommitted changes; otherwise they are skipped with a warning.
#     User-owned files (CLAUDE.md, settings.json, core rules, memory content)
#     are never overwritten.
#   - CLAUDE.md and .claude/settings.json are special-cased: if the target already
#     has one, the template is staged next to it (*.template) and a merge prompt
#     is printed for your coding agent. A script can't safely merge markdown/JSON.
#   - .claude/memory/active.md (the local work snapshot) is added to .gitignore.
#   - An older layout (v1: CLAUDE-*.md in the project root; v2: .claude/memory/tasks/,
#     project-state.md, decisions/) is detected and a migration prompt is printed.
#     Nothing old is moved or deleted automatically.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="${INIT_MEMORY_BANK_TEMPLATE:-$SELF_DIR}"
UPGRADE=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --upgrade) UPGRADE=1 ;;
    *) echo "error: unknown flag $1" >&2; exit 1 ;;
  esac
  shift
done
TARGET_DIR="${1:-.}"

if [[ ! -f "$TEMPLATE_DIR/CLAUDE.md" || ! -d "$TEMPLATE_DIR/.claude/memory" ]]; then
  echo "error: template not found at $TEMPLATE_DIR (set INIT_MEMORY_BANK_TEMPLATE to override)" >&2
  exit 1
fi
command -v python3 >/dev/null || echo "warning: python3 not found on PATH; hooks and memory-lint need it." >&2

mkdir -p "$TARGET_DIR"

FILES=(
  "CLAUDE.md"
  ".claude/settings.json"
  ".claude/checks.example.json"
  ".claude/rules/core-rules.md"
  ".claude/rules/coding-guidelines.md"
  ".claude/rules/memory-files.md"
  ".claude/hooks/session_start.py"
  ".claude/hooks/post_edit_check.py"
  ".claude/skills/update-memory-bank/SKILL.md"
  ".claude/skills/memory-audit/SKILL.md"
  ".claude/memory/decisions.md"
  ".claude/memory/patterns.md"
  ".claude/memory/troubleshooting.md"
  "scripts/memory-lint.py"
  "scripts/pre_commit_memory_check.py"
)

MERGE_FILES=("CLAUDE.md" ".claude/settings.json")
# Owned by the template, not the project: --upgrade may replace these.
TEMPLATE_OWNED=(
  ".claude/checks.example.json"
  ".claude/rules/memory-files.md"
  ".claude/hooks/session_start.py"
  ".claude/hooks/post_edit_check.py"
  ".claude/skills/update-memory-bank/SKILL.md"
  ".claude/skills/memory-audit/SKILL.md"
  "scripts/memory-lint.py"
  "scripts/pre_commit_memory_check.py"
)

# True when replacing the file could lose work: uncommitted or untracked
# changes, or no git repo to recover from.
has_local_changes() {
  local out
  out="$(git -C "$TARGET_DIR" status --porcelain -- "$1" 2>/dev/null)" || return 0
  [[ -n "$out" ]]
}

created=()
skipped=()
staged=()
updated=()
kept=()
outdated=0

for file in "${FILES[@]}"; do
  src="$TEMPLATE_DIR/$file"
  dst="$TARGET_DIR/$file"

  if [[ -f "$dst" ]]; then
    if [[ $UPGRADE -eq 1 && " ${TEMPLATE_OWNED[*]} " == *" $file "* ]] && ! cmp -s "$src" "$dst"; then
      if has_local_changes "$file"; then
        kept+=("$file")
      else
        cp "$src" "$dst"
        updated+=("$file")
      fi
    elif [[ " ${MERGE_FILES[*]} " == *" $file "* ]]; then
      cp "$src" "$dst.template"
      staged+=("$file")
    else
      skipped+=("$file")
      if [[ " ${TEMPLATE_OWNED[*]} " == *" $file "* ]] && ! cmp -s "$src" "$dst"; then
        outdated=$((outdated + 1))
      fi
    fi
    continue
  fi

  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  created+=("$file")
done

chmod +x "$TARGET_DIR"/.claude/hooks/*.py "$TARGET_DIR/scripts"/*.py 2>/dev/null || true

# active.md is a per-checkout snapshot, never committed.
gitignore_msg=""
if ! grep -qxF ".claude/memory/active.md" "$TARGET_DIR/.gitignore" 2>/dev/null; then
  if [[ -s "$TARGET_DIR/.gitignore" && -n "$(tail -c 1 "$TARGET_DIR/.gitignore")" ]]; then
    echo >> "$TARGET_DIR/.gitignore"
  fi
  echo ".claude/memory/active.md" >> "$TARGET_DIR/.gitignore"
  gitignore_msg="added to .gitignore: .claude/memory/active.md (local work snapshot)"
fi

# Real git hook (not a Claude Code hook): fires for any commit, from any tool,
# by any developer -- not just inside a Claude Code session. Never overwritten.
precommit_msg=""
if [[ -d "$TARGET_DIR/.git" ]]; then
  hook_dst="$TARGET_DIR/.git/hooks/pre-commit"
  if [[ -e "$hook_dst" ]]; then
    precommit_msg="$TARGET_DIR/.git/hooks/pre-commit already exists; not touching it. To get the
memory-drift warning, add this line to it (or your hook manager):
  python3 \"\$(git rev-parse --show-toplevel)/scripts/pre_commit_memory_check.py\""
  else
    mkdir -p "$(dirname "$hook_dst")"
    cat > "$hook_dst" <<'HOOK'
#!/bin/sh
exec python3 "$(git rev-parse --show-toplevel)/scripts/pre_commit_memory_check.py"
HOOK
    chmod +x "$hook_dst"
    precommit_msg="installed: .git/hooks/pre-commit (warns before commit if memory looks stale)"
  fi
fi

echo "== claude_memory_bank install (v3): $TARGET_DIR =="
echo "created:"
for f in "${created[@]:-}"; do [[ -n "$f" ]] && echo "  + $f"; done
echo "skipped (already exists):"
for f in "${skipped[@]:-}"; do [[ -n "$f" ]] && echo "  = $f"; done
if [[ $outdated -gt 0 ]]; then
  echo "  ($outdated of these differ from the template's version; re-run with --upgrade to update them)"
fi
if [[ $UPGRADE -eq 1 ]]; then
  echo "updated to the template's version (review with: git diff):"
  for f in "${updated[@]:-}"; do [[ -n "$f" ]] && echo "  ^ $f"; done
  if [[ ${#kept[@]} -gt 0 ]]; then
    echo "NOT updated, the file has uncommitted changes (commit or stash them, then re-run):"
    for f in "${kept[@]}"; do echo "  ! $f"; done
  fi
fi

if [[ ${#staged[@]} -gt 0 ]]; then
  echo
  echo "Already existed, template staged as <file>.template (NOT overwritten):"
  for f in "${staged[@]}"; do echo "  ~ $f.template"; done
  cat <<'EOF'

Hand this prompt to your coding agent:
---
Merge the staged *.template files into their originals, then delete the .template files.
- CLAUDE.md: add the "## Gotchas" and "## Project memory" sections if missing. Keep every
  existing section unchanged. Remove any "@.claude/rules/..." import lines: .claude/rules/
  loads automatically, so importing a rule injects it twice.
- .claude/settings.json: add the template's hooks and permissions.deny entries to the existing
  arrays. Do not remove or reorder existing entries. Validate the result is valid JSON.
Show me all diffs before finishing.
---
EOF
fi

if compgen -G "$TARGET_DIR/CLAUDE-*.md" >/dev/null; then
  cat <<'EOF'

Detected a v1 memory bank (CLAUDE-*.md in the project root). Hand this prompt to your agent:
---
Migrate the v1 memory bank into .claude/memory/ (read .claude/rules/memory-files.md first):
- CLAUDE-activeContext.md → the current task into .claude/memory/active.md (sections as in the
  update-memory-bank skill); lasting constraints into the "## Gotchas" section of CLAUDE.md.
- CLAUDE-decisions.md → .claude/memory/decisions.md, newest first, keeping statuses.
- CLAUDE-patterns.md → .claude/memory/patterns.md; CLAUDE-troubleshooting.md →
  .claude/memory/troubleshooting.md (append below the header, drop obsolete entries).
- .claude/commands/update-memory-bank.md (v1) is replaced by the update-memory-bank skill,
  which has the same /name. Delete the old command so the two don't collide.
- Run python3 scripts/memory-lint.py until it reports no errors.
- Show me the diff. Only after I approve, git rm the old CLAUDE-*.md files.
---
EOF
fi

if [[ -d "$TARGET_DIR/.claude/memory/tasks" || -f "$TARGET_DIR/.claude/memory/project-state.md" \
      || -d "$TARGET_DIR/.claude/memory/decisions" ]]; then
  cat <<'EOF'

Detected a v2 memory bank (tasks/, project-state.md or decisions/ in .claude/memory/).
Hand this prompt to your agent:
---
Migrate the v2 memory bank to v3 (read .claude/rules/memory-files.md first):
- tasks/<current branch>.md → .claude/memory/active.md (local, gitignored). Other task files:
  move durable learnings to troubleshooting.md / patterns.md, then drop them.
- project-state.md → lasting constraints into "## Gotchas" in CLAUDE.md; current focus into
  active.md. Then delete it.
- decisions/ADR-*.md → one entry each in .claude/memory/decisions.md, newest first, keeping
  statuses; then delete decisions/.
- Delete .claude/hooks/stop_memory_nudge.py, .claude/hooks/session_end.py and
  .claude/skills/project-memory/, and remove the Stop and SessionEnd entries for them from
  .claude/settings.json. Replace the "## Project memory" section of CLAUDE.md with the template's.
- Run python3 scripts/memory-lint.py until it reports no errors.
- Show me the diff. Only after I approve, git rm the old files.
---
EOF
fi

for msg in "$gitignore_msg" "$precommit_msg"; do
  [[ -n "$msg" ]] && { echo; echo "$msg"; }
done

echo
echo "Next: fill CLAUDE.md (Overview, Commands, Gotchas), copy .claude/checks.example.json to"
echo ".claude/checks.json for per-edit lint, then run: python3 scripts/memory-lint.py"
echo "Want spec-first planning and ticket delegation on top of this? See"
echo "https://github.com/TranThanh96/claude_ticket_workflow"
