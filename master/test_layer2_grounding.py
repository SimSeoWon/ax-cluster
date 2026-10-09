"""#696: 기준 커밋의 선언과 완전한 검증 입력. 외부 모델/네트워크 없이 검사한다."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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


if __name__ == "__main__":
    unittest.main()
