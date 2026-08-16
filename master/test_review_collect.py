"""소비자 review_collector + issue_classifier (#156) 계약 테스트.

재는 것 넷:
    ① 왕복          [중요] 생산자(review_gen)가 **실제로 쓴 파일**을 소비자가 읽는가 —
                    정규식 복사 검증이 아니라 실물 파일 왕복
    ② 파싱 규약     심각도 정규화 · 헤더/구분선 스킵 · since_date · `_` 접두 스킵 · 커밋 해시
    ③ 분류          코멘트([리뷰]) 제외 · 라인 버킷 중복 제거(최신 우선) · 반복 패턴(3파일+)
    ④ 빈 표 계약    위반 0건 리포트에서 이슈 0건 — 「(없음)」 쓰레기 이슈가 안 생긴다

실행: .venv/bin/python master/test_review_collect.py   (LLM 0 — chat 주입)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import review_gen as RG               # noqa: E402
from master.context_synth import issue_classifier as IC         # noqa: E402
from master.context_synth.review_collector import (             # noqa: E402
    ReviewIssue, _normalize_severity, parse_review_reports)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / "repo"
        self.ontology = root / "ontology"


def fixture():
    root = Path(tempfile.mkdtemp(prefix="ax-rc-"))
    p = P(root)
    p.repo.mkdir()
    subprocess.run(["git", "-c", "user.name=사람", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", "-C", str(p.repo), "init", "-q",
                    "-b", "main"], capture_output=True)
    src = p.repo / "Source" / "M"
    src.mkdir(parents=True)
    (src / "A.cpp").write_text("int F() { return 1; }\n", encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-c", "user.name=사람", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", "-C", str(p.repo), *args],
                       capture_output=True)
    return p


CANNED = """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|
| Source/M/A.cpp | 네이밍 | 접두사 b 누락 | 12 | 중간 |

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/A.cpp | 높음 | 3 | null 체크 누락 | IsValid 가드 |

## 3. 영향 분석
없음.
"""

EMPTY_TABLES = """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|

