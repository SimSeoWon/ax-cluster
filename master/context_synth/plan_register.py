"""플랜 MD → Redmine 이슈 등록/갱신 (#155) — 원전 `mcp/redmine_tracker/plan_register.py` 의 이식.

frontmatter 의 `redmine_issue_id` 유무로 create/update 를 가르고, 결과(발급 id·동기화 날짜)를
frontmatter 에 되적는다. plan_dedup 의 상속과 한 쌍 — 같은 파일이 매주 지적돼도 이슈는
하나로 굴러간다.

원전과의 차이: Redmine 호출이 `redmine_tracker.exe` 서브프로세스가 아니라 우리
`master.redmine`(키는 마스터의 컨테이너 DB) 직호출이다 — 원전은 watcher/exe 분리 구조라
exe 경유였고, 우리는 같은 프로세스라 그 간접층이 필요 없다. 트래커는 원전과 같은
「코드리뷰」, 프로젝트도 같은 ModularStage (새 프로젝트 금지 규칙).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .. import redmine

_PLAN_SEVERITY_TO_PRIORITY = {
    "high": "높음",
    "mid": "보통",
    "low": "낮음",
    "pattern": "보통",
}

TRACKER_NAME = "코드리뷰"       # 원전과 동일 — 실재 확인 (2026-08-17)


def _parse_plan_frontmatter(content: str) -> tuple:
    """플랜 MD의 frontmatter(dict)와 본문을 분리한다."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not m:
        return {}, content
    raw_fm, body = m.group(1), m.group(2)

    fm: dict = {}
    current_key = None
    for line in raw_fm.splitlines():
        if line.startswith("  - ") and current_key:
            fm.setdefault(current_key, []).append(line[4:].strip())
            continue
        m2 = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if m2:
            key, val = m2.group(1), m2.group(2).strip()
            if val:
                fm[key] = val
                current_key = None
            else:
                fm[key] = []
                current_key = key
    return fm, body


def _serialize_plan_frontmatter(fm: dict, body: str) -> str:
    """frontmatter dict를 다시 MD 문자열로 합친다."""
    lines = ["---"]
    for key, val in fm.items():
        if isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def _build_plan_issue_subject(fm: dict) -> str:
    """플랜에서 Redmine 이슈 제목을 생성한다."""
    severity = fm.get("severity", "mid")
    target = fm.get("target_file", "")
    category = fm.get("category", "")

    if severity == "pattern":
        short = target.split(",")[0].strip() if target else "반복 패턴"
        subject = f"[플랜] 반복 패턴 — {short}"
    else:
        subject = f"[플랜] {target} — {severity.upper()}"
        if category:
            subject += f" ({category})"

    return subject[:250]


def _find_source_review_file(plan_path: Path, filename: str):
    """active reviews 또는 _archive에서 source review 파일을 찾는다.

    우리 구조: <root>/plans/<author>/<week>/<plan>.md · 리뷰는 <root>/reviews/<author>/.
    (원전은 .claude/ 아래 같은 상대 위상 — 계단 수가 같아 로직 동일)
    """
    try:
        root = plan_path.parent.parent.parent.parent
        author = plan_path.parent.parent.name
        author_reviews = root / "reviews" / author
    except Exception:                                        # noqa: BLE001
        return None
    if not author_reviews.exists():
        return None
    active = author_reviews / filename
    if active.exists():
        return active
    archive_dir = author_reviews / "_archive"
    if archive_dir.exists():
        for week_dir in archive_dir.iterdir():
            if not week_dir.is_dir():
                continue
            cand = week_dir / filename
            if cand.exists():
                return cand
    return None


