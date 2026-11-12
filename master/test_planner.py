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

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import redmine as RM                                 # noqa: E402
from master.context_synth import plan_register as PR             # noqa: E402
from master.context_synth import planner as PL                   # noqa: E402
from master.context_synth import plan_generator as PG            # noqa: E402
from master.context_synth.plan_dedup import _inherit_redmine_issue_id  # noqa: E402

PASS = FAIL = 0

VALID_FILE = """## 문제 분석
널 참조가 전달되면 역참조에서 실패한다.

## 수정 방안
Before: ptr->Run(); After: if (ptr) ptr->Run();

## 영향 범위
호출자의 기존 정상 입력 동작은 유지한다.

## 우선순위 근거
사용자 입력으로 발생하는 실패를 막는다.
"""
VALID_PATTERN = """## 패턴 분석
동일한 네이밍 위반이 여러 파일에 반복된다.

## 일괄 수정 가이드
변수 선언과 사용 지점을 함께 대조해 일관된 표기를 적용한다.

## 적용 대상 파일 목록
- Source/M/A.cpp

## 우선순위 근거
동작 변경 없이 읽기 비용을 줄인다.
"""


def valid_response(prompt: str) -> str:
    return VALID_PATTERN if "[반복 패턴]" in prompt else VALID_FILE


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        # [DOC] #632: 테스트 요청 프로젝트 이름과 Redmine 매핑은 별개다.
        self.name = "NS"
        self.root = root
        self.context = root / "context"
        self.repo = root / "repo"
        self.usage_log = root / "usage_log.jsonl"


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


def fixture(n_reviews=3, *, pattern=False):
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
        review = REVIEW_TPL.format(h12=h[:12], h=h, ln=10 + i * 30)
        if pattern:
            # 실제 분류기는 서로 다른 파일 3개부터 반복 패턴으로 묶는다.
            review = review.replace("Source/M/A.cpp", f"Source/M/A{i}.cpp")
        (rdir / f"{today}_09{i:02d}_{h[:8]}.md").write_text(review, encoding="utf-8")
    return p, rdir


# ── ① 끝-끝 왕복 ─────────────────────────────────────────────

def test_end_to_end():
    # [DOC] #632: planner는 프로젝트 이름을 주차 등록에 전달한다. 외부 호출은 주입한다.
    p, rdir = fixture(pattern=True)
    chats, regs = [], []

    def chat(prompt):
        chats.append(prompt)
        return valid_response(prompt)

    ok = PL.run_weekly_plans(p, chat=chat,
                             register=lambda wd, an, logf=None, project="":
                             regs.append((wd, an, project)),
                             logf=lambda m: None)
    check("[중요] 플랜이 생성됐다", ok is True)
    week = datetime.now().strftime("%Y-W%W")
    wd = p.root / "plans" / "사람" / week
    plans = [f.name for f in wd.glob("*.md") if f.name != "_summary.md"]
    check("고위험 파일 플랜이 나왔다 (B.cpp 높음)", "high_B.md" in plans, str(plans))
    check("LLM 프롬프트에 금지 규칙이 실린다 (리네이밍 금지)",
          chats and "리네이밍 제안 금지" in chats[0])
    check("#900 파일·패턴 프롬프트 모두 무인 완성 응답 계약을 싣는다",
          chats and all("무인 주간 플랜 생성 배치" in c and "사용자 응답을 기다리거나" in c
                        and "추가 위임 없이" in c for c in chats))
    check("#900 정상 파일·패턴 응답을 모두 저장",
          any(name.startswith("pattern_") for name in plans) and "high_B.md" in plans)
    check("소스 스니펫이 프롬프트에 실린다 (repo 에 실재하는 B.cpp 플랜)",
          any("[소스 코드]" in c and "int line" in c for c in chats), str(len(chats)))
    check("[중요] Redmine 등록이 호출된다 (주차 디렉토리·작성자)",
          regs == [(wd, "사람", p.name)], str(regs))
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
        d / "ctx", d, None, "2026-W33", chat=valid_response)
    check("[중요] 중위험 2건뿐이면 파일 플랜 없음 (고위험 or 중위험 3+)",
          got["plans_generated"] == 0, str(got))
    got2 = generate_improvement_plans(
        {"file_issues": {"Source/M/C.cpp": [mk("mid"), mk("mid"), mk("mid")]},
         "pattern_issues": [], "excluded_count": 0, "total": 3},
        d / "ctx", d, None, "2026-W33", chat=valid_response)
    check("중위험 3건이면 생성", got2["plans_generated"] == 1)
    got3 = generate_improvement_plans(
        {"file_issues": {"Source/M/D.cpp": [mk("high")]},
         "pattern_issues": [], "excluded_count": 0, "total": 1},
        d / "ctx", d, None, "2026-W33", chat=valid_response)
    check("[중요] 상용 플랜엔 토큰 예산이 없다 — 고위험 1건이면 생성 (#823)",
          got3["plans_generated"] == 1)


