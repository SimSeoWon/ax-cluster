"""주간 플랜 소비자 (#155) 계약 테스트 — planner + plan_generator + plan_dedup + plan_register.

재는 것 다섯:
    ① 끝-끝 왕복    생산자 리포트(실물 형식) → 파싱 → 그룹핑 → 플랜 MD + 요약 + 인덱스 +
                   아카이브 + Redmine 등록 호출 — 전부 주입으로 LLM/네트워크 0
    ② 게이트        최소 리뷰 수 미달 스킵 · 주차 중복 스킵 · 파일 플랜 조건(고위험 or 중위험 3+)
    ③ 상속          지난 주차의 redmine_issue_id 를 물려받아 갱신으로 돈다 (매주 새 이슈 금지)
    ④ 등록          create → id 를 frontmatter 에 되적음 · 기존 id 는 update · 비플랜 MD 거부
    ⑤ create_issue  sender 주입으로 본문 형태 검증 (트래커/우선순위 이름 해석)

실행: .venv/bin/python master/test_planner.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import redmine as RM                                 # noqa: E402
from master.context_synth import plan_register as PR             # noqa: E402
from master.context_synth import planner as PL                   # noqa: E402
from master.context_synth.plan_dedup import _inherit_redmine_issue_id  # noqa: E402

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
        self.context = root / "context"
        self.repo = root / "repo"


REVIEW_TPL = """# 자동 코드 리뷰 — {h12}

- 커밋: `{h}`

### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|
| Source/M/A.cpp | 네이밍 | 접두사 b 누락 | {ln} | 중간 |

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/B.cpp | 높음 | 3 | null 체크 누락 | IsValid 가드 |

