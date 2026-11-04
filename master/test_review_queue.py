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
        # `#847` 실측 사유(2026-10-30 18:29:23) — 종전에는 TRANSIENT 로 시도를 소비했다
        ("리뷰 생성 실패: Antigravity 실패 — gemini-3.8-flash-medium: model cooldown 237s", Q.QUOTA),
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


def test_orphan_running_is_reclaimed():
    """🔴 #749 — 소비자가 죽어 남은 running 을 잠금을 쥔 소비자가 회수한다."""
    import subprocess
    root = make_root()
    Q.enqueue(root, key="dead1")
    Q.claim(root)                                               # 소비자가 꺼낸 뒤 죽었다
    check("#749 claim 은 pending 만 집는다 — 회수 없이는 영구 누락",
          Q.claim(root) is None and Q.counts(root)["running"] == 1)
    logs = []
    with Q.consumer_lock(root) as held:
        check("#749 잠금을 얻는다", held is True)
        got = Q.reclaim_orphans(root, logf=logs.append)
    it = Q.items(root)[0]
    check("#749 회수 → pending (일시적 실패 한 번)",
          [g["key"] for g in got] == ["dead1"] and it["state"] == "pending"
          and it["last_kind"] == Q.TRANSIENT and it["attempts"] == 1, str(it))
    check("#749 회수 사유가 이력에 남는다", it["history"][-1]["why"] == Q.ORPHAN_WHY)
    check("#749 회수를 로그에 남긴다", any("회수 dead1" in m for m in logs), str(logs))
    check("#749 회수 뒤 다시 꺼낼 수 있다", Q.claim(root)["key"] == "dead1")

    # 매번 죽는 항목은 상한(3)에서 멈춘다 — 무한 반복 없음
    for _ in range(2):
        with Q.consumer_lock(root):
            Q.reclaim_orphans(root)
        if Q.items(root)[0]["state"] == "pending":
            Q.claim(root)
    check("🔴 #749 세 번 죽으면 abandoned", Q.items(root)[0]["state"] == "abandoned",
          str(Q.items(root)[0]["state"]))
    shutil.rmtree(root)

    # 다른 프로세스가 잠금을 쥐면 못 얻는다 — 살아 있는 소비자의 running 은 건드리지 않는다
    root = make_root()
    code = ("import sys,time; sys.path.insert(0, %r); from master.context_synth import review_queue as Q\n"
            "with Q.consumer_lock(%r) as h:\n print('held' if h else 'no', flush=True); time.sleep(3)")
    proc = subprocess.Popen([sys.executable, "-c", code % (str(Path(__file__).resolve().parents[1]), str(root))],
                            stdout=subprocess.PIPE, text=True)
    first = proc.stdout.readline().strip()
    with Q.consumer_lock(root) as held:
        check("#749 다른 소비자가 쥐고 있으면 False", first == "held" and held is False, first)
    proc.wait()
    with Q.consumer_lock(root) as held:
        check("#749 그 프로세스가 끝나면 다시 얻는다(스테일 잠금 없음)", held is True)
    shutil.rmtree(root)


def test_wait_kind():
    """`#880` — 미러 미도착은 WAIT · 상한 12 · 결정적 마커보다 앞선다."""
    why = "범위 끝 bcdd2905c70f 이 미러에 아직 없다 — 색인기 fetch 를 기다린다"
    check("⑫ 미러 미도착 → WAIT", Q.classify(why) == Q.WAIT, Q.classify(why))
    check("⑫ WAIT 상한 12", Q.cap(Q.WAIT) == 12)
    check("⑫ WAIT 는 한도 소진이 아니다(시도를 소비한다)", not Q.is_quota(Q.WAIT))
    root = make_root()
    Q.enqueue(root, key="w")
    for n in range(1, 13):
        it = Q.claim(root)
        out = Q.finish(root, it["id"], ok=False, why=why)
        if n < 12 and out["state"] != "pending":
            check(f"⑫ {n}회째는 pending", False, out["state"])
            break
    check("⑫ 12회째에 abandoned", out["state"] == "abandoned" and out["attempts"] == 12,
          f"{out['state']} {out['attempts']}")
    shutil.rmtree(root)


def test_claim_exclude():
    """`#880` — exclude 에 든 항목은 꺼내지 않는다(실패해 되돌아간 1순위 항목도)."""
    root = make_root()
    Q.enqueue(root, key="hi", priority=10)
    Q.enqueue(root, key="lo")
    a = Q.claim(root)
    Q.finish(root, a["id"], ok=False, why="응답 없음")            # 일시적 → pending, 우선순위 그대로
    check("⑪ 되돌아간 1순위는 exclude 없으면 다시 1순위", Q.claim(root, exclude=())["key"] == "hi")
    Q.finish(root, "commit:hi", ok=False, why="응답 없음")
    b = Q.claim(root, exclude={"commit:hi"})
    check("⑪ exclude 면 다음 항목을 꺼낸다", b and b["key"] == "lo", str(b))
    check("⑪ exclude 만 남으면 None", Q.claim(root, exclude={"commit:hi", "commit:lo"}) is None)
    shutil.rmtree(root)


def test_set_priority():
    """`#884` T2 — 일감 해시의 커밋 리뷰를 10 으로 올린다. 올리기만 하고 meta 는 합친다."""
    root = make_root()
    Q.enqueue(root, key="lo")
    Q.enqueue(root, key="mid")
    log = []
    it = Q.set_priority(root, "commit:mid", 10, meta={"issue_id": 884}, logf=log.append)
    check("⑬ 올린다", it["priority"] == 10 and it["meta"] == {"issue_id": 884}, str(it))
    check("⑬ 로그 한 줄", len(log) == 1 and "0→10" in log[0], str(log))
    check("⑬ 올린 항목을 먼저 꺼낸다", Q.claim(root)["key"] == "mid")
    it = Q.set_priority(root, "commit:mid", 0, meta={"issue_round": 2}, logf=log.append)
    check("⑬ 낮추지 않는다 · meta 는 합친다",
          it["priority"] == 10 and it["meta"] == {"issue_id": 884, "issue_round": 2}, str(it))
    check("⑬ 상태는 안 바꾼다", it["state"] == "running", it["state"])
    check("⑬ 낮추기 요청은 로그가 말한다", "낮추지 않는다" in log[-1], log[-1])
    check("⑬ 없는 항목은 거절", raises(Q.set_priority, root, "commit:nope", 10))
    shutil.rmtree(root)


if __name__ == "__main__":
    for fn in (test_classify, test_caps, test_enqueue_and_claim, test_outcomes,
               test_format_violation_does_not_block, test_broken_queue_and_location,
               test_concurrent_claim, test_orphan_running_is_reclaimed, test_claim_exclude,
               test_wait_kind, test_set_priority):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
