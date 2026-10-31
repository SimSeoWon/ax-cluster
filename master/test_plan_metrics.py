"""플랜 효용 계측(`#864` T2·T3) — 가짜 노트 이력·플랜 본문·git·거절 기록으로만 돈다(네트워크 0).

실행: .venv/bin/python -B master/test_plan_metrics.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB     # noqa: E402
from master import plan_metrics as M    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


STATUSES = {1: {"id": 1, "name": "신규", "is_closed": False},
            2: {"id": 2, "name": "진행", "is_closed": False},
            3: {"id": 3, "name": "해결", "is_closed": False},
            5: {"id": 5, "name": "검토", "is_closed": False},
            4: {"id": 4, "name": "완료", "is_closed": True}}


def j(at: str, notes: str = "", status=None) -> dict:
    details = [] if status is None else [{"property": "attr", "name": "status_id",
                                          "old_value": str(status[0]), "new_value": str(status[1])}]
    return {"created_on": f"2026-10-31T{at}:00Z", "notes": notes, "details": details}


def plan_issue() -> dict:
    tasks = [PB.Task("T1", "완료", "읽기", "`master/a.py` · master/test_a.py", [], "", "abc1234"),
             PB.Task("T2", "완료", "쓰기", "docs/ 문서", ["T1"], "", "3/3"),
             PB.Task("T3", "작업중", "검사", "자유 서술만", ["T2"]),
             PB.Task("T4", "대기", "나중", "master/*.json")]
    body = PB.append("## 스펙\n", tasks)
    return {"id": 900, "subject": "가짜 플랜", "status": {"id": 4, "name": "완료"},
            "created_on": "2026-10-31T09:00:00Z", "closed_on": "2026-10-31T15:00:00Z",
            "description": body,
            "journals": [
                j("09:05", "플랜 등록 — 추가 T1, T2 · 제거 없음\n사유: x"),
                j("09:10", "플랜 T1: 대기 → 작업중 — 시작"),
                j("09:20", "플랜 T1: 작업중 → 차단 — 막힘"),
                j("09:25", "플랜 T1: 차단 → 작업중"),
                j("09:40", "플랜 T1: 작업중 → 완료 — 커밋 abc1234 · test_a 12/12 통과"),
                j("09:41", "플랜 T2: 대기 → 작업중"),
                # 50분 공백 → 교대: T2 가 작업중이었고 다음 전이가 T2 → 이어 잡음
                j("10:31", "플랜 T2: 작업중 → 완료 — 문서만 고쳤다(근거 없음)"),
                j("10:32", "플랜 T3: 대기 → 작업중"),
                j("10:33", "플랜 T3: 작업중 → 대기"),
                j("10:34", "플랜 T3: 대기 → 작업중"),
                # 60분 공백 → T3 작업중인데 다음 전이는 T4 → 못 이어 잡음
                j("11:34", "플랜 T4: 대기 → 차단 — 외부 대기"),
                j("11:35", "플랜 T4: 차단 → 대기"),
                j("12:00", "일반 노트 — 플랜 아님"),
                j("14:00", "종결 · 커밋 deadbe7 · 9건 통과", status=(2, 4)),
            ]}


def run() -> None:
    issue = plan_issue()

    # ── 정규식 ──
    check("해시 — 숫자·문자 혼합", M.has_hash("커밋 abc1234 반영"))
    check("해시 — 날짜·영단어 아님", not M.has_hash("2026103112 · deadbeef cafebabe"))
    check("검사 수치", M.has_test("12/12") and M.has_test("27건") and M.has_test("통과")
          and not M.has_test("문서만 고쳤다"))

    trans = M.plan_transitions(issue["journals"])
    check("전이만 뽑는다", len(trans) == 11, str(len(trans)))
    check("노트 분리", trans[0]["note"] == "시작" and trans[3]["note"].startswith("커밋"))

    st = M.task_stats(trans)
    check("T1 리드 30분", st["T1"]["lead_min"] == 30.0, str(st["T1"]))
    check("T1 차단 1·되돌림 1", st["T1"]["blocked"] == 1 and st["T1"]["reopen"] == 1)
    check("T3 작업중→대기 되돌림", st["T3"]["working_to_waiting"] == 1 and st["T3"]["lead_min"] is None)
    check("T4 차단만", st["T4"]["blocked"] == 1 and st["T4"]["reopen"] == 0)

    ev = M.evidence_fidelity(trans)
    check("근거 — 완료 2 · 해시 1 · 검사 1", ev["done_transitions"] == 2 and ev["with_hash"] == 1
          and ev["with_test"] == 1 and ev["either_ratio"] == 0.5, str(ev))

    rs = M.resume_accuracy(trans, 30)
    check("재개 — 공백 2 · 셀 것 2 · 이어 1", rs["gaps"] == 2 and rs["countable"] == 2
          and rs["continued"] == 1 and rs["ratio"] == 0.5 and rs["label"] == "근사", str(rs))
    rs = M.resume_accuracy(trans, 55)
    check("재개 — 기준 55분이면 공백 1", rs["gaps"] == 1 and rs["continued"] == 0)
    idle = M.plan_transitions([j("09:00", "플랜 T1: 대기 → 작업중"), j("09:01", "플랜 T1: 작업중 → 완료 — a1b2c3d"),
                               j("12:00", "플랜 T2: 대기 → 작업중")])
    rs = M.resume_accuracy(idle, 30)
    check("재개 — 작업중 없는 공백은 유휴", rs["gaps"] == 1 and rs["countable"] == 0 and rs["idle_gaps"] == 1)

    # ── 범위 이탈 ──
    toks = M.target_tokens([t.target for t in PB.parse(issue["description"]).tasks])
    check("대상 토큰", toks == ["master/a.py", "master/test_a.py", "docs/", "master/*.json"], str(toks))
    check("대상 판정", M.in_targets("master/a.py", toks) and M.in_targets("docs/x/y.md", toks)
          and M.in_targets("master/c.json", toks) and not M.in_targets("master/b.py", toks))

    def fake_git(args):
        check("git 그렙이 경계를 건다", any("#900([^0-9]|$)" in a for a in args), str(args))
        return ("\x1eaaaaaaa1111\x1ffix(#900): 고침\n\n본문\x1f\nmaster/a.py\nmaster/b.py\n"
                "\x1ebbbbbbb2222\x1fdocs: 인수인계\n\n#900 완료\x1f\ndocs/x.md\nreports/r.md\n"
                "\x1eccccccc3333\x1ffix(#9001): 다른 일감\x1f\nmaster/z.py\n")
    commits = M.issue_commits(900, git=fake_git)
    check("#9001 은 거른다", [c["hash"][:7] for c in commits] == ["aaaaaaa", "bbbbbbb"], str(commits))
    check("제목 언급 = primary", commits[0]["primary"] and not commits[1]["primary"])
    sc = M.scope_drift(commits, [t.target for t in PB.parse(issue["description"]).tasks])
    check("이탈 — 파일 4 · 밖 2", sc["files"] == 4 and sc["outside"] == ["master/b.py", "reports/r.md"]
          and sc["outside_ratio"] == 0.5, str(sc))
    check("이탈 — 제목 커밋만 2 중 1", sc["primary_files"] == 2 and sc["primary_outside"] == ["master/b.py"])

    # ── 기준선 ──
    b = M.baseline_metrics(issue, STATUSES)
    check("기준선 리드 6h", b["lead_hours"] == 6.0 and b["closed"], str(b))
    check("기준선 종결 노트 근거", b["close_note"] == {"hash": True, "test": True})
    reo = {"id": 1, "subject": "s", "status": {"id": 4}, "created_on": "2026-10-31T00:00:00Z",
           "closed_on": "2026-10-31T10:00:00Z",
           "journals": [j("01:00", status=(1, 2)), j("02:00", status=(2, 3)),
                        j("04:00", "재현됨", status=(3, 2)), j("05:00", status=(2, 3)),
                        j("06:00", status=(3, 4)), j("07:00", status=(4, 2)),
                        j("08:00", status=(2, 5)), j("09:00", status=(5, 4)),
                        j("10:00", "그냥 닫음", status=(4, 4))]}
    b = M.baseline_metrics(reo, STATUSES)
    check("재개 2(해결→진행 · 완료→진행), 검토→완료는 아님", b["reopen"] == 2, str(b))
    check("해결 체류 2h+1h", b["resolved_hours"] == 3.0, str(b))
    check("마지막 종결 노트 근거 없음", b["close_note"] == {"hash": False, "test": False})
    still = {"id": 2, "subject": "s", "status": {"id": 3}, "created_on": "2026-10-31T00:00:00Z",
             "closed_on": None, "journals": [j("01:00", status=(1, 3))]}
    b = M.baseline_metrics(still, STATUSES, now=datetime(2026, 10, 31, 3, tzinfo=timezone.utc))
    check("미종결 — 리드 N/A · 해결 체류는 지금까지", b["lead_hours"] is None
          and b["resolved_hours"] == 2.0 and b["close_note"] is None, str(b))
    agg = M.aggregate([M.baseline_metrics(reo, STATUSES), M.baseline_metrics(issue, STATUSES), b])
    check("집계", agg["issues"] == 3 and agg["closed"] == 2 and agg["lead_hours_median"] == 8.0
          and agg["reopened_issues"] == 1 and agg["close_notes"] == 2
          and agg["close_note_either_share"] == 0.5, str(agg))

    # ── CLI (가짜 HTTP·git·거절 기록) ──
    tmp = Path(tempfile.mkdtemp())
    events = tmp / "plan_events.jsonl"
    events.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in [
        {"issue_id": 900, "kind": "missing_note"}, {"issue_id": 900, "kind": "missing_note"},
        {"issue_id": 900, "kind": "unsettled_deps"}, {"issue_id": 1, "kind": "no_plan"}]) + "\n깨진 줄\n",
        encoding="utf-8")
    pages = []

    def fake_get(path):
        if path == "/issue_statuses.json":
            return {"issue_statuses": list(STATUSES.values())}
        if path.startswith("/issues.json"):
            pages.append(path)
            off = int(path.rsplit("offset=", 1)[1])
            ids = [1, 2, 900][off:off + 2] if "limit=2" in path else [1, 2, 900]
            return {"total_count": 3, "issues": [{"id": i} for i in ids]}
        iid = int(path.split("/issues/")[1].split(".json")[0])
        return {"issue": {900: issue, 1: reo, 2: still}[iid]}

    def git2(args):
        return fake_git(args) if any("#900" in a for a in args) else ""

    out = io.StringIO()
    rc = M.main(["issue", "900", "--json", "--events", str(events)], get=fake_get, git=git2, out=out)
    got = json.loads(out.getvalue())[0]
    check("issue --json", rc == 0 and got["tasks_by_state"] == {"완료": 2, "작업중": 1, "대기": 1}
          and got["rejections"] == {"total": 3, "by_kind": {"missing_note": 2, "unsettled_deps": 1}}
          and got["plan_sets"] == 1 and got["transitions"] == 11, str(got)[:400])
    out = io.StringIO()
    M.main(["issue", "900", "--events", str(events)], get=fake_get, git=git2, out=out)
    txt = out.getvalue()
    check("issue 표", "근거 충실도" in txt and "범위 이탈[근사]" in txt and "재개[근사]" in txt
          and "missing_note" in txt, txt)
    out = io.StringIO()
    M.main(["issue", "900", "--events", str(tmp / "없음.jsonl")], get=fake_get, git=git2, out=out)
    check("거절 기록 파일 없음은 N/A", "기록 없음" in out.getvalue())

    check("버전 페이지 넘김", M.fetch_version_issue_ids(19, get=fake_get, page=2) == [1, 2, 900]
          and len(pages) == 2, str(pages))
    out = io.StringIO()
    M.main(["baseline", "--version-id", "19", "--json"], get=fake_get, git=git2, out=out)
    got = json.loads(out.getvalue())
    check("baseline --json", got["aggregate"]["issues"] == 3 and "scope_drift" in got["na_for_baseline"])
    out = io.StringIO()
    M.main(["baseline", "--version-id", "19"], get=fake_get, git=git2, out=out)
    check("baseline 표에 N/A 명시", "기준선 N/A" in out.getvalue())
    out = io.StringIO()
    M.main(["compare", "--version-id", "19", "--issues", "900", "--events", str(events)],
           get=fake_get, git=git2, out=out)
    check("compare 표", "기준선:" in out.getvalue() and "플랜  :" in out.getvalue())
    out = io.StringIO()
    M.main(["compare", "--version-id", "19", "--issues", "900", "--json", "--events", str(events)],
           get=fake_get, git=git2, out=out)
    got = json.loads(out.getvalue())
    check("compare --json", got["plan"]["aggregate"]["issues"] == 1
          and got["baseline"]["aggregate"]["issues"] == 3)

    # 깨진 플랜 본문도 계측은 돈다
    broken = dict(issue, description="<!-- ax:plan:begin v=1 -->\n|x|\n")
    m = M.issue_metrics(broken, commits=[], events=None, statuses=STATUSES)
    check("깨진 플랜은 오류만 싣는다", not m["has_plan"] and m["plan_error"] and m["transitions"] == 11)


if __name__ == "__main__":
    run()
    total = PASS + FAIL
    if FAIL:
        print(f"FAIL test_plan_metrics: {PASS}/{total} 통과")
        sys.exit(1)
    print(f"OK test_plan_metrics: {PASS}/{total} 통과")
