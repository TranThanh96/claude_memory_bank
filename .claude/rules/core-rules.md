<!-- Loaded automatically at session start (no `paths` frontmatter), so it must
     NOT also be @imported from CLAUDE.md. Keep each rule verifiable.
     Rules here are guidance; anything that must never happen belongs in
     .claude/settings.json (permissions.deny) or a hook.
     coding-guidelines.md is also always loaded: don't repeat what it covers
     (assumptions, simplicity, surgical changes / minimal diffs, verification loops). -->
# Core Rules
- Read the relevant code before changing it; don't guess an API.
- Run the relevant tests after a change; never report "done" while tests fail.
- Large changes (>3 files or any public interface change): present a plan first and wait for approval.
- Don't add a new dependency without asking first.
