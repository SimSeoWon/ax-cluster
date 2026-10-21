"""재검증 기록·현재 지문·표시 대상 선택 회귀 (실제 모델/큐 호출 없음)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths, SourceScope
from master.work import revalidation as R


class RevalidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.paths = ProjectPaths("T", root, scope=SourceScope(roots=("master",), exts=(".py",)))
        self.root = root
        (self.paths.repo / "master").mkdir(parents=True)
        (self.paths.repo / "master/a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        self.paths.context.mkdir()
        self.paths.ontology.mkdir()

    def document(self, name="master/a.md", **updates):
        meta = dict(needs_revalidation=True, generation_model="local",
                    generation_source_files=["master/a.py"],
                    generation_source_fingerprint=R.source_fingerprint(self.paths, ["master/a.py"]))
        meta.update(updates)
        path = self.paths.context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        import yaml
        path.write_text("---\n" + yaml.safe_dump(meta) + "---\n기존 산출물\n", encoding="utf-8")
        return path

    def test_mark_persists_idempotently_and_clear_rejects_stale(self):
        first = R.mark(self.root, "task", "t", fingerprint="one", metadata={"round": 1})
        second = R.mark(self.root, "task", "t", fingerprint="one", metadata={"round": 2})
        self.assertEqual(first, second)
        self.assertEqual(R.pending(self.root)[0]["metadata"]["round"], 1)
        R.mark(self.root, "task", "t", fingerprint="two", metadata={"round": 2})
        self.assertFalse(R.clear(self.root, "task", "t", fingerprint="one"))
        self.assertEqual(R.pending(self.root)[0]["fingerprint"], "two")
        self.assertTrue(R.clear(self.root, "task", "t", fingerprint="two"))
        self.assertEqual(R.pending(self.root), [])

    def test_concurrent_marks_do_not_lose_records(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda n: R.mark(self.root, "task", str(n), fingerprint=str(n),
                                          metadata={"number": n}), range(16)))
        self.assertEqual(len(R.pending(self.root)), 16)
        self.assertEqual(len(R.pending(self.root, limit=3)), 3)

    def test_corruption_is_not_replaced_with_empty_store(self):
        R.mark(self.root, "task", "t", fingerprint="one", metadata={})
        file = self.root / "revalidation/records.json"
        file.write_text("invalid json", encoding="utf-8")
        with self.assertRaises(ValueError):
            R.mark(self.root, "task", "new", fingerprint="new", metadata={})
        self.assertEqual(file.read_text(), "invalid json")

    def test_invalid_kind_and_symlink_store_are_rejected(self):
        with self.assertRaises(ValueError):
            R.mark(self.root, "code", "t", fingerprint="one", metadata={})
        destination = self.root / "elsewhere"
        destination.mkdir()
        (self.root / "revalidation").symlink_to(destination)
        with self.assertRaises(ValueError):
            R.mark(self.root, "task", "t", fingerprint="one", metadata={})

    def test_directory_hash_detects_added_removed_and_changed_files(self):
        directory = self.root / "artifact"
        directory.mkdir()
        file = directory / "one"
        file.write_text("one")
        original = R.artifact_fingerprint(directory)
        file.write_text("two")
        self.assertNotEqual(R.artifact_fingerprint(directory), original)
        file.write_text("one")
        added = directory / "two"
        added.write_text("two")
        self.assertNotEqual(R.artifact_fingerprint(directory), original)
        added.unlink()
        self.assertEqual(R.artifact_fingerprint(directory), original)

    def test_only_marked_documents_are_selected(self):
        self.document()
        self.document("unmarked.md", needs_revalidation=False)
        R.mark(self.root, "task", "terminal", fingerprint="task", metadata={"status": "merged"})
        entries = R.marked_documents(self.paths)
        self.assertEqual([(e["kind"], e["key"]) for e in entries], [("context", "master/a")])
        self.assertEqual(len(R.pending(self.root)), 1)

    def test_source_changed_does_not_call_or_clear_mark(self):
        path = self.document()
        original = path.read_bytes()
        (self.paths.repo / "master/a.py").write_text("changed", encoding="utf-8")
        called = []
        out = R.run_documents(self.paths, context_runner=lambda *a, **kw: called.append(kw))
        self.assertFalse(out["ok"])
        self.assertFalse(called)
        self.assertEqual(path.read_bytes(), original)

    def test_cloud_only_runner_gets_current_source_and_artifact_guards(self):
        path = self.document()
        called = []
        def runner(paths, key, files, **kw):
            called.append((key, files, kw))
            return SimpleNamespace(written=False, needs_revalidation=True, reason="quota exhausted")
        out = R.run_documents(self.paths, context_runner=runner)
        self.assertFalse(out["ok"])
        self.assertEqual(called[0][0], "master/a")
        self.assertTrue(called[0][2]["cloud_only"])
        self.assertEqual(called[0][2]["expected_artifact_fingerprint"], R.artifact_fingerprint(path))
        self.assertEqual(len(R.marked_documents(self.paths)), 1)

    def test_source_path_escape_and_wrong_scope_are_rejected(self):
        self.document(generation_source_files=["../../outside.py"])
        called = []
        out = R.run_documents(self.paths, context_runner=lambda *a, **kw: called.append(kw))
        self.assertFalse(out["ok"])
        self.assertFalse(called)
        with self.assertRaises(ValueError):
            R.source_fingerprint(self.paths, ["docs/other.py"])

    def test_ontology_manifest_selection_and_guards(self):
        from master.ontology import package, yaml_io
        domain = self.paths.ontology / "domains/D"
        domain.mkdir(parents=True)
        manifest = domain / package.MANIFEST
        manifest.write_text(yaml_io.dump({"generation": {
            "needs_revalidation": True, "source_files": ["master/a.py"],
            "source_fingerprint": R.source_fingerprint(self.paths, ["master/a.py"])
        }}), encoding="utf-8")
        calls = []
        def runner(paths, key, **kw):
            calls.append((key, kw))
            return SimpleNamespace(ok=False, written=None, needs_revalidation=True,
                                   reasons=["cloud failed"])
        out = R.run_documents(self.paths, ontology_runner=runner)
        self.assertFalse(out["ok"])
        self.assertEqual(calls[0][0], "D")
        self.assertEqual(calls[0][1]["expected_artifact_fingerprint"], R.artifact_fingerprint(domain))

    def test_failures_do_not_starve_later_documents(self):
        """#840 결함 ② — 앞 대상의 소스 변경은 예산을 안 쓰고, 실패한 호출은 다음 주기에 뒤로 간다."""
        (self.paths.repo / "master/b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
        self.document("master/a.md")
        self.document("master/b.md", generation_source_files=["master/b.py"],
                      generation_source_fingerprint=R.source_fingerprint(self.paths, ["master/b.py"]))
        self.document("master/c.md")
        self.document("master/d.md")
        stale = self.document("master/0.md")
        (self.paths.repo / "master/stale.py").write_text("x = 1\n", encoding="utf-8")
        stale.write_text(stale.read_text(encoding="utf-8").replace(
            "- master/a.py", "- master/stale.py"), encoding="utf-8")
        (self.paths.repo / "master/stale.py").write_text("x = 2\n", encoding="utf-8")
        seen = []
        def failing(paths, key, files, **kw):
            seen.append(key)
            return SimpleNamespace(written=False, needs_revalidation=True, reason="cloud failed")
        R.run_documents(self.paths, limit=2, context_runner=failing)
        self.assertEqual(seen, ["master/a", "master/b"], "소스 변경 대상은 호출 예산을 쓰지 않는다")
        seen.clear()
        R.run_documents(self.paths, limit=2, context_runner=failing)
        self.assertEqual(seen, ["master/c", "master/d"], "실패한 앞 대상이 뒤 문서를 막지 않는다")
        seen.clear()
        R.run_documents(self.paths, limit=2, context_runner=failing)
        self.assertEqual(seen, ["master/a", "master/b"], "한 바퀴 돌면 가장 오래 안 본 것부터")

    def test_scan_root_symlink_is_rejected(self):
        """#840 결함 ③ — context/ontology 루트가 트윈 밖을 가리키면 스캔하지 않는다."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        self.paths.context.rmdir()
        self.paths.context.symlink_to(outside.name, target_is_directory=True)
        self.document()
        with self.assertRaises(ValueError):
            R.marked_documents(self.paths)
        self.paths.context.unlink()
        self.paths.context.mkdir()
        (self.paths.ontology / "domains").symlink_to(outside.name, target_is_directory=True)
        with self.assertRaises(ValueError):
            R.marked_documents(self.paths)

    def test_batch_respects_disable_and_daily_gap(self):
        from datetime import datetime
        from unittest.mock import patch
        from master.batch import run as batch, gates
        self.document()
        definition = next(b for b in batch.BATCHES if b.schedule.key == "cloud_revalidation")
        now = datetime(2026, 10, 21, 12)
        with patch.object(batch, "BATCHES", [definition]), patch.object(
                R, "run_documents", return_value={"ok": True, "entries": 1}) as runner:
            result = batch.run(self.paths, {"batch": {"cloud_revalidation": False}},
                               now=now, force=True)
            self.assertFalse(result[0].ran)
            runner.assert_not_called()
            self.assertIsNone(gates.read_marker(self.root, "cloud_revalidation"))
            plan = batch.plan(self.paths, {}, now=now)
            self.assertTrue(plan[0].result["would_run"])
            runner.assert_not_called()
            self.assertTrue(batch.run(self.paths, {}, now=now)[0].ran)
            self.assertFalse(batch.run(self.paths, {}, now=now)[0].ran)
            self.assertEqual(runner.call_count, 1)

    def test_failed_batch_does_not_record_success_marker(self):
        from datetime import datetime
        from unittest.mock import patch
        from master.batch import run as batch, gates
        self.document()
        definition = next(b for b in batch.BATCHES if b.schedule.key == "cloud_revalidation")
        with patch.object(batch, "BATCHES", [definition]), patch.object(
                R, "run_documents", return_value={"ok": False, "reason": "quota"}):
            result = batch.run(self.paths, {}, now=datetime(2026, 10, 21, 12))
        self.assertTrue(result[0].error)
        self.assertIsNone(gates.read_marker(self.root, "cloud_revalidation"))


if __name__ == "__main__":
    unittest.main()
