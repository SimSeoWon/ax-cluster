"""plan_dedup (#155) — 원전 `watcher/plan_dedup.py` 67줄의 이식 (로직 글자대로).

주간 플랜이 매주 같은 파일을 지적할 때 Redmine 이슈가 매주 새로 생기는 것을 막는다 —
직전 N주차에서 같은 키(파일 플랜은 `target_file`, 패턴 플랜은 파일명)를 가진 플랜의
`redmine_issue_id` 를 상속해 **갱신**으로 돌린다.
"""
from __future__ import annotations

import re
from pathlib import Path


def _inherit_redmine_issue_id(plans_dir: Path, current_week: str, plan_filename: str,
                              target_file: str, lookback_weeks: int = 4,
                              logf=None) -> str:
    """직전 N주차에서 동일 키를 가진 플랜의 redmine_issue_id를 찾아 반환.

    매칭 키:
      - file 플랜 (high_*/mid_*): frontmatter `target_file` 일치
      - pattern 플랜 (pattern_*): 파일명 prefix `pattern_<name>` 일치

    찾지 못하면 빈 문자열 반환 (신규 등록).
    """
    log = logf or (lambda m: None)
    if not plans_dir.exists():
        return ""

    is_pattern = plan_filename.startswith("pattern_")

    # 모든 주차 디렉토리를 최신순으로 정렬, 현재 주차 이전 것만 lookback_weeks개 검사
    week_dirs = sorted(
        (d for d in plans_dir.iterdir()
         if d.is_dir() and d.name.startswith("20") and d.name != current_week),
        reverse=True,
    )[:lookback_weeks]

    for wd in week_dirs:
        if is_pattern:
            cand = wd / plan_filename
            if not cand.exists():
                continue
        else:
            # file 플랜: severity prefix가 다를 수 있으므로 모든 high_*/mid_* 검사
            candidates = [f for f in wd.iterdir()
                          if f.is_file() and f.suffix == ".md"
                          and (f.name.startswith("high_") or f.name.startswith("mid_"))]
            cand = None
            for c in candidates:
                try:
                    text = c.read_text(encoding='utf-8')
                except Exception:                            # noqa: BLE001
                    continue
                m = re.search(r'^target_file:\s*(.+)$', text, re.MULTILINE)
                if m and m.group(1).strip() == target_file:
                    cand = c
                    break
            if not cand:
                continue
        # 매칭된 플랜에서 redmine_issue_id 추출
        try:
            text = cand.read_text(encoding='utf-8')
        except Exception:                                    # noqa: BLE001
            continue
        m = re.search(r'^redmine_issue_id:\s*(\S+)\s*$', text, re.MULTILINE)
        if m:
            issue_id = m.group(1).strip()
            log(f"[플랜] redmine_issue_id 상속 ({plan_filename} ← {wd.name}/{cand.name}): "
                f"#{issue_id}")
            return issue_id
    return ""
