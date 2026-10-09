"""#769 위키: 외부 서비스 없이 주입 sender와 실제 라우트 본문·권한 검증."""
import ast
import asyncio
import copy
import io
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master import redmine as rm
from master.auth import BearerAuthMiddleware, REQUESTER_SCOPE, WORKER_SCOPE
from master.task_queue.models import RedmineWikiReq
from client.runtime import client_mcp


class Sender:
    def __init__(self, page=None, failure=None, mismatch=False):
        self.page = copy.deepcopy(page)
        self.calls = []
        self.failure = failure
        self.mismatch = mismatch

    def __call__(self, method, url, payload=None):
        self.calls.append((method, url, copy.deepcopy(payload)))
        if self.failure and self.failure[0] == method:
            raise urllib.error.HTTPError(url, self.failure[1], "failure", {}, io.BytesIO(b"{}"))
        if method == "GET":
            if self.page is None:
                raise urllib.error.HTTPError(url, 404, "missing", {}, io.BytesIO(b""))
            return {"wiki_page": copy.deepcopy(self.page)}
        data = payload["wiki_page"]
        self.page = {"title": "아이디어", "text": data["text"],
                     "version": (self.page or {}).get("version", 0) + 1}
        if data.get("parent_title"):
            self.page["parent"] = {"title": data["parent_title"]}
        if self.mismatch:
            self.page["text"] = "다른 본문"
        return {}


