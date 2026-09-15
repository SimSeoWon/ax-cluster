"""리뷰·플랜 수정 워크플로우의 표면 (`#629`·`#630`) — 토큰 · 공개 화면 · 클라 도구 · `.33` 흐름.

검증하는 것:

    ① 스코프 — 요청자만 `/fixes` 를 연다 (토큰 없음 401 · 워커 403) · `/api/v1` 밖이다
    ② 8103 — `/reviews` 는 공개 접두에 있고 `/fixes` 는 없다 · 태그 정책이 선언돼 있다
    ③ [중요] 공개 화면에 본문·지적 설명·소스 경로가 없다 · 작성자 이름은 이스케이프된다
    ④ 클라 도구 — 경로·인코딩·상태 검증 · 결정 도구 금지어에 걸리지 않는다
    ⑤ fix_flow 대조 — **실제 git 저장소**에서 단서 넷(unchanged·line_present·line_missing·gone)
       · [중요] fetch 가 실패하면 낡은 main 으로 대조하지 않고 멈춘다
    ⑥ fix_flow worktree — [중요] 사람 체크아웃의 브랜치를 바꾸지 않는다 · 재사용은 리셋하지 않는다
    ⑦ 배달 — 스킬·payload 가 요청자에게 가고 fix_flow 는 stdlib 만 쓴다

`.venv/bin/python master/test_fixes_surface.py`
"""
from __future__ import annotations

import ast
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.auth import BearerAuthMiddleware, REQUESTER_SCOPE, WORKER_SCOPE   # noqa: E402
from master.context_synth import fix_index as FX                             # noqa: E402
from master.test_fix_index import SECRET_DESC, SECRET_PATH, make_root         # noqa: E402
from client.runtime import client_mcp as M                                    # noqa: E402
from client.runtime import fix_flow as FF                                     # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── ① 스코프 ────────────────────────────────────────────────────────────────

def _status(method: str, path: str, token) -> int:
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
    app = BearerAuthMiddleware(inner, "admin-token-xxxxxxxx",
                               scoped=(("requester-token-xx", REQUESTER_SCOPE),
                                       ("worker-token-xxxxx", WORKER_SCOPE)))
    out = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(ev):
        out.append(ev)
    headers = [] if token is None else [(b"authorization", f"Bearer {token}".encode())]
    asyncio.run(app({"type": "http", "method": method, "path": path, "headers": headers},
                    receive, send))
    return out[0]["status"]


def test_scope():
    rq, wk = "requester-token-xx", "worker-token-xxxxx"
    check("① 요청자 GET /fixes 200", _status("GET", "/fixes", rq) == 200)
    check("① 요청자 GET /fixes/R12 200", _status("GET", "/fixes/R12", rq) == 200)
    check("① 요청자 POST /fixes/R12-3/status 200", _status("POST", "/fixes/R12-3/status", rq) == 200)
    check("① 요청자라도 다른 쓰기 경로는 403", _status("POST", "/fixes/R12-3/delete", rq) == 403)
    check("① [중요] 워커는 403", _status("GET", "/fixes", wk) == 403)
    check("① [중요] 토큰 없으면 401", _status("GET", "/fixes", None) == 401)
    check("① [중요] `/api/v1` 아래가 아니다 (8103 무인증 접두 회피)",
          not any(r[1].startswith("/api/v1/fixes") for r in REQUESTER_SCOPE))


# ── ② 8103 공개 접두 · 태그 정책 ────────────────────────────────────────────

def test_public_prefix_and_policy():
    from master.webui.app import PREFIXES
    from master.task_queue import tagging
    check("② /reviews 는 8103 공개 화면이다", "/reviews" in PREFIXES, str(PREFIXES))
    check("② [중요] /fixes 는 8103 공개 접두에 없다", not any(p.startswith("/fixes") for p in PREFIXES))
    for key in ("GET /fixes", "GET /fixes/{serial}", "POST /fixes/{item}/status"):
        check(f"② 태그 정책 선언: {key}", tagging.POLICY.get(key) == tagging.MOUNT,
              str(tagging.POLICY.get(key)))
    src = (Path(__file__).parent / "task_queue" / "server.py").read_text(encoding="utf-8")
    for deco in ('@app.get("/fixes")', '@app.get("/fixes/{serial}")',
                 '@app.post("/fixes/{item}/status")'):
        check(f"② 서버 라우트가 정책 키와 같은 글자다: {deco}", deco in src)


