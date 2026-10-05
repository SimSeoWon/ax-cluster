"""공용 좌측 목록이 **8103 의 모든 화면**에 있다 (사용자 결정 2026-10-04, 「a-1」).

검증하는 것 — ASGI 앱을 프로세스 안에서 불러 실제 응답 본문을 본다(라이브 조회 0):

    ① 화면마다 `<nav class="side">` 하나 · `/usage` 링크 · 켜진 항목(`class="item on"`)은 **정확히
       하나**이고 그 화면의 경로다 (`/` · `/ontology`(하위 화면 포함) · `/cluster` · `/reviews`)
    ② 원전 화면의 본문 표지가 그대로 있다 — 감싸기가 원전을 지우지 않았다
    ③ [중요] 화면마다 끼우던 옛 링크 버튼(`온보딩 →`·`리뷰·플랜 →`·`클러스터 상태 →`)은 걷혔다
    ④ [중요] 원전 파일(`web_ui_original.py`·`static/ontology/*`)은 바이트 그대로다 — 감싸기는
       서빙 시점의 일이다

`.venv/bin/python -B -m unittest master.test_webui_side_nav`
"""
import asyncio
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

# 통합 검사는 스크립트로 단독 실행한다(`tests/integration/checks.json`) — 저장소 루트를 경로에 둔다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master import status
from master.context_synth import fix_index
from master.webui import app, fixes_page, orchestration, routes


def _request(webui, path, query=b""):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(webui({"type": "http", "method": "GET", "path": path,
                       "query_string": query}, receive, send))
    start, body = messages
    return start["status"], body["body"].decode("utf-8")


class SideNavEverywhereTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        # 클러스터 스냅샷 — 실제 `status.render` 가 만든 자립형 HTML
        (root / "cluster.html").write_text(
            status.render(status.Snapshot(at="2026-10-04 00:00:00Z", seconds=1.0)),
            encoding="utf-8")
        self.paths = SimpleNamespace(root=root, name="T")
        self.webui = app.WebUI(lambda: self.paths)

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_nav(self, text, current):
        self.assertEqual(text.count('<nav class="side">'), 1)
        self.assertIn('href="/usage"', text)
        self.assertEqual(text.count('class="item on"'), 1, re.findall(r'class="item on"[^>]*', text))
        self.assertIn(f'class="item on" href="{current}"', text)
        # 목록은 본문 앞, 본문은 <main> 안
        self.assertLess(text.index('<nav class="side">'), text.index("<main>"))
        self.assertLess(text.index("<main>"), text.rindex("</main>"))
        self.assertLess(text.rindex("</main>"), text.lower().rindex("</body>"))
        for old in ("온보딩 →", "리뷰·플랜 →", "클러스터 상태 →", "/ 클러스터 상태"):
            self.assertNotIn(old, text)

    def test_context_search(self):
        st, text = _request(self.webui, "/")
        self.assertEqual(st, 200)
        self._assert_nav(text, "/")
        for marker in ('id="searchQuery"', 'id="statusCards"', 'class="container"',
                       "Ontology Viewer →"):
            self.assertIn(marker, text)

    def test_ontology_pages(self):
        cases = (("/ontology", ('id="treeNav"', 'class="board-shell"')),
                 ("/ontology/domain/Any", ('id="treeNav"', 'class="layout"', 'id="sidebar"')),
                 ("/ontology/task/Any", ('class="board task-detail"', "← 게시판")))
        for path, markers in cases:
            with self.subTest(path=path):
                st, text = _request(self.webui, path)
                self.assertEqual(st, 200)
                self._assert_nav(text, "/ontology")
                self.assertIn("/ontology-static/app.css", text)
                for marker in markers:
                    self.assertIn(marker, text)

    def test_cluster(self):
        with patch.object(status, "fetch_live", return_value={"error": "offline"}), \
                patch.object(orchestration, "section", return_value=""):
            st, text = _request(self.webui, "/cluster")
        self.assertEqual(st, 200)
        self._assert_nav(text, "/cluster")
        self.assertIn("<h1>AX 클러스터 상태</h1>", text)
        self.assertNotIn("← Context Search", text)
        self.assertNotIn(status.LIVE_MARK, text)

    def test_cluster_missing_snapshot_still_has_nav(self):
        (self.paths.root / "cluster.html").unlink()
        st, text = _request(self.webui, "/cluster")
        self.assertEqual(st, 503)
        self._assert_nav(text, "/cluster")
        self.assertIn("python -m master.status html", text)
        self.assertNotIn(str(self.paths.root), text)

    def test_reviews_list_and_detail(self):
        resolved = (None, ["T"], self.paths)
        with patch.object(fixes_page, "_resolve", return_value=resolved), \
                patch.object(fix_index, "list_docs", return_value={"docs": []}), \
                patch.object(fix_index, "get_doc", return_value={"ok": False, "reason": "없다"}):
            st, text = _request(self.webui, "/reviews")
            self.assertEqual(st, 200)
            self._assert_nav(text, "/reviews")
            self.assertNotIn('class="nav"', text)
            st, text = _request(self.webui, "/reviews/R1")
            self.assertEqual(st, 404)
            self._assert_nav(text, "/reviews")
            self.assertIn("← T 목록", text)


class OriginalsUntouchedTests(unittest.TestCase):
    def test_wrap_does_not_touch_original_bytes(self):
        """감싸기는 응답에만 — 원전 문자열·파일은 그대로다."""
        from master.webui.web_ui_original import WEB_UI_HTML
        self.assertNotIn('<nav class="side">', WEB_UI_HTML)
        for name in ("index.html", "domain.html", "task.html"):
            self.assertNotIn(b'<nav class="side">', routes.page(name))

    def test_wrap_falls_back_without_markers(self):
        out = routes.wrap_side_nav("<p>x</p>", "/cluster")
        self.assertIn("<style>", out)
        self.assertLess(out.index('<nav class="side">'), out.index("<p>x</p>"))
        self.assertIn('class="item on" href="/cluster"', out)
        self.assertTrue(out.endswith("</main></div>"))

    def test_wrap_places_style_inside_head_regardless_of_case(self):
        for closing in ("</HEAD>", "</HeAd>", "</head>"):
            with self.subTest(closing=closing):
                prefix = "<!doctype html><html><HEAD><title>İ 원문</title>"
                original = prefix + closing + "<body><p>내용</p></body></html>"
                out = routes.wrap_side_nav(original, "/cluster")
                self.assertEqual(out[:out.index("<style>")], prefix)
                self.assertIn("</style>" + closing + "<body>", out)
                self.assertEqual(out.count("<style>"), 1)


if __name__ == "__main__":
    unittest.main()
