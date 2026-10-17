"""소비자 review_collector (#156) — 원전 `watcher/review_collector.py` 137줄의 이식.

생산자①(`review_gen.py`)이 쓴 `reviews/<작성자>/*.md` 를 구조화된 이슈 목록으로 파싱한다.
[중요] **이 파서가 생산자의 형식 계약 그 자체다** — `review_gen.parseable_rows`/`format_ok` 가
이 정규식을 기준으로 만들어졌고, 여기가 바뀌면 생산자 검증기도 같이 바뀌어야 한다.

원전과의 차이 하나 (`#815` ④): 「## 4. 골조 지시 이행」 절. 안전성 표는 그 절 앞에서 끊는다
(끊지 않으면 4절 행이 안전성으로 새어 든다). 4절 행은 `include_intent=True` 일 때만
`category="intent"` 로 낸다 — 기본값은 빼는 쪽이라 주간 플랜(`planner`)은 종전 그대로 읽는다.
4절이 없는 리뷰는 파싱 결과가 종전과 같다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReviewIssue:
    file: str
    line: str
    category: str          # "convention" | "safety" | "intent"(#815 ④)
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


# `#815` ④ — 4절 머리. 「## 4.」 만으로 잡지 않는다 — 다른 4절이 있는 리뷰의 번호를 흔들지 않게
_INTENT_SECTION = re.compile(r'^##\s*4\.\s*골조\s*지시\s*이행', re.MULTILINE)


def _intent_severity(kind: str) -> str:
    """구분 → 심각도. 불이행 = mid(게이트를 지난 동작 이탈) · 골조 모순 = low(코드는 동결 쪽을 따랐다,
    고칠 곳은 골조) · 모르는 값도 low — 원문은 설명에 그대로 남는다."""
    if "모순" in kind:
        return "low"
    if "불이행" in kind:
        return "mid"
    return "low"


def parse_review_reports(author_reviews_dir: Path, since_date: str, *,
                         include_intent: bool = False) -> list:
    """특정 작성자의 리뷰 MD 파일들을 파싱하여 구조화된 이슈 목록을 반환한다.

    author_reviews_dir: 작성자별 리뷰 디렉토리 (reviews/<author>/)
    since_date: 'YYYY-MM-DD' 형식, 이 날짜 이후의 리뷰만 수집.
    include_intent: 4절(골조 지시 이행) 행도 낸다 — 수정 항목 색인(`fix_index`)만 켠다.
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

            # 4절 위치 (#815 ④) — 없으면 None 이고 아래 두 표의 범위는 종전과 같다
            im = _INTENT_SECTION.search(block)
            intent_start = im.start() if im else None

            if conv_start is not None:
                conv_end = safety_start if safety_start else len(block)
                if intent_start is not None and conv_start < intent_start < conv_end:
                    conv_end = intent_start
                _parse_table_rows(
                    block[conv_start:conv_end], "convention",
                    module_name, date_part, commit_hash, rf.name, issues,
                )

            if safety_start is not None:
                safety_end = len(block)
                if intent_start is not None and intent_start > safety_start:
                    safety_end = intent_start
                _parse_table_rows(
                    block[safety_start:safety_end], "safety",
                    module_name, date_part, commit_hash, rf.name, issues,
                )

            if include_intent and intent_start is not None:
                ends = [x for x in (conv_start, safety_start)
                        if x is not None and x > intent_start]
                _parse_table_rows(
                    block[intent_start:min(ends) if ends else len(block)], "intent",
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
        elif category == "intent":
            # | 파일 | 지시([PSEUDO]) | 실제 구현 | 라인 | 구분 | — 목록 화면이 분류 칸을 안 그리므로 설명이 스스로 밝힌다
            out_list.append(ReviewIssue(
                file=vals[0], line=vals[3],
                category="intent",
                severity=_intent_severity(vals[4]),
                description=f"골조 지시 이행({vals[4]}): 지시 「{vals[1]}」 · 실제 「{vals[2]}」",
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
