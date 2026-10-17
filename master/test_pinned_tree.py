"""#825: 고정 SHA 분리 worktree — 생성·고정·쓰기 감지·정리. 실 LLM 호출 없음."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.context_synth import pinned_tree as PT


class PinnedTreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "a.py").write_text("one\n")
        self.git("add", "a.py")
        self.git("commit", "-m", "1")
        self.sha1 = self.git("rev-parse", "HEAD").strip()
        (self.repo / "a.py").write_text("two\n")
        self.git("commit", "-am", "2")
        self.logs = []

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def test_checkout_at_sha_outside_repo_and_removed(self):
        writes = []
        with PT.pinned_worktree(self.repo, self.sha1, logf=self.logs.append,
                                writes=writes) as tree:
            self.assertEqual((tree / "a.py").read_text(), "one\n")
            self.assertFalse(tree.is_relative_to(self.repo))
            self.assertIn(str(tree), self.git("worktree", "list", "--porcelain"))
            self.assertEqual(PT.check_writes(tree), [])
        self.assertFalse(tree.exists())
        self.assertFalse(tree.parent.exists())
        self.assertNotIn(str(tree), self.git("worktree", "list", "--porcelain"))
        self.assertEqual(writes, [])
        self.assertTrue(any("생성" in m for m in self.logs) and any("제거" in m for m in self.logs))
        self.assertEqual((self.repo / "a.py").read_text(), "two\n")

    def test_writes_are_logged_and_exposed(self):
        writes = []
        with PT.pinned_worktree(self.repo, self.sha1, logf=self.logs.append,
                                writes=writes) as tree:
            (tree / "a.py").write_text("changed\n")
            (tree / "new.txt").write_text("x\n")
        self.assertEqual(len(writes), 2, writes)
        self.assertTrue(any("쓰기 2건" in m for m in self.logs), self.logs)
        self.assertFalse(tree.exists())

    def test_removed_even_when_block_raises(self):
        with self.assertRaises(KeyError):
            with PT.pinned_worktree(self.repo, self.sha1, logf=self.logs.append) as tree:
                raise KeyError("x")
        self.assertFalse(tree.exists())
        self.assertNotIn(str(tree), self.git("worktree", "list", "--porcelain"))

    def test_bad_sha_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            with PT.pinned_worktree(self.repo, "0" * 40, logf=self.logs.append):
                pass
        self.assertTrue(any("생성 실패" in m for m in self.logs), self.logs)


if __name__ == "__main__":
    unittest.main()
