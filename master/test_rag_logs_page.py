"""#837 저장된 검색 스냅샷과 원문 연결·안전한 출력 검사. 라이브 호출 없음."""
import html
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.webui import rag_logs


class RAGLogsPageTests(unittest.TestCase):
    def setUp(self):
        self.paths = SimpleNamespace(name="AXCluster")
        self.entry = {
            "search_id": "search-one", "request_id": "request-one", "ts": "2026-10-18T10:00:00+00:00",
            "task_type": "user_task", "user_request": '<script>alert("원문")</script>',
            "query": "LLM 질의", "query_expanded": "별칭 확장", "query_used": "실제 검색어",
            "status": "success", "caller": "mcp", "user_request_source": "explicit",
            "result_snapshot": [{"rank": 1, "file_id": "old.md", "source": "vector+bm25",
                                 "rrf_score": 0.024, "excerpt": "당시 <본문>"}],
        }

    def test_snapshot_and_origin_are_escaped_and_grouped(self):
        second = dict(self.entry, search_id="search-two", query="두 번째 질의")
        text = rag_logs.render({"items": [self.entry, second], "total": 2}).decode()
        self.assertEqual(text.count('<section class="group">'), 1)
        self.assertEqual(text.count("사용자 명령 원문</h3>"), 1)
        self.assertNotIn('<script>alert', text)
        self.assertIn('&lt;script&gt;', text)
        for value in ("LLM 질의", "별칭 확장", "실제 검색어", "old.md", "당시 &lt;본문&gt;", "rrf_score: 0.024"):
            self.assertIn(value, text)
        self.assertIn('class="item on" href="/rag-logs"', text)

    def test_filters_forwarded_to_reader(self):
        loader = Mock(return_value={"items": [], "total": 0, "offset": 0, "limit": 50})
        status, _ = rag_logs.page(self.paths, {"query": "검색", "status": "missing_origin", "start": "2026-10-01"},
                                  loader=loader, detail_loader=Mock())
        self.assertEqual(status, 200)
        loader.assert_called_once_with(self.paths, task_type="", query="검색", request_id="", status="missing_origin",
                                       date_from="2026-10-01", date_to="", offset=0, limit=50)

    def test_detail_loads_same_request_without_search_filters(self):
        loader = Mock(return_value={"items": [self.entry], "total": 1, "offset": 0, "limit": 50})
        detail = Mock(return_value=self.entry)
        status, text = rag_logs.page(self.paths, {"search_id": "search-one", "query": "다른 검색", "status": "error"},
                                     loader=loader, detail_loader=detail)
        self.assertEqual(status, 200)
        detail.assert_called_once_with(self.paths, "search-one")
        self.assertEqual(loader.call_args.kwargs["request_id"], "request-one")
        self.assertEqual(loader.call_args.kwargs["query"], "")
        self.assertIn(b'<details open>', text)

    def test_legacy_missing_origin_and_error_do_not_invent_accuracy(self):
        legacy = {"query": "이전 검색", "result_details": [{"file_id": "old.md"}]}
        error = {"search_id": "error", "task_type": "auto_review", "status": "error",
                 "error": "/private/server/key.json", "result_snapshot": []}
        text = rag_logs.render({"items": [legacy, error], "total": 2}).decode()
        self.assertIn("사용자 명령 원문 미수집", text)
        self.assertIn("자동 작업", text)
        self.assertIn("이전 형식 로그", text)
        self.assertNotIn("/private/server/key.json", text)
        self.assertIn("정답 적중률을 뜻하지 않습니다", text)

    def test_synthesis_origin_states_are_distinguished(self):
        automatic = dict(self.entry, task_type="context_synthesis", user_request=None)
        text = rag_logs.render({"items": [automatic], "total": 1}).decode()
        self.assertIn("자동 작업 · 사용자 명령 원문 없음", text)
        self.assertNotIn("사용자 명령 원문 미수집", text)
        missing = dict(automatic, task_type="user_task")
        text = rag_logs.render({"items": [missing], "total": 1}).decode()
        self.assertIn("사용자 명령 원문 미수집", text)
        explicit = dict(automatic, user_request="자동합성에 전달한 원문")
        text = rag_logs.render({"items": [explicit], "total": 1}).decode()
        self.assertIn("자동합성에 전달한 원문", text)
        self.assertNotIn("자동 작업 · 사용자 명령 원문 없음", text)

    def test_old_selection_is_separate_from_fifty_item_request_page(self):
        entries = [dict(self.entry, search_id=f"new-{index}", query=f"새 검색 {index}") for index in range(50)]
        selected = dict(self.entry, search_id="old-selected", query="선택한 오래된 질의",
                        result_snapshot=[{"excerpt": "오래된 검색의 반환 본문"}])
        loader = Mock(return_value={"items": entries, "total": 51, "offset": 0, "limit": 50})
        status, body = rag_logs.page(self.paths, {"search_id": "old-selected", "offset": "50"},
                                     loader=loader, detail_loader=Mock(return_value=selected))
        text = body.decode()
        self.assertEqual(status, 200)
        self.assertEqual(loader.call_args.kwargs["offset"], 0)
        self.assertEqual(loader.call_args.kwargs["request_id"], "request-one")
        self.assertIn("선택한 검색 상세", text)
        self.assertIn("검색 51건 · 이번 화면 50건", text)
        self.assertEqual(text.count('<details open>'), 1)
        self.assertEqual(text.count("오래된 검색의 반환 본문"), 1)
        self.assertIn("offset=50", text)
        self.assertIn(">다음</a>", text)
        self.assertNotIn(">이전</a>", text)
        pager = text.split('<div class="pager">', 1)[1]
        next_url = html.unescape(pager.split('href="', 1)[1].split('"', 1)[0])
        next_filters = {key: values[0] for key, values in parse_qs(urlsplit(next_url).query).items()}
        self.assertNotIn("search_id", next_filters)
        self.assertEqual(next_filters["offset"], "50")
        self.assertEqual(next_filters["request_id"], "request-one")
        next_loader = Mock(return_value={"items": [selected], "total": 51, "offset": 50, "limit": 50})
        next_detail = Mock()
        status, next_body = rag_logs.page(self.paths, next_filters, loader=next_loader, detail_loader=next_detail)
        self.assertEqual(status, 200)
        next_detail.assert_not_called()
        self.assertEqual(next_loader.call_args.kwargs["offset"], 50)
        self.assertNotIn(">다음</a>", next_body.decode())
        self.assertIn(">이전</a>", next_body.decode())

    def test_selection_on_page_is_not_duplicated_or_counted_twice(self):
        loader = Mock(return_value={"items": [self.entry], "total": 1, "offset": 0, "limit": 50})
        status, body = rag_logs.page(self.paths, {"search_id": "search-one"},
                                     loader=loader, detail_loader=Mock(return_value=self.entry))
        text = body.decode()
        self.assertEqual(status, 200)
        self.assertEqual(text.count('<details open>'), 1)
        self.assertEqual(text.count("당시 &lt;본문&gt;"), 1)
        self.assertIn("검색 1건 · 이번 화면 1건", text)
        self.assertNotIn("선택한 검색 상세", text)
        self.assertNotIn(">다음</a>", text)

    def test_date_filter_labels_match_recorded_timezone(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = SimpleNamespace(name="AXCluster", root=root, search_log=root / "search_log.jsonl")
            entries = [dict(self.entry, search_id="before", ts="2026-10-19T23:59:00+09:00", query="전날 질의"),
                       dict(self.entry, search_id="after", ts="2026-10-20T00:01:00+09:00", query="당일 질의")]
            paths.search_log.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
            status, body = rag_logs.page(paths, {"start": "2026-10-20", "end": "2026-10-20"})
        text = body.decode()
        self.assertEqual(status, 200)
        self.assertNotIn("(UTC)", text)
        self.assertIn("로그 기록일 기준", text)
        self.assertIn("KST(+09:00)", text)
        self.assertIn("2026-10-20T00:01:00+09:00", text)
        self.assertIn("당일 질의", text)
        self.assertNotIn("전날 질의", text)
        self.assertIn("검색 1건 · 이번 화면 1건", text)

    def test_invalid_filters_and_read_failure_are_safe(self):
        loader = Mock(side_effect=OSError("/private/server/key.json"))
        status, body = rag_logs.page(self.paths, {"start": "not-a-date"}, loader=loader, detail_loader=Mock())
        self.assertEqual(status, 400)
        loader.assert_not_called()
        status, body = rag_logs.page(self.paths, {}, loader=loader, detail_loader=Mock())
        self.assertEqual(status, 503)
        self.assertNotIn(b"/private", body)
        status, _ = rag_logs.page(self.paths, {"search_id": "../../private"}, loader=loader,
                                  detail_loader=Mock(return_value=None))
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
