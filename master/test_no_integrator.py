"""🔴 통합자가 되살아나면 여기서 막는다 (사용자 지시 2026-09-03, 3일째 반복).

메모리·문서는 내가 무시하면 그만이다. **기계가 막아야 한다** — 오늘 나를 실제로 멈춰 세운
것은 `pre-push` 훅이었고(미병합 브랜치 삭제를 거부하고 사람에게 넘겼다), 메모리가 아니었다.

계약 셋:

    ① 마스터에 「통합자」를 고르거나 부르는 코드가 **없다**
    ② 마스터가 UE5 빌드를 부르는 자리는 **골조 게이트와 `.33` 검수 둘뿐**이다
    ③ 조각 종결 통보가 **git·빌드에 묶여 있지 않다** — 큐 루트가 git 이 아니어도 나간다

정본: 조각이 전부 끝나면 `.33` 에 공지하고, `.33` 이 **서브 브랜치를 전부 머지해 한 곳에서
한 번** 검사한 뒤 `main` 에 올릴지 판단한다. 조각 단위 통과 도장은 값이 없다.

`.venv/bin/python master/test_no_integrator.py`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # master/
PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _py_files():
    """`master/` 의 프로덕션 파이썬. 테스트는 뺀다 — 테스트는 이름을 인용해도 된다."""
    for p in sorted(ROOT.rglob("*.py")):
        if p.name.startswith("test_") or "__pycache__" in p.parts:
            continue
        yield p


def _code_lines(p: Path):
    """주석·독스트링 줄을 뺀 대략의 실코드. [주의] 완벽한 파서가 아니다 —
    목적은 **이름이 코드로 되살아난 것**을 잡는 것이고, 설명 주석은 남겨 둬야 한다
    (지운 이유를 적어 두는 것이 다음 사람에게 필요하다)."""
    out = []
    in_doc = False
    for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        s = ln.strip()
        ticks = s.count('"""') + s.count("'''")
        if in_doc:
            if ticks:
                in_doc = False
            continue
        if s.startswith('"""') or s.startswith("'''"):
            if ticks < 2:
                in_doc = True
            continue
        if s.startswith("#") or not s:
            continue
        out.append((i, ln.split("#")[0]))
    return out


# ── ① 통합자를 고르거나 부르는 코드가 없다 ──────────────────────────────────────

BANNED = ("pick_integrator", "run_auto", "integrate_now",
          "_do_auto_cleanup", "_run_integration_build")


def test_no_integrator_symbol_survives() -> None:
    hits = []
    for p in _py_files():
        for lineno, ln in _code_lines(p):
            for name in BANNED:
                if name in ln:
                    hits.append(f"{p.relative_to(ROOT.parent)}:{lineno} {name}")
    check("[중요] 통합자 심볼이 코드에 없다", not hits, " · ".join(hits[:6]))


def test_integrate_run_has_no_caller() -> None:
    """`integrate.run` 은 통합자 본체다. **아무도 부르지 않아야 한다.**

    [주의] 모듈 파일 자체는 아직 남아 있다(약 1,000줄) — 처분은 미결이고, 그래서
    「배선이 끊겨 있다」를 여기서 지킨다.
    """
    pat = re.compile(r"\bintegrate\.run\s*\(|\bIG\.run\s*\(")
    hits = []
    for p in _py_files():
        for lineno, ln in _code_lines(p):
            if pat.search(ln):
                hits.append(f"{p.relative_to(ROOT.parent)}:{lineno}")
    check("[중요] integrate.run 호출자 0", not hits, " · ".join(hits[:6]))


# ── ② 마스터는 UE5 빌드를 부르지 않는다 (두 예외만) ─────────────────────────────

BUILD_CALLERS_ALLOWED = {
    "master/work/skeleton_gate.py",   # 골조 UHT 게이트 — 파견 **전**, 통합과 무관
    "master/work/build_local.py",     # `.33` 검수가 쓰는 로컬 빌드 팩토리
    "master/work/review.py",          # `.33` 의 검수·통합 빌드 — **여기가 맞는 자리**
    "master/layer3_verify.py",        # 빌드 실행기 자체 (호출자가 아니라 구현)
    "master/client/uproject.py",      # 배달 도구
}


