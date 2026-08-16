"""프로젝트 코드 규약 (소 3.5.7) — [중요] **프로젝트 문서가 SSOT 임을 못박는다.**

리포트 14 §14.5 에서 드러난 것: 프로젝트 미러의 `repo/CLAUDE.md` 가 우리 저장소에서 **인용 0회**
였는데 이식 설계의 절반을 갖고 있었고, 그중 「Code conventions」 를 **매니페스트가 전혀 나르지
않았다**(도메인 규범만 실었다).

[주의] 베껴 두면 어긋나므로 **읽어서** 싣는다. 이 테스트가 지키는 것 둘:
  ① UE 금지 3종은 프로젝트 문서와 무관하게 **항상** 실린다 (판단 사항이 아니다)
  ② 프로젝트 절은 **읽어서** 실린다 — 하드코딩 사본이 아니다 (파일을 바꾸면 결과가 바뀐다)

`.venv/bin/python master/test_conventions.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import conventions as C      # noqa: E402

PASS = FAIL = 0

DOC = """# CLAUDE.md

## Targets and modules

빌드 대상은 하나다.

## Code conventions

- 주석은 한국어로 쓴다.
- `IsValid(X)` 를 쓴다.

## Commit conventions

여기는 실리지 않아야 한다.
"""


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_extract_section_is_bounded():
    got = C.extract_section(DOC, "Code conventions")
    check("절을 찾는다", "주석은 한국어" in got, got[:60])
    check("[중요] 다음 헤딩에서 끊는다 (파일 끝까지 삼키지 않는다)",
          "실리지 않아야" not in got, got[-60:])
    check("앞 절도 안 섞인다", "빌드 대상" not in got)
    check("없는 절은 빈 문자열", C.extract_section(DOC, "No Such") == "")
    check("빈 입력도 빈 문자열", C.extract_section("", "Code conventions") == "")


def test_ue_prohibitions_always_present():
    with tempfile.TemporaryDirectory() as td:
        body, note = C.bundle(Path(td))          # CLAUDE.md 없음
        check("[중요] 문서가 없어도 UE 금지는 실린다", "리네이밍하지 않는다" in body, body[:80])
        check("상속 구조 금지도 실린다", "상속 구조를 바꾸지 않는다" in body)
        check("모듈 간 이동 금지도 실린다", "모듈 간으로 코드를 옮기지 않는다" in body)
        check("판단 사항이 아니라고 못박는다", "판단 사항이 아니다" in body)
        check("[주의] 문서 부재가 note 로 보고된다", bool(note) and "CLAUDE.md" in note, note)


def test_project_section_is_read_not_hardcoded():
    """[중요] 파일을 바꾸면 결과가 바뀌어야 한다 — 사본이면 안 바뀐다."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "CLAUDE.md"
        p.write_text(DOC, encoding="utf-8")
        body, note = C.bundle(Path(td))
        check("프로젝트 절이 실린다", "`IsValid(X)` 를 쓴다" in body, body[-200:])
        check("SSOT 라고 표시한다", "프로젝트가 SSOT" in body)
        check("정상이면 note 가 없다", not note, note)

        p.write_text(DOC.replace("`IsValid(X)` 를 쓴다", "규약이 바뀌었다"), encoding="utf-8")
        body2, _ = C.bundle(Path(td))
        check("[중요] 파일을 바꾸면 결과가 바뀐다 (하드코딩 사본이 아니다)",
              "규약이 바뀌었다" in body2 and "`IsValid(X)`" not in body2, body2[-120:])


def test_missing_section_is_reported():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "CLAUDE.md").write_text("# x\n\n## Other\n\n내용\n", encoding="utf-8")
        body, note = C.bundle(Path(td))
        check("절이 없으면 note 로 보고한다", bool(note) and "절을 찾지 못했다" in note, note)
        check("그래도 UE 금지는 실린다", "리네이밍하지 않는다" in body)


def main() -> int:
    for fn in (test_extract_section_is_bounded, test_ue_prohibitions_always_present,
               test_project_section_is_read_not_hardcoded, test_missing_section_is_reported):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_conventions: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
