"""소비자 review_collector (#156) — 원전 `watcher/review_collector.py` 137줄의 이식.

생산자①(`review_gen.py`)이 쓴 `reviews/<작성자>/*.md` 를 구조화된 이슈 목록으로 파싱한다.
[중요] **이 파서가 생산자의 형식 계약 그 자체다** — `review_gen.parseable_rows`/`format_ok` 가
이 정규식을 기준으로 만들어졌고, 여기가 바뀌면 생산자 검증기도 같이 바뀌어야 한다.

원전과의 차이: 없음 (파싱 로직 글자대로). 타입 힌트 표기만 우리 파이썬에 맞췄다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReviewIssue:
    file: str
    line: str
    category: str          # "convention" | "safety"
    severity: str          # "high" | "mid" | "low"
    description: str
    recommendation: str
    review_date: str
    commit_hash: str
    module: str
    source_review: str = ""  # 원본 리뷰 파일명


def _normalize_severity(raw: str) -> str:
    """심각도를 정규화: 높음/상/High->high, 중간/중/Medium->mid, 나머지->low."""
    raw = raw.strip().lower()
    if raw in ("높음", "high", "상"):
        return "high"
    if raw in ("중간", "medium", "중"):
        return "mid"
    return "low"


def parse_review_reports(author_reviews_dir: Path, since_date: str) -> list:
    """특정 작성자의 리뷰 MD 파일들을 파싱하여 구조화된 이슈 목록을 반환한다.

    author_reviews_dir: 작성자별 리뷰 디렉토리 (reviews/<author>/)
    since_date: 'YYYY-MM-DD' 형식, 이 날짜 이후의 리뷰만 수집.
    """
    issues: list[ReviewIssue] = []

    for rf in sorted(author_reviews_dir.glob("*.md")):
        if rf.name.startswith("_"):
            continue
        date_part = rf.stem[:10]
        if date_part < since_date:
            continue

        try:
            content = rf.read_text(encoding='utf-8')
        except Exception:                                    # noqa: BLE001
            continue

        hash_m = re.search(r'커밋:\s*`([a-f0-9]+)`', content)
        commit_hash = hash_m.group(1) if hash_m else ""

        # 모듈 섹션 분리 (### 헤더 기준)
        module_blocks = re.split(r'^###\s+', content, flags=re.MULTILINE)

        for block in module_blocks[1:]:
            first_line = block.split('\n', 1)[0]
            module_name = first_line.strip().rstrip('/')

            # 컨벤션 섹션 위치
            conv_start = None
            for pattern in (r'코딩\s*컨벤션', r'##\s*1\.'):
                m = re.search(pattern, block)
                if m:
                    conv_start = m.start()
                    break

            # 안전성 섹션 위치
            safety_start = None
            for pattern in (r'버그', r'안전성', r'##\s*2\.'):
                m = re.search(pattern, block)
                if m:
                    safety_start = m.start()
                    break

            if conv_start is not None:
                conv_end = safety_start if safety_start else len(block)
                _parse_table_rows(
                    block[conv_start:conv_end], "convention",
                    module_name, date_part, commit_hash, rf.name, issues,
                )

            if safety_start is not None:
                _parse_table_rows(
                    block[safety_start:], "safety",
                    module_name, date_part, commit_hash, rf.name, issues,
                )

    return issues


def _parse_table_rows(text: str, category: str, module: str,
                      date: str, commit: str, source_file: str,
                      out_list: list) -> None:
    """마크다운 테이블 행을 파싱하여 ReviewIssue로 변환한다."""
    for m in re.finditer(
        r'\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*'
        r'\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|',
        text,
    ):
        vals = [v.strip() for v in m.groups()]
        # 헤더/구분선 건너뛰기
        if vals[0] in ("파일", "") or any("---" in v for v in vals[:2]):
            continue

        if category == "convention":
            # | 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
            out_list.append(ReviewIssue(
                file=vals[0], line=vals[3],
                category="convention",
                severity=_normalize_severity(vals[4]),
                description=f"{vals[1]}: {vals[2]}",
                recommendation="",
                review_date=date, commit_hash=commit,
                module=module, source_review=source_file,
            ))
        else:
            # | 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
            out_list.append(ReviewIssue(
                file=vals[0], line=vals[2],
                category="safety",
                severity=_normalize_severity(vals[1]),
                description=vals[3],
                recommendation=vals[4],
                review_date=date, commit_hash=commit,
                module=module, source_review=source_file,
            ))
