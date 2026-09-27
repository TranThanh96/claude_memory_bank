"""End-to-end tests for the template: installer, hooks, memory-lint.

Run from the repo root:  python3 -m unittest discover -s tests -v
Stdlib only. Each test builds a throwaway git repo, installs the template with
the real install.sh, and feeds hooks the same JSON Claude Code sends on stdin.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent


class Project:
    """A temp git repo with the template installed."""

    def __init__(self, root: Path, tmpdir: Path) -> None:
        self.root = root
        self.env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "TMPDIR": str(tmpdir)}
        self.env.pop("MEMORY_NUDGE_MIN_FILES", None)

    def sh(self, *cmd: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=self.root, env=self.env, capture_output=True, text=True, check=check)

    def git(self, *args: str) -> str:
        return self.sh("git", *args).stdout.strip()

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def commit(self, msg: str = "wip") -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", msg)

    def hook(self, name: str, payload: dict, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        env = {**self.env, **(extra_env or {})}
        return subprocess.run(
            ["python3", str(self.root / ".claude" / "hooks" / name)],
            cwd=self.root, env=env, input=json.dumps(payload), capture_output=True, text=True,
        )

    def lint(self, *args: str) -> subprocess.CompletedProcess:
        return self.sh("python3", "scripts/memory-lint.py", *args, check=False)


class TemplateTestCase(unittest.TestCase):
    INSTALL_ARGS: tuple[str, ...] = ()

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="cmb-test-"))
        (self._tmp / "tmp").mkdir()
        root = self._tmp / "proj"
        root.mkdir()
        self.p = Project(root, self._tmp / "tmp")
        self.p.git("init", "-q", "-b", "main")
        self.p.git("config", "user.email", "t@example.com")
        self.p.git("config", "user.name", "test")
        self.p.env["INIT_MEMORY_BANK_TEMPLATE"] = str(TEMPLATE)
        self.install = self.p.sh("bash", str(TEMPLATE / "install.sh"), *self.INSTALL_ARGS,
                                  str(root), check=False)
        self.assertEqual(self.install.returncode, 0, self.install.stderr)
        self.p.write("app.py", "print('hi')\n")
        self.p.commit("init")
        self.sid = str(uuid.uuid4())

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def start(self, source: str = "startup") -> str:
        res = self.p.hook("session_start.py", {"session_id": self.sid, "source": source})
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"] if res.stdout else ""

    def write_active(self, body: str = "# Task: demo task\n## Status\n- [ ] next  ← resume here\n") -> Path:
        return self.p.write(".claude/memory/active.md", body)


class TestInstaller(TemplateTestCase):
    def test_fresh_install_creates_core_files(self):
        for rel in (".claude/settings.json", ".claude/hooks/session_start.py",
                    ".claude/skills/update-memory-bank/SKILL.md", "scripts/memory-lint.py"):
            self.assertTrue((self.p.root / rel).is_file(), rel)
        json.loads((self.p.root / ".claude/settings.json").read_text())

    def test_existing_files_are_never_overwritten(self):
        self.p.write("CLAUDE.md", "# mine\n")
        self.p.write(".claude/settings.json", '{"model": "opus"}\n')
        res = subprocess.run(["bash", str(TEMPLATE / "install.sh"), str(self.p.root)],
                             env=self.p.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.p.root / "CLAUDE.md").read_text(), "# mine\n")
        self.assertTrue((self.p.root / "CLAUDE.md.template").is_file())
        self.assertTrue((self.p.root / ".claude/settings.json.template").is_file())

    def test_installs_git_pre_commit_hook_when_absent(self):
        hook = self.p.root / ".git/hooks/pre-commit"
        self.assertTrue(hook.is_file())
        self.assertTrue(os.access(hook, os.X_OK))
        self.assertIn("pre_commit_memory_check.py", hook.read_text())

    def test_does_not_overwrite_existing_git_pre_commit_hook(self):
        hook = self.p.root / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\necho mine\n")
        res = subprocess.run(["bash", str(TEMPLATE / "install.sh"), str(self.p.root)],
                             env=self.p.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(hook.read_text(), "#!/bin/sh\necho mine\n")
        self.assertIn(".git/hooks/pre-commit already exists", res.stdout)

    def test_v1_layout_is_detected(self):
        self.p.write("CLAUDE-activeContext.md", "# old\n")
        res = subprocess.run(["bash", str(TEMPLATE / "install.sh"), str(self.p.root)],
                             env=self.p.env, capture_output=True, text=True)
        self.assertIn("Detected a v1 memory bank", res.stdout)
        self.assertTrue((self.p.root / "CLAUDE-activeContext.md").is_file(), "v1 files must not be moved")

    def test_active_md_is_gitignored_once(self):
        self.assertEqual(self.p.git("check-ignore", ".claude/memory/active.md"), ".claude/memory/active.md")
        subprocess.run(["bash", str(TEMPLATE / "install.sh"), str(self.p.root)],
                       env=self.p.env, capture_output=True, text=True, check=True)
        self.assertEqual((self.p.root / ".gitignore").read_text().count("active.md"), 1)

    def test_appends_to_existing_gitignore_without_newline(self):
        (self.p.root / ".gitignore").write_text("node_modules/")
        subprocess.run(["bash", str(TEMPLATE / "install.sh"), str(self.p.root)],
                       env=self.p.env, capture_output=True, text=True, check=True)
        self.assertEqual((self.p.root / ".gitignore").read_text(),
                         "node_modules/\n.claude/memory/active.md\n")

    def test_v2_layout_is_detected(self):
        self.p.write(".claude/memory/tasks/main.md", "# old\n")
        res = subprocess.run(["bash", str(TEMPLATE / "install.sh"), str(self.p.root)],
                             env=self.p.env, capture_output=True, text=True)
        self.assertIn("Detected a v2 memory bank", res.stdout)
        self.assertTrue((self.p.root / ".claude/memory/tasks/main.md").is_file(), "v2 files must not be moved")


class TestUpgrade(TemplateTestCase):
    HOOK = ".claude/hooks/session_start.py"

    def run_installer(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(TEMPLATE / "install.sh"), *args, str(self.p.root)],
                              env=self.p.env, capture_output=True, text=True)

    def make_outdated(self) -> None:
        self.p.write(self.HOOK, "# old version\n")
        self.p.commit("old hook")

    def test_without_flag_reports_outdated_but_keeps_it(self):
        self.make_outdated()
        res = self.run_installer()
        self.assertIn("1 of these differ from the template's version", res.stdout)
        self.assertEqual((self.p.root / self.HOOK).read_text(), "# old version\n")

    def test_upgrade_replaces_committed_template_files(self):
        self.make_outdated()
        res = self.run_installer("--upgrade")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(f"^ {self.HOOK}", res.stdout)
        self.assertEqual((self.p.root / self.HOOK).read_text(), (TEMPLATE / self.HOOK).read_text())

    def test_upgrade_keeps_files_with_uncommitted_changes(self):
        self.make_outdated()
        self.p.write(self.HOOK, "# my local edit\n")
        res = self.run_installer("--upgrade")
        self.assertIn(f"! {self.HOOK}", res.stdout)
        self.assertEqual((self.p.root / self.HOOK).read_text(), "# my local edit\n")

    def test_upgrade_never_touches_user_owned_files(self):
        self.p.write("CLAUDE.md", "# mine\n")
        self.p.write(".claude/rules/core-rules.md", "# my rules\n")
        self.p.write(".claude/memory/patterns.md", "# my patterns\n")
        self.p.commit("customise")
        self.run_installer("--upgrade")
        self.assertEqual((self.p.root / "CLAUDE.md").read_text(), "# mine\n")
        self.assertEqual((self.p.root / ".claude/rules/core-rules.md").read_text(), "# my rules\n")
        self.assertEqual((self.p.root / ".claude/memory/patterns.md").read_text(), "# my patterns\n")
        self.assertTrue((self.p.root / "CLAUDE.md.template").is_file())

    def test_upgrade_outside_git_keeps_files(self):
        # A fresh directory, not a deleted .git: removing .git races git's background
        # maintenance (maintenance.lock) on macOS runners.
        target = self._tmp / "nogit"
        env = {**self.p.env, "GIT_CEILING_DIRECTORIES": str(self._tmp)}
        install = ["bash", str(TEMPLATE / "install.sh")]
        subprocess.run([*install, str(target)], env=env, capture_output=True, text=True, check=True)
        (target / self.HOOK).write_text("# old version\n")
        res = subprocess.run([*install, "--upgrade", str(target)], env=env, capture_output=True, text=True)
        self.assertIn(f"! {self.HOOK}", res.stdout)
        self.assertEqual((target / self.HOOK).read_text(), "# old version\n")


class TestSessionStart(TemplateTestCase):
    def test_injects_active_with_age(self):
        f = self.write_active("<!-- note for humans -->\n# Task: demo task\n")
        past = int(self.p.git("log", "-1", "--format=%ct")) - 60
        os.utime(f, (past, past))
        self.p.write("app.py", "print('changed')\n")
        self.p.commit("more")
        ctx = self.start()
        self.assertIn("# Task: demo task", ctx)
        self.assertIn("2 commit(s) have landed since then", ctx)
        self.assertNotIn("<!--", ctx, "HTML comments must be stripped")

    def test_reports_missing_active(self):
        self.assertIn("No work in progress is recorded", self.start())

    def test_reports_uncommitted_changes(self):
        self.assertNotIn("uncommitted", self.start())
        self.p.write("app.py", "print('dirty')\n")
        self.p.write("new.py", "x = 1\n")
        self.assertIn("2 uncommitted change(s)", self.start())

    def test_active_is_not_counted_as_uncommitted(self):
        self.write_active()
        self.assertNotIn("uncommitted", self.start())

    def test_compact_reinjects_and_says_so(self):
        self.write_active()
        ctx = self.start("compact")
        self.assertIn("just compacted", ctx)
        self.assertIn("# Task: demo task", ctx)

    def test_silent_in_uninitialised_project(self):
        shutil.rmtree(self.p.root / ".claude" / "memory")
        res = self.p.hook("session_start.py", {"session_id": self.sid, "source": "startup"})
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_output_is_capped_and_short_facts_survive(self):
        self.write_active("# Task: big\n" + "- filler line for size\n" * 2000)
        self.p.write("app.py", "print('dirty')\n")
        ctx = self.start("compact")
        self.assertLess(len(ctx), 10_000)
        self.assertIn("just compacted", ctx)
        self.assertIn("uncommitted", ctx)
        self.assertIn("[truncated", ctx)


class TestPostEditCheck(TemplateTestCase):
    def edit(self, rel: str) -> subprocess.CompletedProcess:
        return self.p.hook("post_edit_check.py", {"tool_name": "Edit",
                                                  "tool_input": {"file_path": str(self.p.root / rel)}})

    def configure(self) -> None:
        self.p.write(".claude/checks.json", json.dumps({"checks": [
            {"glob": "**/*.py", "command": "python3 -m py_compile {file}"},
            {"glob": ".claude/memory/**", "command": "python3 scripts/memory-lint.py --quiet"},
        ]}))

    def test_noop_without_config(self):
        self.p.write("bad.py", "def f(:\n")
        self.assertEqual(self.edit("bad.py").returncode, 0)

    def test_failure_exits_2_with_output_for_claude(self):
        self.configure()
        self.p.write("src/bad.py", "def f(:\n")
        res = self.edit("src/bad.py")
        self.assertEqual(res.returncode, 2)
        self.assertIn("SyntaxError", res.stderr)

    def test_passing_file_and_outside_project(self):
        self.configure()
        self.assertEqual(self.edit("app.py").returncode, 0)
        res = self.p.hook("post_edit_check.py", {"tool_input": {"file_path": "/etc/hosts"}})
        self.assertEqual(res.returncode, 0)

    def test_bad_memory_edit_is_caught(self):
        self.configure()
        self.p.write(".claude/memory/decisions.md", "".join(f"- d{i}\n" for i in range(200)))
        res = self.edit(".claude/memory/decisions.md")
        self.assertEqual(res.returncode, 2)
        self.assertIn("decisions.md: 200 content lines > budget 150", res.stderr)


class TestPreCommitCheck(TemplateTestCase):
    def check(self, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        env = {**self.p.env, **(extra_env or {})}
        return subprocess.run(
            ["python3", "scripts/pre_commit_memory_check.py"],
            cwd=self.p.root, env=env, capture_output=True, text=True,
        )

    def touch_and_stage(self, n: int, start: int = 0) -> None:
        for i in range(start, start + n):
            self.p.write(f"src/f{i}.py", f"x = {i}\n")
        self.p.git("add", "-A")

    def test_below_both_thresholds_is_silent(self):
        self.touch_and_stage(2)
        res = self.check()
        self.assertEqual((res.returncode, res.stderr), (0, ""))

    def test_warns_when_file_threshold_reached_in_one_commit(self):
        self.touch_and_stage(3)
        res = self.check()
        self.assertEqual(res.returncode, 0)
        self.assertIn("3 file(s) changed across 0 commit(s)", res.stderr)

    def test_warns_from_many_small_commits_even_under_file_threshold(self):
        # Five separate 1-file commits: each is below MEMORY_NUDGE_MIN_FILES (3),
        # but the commit count crosses MEMORY_NUDGE_MIN_COMMITS (5) -- this is the
        # drift the per-commit-only check would miss.
        for i in range(5):
            self.touch_and_stage(1, start=i)
            self.p.commit(f"small {i}")
        self.touch_and_stage(1, start=5)
        res = self.check()
        self.assertIn("5 commit(s)", res.stderr)

    def five_small_commits(self) -> None:
        for i in range(5):
            self.touch_and_stage(1, start=i)
            self.p.commit(f"small {i}")

    def test_fresh_active_md_resets_the_baseline(self):
        # active.md is gitignored, so updating it never moves the git-log baseline.
        self.five_small_commits()
        self.write_active()
        self.touch_and_stage(1, start=5)
        res = self.check()
        self.assertEqual((res.returncode, res.stderr), (0, ""))

    def test_stale_active_md_does_not_hide_drift(self):
        f = self.write_active()
        past = int(self.p.git("log", "-1", "--format=%ct")) - 60
        os.utime(f, (past, past))
        self.five_small_commits()
        self.touch_and_stage(1, start=5)
        self.assertIn("5 commit(s)", self.check().stderr)

    def test_staged_memory_change_suppresses_warning(self):
        self.touch_and_stage(5)
        self.p.write(".claude/memory/patterns.md", "# Patterns\n- x\n")
        self.p.git("add", "-A")
        res = self.check()
        self.assertEqual((res.returncode, res.stderr), (0, ""))

    def test_can_be_disabled(self):
        self.touch_and_stage(10)
        res = self.check({"MEMORY_NUDGE_MIN_FILES": "0", "MEMORY_NUDGE_MIN_COMMITS": "0"})
        self.assertEqual((res.returncode, res.stderr), (0, ""))

    def test_silent_in_uninitialised_project(self):
        shutil.rmtree(self.p.root / ".claude" / "memory")
        self.p.git("add", "-A")
        self.touch_and_stage(5)
        res = self.check()
        self.assertEqual((res.returncode, res.stderr), (0, ""))

    def test_reports_memory_over_budget_even_with_drift_disabled(self):
        self.p.write(".claude/memory/decisions.md", "".join(f"- d{i}\n" for i in range(200)))
        res = self.check({"MEMORY_NUDGE_MIN_FILES": "0", "MEMORY_NUDGE_MIN_COMMITS": "0"})
        self.assertEqual(res.returncode, 0)
        self.assertIn("memory-lint ERROR  .claude/memory/decisions.md: 200 content lines > budget 150", res.stderr)

    def test_lint_warnings_are_not_repeated_on_commit(self):
        (self.p.root / ".gitignore").write_text("")  # lint WARN: active.md not gitignored
        self.assertNotIn("memory-lint", self.check().stderr)

    def test_never_exits_nonzero(self):
        self.touch_and_stage(50)
        self.assertEqual(self.check().returncode, 0)


class TestMemoryLint(TemplateTestCase):
    def test_fresh_install_has_no_errors(self):
        self.assertEqual(self.p.lint().returncode, 0)

    def test_strict_fails_on_placeholders(self):
        self.assertEqual(self.p.lint("--strict").returncode, 1)

    def test_duplicate_rule_import(self):
        with open(self.p.root / "CLAUDE.md", "a") as f:
            f.write("\n@.claude/rules/core-rules.md\n")
        res = self.p.lint()
        self.assertEqual(res.returncode, 1)
        self.assertIn("injected twice", res.stdout)

    def test_import_inside_backticks_is_not_flagged(self):
        with open(self.p.root / "CLAUDE.md", "a") as f:
            f.write("\nRules live in `@.claude/rules/core-rules.md`.\n")
        self.assertNotIn("injected twice", self.p.lint().stdout)

    def test_over_budget(self):
        self.p.write(".claude/memory/patterns.md", "".join(f"- p{i}\n" for i in range(200)))
        self.assertIn("patterns.md: 200 content lines > budget 150", self.p.lint().stdout)

    def test_dead_reference_is_an_error(self):
        self.p.write(".claude/memory/patterns.md", "# Patterns\n## Handlers\n- See `src/gone.py`\n")
        res = self.p.lint()
        self.assertEqual(res.returncode, 1)
        self.assertIn("patterns.md: `src/gone.py` does not exist", res.stdout)

    def test_reference_past_end_of_file_warns(self):
        self.p.write("src/real.py", "x = 1\n")
        self.p.write(".claude/memory/troubleshooting.md", "# T\n## Boom\n- Fix: `src/real.py:5-9`\n")
        res = self.p.lint()
        self.assertEqual(res.returncode, 0)
        self.assertIn("`src/real.py:5-9` points past the end of the file (1 lines)", res.stdout)

    def test_valid_references_pass(self):
        self.p.write("src/real.py", "x = 1\ny = 2\n")
        self.p.write(".claude/memory/patterns.md",
                     "# P\n## A\n- `src/real.py:2`\n## B\n- `src/`, branch `feat/login`\n")
        out = self.p.lint().stdout
        self.assertNotIn("patterns.md", out)

    def test_entry_without_reference_warns(self):
        self.p.write(".claude/memory/troubleshooting.md", "# T\n## Flaky CI\n- Cause: runners are slow\n")
        self.assertIn("entry 'Flaky CI' cites no file", self.p.lint().stdout)

    def test_module_rule_references_are_checked(self):
        self.p.write(".claude/rules/api.md", '---\npaths:\n  - "src/api/**"\n---\n- Pattern: `src/api/base.py`\n')
        self.assertIn(".claude/rules/api.md: `src/api/base.py` does not exist", self.p.lint().stdout)

    def test_active_over_budget(self):
        self.write_active("".join(f"- s{i}\n" for i in range(41)))
        self.assertIn("active.md: 41 content lines > budget 40", self.p.lint().stdout)

    def test_warns_when_active_is_not_gitignored(self):
        self.assertNotIn("not gitignored", self.p.lint().stdout)
        (self.p.root / ".gitignore").write_text("")
        self.assertIn("active.md is not gitignored", self.p.lint().stdout)


if __name__ == "__main__":
    unittest.main()
