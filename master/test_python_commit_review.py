"""Python 커밋 등재부터 최종 리뷰 저장까지 실제 Git·큐로 검증한다."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.context_search.paths import ProjectPaths, SourceScope
from master.context_synth import review_gen as G, review_queue as Q, review_runner as R
from master.events import consumer as C
from master.projects import profile as P


class PythonCommitReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ax-python-review-")
        self.root = Path(self.tmp.name)
        self.paths = ProjectPaths(name="PythonReviewTest", root=self.root,
                                  scope=SourceScope(roots=("src",), exclude=("src/vendor",), exts=(".py",)))
        self.repo = self.paths.repo
        (self.repo / "src").mkdir(parents=True)
        self.git("init", "-q")
        self.git("config", "user.name", "PythonReviewTester")
        self.git("config", "user.email", "python-review@example.invalid")
        self.file = self.repo / "src" / "divide.py"
        self.file.write_text("def divide(value: int, divisor: int) -> float:\n    return value / divisor\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.file.write_text("async def divide(value: int, divisor: int = 0) -> float:\n    return value / divisor\n")
        self.git("add", ".")
        self.git("commit", "-qm", "introduce zero default")
        self.commit = self.git("rev-parse", "HEAD").strip()
        original = P.load
        self.profile = patch.object(P, "load", side_effect=lambda name:
                                   {"kind": "code", "work_exts": [".py"]}
                                   if name == self.paths.name else original(name))
        self.profile.start()

    def tearDown(self):
        self.profile.stop()
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def enqueue(self, files=None):
        result = C.ProjectResult(project_id="test/PythonReview", to_commit=self.commit)
        C._enqueue_review(self.paths, files or ["src/divide.py"], result, commit=self.commit)
        return result

    def test_commit_is_queued_once_and_reviewed_with_python_prompts(self):
        files = ["src/divide.py", "other.py", "src/vendor/ignored.py", "README.md"]
        result = self.enqueue(files)
        self.assertEqual(result.review_queued, self.commit)
        self.enqueue(files)
        self.assertEqual(len(Q.items(self.root)), 1)
        self.assertEqual(Q.items(self.root)[0]["files"], ["src/divide.py"])
        prompts = []
        def local(prompt):
            prompts.append(prompt)
            return "divisor 기본값이 0이며 검사 없이 나눕니다."
        def commercial(prompt):
            prompts.append(prompt)
            return """### src
## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|
## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| src/divide.py | 높음 | 1 | 기본 분모 0으로 ZeroDivisionError | 분모 검사 |
## 3. 영향 분석
기본 인수로 호출하면 실패합니다.
"""
        done = R.run_once(self.paths, draft_call=local, review_call=commercial)
        self.assertEqual(done.state, "done")
        self.assertEqual(Q.counts(self.root)["done"], 1)
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertIn("Python", prompt)
            self.assertNotIn("Unreal Engine", prompt)
            self.assertNotIn("의존 파일·Blueprint 에 줄 수 있는 영향", prompt)
            self.assertNotIn("Source/ModularStage/Mission", prompt)
            self.assertIn("divisor: int=0", prompt.replace(" = ", "="))
        self.assertIn("미검증", prompts[1])
        body = Path(done.written).read_text()
        self.assertTrue(G.format_ok(body))
        self.assertEqual(G.parseable_rows(body), 1)
        self.assertFalse(list((self.root / "reviews" / "_drafts").rglob("*.md")))

    def test_project_kind_selects_prompt_even_with_same_file_extension(self):
        for kind, role in (("unreal", "Unreal Engine 5 C++"), ("code", "Python")):
            with self.subTest(kind=kind), patch.object(P, "load", return_value={"kind": kind}):
                self.assertEqual(G.review_kind(self.paths), kind)
                prompt = G.build_prompt(diff="+pass", files=["src/divide.py"],
                                        commit=self.commit, kind=G.review_kind(self.paths))
                self.assertTrue(prompt.startswith(f"당신은 {role} 코드 리뷰어"))
                local = []
                R.draft("+pass", call=lambda p: local.append(p) or "없음", kind=kind)
                self.assertTrue(local[0].startswith(f"당신은 {role} 리뷰어"))

    def test_declarations_use_commit_instead_of_working_tree(self):
        self.file.write_text("def unrelated_dirty_function():\n    pass\n")
        decls = R.declarations(self.repo, ["src/divide.py"], self.commit)
        self.assertIn("async def divide", decls)
        self.assertIn("divisor", decls)
        self.assertNotIn("unrelated_dirty_function", decls)
        self.assertNotIn("return value", decls)

    def test_index_only_does_not_enqueue(self):
        with patch.object(P, "load", return_value={"kind": "index_only"}):
            result = self.enqueue()
            self.assertIn("색인 전용", result.review_note)
            self.assertFalse(Q.items(self.root))

    def test_outside_source_does_not_enqueue(self):
        result = self.enqueue(["other.py", "src/vendor/ignored.py", "src/wrong.cpp"])
        self.assertIn("소스 변경 없음", result.review_note)
        self.assertFalse(Q.items(self.root))

    def test_syntax_error_still_has_review_diff(self):
        self.file.write_text("def broken(:\n")
        self.git("add", ".")
        self.git("commit", "-qm", "broken syntax")
        commit = self.git("rev-parse", "HEAD").strip()
        self.assertIn("파싱 실패", R.declarations(self.repo, ["src/divide.py"], commit))
        self.assertIn("def broken", G.commit_diff(self.repo, ["src/divide.py"], commit))


if __name__ == "__main__":
    unittest.main()