## 3. 영향 분석
없음.
"""


def fixture(n_reviews=3):
    root = Path(tempfile.mkdtemp(prefix="ax-pl-"))
    p = P(root)
    (p.context / "_domains").mkdir(parents=True)
    (p.repo / "Source" / "M").mkdir(parents=True)
    (p.repo / "Source" / "M" / "B.cpp").write_text(
        "\n".join(f"int line{i};" for i in range(20)), encoding="utf-8")
    rdir = root / "reviews" / "사람"
    rdir.mkdir(parents=True)
    today = datetime.now().strftime("%Y-%m-%d")
    for i in range(n_reviews):
        h = f"{'ab' * 16}{i:02d}"[:40]
        # 라인을 30씩 벌린다 — ±5 라인 버킷 중복 제거에 접히지 않게 (계약: 반복 지적이
        # 같은 자리면 최신만 남는다. 여기선 「서로 다른 지적 3건」이 필요하다)
        (rdir / f"{today}_09{i:02d}_{h[:8]}.md").write_text(
            REVIEW_TPL.format(h12=h[:12], h=h, ln=10 + i * 30), encoding="utf-8")
    return p, rdir


# ── ① 끝-끝 왕복 ─────────────────────────────────────────────

def test_end_to_end():
    p, rdir = fixture()
    chats, regs = [], []

    def chat(prompt):
        chats.append(prompt)
        return "## 문제 분석\n분석\n\n## 수정 방안\n방안\n\n## 영향 범위\n없음\n\n## 우선순위 근거\n높음"

    ok = PL.run_weekly_plans(p, chat=chat,
                             register=lambda wd, an, logf=None: regs.append((wd, an)),
                             logf=lambda m: None)
    check("[중요] 플랜이 생성됐다", ok is True)
    week = datetime.now().strftime("%Y-W%W")
    wd = p.root / "plans" / "사람" / week
    plans = [f.name for f in wd.glob("*.md") if f.name != "_summary.md"]
    check("고위험 파일 플랜이 나왔다 (B.cpp 높음)", "high_B.md" in plans, str(plans))
    check("LLM 프롬프트에 금지 규칙이 실린다 (리네이밍 금지)",
          chats and "리네이밍 제안 금지" in chats[0])
    check("소스 스니펫이 프롬프트에 실린다 (repo 에 실재하는 B.cpp 플랜)",
          any("[소스 코드]" in c and "int line" in c for c in chats), str(len(chats)))
    check("[중요] Redmine 등록이 호출된다 (주차 디렉토리·작성자)",
          regs == [(wd, "사람")], str(regs))
    body = (wd / "high_B.md").read_text(encoding="utf-8")
    check("플랜 frontmatter 계약 (type/week/target_file/status)",
          "type: improvement_plan" in body and "target_file: Source/M/B.cpp" in body
          and "status: pending" in body)
    check("원본 리뷰 지적이 인용된다", "## 원본 리뷰 지적" in body and "null 체크 누락" in body)
    summary = (wd / "_summary.md").read_text(encoding="utf-8")
    check("주간 요약이 나온다 (고위험 표 포함)",
          "type: weekly_plan" in summary and "고위험 이슈" in summary)
    check("작성자 인덱스 갱신", (p.root / "plans" / "사람" / "_index.md").exists())
    check("글로벌 인덱스 갱신 (작성자 집계)",
          "사람" in (p.root / "plans" / "_index.md").read_text(encoding="utf-8"))
    check("[중요] 반영된 리뷰는 _archive 로 이동 (다음 주 재계수 방지)",
          not list(rdir.glob("2*.md")) and len(list((rdir / "_archive" / week).glob("*.md"))) == 3)

    ok2 = PL.run_weekly_plans(p, chat=chat, register=lambda *a, **k: regs.append("again"),
                              logf=lambda m: None)
    check("[중요] 같은 주차 재실행은 스킵 (요약 존재)", ok2 is False and "again" not in regs)


# ── ② 게이트 ─────────────────────────────────────────────────

def test_gates():
    p, _ = fixture(n_reviews=2)
    called = []
    ok = PL.run_weekly_plans(p, chat=lambda pr: called.append(1) or "x",
                             register=lambda *a, **k: None, logf=lambda m: None)
    check("[중요] 리뷰 2건 < 최소 3건 — 스킵 (LLM 무호출)", ok is False and called == [])

    from master.context_synth.plan_generator import generate_improvement_plans
    from master.context_synth.review_collector import ReviewIssue

    def mk(sev, ln="10", file="Source/M/C.cpp"):
        return ReviewIssue(file=file, line=ln, category="convention", severity=sev,
                           description="네이밍: x", recommendation="",
                           review_date="2026-08-16", commit_hash="c", module="M",
                           source_review="r.md")

    d = Path(tempfile.mkdtemp(prefix="ax-pl2-"))
    got = generate_improvement_plans(
        {"file_issues": {"Source/M/C.cpp": [mk("mid"), mk("mid")]},
         "pattern_issues": [], "excluded_count": 0, "total": 2},
        d / "ctx", d, None, "2026-W33", chat=lambda pr: "본문")
    check("[중요] 중위험 2건뿐이면 파일 플랜 없음 (고위험 or 중위험 3+)",
          got["plans_generated"] == 0, str(got))
    got2 = generate_improvement_plans(
        {"file_issues": {"Source/M/C.cpp": [mk("mid"), mk("mid"), mk("mid")]},
         "pattern_issues": [], "excluded_count": 0, "total": 3},
        d / "ctx", d, None, "2026-W33", chat=lambda pr: "본문")
    check("중위험 3건이면 생성", got2["plans_generated"] == 1)
    got3 = generate_improvement_plans(
        {"file_issues": {"Source/M/D.cpp": [mk("high")]},
         "pattern_issues": [], "excluded_count": 0, "total": 1},
        d / "ctx", d, None, "2026-W33", chat=lambda pr: "본문", token_budget=0)
    check("[중요] 토큰 예산 0 이면 생성 안 함 (예산이 상한이다)",
          got3["plans_generated"] == 0)


# ── ③ redmine_issue_id 상속 ──────────────────────────────────

def test_dedup_inheritance():
    d = Path(tempfile.mkdtemp(prefix="ax-pl3-"))
    prev = d / "2026-W32"
    prev.mkdir(parents=True)
    (prev / "high_B.md").write_text(
        "---\ntype: improvement_plan\ntarget_file: Source/M/B.cpp\n"
        "redmine_issue_id: 321\n---\n본문", encoding="utf-8")
    got = _inherit_redmine_issue_id(d, "2026-W33", "mid_B.md", "Source/M/B.cpp")
    check("[중요] 지난 주차 같은 target_file 의 이슈 id 를 상속 (severity 접두가 달라도)",
          got == "321", got)
    check("다른 파일은 상속 없음 (신규 등록)",
          _inherit_redmine_issue_id(d, "2026-W33", "high_X.md", "Source/M/X.cpp") == "")
    (prev / "pattern_네이밍.md").write_text(
        "---\ntype: improvement_plan\nredmine_issue_id: 322\n---\n", encoding="utf-8")
    check("패턴 플랜은 파일명으로 상속",
          _inherit_redmine_issue_id(d, "2026-W33", "pattern_네이밍.md", "") == "322")


# ── ④ 플랜 등록 ──────────────────────────────────────────────

def test_register():
    d = Path(tempfile.mkdtemp(prefix="ax-pl4-"))
    plan = d / "plans" / "사람" / "2026-W33" / "high_B.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "---\ntype: improvement_plan\nweek: 2026-W33\ncategory: safety\n"
        "severity: high\ntarget_file: Source/M/B.cpp\nsource_reviews:\n  - r1.md\n"
        "status: pending\n---\n\n## 문제 분석\n본문", encoding="utf-8")
    rdir = d / "reviews" / "사람"
    rdir.mkdir(parents=True)
    (rdir / "r1.md").write_text("### Source/M\n| Source/M/B.cpp | 높음 | 3 | null | 가드 |\n",
                                encoding="utf-8")

    created = []

    def fake_create(subject, description, **kw):
        created.append((subject, description, kw))
        return {"id": 900}

    got = PR.register_plan(plan, create=fake_create, update=lambda *a, **k: "안 옴")
    check("[중요] 신규 플랜은 create — 제목 규약 [플랜] <파일> — HIGH (분류)",
          got == {"action": "created", "issue_id": 900,
                  "subject": "[플랜] Source/M/B.cpp — HIGH (safety)"}, str(got))
    check("트래커/우선순위가 이름으로 간다 (코드리뷰·높음)",
          created[0][2] == {"tracker_name": "코드리뷰", "priority_name": "높음"},
          str(created[0][2]))
    check("[중요] 원본 리뷰가 설명에 인용된다 (경로 + 발췌)",
          "원본 리뷰 위치" in created[0][1] and "null" in created[0][1])
    text = plan.read_text(encoding="utf-8")
    check("[중요] 발급 id 가 frontmatter 에 되적힌다 (다음 주 상속의 원천)",
          "redmine_issue_id: 900" in text and "redmine_last_sync:" in text)

    updates = []
    got2 = PR.register_plan(plan, create=fake_create,
                            update=lambda iid, notes="": updates.append((iid, notes)) or "갱신")
    check("[중요] id 가 있으면 update 로 돈다 (새 이슈 금지)",
          got2 == {"action": "updated", "issue_id": 900} and updates[0][0] == 900, str(got2))

    bad = d / "notplan.md"
    bad.write_text("---\ntype: weekly_plan\n---\n", encoding="utf-8")
    check("비플랜 MD 는 거부", "error" in PR.register_plan(bad, create=fake_create,
                                                        update=lambda *a, **k: ""))

    week = PR.register_week_plans(plan.parent, "사람", create=fake_create,
                                  update=lambda iid, notes="": "갱신")
    check("주차 일괄 등록이 집계를 돌려준다 (기존 id → 갱신 1)",
          week["updated"] == 1 and week["created"] == 0 and not week["errors"], str(week))


# ── ⑤ create_issue ───────────────────────────────────────────

def test_create_issue():
    sent = []

    def sender(method, url, payload):
        sent.append((method, url, payload))
        if "trackers" in url:
            return {"trackers": [{"id": 1, "name": "코드리뷰"}]}
        if "priorities" in url:
            return {"issue_priorities": [{"id": 3, "name": "높음"}]}
        return {"issue": {"id": 901}}

    got = RM.create_issue("제목", "설명", tracker_name="코드리뷰", priority_name="높음",
                          sender=sender)
    check("create_issue 가 id 를 돌려준다", got == {"id": 901}, str(got))
    post = [s for s in sent if s[0] == "POST"][0]
    check("[중요] 같은 프로젝트로 간다 (modularstage — 새 프로젝트 금지)",
          post[2]["issue"]["project_id"] == "modularstage"
          and post[2]["issue"]["tracker_id"] == 1
          and post[2]["issue"]["priority_id"] == 3, str(post[2]))
    check("빈 제목은 error", "error" in RM.create_issue(" ", sender=sender))


def main() -> int:
    for fn in (test_end_to_end, test_gates, test_dedup_inheritance,
               test_register, test_create_issue):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_planner: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