class WikiTests(unittest.TestCase):
    def page(self, text="기존", parent=True):
        out = {"title": "아이디어", "text": text, "version": 3}
        if parent:
            out["parent"] = {"title": "기록"}
        return out

    def put(self, sender, **kw):
        return rm.put_wiki_page("아이디어", "추가", project="ax-cluster", key="fake", sender=sender, **kw)

    def test_append_preserves_parent_and_body(self):
        s = Sender(self.page())
        out = self.put(s)
        self.assertTrue(out["ok"])
        self.assertEqual(s.calls[1][2]["wiki_page"],
                         {"text": "기존\n추가", "comments": "", "version": 3, "parent_title": "기록"})
        self.assertEqual([x[0] for x in s.calls], ["GET", "PUT", "GET"])

    def test_append_separator(self):
        for old in ("", "기존\n"):
            s = Sender(self.page(old, False))
            self.assertTrue(self.put(s)["ok"])
            self.assertEqual(s.page["text"], old + "추가")

    def test_replace_requires_matching_version(self):
        for version in (None, 2):
            s = Sender(self.page())
            self.assertFalse(self.put(s, mode="replace", version=version)["ok"])
            self.assertEqual(len(s.calls), 1)
        s = Sender(self.page())
        self.assertTrue(self.put(s, mode="replace", version=3)["ok"])
        self.assertEqual(s.page["text"], "추가")
        self.assertEqual(s.page["parent"]["title"], "기록")

    def test_append_expected_version(self):
        s = Sender(self.page())
        self.assertFalse(self.put(s, version=2)["ok"])
        self.assertEqual(len(s.calls), 1)

    def test_only_404_creates(self):
        s = Sender()
        out = self.put(s)
        self.assertTrue(out["created"])
        self.assertNotIn("version", s.calls[1][2]["wiki_page"])
        for code in (401, 403, 500):
            s = Sender(failure=("GET", code))
            self.assertFalse(self.put(s)["ok"])
            self.assertEqual(len(s.calls), 1)

    def test_conflict_no_retry(self):
        s = Sender(self.page(), failure=("PUT", 409))
        out = self.put(s)
        self.assertEqual(out["http_status"], 409)
        self.assertFalse(out["retry_safe"])
        self.assertEqual(len(s.calls), 2)

    def test_readback_failure_is_uncertain(self):
        s = Sender(self.page(), mismatch=True)
        self.assertTrue(self.put(s)["possibly_applied"])
        class ReadbackFails(Sender):
            def __call__(self, method, url, payload=None):
                if len(self.calls) == 2:
                    raise OSError("readback unavailable")
                return super().__call__(method, url, payload)
        self.assertTrue(self.put(ReadbackFails(self.page()))["possibly_applied"])
        class BadParent(Sender):
            def __call__(self, method, url, payload=None):
                out = super().__call__(method, url, payload)
                if len(self.calls) == 3:
                    out["wiki_page"]["parent"] = "malformed"
                return out
        self.assertTrue(self.put(BadParent(self.page()))["possibly_applied"])

    def test_unicode_segments_are_quoted(self):
        s = Sender(self.page())
        self.assertTrue(rm.get_wiki_page("한글/?#", project="a/b", key="fake", sender=s)["ok"])
        self.assertIn("/projects/a%2Fb/wiki/", s.calls[0][1])
        self.assertIn("%2F%3F%23.json", s.calls[0][1])

    def test_invalid_input_never_calls_sender(self):
        for kw in ({"version": True}, {"version": 1.5}, {"version": "3"},
                   {"version": 0}, {"mode": "delete"}, {"comments": 2}):
            s = Sender(self.page())
            self.assertFalse(self.put(s, **kw)["ok"])
            self.assertEqual(s.calls, [])
        for value in (True, 1.5, "3"):
            with self.assertRaises(ValueError):
                RedmineWikiReq(title="x", text="y", version=value)

    def routes(self):
        # Compile the actual registered function bodies, avoiding daemon startup side effects.
        tree = ast.parse((Path(__file__).parent / "task_queue/server.py").read_text())
        namespace = {"RedmineWikiReq": RedmineWikiReq, "__package__": "master.task_queue"}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("redmine_wiki_get_ep", "redmine_wiki_put_ep"):
                node.decorator_list = []
                exec(compile(ast.Module(body=[node], type_ignores=[]), "server.py", "exec"), namespace)
        return namespace

    def test_mcp_dispatch_through_routes_and_redmine_sender(self):
        namespace = self.routes()
        sender = Sender(self.page())
        original_get, original_put = rm.get_wiki_page, rm.put_wiki_page
        calls = []
        def api(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "PUT":
                return namespace["redmine_wiki_put_ep"](RedmineWikiReq(**payload, project="AXCluster"))
            query = parse_qs(urlsplit(path).query)
            return namespace["redmine_wiki_get_ep"](query["title"][0], "AXCluster")
        def get(title, **kw):
            kw.setdefault("key", "fake")
            kw.setdefault("sender", sender)
            return original_get(title, **kw)
        def put(title, text, **kw):
            return original_put(title, text, **kw, key="fake", sender=sender)
        with patch.object(rm, "project_of", return_value="ax-cluster"), \
             patch.object(rm, "get_wiki_page", side_effect=get), patch.object(rm, "put_wiki_page", side_effect=put):
            result = client_mcp.dispatch_tool("redmine_put_wiki_page", {"title": "아이디어", "text": "추가"}, api=api)
            self.assertTrue(result["ok"])
            self.assertEqual(result["wiki_page"]["text"], "기존\n추가")
            self.assertEqual(result["version"], 4)
            read = client_mcp.dispatch_tool("redmine_get_wiki_page", {"title": "아이디어"}, api=api)
            self.assertEqual(read["wiki_page"], result["wiki_page"])
        self.assertEqual([call[0] for call in sender.calls], ["GET", "PUT", "GET", "GET"])
        self.assertEqual([call[0] for call in calls], ["PUT", "GET"])

    def test_real_route_bodies_resolve_project_without_fallback(self):
        namespace = self.routes()
        with patch.object(rm, "project_of", return_value="") as resolve, patch.object(rm, "put_wiki_page") as put:
            self.assertFalse(namespace["redmine_wiki_put_ep"](RedmineWikiReq(project="bad", title="x", text="y"))["ok"])
            resolve.assert_called_once_with("bad")
            put.assert_not_called()
        with patch.object(rm, "project_of", return_value="target"), patch.object(rm, "get_wiki_page", return_value={"ok": True}) as get:
            self.assertTrue(namespace["redmine_wiki_get_ep"]("x", "tag")["ok"])
            get.assert_called_once_with("x", project="target")
        with patch.object(rm, "project_of", return_value="target"), patch.object(rm, "put_wiki_page", return_value={"ok": True}) as put:
            namespace["redmine_wiki_put_ep"](RedmineWikiReq(project="tag", title="x", text="y"))
            put.assert_called_once_with("x", "y", project="target", mode="append", version=None, comments="")

    def test_exact_requester_scope_and_worker_denial(self):
        async def status(rules, path, method="PUT"):
            sent = []
            async def inner(scope, receive, send):
                await send({"type": "http.response.start", "status": 200})
            async def receive():
                return {"type": "http.request"}
            async def send(msg):
                sent.append(msg)
            app = BearerAuthMiddleware(inner, "m" * 40, scoped=(("r" * 40, rules),))
            await app({"type": "http", "path": path, "method": method,
                       "headers": [(b"authorization", b"Bearer " + b"r" * 40)]}, receive, send)
            return sent[0]["status"]
        self.assertEqual(asyncio.run(status(REQUESTER_SCOPE, "/api/v1/redmine/wiki")), 200)
        for path in ("/api/v1/redmine/wiki/x", "/api/v1/redmine/wiki2"):
            self.assertEqual(asyncio.run(status(REQUESTER_SCOPE, path)), 403)
        self.assertEqual(asyncio.run(status(WORKER_SCOPE, "/api/v1/redmine/wiki")), 403)
        self.assertEqual(asyncio.run(status(REQUESTER_SCOPE, "/api/v1/redmine/wiki", "DELETE")), 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
