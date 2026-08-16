"""생산자③ 작업 기록(history) (#207) — 원전 α′ 규약의 이식.

원전 규약 (`project_claude_md.py` 「작업 히스토리 작성 규약」): 비자명한 의사결정·아키텍처
변경 직후 `.claude/history/YYYY-MM-DD_HHMM_<작업요약>.md` 를 frontmatter 의무 필드로 남긴다.
**이 history 는 온톨로지 시드의 1순위 원천**이고, 소비자(`history_harvest.py`, `#158`)가
frontmatter 를 직접 읽어 narrative 컨텍스트로 쓴다.

우리 적재 지점 둘 (#206 신호와 같은 미러 구조):
    파이프라인   work 이 merged/rejected 로 **종결될 때** 큐가 자동 기록 — 완주의 사실 기록
    요청자(.33)  비자명한 결정 직후 클라 MCP `log_history` → 8101 `POST /api/v1/history`
                (마스터 대행 — history 는 마스터의 트윈 디렉토리에 있다)

[중요] **frontmatter 는 원전 미니 파서(`_parse_simple_frontmatter`)가 읽을 수 있는 형태로만
쓴다** — 실측한 함정: 그 파서는 인라인 리스트(`[a, b]`)를 못 읽는다(스칼라 문자열이 되어
`isinstance(list)` 검사에서 통째로 버려진다). 리스트는 반드시 대시(`- item`) 형태로, 빈
리스트는 `key:` 뒤를 비워 둔다. user_quote 는 block scalar(`|`)다.

decision_type 은 원전 enum: architecture | policy | experiment | revert | bugfix | refactor |
infra — 그리고 소비자의 폴백이자 접두 매핑에 실재하는 "feature". 그 밖의 값은 막는다.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

HISTORY_DIRNAME = "history"

DECISION_TYPES = ("architecture", "policy", "experiment", "revert",
                  "bugfix", "refactor", "infra", "feature")

_SAFE = re.compile(r'[\\/:*?"<>|\s]+')


def history_dir(paths) -> Path:
    return Path(paths.root) / HISTORY_DIRNAME


def _yaml_list(key: str, items) -> list:
    """[중요] 대시 리스트만 — 원전 미니 파서는 인라인 `[a, b]` 를 못 읽는다 (실측)."""
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not items:
        return [f"{key}:"]
    return [f"{key}:"] + [f"  - {x}" for x in items]


def _yaml_scalar(key: str, value: str) -> str:
    v = (value or "").strip()
    return f"{key}: \"{v}\"" if v else f"{key}: null"


def render(*, title: str, decision_type: str = "feature", date: datetime | None = None,
           work_id: str = "", session_id: str = "", affected_classes=(),
           affected_domains=(), supersedes: str = "", alternatives_considered=(),
           tags=(), user_quote: str = "", body: str = "") -> str:
    """원전 frontmatter 블록 + 본문. 파일명이 아니라 **내용**을 만든다 — 저장은 write()."""
    if not (title or "").strip():
        raise ValueError("title 은 필수다")
    if decision_type not in DECISION_TYPES:
        raise ValueError(f"decision_type 은 {DECISION_TYPES} 중 하나다: {decision_type!r}")
    ts = date or datetime.now()
    lines = [
        "---",
        f"date: {ts.strftime('%Y-%m-%d %H:%M')}",
        _yaml_scalar("work_id", work_id),
        _yaml_scalar("session_id", session_id),
        f"decision_type: {decision_type}",
        *_yaml_list("affected_classes", affected_classes),
        *_yaml_list("affected_domains", affected_domains),
        _yaml_scalar("supersedes", supersedes),
        *_yaml_list("alternatives_considered", alternatives_considered),
        *_yaml_list("tags", tags),
    ]
    q = (user_quote or "").strip()
    if q:
        lines.append("user_quote: |")
        lines += [f"  {ln}" for ln in q.splitlines()]
    else:
        lines.append("user_quote: null")
    lines += ["---", "", f"# {title.strip()}", ""]
    if (body or "").strip():
        lines.append(body.strip())
        lines.append("")
    return "\n".join(lines)


def write(paths, content: str, *, title: str, date: datetime | None = None) -> str:
    """`history/YYYY-MM-DD_HHMM_<작업요약>.md` 로 저장 (원전 파일명 규약 그대로)."""
    ts = date or datetime.now()
    slug = _SAFE.sub("_", title.strip()).strip("_")[:48] or "record"
    d = history_dir(paths)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ts.strftime('%Y-%m-%d_%H%M')}_{slug}.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


def classes_from_files(files) -> list:
    """소스 경로에서 클래스명 후보 (best-effort) — `Source/M/UHitBox.cpp` → `UHitBox`.

    원전 규약은 「CamelCase 식별자만」이다. 파일 스템이 클래스명과 다른 경우를 여기서 알 수
    없으므로 후보일 뿐이고, 소비자(#158)의 BM25 매칭 토큰으로 쓰인다 — 없는 것보다 낫다.
    """
    out, seen = [], set()
    for f in files or ():
        stem = Path(str(f)).stem
        if re.fullmatch(r'[A-Z][A-Za-z0-9]*', stem) and stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def record_work_terminal(paths, work: dict, tasks: list, merge_status: str) -> str:
    """파이프라인 자동 기록 — work 종결(merged/rejected) 시 큐가 부른다.

    사실만 적는다: 제목·결정·태스크 수·파일. user_quote 는 요청자의 검수 노트
    (review_decision.notes — 사람의 발화라 WHY 신호다). 실패해도 종결을 막지 않는 것은
    호출자(fail-soft)의 몫이고, 여기는 정직하게 예외를 낸다.
    """
    work = work or {}
    title = (work.get("title") or work.get("work_id") or "무제 work").strip()
    decision = work.get("review_decision") or {}
    files = []
    for t in tasks or ():
        # 실측 스키마 — task 레코드는 target_file/header_file **단수**다 (title 은 없다)
        for f in (t.get("target_file"), t.get("header_file")):
            if f and f not in files:
                files.append(f)
    body_lines = [
        "## 작업 개요",
        f"- work: `{work.get('work_id', '')}` — {title}",
        f"- 종결: **{merge_status}**"
        + (f" · 판정자 {decision.get('decided_by')}" if decision.get("decided_by") else "")
        + (f" · {decision.get('decided_at')}" if decision.get("decided_at") else ""),
        f"- 태스크 {len(tasks or ())}건",
        "",
        "## 수정된 파일 목록",
        *([f"- `{f}`" for f in files] or ["- (기록된 파일 없음)"]),
    ]
    return write(paths, render(
        title=title,
        decision_type="feature",
        work_id=str(work.get("work_id") or ""),
        affected_classes=classes_from_files(files),
        tags=["pipeline", merge_status],
        user_quote=str(decision.get("notes") or ""),
        body="\n".join(body_lines),
    ), title=title)