# ── ③ 공개 화면 ─────────────────────────────────────────────────────────────

class FakeRegistry:
    def __init__(self, dirs: dict, active: str):
        self._dirs = dirs
        self.active = active

    @property
    def names(self):
        return list(self._dirs)

    def dir_of(self, name):
        return self._dirs[name]


def test_public_page_has_no_body():
    from master.webui import fixes_page
    root = make_root()
    FX.set_status(root, "R1-1", "applied", branch="fix/R1")
    reg = FakeRegistry({"NS": root, "ModularStage": root}, "NS")
    st, text = fixes_page.render("", registry=reg)
    check("③ 200", st == 200, text[:200])
    check("③ [중요] 지적 설명이 화면에 없다", SECRET_DESC not in text)
    check("③ [중요] 소스 경로가 화면에 없다", SECRET_PATH not in text)
    check("③ 번호가 보인다", "R1" in text and "P1" in text)
    check("③ 결정 상태 칩이 보인다", "적용됨 1" in text and "미결 2" in text, text[-1500:])
    check("③ 프로젝트 탭이 있다", "/reviews?project=ModularStage" in text)

    evil = [{"serial": "R9", "kind": "review", "author": "<script>x</script>", "created": "",
             "commit": "", "files": 0, "items": 0, "severity": {}, "states": {}}]
    st, text = fixes_page.render("NS", registry=reg, list_docs=lambda r: {"docs": evil})
    check("③ [중요] 작성자 이름을 이스케이프한다", "<script>x</script>" not in text
          and "&lt;script&gt;" in text)

    def boom(r):
        raise OSError(f"{root}/fixes/index.json 권한 없음")
    st, text = fixes_page.render("NS", registry=reg, list_docs=boom)
    check("③ [중요] 실패해도 예외 문자열(절대 경로)을 싣지 않는다",
          st == 500 and str(root) not in text, text[-300:])
    shutil.rmtree(root)


# ── ④ 클라 도구 ─────────────────────────────────────────────────────────────

def test_client_tools():
    calls = []

    def api(m, p, pl=None):
        calls.append((m, p, pl))
        return {"ok": True}
    M.dispatch_tool("list_fixes", {}, api=api)
    check("④ list_fixes → GET /fixes", calls[-1] == ("GET", "/fixes", None), str(calls[-1]))
    M.dispatch_tool("get_fix", {"serial": "R12"}, api=api)
    check("④ get_fix → GET /fixes/R12", calls[-1] == ("GET", "/fixes/R12", None), str(calls[-1]))
    M.dispatch_tool("update_fix_status", {"item": "R12-3", "state": "applied",
                                          "branch": "fix/R12", "note": ""}, api=api)
    check("④ update_fix_status → POST /fixes/R12-3/status (빈 값은 안 싣는다)",
          calls[-1] == ("POST", "/fixes/R12-3/status", {"state": "applied", "branch": "fix/R12"}),
          str(calls[-1]))
    for args in ({"item": "R12-3", "state": "done"}, {"item": "", "state": "applied"}):
        try:
            M.dispatch_tool("update_fix_status", args, api=api)
            check(f"④ 거절: {args}", False)
        except M.ClientError:
            check(f"④ 거절: {args}", True)
    try:
        M.dispatch_tool("get_fix", {"serial": " "}, api=api)
        check("④ 빈 번호 거절", False)
    except M.ClientError:
        check("④ 빈 번호 거절", True)
    names = {t["name"] for t in M.TOOLS}
    check("④ 도구 셋이 등록돼 있다", {"list_fixes", "get_fix", "update_fix_status"} <= names)
    for banned in ("decide", "patch", "merge", "reject", "finalize", "approve"):
        check(f"④ 결정 도구 금지어에 걸리지 않는다: {banned}",
              not any(banned in n for n in ("list_fixes", "get_fix", "update_fix_status")))


# ── ⑤⑥ fix_flow — 실제 git ──────────────────────────────────────────────────

