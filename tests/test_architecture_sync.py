import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.check_architecture_sync import (
    architecture_relevant,
    committed_changes,
    decode_nul_paths,
    hook_failure_response,
    missing_architecture_update,
    normalize_paths,
    working_tree_changes,
)


class ArchitectureSyncTests(unittest.TestCase):
    def test_architecture_relevant_paths_are_classified(self):
        for path in (
            "backend/tasks.py",
            "api/search.js",
            "frontend/search.html",
            "contracts/api-contract.schema.json",
            "scripts/query.sh",
            ".github/workflows/contract.yml",
            ".codex/hooks.json",
            "package.json",
            "AGENTS.md",
            "workers/new_worker.py",
            "deploy/service.yaml",
        ):
            with self.subTest(path=path):
                self.assertTrue(architecture_relevant(path))

        for path in (
            "tests/test_contract.py",
            "tests/fixtures/report.json",
            "public/index.html",
            "data/patent.json",
            "README.md",
            "notes.txt",
            "upload_records.db",
        ):
            with self.subTest(path=path):
                self.assertFalse(architecture_relevant(path))

    def test_relevant_change_requires_architecture_update(self):
        self.assertEqual(
            missing_architecture_update({"backend/tasks.py", "tests/test_contract.py"}),
            ["backend/tasks.py"],
        )

    def test_architecture_update_satisfies_check(self):
        self.assertEqual(
            missing_architecture_update({"backend/tasks.py", "ARCHITECTURE.md"}),
            [],
        )

    def test_deleted_architecture_file_does_not_satisfy_check(self):
        self.assertEqual(
            missing_architecture_update(
                {"backend/tasks.py", "ARCHITECTURE.md"},
                architecture_exists=False,
            ),
            ["backend/tasks.py"],
        )

    def test_deleted_architecture_file_fails_even_without_code_changes(self):
        self.assertEqual(
            missing_architecture_update(
                {"ARCHITECTURE.md"},
                architecture_exists=False,
            ),
            ["ARCHITECTURE.md"],
        )

    def test_test_only_change_does_not_require_architecture_update(self):
        self.assertEqual(missing_architecture_update({"tests/test_contract.py"}), [])

    def test_paths_are_normalized(self):
        self.assertEqual(normalize_paths(["backend\\tasks.py", "", "api/search.js"]), {
            "backend/tasks.py",
            "api/search.js",
        })

    def test_nul_delimited_paths_preserve_embedded_newlines(self):
        self.assertEqual(
            decode_nul_paths(b"backend/odd\nname.py\0frontend/search.html\0"),
            {"backend/odd\nname.py", "frontend/search.html"},
        )

    def test_hook_blocks_once_without_looping_forever(self):
        first = hook_failure_response("Update architecture", stop_hook_active=False)
        repeated = hook_failure_response("Update architecture", stop_hook_active=True)

        self.assertEqual(first, {"decision": "block", "reason": "Update architecture"})
        self.assertTrue(repeated["continue"])
        self.assertIn("CI will remain blocked", repeated["systemMessage"])


class ArchitectureSyncGitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "backend").mkdir()
        (self.root / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
        (self.root / "backend" / "tasks.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Architecture Test")
        self.git("config", "user.email", "architecture@example.test")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.temp_dir.cleanup()

    def git(self, *args):
        result = subprocess.run(
            ("git", *args),
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def test_working_tree_includes_tracked_and_untracked_unusual_paths(self):
        (self.root / "backend" / "tasks.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.root / "workers").mkdir()
        unusual = self.root / "workers" / "odd\nname.py"
        unusual.write_text("VALUE = 3\n", encoding="utf-8")

        changed = working_tree_changes(self.root)

        self.assertIn("backend/tasks.py", changed)
        self.assertIn("workers/odd\nname.py", changed)

    def test_committed_direct_merge_base_and_zero_base_ranges(self):
        (self.root / "backend" / "tasks.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.root / "ARCHITECTURE.md").write_text("# Architecture\n\nUpdated.\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "change")
        head = self.git("rev-parse", "HEAD").strip()

        expected = {"ARCHITECTURE.md", "backend/tasks.py"}
        self.assertEqual(committed_changes(self.root, self.base, head), expected)
        self.assertEqual(
            committed_changes(self.root, self.base, head, merge_base=True),
            expected,
        )
        self.assertTrue(expected <= committed_changes(self.root, "0" * 40, head))

    def test_rename_is_evaluated_as_delete_and_add(self):
        self.git("mv", "backend/tasks.py", "notes.txt")

        changed = working_tree_changes(self.root)

        self.assertIn("backend/tasks.py", changed)
        self.assertIn("notes.txt", changed)


if __name__ == "__main__":
    unittest.main()
