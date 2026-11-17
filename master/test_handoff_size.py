"""인수인계서 길이 가드 (`#842`) — `docs/orchestrator-handoff.md` 는 한 벌로 덮어쓴다.

2026-10-21 에 2,506줄(338KB)까지 쌓여 한 번에 읽히지 않았다. 원인은 세션마다 새 체크포인트를
위에 쓰고 직전 것을 「이전 체크포인트」로 내려 남긴 것이고, 「한 벌만 유지」(`docs/15` §15.3)는
문장뿐이라 아무도 막지 않았다. 그래서 코드가 막는다.

재는 것:
  ① 줄 수가 상한 이하
  ② 「이전 체크포인트」 항목이 없다 — 쌓는 갱신의 흔적
  ③ `AGENTS.md` 가 가리키는 「바로 다음 작업」 절이 있다
  ④ 가드가 실제로 잡는다 — 옮겨 둔 옛 원문(history)을 넣으면 실패한다
  ⑤ 끝난 일감의 절·표·목록을 쌓지 않는다 (`#975`) — 줄 수와 별도로 검사한다

`.venv/bin/python master/test_handoff_size.py` (venv 없이 `python3` 도 된다)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs" / "orchestrator-handoff.md"
HISTORY = ROOT / "docs" / "orchestrator-handoff-history.md"
MAX_LINES = 500
STACKED = re.compile(r"^\s*-\s*\*\*이전 체크포인트", re.M)
NEXT_STEP = re.compile(r"^#{2,3}\s*바로 다음 작업", re.M)
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
ISSUE = re.compile(r"(?<![\w#])#(\d+)\b")
CLOSED = re.compile(r"(?:마감|완료)(?!\s*(?:예정|대기|전|후|뒤|필요|여부|조건|기준))")
HISTORY_TITLE = re.compile(
    r"(?:최근|직전|이전|지난)\s*(?:마감|완료)|(?:마감|완료)\s*(?:이력|목록|내역|현황|상태|결과)"
)
ENTRY = re.compile(r"^\s*(?:[-+*]\s+|\d+[.)]\s+|\|)")
ISSUE_ENTRY = re.compile(r"^\s*(?:[-+*]\s+|\d+[.)]\s+|\|)\s*#\d+\b")
CLOSED_STATUS = re.compile(r"(?:마감\s+)?(?:완료|마감)(?=\s*(?:$|[|·,.(]))")

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


def closed_history(text: str) -> list[str]:
    """번호만 세지 않는다: 마감 절의 반복 또는 이력 절의 표·목록을 센다.

    이력 제목은 첫 표·목록 블록에 적용하고, 그 밖에서는 일감 바로 뒤 또는 표의 독립
    셀에 명시된 완료 상태를 요구한다. 설명문·코드 펜스의 예시는 세지 않는다.
    """
    out: list[str] = []
    closed_sections: set[str] = set()
    entries: set[str] = set()
    history_level = 0
    fence = ""

    def flush() -> None:
        if len(entries) >= 2:
            out.append(f"끝난 일감 누적: 표·목록 {len(entries)}건 — 지난 내용은 reports/·Redmine 노트로")
        entries.clear()

    for line in text.splitlines():
        stripped = line.lstrip()
        if fence:
            if re.fullmatch(re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", stripped):
                fence = ""
            continue
        opening = re.match(r"(`{3,}|~{3,})", stripped)
        if opening:
            fence = opening.group(1)
            continue
        heading = HEADING.match(line)
        if heading:
            flush()
            level, title = len(heading.group(1)), heading.group(2)
            if history_level and level <= history_level:
                history_level = 0
            if HISTORY_TITLE.search(title):
                history_level = level
            if CLOSED.search(title):
                closed_sections.update(ISSUE.findall(title))
            continue
        # 이력 표·목록 뒤의 별도 문단은 같은 절에 있어도 잔여 관측 등일 수 있다.
        if history_level and entries and not ENTRY.match(line) and not line.startswith("  "):
            flush()
            history_level = 0
        if ISSUE_ENTRY.match(line):
            status = re.sub(r"^\s*(?:[-+*]\s+|\d+[.)]\s+|\|)\s*#\d+\s*[:：|]?\s*", "", line)
            explicit = CLOSED_STATUS.match(status) or (
                line.lstrip().startswith("|") and any(CLOSED_STATUS.fullmatch(cell.strip())
                                                     for cell in line.split("|") if cell.strip()))
            if history_level or explicit:
                entries.update(ISSUE.findall(line))
    flush()
    if len(closed_sections) >= 2:
        out.append(f"끝난 일감 누적: 마감 절 {len(closed_sections)}건 — 현재 체크포인트 한 벌로 덮어쓴다")
    return out


def problems(text: str) -> list[str]:
    out = []
    n = text.count("\n") + (0 if text.endswith("\n") else 1)
    if n > MAX_LINES:
        out.append(f"{n}줄 > 상한 {MAX_LINES} — 덮어써서 줄이고 지난 내용은 reports/·Redmine 노트로")
    k = len(STACKED.findall(text))
    if k:
        out.append(f"「이전 체크포인트」 {k}개 — 쌓지 말고 덮어쓴다")
    if not NEXT_STEP.search(text):
        out.append("「바로 다음 작업」 절 없음 — AGENTS.md 가 이 절을 가리킨다")
    out.extend(closed_history(text))
    return out


def test_current_handoff() -> None:
    p = problems(HANDOFF.read_text(encoding="utf-8"))
    check("현재 인수인계서가 상한·형식을 지킨다", not p, " · ".join(p))


def test_guard_catches_stacked_history() -> None:
    if not HISTORY.exists():
        check("옛 원문이 있다(가드 실측용)", False, str(HISTORY))
        return
    p = problems(HISTORY.read_text(encoding="utf-8"))
    check("🔴 옛 원문(2,506줄)은 줄 수로 걸린다", any("상한" in x for x in p), " · ".join(p))
    check("🔴 옛 원문은 「이전 체크포인트」로 걸린다", any("이전 체크포인트" in x for x in p), " · ".join(p))


def test_small_cases() -> None:
    ok = "# 현재 AX 작업 인수인계\n\n## 바로 다음 작업\n\n1. 대조\n"
    check("짧은 정상본 → 통과", not problems(ok), " · ".join(problems(ok)))
    check("「바로 다음 작업」 빠짐 → 걸린다", problems("# 현재\n\n## 상태\n"))
    check("쌓인 항목 한 개 → 걸린다", problems(ok + "\n- **이전 체크포인트: 어제**\n"))
    check("상한 초과 → 걸린다", problems(ok + "x\n" * MAX_LINES))


def test_closed_history() -> None:
    ok = "# 현재 AX 작업 인수인계\n\n## 바로 다음 작업\n\n1. 대조\n"
    bad = {
        "마감 절 반복": "## #970 마감\n결과\n## 직전 마감 — #969 완료\n결과\n",
        "최근 마감 표": "## 최근 마감\n| 일감 | 결과 |\n|---|---|\n| #970 | 수정 |\n| #969 | 수정 |\n",
        "완료 목록": "## 완료 내역\n- #970 수정\n1. #969 수정\n",
        "명시 완료 상태 목록": "## 상태\n- #970: 마감 완료\n- #969: 완료\n",
        "명시 완료 상태 표": "## 상태\n| #970 | 완료 |\n| #969 | 마감 |\n",
        "한 행에 여러 마감": "## 이번 세션 마감 상태\n- #211: 해시 · #979: 해시\n",
    }
    for name, body in bad.items():
        p = problems(ok + body)
        check(name + " → 누적으로 걸린다", any("끝난 일감 누적" in x for x in p), " · ".join(p))
    good = {
        "정상 작업 참조": "## 진행 중 작업\n- #975 진행 중\n- #978 진행 중\n## 미해결 사항\n- #970 미확인\n- #969 완료 여부 미확인\n",
        "다음 작업의 마감 계획": "- #975 마감 후 확인\n- #978 완료 예정\n",
        "이미 끝난 작업의 미해결 사항": "## 마감 뒤 남은 확인 거리\n- #970: 합성 미확인\n- #969: 배달 필요\n",
        "번호만 있는 표": "## 관련 일감\n| #970 | 참고 |\n| #969 | 참고 |\n",
        "한 일감 체크포인트": "## #975 마감\n- #975 완료\n",
        "동일 일감 반복": "## 최근 마감\n- #975 결과\n- #975 근거\n",
        "이력 절 밖의 참조": "## 최근 마감\n지난 내용은 Redmine으로\n## 미해결 사항\n- #970 확인 필요\n- #969 확인 필요\n",
        "코드 펜스의 예시": "```markdown\n## #970 마감\n## #969 완료\n```\n",
        "실제 정상 판의 설명문": "## 남은 관측\n- #964·#966 배포 후 관측(C6): 완료 주차 재생성 없음\n- 인계서는 한 벌로 덮어쓰며 이전 완료 내역을 누적하지 않는다(#842, 상한 150줄).\n",
        "이력 표 뒤 잔여 관측": "## 최근 마감\n| #975 | 결과 |\n\n- #964·#966 배포 후 관측(C6): 완료 주차 재생성 없음\n- #383 미실측: 실합성\n",
    }
    for name, body in good.items():
        p = problems(ok + body)
        check(name + " → 통과", not p, " · ".join(p))


def test_line_boundary() -> None:
    prefix = "# 현재\n## 바로 다음 작업\n"
    for trailing in (True, False):
        for n in (500, 501):
            text = prefix + "내용\n" * (n - 2)
            if not trailing:
                text = text.rstrip("\n")
            p = problems(text)
            check(f"{n}줄 · 마지막 개행 {trailing}", bool(p) == (n > 500), " · ".join(p))
    check("길이 상한은 500", MAX_LINES == 500, MAX_LINES)


def main() -> int:
    test_current_handoff()
    test_guard_catches_stacked_history()
    test_small_cases()
    test_closed_history()
    test_line_boundary()
    print(f"{'OK' if not FAIL else 'FAIL'} test_handoff_size: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
