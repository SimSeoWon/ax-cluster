"""리뷰 큐 (`#634`) — **상태가 재시도를 판정한다.**

검증하는 것:

    ① 실패 갈래를 실측 사유로 가른다 (ENV · 결정적 · QUOTA · 일시적)
    ② 상한은 원전값 3, ENV·결정적은 1 — 재시도가 토큰만 쓰는 자리에서 멈춘다
    ③ QUOTA 는 시도 횟수를 **소비하지 않는다** (한도는 공용 자원)
    ④ 커밋당 등재는 한 번 (2026-09-13 NS 리뷰 150개 사고의 결)
    ⑤ 사람 요청(`#638`)이 자동 등재보다 먼저 꺼내진다
    ⑥ 🔴 **결함 ⓒ** — 형식 위반으로 끝나도 다시 잡힌다 (파일 존재로 막지 않는다)
    ⑦ 🔴 **결함 ⓓ** — 재시도가 호출되지 않는 경로가 없다
    ⑧ 포기한 항목도 사람이 다시 넣을 수 있다 (상한을 가볍게 갈 수 있는 근거)
    ⑨ [중요] 깨진 큐를 빈 것으로 덮지 않는다 (덮으면 대기 항목이 조용히 사라진다)
    ⑩ 큐는 `reviews/` 밖이다 (`plan_archive` 가 그 디렉토리를 옮긴다)
    ⑪ 동시에 꺼내도 같은 항목을 두 번 집지 않는다

`.venv/bin/python master/test_review_queue.py`
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import review_queue as Q                 # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def make_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="ax-rq-"))


def raises(fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except Q.ReviewQueueError:
        return True
    except Exception:                                              # noqa: BLE001
        return False
    return False


# ── ① 갈래 판정 — 전부 카나리에서 실제로 난 문구다 ──────────────────────────

def test_classify():
    cases = [
        ("429 You've hit your session limit", Q.QUOTA),
        ("rate limit exceeded", Q.QUOTA),
        ("0xC0000142", Q.ENV),
        ("CreateProcessAsUserW failed", Q.ENV),
        ("agy: 실행파일 없음 — PATH 미등록", Q.ENV),
        ("diff 를 읽지 못했다 — 리뷰 없이 넘기지 않고 기록한다", Q.DETERMINISTIC),
        ("fatal: bad object deadbeef", Q.DETERMINISTIC),
        ("상용 체인(agy → claude) 둘 다 응답 없음", Q.TRANSIENT),
    ]
    for why, want in cases:
        got = Q.classify(why)
        check(f"① {want} ← {why[:40]}", got == want, f"got={got}")


def test_caps():
    check("② 일시적 상한 3 (원전 _DEFAULT_MAX_ATTEMPTS)", Q.cap(Q.TRANSIENT) == 3)
    check("② 형식 위반 상한 3", Q.cap(Q.FORMAT) == 3)
    check("② ENV 는 1 — 재시도는 토큰만 쓴다", Q.cap(Q.ENV) == 1)
    check("② 결정적은 1 — 몇 번을 돌려도 같다", Q.cap(Q.DETERMINISTIC) == 1)


# ── ④⑤ 등재·꺼내기 ─────────────────────────────────────────────────────────

def test_enqueue_and_claim():
    root = make_root()
    it = Q.enqueue(root, kind="commit", key="abc123", files=["Source/A.cpp"])
    check("④ 등재는 pending·시도 0", it["state"] == "pending" and it["attempts"] == 0)
    check("④ 파일 목록이 실린다", it["files"] == ["Source/A.cpp"])

    Q.enqueue(root, key="abc123")
    check("④ 같은 커밋을 두 번 넣어도 하나", len(Q.items(root)) == 1)

    Q.enqueue(root, kind="scope", key="Source/NS/Combat")
    check("④ kind 가 다르면 다른 항목", len(Q.items(root)) == 2)

    check("④ 알 수 없는 kind 거절", raises(Q.enqueue, root, kind="무엇", key="x"))
    check("④ 빈 key 거절", raises(Q.enqueue, root, kind="commit", key=""))

    c = Q.claim(root)
    check("④ claim 이 running·시도 1", c["state"] == "running" and c["attempts"] == 1)
    shutil.rmtree(root)

    root = make_root()
    Q.enqueue(root, key="auto1")
    Q.enqueue(root, key="사람요청", requester="user", priority=10)
    check("⑤ 사람 요청을 먼저 꺼낸다", Q.claim(root)["key"] == "사람요청")
    shutil.rmtree(root)


# ── ②③⑦ 결과와 상한 ───────────────────────────────────────────────────────

def test_outcomes():
    root = make_root()
    Q.enqueue(root, key="ok1")
    r = Q.finish(root, Q.claim(root)["id"], ok=True, note="R35")
    check("성공은 done", r["state"] == "done")
    shutil.rmtree(root)

    root = make_root()
    Q.enqueue(root, key="t1")
    r = Q.finish(root, Q.claim(root)["id"], ok=False, why="둘 다 응답 없음")
    check("⑦ 일시적 실패는 pending 으로 돌아간다", r["state"] == "pending")
    check("🔴 ⑦ 재시도가 호출되지 않는 경로가 없다", Q.claim(root) is not None)
    shutil.rmtree(root)

    root = make_root()
    Q.enqueue(root, key="t2")
    for _ in range(3):
        r = Q.finish(root, Q.claim(root)["id"], ok=False, why="둘 다 응답 없음")
    check("② 일시적은 3회에 포기", r["state"] == "abandoned" and r["attempts"] == 3)
    check("② 포기하면 더 안 꺼낸다", Q.claim(root) is None)
    shutil.rmtree(root)

    for why, label in (("agy: 실행파일 없음 — PATH 미등록", "ENV"),
                       ("diff 를 읽지 못했다", "결정적")):
        root = make_root()
        Q.enqueue(root, key="x")
        r = Q.finish(root, Q.claim(root)["id"], ok=False, why=why)
        check(f"② {label} 은 첫 번째에 멈춘다",
              r["state"] == "abandoned" and r["attempts"] == 1, str(r["attempts"]))
        shutil.rmtree(root)

    root = make_root()
    Q.enqueue(root, key="q1")
    for _ in range(5):
        r = Q.finish(root, Q.claim(root)["id"], ok=False, why="429 session limit")
    check("③ QUOTA 로는 포기하지 않는다", r["state"] == "pending")
    check("③ QUOTA 는 시도를 소비하지 않는다", r["attempts"] == 0, str(r["attempts"]))
    shutil.rmtree(root)


# ── ⑥⑧ 결함 ⓒ 와 복구 경로 ─────────────────────────────────────────────────

def test_format_violation_does_not_block():
    root = make_root()
    Q.enqueue(root, key="f1")
    Q.finish(root, Q.claim(root)["id"], ok=False, why="형식 위반 — 소비자 파서 기준 0건")
    check("🔴 ⑥ 형식 위반으로 끝나도 다시 잡힌다 (결함 ⓒ)", Q.claim(root) is not None)
    shutil.rmtree(root)

    root = make_root()
    Q.enqueue(root, key="r1")
    Q.finish(root, Q.claim(root)["id"], ok=False, why="실행파일 없음")
    check("⑧ 포기 상태가 남는다", bool(Q.items(root, state="abandoned")))
    Q.enqueue(root, key="r1", requester="user", priority=10)
    got = Q.claim(root)
    check("⑧ 사람이 다시 넣으면 잡힌다", got is not None and got["key"] == "r1")
    shutil.rmtree(root)

    root = make_root()
    Q.enqueue(root, key="d1")
    Q.finish(root, Q.claim(root)["id"], ok=True)
    Q.enqueue(root, key="d1")
    c = Q.counts(root)
    check("done 은 다시 등재되지 않는다", c["done"] == 1 and c["pending"] == 0, str(c))
    shutil.rmtree(root)


# ── ⑨⑩ 깨진 큐 · 자리 ──────────────────────────────────────────────────────

def test_broken_queue_and_location():
    root = make_root()
    Q.enqueue(root, key="abc123")
    check("⑩ 큐는 reviews/ 밖이다",
          "reviews" not in Q.queue_path(root).relative_to(root).parts)
    Q.queue_path(root).write_text("{깨졌다", encoding="utf-8")
    check("⑨ 깨진 큐는 읽기에서 멈춘다", raises(Q.counts, root))
    check("⑨ 깨진 큐를 등재로 덮지 않는다", raises(Q.enqueue, root, key="def456"))
    Q.queue_path(root).write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    check("⑨ 형식이 아니면 거절", raises(Q.counts, root))
    shutil.rmtree(root)

    root = make_root()
    check("없는 항목 finish 는 거절", raises(Q.finish, root, "commit:없다", ok=True))
    shutil.rmtree(root)


# ── ⑪ 동시성 ───────────────────────────────────────────────────────────────

def test_concurrent_claim():
    root = make_root()
    for i in range(6):
        Q.enqueue(root, key=f"c{i}")
    got, errors = [], []

    def run():
        try:
            it = Q.claim(root)
            if it:
                got.append(it["id"])
        except Exception as e:                                     # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=run) for _ in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    check("⑪ 동시 claim 에 오류가 없다", not errors, str(errors))
    check("⑪ 같은 항목을 두 번 집지 않는다", len(got) == len(set(got)), str(got))
    check("⑪ 6개를 넘겨 꺼내지 않는다", len(got) == 6, str(len(got)))
    shutil.rmtree(root)


if __name__ == "__main__":
    for fn in (test_classify, test_caps, test_enqueue_and_claim, test_outcomes,
               test_format_violation_does_not_block, test_broken_queue_and_location,
               test_concurrent_claim):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
