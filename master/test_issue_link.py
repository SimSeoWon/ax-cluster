"""색인기 커밋 리뷰 등재 ↔ 일감 마감 추적 연결 (`#884` T2).

검증하는 것:

    ① 추적 해시가 등재되면 우선순위 10 · meta(issue_id) · 해시 `queued`
    ② 추적에 없는 해시는 아무것도 안 바뀐다 (우선순위 0 그대로)
    ③ 이미 `done` 인 항목이 돌아오면 해시 `done` (+ 리뷰 번호)
    ④ 건너뜀은 `skipped` · 정상 리뷰가 이미 있으면(`reviewed=True`) `done`
    ⑤ link_round 가 등록 전에 들어간 큐 항목을 줍는다 (abandoned 포함)
    ⑥ 추적 파일이 깨져도 예외를 색인기로 올리지 않는다
    ⑦ 추적 파일이 없으면 잠금 파일도 만들지 않는다

`.venv/bin/python master/test_issue_link.py`
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import issue_link as L                  # noqa: E402
from master.context_synth import issue_track as T                 # noqa: E402
from master.context_synth import review_queue as Q                # noqa: E402

PASS = FAIL = 0
A, B, C, D = "a" * 40, "b" * 40, "c" * 40, "d" * 40
BASE, END = "0" * 40, "f" * 40


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# #917(R240-12): 만든 임시 루트를 모두 기억해 두고 검사 함수가 끝나면(단언 실패·예외 포함) 지운다.
_TMP: list = []


def new_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="ax-il-"))
    _TMP.append(root)
    return root


def run_cleaning(fn) -> None:
    """`fn()` 을 돌리고 성공·실패와 상관없이 그동안 만든 임시 루트를 지운다. 예외는 그대로 올린다."""
    try:
        fn()
    finally:
        while _TMP:
            shutil.rmtree(_TMP.pop(), ignore_errors=True)


def make_root(hashes=(A, B, C)) -> Path:
    root = new_root()
    if hashes:
        res = T.register(root, 884, project="AXCluster", base=BASE, end=END, hashes=list(hashes))
        assert res["ok"], res
    return root


def hstate(root, sha, n=884):
    rnd = T.current(root, n)
    return next(h for h in rnd["hashes"] if h["sha"] == sha)


def item(root, sha):
    return next(x for x in Q.items(root) if x["id"] == f"commit:{sha}")


def test_on_enqueued():
    root = make_root()
    log = []
    it = Q.enqueue(root, key=A, files=["Source/A.cpp"])
    out = L.on_enqueued(root, A, it, logf=log.append)
    check("① 연결됨", out.get("linked") and out.get("ok"), str(out))
    check("① 우선순위 10", item(root, A)["priority"] == 10, str(item(root, A)))
    check("① meta issue_id", (item(root, A).get("meta") or {}).get("issue_id") == 884, str(item(root, A)))
    check("① 해시 queued", hstate(root, A)["state"] == "queued", str(hstate(root, A)))
    check("① 로그가 남는다", any("우선순위" in m for m in log) and any("set_hash" in m for m in log),
          str(log))
    # 같은 등재가 다시 와도(enqueue 가 기존 항목을 돌려줌) queued→queued 로 무해
    out2 = L.on_enqueued(root, A, Q.enqueue(root, key=A), logf=log.append)
    check("① 재등재도 무해", out2.get("ok") and hstate(root, A)["state"] == "queued", str(out2))

    # ② 추적에 없는 해시
    log2 = []
    it = Q.enqueue(root, key=D)
    out = L.on_enqueued(root, D, it, logf=log2.append)
    check("② 추적 밖은 linked=False", out == {"ok": True, "linked": False}, str(out))
    check("② 우선순위 0 그대로", item(root, D)["priority"] == 0, str(item(root, D)))
    check("② 아무것도 찍지 않는다", not log2, str(log2))
    shutil.rmtree(root)


def test_on_enqueued_done():
    root = make_root()
    Q.enqueue(root, key=B)
    Q.claim(root)
    done = Q.finish(root, f"commit:{B}", ok=True)
    out = L.on_enqueued(root, B, Q.enqueue(root, key=B), logf=lambda m: None)
    check("③ done 항목 → 해시 done", hstate(root, B)["state"] == "done", str(out))
    check("③ done 항목의 우선순위는 건드리지 않는다", item(root, B)["priority"] == 0, str(item(root, B)))
    check("③ 큐 상태가 done 이었다", done["state"] == "done")
    shutil.rmtree(root)


def test_on_skipped():
    root = make_root()
    out = L.on_skipped(root, A, "리뷰 등재 생략: 소스 변경 없음", logf=lambda m: None)
    h = hstate(root, A)
    check("④ skipped", h["state"] == "skipped" and "소스 변경 없음" in h["why"], str(h))
    check("④ 결과 ok", out.get("ok") and out.get("hash_state") == "skipped", str(out))
    out = L.on_skipped(root, B, "리뷰 등재 생략: 정상 리뷰가 이미 있다 (x_bbbbbbbb.md)", reviewed=True,
                       logf=lambda m: None)
    h = hstate(root, B)
    check("④ 정상 리뷰가 있으면 done", h["state"] == "done" and "정상 리뷰" in h["why"], str(h))
    # queued 해시를 건너뜀으로 옮기는 것은 issue_track 이 거절 — 예외 없이 ok=False
    Q.enqueue(root, key=C)
    L.on_enqueued(root, C, item(root, C), logf=lambda m: None)
    out = L.on_skipped(root, C, "소스 밖", logf=lambda m: None)
    check("④ queued→skipped 는 거절되지만 올리지 않는다",
          out.get("ok") is False and out.get("reason") == "bad_transition"
          and hstate(root, C)["state"] == "queued", str(out))
    check("④ 추적 밖 해시는 무시", L.on_skipped(root, D, "x") == {"ok": True, "linked": False})
    shutil.rmtree(root)


def test_link_round():
    root = new_root()
    # 등록 **전에** 색인기가 넣은 항목들
    Q.enqueue(root, key=A)                       # pending
    Q.enqueue(root, key=B)
    Q.claim(root)                                # A → running (먼저 들어갔다)
    Q.enqueue(root, key=C)
    # B 를 done, C 를 abandoned 로
    Q.claim(root)                                # B → running
    Q.finish(root, f"commit:{B}", ok=True)
    Q.claim(root)                                # C → running
    Q.finish(root, f"commit:{C}", ok=False, why="실행파일 없음")   # ENV → abandoned
    T.register(root, 884, project="AXCluster", base=BASE, end=END, hashes=[A, B, C, D])
    log = []
    out = L.link_round(root, 884, logf=log.append)
    check("⑤ 결과 ok", out.get("ok"), str(out))
    check("⑤ 이음 3 · 큐에 없음 1", len(out["linked"]) == 3 and out["untouched"] == [D], str(out))
    check("⑤ running → queued · 우선순위 10",
          hstate(root, A)["state"] == "queued" and item(root, A)["priority"] == 10,
          f"{hstate(root, A)} {item(root, A)['priority']}")
    check("⑤ done → done", hstate(root, B)["state"] == "done")
    check("⑤ abandoned → abandoned (사유)", hstate(root, C)["state"] == "abandoned"
          and "실행파일" in hstate(root, C)["why"], str(hstate(root, C)))
    check("⑤ 큐에 없는 해시는 waiting", hstate(root, D)["state"] == "waiting")
    check("⑤ 요약 로그", any("연결 — 이음 3" in m for m in log), str(log))
    # 다시 불러도 waiting 만 보므로 무해
    out2 = L.link_round(root, 884, logf=lambda m: None)
    check("⑤ 재호출은 이음 0", out2["ok"] and not out2["linked"] and out2["untouched"] == [D], str(out2))
    check("⑤ 등록 없는 일감", L.link_round(root, 999, logf=lambda m: None).get("reason") == "not_registered")
    shutil.rmtree(root)


def test_corruption_tolerated():
    root = make_root()
    T.state_path(root).write_text("{깨짐", encoding="utf-8")
    Q.enqueue(root, key=A)
    log = []
    try:
        a = L.on_enqueued(root, A, item(root, A), logf=log.append)
        b = L.on_skipped(root, B, "x", logf=log.append)
        c = L.link_round(root, 884, logf=log.append)
        raised = False
    except Exception as e:                       # noqa: BLE001
        raised, a, b, c = repr(e), {}, {}, {}
    check("⑥ 예외를 올리지 않는다", raised is False, str(raised))
    check("⑥ track_corrupt 로 보고", a.get("reason") == b.get("reason") == c.get("reason") == "track_corrupt",
          f"{a} {b} {c}")
    check("⑥ [중요] 로 크게 찍는다", sum("[issue_link] [중요]" in m for m in log) == 3, str(log))
    check("⑥ 큐 우선순위는 그대로", item(root, A)["priority"] == 0)
    check("⑥ 추적 파일을 덮지 않았다", T.state_path(root).read_text(encoding="utf-8") == "{깨짐")
    # 큐가 깨져도 (on_enqueued 의 set_priority) 올리지 않는다
    root2 = make_root()
    Q.enqueue(root2, key=A)
    Q.queue_path(root2).write_text("not json", encoding="utf-8")
    log2 = []
    out = L.on_enqueued(root2, A, {"id": f"commit:{A}", "state": "pending"}, logf=log2.append)
    check("⑥ 큐가 깨져도 예외 없음 · [주의]", out.get("reason") == "error"
          and any("[issue_link] [주의]" in m for m in log2), f"{out} {log2}")
    shutil.rmtree(root)
    shutil.rmtree(root2)


def test_no_state_file_no_lock():
    root = new_root()
    out = L.on_skipped(root, A, "x")
    check("⑦ 추적 파일 없으면 linked=False", out == {"ok": True, "linked": False}, str(out))
    check("⑦ 잠금 파일을 만들지 않는다", not (root / T.LOCK_NAME).exists(), str(list(root.iterdir())))
    check("⑦ 빈 sha 는 무시", L.on_enqueued(root, "", {}) == {"ok": True, "linked": False})
    shutil.rmtree(root)


def test_closed_round_not_linked():
    """종합 리뷰가 끝난(닫힌) 라운드의 해시는 issue_of_hash 와 같이 보지 않는다."""
    root = make_root(hashes=(A,))
    L.on_skipped(root, A, "x", logf=lambda m: None)
    T.set_summary(root, 884, state="done", logf=lambda m: None)
    Q.enqueue(root, key=A)
    out = L.on_enqueued(root, A, item(root, A), logf=lambda m: None)
    check("닫힌 라운드는 잇지 않는다", out == {"ok": True, "linked": False} and item(root, A)["priority"] == 0,
          str(out))
    shutil.rmtree(root)


def test_public_apply():
    """`#884` T5 — `apply` 가 공개 이름이고 `_apply` 는 같은 함수의 별칭이다."""
    check("⑨ apply 공개 · _apply 별칭", callable(L.apply) and L._apply is L.apply)
    root = make_root()
    it = Q.enqueue(root, key=C, files=["Source/C.cpp"])
    out = L.apply(root, 884, 1, C, it, lambda m: None)
    check("⑨ apply → queued · 우선순위 10", out.get("ok") and out.get("hash_state") == "queued"
          and item(root, C)["priority"] == 10, str(out))
    shutil.rmtree(root)


def test_cleanup_on_failure():
    """`#917`(R240-12) — 검사 함수가 중간에 실패해도 임시 루트가 남지 않는다."""
    made = []

    def boom():
        made.append(make_root())
        raise AssertionError("의도한 실패")
    try:
        run_cleaning(boom)
        raised = False
    except AssertionError:
        raised = True
    check("R240-12 예외는 그대로 올라온다", raised)
    check("R240-12 실패해도 임시 루트를 지운다", made and not made[0].exists() and not _TMP, str(made))


if __name__ == "__main__":
    for fn in (test_public_apply, test_on_enqueued, test_on_enqueued_done, test_on_skipped, test_link_round,
               test_corruption_tolerated, test_no_state_file_no_lock, test_closed_round_not_linked,
               test_cleanup_on_failure):
        run_cleaning(fn)
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
