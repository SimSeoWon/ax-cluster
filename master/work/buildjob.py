"""빌드 잡 등록·관찰 — 마스터 측 입구 (#204).

κ.0: 빌드는 마스터가 SSH 로 미는 것이 아니라 **큐에 실리고 UE5 워커가 집는다.**
[중요] 이 CLI 는 판단하지 않는다 — 등록하고, 결과(사실)를 보여줄 뿐이다. Flow Y 의
SSH 직접 경로는 그대로 있다(§8.4 — 조용한 폴백 없음, 경로 선택은 호출자가 명시).

    python -m master.work.buildjob enqueue [--tree <워커쪽 경로>] [--timeout N]
    python -m master.work.buildjob watch <task_id> [--timeout N]
    python -m master.work.buildjob close <work_id 접두> --result=pass|fail

`enqueue` 는 전용 work(`[buildjob]` 접두)를 만들고 `type="build"`·`requires=["ue5"]`
태스크 하나를 건다. tree 를 안 주면 워커의 자기 체크아웃(claimer 의 config 기준)이 대상.

[중요] `close` 는 사람이(또는 파이프라인이) watch 로 결과를 **읽은 뒤** 부른다 — verdict 는
마스터의 판단이라 자동이 아니다 (κ.0 ①). 종결 없이 두면 work 가 미종결로 남아 프로젝트
전환 가드(#210)에 걸린다 — 1단계 첫 실전이 정확히 그렇게 걸렸다.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:8101"
HTTP_TIMEOUT = 30


def _token() -> str:
    return (Path.home() / ".config" / "ax-cluster" / "token").read_text(
        encoding="utf-8").strip()


def _call(method: str, path: str, payload=None, *, api=None):
    if api is not None:
        return api(method, path, payload)
    req = urllib.request.Request(
        BASE + path,
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace").strip()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:300]}


def enqueue(*, tree: str = "", timeout: int = 1800, api=None) -> dict:
    """work + build 태스크 등록. 반환에 task_id — watch 가 그걸 받는다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    st, w = _call("POST", "/api/v1/works", {
        "title": f"[buildjob] 빌드 게이트 큐 잡 {stamp}",
        "target_repo": "ModularStage",
        "distribution_mode": "pull",              # C.6 플래그 — 이 work 는 pull 이 정체성
        "original_request": "#204 — 빌드를 큐 잡으로 (κ.0 CI 러너 패턴)",
    }, api=api)
    if st != 200 or not w.get("work_id"):
        return {"ok": False, "step": "work", "http": st, "detail": w}
    st, t = _call("POST", "/api/v1/tasks", {
        "work_id": w["work_id"],
        "type": "build",
        "task_data": ({"tree": tree} if tree else {}) | {"timeout": timeout},
        "requires": ["ue5"],
        "origin": "master",
    }, api=api)
    if st != 200 or not t.get("task_id"):
        return {"ok": False, "step": "task", "http": st, "detail": t}
    return {"ok": True, "work_id": w["work_id"], "task_id": t["task_id"]}


