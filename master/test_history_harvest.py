"""소비자 history_harvest (#158) 계약 테스트.

재는 것 다섯:
    ① 생산자 왕복    [중요] history_gen(생산자③)이 **실제로 쓴 파일**을 이 파서가 읽는가 —
                    emission/parser 쌍의 실물 왕복
    ② claude 파서    8필드 · user_quote 우선 summary · 섹션 추출 · next_steps 결합
    ③ gemini 파서    Format A/B/C · prefix→decision_type · 경로→클래스/도메인 추론
    ④ walk/filter    date DESC · `_` 스킵 · prefix-tolerant 클래스 매칭 · limit/cap
    ⑤ audit          온톨로지 YAML 도메인 대비 coverage (read-only)

실행: .venv/bin/python master/test_history_harvest.py   (LLM 0 · 네트워크 0)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import history_gen as HG              # noqa: E402
from master.context_synth import history_harvest as HH          # noqa: E402

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
        self.ontology = root / "ontology"


def fixture():
    return P(Path(tempfile.mkdtemp(prefix="ax-hh-")))


# ── ① 생산자③ ↔ 소비자 실물 왕복 ────────────────────────────

def test_producer_roundtrip():
    p = fixture()
    path = HG.write(p, HG.render(
        title="스포너 구조 변경",
        decision_type="architecture",
        work_id="w-7",
        affected_classes=["UMissionPropsComponent_Spawner"],
        affected_domains=["MissionEditor"],
        alternatives_considered=["델리게이트 유지 — 순환 참조로 기각"],
        user_quote="스포너가 에셋 브라우저를 직접 열게 해줘",
        body="## 작업 개요\n선택 흐름 교체.\n\n## 주요 설계 결정\n람다로 위임.\n\n"
             "## 후속 작업 / 미해결 검토\n- 언바인드 시점 재확인",
    ), title="스포너 구조 변경")
    rec = HH.parse_claude_history(Path(path))
    check("[중요] 생산자③의 실물 파일을 파서가 읽는다", rec is not None)
    check("decision_type·클래스·도메인이 살아온다",
          rec.decision_type == "architecture"
          and rec.affected_classes == ["UMissionPropsComponent_Spawner"]
          and rec.affected_domains == ["MissionEditor"], str(rec))
    check("[중요] summary = user_quote (WHY 신호가 본문보다 강함)",
          rec.summary == "스포너가 에셋 브라우저를 직접 열게 해줘", rec.summary)
    check("flow_narrative = 주요 설계 결정 섹션", rec.flow_narrative == "람다로 위임.",
          rec.flow_narrative)
    check("next_steps = alternatives + 후속 섹션",
          rec.next_steps == ["델리게이트 유지 — 순환 참조로 기각", "언바인드 시점 재확인"],
          str(rec.next_steps))
    check("date 는 YYYY-MM-DD 로 잘린다", len(rec.date) == 10 and rec.date.count("-") == 2)


# ── ② claude 파서 방어 ───────────────────────────────────────

def test_claude_parser_defenses():
    d = Path(tempfile.mkdtemp(prefix="ax-hh2-"))
    f = d / "no_fm.md"
    f.write_text("# 제목만\n\n본문", encoding="utf-8")
    check("frontmatter 없으면 None", HH.parse_claude_history(f) is None)
    f2 = d / "half.md"
    f2.write_text("---\ndate: 2026-08-17\n본문에 닫는 경계가 없다", encoding="utf-8")
    check("경계가 안 닫히면 None", HH.parse_claude_history(f2) is None)
    check("없는 파일은 None", HH.parse_claude_history(d / "없음.md") is None)


# ── ③ gemini 파서 ────────────────────────────────────────────

GEMINI_A = """# Task Report

## Date: 2026-02-28
## Task: Hex cluster system
## Overview: Implements the hex septet cluster.
## Changes:
- Added cluster generation
## Key Files Affected:
- Source/ModularStage/Hex/UHexCluster.h (신규)
- `Source/ModularStage/Hex/UHexCluster.cpp`
## Next Steps:
- Wire into spawner
"""

GEMINI_B = """Date: 2026-04-26
Task: Character hierarchy
Overview: Restructure character classes.
Changes: moved base to ACharacterBase
Key Files Affected:
- Source/ModularStage/Character/ACharacterBase.h
"""

GEMINI_C = """# 분석 보고서

이 문서는 `Source/ModularStage/Hex/AHexTilemap.h` 의 절차 생성 구조를 분석한다.

