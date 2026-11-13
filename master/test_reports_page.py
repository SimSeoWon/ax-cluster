"""#919 실제 보고서 파일·ASGI 응답으로 목록/링크/경계를 검증한다 (네트워크·임시 Git 0)."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.webui import app, nav, reports_page as RP

SHA_A = "a" * 40
SHA_B = "b" * 40


def request(path="/reports", query=b"", method="GET"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    # 이 화면은 프로젝트 마운트 해석에 의존하지 않아야 한다.
    def unused():
        raise AssertionError("reports must use repository root")

    asyncio.run(app.WebUI(unused)({"type": "http", "method": method,
        "path": path, "query_string": query}, receive, send))
    return messages[0]["status"], messages[1]["body"].decode()


class ReportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reports = self.root / "reports"
        (self.reports / "research").mkdir(parents=True)
        (self.reports / "001-old.md").write_text(
            "# Earlier report\n\n2026-01-01 · 지휘 Codex\n\n#919 변경 `"+SHA_A[:8]+"`\n",
            encoding="utf-8")
        (self.reports / "research" / "2026-02-01-new.md").write_text(
            "> 작성: Gemini · 검증: Codex\n\n# Recent research\n\n"
            "[earlier](../001-old.md) [external](https://example.org/docs)\n",
            encoding="utf-8")
        (self.reports / "999-untracked.md").write_text("# No metadata\n\nplain\n", encoding="utf-8")
        self.root_patch = patch.object(RP, "REPO", self.root)
        self.git_patch = patch.object(RP, "_git", side_effect=self.git)
        self.env_patch = patch.dict(os.environ, {"AX_REDMINE_URL": "http://redmine.test", "AX_GITEA_WEB_URL": "http://gitea.test:3000"})
        self.root_patch.start()
        self.git_patch.start()
        self.env_patch.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.git_patch.stop)
        self.addCleanup(self.env_patch.stop)

    @staticmethod
    def git(*args):
        if args[:3] == ("remote", "get-url", "origin"):
            return "git@gitea.test:Team/cluster.git\n"
        if "--name-only" in args:
            return (f"\x1e{SHA_B}\x002000\x00Commit Writer\n\nreports/research/2026-02-01-new.md\n"
                    f"\x1e{SHA_A}\x001000\x00Git Account\n\nreports/001-old.md\n")
        return SHA_A+"\n"+SHA_B+"\n"

    def test_latest_git_order_and_explicit_fallback(self):
        status, text = request()
        self.assertEqual(status, 200)
        self.assertLess(text.index("Recent research"), text.index("Earlier report"))
        self.assertLess(text.index("Earlier report"), text.index("No metadata"))
        self.assertIn("커밋 시각·작성자 미상 · 파일명순", text)
        self.assertIn("Git Account", text)
        self.assertIn("3개 리포트", text)

    def test_detail_writer_and_git_author_are_separate(self):
        status, text = request(query=b"file=001-old.md")
        self.assertEqual(status, 200)
        self.assertIn("본문 작성 표기: 2026-01-01 · 지휘 Codex", text)
        self.assertIn("Git Account", text)
        self.assertIn("http://redmine.test/issues/919", text)
        self.assertIn("http://gitea.test:3000/Team/cluster/commit/"+SHA_A, text)

    def test_research_writer_and_internal_external_links(self):
        status, text = request(query=b"file=research%2F2026-02-01-new.md")
        self.assertEqual(status, 200)
        self.assertIn("본문 작성 표기: 작성: Gemini · 검증: Codex", text)
        self.assertIn('href="/reports?file=001-old.md"', text)
        self.assertIn('href="https://example.org/docs"', text)

    def test_unknown_writer_not_inferred(self):
        _, text = request(query=b"file=999-untracked.md")
        self.assertIn("본문 작성 표기: 미상", text)

    def test_kind_and_text_filters(self):
        _, text = request(query=b"kind=research")
        self.assertIn("1개 리포트", text)
        self.assertIn("Recent research", text)
        self.assertNotIn(">Earlier report</a>", text)
        _, text = request(query=b"kind=work&q=919")
        self.assertIn("1개 리포트", text)
        self.assertIn("Earlier report", text)
        self.assertEqual(request(query=b"kind=other")[0], 400)

    def test_nested_runs_and_other_directories_not_listed(self):
        (self.reports / "research" / "run").mkdir()
        (self.reports / "research" / "run" / "secret.md").write_text("# Hidden run")
        (self.reports / "debates").mkdir()
        (self.reports / "debates" / "secret.md").write_text("# Hidden debate")
        _, text = request()
        self.assertNotIn("Hidden run", text)
        self.assertNotIn("Hidden debate", text)
        self.assertEqual(request(query=b"file=research/run/secret.md")[0], 400)

    def test_traversal_and_encoding_are_rejected(self):
        for value in (b"../AGENTS.md", b"%2e%2e%2fAGENTS.md", b"%252e%252e%252fAGENTS.md",
                      b"/etc/passwd", b"C%3A%5Csecret.md", b"research//x.md", b"research/./x.md",
                      b".hidden.md", b"%00.md"):
            with self.subTest(value=value):
                status, text = request(query=b"file="+value)
                self.assertEqual(status, 400)
                self.assertNotIn(str(self.root), text)

    def test_symlink_file_and_directory_are_rejected(self):
        outside = self.root / "outside.md"
        outside.write_text("# Private content")
        (self.reports / "linked.md").symlink_to(outside)
        status, text = request(query=b"file=linked.md")
        self.assertEqual(status, 400)
        self.assertNotIn("Private content", text)
        _, text = request()
        self.assertNotIn("Private content", text)
        target = self.root / "elsewhere"
        target.mkdir()
        (target / "inside.md").write_text("# Private dir")
        # research 디렉터리가 링크로 바뀌어도 그 실체를 읽지 않는다.
        (self.reports / "research").rename(self.reports / "old-research")
        (self.reports / "research").symlink_to(target, target_is_directory=True)
        self.assertEqual(request(query=b"file=research/inside.md")[0], 400)
        self.assertNotIn("Private dir", request()[1])

    def test_missing_file_and_root(self):
        self.assertEqual(request(query=b"file=absent.md")[0], 404)
        with patch.object(RP, "REPO", self.root / "absent"):
            status, text = request()
        self.assertEqual(status, 200)
        self.assertIn("0개 리포트", text)

    def test_markdown_preserves_structures_and_escapes_html(self):
        text = ("# Heading\n\n<script>alert(1)</script>\n\n"
                "```html\n<img src=x onerror=alert(1)> #919\n```\n\n"
                "| Name | Value |\n|---|---|\n| **bold** | `code` |\n\n"
                "1. first\n2. second\n\n- bullet\n\n> quote\n")
        (self.reports / "safe.md").write_text(text)
        status, output = request(query=b"file=safe.md")
        self.assertEqual(status, 200)
        self.assertNotIn("<script>", output)
        self.assertNotIn("<img", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("<pre><code>&lt;img", output)
        self.assertIn("<thead>", output)
        self.assertIn("<ol>", output)
        self.assertIn("<ul>", output)
        self.assertIn("<blockquote>", output)

    def test_unsafe_links_are_plain_and_hash_must_be_real(self):
        (self.reports / "links.md").write_text(
            "# Links\n\n[bad](javascript:alert(1)) [file](file:///etc/passwd) "
            "[hidden](../AGENTS.md) [relative](001-old.md) "
            "`deadbee` #919 `"+SHA_A[:8]+"`\n")
        _, text = request(query=b"file=links.md")
        self.assertNotIn('href="javascript:', text)
        self.assertNotIn('href="file:', text)
        self.assertNotIn('href="../', text)
        self.assertIn('href="/reports?file=001-old.md"', text)
        self.assertNotIn("/commit/deadbee", text)
        self.assertIn("/commit/"+SHA_A, text)

    def test_git_unavailable_is_visible_fallback(self):
        with patch.object(RP, "_git", side_effect=OSError("/secret/key")):
            status, text = request()
        self.assertEqual(status, 200)
        self.assertIn("Git 이력 조회 불가", text)
        self.assertNotIn("/secret/key", text)

    def test_malformed_link_and_tab_heading_keep_report_readable(self):
        (self.reports / "malformed.md").write_text(
            "#\tTab heading\n\n[broken](http://[broken) plain text after link\n")
        status, text = request(query=b"file=malformed.md")
        self.assertEqual(status, 200)
        self.assertIn("<h2>Tab heading</h2>", text)
        self.assertIn("plain text after link", text)
        self.assertNotIn('href="http://[broken', text)

    def test_remote_host_mismatch_does_not_invent_commit_links(self):
        with patch.dict(os.environ, {"AX_GITEA_WEB_URL": "https://elsewhere.test"}):
            _, text = request(query=b"file=001-old.md")
        self.assertNotIn("/commit/", text)
        self.assertIn(SHA_A[:12], text)

    def test_router_read_only_and_navigation(self):
        for path in ("/reports", "/reports/"):
            with self.subTest(path=path):
                status, text = request(path)
                self.assertEqual(status, 200)
                self.assertEqual(text.count('<nav class="side">'), 1)
                self.assertEqual(text.count('class="item on"'), 1)
                self.assertIn('class="item on" href="/reports"', text)
                for route, _, _ in nav.ITEMS:
                    self.assertIn('href="'+route+'"', text)
        for method in ("POST", "DELETE", "PATCH"):
            self.assertEqual(request(method=method)[0], 405)
        self.assertIn("/reports", app.PREFIXES)


if __name__ == "__main__":
    unittest.main()
