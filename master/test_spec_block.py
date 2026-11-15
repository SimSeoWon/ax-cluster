"""스펙 영역(`#960` T3) 계약 테스트 — [중요] **파급 측정 전에는 못 쓰고, 본문 원문은 그대로인가.**

실행: .venv/bin/python master/test_spec_block.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import interview as IV               # noqa: E402
from master import interview_categories as IC    # noqa: E402
from master import plan_block as PB              # noqa: E402
from master import plan_start as ST              # noqa: E402
from master import spec_block as SB              # noqa: E402
from master.test_interview import FakeIssue      # noqa: E402

PASS = FAIL = 0
CATS = IC.load()
SIX = ("### 문제·맥락\n\n왜\n\n### 초반 분류\n\n신규\n\n### 관측 결과\n\n명령\n\n"
       "### 범위·비범위\n\n안 함\n\n### 완료 조건\n\n검사\n\n### 열린 결정\n\n없음")
ORIGINAL = "## 요청\n\n사용자가 쓴 원문 — `백틱` 과 표\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


FakeSpecIssue = FakeIssue                          # #963 T9 — 공용 픽스처가 update 를 갖는다


def _raises(fn, needle: str, exc=IV.InterviewError) -> bool:
    try:
        fn()
    except exc as e:
        return needle in str(e)
    return False


def _run(fi, steps):
    for s, c in steps:
        IV.record(1, s, "결과", "맞다", category=c, getter=fi.get, noter=fi.note, cats=CATS)


def _write(fi, content=SIX, answer="승인"):
    return IV.write_spec(1, content, answer, getter=fi.get, updater=fi.update, cats=CATS)


def test_block_format():
    check("없으면 None", SB.parse(ORIGINAL) is None)
    b = SB.put(ORIGINAL, SIX)
    check("원문 보존(앞부분 글자 그대로)", b.startswith(ORIGINAL.rstrip("\n")))
    check("영역 안 글", SB.parse(b) == SIX)
    check("여섯 항목 다 있음", SB.missing(SB.parse(b)) == [])
    b2 = SB.put(b, SIX.replace("왜", "고친 이유"))
    check("다시 쓰면 안만 바뀐다", b2.startswith(ORIGINAL.rstrip("\n")) and "고친 이유" in SB.parse(b2)
          and b2.count("ax:spec:begin") == 1)
    crlf = ORIGINAL.replace("\n", "\r\n")
    check("CRLF 본문은 CRLF 유지", "\n" not in SB.put(crlf, SIX).replace("\r\n", ""))
    check("누락 항목 보고", SB.missing("### 문제\n\nx") == ["triage", "observe", "scope", "done", "open"])
    check("표지 주입 거절", _raises(lambda: SB.put(ORIGINAL, SIX + "\n<!-- ax:plan:end -->"), "표지", SB.SpecError))
    check("깨진 태그 거절", _raises(lambda: SB.parse("<!-- ax:spec:begin v=1 -->"), "한 쌍", SB.SpecError))
    planned = PB.append(ORIGINAL, [PB.Task("T1", "대기", "목표")])
    b3 = SB.put(planned, SIX)
    check("플랜이 있으면 그 앞에 끼운다", b3.index("ax:spec:begin") < b3.index("## 플랜") < b3.index("ax:plan:begin"),
          b3)
    check("플랜은 그대로 파싱", PB.parse(b3).tasks[0].id == "T1")
    check("플랜 판정은 스펙 영역 제목도 센다", ST.spec_missing(SB.put("본문\n", SIX)) == [])


def test_write_only_after_impact():
    fi = FakeSpecIssue(body=ORIGINAL)
    check("분류 전 거절", _raises(lambda: _write(fi), "모든 단계 뒤"))
    _run(fi, [("classify", "feature"), ("investigate", ""), ("specify", "")])
    check("파급 측정 전 거절", _raises(lambda: _write(fi), "파급 측정"))
    _run(fi, [("impact", "")])
    check("빈 승인 거절", _raises(lambda: _write(fi, answer=" "), "사용자 답이 비었다"))
    check("항목 누락 거절", _raises(lambda: _write(fi, content="### 문제\n\nx"), "빠진 것"))
    check("거절은 본문을 안 바꾼다", fi.body == ORIGINAL)
    out = _write(fi)
    check("파급 측정 뒤 기록", out["ok"] and not out["replaced"] and out["next"] == "plan", str(out))
    check("원문 보존", fi.body.startswith(ORIGINAL.rstrip("\n")))
    check("노트 표지", fi.journals[-1]["notes"].startswith("[ax:interview-spec v=1]"))
    check("스펙 노트는 단계 상태를 흐리지 않는다", IV.state_of(fi.journals, CATS).problems == [])
    st = IV.status(1, getter=fi.get, cats=CATS)
    check("상태에 spec_exists", st["spec_exists"] and st["next"] == "spec", str(st))
    check("스펙 뒤 단계 기록 거절", _raises(
        lambda: IV.record(1, "impact", "r", "a", getter=fi.get, noter=fi.note, cats=CATS), "스펙 영역이 이미"))
    out = _write(fi, content=SIX.replace("없음", "하나 남음"))
    check("스펙 다시 쓰기 = 갱신", out["replaced"] and "하나 남음" in SB.parse(fi.body))
    planned = FakeSpecIssue(body=PB.append(ORIGINAL, [PB.Task("T1", "대기", "목표")]),
                            notes=[j["notes"] for j in fi.journals])
    check("플랜 있으면 거절", _raises(lambda: _write(planned), "플랜 영역이 이미"))


def main() -> int:
    for fn in (test_block_format, test_write_only_after_impact):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_spec_block: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
