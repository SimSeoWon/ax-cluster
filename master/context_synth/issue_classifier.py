"""소비자 issue_classifier (#156) — 원전 `watcher/issue_classifier.py` 124줄의 이식.

수집된 리뷰 이슈를 ① 코멘트 확인분 제외 ② 중복 제거 ③ 파일별 그룹핑 ④ 반복 패턴 탐지로
정리한다. 후속 소비자(planner `#155`)가 이 그룹핑 결과에서 주간 계획을 만든다.

원전과의 차이 둘 (둘 다 import 대체이지 로직 변경이 아니다):
    common.DOMAIN_DIR_NAME       → 상수 "_domains" (우리 트윈도 같은 이름 — 실측)
    context._extract_comments_section → 4줄 함수를 여기로 (원전 context.py:107)

[중요] 코멘트 제외의 원천은 컨텍스트 MD 의 `## 코멘트` 섹션 `[리뷰]` 표기다 — 사람이
"이 지적은 확인했다"고 남긴 것을 매주 다시 들이밀지 않기 위한 장치. 우리 트윈의 받아온
스냅샷에도 이 섹션이 실재한다 (실측 2026-08-17).
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .review_collector import ReviewIssue

DOMAIN_DIR_NAME = "_domains"

PATTERN_MIN_FILES = 3        # 반복 패턴 최소 파일 수
DEDUP_LINE_RANGE = 5         # 중복 판정 라인 범위 (±5)


def _extract_comments_section(md_content: str) -> str:
    """MD 파일에서 ## 코멘트 섹션을 추출한다. 없으면 빈 문자열 반환. (원전 context.py:107)"""
    match = re.search(r'(## 코멘트\s*\n.*)', md_content, re.DOTALL)
    return match.group(1).rstrip() if match else ""


def group_issues(issues: list, context_dir: Path) -> dict:
    """이슈를 파일별/패턴별로 그룹핑하고 코멘트 확인 이슈를 제외한다.

    반환: {
        "file_issues": {file: [ReviewIssue]},
        "pattern_issues": [{"pattern", "files", "severity", "examples", "count"}],
        "excluded_count": int,
        "total": int,
    }
    """
    excluded = 0
    filtered: list[ReviewIssue] = []

    # 코멘트 기반 제외 캐시: {file_stem: {acknowledged keywords}}
    comment_cache: dict[str, set] = {}

    for issue in issues:
        file_stem = Path(issue.file).stem

        if file_stem not in comment_cache:
            exclusions: set = set()
            for md_file in context_dir.rglob(f"{file_stem}.md"):
                if DOMAIN_DIR_NAME in str(md_file):
                    continue
                try:
                    content = md_file.read_text(encoding='utf-8')
                    comments = _extract_comments_section(content)
                    if comments:
                        for cm in re.finditer(
                            r'\[리뷰\]\s*(.+?)(?:\(|$)', comments, re.MULTILINE
                        ):
                            text = cm.group(1).strip().lower()
                            # C++ 식별자 + 한국어 단어를 키워드로 추출
                            for token in re.findall(
                                r'[a-zA-Z_][a-zA-Z0-9_]*|[가-힣]+', text
                            ):
                                if len(token) >= 3:
                                    exclusions.add(token)
                except Exception:                            # noqa: BLE001
                    pass
            comment_cache[file_stem] = exclusions

        excl = comment_cache.get(file_stem, set())
        if excl and any(kw in issue.description.lower() for kw in excl):
            excluded += 1
            continue

        filtered.append(issue)

    # 중복 제거: 같은 파일 + 같은 라인 버킷 + 같은 카테고리 -> 최신만
    deduped: list[ReviewIssue] = []
    seen: set = set()
    filtered.sort(key=lambda i: i.review_date, reverse=True)
    for issue in filtered:
        line_num = 0
        ln_m = re.search(r'\d+', issue.line)
        if ln_m:
            line_num = int(ln_m.group())
        line_bucket = line_num // DEDUP_LINE_RANGE * DEDUP_LINE_RANGE
        key = f"{issue.file}|{line_bucket}|{issue.category}"
        if key not in seen:
            seen.add(key)
            deduped.append(issue)

    # 파일별 그룹핑
    file_issues: dict[str, list] = defaultdict(list)
    for issue in deduped:
        file_issues[issue.file].append(issue)

    # 반복 패턴 탐지
    desc_counter: dict[str, list] = defaultdict(list)
    for issue in deduped:
        key = issue.description.split(":")[0].strip() if ":" in issue.description \
            else issue.description[:30]
        desc_counter[key].append(issue)

    patterns = []
    for pattern_key, pattern_list in desc_counter.items():
        unique_files = list(set(i.file for i in pattern_list))
        if len(unique_files) >= PATTERN_MIN_FILES:
            severities = [i.severity for i in pattern_list]
            if "high" in severities:
                psev = "high"
            elif "mid" in severities:
                psev = "mid"
            else:
                psev = "low"
            patterns.append({
                "pattern": pattern_key,
                "files": unique_files,
                "severity": psev,
                "examples": pattern_list[:5],
                "count": len(pattern_list),
            })

    return {
        "file_issues": dict(file_issues),
        "pattern_issues": patterns,
        "excluded_count": excluded,
        "total": len(deduped),
    }