def watch(task_id: str, *, timeout: int = 2400, api=None, sleeper=time.sleep) -> dict:
    """submitted/failed 가 될 때까지 관찰. [중요] 결과를 해석하지 않는다 — 사실을 내민다."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        st, tasks = _call("GET", "/api/v1/tasks", api=api)
        if st != 200:
            return {"ok": False, "error": f"큐 조회 실패 HTTP {st}"}
        t = next((x for x in tasks if str(x.get("task_id", "")).startswith(task_id)), None)
        if t is None:
            return {"ok": False, "error": f"태스크가 없다: {task_id}"}
        s = str(t.get("status") or "")
        if s != last:
            print(f"  {datetime.now().strftime('%H:%M:%S')} status={s}"
                  + (f" worker={t.get('assignee') or t.get('worker_id') or ''}"
                     if s == "claimed" else ""))
            last = s
        if s in ("submitted", "failed", "verified", "cancelled"):
            return {"ok": s in ("submitted", "verified"), "status": s, "task": t}
        sleeper(5)
    return {"ok": False, "error": f"{timeout}초 안에 안 끝났다 (마지막 status={last})"}


def close(work_prefix: str, *, result: str, api=None, sleeper_close=None) -> dict:
    """buildjob work 종결 — 태스크 verify + work merge_status. **verdict 는 호출자의 판단.**

    result="pass" → verify(pass) + merged / "fail" → verify(reject) + rejected.
    [주의] merged/rejected PATCH 는 종결 기록(생산자③)을 트윈에 남긴다 — 빌드 게이트가
    돌았다는 사실은 기록할 가치가 있는 파이프라인 이벤트다.
    """
    if result not in ("pass", "fail"):
        return {"ok": False, "error": f"result 는 pass|fail — {result!r}"}
    st, works = _call("GET", "/api/v1/works", api=api)
    if st != 200:
        return {"ok": False, "error": f"works 조회 실패 HTTP {st}"}
    w = next((x for x in works if str(x.get("work_id", "")).startswith(work_prefix)), None)
    if w is None:
        return {"ok": False, "error": f"work 가 없다: {work_prefix}"}
    wid = str(w["work_id"])
    st, tasks = _call("GET", "/api/v1/tasks", api=api)
    if st != 200:
        return {"ok": False, "error": f"tasks 조회 실패 HTTP {st}"}
    done = []
    for t in tasks:
        if str(t.get("work_id")) != wid or str(t.get("type")) != "build":
            continue
        if str(t.get("status")) == "submitted":
            st2, r2 = _call("POST", f"/api/v1/tasks/{t['task_id']}/verify",
                            {"passed": result == "pass",
                             "result": "pass" if result == "pass" else "reject"}, api=api)
            done.append({"task": t["task_id"], "verify_http": st2,
                         **({"detail": r2} if st2 != 200 else {})})
    # [중요] 마지막 verify 는 merge_status 를 두 번 쓴다 — **동기로** ready_for_review
    #    (logic_lifecycle, verify 안), 그리고 **비동기 auto-cleanup 의 끝**에서 또 한 번
    #    (logic_cleanup §4). 실측 2026-08-18: 동기 flip 만 보고 종결을 썼더니 몇 초 뒤
    #    비동기 쪽이 되덮었다. 그래서 「쓰고 → 되읽고 → 되덮였으면 다시 쓴다」 — cleanup 은
    #    verify 당 한 번이라 유한하고, 종결이 붙는(stick) 것을 눈으로 확인해야 끝이다.
    terminal = "merged" if result == "pass" else "rejected"
    sleep = sleeper_close or time.sleep
    stuck = ""
    st3, r3 = 0, {}
    for attempt in range(6):
        st3, r3 = _call("PATCH", f"/api/v1/works/{wid}", {"merge_status": terminal}, api=api)
        if st3 != 200:
            break
        sleep(3)
        st_w, w_now = _call("GET", f"/api/v1/works/{wid}", api=api)
        # [주의] 단건 GET 은 {"work": {...}, "tasks": [...]} 로 감싼다 — 목록 GET 과 다르다
        inner = (w_now or {}).get("work") or (w_now or {})
        if st_w == 200 and inner.get("merge_status") == terminal:
            stuck = f"{terminal} 확정 (시도 {attempt + 1}회)"
            break
        stuck = f"[주의] 되덮임 감지 — 마지막 관측 {inner.get('merge_status')!r}"
    return {"ok": st3 == 200 and stuck.startswith(terminal), "work_id": wid,
            "verified": done, "settle": stuck,
            "merge_status_http": st3, **({"detail": r3} if st3 != 200 else {})}


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    kw = {}
    pos = []
    for a in rest:
        if a.startswith("--tree="):
            kw["tree"] = a.split("=", 1)[1]
        elif a.startswith("--timeout="):
            kw["timeout"] = int(a.split("=", 1)[1])
        elif a.startswith("--result="):
            kw["result"] = a.split("=", 1)[1]
        elif not a.startswith("--"):
            pos.append(a)
    if cmd == "enqueue":
        got = enqueue(**kw)
        print(json.dumps(got, ensure_ascii=False, indent=2))
        return 0 if got.get("ok") else 1
    if cmd == "watch" and pos:
        got = watch(pos[0], **({"timeout": kw["timeout"]} if "timeout" in kw else {}))
        print(json.dumps(got, ensure_ascii=False, indent=2))
        return 0 if got.get("ok") else 1
    if cmd == "close" and pos and "result" in kw:
        got = close(pos[0], result=kw["result"])
        print(json.dumps(got, ensure_ascii=False, indent=2))
        return 0 if got.get("ok") else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
