"""착수 전 인터뷰 단계 기록(`#960` T2) 계약 테스트 — [중요] **과정을 건너뛰면 거절되는가.**

실행: .venv/bin/python master/test_interview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import interview as IV               # noqa: E402
from master import interview_categories as IC    # noqa: E402
from master import plan_block as PB              # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class FakeIssue:
    """Redmine 한 건 — 노트는 시간순으로 쌓인다."""

    def __init__(self, body: str = "## 문제\n\n본문\n", notes: list | None = None):
        self.body = body
        self.journals = [{"notes": n, "created_on": f"t{i}"} for i, n in enumerate(notes or [])]
        self.fail_write = False

    def get(self, issue_id):
        return {"id": issue_id, "description": self.body, "journals": list(self.journals)}

    def note(self, issue_id, notes):
        if self.fail_write:
            return "[주의] 레드마인 갱신 실패"
        self.journals.append({"notes": notes, "created_on": f"t{len(self.journals)}"})
        return "레드마인 갱신"


CATS = IC.load()


def _rec(fi: FakeIssue, step: str, cat: str = "", result: str = "결과", answer: str = "맞다"):
    return IV.record(1, step, result, answer, category=cat, getter=fi.get, noter=fi.note, cats=CATS)


def _raises(fn, needle: str) -> bool:
    try:
        fn()
    except IV.InterviewError as e:
        return needle in str(e)
    return False


def test_feature_full_flow_with_skip():
    fi = FakeIssue()
    st = IV.status(1, getter=fi.get, cats=CATS)
    check("처음엔 분류", st["next"] == "classify" and not st["category"], str(st))
    check("분류 목록이 문서에서", {c["name"] for c in st["categories"]} == {"bug", "modify", "feature"})
    out = _rec(fi, "classify", "feature")
    check("분류 뒤 조사", out["next"] == "investigate", str(out))
    _rec(fi, "investigate")
    out = _rec(fi, "specify")
    check("신규: 명세 뒤 재현 건너뜀 노트", out["written"] == ["specify", "reproduce(건너뜀)"], str(out["written"]))
    check("건너뜀 뒤 파급 측정", out["next"] == "impact", out["next"])
    check("건너뜀 노트 표지", "[ax:interview step=reproduce category=feature skipped=1 v=1]" in fi.journals[-1]["notes"])
    out = _rec(fi, "impact")
    check("다 거치면 스펙 영역", out["next"] == IV.SPEC, out["next"])
    st = IV.status(1, getter=fi.get, cats=CATS)
    check("노트에서 복원", st["done"] == ["classify", "investigate", "specify", "impact"]
          and st["skipped"] == ["reproduce"] and st["next"] == "spec", str(st))


def test_bug_has_reproduce():
    fi = FakeIssue()
    _rec(fi, "classify", "bug")
    _rec(fi, "investigate")
    out = _rec(fi, "specify")
    check("버그: 명세 뒤 재현", out["next"] == "reproduce" and out["written"] == ["specify"], str(out))
    check("버그: 재현 건너뛰고 파급 거절", _raises(lambda: _rec(fi, "impact"), "순서 건너뜀"))
    _rec(fi, "reproduce")
    check("재현 뒤 파급", IV.status(1, getter=fi.get, cats=CATS)["next"] == "impact")


def test_rejections():
    fi = FakeIssue()
    check("분류 전 조사 거절", _raises(lambda: _rec(fi, "investigate"), "분류가 먼저"))
    check("모르는 단계 거절", _raises(lambda: _rec(fi, "guess"), "모르는 단계"))
    check("모르는 분류 거절", _raises(lambda: _rec(fi, "classify", "port"), "분류 'port' 가 없다"))
    check("사용자 답 빈칸 거절", _raises(lambda: _rec(fi, "classify", "bug", answer="  "), "사용자 답이 비었다"))
    check("결과 빈칸 거절", _raises(lambda: _rec(fi, "classify", "bug", result=""), "결과가 비었다"))
    check("거절은 노트를 안 쓴다", fi.journals == [])
    _rec(fi, "classify", "feature")
    check("조사 건너뛰고 명세 거절", _raises(lambda: _rec(fi, "specify"), "순서 건너뜀"))
    check("적용 안 되는 재현 거절", _raises(lambda: _rec(fi, "reproduce"), "적용하지 않는다"))
    check("분류는 분류 단계에서만", _raises(lambda: _rec(fi, "investigate", "bug"), "분류 단계에서만"))
    planned = FakeIssue(body=PB.append("## 문제\n\n본문\n", [PB.Task("T1", "대기", "목표")]))
    check("플랜 있는 일감 거절", _raises(lambda: _rec(planned, "classify", "bug"), "플랜 영역이 이미"))


def test_redo_latest_wins_and_invalidates_later():
    fi = FakeIssue()
    for s, c in (("classify", "bug"), ("investigate", ""), ("specify", ""), ("reproduce", "")):
        _rec(fi, s, c)
    out = _rec(fi, "specify", result="고친 명세")
    check("명세 재기록 → 다음은 재현 다시", out["next"] == "reproduce", str(out))
    st = IV.state_of(fi.journals, CATS)
    check("재기록 뒤 재현 기록 무효", "reproduce" not in st.records)
    check("최신 명세가 기준", "고친 명세" in st.records["specify"].text)
    out = _rec(fi, "classify", "feature")
    check("분류 변경 → 처음부터", out["next"] == "investigate" and any("분류 변경" in x for x in out["log"]), str(out))
    check("분류 변경 뒤 상태", IV.state_of(fi.journals, CATS).category == "feature")


def test_resume_after_interrupt():
    fi = FakeIssue()
    _rec(fi, "classify", "modify")
    _rec(fi, "investigate")
    # 세션이 끊겼다 — 새 세션은 노트만 읽는다
    fresh = FakeIssue(notes=[j["notes"] for j in fi.journals] + ["사람이 남긴 일반 노트"])
    st = IV.status(1, getter=fresh.get, cats=CATS)
    check("중단 뒤 다음 단계 명세", st["next"] == "specify" and st["category"] == "modify", str(st))
    check("분류 문서 경로를 돌려준다", st.get("category_doc", "").endswith("category-modify.md"))


def test_write_failure_is_transport_error():
    fi = FakeIssue()
    fi.fail_write = True
    try:
        _rec(fi, "classify", "bug")
        ok = False
    except IV.InterviewTransportError:
        ok = True
    check("쓰기 실패는 전송 오류", ok)


def test_foreign_marks_ignored():
    notes = [IV.render("classify", "bug", result="r", user_answer="a"),
             "[ax:interview step=guess category=bug v=1]\nx",
             IV.render("investigate", "feature", result="r", user_answer="a")]
    st = IV.state_of([{"notes": n} for n in notes], CATS)
    check("모르는 표지·다른 분류는 무시", st.next == "investigate" and len(st.problems) == 2, str(st.as_dict()))


def main() -> int:
    for fn in (test_feature_full_flow_with_skip, test_bug_has_reproduce, test_rejections,
               test_redo_latest_wins_and_invalidates_later, test_resume_after_interrupt,
               test_write_failure_is_transport_error, test_foreign_marks_ignored):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_interview: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
