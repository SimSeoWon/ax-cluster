"""노드 점검·설치 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_provision.py

🔴 지키는 불변식:
   1. **점검은 아무것도 올리지 않는다** — 읽기만 한다
   2. **"됐다" 를 믿지 않는다** — pull 후 `/api/tags` 로 산출물을 다시 확인한다
   3. **상주 금지 노드에 모델이 올라와 있으면 잡아낸다** — 사용자 작업과 VRAM 을 다투는 중이다
   4. **reconcile 은 기본이 dry-run** — 수 GB 를 말없이 받지 않는다
   5. **한 노드가 죽어도 나머지 점검은 계속된다**
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.provision import (  # noqa: E402
    CODER, Node, ProvisionError, check, check_node, pull, reconcile,
)

PASS = FAIL = 0


def check_(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def fake_get(tags=(), ps=(), fail=None):
    calls = []

    def get(url, timeout=None):
        calls.append(url)
        if fail:
            raise fail
        if url.endswith("/api/tags"):
            return {"models": [{"name": n} for n in tags]}
        if url.endswith("/api/ps"):
            return {"models": [{"name": n} for n in ps]}
        raise AssertionError(f"뜻밖의 URL: {url}")

    get.calls = calls
    return get


N_INF = Node("inf", "10.0.0.1:11434", want=[CODER])
N_WS = Node("ws", "10.0.0.2:11434", want=[], resident=False, note="메인 작업 PC")


def main() -> int:
    print("\n[1] 점검은 읽기만 한다")
    g = fake_get(tags=[CODER, "gemma4:e4b"], ps=[CODER])
    st = check_node(N_INF, getter=g)
    check_("닿는다", st.reachable)
    check_("모델 목록", st.models == sorted([CODER, "gemma4:e4b"]), str(st.models))
    check_("상주 목록은 /api/ps 에서", st.loaded == [CODER])
    check_("want 충족", st.missing == [] and st.ok)
    check_("🔴 쓰기 호출이 없다", all("/api/pull" not in u for u in g.calls), str(g.calls))
    check_("tags 와 ps 만 부른다", len(g.calls) == 2, str(g.calls))

    print("\n[2] /api/tags(디스크) 와 /api/ps(VRAM) 는 다르다")
    st = check_node(N_INF, getter=fake_get(tags=[CODER], ps=[]))
    check_("받아는 놨지만 안 올라와 있다", st.models == [CODER] and st.loaded == [])
    check_("  그래도 ok (want 는 보유 기준)", st.ok)

    print("\n[3] 🔴 상주 금지 노드에 모델이 올라와 있으면 잡는다")
    st = check_node(N_WS, getter=fake_get(tags=["gemma4:e4b"], ps=[]))
    check_("올라온 게 없으면 정상", not st.violating and st.ok)
    st = check_node(N_WS, getter=fake_get(tags=["gemma4:e4b"], ps=["gemma4:e4b"]))
    check_("올라와 있으면 위반", st.violating)
    check_("  출력에 드러난다", "상주 금지인데" in st.line(), st.line())
    check_("  ⚠️ 로 표시", st.line().strip().startswith("⚠️"), st.line())
    st2 = check_node(N_INF, getter=fake_get(tags=[CODER], ps=[CODER]))
    check_("추론 노드는 상주해도 정상", not st2.violating)

    print("\n[4] want 중 없는 것을 보고한다")
    st = check_node(N_INF, getter=fake_get(tags=["gemma4:e4b"], ps=[]))
    check_("missing", st.missing == [CODER], str(st.missing))
    check_("  ok=False", not st.ok)
    check_("  출력에 드러난다", "없음:" in st.line(), st.line())
    check_("want 가 비면 missing 도 없다",
           check_node(N_WS, getter=fake_get(tags=[], ps=[])).missing == [])

    print("\n[5] 닿지 않아도 예외를 던지지 않는다 (한 대가 죽어도 점검은 계속된다)")
    st = check_node(N_INF, getter=fake_get(fail=urllib.error.URLError("연결 거부")))
    check_("reachable=False", not st.reachable)
    check_("원인이 남는다", "연결 거부" in st.error, st.error)
    check_("ok=False", not st.ok)
    check_("출력에 표시", "닿지 않음" in st.line(), st.line())
    sts = check([N_INF, N_WS], getter=fake_get(fail=urllib.error.URLError("x")))
    check_("전 노드를 다 돈다", len(sts) == 2)

    print("\n[6] /api/ps 가 없어도 점검을 통째로 실패시키지 않는다")

    def ps_missing(url, timeout=None):
        if url.endswith("/api/tags"):
            return {"models": [{"name": CODER}]}
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    st = check_node(N_INF, getter=ps_missing)
    check_("tags 는 살아 있다", st.reachable and st.models == [CODER])
    check_("loaded 는 빈 채로 둔다 (추측하지 않는다)", st.loaded == [])

    print("\n[7] 🔴 pull 의 '됐다' 를 믿지 않는다 — 산출물을 다시 본다")
    posts = []

    def poster(url, payload):
        posts.append((url, payload))
        return {"status": "success"}

    st = pull(N_INF, CODER, poster=poster, getter=fake_get(tags=[CODER], ps=[]))
    check_("성공 시 상태 반환", CODER in st.models)
    check_("pull 을 불렀다", posts[0][0].endswith("/api/pull"), str(posts))
    check_("stream=False", posts[0][1]["stream"] is False)

    try:
        pull(N_INF, CODER, poster=poster, getter=fake_get(tags=["딴것"], ps=[]))
        check_("🔴 success 라도 tags 에 없으면 실패 처리", False, "통과해 버렸다")
    except ProvisionError as e:
        check_("🔴 success 라도 tags 에 없으면 실패 처리", True)
        check_("  이유를 말한다", "받아지지 않았다" in str(e), str(e))

    print("\n[8] pull 실패 경로")
    try:
        pull(N_INF, "없는모델", poster=lambda u, p: {"error": "invalid model name"},
             getter=fake_get())
        check_("에러 응답을 거부", False)
    except ProvisionError as e:
        check_("에러 응답을 거부", "invalid model name" in str(e), str(e))

    def dead(url, payload):
        raise urllib.error.URLError("연결 거부")

    try:
        pull(N_INF, CODER, poster=dead, getter=fake_get())
        check_("연결 실패를 거부", False)
    except ProvisionError as e:
        check_("연결 실패를 거부", "pull 실패" in str(e), str(e))

    print("\n[9] 🔴 reconcile 은 기본이 dry-run")
    posts.clear()
    msgs = []
    sts = reconcile([N_INF], dry_run=True, progress=msgs.append,
                    poster=poster, getter=fake_get(tags=["gemma4:e4b"], ps=[]))
    check_("🔴 아무것도 받지 않는다", posts == [], str(posts))
    check_("무엇을 받을지 알린다", any("dry-run" in m and CODER in m for m in msgs), str(msgs))
    check_("상태는 그대로 missing", sts[0].missing == [CODER])

    print("\n[10] --apply 면 실제로 받는다")
    # pull 전에는 없고 pull 뒤에는 있어야 한다 — 상태가 변하는 가짜가 필요하다.
    box = {"tags": ["gemma4:e4b"]}

    def evolving(url, timeout=None):
        if url.endswith("/api/tags"):
            return {"models": [{"name": n} for n in box["tags"]]}
        return {"models": []}

    posts.clear()

    def installing(url, payload):
        posts.append((url, payload))
        box["tags"] = box["tags"] + [payload["model"]]   # 실제로 받아진다
        return {"status": "success"}

    sts = reconcile([N_INF], dry_run=False, poster=installing, getter=evolving)
    check_("pull 을 불렀다", len(posts) == 1 and posts[0][1]["model"] == CODER, str(posts))
    check_("받은 뒤 ok", sts[0].ok and CODER in sts[0].models, str(sts[0].models))

    print("\n[10b] 받았다고 하는데 실제로 안 생기면 reconcile 이 터진다")
    box["tags"] = ["gemma4:e4b"]
    posts.clear()
    try:
        reconcile([N_INF], dry_run=False, getter=evolving,
                  poster=lambda u, p: (posts.append((u, p)), {"status": "success"})[1])
        check_("🔴 거짓 성공을 통과시키지 않는다", False, "통과해 버렸다")
    except ProvisionError:
        check_("🔴 거짓 성공을 통과시키지 않는다", True)

    posts.clear()
    reconcile([N_WS], dry_run=False, poster=poster, getter=fake_get(tags=[], ps=[]))
    check_("want 가 없는 노드는 건드리지 않는다", posts == [], str(posts))

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
