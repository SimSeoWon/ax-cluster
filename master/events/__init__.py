"""이벤트 큐 — Gitea 훅과 색인기 사이의 영속 스풀 (PLAN §5.4.5, §5.4.5-a)."""

from .spool import (  # noqa: F401
    Batch,
    Event,
    Spool,
    SpoolError,
    coalesce,
)