def _extract_review_section(review_text: str, target_file: str) -> str:
    """리뷰 MD에서 target_file 관련 섹션 또는 라인 컨텍스트를 추출한다. (원전 글자대로)

    추출 단계:
      1) ## 헤더에 target_file이 포함된 섹션 (헤더 기반 리뷰)
      2) 1)에서 파일명만 일치 폴백
      3) 본문에서 target_file/파일명이 등장한 라인 주변 컨텍스트 (카테고리 기반 리뷰)
      4) 그래도 못 찾으면 빈 문자열
    """
    if not review_text or not target_file:
        return ""

    name_only = target_file.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]

    # 1차: ## 헤더에 target_file이 등장하는 섹션
    pattern = re.compile(
        r'^##\s+.*?' + re.escape(target_file) + r'.*?$([\s\S]*?)(?=^##\s|\Z)',
        re.MULTILINE,
    )
    m = pattern.search(review_text)
    if m:
        return m.group(1).strip()

    # 1차 폴백: 파일명만 일치 (경로 없는 헤더)
    if name_only and name_only != target_file:
        pattern2 = re.compile(
            r'^##\s+.*?' + re.escape(name_only) + r'.*?$([\s\S]*?)(?=^##\s|\Z)',
            re.MULTILINE,
        )
        m2 = pattern2.search(review_text)
        if m2:
            return m2.group(1).strip()

    # 2차: 본문 라인 검색 (카테고리 구조 리뷰 대응)
    lines = review_text.splitlines()
    matched: list = []
    for i, line in enumerate(lines):
        if target_file in line:
            matched.append(i)
        elif name_only and name_only != target_file and name_only in line:
            matched.append(i)

    if not matched:
        return ""

    # 인접 매치(<5라인 간격)는 같은 블록으로 병합
    blocks: list = []
    cur_s = cur_e = matched[0]
    for idx in matched[1:]:
        if idx - cur_e < 5:
            cur_e = idx
        else:
            blocks.append((cur_s, cur_e))
            cur_s = cur_e = idx
    blocks.append((cur_s, cur_e))

    # 블록 ±2라인 컨텍스트 추출 (최대 5블록, 합산 4000자 cap)
    chunks: list = []
    total_len = 0
    for s, e in blocks[:5]:
        snippet_s = max(0, s - 2)
        snippet_e = min(len(lines), e + 3)
        snippet = "\n".join(lines[snippet_s:snippet_e]).strip()
        if not snippet:
            continue
        if total_len + len(snippet) > 4000:
            chunks.append(snippet[: max(0, 4000 - total_len)] + "…")
            break
        chunks.append(snippet)
        total_len += len(snippet)

    return "\n\n".join(chunks)