## 1. 개요
타일맵은 층위 구조다.
"""


def test_gemini_parser():
    HH.reset_unknown_prefix_dedupe()
    d = Path(tempfile.mkdtemp(prefix="ax-hh3-"))
    fa = d / "Feature_HexSeptetClusterSystem_20260228_183000.txt"
    fa.write_text(GEMINI_A, encoding="utf-8")
    ra = HH.parse_gemini_history(fa)
    check("[중요] Format A — 섹션·경로·클래스 추출",
          ra.date == "2026-02-28" and ra.decision_type == "feature"
          and ra.affected_classes == ["UHexCluster"], str(ra.affected_classes))
    check("경로에서 도메인 추론 (Source/<모듈>/<하위>)", ra.affected_domains == ["Hex"],
          str(ra.affected_domains))
    check("next_steps 추출", ra.next_steps == ["Wire into spawner"], str(ra.next_steps))

    fb = d / "CharacterHierarchy_20260426_120000.txt"
    fb.write_text(GEMINI_B, encoding="utf-8")
    logged = []
    HH.set_log(lambda m: logged.append(m))
    rb = HH.parse_gemini_history(fb)
    HH.set_log(None)
    check("[중요] Format B (평문 헤더) 도 파싱", rb.affected_classes == ["ACharacterBase"],
          str(rb.affected_classes))
    check("[중요] 미지 prefix 는 feature 폴백 + 1회만 카나리 (원전 σ.15 dedupe)",
          rb.decision_type == "feature"
          and sum(1 for m in logged if "unknown prefix" in m) == 1, str(logged))
    logged2 = []
    HH.set_log(lambda m: logged2.append(m))
    HH.parse_gemini_history(fb)
    HH.set_log(None)
    check("같은 prefix 재발견은 silent", logged2 == [])

    fc = d / "Analysis_ProjectAlpha_HexTilemap_20260222_150000.txt"
    fc.write_text(GEMINI_C, encoding="utf-8")
    rc = HH.parse_gemini_history(fc)
    check("Format C (분석 문서) best-effort — 백쿼트 경로에서 클래스",
          rc.decision_type == "experiment" and "AHexTilemap" in rc.affected_classes, str(rc))


# ── ④ walk + filter ──────────────────────────────────────────

def test_walk_and_filter():
    p = fixture()
    cdir, gdir = HH.project_history_dirs(p)
    cdir.mkdir(parents=True)
    gdir.mkdir(parents=True)
    HG.write(p, HG.render(title="옛 결정", affected_classes=["UOld"],
                          date=__import__("datetime").datetime(2026, 1, 1)),
             title="옛 결정", date=__import__("datetime").datetime(2026, 1, 1))
    HG.write(p, HG.render(title="새 결정", affected_classes=["Manager_TableData"],
                          date=__import__("datetime").datetime(2026, 8, 1)),
             title="새 결정", date=__import__("datetime").datetime(2026, 8, 1))
    (cdir / "_index.md").write_text("---\ndate: 2026-08-17\n---\n인덱스", encoding="utf-8")
    (gdir / "Feature_X_20260228.txt").write_text(GEMINI_A, encoding="utf-8")

    recs = HH.walk_histories(cdir, gdir)
    check("[중요] 통합 walk — claude 2 + gemini 1 (`_` 스킵)", len(recs) == 3, str(len(recs)))
    check("date DESC 정렬", [r.date for r in recs] == ["2026-08-01", "2026-02-28", "2026-01-01"],
          str([r.date for r in recs]))

    got = HH.filter_for_classes(recs, {"UManager_TableData"})
    check("[중요] prefix-tolerant 매칭 — 온톨로지 UManager_TableData ↔ 기록 Manager_TableData",
          len(got) == 1 and got[0].summary == "" or got[0].path.endswith(".md"), str(len(got)))
    check("정확 매칭 모드에선 안 잡힌다",
          HH.filter_for_classes(recs, {"UManager_TableData"}, prefix_tolerant=False) == [])
    long = HH.filter_for_classes(recs, {"UHexCluster"}, per_record_chars=10)
    check("발췌 cap + '...' 마커", long and long[0].raw_excerpt.endswith("..."),
          long[0].raw_excerpt if long else "")
    check("빈 class_names 는 빈 결과", HH.filter_for_classes(recs, set()) == [])


# ── ⑤ audit ──────────────────────────────────────────────────

def test_audit():
    p = fixture()
    dd = p.ontology / "domains"
    (dd / "MissionRuntime" / "L1" / "objects").mkdir(parents=True)
    (dd / "MissionRuntime" / "L1" / "objects" / "UHexCluster.yaml").write_text("name: UHexCluster\n")
    (dd / "EmptyDomain" / "L1" / "objects").mkdir(parents=True)
    cdir, gdir = HH.project_history_dirs(p)
    gdir.mkdir(parents=True)
    (gdir / "Feature_X_20260228.txt").write_text(GEMINI_A, encoding="utf-8")

    got = HH.audit_coverage(p)
    check("[중요] coverage — 도메인 2 중 1 매칭 (온톨로지 YAML 이 정본)",
          got["total_domains"] == 2 and got["matched_domains"] == 1
          and got["unmatched"] == ["EmptyDomain"], str(got))
    check("소스별 계수", got["gemini_count"] == 1 and got["claude_count"] == 0)

    p2 = fixture()
    check("온톨로지 없으면 빈 진단 (silent)", HH.audit_coverage(p2)["total_domains"] == 0)


def main() -> int:
    for fn in (test_producer_roundtrip, test_claude_parser_defenses,
               test_gemini_parser, test_walk_and_filter, test_audit):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_history_harvest: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
