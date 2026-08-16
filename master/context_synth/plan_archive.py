"""리뷰 아카이브 (#155) — 원전 `watcher/archive.py` 62줄의 이식 (로직 글자대로).

플랜에 반영된 리뷰는 `reviews/<작성자>/_archive/<주차>/` 로 이동한다 — 다음 주 플랜이
같은 리뷰를 다시 세지 않기 위한 장치이고, 소비자 파서의 `_` 접두 스킵과 한 쌍이다.
[주의] 파일명은 원전의 `archive.py` 가 아니라 `plan_archive.py` 다 — `master/ontology/` 쪽
이식과의 이름 충돌을 피했을 뿐 내용은 같다.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

ARCHIVE_RETENTION_WEEKS = 4  # 아카이브 보관 주수


def archive_reviews(author_reviews_dir: Path, source_reviews: set, week_num: str,
                    logf=None) -> int:
    """플랜에 반영된 리뷰 파일을 작성자 디렉토리 내 _archive/YYYY-WNN/으로 이동한다.

    보관 기간 초과 아카이브는 자동 삭제. 반환: 이동한 파일 수.
    """
    log = logf or (lambda m: None)
    if not source_reviews:
        return 0

    archive_base = author_reviews_dir / "_archive"
    week_archive = archive_base / week_num
    week_archive.mkdir(parents=True, exist_ok=True)

    moved = 0
    for review_name in source_reviews:
        src = author_reviews_dir / review_name
        if src.exists():
            dst = week_archive / review_name
            src.rename(dst)
            moved += 1

    if moved:
        log(f"[플랜] 리뷰 아카이브 ({author_reviews_dir.name}): {moved}건 -> "
            f"_archive/{week_num}/")

    _cleanup_old_archives(archive_base, logf=logf)
    return moved


def _cleanup_old_archives(archive_base: Path, logf=None) -> None:
    """보관 기간이 지난 아카이브 폴더를 삭제한다."""
    log = logf or (lambda m: None)
    if not archive_base.exists():
        return

    cutoff = datetime.now() - timedelta(weeks=ARCHIVE_RETENTION_WEEKS)
    cutoff_week = cutoff.strftime("%Y-W%W")

    for d in sorted(archive_base.iterdir()):
        if d.is_dir() and d.name < cutoff_week:
            shutil.rmtree(d, ignore_errors=True)
            log(f"[플랜] 만료 아카이브 삭제: {d.name}")
