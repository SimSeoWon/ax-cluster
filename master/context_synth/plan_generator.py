"""plan_generator (#155) — 원전 `watcher/plan_generator.py` 432줄의 이식.

그룹핑된 리뷰 이슈에서 LLM 개선 플랜 MD 를 만든다: 파일별(고위험 또는 중위험 3건+) +
반복 패턴 일괄. [중요] **코드를 직접 수정하지 않는다 — 사람이 확인 후 실행** (원전 원문.
우리가 새로 세운 원칙과 같은 원칙이 원전에 이미 있었다).

원전과의 차이 (전부 import·백엔드 대체, 로직 동일):
    common._call_llm            → 상용 체인(agy→claude, `review_gen.commercial_chat`) —
                                  원전 기본값도 Claude 였다(#205 에서 실측·확정한 그 근거)
    common.DOMAIN_DIR_NAME      → issue_classifier.DOMAIN_DIR_NAME
    context._extract_comments_section → issue_classifier 의 이식본
    context._find_matching_domain     → 여기로 동반 이식 (원전 context.py:129, 쓰는 곳이 여기뿐)
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .issue_classifier import DOMAIN_DIR_NAME, _extract_comments_section
from .plan_dedup import _inherit_redmine_issue_id
from .review_gen import commercial_chat

PLAN_TOKEN_BUDGET = 100_000  # 주당 토큰 상한 (기본값)


def _find_matching_domain(context_dir: Path, file_paths: list) -> str:
    """파일이 속한 도메인 문서를 찾아 핵심 섹션(시스템 개요 + 설계 패턴)을 반환한다.
    (원전 context.py:129 글자대로)"""
    domain_dir = context_dir / DOMAIN_DIR_NAME
    if not domain_dir.exists():
        return ""

    file_stems = set()
    for fp in file_paths:
        file_stems.add(str(Path(fp).with_suffix('.md')))
        file_stems.add(str(Path(fp).parent) + ".md")

    for md_file in domain_dir.glob("*.md"):
        if md_file.name.startswith("_"):
            continue
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception:                                    # noqa: BLE001
            continue

        sources = set(re.findall(r'-\s+(\S+\.md)', content))
        if not sources:
            continue
        if not (file_stems & sources):
            continue

        sections = []
        for header in ("## 시스템 개요", "## 클래스 간 관계", "## 설계 패턴"):
            match = re.search(rf'({header}\s*\n)(.*?)(?=\n## |\Z)', content, re.DOTALL)
            if match:
                sections.append(match.group(1) + match.group(2).strip())

        if sections:
            return "\n\n".join(sections)[:1500]

    return ""


def _get_developer_direction(context_dir: Path, file_path: str) -> str:
    """파일의 [방향] 코멘트를 수집한다."""
    file_stem = Path(file_path).stem
    directions: list = []
    for md_file in context_dir.rglob(f"{file_stem}.md"):
        if DOMAIN_DIR_NAME in str(md_file):
            continue
        try:
            content = md_file.read_text(encoding='utf-8')
            comments = _extract_comments_section(content)
            if comments:
                for cm in re.finditer(r'\[방향\]\s*(.+)', comments):
                    directions.append(cm.group(1).strip())
        except Exception:                                    # noqa: BLE001
            pass
    return "\n".join(f"- {d}" for d in directions) if directions else ""


def _read_source_snippet(repo_dir: Path, file_path: str, issues: list) -> str:
    """이슈 라인 주변의 소스 코드를 읽는다 (최대 2KB)."""
    candidates = list(repo_dir.rglob(Path(file_path).name))
    if not candidates:
        return ""

    try:
        lines = candidates[0].read_text(encoding='utf-8', errors='ignore').splitlines()
    except Exception:                                        # noqa: BLE001
        return ""

    target_lines: set = set()
    for issue in issues:
        ln_m = re.search(r'\d+', issue.line)
        if ln_m:
            ln = int(ln_m.group())
            for offset in range(-5, 6):
                target_lines.add(max(0, ln + offset - 1))

    if not target_lines:
        return "\n".join(lines[:50])

    snippets: list = []
    current_block: list = []
    prev_ln = -10

    for ln in sorted(target_lines):
        if ln >= len(lines):
            continue
        if ln - prev_ln > 3:
            if current_block:
                snippets.append("\n".join(current_block))
                current_block = []
            current_block.append(f"// ... (라인 {ln + 1} 부근)")
        current_block.append(f"{ln + 1:4d} | {lines[ln]}")
        prev_ln = ln

    if current_block:
        snippets.append("\n".join(current_block))

    return "\n\n".join(snippets)[:2000]


def generate_improvement_plans(grouped: dict, context_dir: Path, plans_dir: Path,
                               repo_dir, week_num: str,
                               token_budget: int = PLAN_TOKEN_BUDGET,
                               chat=None, logf=None) -> dict:
    """그룹핑된 이슈를 바탕으로 LLM 개선 플랜을 생성한다.

    반환: {"plans_generated": int, "tokens_used": int, "source_reviews": set}
    `chat(prompt) -> str` 주입은 테스트 자리 — 실전은 상용 체인이다.
    """
    log = logf or (lambda m: None)
    ask = chat or commercial_chat
    week_dir = plans_dir / week_num
    week_dir.mkdir(parents=True, exist_ok=True)

    plans_generated = 0
    tokens_used = 0
    source_reviews: set = set()

    # ── A. 파일별 플랜 (고위험 또는 중위험 3건+) ──
    for file_path, issues in grouped["file_issues"].items():
        high = [i for i in issues if i.severity == "high"]
        mid = [i for i in issues if i.severity == "mid"]

        if not high and len(mid) < 3:
            continue

        if tokens_used >= token_budget:
            log(f"[플랜] 토큰 예산 소진 ({tokens_used:,}/{token_budget:,})")
            break

        target = high + mid
        sev_label = "high" if high else "mid"
        safe_name = re.sub(r'[\\/:*?"<>|\s]', '_', Path(file_path).stem)
        plan_filename = f"{sev_label}_{safe_name}.md"

        domain_ctx = _find_matching_domain(context_dir, [file_path])
        direction = _get_developer_direction(context_dir, file_path)
        direction_notice = ""
        if direction:
            direction_notice = f"\n[개발자 설계 방향]\n{direction}\n"

        source_snippet = ""
        if repo_dir:
            source_snippet = _read_source_snippet(Path(repo_dir), file_path, target)

        issue_list = "\n".join(
            f"- [{i.category}/{i.severity}] 라인 {i.line}: {i.description}"
            + (f" (권장: {i.recommendation})" if i.recommendation else "")
            for i in target
        )

        prompt = (
            f"아래는 코드 리뷰에서 발견된 이슈들이다.\n"
            f"각 이슈에 대해 구체적인 개선 방안을 작성해줘.\n\n"
            f"[대상 파일] {file_path}\n"
            f"[이슈 목록]\n{issue_list}\n"
            f"{direction_notice}"
            + (f"\n[도메인 컨텍스트]\n{domain_ctx}\n" if domain_ctx else "")
            + (f"\n[소스 코드]\n{source_snippet}\n" if source_snippet else "")
            + "\n[금지 규칙]\n"
            f"- 클래스/컴포넌트/함수/UPROPERTY 멤버 변수 리네이밍 제안 금지 (Blueprint 에셋 파괴 위험)\n"
            f"- 클래스 상속 구조 변경 제안 금지\n"
            f"- 모듈 간 코드 이동 제안 금지\n\n"
            f"출력 형식:\n"
            f"## 문제 분석\n(왜 이것이 문제인지)\n\n"
            f"## 수정 방안\n(Before/After 예시 포함)\n\n"
            f"## 영향 범위\n(다른 코드에 미치는 영향)\n\n"
            f"## 우선순위 근거\n(지금 고쳐야 하는 이유)\n"
        )

        try:
            raw = ask(prompt)
        except Exception as e:                               # noqa: BLE001
            log(f"[플랜] LLM 실패 ({plan_filename}): {e}")
            continue
        if not raw:
            continue

        sr = sorted(set(i.source_review for i in target if i.source_review))
        source_reviews.update(sr)

        inherited_id = _inherit_redmine_issue_id(plans_dir, week_num, plan_filename,
                                                 file_path, logf=log)

        plan_md = _build_plan_md(
            week=week_num, category="safety" if high else "convention",
            severity=sev_label, target_file=file_path,
            source_reviews=sr, original_issues=target, plan_body=raw.strip(),
            redmine_issue_id=inherited_id,
        )
        (week_dir / plan_filename).write_text(plan_md, encoding='utf-8')
        plans_generated += 1
        tokens_used += len(prompt) // 4 + len(raw) // 4

    # ── B. 반복 패턴 일괄 플랜 ──
    for pinfo in grouped["pattern_issues"]:
        if tokens_used >= token_budget:
            break

        safe_name = re.sub(r'[\\/:*?"<>|\s]', '_', pinfo["pattern"][:30])
        plan_filename = f"pattern_{safe_name}.md"

        examples = "\n".join(
            f"- {e.file} 라인 {e.line}: {e.description}"
            for e in pinfo["examples"]
        )

        prompt = (
            f"아래는 프로젝트 전체에서 반복적으로 발견되는 코드 패턴 이슈이다.\n"
            f"프로젝트 전체에 적용할 수 있는 일관된 수정 가이드를 작성해줘.\n\n"
            f"[반복 패턴] {pinfo['pattern']}\n"
            f"[해당 파일 수] {len(pinfo['files'])}개\n"
            f"[대표 사례]\n{examples}\n\n"
            f"[금지 규칙]\n"
            f"- 클래스/컴포넌트/함수/UPROPERTY 멤버 변수 리네이밍 제안 금지\n"
            f"- 클래스 상속 구조 변경 제안 금지\n\n"
            f"출력 형식:\n"
            f"## 패턴 분석\n(왜 이것이 문제인지)\n\n"
            f"## 일괄 수정 가이드\n(공통 적용 방법)\n\n"
            f"## 적용 대상 파일 목록\n\n"
            f"## 우선순위 근거\n"
        )

        try:
            raw = ask(prompt)
        except Exception as e:                               # noqa: BLE001
            log(f"[플랜] LLM 실패 ({plan_filename}): {e}")
            continue
        if not raw:
            continue

        sr = sorted(set(i.source_review for i in pinfo["examples"] if i.source_review))
        source_reviews.update(sr)

        inherited_id = _inherit_redmine_issue_id(
            plans_dir, week_num, plan_filename,
            target_file=", ".join(pinfo["files"][:5]), logf=log,
        )

        plan_md = _build_plan_md(
            week=week_num, category="convention", severity="pattern",
            target_file=", ".join(pinfo["files"][:5]),
            source_reviews=sr, original_issues=pinfo["examples"],
            plan_body=raw.strip(),
            redmine_issue_id=inherited_id,
        )
        (week_dir / plan_filename).write_text(plan_md, encoding='utf-8')
        plans_generated += 1
        tokens_used += len(prompt) // 4 + len(raw) // 4

    return {
        "plans_generated": plans_generated,
        "tokens_used": tokens_used,
        "source_reviews": source_reviews,
    }


def _build_plan_md(week: str, category: str, severity: str,
                   target_file: str, source_reviews: list,
                   original_issues: list, plan_body: str,
                   redmine_issue_id: str = "") -> str:
    """개선 플랜 MD 문서를 생성한다."""
    source_list = "\n".join(f"  - {r}" for r in source_reviews)
    issue_summary = "\n".join(
        f"- [{i.review_date}] {i.file} 라인 {i.line}: {i.description} ({i.severity})"
        for i in original_issues[:10]
    )

    redmine_line = f"redmine_issue_id: {redmine_issue_id}\n" if redmine_issue_id else ""

    return (
        f"---\n"
        f"type: improvement_plan\n"
        f"week: {week}\n"
        f"category: {category}\n"
        f"severity: {severity}\n"
        f"target_file: {target_file}\n"
        f"source_reviews:\n{source_list}\n"
        f"status: pending\n"
        f"{redmine_line}"
        f"---\n\n"
        f"## 원본 리뷰 지적\n\n"
        f"{issue_summary}\n\n"
        f"{plan_body}\n"
    )


def _build_weekly_summary(week_num: str, period: str, plans_dir: Path,
                          grouped: dict, plan_result: dict,
                          author_name: str = "") -> str:
    """주간 플랜 요약 문서를 생성한다."""
    week_dir = plans_dir / week_num
    plan_files = [f for f in sorted(week_dir.glob("*.md")) if f.name != "_summary.md"]

    high_plans = [f for f in plan_files if f.name.startswith("high_")]
    mid_plans = [f for f in plan_files if f.name.startswith("mid_")]
    pattern_plans = [f for f in plan_files if f.name.startswith("pattern_")]

    high_table = ""
    if high_plans:
        rows = []
        for pf in high_plans:
            try:
                content = pf.read_text(encoding='utf-8')
                target_m = re.search(r'target_file:\s*(.+)', content)
                target = target_m.group(1).strip() if target_m else pf.stem
            except Exception:                                # noqa: BLE001
                target = pf.stem
            rows.append(f"| {target} | [상세]({pf.name}) |")
        high_table = (
            "\n## 고위험 이슈 (즉시 확인 권장)\n\n"
            "| 파일 | 플랜 |\n|------|------|\n"
            + "\n".join(rows)
        )

    pattern_table = ""
    if pattern_plans:
        rows = []
        for pf in pattern_plans:
            name = pf.stem.replace("pattern_", "")
            rows.append(f"| {name} | [상세]({pf.name}) |")
        pattern_table = (
            "\n## 반복 패턴 (프로젝트 전체)\n\n"
            "| 패턴 | 플랜 |\n|------|------|\n"
            + "\n".join(rows)
        )

    prev_rows: list = []
    for d in sorted(plans_dir.iterdir()):
        if not d.is_dir() or d.name == week_num or not d.name.startswith("20"):
            continue
        pending = 0
        for f in d.glob("*.md"):
            if f.name == "_summary.md":
                continue
            try:
                if "status: pending" in f.read_text(encoding='utf-8', errors='ignore'):
                    pending += 1
            except Exception:                                # noqa: BLE001
                pass
        if pending > 0:
            prev_rows.append(f"| {d.name} | {pending}건 | [보기](../{d.name}/_summary.md) |")

    prev_table = ""
    if prev_rows:
        prev_table = (
            "\n## 미처리 플랜 (이전 주차)\n\n"
            "| 주차 | 미처리 | 링크 |\n|------|--------|------|\n"
            + "\n".join(prev_rows)
        )

    return (
        f"---\n"
        f"type: weekly_plan\n"
        f"week: {week_num}\n"
        f"period: {period}\n"
        f"total_issues: {grouped['total']}\n"
        f"excluded_issues: {grouped['excluded_count']}\n"
        f"plans_generated: {plan_result['plans_generated']}\n"
        f"tokens_used: {plan_result['tokens_used']}\n"
        f"---\n\n"
        f"# 주간 개선 플랜 — {author_name or '전체'} ({week_num})\n\n"
        f"기간: {period}\n\n"
        f"## 요약\n\n"
        f"- 발견 이슈: {grouped['total']}건 "
        f"(코멘트 제외 {grouped['excluded_count']}건)\n"
        f"- 생성 플랜: {plan_result['plans_generated']}건 "
        f"(고위험 {len(high_plans)} / 중위험 {len(mid_plans)} / 패턴 {len(pattern_plans)})\n"
        f"- 토큰 사용: {plan_result['tokens_used']:,}\n"
        f"{high_table}\n{pattern_table}\n{prev_table}\n"
    )


def _update_plan_index(plans_dir: Path, author_name: str = "") -> None:
    """작성자별 플랜 인덱스 (_index.md)를 갱신한다."""
    title = f"# 개선 플랜 인덱스 — {author_name}\n" if author_name else "# 개선 플랜 인덱스\n"
    lines = [
        title,
        f"갱신: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
    ]

    week_dirs = sorted(
        [d for d in plans_dir.iterdir()
         if d.is_dir() and not d.name.startswith("_") and d.name.startswith("20")],
        reverse=True,
    )

    for d in week_dirs[:8]:
        summary = d / "_summary.md"
        if summary.exists():
            try:
                content = summary.read_text(encoding='utf-8')
                plans_m = re.search(r'plans_generated:\s*(\d+)', content)
                count = plans_m.group(1) if plans_m else "?"
                lines.append(f"- [{d.name}]({d.name}/_summary.md) — {count}건")
            except Exception:                                # noqa: BLE001
                lines.append(f"- [{d.name}]({d.name}/_summary.md)")

    (plans_dir / "_index.md").write_text("\n".join(lines), encoding='utf-8')


def _update_global_plan_index(plans_dir: Path) -> None:
    """전체 작성자를 아우르는 글로벌 플랜 인덱스를 갱신한다."""
    lines = [
        "# 개선 플랜 인덱스 (전체)\n",
        f"갱신: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
    ]

    author_dirs = sorted(
        [d for d in plans_dir.iterdir()
         if d.is_dir() and not d.name.startswith("_")],
    )

    for author_dir in author_dirs:
        week_dirs = sorted(
            [d for d in author_dir.iterdir()
             if d.is_dir() and d.name.startswith("20")],
            reverse=True,
        )
        total_plans = 0
        latest_week = ""
        for d in week_dirs:
            summary = d / "_summary.md"
            if summary.exists():
                if not latest_week:
                    latest_week = d.name
                try:
                    content = summary.read_text(encoding='utf-8')
                    plans_m = re.search(r'plans_generated:\s*(\d+)', content)
                    if plans_m:
                        total_plans += int(plans_m.group(1))
                except Exception:                            # noqa: BLE001
                    pass
        if latest_week:
            lines.append(
                f"- **{author_dir.name}**: {len(week_dirs)}주, "
                f"플랜 {total_plans}건 "
                f"([최신]({author_dir.name}/{latest_week}/_summary.md))"
            )

    (plans_dir / "_index.md").write_text("\n".join(lines), encoding='utf-8')
