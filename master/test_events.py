"""이벤트 큐 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_events.py

[중요] 지키는 불변식 (PLAN §5.4.5, §5.4.5-a):
   1. **유실 없음** — 소비 중 들어온 이벤트가 사라지지 않는다 (jsonl 을 버린 이유)
   2. **at-least-once** — 크래시하면 다시 처리된다. 절대 조용히 사라지지 않는다
   3. **합치기 키는 `project_id`, casefold** — 프로젝트가 섞이지 않는다
   4. **거부는 지우지 않는다** — '안 옴' 과 '거부됨' 은 다른 사건이다
   5. **소비자는 하나** — flock
"""
from __future__ import annotations

import json
import multiprocessing as mp
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.events import Event, Spool, SpoolError, coalesce  # noqa: E402
from master.events.spool import INDEX_TRAILER  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def ev(pid="Sim/ModularStage", new="abc", **kw):
    return Event(project_id=pid, ref="refs/heads/main", old="000", new=new, **kw)


def _hold_lock(root, ready, release):
    s = Spool(Path(root))
    ready.put(s.acquire())
    release.get()      # 부모가 검사할 때까지 잡고 있는다
    s.release()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-events-test-"))
    s = Spool(tmp)

    print("[1] 넣고 꺼내기")
    s.enqueue(ev(new="c1"))
    s.enqueue(ev(pid="Sim/Other", new="c2"))
    check("대기 2건", s.pending_count() == 2, str(s.pending_count()))
    b = s.claim_batch()
    check("배치 2건", len(b) == 2, b.summary())
    check("incoming 이 비었다", s.pending_count() == 0)
    check("claimed 에 배치가 남아 있다", b.dir.is_dir())
    s.done(b)
    check("done 후 배치 디렉토리 제거", not b.dir.exists())

    print("\n[2] [중요] 합치기 — project_id 별 최신 하나")
    for i in range(5):
        s.enqueue(ev(new=f"c{i}"))
    s.enqueue(ev(pid="Sim/Other", new="x1"))
    b = s.claim_batch()
    check("2개 프로젝트로 축약", len(b) == 2, b.summary())
    check("4건 절약", b.coalesced_away == 4, str(b.coalesced_away))
    ms = [e for e in b.events if e.project_id == "Sim/ModularStage"][0]
    check("[중요] 남은 것이 **최신**", ms.new == "c4", ms.new)
    s.done(b)

    print("\n[3] [중요] 합치기 키는 casefold (§5.5.4-④)")
    merged, dropped = coalesce([ev(pid="Sim/ModularStage", new="a"),
                                ev(pid="sim/modularstage", new="b"),
                                ev(pid="SIM/MODULARSTAGE", new="c")])
    check("대소문자만 다르면 같은 프로젝트", len(merged) == 1 and dropped == 2,
          f"{len(merged)} / {dropped}")
    check("최신이 남는다", merged[0].new == "c", merged[0].new)
    merged, _ = coalesce([ev(pid="Sim/A"), ev(pid="Sim/B")])
    check("다른 프로젝트는 안 뭉친다", len(merged) == 2)

    print("\n[4] [중요] 유실 없음 — 소비 중 들어온 이벤트")
    # jsonl 을 버린 이유가 이것이다. claim 이후에 들어온 것은 **다음 배치**에 온전히 있어야 한다.
    s.enqueue(ev(new="before"))
    b1 = s.claim_batch()
    s.enqueue(ev(new="during"))          # claim 직후 도착
    s.done(b1)
    b2 = s.claim_batch()
    check("이전 배치는 before", b1.events[0].new == "before", b1.events[0].new)
    check("[중요] 사이에 들어온 during 이 다음 배치에 있다",
          len(b2) == 1 and b2.events[0].new == "during", b2.summary())
    s.done(b2)

    print("\n[5] [중요] at-least-once — done 을 안 부르면 다시 온다")
    s.enqueue(ev(new="crashme"))
    b = s.claim_batch()
    check("배치를 받았다", len(b) == 1)
    # done 을 부르지 않고 '크래시'
    s2 = Spool(tmp)
    orphans = s2.orphan_batches()
    check("고아 배치가 남아 있다", len(orphans) == 1, str(orphans))
    batches = list(s2.iter_all_pending())
    check("재기동 시 고아부터 나온다", batches[0].events[0].new == "crashme",
          str([e.new for b_ in batches for e in b_.events]))
    for b_ in batches:
        s2.done(b_)
    check("정리 후 고아 없음", s2.orphan_batches() == [])

    print("\n[6] [중요] 검증 실패는 rejected/ 로 — 지우지 않는다")
    (s.incoming / "bad.json").write_text("{ this is not json", encoding="utf-8")
    (s.incoming / "nopid.json").write_text(json.dumps({"ref": "refs/heads/main"}),
                                           encoding="utf-8")
    b = s.claim_batch()
    check("둘 다 거부", b.rejected == 2, str(b.rejected))
    check("처리 대상 0건", len(b) == 0)
    rej = sorted(p.name for p in s.rejected.iterdir())
    check("rejected/ 에 파일이 남는다", any(n.endswith(".json") for n in rej), str(rej))
    check("사유 파일이 함께 남는다", any(n.endswith(".why") for n in rej), str(rej))
    whys = " ".join((s.rejected / n).read_text(encoding="utf-8")
                    for n in rej if n.endswith(".why"))
    check("project_id 누락 사유 명시", "project_id" in whys, whys[:80])
    s.done(b)

    print("\n[7] 미등록 프로젝트 거부 (§5.5.4-④)")
    s.enqueue(ev(pid="Sim/ModularStage"))
    s.enqueue(ev(pid="Sim/NotRegistered"))
    known = {"sim/modularstage"}
    b = s.claim_batch(is_registered=lambda pid: pid.casefold() in known)
    check("등록된 것만 통과", len(b) == 1 and b.events[0].project_id == "Sim/ModularStage",
          b.summary())
    check("나머지는 거부", b.rejected == 1, str(b.rejected))
    s.done(b)

    print("\n[8] [중요] 재귀 차단 — [ax-index] 커밋은 소비하지 않는다 (§5.5.3-d)")
    s.enqueue(ev(new="human", subject="모듈 정리"))
    s.enqueue(ev(pid="Sim/Other", new="idx",
                 subject=f"컨텍스트 갱신 {INDEX_TRAILER}"))
    b = s.claim_batch()
    check("색인 출력 1건 스킵", b.skipped_index_output == 1, b.summary())
    check("사람 커밋만 남는다",
          len(b) == 1 and b.events[0].new == "human", b.summary())
    s.done(b)
    # 같은 프로젝트에서 색인 커밋이 최신이어도 사람 커밋을 잡아먹으면 안 된다
    s.enqueue(ev(new="human2", subject="수정"))
    s.enqueue(ev(new="idx2", subject=f"재색인 {INDEX_TRAILER}"))
    b = s.claim_batch()
    check("[중요] 색인 커밋이 더 최신이어도 사람 커밋이 남는다",
          len(b) == 1 and b.events[0].new == "human2", b.summary())
    s.done(b)

    print("\n[9] [중요] 단일 소비자 — flock")
    ready, release = mp.Queue(), mp.Queue()
    proc = mp.Process(target=_hold_lock, args=(str(tmp), ready, release))
    proc.start()
    check("다른 프로세스가 락을 잡았다", ready.get(timeout=10))
    s3 = Spool(tmp)
    check("[중요] 두 번째 소비자는 획득 실패", not s3.acquire())
    try:
        with Spool(tmp):
            check("with 문은 예외를 낸다", False, "예외가 안 났다")
    except SpoolError:
        check("with 문은 예외를 낸다", True)
    release.put(True)
    proc.join(timeout=10)
    check("놓인 뒤에는 획득 성공", s3.acquire())
    s3.release()

    print("\n[10] 원자성 — 부분 기록이 보이지 않는다")
    p = s.enqueue(ev(new="atomic"))
    check("incoming 에 최종 파일만", p.parent == s.incoming)
    check("tmp 가 비어 있다", list(s.tmp.iterdir()) == [], str(list(s.tmp.iterdir())))
    check("내용이 온전한 JSON", json.loads(p.read_text(encoding="utf-8"))["new"] == "atomic")
    s.done(s.claim_batch())

    print("\n[11] project_id 없는 이벤트는 생산 단계에서도 거부")
    try:
        Event.from_dict({"ref": "x"})
        check("from_dict 가 거부", False, "예외가 안 났다")
    except SpoolError:
        check("from_dict 가 거부", True)
    for bad in ("", "   ", None):
        try:
            Event.from_dict({"project_id": bad})
            check(f"  {bad!r} 거부", False)
        except SpoolError:
            check(f"  {bad!r} 거부", True)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
