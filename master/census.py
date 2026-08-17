"""원전 인용 census — **재실행 가능한 절차** (#177/#178, 소 4.3.1).

리포트 14 §1 의 측정(2026-08-13: 원전 74파일/23,710줄 인용 0)을 일회성 grep 이 아니라
언제든 다시 돌리는 도구로 남긴다. `sigma_audit.py` 와 같은 자리 — 감사 도구는 `master/` 에,
순수 stdlib 로, 판정 없이 **셀 수 있는 것만** 센다.

## 사용

    python3 master/census.py                     전체 census — 인용 0 목록·필독 4종 상태
    python3 master/census.py <원전파일명> ...     만들기 전에: 그 파일이 우리 저장소에 언급됐나

## [중요] 이 지표는 양방향으로 틀린다 — 상한이지 손실량이 아니다 (리포트 14 §1)

    인용됨 ≠ 읽음      원전 docs/ 8종은 전부 인용됐지만 그중 4종은 "미독"이라 적힌 문장이었다
    인용 0 ≠ 미이식    logic_lifecycle.py 는 인용 0인데 verify_task/submit_fail 로 실제 이식됨
    파일 수 ≠ 개념 수  인용 0의 상당수가 원전 내부 facade 리팩터링 산물(개념 중복)

그래서 이 도구는 «미이식» 딱지를 붙이지 않는다 — **"읽은 흔적 없음의 후보"** 목록을 줄 뿐이고,
결론을 걸 파일은 반드시 실물을 열어 확인한다(리포트 14 가 상위 4건에 그렇게 했다).

## [주의] 리포트 14 원방법과 딱 한 곳이 다르다 — 경계 보정

원방법은 basename 부분 문자열 계수였는데, 그러면 `server.py` 가 `http_server.py` 에도 걸린다
(과대 계수 — 인용 0 을 놓치는 방향이라 더 나쁘다). 여기서는 앞이 식별자 문자가 아닐 때만
센다(`/` 뒤는 인정, `_` 뒤는 거부). 기준선 74/23,710 과 수가 다르면 이 보정이 첫 용의자다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ORIGIN = Path.home() / "AgentTest"
REPO = Path(__file__).resolve().parent.parent
EXTRA_CORPUS = (Path.home() / "claude-workspace" / "reports",)

# 리포트 14 §1 과 같은 제외 (원전 쪽: tests·plan_archive·history)
ORIGIN_SKIP_DIRS = {"tests", "plan_archive", "history", ".git", "__pycache__", "node_modules"}
ORIGIN_EXTS = {".py", ".md"}
# 코퍼스 쪽: .git · ModularStage(트윈/게임) · .venv 제외 — 리포트 14 §1 과 동일
CORPUS_SKIP_DIRS = {".git", ".venv", "ModularStage", "__pycache__", "node_modules"}
CORPUS_EXTS = {".md", ".py", ".yaml", ".yml", ".json", ".service", ".timer", ".path"}

# [중요] M4 가 "가장 아프다"고 판정한 필독 4종 (CLAUDE.md 의 목록과 같은 것) —
#    census 를 돌릴 때마다 이들의 인용 상태를 따로 보여준다.
MUST_READS = (
    "local_llm_distributed_workers_plan_v5.0.md",
    "AGENTS.md",
    "audit_matrix.md",
    "plan_completed_v4.5.md",
)


def origin_files(root: Path = ORIGIN) -> list:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in ORIGIN_EXTS:
            continue
        if any(part in ORIGIN_SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return out


def corpus_text(repo: Path = REPO, extra=EXTRA_CORPUS) -> str:
    chunks = []
    roots = [repo] + [x for x in extra if x.is_dir()]
    for root in roots:
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in CORPUS_EXTS:
                continue
            if any(part in CORPUS_SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(chunks)


def count_citation(corpus: str, basename: str) -> int:
    """앞이 식별자 문자([A-Za-z0-9_])가 아닐 때만 센다 — `http_server.py` 가
    `server.py` 로 잡히는 과대 계수를 막는다 (`/` 뒤·행 첫머리·공백 뒤는 인정)."""
    return len(re.findall(r"(?<![A-Za-z0-9_])" + re.escape(basename), corpus))


def run_census(*, origin: Path = ORIGIN, repo: Path = REPO, extra=EXTRA_CORPUS) -> dict:
    corpus = corpus_text(repo, extra)
    cited, uncited = [], []
    for p in origin_files(origin):
        n = count_citation(corpus, p.name)
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").count("\n") + 1
        except OSError:
            lines = 0
        rel = str(p.relative_to(origin))
        (cited if n else uncited).append({"file": rel, "lines": lines, "citations": n})
    must = {}
    for name in MUST_READS:
        must[name] = count_citation(corpus, name)
    return {"cited": cited, "uncited": uncited, "must_reads": must}


def main(argv) -> int:
    if not ORIGIN.is_dir():
        print(f"[중요] 원전이 없다: {ORIGIN} — census 를 돌릴 수 없다")
        return 1

    if argv:                       # 만들기 전에 — 특정 원전 파일의 인용 확인
        corpus = corpus_text()
        rc = 0
        for a in argv:
            name = Path(a).name
            n = count_citation(corpus, name)
            hits = [p for p in origin_files() if p.name == name]
            if not hits:
                print(f"[주의] {name}: 원전에 그런 파일이 없다 (제외 디렉토리 안일 수도)")
                rc = 1
                continue
            mark = "[완료]" if n else "[중요]"
            print(f"{mark} {name}: 인용 {n}회"
                  + ("" if n else " — 읽은 흔적 없음의 후보. 만들기 전에 실물을 연다: "
                     + " · ".join(str(h) for h in hits[:3])))
        return rc

    got = run_census()
    un, ct = got["uncited"], got["cited"]
    un_lines = sum(x["lines"] for x in un)
    print(f"원전 대상 {len(un) + len(ct)}파일 — 인용 0: {len(un)}파일 {un_lines:,}줄 · "
          f"인용 있음: {len(ct)}파일")
    print("(기준선 2026-08-13: 74파일/23,710줄 — 리포트 14 §1. "
          "수가 다르면 경계 보정(모듈 머리말)이 첫 용의자)")
    print("\n[중요] 필독 4종 인용 상태 (0 이면 그 문서의 교훈이 새 작업에 안 실리고 있다):")
    for name, n in got["must_reads"].items():
        print(f"  {'[완료]' if n else '[중요]'} {name}: {n}회")
    top = sorted(un, key=lambda x: -x["lines"])[:15]
    if top:
        print("\n인용 0 상위 (줄수 순, 15건) — «미이식» 딱지가 아니라 **열어 볼 후보**다:")
        for x in top:
            print(f"  {x['lines']:>6,}줄  {x['file']}")
    print("\n[주의] 이 지표는 양방향으로 틀린다 — 인용됨≠읽음 · 인용0≠미이식 · 파일수≠개념수."
          "\n     상한이지 손실량이 아니다. 결론을 걸 파일은 실물을 열어 확인한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