def _git(cwd, *a) -> str:
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo(tmp: Path) -> tuple:
    bare = tmp / "remote.git"
    work = tmp / "Game"
    _git(tmp, "init", "--bare", "-b", "main", str(bare))
    _git(tmp, "init", "-b", "main", str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    src = work / "Source"
    src.mkdir()
    (src / "A.cpp").write_text("void A() {\n  auto* P = Get();\n  P->Run();\n}\n", encoding="utf-8")
    (src / "B.cpp").write_text("int B = 0;\nint C = 1;\n", encoding="utf-8")
    (src / "D.cpp").write_text("int D = 0;\n", encoding="utf-8")
    (src / "E.cpp").write_text("int E = 0;\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "reviewed")
    reviewed = _git(work, "rev-parse", "HEAD")
    (src / "A.cpp").write_text("// 머리\nvoid A() {\n  auto* P = Get();\n  P->Run();\n}\n",
                               encoding="utf-8")
    (src / "B.cpp").write_text("int B = 0;\nint C = 2;\n", encoding="utf-8")
    (src / "D.cpp").unlink()
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "later")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "main")
    return work, reviewed


def _doc(work: Path, commit: str) -> None:
    items = [{"id": "R1-1", "file": "Source/A.cpp", "line": "3", "severity": "high",
              "description": "null 역참조", "recommendation": "IsValid"},
             {"id": "R1-2", "file": "`Source/B.cpp`", "line": "2", "severity": "mid",
              "description": "C 값 | 파이프", "recommendation": ""},
             {"id": "R1-3", "file": "Source/D.cpp", "line": "1", "severity": "low",
              "description": "D", "recommendation": ""},
             {"id": "R1-4", "file": "Source/E.cpp", "line": "1", "severity": "low",
              "description": "E", "recommendation": ""}]
    d = FF.work_dir(work, "R1")
    (d / "doc.json").write_text(json.dumps({"ok": True, "serial": "R1", "kind": "review",
                                            "commit_full": commit, "items_detail": items},
                                           ensure_ascii=False), encoding="utf-8")


