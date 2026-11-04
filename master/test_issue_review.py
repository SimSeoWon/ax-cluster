"""일감 범위 리뷰 상태 (`#883` T3) — 완료 게이트가 읽는 기계 판정.

검증하는 것:

    ① 범위 항목 없음 → none · 막힘
    ② pending·running·WAIT 재큐 → pending · 막힘
    ③ abandoned → abandoned · 막힘 (복구 경로를 말한다)
    ④ done + HIGH 0 → 완료 가능 (mid·low 미결은 안 막는다)
    ⑤ done + HIGH open → 막힘 · 번호와 항목 id 를 말한다
    ⑥ HIGH 를 사유와 함께 기각 → 완료 가능
    ⑦ HIGH accepted → 막힘 (applied 까지) · failed 도 막힘 · applied 는 풀림
    ⑧ 범위 항목이 여럿 → 최신(created_at) 이 이긴다 · id 는 전부 싣는다
    ⑨ 사유 없는 기각은 거절 → 여전히 막힘
    ⑩ done(스킵, 리뷰 파일 없음) → 완료 가능 · done 인데 번호 없음 → 막힘(fail-closed)
    ⑪ 다른 일감의 항목은 섞이지 않는다 · 큐를 바꾸지 않는다
    ⑫ (`#884` T5) 마감 추적 라운드가 있으면 그 종합 리뷰(summary)로 판정한다 — 옛 범위 항목보다 우선
         대기 해시 → pending(개수) · summary waiting/queued/running → pending · failed → failed ·
         abandoned → abandoned(막힘) · done+serial → HIGH 판정 · done 스킵 → 완료 가능 ·
         done 번호 없음 → 막힘 · 깨진 추적 파일 → 예외(관문이 막는다) · 추적 파일 없으면 잠금 파일도 안 만든다

`.venv/bin/python master/test_issue_review.py`
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import fix_index as F                   # noqa: E402
from master.context_synth import issue_review as IR               # noqa: E402
from master.context_synth import issue_track as IT                # noqa: E402
from master.context_synth import review_queue as RQ               # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


ISSUE = 883
B1, E1 = "1" * 40, "2" * 40
B2, E2 = "3" * 40, "4" * 40


def range_review(base: str, end: str, issue: int, rows: list) -> str:
    """rows: [(위험도, 라인)] — 2절 안전성 행. 1절 컨벤션은 low 한 행."""
    safety = "\n".join(f"| m/x.py | {sev} | {line} | 설명{line} | 고친다 |" for sev, line in rows)
    return (f"# 일감 범위 리뷰 — #{issue}\n\n- 범위: `{base}..{end}`\n- 일감: #{issue}\n"
            f"- 작성자: Antigravity\n- 파일: 1개\n- 생성: 2026-11-04 10:00\n\n"
            "### m\n\n## 1. 변경분 코딩 컨벤션\n"
            "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n"
            "| m/x.py | 명명 | 접두 누락 | 3 | low |\n\n"
            "## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
            "|---|---|---|---|---|\n" + safety + "\n")


def write_review(root: Path, base: str, end: str, issue: int, rows: list, hhmm="1000") -> None:
    d = root / "reviews" / "_range"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"2026-11-04_{hhmm}_issue{issue}_{base[:8]}-{end[:8]}.md").write_text(
        range_review(base, end, issue, rows), encoding="utf-8")


def enqueue(root: Path, base: str, end: str, issue: int = ISSUE) -> dict:
    return RQ.enqueue(root, kind="range", key=f"{base}..{end}",
                      meta={"issue_id": issue, "base": base, "end": end},
                      requester=f"issue_flow#{issue}")


def set_queue(root: Path, item_id: str, **kv) -> None:
    """테스트 전용 — 큐 파일의 항목 필드를 직접 바꾼다(created_at 순서 고정 등)."""
    p = RQ.queue_path(root)
    data = json.loads(p.read_text(encoding="utf-8"))
    for it in data["items"]:
        if it["id"] == item_id:
            it.update(kv)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def done(root: Path, item_id: str, note: str = "ok") -> None:
    RQ.claim(root)
    RQ.finish(root, item_id, ok=True, note=note)


def new_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="issrev-"))


def test_none():
    root = new_root()
    enqueue(root, B1, E1, issue=999)                # 다른 일감
    got = IR.issue_review_status(root, ISSUE)
    check("① none", got["review"] == "none" and got["ok_to_complete"] is False
          and got["items"] == [], str(got))
    check("① 사유가 등재를 말한다", "등재" in got["why"], got["why"])
    shutil.rmtree(root)


def test_pending():
    root = new_root()
    it = enqueue(root, B1, E1)
    got = IR.issue_review_status(root, ISSUE)
    check("② pending(대기)", got["review"] == "pending" and not got["ok_to_complete"]
          and got["item_id"] == it["id"], str(got))
    RQ.claim(root)
    check("② running → pending", IR.issue_review_status(root, ISSUE)["review"] == "pending")
    RQ.finish(root, it["id"], ok=False, why=f"범위 끝 {E1[:12]} 이 미러에 아직 없다 — 색인기 fetch 를 기다린다")
    got = IR.issue_review_status(root, ISSUE)
    check("② WAIT 재큐 → pending · 직전 사유를 싣는다",
          got["review"] == "pending" and "미러" in got["last_why"] and "wait" in got["why"], str(got))
    before = RQ.queue_path(root).read_bytes()
    IR.issue_review_status(root, ISSUE)
    check("⑪ 판정은 큐를 바꾸지 않는다", RQ.queue_path(root).read_bytes() == before)
    shutil.rmtree(root)


def test_abandoned():
    root = new_root()
    it = enqueue(root, B1, E1)
    RQ.claim(root)
    RQ.finish(root, it["id"], ok=False, why="범위 aaaa..bbbb 의 커밋을 찾지 못했다")   # 결정적 → 상한 1
    got = IR.issue_review_status(root, ISSUE)
    check("③ abandoned", got["review"] == "abandoned" and not got["ok_to_complete"], str(got))
    check("③ 복구 경로(재등재)를 말한다", "다시 등재" in got["why"], got["why"])
    shutil.rmtree(root)


def test_done_paths():
    root = new_root()
    it = enqueue(root, B1, E1)
    write_review(root, B1, E1, ISSUE, [("mid", 10)])
    done(root, it["id"])
    got = IR.issue_review_status(root, ISSUE)
    check("④ done + HIGH 0 → 완료 가능", got["review"] == "done" and got["ok_to_complete"]
          and got["serial"] == "R1" and got["blocking"] == [], str(got))
    check("④ mid·low 미결은 건수만", got["open_other"] == 2 and "R1" in got["why"], str(got))
    shutil.rmtree(root)

    root = new_root()
    it = enqueue(root, B1, E1)
    write_review(root, B1, E1, ISSUE, [("high", 10), ("높음", 20), ("low", 30)])
    done(root, it["id"])
    got = IR.issue_review_status(root, ISSUE)
    ids = [b["id"] for b in got["blocking"]]
    check("⑤ HIGH open → 막힘 (원문 「높음」도 high)", got["review"] == "done"
          and not got["ok_to_complete"] and ids == ["R1-2", "R1-3"], str(got))
    check("⑤ 막힘 항목 모양", got["blocking"][0] == {
        "id": "R1-2", "file": "m/x.py", "line": "10", "summary": "설명10",
        "severity": "high", "state": "open"}, str(got["blocking"][0]))
    check("⑤ 사유가 번호·id·복구를 말한다", all(s in got["why"] for s in ("R1", "R1-2", "R1-3", "dismissed")),
          got["why"])

    r = F.set_status(root, "R1-2", "dismissed")
    check("⑨ 사유 없는 기각 거절", r["ok"] is False, str(r))
    check("⑨ 거절 뒤에도 막힘", [b["id"] for b in IR.issue_review_status(root, ISSUE)["blocking"]]
          == ["R1-2", "R1-3"])

    F.set_status(root, "R1-2", "dismissed", note="의도된 동작")
    F.set_status(root, "R1-3", "accepted", note="고친다")
    got = IR.issue_review_status(root, ISSUE)
    check("⑦ accepted 는 막힘", not got["ok_to_complete"]
          and got["blocking"] == [{**got["blocking"][0], "id": "R1-3", "state": "accepted"}], str(got))
    F.set_status(root, "R1-3", "failed")
    check("⑦ failed 도 막힘", IR.issue_review_status(root, ISSUE)["blocking"][0]["state"] == "failed")
    F.set_status(root, "R1-3", "applied", commit="f" * 40)
    got = IR.issue_review_status(root, ISSUE)
    check("⑥⑦ 기각(사유)·applied → 완료 가능", got["ok_to_complete"] and got["blocking"] == [], str(got))
    F.set_status(root, "R1-3", "stale")
    check("⑦ stale 도 풀림", IR.issue_review_status(root, ISSUE)["ok_to_complete"])
    shutil.rmtree(root)


def test_latest_wins():
    root = new_root()
    a = enqueue(root, B1, E1)
    write_review(root, B1, E1, ISSUE, [("high", 10)], hhmm="0900")
    done(root, a["id"])
    b = enqueue(root, B2, E2)
    set_queue(root, a["id"], created_at="2026-11-04T09:00:00+09:00")
    set_queue(root, b["id"], created_at="2026-11-04T11:00:00+09:00")
    got = IR.issue_review_status(root, ISSUE)
    check("⑧ 최신 항목(pending)이 이긴다", got["review"] == "pending" and got["item_id"] == b["id"]
          and got["items"] == [a["id"], b["id"]] and got["latest_of"] == 2, str(got))
    check("⑧ 사유가 「최신」을 밝힌다", "2개 중 최신" in got["why"], got["why"])
    write_review(root, B2, E2, ISSUE, [("low", 5)], hhmm="1100")
    done(root, b["id"])
    got = IR.issue_review_status(root, ISSUE)
    check("⑧ 최신 리뷰(HIGH 0) 기준으로 완료 가능 — 옛 R 의 HIGH 는 안 본다",
          got["ok_to_complete"] and got["serial"] == "R2", str(got))
    set_queue(root, a["id"], created_at="2026-11-04T12:00:00+09:00")
    got = IR.issue_review_status(root, ISSUE)
    check("⑧ 순서는 created_at 으로 정한다", got["item_id"] == a["id"] and got["serial"] == "R1"
          and not got["ok_to_complete"], str(got))
    shutil.rmtree(root)


def test_skip_and_unknown_serial():
    root = new_root()
    it = enqueue(root, B1, E1)
    done(root, it["id"], note="스킵: 소스 변경 없음")
    got = IR.issue_review_status(root, ISSUE)
    check("⑩ 스킵 완료 → 완료 가능", got["review"] == "done" and got["ok_to_complete"]
          and got["serial"] == "", str(got))
    shutil.rmtree(root)

    root = new_root()
    it = enqueue(root, B1, E1)
    done(root, it["id"], note="2026-11-04_1000_x.md (R9)")
    got = IR.issue_review_status(root, ISSUE)
    check("⑩ [중요] done 인데 번호 없음 → 막힘(fail-closed)", got["review"] == "done"
          and not got["ok_to_complete"] and "번호" in got["why"], str(got))
    shutil.rmtree(root)


def test_logs():
    root = new_root()
    lines = []
    IR.issue_review_status(root, ISSUE, logf=lines.append)
    check("로그: 판정 줄을 찍는다", any("[issue-review] #883 판정 none" in m for m in lines), str(lines))
    shutil.rmtree(root)


HA, HB = "a" * 40, "b" * 40


def tracked_root(*, legacy_done: bool = False) -> Path:
    root = new_root()
    if legacy_done:                                 # 같은 일감의 옛 범위 항목(HIGH 0 done)이 있어도
        it = enqueue(root, B2, E2)
        write_review(root, B2, E2, ISSUE, [("mid", 1)], hhmm="0900")
        done(root, it["id"])
    r = IT.register(root, ISSUE, project="AXCluster", base=B1, end=E1, hashes=[HA, HB])
    assert r["ok"], r
    return root


def terminal(root: Path) -> None:
    IT.set_hash(root, ISSUE, HA, state="done", serial="R90", findings=0)
    IT.set_hash(root, ISSUE, HB, state="skipped", why="소스 변경 없음")


def track_item(root: Path) -> dict:
    return RQ.enqueue(root, kind="range", key=f"{B1}..{E1}", priority=10,
                      meta={"issue_id": ISSUE, "base": B1, "end": E1, "issue_round": 1, "track": True},
                      requester="issue_progress")


def test_track_pending_and_failed():
    root = tracked_root(legacy_done=True)
    lines = []
    got = IR.issue_review_status(root, ISSUE, logf=lines.append)
    check("⑫ 추적 라운드가 옛 범위 항목보다 우선 → pending", got["review"] == "pending"
          and not got["ok_to_complete"] and got["round"] == 1, str(got))
    check("⑫ 대기 해시 수를 말한다", "대기 해시 2개" in got["why"] and got["hashes"]["pending"] == 2
          and got["hashes"]["total"] == 2, str(got))
    check("⑫ 로그: 추적 라운드로 판정", any("마감 추적 라운드 1 로 판정" in m for m in lines)
          and any("판정 pending" in m for m in lines), str(lines))
    IT.set_hash(root, ISSUE, HA, state="queued")
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ queued 해시도 대기", got["hashes"]["queued"] == 1 and got["hashes"]["waiting"] == 1
          and got["review"] == "pending", str(got))
    terminal(root)
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ 해시 종결 · summary waiting → pending", got["review"] == "pending"
          and "종합 리뷰 waiting" in got["why"] and got["hashes"]["pending"] == 0, str(got))
    it = track_item(root)
    IT.set_summary(root, ISSUE, state="queued", item_id=it["id"])
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ summary queued → pending · item_id", got["review"] == "pending" and got["item_id"] == it["id"]
          and got["queue_state"] == "pending" and got["items"] == [it["id"]], str(got))
    IT.set_summary(root, ISSUE, state="running")
    check("⑫ summary running → pending", IR.issue_review_status(root, ISSUE)["review"] == "pending")
    IT.set_summary(root, ISSUE, state="failed")
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ summary failed → failed · 막힘", got["review"] == "failed" and not got["ok_to_complete"]
          and "다시 건다" in got["why"], str(got))
    IT.set_summary(root, ISSUE, state="abandoned")
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ summary abandoned → abandoned · 막힘", got["review"] == "abandoned" and not got["ok_to_complete"]
          and "다시 등재" in got["why"], str(got))
    shutil.rmtree(root)


def test_track_done():
    root = tracked_root()
    terminal(root)
    write_review(root, B1, E1, ISSUE, [("high", 10), ("low", 30)])
    F.sweep(root, logf=lambda m: None)
    serial = F.serial_for_range(root, B1, E1)
    it = track_item(root)
    IT.set_summary(root, ISSUE, state="queued", item_id=it["id"])
    IT.set_summary(root, ISSUE, state="done", serial=serial, noted=True)
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ done + HIGH open → 막힘 · 번호", got["review"] == "done" and got["serial"] == serial
          and not got["ok_to_complete"] and [b["id"] for b in got["blocking"]] == [f"{serial}-2"]
          and "라운드 1 종합 리뷰" in got["why"], str(got))
    F.set_status(root, f"{serial}-2", "dismissed", note="의도")
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ HIGH 기각 → 완료 가능", got["ok_to_complete"] and got["blocking"] == []
          and got["hashes"] == {"total": 2, "waiting": 0, "queued": 0, "done": 1, "abandoned": 0,
                                "skipped": 1, "pending": 0}, str(got))
    shutil.rmtree(root)

    root = tracked_root()
    terminal(root)
    it = track_item(root)
    IT.set_summary(root, ISSUE, state="queued", item_id=it["id"])
    done(root, it["id"], note="스킵: 변경 파일 없음")
    IT.set_summary(root, ISSUE, state="done", noted=True)
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ done 스킵(번호 없음) → 완료 가능", got["review"] == "done" and got["ok_to_complete"]
          and got["serial"] == "", str(got))
    shutil.rmtree(root)

    root = tracked_root()
    terminal(root)
    it = track_item(root)
    IT.set_summary(root, ISSUE, state="queued", item_id=it["id"])
    done(root, it["id"], note="x.md")
    IT.set_summary(root, ISSUE, state="done", noted=True)
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ [중요] done 인데 번호 없음 → 막힘", got["review"] == "done" and not got["ok_to_complete"]
          and "번호" in got["why"], str(got))
    shutil.rmtree(root)


def test_track_corrupt_and_absent():
    root = new_root()
    IT.state_path(root).write_text("{깨짐", encoding="utf-8")
    try:
        IR.issue_review_status(root, ISSUE)
        raised = False
    except IT.IssueTrackError:
        raised = True
    check("⑫ 깨진 추적 파일 → IssueTrackError(관문이 막는다)", raised)
    check("⑫ 깨진 파일 덮어쓰지 않음", IT.state_path(root).read_text(encoding="utf-8") == "{깨짐")
    shutil.rmtree(root)

    root = new_root()
    got = IR.issue_review_status(root, ISSUE)
    check("⑫ 추적 없음 → 옛 경로 · round None", got["review"] == "none" and got["round"] is None
          and got["hashes"] == {}, str(got))
    check("⑫ 추적 파일 없으면 잠금 파일도 안 만든다", not (root / IT.LOCK_NAME).exists()
          and not IT.state_path(root).exists())
    shutil.rmtree(root)


if __name__ == "__main__":
    for fn in (test_none, test_pending, test_abandoned, test_done_paths, test_latest_wins,
               test_skip_and_unknown_serial, test_logs, test_track_pending_and_failed,
               test_track_done, test_track_corrupt_and_absent):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