def test_incomplete_responses():
    """실제 질문 응답과 불완전 문서는 정상 플랜이 아니며 원문 진단은 남긴다."""
    from master.context_synth.review_collector import ReviewIssue

    issue = ReviewIssue(file="Source/M/B.cpp", line="3", category="safety", severity="high",
                        description="null", recommendation="guard", review_date="2026-11-07",
                        commit_hash="c", module="M", source_review="r.md")
    grouped = {"file_issues": {issue.file: [issue]}, "pattern_issues": [],
               "excluded_count": 0, "total": 1}
    bad = [
        ("P13 질문", "Gemini(agy)에 위임할까요, 아니면 제가 이 세션에서 직접 작성할까요?"),
        ("P14 질문", "현재 세션에서 바로 작성할지, Gemini(agy)에 위임할지 선택해 주세요."),
        ("P15 질문", "수정 가이드는 이 세션에서 직접 작성할까요, Gemini(agy)에 위임할까요?"),
        ("거절", "제공된 자료만으로 수정안을 작성할 수 없습니다."),
        ("빈 응답", "  \n"),
        ("필수 절 누락", VALID_FILE.split("## 영향 범위")[0]),
        ("빈 절", VALID_FILE.replace("사용자 입력으로 발생하는 실패를 막는다.", "")),
        ("지시문만", VALID_FILE.replace("사용자 입력으로 발생하는 실패를 막는다.",
                                    "(지금 고쳐야 하는 이유)")),
        ("코드 예시 속 가짜 절", "```markdown\n" + VALID_FILE + "```\n"),
    ]
    with tempfile.TemporaryDirectory(prefix="ax-pl-invalid-") as td:
        for n, (label, raw) in enumerate(bad):
            d = Path(td) / str(n)
            got = PG.generate_improvement_plans(grouped, d / "ctx", d, None, "2026-W44",
                                                chat=lambda _, result=raw: result)
            check(f"#900 {label} — 성공 저장·집계 0", got["plans_generated"] == 0
                  and not got["source_reviews"] and not list(d.rglob("*.md")), str(got))
            check(f"#900 {label} — 대상·사유·원본리뷰·응답 진단",
                  len(got["failures"]) == 1 and got["failures"][0]["file"] == "high_B.md"
                  and got["failures"][0]["reason"] and got["failures"][0]["source_reviews"] == ["r.md"]
                  and got["failures"][0]["response"] == raw and got["tokens_used"] > 0, str(got))

        def boom(_):
            raise RuntimeError("대역 호출 실패")

        d = Path(td) / "exception"
        got = PG.generate_improvement_plans(grouped, d / "ctx", d, None, "2026-W44", chat=boom)
        check("#900 LLM 예외 — 정상 저장 없이 원인 기록", got["plans_generated"] == 0
              and not list(d.rglob("*.md")) and "RuntimeError" in got["failures"][0]["reason"]
              and got["tokens_used"] > 0, str(got))