def test_flow_check_real_git():
    tmp = Path(tempfile.mkdtemp(prefix="fixflow-"))
    try:
        work, reviewed = _repo(tmp)
        _doc(work, reviewed)
        res = FF.cmd_check(work, "r1", fetch=True)
        hints = {r["id"]: r["hint"] for r in res["items"]}
        check("⑤ 줄이 밀렸지만 남아 있다 → line_present", hints.get("R1-1") == "line_present", str(hints))
        a = next(r for r in res["items"] if r["id"] == "R1-1")
        check("⑤ 지금 줄 번호를 찾는다 (3 → 4)", a.get("now_lines") == [4], str(a))
        check("⑤ 지적한 줄이 바뀌었다 → line_missing (백틱 경로도 푼다)",
              hints.get("R1-2") == "line_missing", str(hints))
        check("⑤ 파일이 지워졌다 → gone", hints.get("R1-3") == "gone", str(hints))
        check("⑤ 안 바뀌었다 → unchanged", hints.get("R1-4") == "unchanged", str(hints))
        check("⑤ 리뷰 커밋이 main 에 들어갔다", res.get("commit_in_main") is True, str(res))
        md = (work / ".ax" / "fixes" / "R1" / "check.md").read_text(encoding="utf-8")
        check("⑤ check.md 에 지적과 단서가 있다", "null 역참조" in md and "남아 있다" in md, md[:400])
        check("⑤ 표 칸의 파이프를 이스케이프한다", "C 값 \\| 파이프" in md, md)
        log = (work / ".ax" / "fixes" / "R1" / "flow.log").read_text(encoding="utf-8")
        check("⑤ 단계가 flow.log 에 남는다", "git fetch origin main rc=0" in log and "대조" in log, log)

        _git(work, "remote", "set-url", "origin", str(tmp / "없는원격.git"))
        try:
            FF.cmd_check(work, "R1", fetch=True)
            check("⑤ [중요] fetch 실패면 멈춘다", False)
        except FF.FlowError as e:
            check("⑤ [중요] fetch 실패면 멈춘다", "fetch" in str(e), str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flow_worktree_leaves_checkout_alone():
    tmp = Path(tempfile.mkdtemp(prefix="fixwt-"))
    try:
        work, _ = _repo(tmp)
        (work / "Source" / "E.cpp").write_text("// 사람이 고치던 중\n", encoding="utf-8")
        head = _git(work, "rev-parse", "HEAD")
        got = FF.cmd_worktree(work, "R1")
        wt = Path(got["path"])
        check("⑥ 체크아웃 옆에 worktree", wt == (tmp / "ax-fix-R1").resolve() and wt.is_dir(), str(got))
        check("⑥ fix/R1 브랜치", _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "fix/R1")
        check("⑥ [중요] 사람 체크아웃의 브랜치·HEAD 그대로",
              _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main"
              and _git(work, "rev-parse", "HEAD") == head)
        check("⑥ [중요] 사람의 미커밋 변경 그대로",
              (work / "Source" / "E.cpp").read_text(encoding="utf-8") == "// 사람이 고치던 중\n")
        (wt / "Source" / "A.cpp").write_text("// 고침\n", encoding="utf-8")
        again = FF.cmd_worktree(work, "R1")
        check("⑥ 두 번째는 재사용", again["reused"] is True, str(again))
        check("⑥ [중요] 재사용은 리셋하지 않는다",
              (wt / "Source" / "A.cpp").read_text(encoding="utf-8") == "// 고침\n")
        (tmp / "ax-fix-R2").mkdir()
        try:
            FF.cmd_worktree(work, "R2")
            check("⑥ worktree 아닌 디렉토리는 덮지 않는다", False)
        except FF.FlowError:
            check("⑥ worktree 아닌 디렉토리는 덮지 않는다", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flow_fetch_and_status_with_fake_api():
    tmp = Path(tempfile.mkdtemp(prefix="fixapi-"))
    try:
        calls = []

        def api(m, p, pl=None):
            calls.append((m, p, pl))
            if p.startswith("/fixes/R7") and m == "GET":
                return {"ok": True, "serial": "R7", "kind": "review", "items": 2, "body": "# 본문\n"}
            if p.endswith("/status"):
                return {"ok": pl.get("state") != "failed", "reason": "막힘"}
            return {"ok": False, "reason": "R8 는 없는 번호다"}
        FF.cmd_fetch(tmp, "R7-2", api=api)
        check("⑤ 내려받기는 문서 번호로 부른다", calls[-1][1] == "/fixes/R7", str(calls[-1]))
        check("⑤ doc.md 에 본문", (tmp / ".ax/fixes/R7/doc.md").read_text(encoding="utf-8") == "# 본문\n")
        try:
            FF.cmd_fetch(tmp, "R8", api=api)
            check("⑤ 거절은 FlowError", False)
        except FF.FlowError as e:
            check("⑤ 거절은 FlowError (사유 포함)", "없는 번호" in str(e), str(e))
        FF.cmd_status(tmp, "R7-2", "applied", branch="fix/R7", commit="abc", api=api)
        check("⑥ 상태 기록 경로", calls[-1][1] == "/fixes/R7-2/status"
              and calls[-1][2]["branch"] == "fix/R7", str(calls[-1]))
        for bad in (("R7-2", "done"), ("X1", "applied"), ("R7-2", "failed")):
            try:
                FF.cmd_status(tmp, *bad, api=api)
                check(f"⑥ 거절: {bad}", False)
            except FF.FlowError:
                check(f"⑥ 거절: {bad}", True)
        log = (tmp / ".ax/fixes/R7/flow.log").read_text(encoding="utf-8")
        check("⑥ 기록도 flow.log 에 남는다", "상태 R7-2 → applied · 기록됨" in log, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── ⑦ 배달 ──────────────────────────────────────────────────────────────────

def test_delivery():
    from master.client import bundle
    check("⑦ 요청자 스킬에 ax-fix", "ax-fix" in bundle.skills_for("requester"))
    check("⑦ 워커에는 가지 않는다", "ax-fix" not in bundle.skills_for("worker"))
    text = bundle.skill_text("ax-fix")
    check("⑦ SKILL.md 머리말", text.startswith("---\nname: ax-fix\n"), text[:80])
    check("⑦ SKILL.md 가 ax-review 와의 경계를 적는다", "ax-review" in text)
    check("⑦ 요청자 payload 에 fix_flow", "clientside/fix_flow.py" in bundle.payloads_for("requester"))
    check("⑦ 워커 payload 에는 없다", "clientside/fix_flow.py" not in bundle.payloads_for("worker"))
    tree = ast.parse(Path(FF.__file__).read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0] if node.level == 0 else ".")
    allowed = {"__future__", "argparse", "json", "re", "subprocess", "sys", "datetime",
               "pathlib", "importlib"}
    check("⑦ [중요] fix_flow 는 stdlib 만 (스크립트 모드 · 클라에 pip 없음)",
          mods <= allowed, str(mods - allowed))


if __name__ == "__main__":
    for fn in (test_scope, test_public_prefix_and_policy, test_public_page_has_no_body,
               test_client_tools, test_flow_check_real_git,
               test_flow_worktree_leaves_checkout_alone, test_flow_fetch_and_status_with_fake_api,
               test_delivery):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
