"""요청 태그 (`#257`·`#258`) — **모든 라우트가 정책을 선언했는가**.

[중요] 이 파일의 첫 테스트가 이 작업의 핵심이다: **실물 라우트를 열거해 선언 표와 맞춘다.**
선언 없이 엔드포인트를 추가하면 여기서 깨진다 — `#243` 이 시소러스 둘만 배선하고
`signals`·`history`·`claim` 을 남긴 것이 정확히 그 사고였다.

`.venv/bin/python master/test_tagging.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue import tagging as T                          # noqa: E402
from master.task_queue import models as M                           # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _routes() -> set:
    """실물 라우트 `{"POST /api/v1/..."}` — 소스의 데코레이터에서 읽는다.

    [주의] 앱을 띄우지 않는다(토큰·상태 루트가 필요하다). 데코레이터는 **선언**이므로
    소스에서 읽는 편이 이 테스트의 목적(선언 누락 탐지)에 맞다.
    """
    import re
    src = (Path(__file__).resolve().parent / "task_queue" / "server.py").read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r'@app\.(get|post|patch|put|delete)\("([^"]+)"\)', src):
        out.add(f"{m.group(1).upper()} {m.group(2)}")
    return out


def test_server_actually_compiles() -> None:
    """[중요] **소스를 텍스트로 읽는 테스트는 구문 오류를 못 잡는다** (실측 2026-08-22).

    이 파일의 다른 테스트들이 전부 통과하는 동안 `server.py` 는 `SyntaxError` 로
    기동조차 못 하고 있었다 — 다중행 `from .models import (...)` **가운데**에 import 를
    끼워 넣었기 때문이다. 텍스트 검사는 그것을 볼 수 없다. 그래서 **파싱한다.**
    [주의] `ActiveState=active` 도 속였다 — `Restart=always` 가 재기동을 반복하고 있었다.
    """
    import ast
    src = (Path(__file__).resolve().parent / "task_queue" / "server.py")
    try:
        ast.parse(src.read_text(encoding="utf-8"))
        check("[중요] server.py 가 파싱된다", True)
    except SyntaxError as e:
        check("[중요] server.py 가 파싱된다", False, f"{e.lineno}행: {e.msg}")
    for mod in ("tagging.py", "models.py", "logic_claim.py"):
        f = src.parent / mod
        try:
            ast.parse(f.read_text(encoding="utf-8"))
            check(f"{mod} 가 파싱된다", True)
        except SyntaxError as e:
            check(f"{mod} 가 파싱된다", False, f"{e.lineno}행: {e.msg}")


def test_every_route_declared() -> None:
    """[중요] **선언 없는 라우트가 있으면 실패다** — 이것이 이 파일의 존재 이유다."""
    live, declared = _routes(), set(T.POLICY)
    check("라우트를 읽었다", len(live) > 20, f"{len(live)}개")
    missing = sorted(live - declared)
    check("[중요] 모든 라우트에 정책이 선언돼 있다", not missing,
          f"선언 누락 {len(missing)}: {missing[:5]}")
    stale = sorted(declared - live)
    check("[주의] 없어진 라우트가 표에 남아 있지 않다", not stale, f"유령 {stale[:5]}")
    check("정책 값은 넷 중 하나다",
          all(v in (T.OPEN, T.TAG, T.MOUNT, T.STAMP) for v in T.POLICY.values()))


def test_undeclared_is_an_error() -> None:
    """조용히 통과시키지 않는다 — 모르는 라우트는 **에러**다."""
    try:
        T.policy_for("POST", "/api/v1/made-up")
        check("[중요] 미선언 라우트를 거부한다", False, "통과해버렸다")
    except KeyError as e:
        check("미선언 라우트를 거부한다", "선언되지" in str(e), str(e)[:60])
        check("고칠 자리를 알려준다", "tagging.py" in str(e))


def test_models_carry_the_tag() -> None:
    """[중요] `OPEN` 이 아닌 표면의 요청 모델은 **`project` 를 받아야** 한다."""
    need = {n for n in dir(M)
            if n.endswith("Req") and hasattr(getattr(M, n), "model_fields")}
    without = sorted(n for n in need if "project" not in getattr(M, n).model_fields)
    # OPEN 표면 둘만 예외다 (관리자 리셋 · 워커 지시)
    check("[중요] 태그 없는 모델은 OPEN 표면 둘뿐이다",
          without == ["AdminResetReq", "DirectiveReq"], str(without))
    check("기본값은 빈 문자열이다 (하위 호환 — 안 보내면 마운트로 해석)",
          M.ClaimReq(worker_id="w").project == "")


def test_reject_shape() -> None:
    """[중요] **거부 형태는 200 + `ok:false` + 사유** (§12.5-c). 409·500 이 아니다."""
    r = T.reject("사유", project="NS", mounted="ModularStage")
    check("ok:false", r["ok"] is False)
    check("사유가 있다", r["reason"] == "사유")
    check("어느 프로젝트를 물었는지 담는다", r["project"] == "NS" and r["mounted"] == "ModularStage")
    check("status 로 기계가 가른다", r["status"] == "not_mounted")


def test_stamp_check_does_not_use_mount() -> None:
    """[중요] `STAMP` 는 **스탬프와 대조**한다 — 마운트와 비교하면 `#210` 을 깨뜨린다."""
    check("어긋나면 사유", "다르다" in T.check_stamp("NS", "ModularStage"))
    check("같으면 통과", T.check_stamp("NS", "NS") == "")
    check("[중요] 태그가 없으면 통과 (하위 호환)", T.check_stamp("", "ModularStage") == "")
    check("[중요] 스탬프 없는 옛 work 는 통과 (`_paths_for` 와 같은 규칙)",
          T.check_stamp("NS", "") == "")
    check("사유가 #210 을 인용한다", "#210" in T.check_stamp("NS", "ModularStage"))


def test_twin_writers_are_gated() -> None:
    """[중요] **트윈에 쓰는 표면은 OPEN·TAG 일 수 없다** — 거기가 `#243` 의 구멍이었다."""
    twin = ("POST /api/v1/history", "POST /api/v1/signals", "POST /api/v1/usage",
            "POST /api/v1/thesaurus/alias", "POST /api/v1/thesaurus/not-a-class",
            "PATCH /api/v1/works/{work_id}")
    for k in twin:
        check(f"{k} 는 대조·거부 표면이다", T.POLICY[k] in (T.MOUNT, T.STAMP), T.POLICY[k])
    check("[중요] 등재는 MOUNT 다 (비마운트 work 를 만들 수 없다)",
          T.POLICY["POST /api/v1/works"] == T.MOUNT)
    check("[중요] 파견은 MOUNT 다 (#248 — 남의 태스크를 집지 않는다)",
          T.POLICY["POST /api/v1/tasks/claim"] == T.MOUNT
          and T.POLICY["POST /api/v1/workers/{worker_id}/poll"] == T.MOUNT)


def test_gates_are_actually_wired() -> None:
    """[중요] 표만 있고 배선이 없으면 선언은 거짓이다 — **서버 소스에서 확인한다.**

    [주의] 이번 세션의 실측이 정확히 이 부류였다: `#243` 이 배선됐다고 서술했는데 실제로는
    500 이 나고 있었고, 막은 것은 우리 코드가 아니라 systemd 샌드박스였다.
    """
    src = (Path(__file__).resolve().parent / "task_queue" / "server.py").read_text(encoding="utf-8")
    for fn in ("register_work_ep", "claim_ep", "worker_poll_ep"):
        i = src.index(f"def {fn}(")
        body = src[i:i + 1200]
        check(f"{fn} 에 마운트 관문이 있다", "_mount_gate(" in body, body[:80])
    for fn, gate in (("history_ep", "_stamp_gate("), ("writer_signal_ep", "_stamp_gate("),
                     ("usage_ep", "_stamp_gate("), ("patch_work_ep", "_stamp_gate(")):
        i = src.index(f"def {fn}(")
        check(f"{fn} 에 스탬프 대조가 있다", gate in src[i:i + 1600])
    for fn in ("history_ep", "writer_signal_ep", "usage_ep"):
        i = src.index(f"def {fn}(")
        check(f"[중요] {fn} 는 work 가 없으면 마운트를 강제한다 (태그만으로 남의 트윈에 쓰지 않는다)",
              "_mount_gate(req.project, require=True)" in src[i:i + 1800])
    check("[중요] 거부에 HTTPException 을 쓰지 않는다 (거절≠장애)",
          "_mount_gate" in src and "return bad" in src)


def test_claim_filters_by_project() -> None:
    """[중요] claim 이 **후보를 실제로 거른다** — 그리고 옛 work 는 계속 후보다."""
    from master.task_queue import logic_claim as C
    import inspect
    src = inspect.getsource(C.claim_task)
    check("project 인자를 받는다", "project: str" in inspect.signature(C.claim_task).__str__()
          or "project" in inspect.signature(C.claim_task).parameters)
    check("스탬프가 있고 다를 때만 건너뛴다", "if wp and wp != want_project" in src, "필터가 없다")
    check("[중요] 세고 **읽는다** (저장하고 안 읽는 값을 만들지 않는다)",
          "skipped_project 건" not in src and "skipped_project}건" in src)

    class _Idx:
        works = {"w1": {"project": "ModularStage"}, "w2": {"project": "NS"}, "w3": {}}
    check("work 의 스탬프를 읽는다",
          C._work_project(_Idx(), {"work_id": "w2"}) == "NS")
    check("[중요] 스탬프 없는 옛 work 는 빈 값 → 필터를 통과한다",
          C._work_project(_Idx(), {"work_id": "w3"}) == "")
    check("없는 work 도 빈 값 (죽지 않는다)", C._work_project(_Idx(), {"work_id": "zz"}) == "")


def test_untagged_is_rejected_on_write_surfaces() -> None:
    """[중요] **태그 없음 = 마운트 다름** (사용자 2026-08-22).

    > *"태그 없으면 동일하게 마운트 다름으로 처리해야지 그러다가 엉뚱한 데이터로
    > 오염되는거잖아"*

    사용자가 든 사유(오염)에서 규칙이 나온다: **오염 경로는 태그가 없어 마운트로
    「가정」하는 자리**다. 그래서 쓰는 표면은 필수, 읽는 표면은 선택이다.
    """
    for k in T.REQUIRE_TAG:
        m, path = k.split(" ", 1)
        check(f"{k} 는 태그가 필수다", T.requires_tag(m, path), k)
        check(f"{k} 는 MOUNT 정책이다", T.POLICY[k] == T.MOUNT, T.POLICY[k])
    # 읽기는 필수가 아니다 — 오염이 없다
    for m, path in (("GET", "/api/v1/works"), ("GET", "/api/v1/tasks"),
                    ("GET", "/api/v1/works/{work_id}")):
        check(f"{m} {path} 는 필수가 아니다", not T.requires_tag(m, path))
    # [중요] STAMP 쓰기는 필수가 아니다 — 스탬프가 판정한다(`#210`)
    for k in ("PATCH /api/v1/works/{work_id}", "POST /api/v1/tasks/{task_id}/submit"):
        check(f"{k} 는 필수가 아니다 (스탬프가 판정한다)", k not in T.REQUIRE_TAG)

    r = T.reject_untagged("ModularStage")
    check("거절 형태는 200 + ok:false", r["ok"] is False)
    check("[중요] 사유가 마운트 불일치와 구분된다", r["status"] == "no_project_tag")
    check("지금 마운트를 알려준다", "ModularStage" in r["reason"])
    check("고칠 자리를 말한다 (.ax/config.json)", "config.json" in r["reason"])


def test_path_normalization() -> None:
    """[중요] 실제 경로를 표의 템플릿으로 맞춘다 — **정확 일치를 먼저** 본다."""
    cases = (
        ("/api/v1/tasks/claim", "/api/v1/tasks/claim"),         # 실측: 이게 {task_id} 로 삼켜졌다
        ("/api/v1/tasks/abc/submit", "/api/v1/tasks/{task_id}/submit"),
        ("/api/v1/works/w1", "/api/v1/works/{work_id}"),
        ("/api/v1/works?project=NS", "/api/v1/works"),          # 쿼리를 뗀다
        ("/api/v1/workers/h1/poll", "/api/v1/workers/{worker_id}/poll"),
        ("/api/v1/works/w1/summary", "/api/v1/works/{work_id}/summary"),
    )
    for raw, want in cases:
        got = T.normalize_path(raw)
        check(f"{raw} → {want}", got == want, got)
    check("[중요] claim 이 필수 표면으로 잡힌다",
          T.requires_tag("POST", "/api/v1/tasks/claim"))
    check("submit 은 필수가 아니다", not T.requires_tag("POST", "/api/v1/tasks/x/submit"))


def test_senders_are_wired() -> None:
    """[중요] **보내는 쪽이 없으면 조임은 장애다** — 발신자를 소스로 확인한다.

    [주의] 마스터 쪽은 **필수 표면에만** 붙여야 한다 — `STAMP` 표면에 마운트를 붙이면
    미종결 work 를 둔 채 활성을 바꿨을 때 `project_mismatch` 가 나고, 그것이 `#210` 이
    지키려던 흐름이다.
    """
    root = Path(__file__).resolve().parent.parent
    runner = (root / "master" / "work" / "runner.py").read_text(encoding="utf-8")
    check("runner 가 관문에서 태그를 붙인다", "_tag(method, path, payload)" in runner)
    check("[중요] runner 는 필수 표면만 붙인다", "requires_tag(method, path)" in runner)
    check("붙이는 값은 마운트다", "Registry.load().active" in runner)

    # [중요] **claimer 발신자 검사 절이 여기 있었다** — `#320`(2026-08-27) 으로 상주가 철거되며
    #    같이 걷혔다. 그 절이 지키던 것(claim 이 `_call` 에서 태그를 붙인다 · 200+ok:false 를
    #    태스크로 착각하지 않는다 · 거절 사유를 파일 로그로 한 번만 찍는다)은 **push 파견에서는
    #    `runner.py` 가 같은 자리**다 — 바로 위 세 검사가 그것이다.
    #    [주의] 상주를 되살린다면 이 검사들도 같이 되살릴 것(`#320` 노트의 되살릴 조건).

    cmcp = (root / "client" / "runtime" / "client_mcp.py").read_text(encoding="utf-8")
    check("클라가 관문에서 붙인다", 'payload = {**payload, "project": project}' in cmcp)
    check("GET 은 쿼리로 붙인다", '"project=" not in path' in cmcp)

    # [주의] `buildjob` 발신자 검사 절이 여기 있었다 — `#861`(2026-10-31) 으로 `buildjob` 이
    #    데몬과 함께 삭제됐다(빌드는 서버가 SSH 로 건다, `plan_build`). 되살림은
    #    `test_no_worker_daemon.py` 가 막는다. 남은 등록 발신자는 아래 `register.py` 다.
    check("[중요] buildjob 발신자는 삭제됐다 (#861)",
          not (root / "master" / "work" / "buildjob.py").exists())

    reg = (root / "master" / "work" / "register.py").read_text(encoding="utf-8")
    check("태스크 등록도 스탬프를 싣는다", reg.count('"project": paths.name') >= 2,
          str(reg.count('"project": paths.name')))


def _live_queue(tmp: Path):
    """[중요] 실물 앱을 **프로세스 안에서** 띄운다 — `uvicorn.run` 만 가로채 감싼 앱(인증 미들웨어 포함)을 받는다.

    토큰은 가짜 값이고 큐 루트·트윈 루트는 임시 디렉토리다(실 큐 `~/ax-state`·실 트윈을 만지지 않는다).
    돌려주는 것: `(TestClient, 전권, requester, worker 토큰)`.
    """
    import os
    import types
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from master.task_queue import server as S
    master_t, req_t, wrk_t = "m" * 40, "r" * 40, "w" * 40
    got = {}
    fake_uv = types.ModuleType("uvicorn")
    fake_uv.run = lambda app, **kw: got.setdefault("app", app)
    (tmp / "queue").mkdir(parents=True, exist_ok=True)
    with patch.dict(sys.modules, {"uvicorn": fake_uv}), \
            patch.object(S, "load_token", return_value=master_t), \
            patch("master.auth.load_role_token",
                  side_effect=lambda role: {"requester": req_t, "worker": wrk_t}.get(role)):
        S._run_http_server(tmp / "queue", 0, "127.0.0.1")
    return TestClient(got["app"]), master_t, req_t, wrk_t


def test_usage_route_live() -> None:
    """[중요] `POST /api/v1/usage` (`#763`) — 실물 라우트가 임시 트윈에 한 줄을 쓰고, 관문이 거절한다."""
    import json
    import os
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="test_usage_route_"))
    old_root = os.environ.get("AX_PROJECTS_ROOT")
    try:
        proots = tmp / "projects"
        for n in ("AXCluster", "NS"):
            (proots / n).mkdir(parents=True)
        (proots / "projects.yaml").write_text(
            "version: 1\nactive: AXCluster\nprojects:\n- AXCluster\n- NS\n", encoding="utf-8")
        os.environ["AX_PROJECTS_ROOT"] = str(proots)
        c, _m, req_t, wrk_t = _live_queue(tmp)
        H = {"Authorization": f"Bearer {req_t}"}
        log = proots / "AXCluster" / "usage_log.jsonl"
        body = {"project": "AXCluster", "source": "ax-gemini", "lane": "agy", "worker": "DESKTOP-FU2GNGL",
                "rc": 0, "seconds": 12.34, "model": "gemini-3.6-flash-high", "note": "n",
                "usage": {"input_tokens": 120, "output_tokens": 45, "cache_read_input_tokens": 7}}
        r = c.post("/api/v1/usage", json=body, headers=H)
        j = r.json()
        check("[중요] requester 토큰 200 · ok", r.status_code == 200 and j.get("ok"), f"{r.status_code} {j}")
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
        check("[중요] 마운트 트윈 usage_log 에 한 줄", len(rows) == 1, str(rows))
        if rows:
            w = rows[0]
            check("  레코드 — source·lane·worker·rc·model·note",
                  (w["source"], w["lane"], w["worker"], w["rc"], w["model"], w.get("note"))
                  == ("ax-gemini", "agy", "DESKTOP-FU2GNGL", 0, "gemini-3.6-flash-high", "n"), str(w))
            check("  토큰 측정 · 비용 미상(0 아님) · 초 반올림",
                  w["measured"] and w["input_tokens"] == 120 and w["output_tokens"] == 45
                  and w["cache_read"] == 7 and w["cost_known"] is False and w["seconds"] == 12.3, str(w))
            check("  응답 record 가 쓴 줄과 같다", j.get("record") == w, str(j.get("record")))
        n0 = len(rows)
        for label, b, status in (
                ("태그 없음 → no_project_tag", {k: v for k, v in body.items() if k != "project"}, "no_project_tag"),
                ("비마운트 태그 → not_mounted", {**body, "project": "NS"}, "not_mounted")):
            r = c.post("/api/v1/usage", json=b, headers=H)
            check(f"[중요] {label} (200 + ok:false)", r.status_code == 200 and r.json().get("status") == status,
                  f"{r.status_code} {r.text[:200]}")
        # STAMP — work 스탬프와 태그가 다르면 project_mismatch
        w = c.post("/api/v1/works", json={"title": "u", "target_repo": "R", "project": "AXCluster"},
                   headers={"Authorization": f"Bearer {_m}"}).json()
        r = c.post("/api/v1/usage", json={**body, "project": "NS", "work_id": w.get("work_id", "")}, headers=H)
        check("[중요] work 스탬프와 다른 태그 → project_mismatch", r.json().get("status") == "project_mismatch",
              r.text[:200])
        for label, b in (("source 비었음", {**body, "source": ""}),
                         ("모르는 키", {**body, "cost": 1}),
                         ("토큰이 문자열", {**body, "usage": {"input_tokens": "120"}}),
                         ("음수 토큰", {**body, "usage": {"input_tokens": -1}})):
            r = c.post("/api/v1/usage", json=b, headers=H)
            check(f"모양 검사 — {label} → 422", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
        r = c.post("/api/v1/usage", json=body, headers={"Authorization": f"Bearer {wrk_t}"})
        check("[중요] worker 토큰 → 403", r.status_code == 403, str(r.status_code))
        r = c.post("/api/v1/usage", json=body)
        check("토큰 없음 → 401", r.status_code == 401, str(r.status_code))
        r = c.post("/api/v1/usage/x", json=body, headers=H)
        check("[중요] 하위 경로는 스코프 밖 → 403 (정확 일치)", r.status_code == 403, str(r.status_code))
        rows = log.read_text(encoding="utf-8").splitlines()
        check("[중요] 거절은 한 줄도 쓰지 않는다", len(rows) == n0, str(len(rows)))
        # 기록 실패 — 500 이 아니라 ok:false + 사유
        log.unlink()
        log.mkdir()                                    # 파일 자리에 디렉토리 → open 실패
        r = c.post("/api/v1/usage", json=body, headers=H)
        check("[중요] 기록 실패 → 200 + ok:false · record_error",
              r.status_code == 200 and r.json().get("status") == "record_error" and r.json().get("reason"),
              f"{r.status_code} {r.text[:200]}")
    finally:
        if old_root is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old_root
        shutil.rmtree(tmp, ignore_errors=True)


ISSUE_ROUTES = ("/api/v1/issue/start", "/api/v1/issue/finish", "/api/v1/issue/pause", "/api/v1/issue/cancel",
                "/api/v1/plan/start", "/api/v1/plan/set", "/api/v1/plan/transition")


def test_issue_routes_declared() -> None:
    """`#884` T6 — 일감 흐름·플랜 대행 일곱은 MOUNT · 태그 필수 · 서버에서 관문을 탄다."""
    for r in ISSUE_ROUTES:
        k = f"POST {r}"
        check(f"{k} 는 MOUNT", T.POLICY.get(k) == T.MOUNT, str(T.POLICY.get(k)))
        check(f"{k} 는 태그 필수", k in T.REQUIRE_TAG)
    src = (Path(__file__).resolve().parent / "task_queue" / "server.py").read_text(encoding="utf-8")
    i = src.index("def _issue_gate(")
    check("[중요] 일감 관문이 마운트를 강제한다", "_mount_gate(req.project, require=True)" in src[i:i + 400])
    for fn in ("issue_start_ep", "issue_finish_ep", "issue_pause_ep", "issue_cancel_ep"):
        i = src.index(f"def {fn}(")
        check(f"{fn} 가 관문을 지난다(_issue_call)", "_issue_call(" in src[i:i + 600])
    for fn in ("plan_start_ep", "plan_set_ep", "plan_transition_ep"):
        i = src.index(f"def {fn}(")
        check(f"{fn} 가 관문을 지난다(_plan_call)", "_plan_call(" in src[i:i + 600])
    check("일감 대행은 _tq_log 한 줄을 남긴다", '_tq_log(f"[issue] {op}' in src)
    from master.task_queue import server as S
    for n in ("IssueStartReq", "IssueFinishReq", "IssuePauseReq", "IssueCancelReq", "PlanStartReq",
              "PlanSetReq", "PlanTransitionReq"):
        check(f"{n} 가 project 를 받는다", "project" in getattr(S, n).model_fields)


def test_issue_routes_live() -> None:
    """[중요] 실물 앱 — requester 200 · worker 403 · 무토큰 401 · 태그 없음/비마운트 거절 · 잠금·추적이 임시 트윈에."""
    import os
    import shutil
    import tempfile
    from unittest.mock import patch
    from master import issue_infra as INF
    from master import issue_lock as IL
    from master import plan_tools as PT
    from master.context_synth import issue_track as IT
    tmp = Path(tempfile.mkdtemp(prefix="test_issue_routes_"))
    old_root = os.environ.get("AX_PROJECTS_ROOT")
    plan = ("## 목적\n\n무엇.\n\n<!-- ax:plan:begin v=1 -->\n"
            "| ID | 상태 | 목표 | 대상 | 선행 | 검증 | 근거 |\n|---|---|---|---|---|---|---|\n"
            "| T1 | 대기 | 한다 | x | — | y |  |\n<!-- ax:plan:end -->\n")
    bodies = {7: plan, 8: plan}
    notes: list = []

    def getter(iid):
        return {"id": iid, "subject": "s", "status": "신규", "description": bodies.get(int(iid), plan)}

    def noter(iid, *, notes: str = "", status_name: str = ""):
        globals_notes.append((iid, notes, status_name))
        return "레드마인 갱신"

    def updater(iid, *, description: str, notes: str):
        bodies[int(iid)] = description
        globals_notes.append((iid, notes, ""))
        return "레드마인 갱신"
    globals_notes = notes
    try:
        proots = tmp / "projects"
        for n in ("AXCluster", "NS"):
            (proots / n).mkdir(parents=True)
        (proots / "projects.yaml").write_text(
            "version: 1\nactive: AXCluster\nprojects:\n- AXCluster\n- NS\n", encoding="utf-8")
        os.environ["AX_PROJECTS_ROOT"] = str(proots)
        twin = proots / "AXCluster"
        with patch.object(INF, "default_getter", getter), patch.object(INF, "default_noter", noter), \
                patch.object(PT, "_default_getter", getter), patch.object(PT, "_default_updater", updater):
            c, _m, req_t, wrk_t = _live_queue(tmp)
            H = {"Authorization": f"Bearer {req_t}"}
            body = {"project": "AXCluster", "issue_id": 7}
            route_fields = {
                "/api/v1/issue/finish": {"base": "a" * 40, "end": "b" * 40, "hashes": ["b" * 40]},
                "/api/v1/plan/set": {"tasks": [{"id": "T1", "goal": "한다"}], "why": "검사"},
                "/api/v1/plan/transition": {"task_id": "T1", "to": "작업중"},
            }
            for r in ISSUE_ROUTES:
                route_body = {**body, **route_fields.get(r, {})}
                st = c.post(r, json=route_body, headers={"Authorization": f"Bearer {wrk_t}"}).status_code
                check(f"[중요] worker 토큰 {r} → 403", st == 403, str(st))
                st = c.post(r, json=route_body).status_code
                check(f"무토큰 {r} → 401", st == 401, str(st))
                untagged_body = {k: v for k, v in route_body.items() if k != "project"}
                j = c.post(r, json=untagged_body, headers=H).json()
                check(f"[중요] 태그 없음 {r} → no_project_tag", j.get("status") == "no_project_tag", str(j)[:160])
                j = c.post(r, json={**route_body, "project": "NS"}, headers=H).json()
                check(f"[중요] 비마운트 {r} → not_mounted", j.get("status") == "not_mounted", str(j)[:160])
            check("거절은 잠금 파일을 만들지 않았다", not IL.state_path(twin).exists() and not notes)
            r = c.post("/api/v1/issue/start/x", json=body, headers=H)
            check("[중요] 하위 경로는 스코프 밖 → 403 (정확 일치)", r.status_code == 403, str(r.status_code))
            r = c.post("/api/v1/issue/start", json={**body, "nope": 1}, headers=H)
            check("모르는 키 → 422", r.status_code == 422, str(r.status_code))

            j = c.post("/api/v1/plan/start", json=body, headers=H).json()
            check("plan/start → 판정 next · 프로젝트 7단계", j.get("verdict") == "next"
                  and j.get("project") == "AXCluster", str(j)[:200])
            j = c.post("/api/v1/issue/start", json={**body, "check_only": True}, headers=H).json()
            check("issue/start check_only → ok · free · 쓰기 0", j.get("ok") and j.get("lock_state") == "free"
                  and not notes, str(j)[:200])
            j = c.post("/api/v1/issue/start", json={**body, "branch": "issue/7", "start_rev": "a" * 40},
                       headers=H).json()
            check("[중요] issue/start → 마운트 트윈 잠금 · 시작 노트", j.get("ok") and IL.current(twin)["issue_id"] == 7
                  and any("a" * 40 in n[1] for n in notes), str(j)[:300])
            check("흐름 로그가 그 트윈의 issue_flow.jsonl 에", (twin / "issue_flow.jsonl").is_file())
            j = c.post("/api/v1/plan/transition", json={"project": "AXCluster", "issue_id": 8, "task_id": "T1",
                                                        "to": "작업중"}, headers=H).json()
            check("[중요] 다른 일감 「작업중」 → plan_refused(#7 잠금 · 그 트윈)", j.get("ok") is False
                  and j.get("status") == "plan_refused" and "#7" in j.get("why", ""), str(j)[:300])
            j = c.post("/api/v1/plan/transition", json={**body, "task_id": "T1", "to": "작업중"}, headers=H).json()
            check("plan/transition 같은 일감 → ok", j.get("ok") and j.get("to") == "작업중", str(j)[:200])
            j = c.post("/api/v1/plan/set", json={**body, "tasks": [{"id": "T1", "goal": "한다"},
                                                                   {"id": "T2", "goal": "더"}], "why": "추가"},
                       headers=H).json()
            check("plan/set → ok · T2 추가", j.get("ok") and j.get("added") == ["T2"], str(j)[:200])
            j = c.post("/api/v1/plan/set", json={**body, "tasks": [{"id": "T1", "goal": "x", "state": "완료"}],
                                                 "why": "옆문"}, headers=H).json()
            check("plan/set 상태 옆문 → plan_refused", j.get("ok") is False and j.get("status") == "plan_refused",
                  str(j)[:200])
            j = c.post("/api/v1/issue/pause", json={**body, "end": "b" * 40}, headers=H).json()
            check("issue/pause → ok · 보류", j.get("ok") and 7 in IL.paused(twin), str(j)[:200])
            j = c.post("/api/v1/issue/start", json={**body, "branch": "issue/7", "start_rev": "a" * 40},
                       headers=H).json()
            check("issue/start(보류) → resumed", j.get("ok") and j.get("resumed"), str(j)[:200])
            j = c.post("/api/v1/issue/finish", json={**body, "base": "a" * 40, "end": "c" * 40,
                                                     "hashes": ["b" * 40, "c" * 40], "subjects": ["하나", "둘"]},
                       headers=H).json()
            check("[중요] issue/finish → 등록 · 잠금 해제 · 리뷰 요청 노트", j.get("ok") and j.get("registered")
                  and j.get("lock_released") and IL.current(twin) is None
                  and (IT.current(twin, 7) or {}).get("end") == "c" * 40
                  and notes[-1][1].startswith("리뷰 요청:"), str(j)[:300])
            j = c.post("/api/v1/issue/finish", json={**body, "base": "a" * 40, "end": "c" * 40,
                                                     "hashes": ["c" * 40, "b" * 40]}, headers=H).json()
            check("issue/finish 범위 어긋남 → 200 + ok:false(span)", j.get("ok") is False and j.get("step") == "span",
                  str(j)[:200])
            j = c.post("/api/v1/issue/start", json={**body, "branch": "issue/7", "start_rev": "a" * 40},
                       headers=H).json()
            j = c.post("/api/v1/issue/cancel", json=body, headers=H).json()
            check("issue/cancel 미리보기 → 쓰기 0", j.get("ok") and j.get("confirmed") is False
                  and IL.current(twin)["issue_id"] == 7, str(j)[:200])
            j = c.post("/api/v1/issue/cancel", json={**body, "confirm": True, "delete_branch": True,
                                                     "commits": ["d" * 40 + " 하나"]}, headers=H).json()
            check("issue/cancel 승인 → 해제 · 삭제 허용", j.get("ok") and j.get("branch_delete_allowed")
                  and IL.current(twin) is None, str(j)[:200])
            check("NS 트윈은 그대로", not (proots / "NS" / "issue_lock.json").exists())
    finally:
        if old_root is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old_root
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for fn in (test_server_actually_compiles, test_every_route_declared, test_undeclared_is_an_error,
               test_models_carry_the_tag, test_reject_shape,
               test_stamp_check_does_not_use_mount, test_twin_writers_are_gated,
               test_gates_are_actually_wired, test_claim_filters_by_project,
               test_untagged_is_rejected_on_write_surfaces, test_path_normalization,
               test_senders_are_wired, test_usage_route_live, test_issue_routes_declared,
               test_issue_routes_live):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_tagging: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