def _build_plan_issue_description(fm: dict, body: str, plan_md_name: str,
                                  plan_path=None) -> str:
    """플랜 MD 내용을 Redmine 이슈 설명으로 변환한다.

    가능하면 source_reviews 파일에서 target_file 섹션을 추출해 description에 인용한다.
    """
    week = fm.get("week", "")
    category = fm.get("category", "")
    severity = fm.get("severity", "")
    target = fm.get("target_file", "")
    source_reviews = fm.get("source_reviews", []) or []

    lines = [
        f"**주차**: {week}",
        f"**심각도**: {severity}",
        f"**분류**: {category}",
        f"**대상**: `{target}`",
        f"**플랜 파일**: `{plan_md_name}`",
    ]
    if source_reviews and plan_path is not None:
        cited_blocks: list = []
        review_paths: list = []
        for sr in source_reviews:
            sr_name = str(sr).strip().lstrip('-').strip()
            if not sr_name:
                continue
            sr_path = _find_source_review_file(plan_path, sr_name)
            if sr_path is None:
                review_paths.append(f"- {sr_name} *(파일 없음 — 보관 만료 가능)*")
                continue
            try:
                rel = sr_path.relative_to(plan_path.parent.parent.parent.parent)
            except Exception:                                # noqa: BLE001
                rel = sr_path
            review_paths.append(f"- `{rel}`")
            try:
                rt = sr_path.read_text(encoding='utf-8', errors='replace')
            except Exception:                                # noqa: BLE001
                continue
            section = _extract_review_section(rt, target)
            if section:
                quoted = "\n".join(f"> {ln}" for ln in section.splitlines())
                cited_blocks.append(f"**{sr_name}**\n\n{quoted}")
        if review_paths:
            lines.append("")
            lines.append("**원본 리뷰 위치**:")
            lines.extend(review_paths)
        if cited_blocks:
            lines.append("")
            lines.append("## 원본 지적 인용")
            lines.append("")
            lines.append("\n\n".join(cited_blocks))
    elif source_reviews:
        lines.append("")
        lines.append("**원본 리뷰**:")
        for sr in source_reviews:
            lines.append(f"- {sr}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(body.strip())

    return "\n".join(lines)


def register_plan(plan_path: Path, *, create=redmine.create_issue,
                  update=redmine.update_issue, logf=None) -> dict:
    """플랜 MD를 Redmine 이슈로 등록하거나 기존 이슈를 갱신한다.

    frontmatter에 redmine_issue_id가 있으면 update, 없으면 create.
    결과를 frontmatter에 다시 기록한다. `create`/`update` 주입은 테스트 자리.
    """
    log = logf or (lambda m: None)
    if not plan_path.exists():
        return {"error": f"플랜 파일을 찾을 수 없음: {plan_path}"}

    try:
        content = plan_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"파일 읽기 실패: {e}"}

    fm, body = _parse_plan_frontmatter(content)
    if fm.get("type") != "improvement_plan":
        return {"error": "개선 플랜 MD가 아님 (frontmatter type 확인)"}

    severity = fm.get("severity", "mid")
    priority_name = _PLAN_SEVERITY_TO_PRIORITY.get(severity, "보통")
    subject = _build_plan_issue_subject(fm)
    description = _build_plan_issue_description(fm, body, plan_path.name, plan_path)

    existing_id = fm.get("redmine_issue_id", "")
    today = datetime.now().strftime("%Y-%m-%d")

    # 기존 이슈 갱신 시도
    if existing_id:
        try:
            issue_id = int(existing_id)
        except (ValueError, TypeError):
            issue_id = None

        if issue_id:
            week = fm.get("week", "")
            result = update(issue_id, notes=f"주간 플랜 갱신 ({week})\n\n{description}")
            if result.startswith("[주의]"):
                return {"error": result}

            fm["redmine_last_sync"] = today
            plan_path.write_text(_serialize_plan_frontmatter(fm, body), encoding="utf-8")
            log(f"[플랜] 갱신 완료 — 이슈 #{issue_id}")
            return {"action": "updated", "issue_id": issue_id}

    # 신규 이슈 생성
    result = create(subject, description, tracker_name=TRACKER_NAME,
                    priority_name=priority_name)
    if "error" in result:
        return result
    new_id = result["id"]

    fm["redmine_issue_id"] = str(new_id)
    fm["redmine_last_sync"] = today
    plan_path.write_text(_serialize_plan_frontmatter(fm, body), encoding="utf-8")

    log(f"[플랜] 생성 완료 — 이슈 #{new_id} '{subject}'")
    return {"action": "created", "issue_id": new_id, "subject": subject}


def register_week_plans(week_dir: Path, author_name: str, *,
                        create=redmine.create_issue, update=redmine.update_issue,
                        logf=None) -> dict:
    """주차 디렉토리의 플랜 MD들을 모두 Redmine에 등록/갱신한다. _summary.md 는 제외."""
    log = logf or (lambda m: None)
    out = {"created": 0, "updated": 0, "errors": []}
    if not week_dir.exists():
        return out

    plan_files = [f for f in sorted(week_dir.glob("*.md")) if f.name != "_summary.md"]
    if not plan_files:
        return out

    for plan_md in plan_files:
        result = register_plan(plan_md, create=create, update=update, logf=logf)
        action = result.get("action")
        if action == "created":
            out["created"] += 1
        elif action == "updated":
            out["updated"] += 1
        elif "error" in result:
            out["errors"].append(f"{plan_md.name}: {result['error']}")

    log(f"[플랜] {author_name}: Redmine 이슈 생성 {out['created']}건, "
        f"갱신 {out['updated']}건"
        + (f", 오류 {len(out['errors'])}건" if out["errors"] else ""))
    for err in out["errors"][:3]:
        log(f"[플랜] {author_name}: Redmine 오류 — {err}")
    return out