## 3. 영향 분석
영향 없음.
"""


# ── ① 실물 왕복 — 생산자가 쓴 파일을 소비자가 읽는다 ─────────

def test_producer_to_collector_roundtrip():
    p = fixture()
    commit = subprocess.run(["git", "-C", str(p.repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    r = RG.review_commit(p, commit, ["Source/M/A.cpp"], chat=lambda pr: CANNED)
    check("생산자가 썼다", bool(r.written) and r.format_ok, r.error or r.skipped)

    issues = parse_review_reports(Path(r.written).parent, "2000-01-01")
    check("[중요] 실물 왕복 — 소비자가 2건을 읽는다", len(issues) == 2, str(len(issues)))
    conv = next(i for i in issues if i.category == "convention")
    safe = next(i for i in issues if i.category == "safety")
    check("컨벤션 열 매핑 (항목:내용 → description, 라인 4열, 심각도 5열)",
          conv.description == "네이밍: 접두사 b 누락" and conv.line == "12"
          and conv.severity == "mid", f"{conv.description}|{conv.line}|{conv.severity}")
    check("안전성 열 매핑 (위험도 2열, 권장 수정 5열)",
          safe.severity == "high" and safe.recommendation == "IsValid 가드", str(safe))
    check("[중요] 커밋 해시가 리포트 머리에서 잡힌다 (전체 해시)",
          conv.commit_hash == commit, conv.commit_hash)
    check("모듈이 ### 절에서 온다", conv.module == "Source/M", conv.module)
    check("원본 리뷰 파일명이 남는다", conv.source_review.endswith(".md"))


def test_empty_tables_yield_zero_issues():
    """[중요] 위반 0건 리포트 → 이슈 0건. 「(없음)」 자리표시가 쓰레기 이슈를 만들던
    결함(생산자 발명)은 이 계약으로 재발을 막는다."""
    p = fixture()
    commit = subprocess.run(["git", "-C", str(p.repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    r = RG.review_commit(p, commit, ["Source/M/A.cpp"], chat=lambda pr: EMPTY_TABLES)
    check("빈 표도 형식 준수다 (재시도 없음)", r.format_ok and not r.retried,
          f"format_ok={r.format_ok} retried={r.retried}")
    issues = parse_review_reports(Path(r.written).parent, "2000-01-01")
    check("[중요] 이슈 0건 — 쓰레기 없음", issues == [], str(issues))


# ── ② 파싱 규약 ───────────────────────────────────────────────

def test_parse_conventions():
    check("심각도 정규화 — 높음/상/High → high",
          all(_normalize_severity(s) == "high" for s in ("높음", "상", "High")))
    check("심각도 정규화 — 중간/중/Medium → mid",
          all(_normalize_severity(s) == "mid" for s in ("중간", "중", "Medium")))
    check("모르는 값은 low (낮음/-/기타)",
          all(_normalize_severity(s) == "low" for s in ("낮음", "-", "?")))

    d = Path(tempfile.mkdtemp(prefix="ax-rc2-"))
    (d / "2026-08-10_0900_aaaa1111.md").write_text(
        "커밋: `aaaa1111`\n" + CANNED, encoding="utf-8")
    (d / "2026-08-16_0900_bbbb2222.md").write_text(
        "커밋: `bbbb2222`\n" + CANNED, encoding="utf-8")
    (d / "_health_report.md").write_text(CANNED, encoding="utf-8")
    got = parse_review_reports(d, "2026-08-15")
    check("[중요] since_date 필터 — 파일명 앞 10자 기준", len(got) == 2
          and all(i.commit_hash == "bbbb2222" for i in got), str(len(got)))
    check("[중요] `_` 접두 파일은 리뷰가 아니다 (_health_report 등)",
          all(i.source_review != "_health_report.md" for i in got))


# ── ③ 분류 — 제외·중복·패턴 ──────────────────────────────────

def mk(file="Source/M/A.cpp", line="10", cat="safety", sev="mid",
       desc="null 체크 누락", date="2026-08-16", rec=""):
    return ReviewIssue(file=file, line=line, category=cat, severity=sev,
                       description=desc, recommendation=rec, review_date=date,
                       commit_hash="c", module="M", source_review="r.md")


def test_group_issues():
    ctx = Path(tempfile.mkdtemp(prefix="ax-rc3-")) / "context"
    (ctx / "Source" / "M").mkdir(parents=True)
    (ctx / "Source" / "M" / "A.md").write_text(
        "요약\n\n## 코멘트\n[리뷰] null 체크는 상위 가드에서 보장됨 (2026-08-01)\n",
        encoding="utf-8")
    (ctx / "_domains").mkdir()
    (ctx / "_domains" / "A.md").write_text(
        "## 코멘트\n[리뷰] 도메인 문서는 제외 원천이 아니다\n", encoding="utf-8")

    got = IC.group_issues([mk()], ctx)
    check("[중요] [리뷰] 코멘트로 확인된 이슈는 제외된다 (같은 지적 반복 금지)",
          got["excluded_count"] == 1 and got["total"] == 0, str(got["total"]))

    got2 = IC.group_issues([mk(file="Source/M/B.cpp", desc="null 체크 누락")], ctx)
    check("다른 파일(코멘트 없음)은 제외 안 됨", got2["total"] == 1)

    dup = [mk(line="11", date="2026-08-10", desc="옛 지적"),
           mk(line="13", date="2026-08-16", desc="새 지적"),   # 같은 버킷(10~14)
           mk(line="17", date="2026-08-12", desc="딴 버킷")]
    got3 = IC.group_issues(dup, Path(tempfile.mkdtemp(prefix="ax-rc4-")))
    kept = [i.description for v in got3["file_issues"].values() for i in v]
    check("[중요] 라인 버킷(±5) 중복은 최신만 남는다", got3["total"] == 2
          and "새 지적" in kept and "옛 지적" not in kept, str(kept))

    many = [mk(file=f"Source/M/F{i}.cpp", line=str(i), desc="네이밍: 접두사 b 누락",
               cat="convention", sev=("high" if i == 0 else "low")) for i in range(3)]
    got4 = IC.group_issues(many, Path(tempfile.mkdtemp(prefix="ax-rc5-")))
    check("[중요] 3개 파일 이상 반복이면 패턴 (설명의 `:` 앞이 키)",
          len(got4["pattern_issues"]) == 1
          and got4["pattern_issues"][0]["pattern"] == "네이밍", str(got4["pattern_issues"]))
    check("패턴 심각도는 최고치로 승급", got4["pattern_issues"][0]["severity"] == "high")
    two = [mk(file=f"Source/M/G{i}.cpp", line=str(i), desc="네이밍: x") for i in range(2)]
    got5 = IC.group_issues(two, Path(tempfile.mkdtemp(prefix="ax-rc6-")))
    check("2개 파일은 패턴이 아니다", got5["pattern_issues"] == [])


def main() -> int:
    for fn in (test_producer_to_collector_roundtrip, test_empty_tables_yield_zero_issues,
               test_parse_conventions, test_group_issues):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_review_collect: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
