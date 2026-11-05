"""#696: 기준 커밋의 선언과 완전한 검증 입력. 외부 모델/네트워크 없이 검사한다."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.work import declarations as D
from master import layer2_verify as L2


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.paths = SimpleNamespace(repo=self.repo)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "api.py").write_text(
            "from enum import Enum\nfrom helper import Result\nLIMIT = 4\nclass Mode(Enum):\n    READY = 1\n"
            "class Api:\n    state: Mode\n    def run(self, value: int, *, flag=False) -> str:\n"
            "        self.result: Result = Result()\n        self.last_value = value\n"
            "        return 'implementation-only-marker'\n", encoding="utf-8")
        (self.repo / "helper.py").write_text("class Result:\n    OK = 1\n", encoding="utf-8")
        (self.repo / "Foo.h").write_text("class Foo { public: void Run(); };\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.git("checkout", "-b", "work")
        (self.repo / "Other.h").write_text("enum Other { FIRST, LAST };\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "frozen")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def test_python_contract_from_base_not_working_tree(self):
        (self.repo / "api.py").write_text("def wrong(): pass\n", encoding="utf-8")
        d = D.from_commit(self.paths, self.base, kind="code", target_files=["api.py"],
                          per_class=16000, total=64000)
        self.assertTrue(d.complete, d.summary)
        rendered = d.render()
        for name in ("from enum import Enum", "LIMIT = 4", "READY = 1", "state: Mode",
                     "run(self, value: int, *, flag=False) -> str"):
            self.assertIn(name, rendered)
        self.assertNotIn("implementation-only-marker", rendered)
        self.assertNotIn("def wrong", rendered)
        self.assertIn("class Result", rendered)
        self.assertIn("result: Result", rendered)
        self.assertIn("last_value = ...", rendered)
        self.assertNotIn("ONLY spellings", d.render(for_verification=True))

    def test_default_preserves_changed_headers(self):
        d = D.from_commit(self.paths, self.base)
        self.assertEqual([rel for _, rel, _ in d.blocks], ["Other.h"])

    def test_existing_cpp_target_adds_base_header(self):
        d = D.from_commit(self.paths, self.base, target_files=["Foo.cpp"])
        self.assertEqual([rel for _, rel, _ in d.blocks], ["Foo.h", "Other.h"])

    def test_missing_truncated_and_dropped_are_incomplete(self):
        missing = D.from_commit(self.paths, self.base, kind="code", target_files=["gone.py"])
        self.assertIn("gone.py", missing.missing)
        self.assertFalse(missing.complete)
        cut = D.from_commit(self.paths, self.base, per_class=5, total=5,
                            target_files=["Foo.h"])
        self.assertTrue(cut.truncated)
        self.assertTrue(cut.dropped)
        self.assertFalse(cut.complete)
        self.assertIn("TRUNCATED", cut.render())
        self.assertIn("OMITTED", cut.render())

    def test_invalid_base_python_is_diagnostic(self):
        with self.assertRaisesRegex(D.DeclError, "Python 기준 선언 파싱 실패"):
            D.python_declarations("def bad(:\n", filename="bad.py")

    def test_fields_only_from_instance_and_class_methods(self):
        rendered = D.python_declarations(
            "class Api:\n"
            "    def __init__(self):\n        self.instance = 1\n        local = 2\n"
            "    @classmethod\n    def setup(cls):\n        cls.shared = 3\n"
            "    @staticmethod\n    def helper(self):\n        self.external = 4\n")
        self.assertIn("instance = ...", rendered)
        self.assertIn("shared = ...", rendered)
        self.assertNotIn("local =", rendered)
        self.assertNotIn("external =", rendered)


class InputTests(unittest.TestCase):
    def test_python_prompt_and_full_input(self):
        prompt = L2.build_prompt([("api.py", "def run(): pass")], kind="code",
                                 declarations="class Api: ...")
        self.assertIn("Python", prompt)
        self.assertNotIn("Unreal Engine", prompt)
        self.assertLess(prompt.index("class Api"), prompt.index("=== api.py"))

    def test_large_input_tail_is_sent_without_truncation(self):
        calls = []
        def approve(prompt, timeout=0):
            calls.append(prompt)
            return "VERDICT: APPROVE"
        content = "x" * (L2.MAX_FILE_CHARS + 1) + "\nTAIL-EVIDENCE"
        v = L2.verify_files([("big.py", content)], kind="code",
                            backends=[("fake", approve)])
        self.assertTrue(v.approved)
        self.assertIn(content, calls[0])
        self.assertNotIn("(truncated)", calls[0])

    def test_base_version_sits_between_declarations_and_files(self):
        """`#757` — 기준 원본은 선언부 뒤, 판정 대상 앞. 바뀐 부분만 보라는 지시가 함께 간다."""
        prompt = L2.build_prompt([("W.cpp", "NEW-BODY")], declarations="class X;",
                                 base_files=[("W.cpp", "Btn.OnClicked_Lambda(f);")])
        head = prompt.index("=== BASE VERSION")
        self.assertLess(prompt.index("=== END DECLARATIONS ==="), head)
        self.assertLess(head, prompt.index("--- W.cpp (base) ---"))
        self.assertLess(prompt.index("Btn.OnClicked_Lambda(f);"), prompt.index("=== END BASE VERSION ==="))
        self.assertLess(prompt.index("=== END BASE VERSION ==="), prompt.index("=== W.cpp ==="))
        for text in ("passed the project's skeleton gate",
                     "Judge ONLY code that was added or changed relative to the base version.",
                     "Do NOT report a construct as invalid"):
            self.assertIn(text, prompt)

    def test_no_base_files_keeps_the_prompt_byte_identical(self):
        files = [("W.cpp", "BODY")]
        for kind in ("unreal", "code"):
            before = L2.build_prompt(files, declarations="class X;", kind=kind)
            self.assertEqual(before, L2.build_prompt(files, declarations="class X;", kind=kind,
                                                     base_files=None))
            self.assertEqual(before, L2.build_prompt(files, declarations="class X;", kind=kind,
                                                     base_files=[]))
            self.assertNotIn("BASE VERSION", before)

    def test_verify_files_forwards_base_files_to_backend(self):
        calls = []
        def approve(prompt, timeout=0):
            calls.append(prompt)
            return "VERDICT: APPROVE"
        L2.clear_cooldown()
        v = L2.verify_files([("W.cpp", "BODY")], backends=[("fake", approve)],
                            base_files=[("W.cpp", "BASE-MARKER")])
        self.assertTrue(v.approved)
        self.assertIn("--- W.cpp (base) ---\nBASE-MARKER", calls[0])

    def test_empty_input_cannot_get_model_approval(self):
        v = L2.verify_files([], backends=[("fake", lambda *_a, **_k: "VERDICT: APPROVE")])
        self.assertEqual(v.failure, "empty_input")


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        L2.clear_cooldown()
        self.addCleanup(L2.clear_cooldown)

    def verify(self, gemini, final="VERDICT: APPROVE", mode="codex", why=""):
        with patch.object(L2, "call_agy_why", return_value=(gemini, why)) as agy, \
             patch.object(L2, "call_codex_why", return_value=(final, "", "")) as codex, \
             patch.object(L2, "call_claude_why", return_value=(final, "")) as claude:
            v = L2.verify_files([("api.py", "def existing(): pass")], kind="code",
                                declarations="def existing(): ...", author_lane=mode,
                                base_files=[("api.py", "def existing(): pass")],
                                orchestrator=mode)
        return v, agy, codex, claude

    def test_false_positive_rechecked_against_full_evidence(self):
        raw = "- existing is missing\nVERDICT: REQUEST_CHANGES"
        v, agy, codex, claude = self.verify(raw)
        self.assertTrue(v.approved)
        self.assertEqual((agy.call_count, codex.call_count, claude.call_count), (1, 1, 0))
        prompt = codex.call_args.args[0]
        for evidence in (raw, "def existing(): ...", "def existing(): pass", "BASE VERSION"):
            self.assertIn(evidence, prompt)
        self.assertIn("gemini_raw_response=" + raw, v.warnings)

    def test_actual_error_stays_request_changes(self):
        raw = "- missing semicolon\nVERDICT: REQUEST_CHANGES"
        v, _, _, claude = self.verify(raw, final=raw, mode="claude")
        self.assertFalse(v.approved)
        self.assertIsNone(v.failure)
        self.assertEqual(v.findings, ["missing semicolon"])
        self.assertEqual(claude.call_count, 1)

    def test_unavailable_and_malformed_gemini_rechecked(self):
        for raw, why in ((None, "타임아웃 300초"), (None, "quota exhausted"),
                         ("invalid output", "")):
            with self.subTest(why=why, raw=raw):
                L2.clear_cooldown()
                v, _, codex, _ = self.verify(raw, why=why)
                self.assertTrue(v.approved)
                self.assertEqual(codex.call_count, 1)
                self.assertIn("gemini_failure_reason=" + why, v.warnings)
                self.assertIn(why or "malformed", codex.call_args.args[0])

    def test_final_response_failure_blocks(self):
        for final in (None, "malformed response"):
            with self.subTest(final=final):
                v, _, _, _ = self.verify("VERDICT: REQUEST_CHANGES", final=final)
                self.assertFalse(v.approved)
                self.assertTrue(v.failure.startswith("orchestrator_"))

    def test_approve_does_not_call_orchestrator(self):
        v, _, codex, claude = self.verify("VERDICT: APPROVE")
        self.assertTrue(v.approved)
        self.assertEqual((codex.call_count, claude.call_count), (0, 0))

    def test_cooldown_still_rechecks_with_reason(self):
        L2._cooldown["agy"] = L2.time.time() + 60
        v, agy, codex, _ = self.verify(None)
        self.assertTrue(v.approved)
        self.assertEqual((agy.call_count, codex.call_count), (0, 1))
        self.assertIn("쿨다운", codex.call_args.args[0])

    def test_both_calls_share_layer2_usage_attribution(self):
        import json
        from master.work import usage as U
        def gemini(prompt, **kw):
            U.emit_cli("agy", None, rc=1)
            return None, "quota"
        def codex(prompt, **kw):
            U.emit_cli("codex", U.Usage(lane="codex", input_tokens=12, output_tokens=3), rc=0)
            return "VERDICT: APPROVE", "", ""
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "usage.jsonl"
            with patch.object(L2, "call_agy_why", side_effect=gemini), \
                 patch.object(L2, "call_codex_why", side_effect=codex), \
                 U.sink(log, source="layer2", work_id="W", task_id="T"):
                v = L2.verify_files([("a.py", "pass")], orchestrator="codex")
            rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertTrue(v.approved)
        self.assertEqual([row["lane"] for row in rows], ["agy", "codex"])
        self.assertTrue(all(row["source"] == "layer2" and row["work_id"] == "W"
                            and row["task_id"] == "T" for row in rows))
        self.assertFalse(rows[0]["measured"])

    def test_legacy_author_exclusion_and_malformed_block_preserved(self):
        calls = []
        def backend(prompt, timeout):
            calls.append(prompt)
            return "invalid response"
        v = L2.verify_files([("api.py", "pass")], author_lane="codex",
                            backends=[("codex", backend), ("agy", backend)])
        self.assertEqual(v.failure, "malformed")
        self.assertEqual(len(calls), 1)


class PieceScopedImportTests(unittest.TestCase):
    """#780: import 확장은 이 조각의 대상에서만, from-import 는 그 이름의 선언만."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.paths = SimpleNamespace(repo=self.repo)
        git = self.git
        git("init", "-b", "main")
        git("config", "user.name", "Fixture")
        git("config", "user.email", "fixture@example.invalid")
        files = {
            "lib.py": "from origin import shared as alias_name\nLIMIT = 3\n"
                      "def wanted(x: int) -> str:\n    return 'body-marker'\n"
                      "def unwanted() -> None:\n    pass\nclass Unwanted:\n    pass\n",
            "origin.py": "def shared() -> int:\n    return 1\n",
            "big_other.py": "def other_only() -> None:\n    pass\n",
            "mod.py": "def used() -> int:\n    return 1\ndef unused() -> int:\n    return 2\n",
            "a.py": "def a():\n    pass\n",
            "b.py": "def b():\n    pass\n",
        }
        for rel, text in files.items():
            (self.repo / rel).write_text(text, encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "base")
        git("checkout", "-b", "work")
        # 골조가 두 조각 파일을 바꾼다 — b.py 만 big_other 를 import 한다.
        (self.repo / "a.py").write_text(
            "from lib import wanted, LIMIT, alias_name, ghost\nimport mod as M\n"
            "def a():\n    return M.used()\n", encoding="utf-8")
        (self.repo / "b.py").write_text(
            "import big_other\ndef b():\n    big_other.other_only()\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "frozen")
        self.base = git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def blocks(self, target):
        d = D.from_commit(self.paths, self.base, kind="code", work_exts=[".py"],
                          target_files=[target], per_class=16000, total=64000)
        return d, {rel: text for _, rel, text in d.blocks}

    def test_other_piece_imports_are_not_followed(self):
        d, blocks = self.blocks("a.py")
        # 골조가 바꾼 b.py 자체는 동결 계약이라 남지만, b.py 의 import 는 따라가지 않는다.
        self.assertIn("b.py", blocks)
        self.assertNotIn("big_other.py", blocks)
        _, other = self.blocks("b.py")
        self.assertIn("big_other.py", other)
        self.assertNotIn("lib.py", other)

    def test_from_import_carries_only_named_declarations(self):
        d, blocks = self.blocks("a.py")
        lib = blocks["lib.py"]
        self.assertIn("def wanted(x: int) -> str", lib)
        self.assertIn("LIMIT = 3", lib)
        self.assertNotIn("unwanted", lib)
        self.assertNotIn("Unwanted", lib)
        self.assertNotIn("body-marker", lib)
        # 재수출은 그 import 줄로 싣고 결손으로 세지 않는다.
        self.assertIn("from origin import shared as alias_name", lib)
        self.assertNotIn("lib.py:alias_name", d.missing)
        # 정말 없는 이름은 조용히 빼지 않는다 — 결손으로 남아 grounding 이 불완전해진다.
        self.assertIn("lib.py:ghost", d.missing)
        self.assertFalse(d.complete)
        self.assertIn("lib.py:ghost", d.render())

    def test_module_import_narrows_to_attributes_used(self):
        _, blocks = self.blocks("a.py")
        self.assertIn("def used()", blocks["mod.py"])
        self.assertNotIn("def unused()", blocks["mod.py"])

    def test_unresolved_module_attribute_falls_back_to_whole_module(self):
        (self.repo / "a.py").write_text("import mod as M\nM.dynamic\n", encoding="utf-8")
        self.git("commit", "-am", "dynamic attr")
        self.base = self.git("rev-parse", "HEAD").strip()
        d, blocks = self.blocks("a.py")
        self.assertIn("def unused()", blocks["mod.py"])
        self.assertFalse(d.missing)

    def test_truncated_narrowed_module_stays_incomplete(self):
        d = D.from_commit(self.paths, self.base, kind="code", work_exts=[".py"],
                          target_files=["a.py"], per_class=20, total=64000)
        self.assertTrue(d.truncated)
        self.assertFalse(d.complete)

    def test_no_budget_never_truncates(self):
        # #780: 층2(클라우드 판정)는 글자 예산 없이 부른다 — None 이면 잘림·예산 초과가 없다.
        d = D.from_commit(self.paths, self.base, kind="code", work_exts=[".py"],
                          target_files=["a.py"], per_class=None, total=None)
        self.assertEqual((d.truncated, d.dropped), ([], []))
        self.assertEqual(d.missing, ["lib.py:ghost"])     # 픽스처의 의도된 결손만 남는다
        tight = D.from_commit(self.paths, self.base, kind="code", work_exts=[".py"],
                              target_files=["a.py"], per_class=20, total=64000)
        self.assertEqual(sorted(b[1] for b in d.blocks), sorted(b[1] for b in tight.blocks))


class AgyHeartbeatTests(unittest.TestCase):
    """`#888` T2 — `run_agy(heartbeat=...)` 의 하트비트·궤적 요약. agy·대화 기록은 가짜다."""

    def setUp(self):
        from master import agy_models as AM, agy_trace as AT
        self.AM, self.AT = AM, AT
        self.markers = []
        stack = [patch.object(L2, "AGY_HEARTBEAT_SEC", 0.05),
                 patch.object(L2.shutil, "which", return_value="/fake/agy")]
        for st in stack:
            st.start()
            self.addCleanup(st.stop)

    def fake_execute(self, result, *, delay=0.3, seen=None):
        def run(exe, build, runner, **kw):
            if seen is not None:
                seen["cmd"] = build("gemini-x", "")
                seen["threads"] = [t.name for t in __import__("threading").enumerate()]
            time.sleep(delay)
            return result
        return patch.object(self.AM, "execute", side_effect=run)

    def fake_trace(self, *, find=None):
        tr = self.AT.Trace(conversation="conv-1", steps=3, turns=2, turn_seconds=[4.0, 9.0],
                           tools=[self.AT.ToolCall("read_file", "/tmp/ax-pinned-q/tree/a.py", 1, 9)],
                           first_ts=1.0, last_ts=14.0, last_status=3, last_step_type=132)

        def default_find(marker, *, since):
            self.markers.append((marker, since))
            return Path("/fake/conv-1.db")
        return (patch.object(self.AT, "find_conversation", side_effect=find or default_find),
                patch.object(self.AT, "read_trace", return_value=tr))

    def test_off_no_thread_no_log(self):
        seen, logs = {}, []
        ok = self.AM.AgyResult(raw="본문", rc=0)
        with self.fake_execute(ok, delay=0.2, seen=seen), \
                patch.object(L2, "_AgyTracer", side_effect=AssertionError("tracer")), \
                patch.object(L2, "_LOGF", logs.append):
            out, why = L2.call_agy_why("p", timeout=5)
        self.assertEqual((out, why), ("본문", ""))
        self.assertNotIn("agy-heartbeat", seen["threads"])
        self.assertEqual(logs, [])

    def test_off_passes_no_new_kwargs(self):
        res = self.AM.AgyResult(raw="x", rc=0)
        with patch.object(L2, "run_agy", return_value=res) as run:
            L2.call_agy_why("p", timeout=5)
        run.assert_called_once_with("p", timeout=5, workdir=None, model="", allow_argon=False,
                                    fallback_models=())

    def test_on_emits_heartbeats_and_summary(self):
        seen, logs = {}, []
        ok = self.AM.AgyResult(raw="본문", rc=0)
        f, r = self.fake_trace()
        with self.fake_execute(ok, delay=0.4, seen=seen), f, r:
            out, why = L2.call_agy_why("p", timeout=5, heartbeat=logs.append,
                                       heartbeat_note="diff 잘림")
        self.assertEqual((out, why), ("본문", ""))
        self.assertIn("agy-heartbeat", seen["threads"])
        beats = [x for x in logs if x.startswith("[agy 하트비트]")]
        self.assertGreaterEqual(len(beats), 2, logs)
        self.assertIn("턴 2", beats[0])
        self.assertIn("마지막 read_file a.py:1-9", beats[0])
        sums = [x for x in logs if x.startswith("[agy 궤적]")]
        self.assertEqual(len(sums), 1, logs)
        self.assertIn("대화 conv-1", sums[0])
        self.assertIn("(4,9초)", sums[0])
        self.assertIn("diff 잘림", sums[0])
        self.assertEqual(logs[-1], sums[0])
        # 마커는 이번 호출의 BRIEF 디렉터리다
        brief = seen["cmd"][seen["cmd"].index("--add-dir") + 1]
        self.assertTrue(self.markers and all(m == brief for m, _ in self.markers), self.markers)

    def test_not_found_line(self):
        logs = []
        f, r = self.fake_trace(find=lambda marker, *, since: None)
        with self.fake_execute(self.AM.AgyResult(raw="x", rc=0), delay=0.2), f, r:
            L2.call_agy_why("p", timeout=5, heartbeat=logs.append)
        self.assertTrue(any("대화 기록 미발견" in x and x.startswith("[agy 하트비트]") for x in logs), logs)
        self.assertTrue(logs[-1].startswith("[agy 궤적] 대화 기록 미발견"), logs)

    def test_heartbeat_exception_does_not_affect_result(self):
        logs = []

        def boom(marker, *, since):
            raise RuntimeError("trace exploded")
        f, r = self.fake_trace(find=boom)
        ok = self.AM.AgyResult(raw="본문", rc=0)
        with self.fake_execute(ok, delay=0.3), f, r, patch.object(L2, "_LOGF", lambda m: None):
            out, why = L2.call_agy_why("p", timeout=5, heartbeat=logs.append)
        self.assertEqual((out, why), ("본문", ""))
        self.assertFalse(any(x.startswith("[agy 하트비트]") for x in logs), logs)
        # 요약 자리에서도 같은 예외 — 그래도 요약 한 줄은 남고 오류 수를 싣는다
        self.assertTrue(logs and logs[-1].startswith("[agy 궤적] 대화 기록 미발견"), logs)
        self.assertIn("하트비트 오류", logs[-1])
        self.assertIn("trace exploded", logs[-1])

    def test_heartbeat_error_counted_in_summary(self):
        logs, calls = [], []

        def flaky(marker, *, since):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first beat")
            return Path("/fake/conv-1.db")
        f, r = self.fake_trace(find=flaky)
        with self.fake_execute(self.AM.AgyResult(raw="x", rc=0), delay=0.3), f, r:
            L2.call_agy_why("p", timeout=5, heartbeat=logs.append)
        self.assertIn("하트비트 오류 1건", logs[-1])
        self.assertIn("대화 conv-1", logs[-1])

    def test_summary_on_timeout(self):
        logs = []
        f, r = self.fake_trace()
        to = self.AM.AgyResult(raw=None, rc=-1, why="타임아웃 240초")
        with self.fake_execute(to, delay=0.15), f, r, patch.object(L2, "_LOGF", lambda m: None):
            out, why = L2.call_agy_why("p", timeout=5, heartbeat=logs.append)
        self.assertEqual((out, why), (None, "타임아웃 240초"))
        self.assertTrue(logs and logs[-1].startswith("[agy 궤적] 대화 conv-1"), logs)

    def test_tracer_thread_stops(self):
        import threading
        f, r = self.fake_trace()
        with self.fake_execute(self.AM.AgyResult(raw="x", rc=0), delay=0.1), f, r:
            L2.call_agy_why("p", timeout=5, heartbeat=lambda m: None)
        self.assertNotIn("agy-heartbeat", [t.name for t in threading.enumerate()])


if __name__ == "__main__":
    unittest.main()
