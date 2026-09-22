"""리뷰·플랜 수정 워크플로우의 표면 (`#629`·`#630`) — 토큰 · 공개 화면 · 클라 도구 · `.33` 흐름.

검증하는 것:

    ① 스코프 — 요청자만 `/fixes` 를 연다 (토큰 없음 401 · 워커 403) · `/api/v1` 밖이다
    ② 8103 — `/reviews` 는 공개 접두에 있고 `/fixes` 는 없다 · 태그 정책이 선언돼 있다
    ③ [중요] 공개 목록에 본문·지적 설명·소스 경로가 없다 · 작성자 이름은 이스케이프된다
       · 상세(`/reviews/R12`)는 **LAN 공개**(사용자 결정 2026-09-16)라 본문이 실린다 —
         [중요] 대신 본문의 태그는 전부 이스케이프한다 · 번호·요청 문구를 복사할 수 있다
    ④ 클라 도구 — 경로·인코딩·상태 검증 · 결정 도구 금지어에 걸리지 않는다
    ⑤ fix_flow 대조 — **실제 git 저장소**에서 단서 넷(unchanged·line_present·line_missing·gone)
       · [중요] fetch 가 실패하면 낡은 main 으로 대조하지 않고 멈춘다
    ⑥ fix_flow prepare — [중요] **깨끗하면 사람 체크아웃 그 자리**(`#660`) · 더러우면 **거절**
       · `--mode worktree` 는 사람의 미커밋 작업을 그대로 둔다 · 재사용은 리셋하지 않는다
       · `release` 가 브랜치 점유를 풀어 사람이 자기 폴더에서 연다
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
from master.test_fix_index import SECRET_DESC, SECRET_PATH, make_root, review_text   # noqa: E402
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


def test_nav_links_everywhere():
    """② [중요] 입구가 `/cluster` 한 곳뿐이라 사용자가 못 찾았다 (2026-09-16) — 모든 화면에서 간다."""
    from master.webui import onboarding, routes
    check("② 첫 화면(/) 메뉴에 리뷰·플랜", b'href="/reviews"' in routes.context_server_html())
    for name in ("index.html", "domain.html", "task.html"):
        body = routes.inject_cluster_link(routes.page(name))
        check(f"② 온톨로지 {name} 메뉴에 리뷰·플랜", b'href="/reviews"' in body)
    check("② 온보딩 메뉴에 리뷰·플랜", b'href="/reviews"' in onboarding.page())


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


def test_detail_page_and_copy():
    """③ 게시판 상세 — 번호를 누르면 뜨고, 번호·요청 문구를 복사해 .33 에 붙여넣는다 (사용자 2026-09-16)."""
    from master.webui import fixes_page
    root = make_root()
    FX.set_status(root, "R1-1", "applied", branch="fix/R1", commit="c" * 40, by="ax-fix", note="널 가드")
    reg = FakeRegistry({"NS": root}, "NS")

    st, lst = fixes_page.render("", registry=reg)
    check("③ 목록 번호가 상세로 링크된다", 'href="/reviews/R1?project=NS"' in lst, lst[-2000:])
    check("③ 목록 [복사]는 요청 문구", 'data-copy="R1 검토해볼까?"' in lst)
    check("③ [중요] http(비보안 문맥)에서도 복사되게 execCommand 폴백", "execCommand('copy')" in lst)
    check("③ 목록에는 여전히 지적 설명이 없다", SECRET_DESC not in lst)

    st, det = fixes_page.render_detail("r1", "NS", registry=reg)
    check("③ 상세 200 (번호 대소문자 무관)", st == 200, det[:300])
    check("③ 상세 복사 상자 — 요청 문구·번호",
          'data-copy="R1 검토해볼까?"' in det and 'data-copy="R1"' in det)
    check("③ 항목 번호도 복사", 'data-copy="R1-3"' in det)
    check("③ 상세에는 지적·경로·권장 수정이 실린다 (LAN 공개 결정)",
          SECRET_DESC in det and SECRET_PATH in det and "IsValid 추가" in det)
    check("③ 결정이 누구·브랜치·커밋·메모와 함께",
          "적용됨" in det and "fix/R1" in det and "c" * 12 in det and "널 가드" in det and "ax-fix" in det)
    check("③ 원문이 렌더링된다 (제목·표)", "<h4>Source/NS/AI</h4>" in det and "<h3>" in det
          and "원문 전체" in det)
    check("③ 목록으로 돌아가는 링크", 'href="/reviews?project=NS"' in det)

    evil = root / "reviews" / "Simkung" / "2026-09-14_0000_eeeeeeee.md"
    evil.write_text(review_text("e" * 40, "Simkung").replace(SECRET_DESC, "<img src=x onerror=alert(1)>")
                    + "\n# <script>alert(1)</script>\n본문 `<b>코드</b>`\n", encoding="utf-8")
    FX.sweep(root)
    serial = FX.serial_for_commit(root, "e" * 40)
    st, det = fixes_page.render_detail(serial, "NS", registry=reg)
    check("③ [중요] 본문·항목의 태그를 이스케이프한다 (공개 상세)",
          st == 200 and "<script>alert(1)</script>" not in det and "<img src=x" not in det
          and "&lt;script&gt;" in det and "&lt;img src=x" in det, det[-800:])
    check("③ [중요] 인라인 코드 안의 태그도 이스케이프", "<code>&lt;b&gt;코드&lt;/b&gt;</code>" in det)

    st, det = fixes_page.render_detail("R99", "NS", registry=reg)
    check("③ 없는 번호는 404", st == 404 and "없는 번호" in det, det[-300:])
    st, det = fixes_page.render_detail("../etc", "NS", registry=reg)
    check("③ 형식이 아니면 404", st == 404)
    st, det = fixes_page.render_detail("P1", "NS", registry=reg)
    check("③ 플랜 상세 — 대상 파일·플랜 상태·복사",
          st == 200 and SECRET_PATH in det and "pending" in det and 'data-copy="P1 검토해볼까?"' in det,
          det[-800:])

    def boom(r, s):
        raise OSError(f"{root}/fixes/index.json 권한 없음")
    st, det = fixes_page.render_detail("R1", "NS", registry=reg, get_doc=boom)
    check("③ [중요] 상세 실패도 예외 문자열(절대 경로)을 싣지 않는다",
          st == 500 and str(root) not in det, det[-300:])

    import types
    from master.projects import config as PC
    from master.webui.app import WebUI
    orig = PC.Registry.load
    PC.Registry.load = classmethod(lambda cls, root_=None: reg)
    try:
        app = WebUI(lambda: types.SimpleNamespace(root=root, name="NS"))
        out = []

        async def rcv():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def snd(ev):
            out.append(ev)
        asyncio.run(app({"type": "http", "method": "GET", "path": "/reviews/R1",
                         "query_string": b"project=NS", "headers": []}, rcv, snd))
        text = b"".join(e.get("body", b"") for e in out[1:]).decode("utf-8")
        check("③ 실제 라우트 /reviews/R1 → 상세", out[0]["status"] == 200 and "R1 — 자동 리뷰" in text,
              str(out[0].get("status")))
    finally:
        PC.Registry.load = orig
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
    # 🔴 [중요] **요청자 체크아웃과 같은 조건으로 만든다** — 온보딩이 `.ax/` 를 여기에 넣는다.
    #    이 한 줄이 없어서 `#662`(in-place 커밋이 **항상** 실패)가 테스트를 통과했다.
    (work / ".git" / "info" / "exclude").write_text("/.ax/\n", encoding="utf-8")
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


def test_flow_prepare_inplace_is_the_default():
    """⑥ [중요] 깨끗한 체크아웃이면 **그 자리에** 붙인다 (`#660`, 사용자 결정 2026-09-22).

    종전 기본(옆 worktree)은 ⑴ 소스트리에 안 보이고 ⑵ git 이 같은 브랜치를 두 폴더에 못 붙여
    사람이 열 수도 없고 ⑶ Intermediate/Binaries 가 없어 증분 빌드도 못 하는 자리였다.
    """
    tmp = Path(tempfile.mkdtemp(prefix="fixinplace-"))
    try:
        work, _ = _repo(tmp)
        got = FF.cmd_prepare(work, "R1")
        check("⑥ [중요] 기본은 사람 체크아웃 그 자리",
              got["mode"] == "inplace" and Path(got["path"]) == work, str(got))
        check("⑥ 그 자리의 브랜치가 fix/R1",
              _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "fix/R1")
        check("⑥ 돌아갈 곳을 말한다", got["previous_branch"] == "main", str(got))
        check("⑥ 옆에 worktree 를 만들지 않는다", not (tmp / "ax-fix-R1").exists())
        again = FF.cmd_prepare(work, "R1")
        check("⑥ 이미 그 브랜치면 재사용", again["reused"] is True, str(again))

        (work / "Source" / "A.cpp").write_text("void A() {\n  auto* P = Get();\n"
                                               "  if (P) P->Run();\n}\n", encoding="utf-8")
        d = FF.cmd_diff(work, "R1")
        check("⑥ 그 자리에서 diff 가 돈다", d["files"] == ["Source/A.cpp"], str(d))
        got = FF.cmd_commit(work, "R1", ["R1-1"], "그 자리 커밋")
        check("⑥ 그 자리에서 커밋된다", got["branch"] == "fix/R1" and got["commit"], str(got))

        rel = FF.cmd_release(work, "R1", to="main")
        check("⑥ release --to 가 체크아웃을 되돌린다",
              rel["branch"] == "main" and _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main",
              str(rel))
        check("⑥ [중요] 되돌려도 수정은 fix/R1 에 남는다",
              "R1-1" in _git(work, "log", "-1", "--format=%s", "fix/R1"))

        # 옆 worktree 가 그 브랜치를 물고 있으면 — git 제약을 **사유로** 말한다
        FF.cmd_prepare(work, "R2", mode="worktree")
        try:
            FF.cmd_prepare(work, "R2", mode="inplace")
            check("⑥ [중요] worktree 점유 중이면 거절하고 release 를 가리킨다", False)
        except FF.FlowError as e:
            check("⑥ [중요] worktree 점유 중이면 거절하고 release 를 가리킨다",
                  "점유" in str(e) and "release" in str(e), str(e))
        rel = FF.cmd_release(work, "R2")
        check("⑥ release 가 점유를 푼다",
              rel["removed"] and not (tmp / "ax-fix-R2").exists(), str(rel))
        got = FF.cmd_prepare(work, "R2", mode="inplace")
        check("⑥ 풀린 뒤에는 그 자리에서 열린다", got["mode"] == "inplace", str(got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flow_worktree_leaves_checkout_alone():
    """⑥ 사람이 고치던 중이면 — auto 는 **거절**하고, 명시한 worktree 만 옆으로 간다."""
    tmp = Path(tempfile.mkdtemp(prefix="fixwt-"))
    try:
        work, _ = _repo(tmp)
        (work / "Source" / "E.cpp").write_text("// 사람이 고치던 중\n", encoding="utf-8")
        head = _git(work, "rev-parse", "HEAD")
        try:
            FF.cmd_prepare(work, "R1")
            check("⑥ [중요] 더러운 체크아웃에는 붙지 않는다 — 몰래 옆으로 도망가지도 않는다", False)
        except FF.FlowError as e:
            check("⑥ [중요] 더러운 체크아웃에는 붙지 않는다 — 몰래 옆으로 도망가지도 않는다",
                  "worktree" in str(e) and "E.cpp" in str(e), str(e))
        check("⑥ 거절은 브랜치를 안 바꾼다",
              _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main")
        got = FF.cmd_prepare(work, "R1", mode="worktree")
        wt = Path(got["path"])
        check("⑥ 체크아웃 옆에 worktree", wt == (tmp / "ax-fix-R1").resolve() and wt.is_dir(), str(got))
        check("⑥ fix/R1 브랜치", _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "fix/R1")
        check("⑥ [중요] 사람 체크아웃의 브랜치·HEAD 그대로",
              _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main"
              and _git(work, "rev-parse", "HEAD") == head)
        check("⑥ [중요] 사람의 미커밋 변경 그대로",
              (work / "Source" / "E.cpp").read_text(encoding="utf-8") == "// 사람이 고치던 중\n")
        (wt / "Source" / "A.cpp").write_text("// 고침\n", encoding="utf-8")
        again = FF.cmd_prepare(work, "R1", mode="worktree")
        check("⑥ 두 번째는 재사용", again["reused"] is True, str(again))
        check("⑥ [중요] 재사용은 리셋하지 않는다",
              (wt / "Source" / "A.cpp").read_text(encoding="utf-8") == "// 고침\n")
        try:
            FF.cmd_release(work, "R1")
            check("⑥ [중요] 미커밋 worktree 는 지우지 않는다", False)
        except FF.FlowError as e:
            check("⑥ [중요] 미커밋 worktree 는 지우지 않는다", "커밋" in str(e), str(e))
        (tmp / "ax-fix-R2").mkdir()
        try:
            FF.cmd_prepare(work, "R2", mode="worktree")
            check("⑥ worktree 아닌 디렉토리는 덮지 않는다", False)
        except FF.FlowError:
            check("⑥ worktree 아닌 디렉토리는 덮지 않는다", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flow_diff_and_commit():
    """⑤ 확인·커밋 — 결과를 로그와 파일로 남기고, fix 브랜치에만 커밋한다 (2026-09-16 로그 점검)."""
    tmp = Path(tempfile.mkdtemp(prefix="fixcommit-"))
    try:
        work, _ = _repo(tmp)
        head = _git(work, "rev-parse", "HEAD")
        try:
            FF.cmd_diff(work, "R1")
            check("⑤ worktree 없으면 diff 거절", False)
        except FF.FlowError:
            check("⑤ worktree 없으면 diff 거절", True)
        wt = Path(FF.cmd_prepare(work, "R1", mode="worktree")["path"])
        try:
            FF.cmd_commit(work, "R1", ["R1-1"], "x")
            check("⑤ 변경이 없으면 커밋 거절", False)
        except FF.FlowError:
            check("⑤ 변경이 없으면 커밋 거절", True)
        (wt / "Source" / "A.cpp").write_text("void A() {\n  auto* P = Get();\n  if (P) P->Run();\n}\n",
                                             encoding="utf-8")
        (wt / "Source" / "New.cpp").write_text("int N = 0;\n", encoding="utf-8")
        d = FF.cmd_diff(work, "R1")
        check("⑤ diff 가 수정·새 파일을 모두 본다",
              set(d["files"]) == {"Source/A.cpp", "Source/New.cpp"}, str(d))
        patch = (work / ".ax/fixes/R1/diff.patch").read_text(encoding="utf-8")
        check("⑤ diff.patch 에 실제 변경", "if (P) P->Run();" in patch, patch[:300])
        check("⑤ diff.patch 에 CRLF 가 없다",
              b"\r\n" not in (work / ".ax/fixes/R1/diff.patch").read_bytes())
        # [중요] 바로 위 한 줄은 **리눅스에서 늘 통과한다** — 번역은 윈도우에서만 일어난다.
        #        그래서 원천을 막는다: 텍스트 모드로 되돌리면 `#660` 이 그대로 재발한다.
        ff_src = Path(FF.__file__).read_text(encoding="utf-8")
        check("⑤ [중요] diff.patch 는 바이트로 쓴다 (#660 윈도우 CRLF 재발 방지)",
              'out.write_bytes(patch.encode("utf-8"))' in ff_src
              and "out.write_text" not in ff_src)
        for bad in ((["R2-1"], "다른 번호"), (["R1"], "행 번호")):
            try:
                FF.cmd_commit(work, "R1", bad[0], "x")
                check(f"⑤ 커밋 거절: {bad[1]}", False)
            except FF.FlowError as e:
                check(f"⑤ 커밋 거절: {bad[1]}", True)
        got = FF.cmd_commit(work, "r1", ["R1-1", "R1-1", "r1-3"], "널 가드\n둘째 줄")
        check("⑤ 항목은 중복 없이 정규화", got["items"] == ["R1-1", "R1-3"], str(got))
        check("⑤ fix/R1 에 커밋됐다", _git(wt, "rev-parse", "HEAD") == got["commit"]
              and _git(wt, "log", "-1", "--format=%s") == "fix(R1-1,R1-3): 널 가드",
              _git(wt, "log", "-1", "--format=%s"))
        check("⑤ [중요] 사람 체크아웃의 main 은 그대로", _git(work, "rev-parse", "HEAD") == head)
        log = (work / ".ax/fixes/R1/flow.log").read_text(encoding="utf-8")
        check("⑤ [중요] diff 요지가 flow.log 에 남는다", "diff — 파일 2개" in log, log)
        check("⑤ [중요] 커밋 해시·항목이 flow.log 에 남는다",
              f"커밋 {got['commit'][:12]} on fix/R1 · 항목 R1-1,R1-3" in log, log)
        _git(wt, "checkout", "-q", "-b", "other")
        (wt / "Source" / "E.cpp").write_text("int E = 9;\n", encoding="utf-8")
        try:
            FF.cmd_commit(work, "R1", ["R1-4"], "x")
            check("⑤ fix/R1 이 아니면 커밋 거절", False)
        except FF.FlowError as e:
            check("⑤ fix/R1 이 아니면 커밋 거절", "fix/R1" in str(e), str(e))
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
    for fn in (test_scope, test_public_prefix_and_policy, test_nav_links_everywhere,
               test_public_page_has_no_body, test_detail_page_and_copy,
               test_client_tools, test_flow_check_real_git,
               test_flow_prepare_inplace_is_the_default,
               test_flow_worktree_leaves_checkout_alone, test_flow_diff_and_commit,
               test_flow_fetch_and_status_with_fake_api,
               test_delivery):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
