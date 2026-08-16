"""planner (#155) — 원전 `watcher/planner.py` 143줄의 이식. 주간 개선 플랜 생성.

평일 리뷰 누적 → 주말 배치: 이슈 파싱 + 그룹핑 + LLM 플랜 생성 (+ Redmine 등록).
[중요] **코드를 직접 수정하지 않는다 — 사람이 확인 후 실행** (원전 원문. 우리가 새로 세운
원칙과 같은 원칙이 원전에 이미 있었다 — Redmine `#155` 설명 참조).

원전과의 차이:
    Step 0 (batch_upgrade_domains, draft→active 자동 승급) 은 **이식하지 않는다** —
    좁힌 것이 아니라 확정 결정의 적용이다: 자동 승급은 원전 스스로 2026-06-01 오동작으로
    **영구 비활성**했고(사용자 확인), 우리 `ontology/create.py` 도 *"활성화는 사람이
    명시한다"* 로 굳혔다. 원전 planner 의 이 호출은 그 폐기 이전의 잔재다.
    Redmine 등록은 exe 서브프로세스가 아니라 `plan_register`(마스터 직호출) — 구조 차이.
    경로는 트윈 기준: reviews/ · plans/ 가 `{paths.root}` 아래 (원전 .claude/ 와 같은 위상).

실행: .venv/bin/python -m master.context_synth.planner [--min-reviews N] [--no-redmine]
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .issue_classifier import group_issues
from .plan_archive import archive_reviews
from .plan_generator import (PLAN_TOKEN_BUDGET, _build_weekly_summary,
                             _update_global_plan_index, _update_plan_index,
                             generate_improvement_plans)
from .review_collector import parse_review_reports

PLAN_MIN_REVIEWS = 3         # 최소 리뷰 건수 (미달 시 스킵)
PLANS_DIRNAME = "plans"
REVIEWS_DIRNAME = "reviews"


def list_author_dirs(reviews_dir: Path) -> list:
    """작성자 디렉토리 목록 (`_` 접두 제외 — _archive 등은 작성자가 아니다)."""
    if not reviews_dir.is_dir():
        return []
    return sorted(d for d in reviews_dir.iterdir()
                  if d.is_dir() and not d.name.startswith("_"))


def run_weekly_plans(paths, *, min_reviews: int = PLAN_MIN_REVIEWS,
                     token_budget: int = PLAN_TOKEN_BUDGET,
                     redmine: bool = True, archive: bool = True,
                     chat=None, register=None, logf=None,
                     now: datetime | None = None) -> bool:
    """작성자별 주간 개선 플랜을 생성한다. 반환: True면 하나 이상 생성.

    `chat`/`register` 주입은 테스트 자리 — 실전은 상용 체인·마스터 Redmine 이다.
    """
    log = logf or (lambda m: None)
    now = now or datetime.now()
    week_num = now.strftime("%Y-W%W")

    plans_dir = Path(paths.root) / PLANS_DIRNAME
    plans_dir.mkdir(parents=True, exist_ok=True)
    reviews_dir = Path(paths.root) / REVIEWS_DIRNAME
    context_dir = Path(paths.context)
    repo_dir = Path(paths.repo) if getattr(paths, "repo", None) else None

    since = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    period = f"{since} ~ {now.strftime('%Y-%m-%d')}"

    author_dirs = list_author_dirs(reviews_dir)
    if not author_dirs:
        log("[플랜] 작성자 디렉토리 없음 — 스킵")
        return False

    any_generated = False

    for author_dir in author_dirs:
        author_name = author_dir.name
        author_plans_dir = plans_dir / author_name
        author_plans_dir.mkdir(parents=True, exist_ok=True)

        # 이번 주 이미 생성했으면 스킵
        week_dir = author_plans_dir / week_num
        if (week_dir / "_summary.md").exists():
            log(f"[플랜] {author_name}: 이번 주차({week_num}) 플랜 이미 존재 — 스킵 "
                f"(재실행하려면 {week_dir} 삭제 후 다시 시도)")
            continue

        log(f"[플랜] 주간 플랜 생성 시작 ({author_name}, {week_num})")

        # Step 1: 작성자 리뷰 파싱
        issues = parse_review_reports(author_dir, since)
        review_count = len(set(i.source_review for i in issues if i.source_review))

        if review_count < min_reviews:
            log(f"[플랜] {author_name}: 리뷰 {review_count}건 < 최소 {min_reviews}건 — 스킵")
            continue

        log(f"[플랜] {author_name}: 리뷰 {review_count}건에서 이슈 {len(issues)}건 파싱")

        # Step 2: 이슈 그룹핑
        grouped = group_issues(issues, context_dir)
        log(f"[플랜] {author_name}: 이슈 {grouped['total']}건 "
            f"(코멘트 제외 {grouped['excluded_count']}건, "
            f"파일별 {len(grouped['file_issues'])}그룹, "
            f"패턴 {len(grouped['pattern_issues'])}개)")

        if grouped["total"] == 0:
            continue

        # Step 3-4: 플랜 생성
        plan_result = generate_improvement_plans(
            grouped, context_dir, author_plans_dir, repo_dir,
            week_num, token_budget=token_budget, chat=chat, logf=log,
        )

        log(f"[플랜] {author_name}: 플랜 {plan_result['plans_generated']}건 생성 "
            f"(토큰 ~{plan_result['tokens_used']:,})")

        # Step 3.5: Redmine 이슈 등록/갱신
        if redmine and plan_result["plans_generated"]:
            from . import plan_register as PR
            reg = register or PR.register_week_plans
            reg(week_dir, author_name, logf=log)

        # 주간 요약 생성
        summary = _build_weekly_summary(
            week_num, period, author_plans_dir, grouped, plan_result,
            author_name=author_name,
        )
        week_dir.mkdir(parents=True, exist_ok=True)
        (week_dir / "_summary.md").write_text(summary, encoding='utf-8')

        _update_plan_index(author_plans_dir, author_name=author_name)

        # Step 5: 리뷰 아카이브 (작성자 디렉토리 내)
        if archive:
            archive_reviews(author_dir, plan_result["source_reviews"], week_num, logf=log)

        log(f"[플랜] {author_name}: 주간 플랜 완료 → plans/{author_name}/{week_num}/")
        any_generated = True

    # 전체 플랜 인덱스 갱신
    if any_generated:
        _update_global_plan_index(plans_dir)
    else:
        log(f"[플랜] 신규 생성된 플랜 없음 (작성자 {len(author_dirs)}명 모두 스킵 또는 미해당)")

    return any_generated


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="주간 개선 플랜 생성 (#155)")
    ap.add_argument("--min-reviews", type=int, default=PLAN_MIN_REVIEWS)
    ap.add_argument("--no-redmine", action="store_true")
    ap.add_argument("--no-archive", action="store_true",
                    help="리뷰를 _archive 로 옮기지 않는다 (재실행 검증용)")
    args = ap.parse_args(argv)

    from ..context_search.paths import resolve
    ok = run_weekly_plans(resolve(""), min_reviews=args.min_reviews,
                          redmine=not args.no_redmine, archive=not args.no_archive,
                          logf=print)
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