def test_master_does_not_build() -> None:
    pat = re.compile(r"run_build_on_workshop\s*\(|run_build_local\s*\(")
    hits = []
    for p in _py_files():
        rel = str(p.relative_to(ROOT.parent))
        if rel in BUILD_CALLERS_ALLOWED:
            continue
        for lineno, ln in _code_lines(p):
            if pat.search(ln):
                hits.append(f"{rel}:{lineno}")
    check("[중요] 허용된 둘 밖에서 UE5 빌드를 부르지 않는다", not hits, " · ".join(hits[:6]))


# ── ③ 공지가 git·빌드에 묶여 있지 않다 ──────────────────────────────────────────

def test_notify_is_not_gated_on_git_or_build() -> None:
    """🔴 **이것이 교착의 원인이었다** (실측 2026-09-03 22:38:59).

    완료 공지가 `_do_auto_cleanup` 안에 묻혀 있었고, 그 함수는 큐 루트가 git 저장소가
    아니면 초입에서 반환했다 — `[auto-cleanup] … 스킵 — git repo 없음`. 조각 4/4 가
    성공해도 `.33` 은 끝난 줄 몰랐다.
    """
    src = (ROOT / "task_queue" / "logic_cleanup.py").read_text(encoding="utf-8")
    i = src.find("def _auto_cleanup_work_async(")
    check("공지 진입점이 있다", i != -1)
    if i == -1:
        return
    j = src.find("\ndef ", i + 10)
    body = src[i: j if j != -1 else len(src)]
    for bad, why in ((".git", "git 저장소 존재 검사"),
                     ("_git(", "git 명령"),
                     ("build", "빌드")):
        check(f"공지 경로에 {why}가 없다", bad not in body,
              f"`{bad}` 가 _auto_cleanup_work_async 안에 있다")
    check("공지 경로가 이슈 생성을 부른다",
          "_try_create_review_issue_async" in body)


# ── ④ 통보 본문이 확인하지 않은 것을 통과로 적지 않는다 ─────────────────────────

def test_notice_does_not_claim_a_build_it_never_ran() -> None:
    """[주의] 원전 문구는 `통합 빌드: 통과` 를 **무조건** 찍었다 — 아무도 빌드하지 않았는데
    통과라고 적는 거짓말이고, 사용자가 그것을 「눈속임」이라 불렀다."""
    src = (ROOT / "task_queue" / "logic_cleanup.py").read_text(encoding="utf-8")
    code = "\n".join(ln for _, ln in _code_lines(ROOT / "task_queue" / "logic_cleanup.py"))
    check("[중요] 「통합 빌드: 통과」를 찍지 않는다", "통합 빌드:" not in code,
          "본문이 빌드 결과를 주장한다")
    check("[중요] 「검증 통과」를 주장하지 않는다", "검증 통과" not in code,
          "조각 종결을 검증으로 적는다")
    check("아직 검증되지 않았음을 명시한다", "아직 아무것도 검증되지 않았다" in src)
    # [주의] 문구는 2026-09-04 에 바뀌었다 — 정본 ⑺ 이 `ax-advance`(작업 브랜치 전진)로
    #    갈리면서 본문이 「전부 작업 브랜치에 머지 → 한 번 통합 빌드」로 다시 쓰였다.
    #    검사하는 것은 **문장이 아니라 계약**이다: 전부 모아서 · 한 번 · 작업 브랜치에.
    check("전부 모아 한 번 검사하라고 적는다",
          "전부 작업 브랜치에 머지한다" in src and "한 번 통합 빌드한다" in src)
    check("[중요] main 단계가 아니라고 못박는다", "`main` 에 올리는 단계가 아니다" in src)
    check("[중요] ax-advance 를 가리킨다 (ax-review 가 아니다)", "`ax-advance`" in src)


def main() -> int:
    for fn in (test_no_integrator_symbol_survives,
               test_integrate_run_has_no_caller,
               test_master_does_not_build,
               test_notify_is_not_gated_on_git_or_build,
               test_notice_does_not_claim_a_build_it_never_ran):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_no_integrator: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