def test_failed_week_can_retry():
    """같은 리뷰가 성공/실패 후보에 공유돼도 전체 주차가 준비되기 전에는 공개하지 않는다."""
    p, rdir = fixture(pattern=True)
    original = {f.name: f.read_bytes() for f in rdir.glob("*.md")}
    regs, logs = [], []
    week_dir = p.root / "plans" / "사람" / datetime.now().strftime("%Y-W%W")
    result = PL.run_weekly_plans(
        p, chat=lambda prompt: VALID_FILE if "[대상 파일]" in prompt else "Gemini에 위임할까요?",
        register=lambda *a, **k: regs.append(a), logf=logs.append)
    attempts = [json.loads(line) for line in
                (week_dir / "_generation_attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    check("#900 부분 응답 실패 — 정상 주차/플랜/등록/인덱스 0", result is False
          and not regs and not list(week_dir.glob("*.md"))
          and not (week_dir.parent / "_index.md").exists()
          and not (week_dir.parent.parent / "_index.md").exists())
    check("#900 부분 응답 실패 — 공유 원본 리뷰 전부 보존",
          original == {f.name: f.read_bytes() for f in rdir.glob("*.md")}
          and not (rdir / "_archive").exists())
    check("#900 부분 응답 실패 — 정상 후보도 미공개·실패응답·토큰 진단",
          attempts[0]["complete"] is False and attempts[0]["plans_generated"] == 0
          and attempts[0]["validated_candidates"] > 0 and attempts[0]["tokens_used"] > 0
          and any(f["response"] == "Gemini에 위임할까요?" for f in attempts[0]["failures"])
          and any("주차 생성 미완료" in log for log in logs))
    result2 = PL.run_weekly_plans(p, chat=valid_response,
                                 register=lambda *a, **k: regs.append(a), logf=logs.append)
    attempts2 = [json.loads(line) for line in
                 (week_dir / "_generation_attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    check("#900 다음 회차 정상 응답 — 완성 플랜·등록·요약 성공", result2 is True
          and len(regs) == 1 and (week_dir / "_summary.md").is_file()
          and (week_dir / "high_B.md").is_file())
    check("#900 성공 후 아카이브·과거 실패 원문 보존", not list(rdir.glob("*.md"))
          and len(list((rdir / "_archive" / week_dir.name).glob("*.md"))) == len(original)
          and len(attempts2) == 2 and attempts2[0] == attempts[0] and attempts2[1]["complete"] is True)
    called = []
    result3 = PL.run_weekly_plans(p, chat=lambda _: called.append(1) or VALID_FILE,
                                 register=lambda *a, **k: regs.append(a), logf=logs.append)
    check("#900 완료 주차만 이후 스킵 — 중복 생성·등록 없음",
          result3 is False and not called and len(regs) == 1)

    p2, rdir2 = fixture()
    regs2 = []
    result0 = PL.run_weekly_plans(p2, chat=lambda _: " ",
                                 register=lambda *a, **k: regs2.append(a), logf=lambda _: None)
    wd2 = p2.root / "plans" / "사람" / datetime.now().strftime("%Y-W%W")
    check("#900 전체 응답 실패 — 0건을 성공 주차로 잠그지 않음", result0 is False
          and not regs2 and not (wd2 / "_summary.md").exists()
          and len(list(rdir2.glob("*.md"))) == 3)

    # 다른 작성자 성공으로 글로벌 인덱스가 갱신돼도 실패 주차를 완료 주수에 넣지 않는다.
    previous = wd2.parent / "2000-W01"
    previous.mkdir()
    (previous / "_summary.md").write_text("plans_generated: 2\n", encoding="utf-8")
    other = wd2.parent.parent / "다른사람" / "2000-W01"
    other.mkdir(parents=True)
    (other / "_summary.md").write_text("plans_generated: 1\n", encoding="utf-8")
    PG._update_global_plan_index(wd2.parent.parent)
    index = (wd2.parent.parent / "_index.md").read_text(encoding="utf-8")
    check("#900 글로벌 인덱스 — 완료 요약 있는 주차만 주수·플랜 집계",
          "**사람**: 1주, 플랜 2건" in index and "**다른사람**: 1주, 플랜 1건" in index
          and wd2.name not in index, index)


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
    # [DOC] #632: 등록 검사는 fake project_lookup을 사용해 네트워크 없이 돈다.
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

    got = PR.register_plan(plan, create=fake_create, update=lambda *a, **k: "안 옴",
                           project="NS", project_lookup=lambda _: "ns-project")
    check("[중요] 신규 플랜은 create — 제목 규약 [플랜] <파일> — HIGH (분류)",
          got == {"action": "created", "issue_id": 900,
                  "subject": "[플랜] Source/M/B.cpp — HIGH (safety)"}, str(got))
    check("트래커/우선순위가 이름으로 간다 (코드리뷰·높음)",
          created[0][2] == {"tracker_name": "코드리뷰", "priority_name": "높음",
                            "project": "ns-project"},
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
                                  update=lambda iid, notes="": "갱신", project="NS",
                                  project_lookup=lambda _: "ns-project")
    check("주차 일괄 등록이 집계를 돌려준다 (기존 id → 갱신 1)",
          week["updated"] == 1 and week["created"] == 0 and not week["errors"], str(week))


# [DOC] #632: 프로젝트 전달 누락 및 잘못된 기본 프로젝트 등록을 회귀 검사한다.
def test_project_routing() -> None:
    d = Path(tempfile.mkdtemp(prefix="ax-pl-route-"))

    def make_plan(name: str) -> Path:
        plan = d / name / "plans" / "사람" / "2026-W33" / "high_B.md"
        plan.parent.mkdir(parents=True)
        plan.write_text(
            "---\ntype: improvement_plan\nweek: 2026-W33\ncategory: safety\n"
            "severity: high\ntarget_file: Source/M/B.cpp\nstatus: pending\n---\n본문",
            encoding="utf-8")
        return plan

    created, updated = [], []

    def fake_create(subject, description, **kw):
        created.append(kw)
        return {"id": 1000 + len(created)}

    def fake_update(*args, **kwargs):
        updated.append((args, kwargs))
        return "갱신"

    mappings = {"NS": "ns-project", "AXCluster": "ax-cluster"}
    for requested in ("NS", "AXCluster"):
        plan = make_plan(requested)
        got = PR.register_plan(plan, create=fake_create, update=fake_update,
                               project=requested, project_lookup=mappings.get)
        check(f"프로젝트 매핑에 따라 생성 ({requested})", got.get("action") == "created"
              and created[-1]["project"] == mappings[requested], str(got))

    for label, requested, lookup in (
            ("누락", "", mappings.get),
            ("빈 매핑", "Unknown", mappings.get),
            ("조회 예외", "Broken", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))):
        plan = make_plan(f"bad-{label}")
        before = plan.read_bytes()
        call_counts = (len(created), len(updated))
        got = PR.register_plan(plan, create=fake_create, update=fake_update,
                               project=requested, project_lookup=lookup)
        check(f"프로젝트 {label}는 호출·파일 변경 없이 거부", "error" in got
              and call_counts == (len(created), len(updated))
              and plan.read_bytes() == before, str(got))

    week_plan = make_plan("week")
    week = PR.register_week_plans(week_plan.parent, "사람", create=fake_create,
                                  update=fake_update, project="NS",
                                  project_lookup=mappings.get)
    check("주차 등록이 프로젝트 매핑을 전달", week["created"] == 1
          and created[-1]["project"] == "ns-project" and not week["errors"], str(week))

    bad_week_plan = make_plan("bad-week")
    bad_week = PR.register_week_plans(bad_week_plan.parent, "사람", create=fake_create,
                                      update=fake_update, project="Unknown",
                                      project_lookup=mappings.get)
    check("주차 등록이 매핑 오류를 집계", bad_week["created"] == 0
          and len(bad_week["errors"]) == 1, str(bad_week))

    p, _ = fixture()
    end_created = []

    def end_register(wd, author, logf=None, project=""):
        return PR.register_week_plans(
            wd, author, create=lambda subject, description, **kw:
            end_created.append(kw) or {"id": 2000}, update=fake_update,
            logf=logf, project=project, project_lookup=mappings.get)

    ok = PL.run_weekly_plans(
        p, chat=valid_response, register=end_register, logf=lambda _: None,
        archive=False)
    week_dir = p.root / "plans" / "사람" / datetime.now().strftime("%Y-W%W")
    check("planner부터 실제 등록까지 요청 프로젝트를 전달", ok and end_created
          and all(kw["project"] == "ns-project" for kw in end_created), str(end_created))

    p_bad, _ = fixture()
    p_bad.name = "Unknown"
    bad_created = []

    def bad_register(wd, author, logf=None, project=""):
        return PR.register_week_plans(
            wd, author, create=lambda *args, **kwargs:
            bad_created.append(kwargs) or {"id": 3000}, update=fake_update,
            logf=logf, project=project, project_lookup=mappings.get)

    bad_ok = PL.run_weekly_plans(
        p_bad, chat=valid_response, register=bad_register, logf=lambda _: None,
        archive=False)
    bad_week_dir = p_bad.root / "plans" / "사람" / datetime.now().strftime("%Y-W%W")
    check("매핑 실패에도 플랜과 요약을 보존", bad_ok and not bad_created
          and (bad_week_dir / "high_B.md").exists()
          and (bad_week_dir / "_summary.md").exists())


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
    check("[중요] 프로젝트 미지정은 AX 인프라 자리로 간다 (ax-cluster — 사용자 결정 2026-09-28)",
          post[2]["issue"]["project_id"] == RM.AX_PROJECT_ID == "ax-cluster"
          and post[2]["issue"]["tracker_id"] == 1
          and post[2]["issue"]["priority_id"] == 3, str(post[2]))
    check("빈 제목은 error", "error" in RM.create_issue(" ", sender=sender))


def main() -> int:
    for fn in (test_end_to_end, test_gates, test_incomplete_responses, test_failed_week_can_retry,
               test_dedup_inheritance,
               test_register, test_project_routing, test_create_issue):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_planner: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
