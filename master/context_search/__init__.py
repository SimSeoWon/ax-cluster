"""컨텍스트 검색 — 마운트된 프로젝트 기준 (PLAN §5.2-E, §5.5.2).

**기능은 공용이고, 어느 프로젝트를 바라보는가에 따라 어느 디렉토리를 읽을지 분기한다.**
경로 해석이 상수가 아니라 함수(`paths.resolve()`)이므로 마운트 전환에 재기동이 필요 없다.
"""
from .paths import ProjectPaths, resolve, resolve_mounted_only
from .index import ContextIndex, open_index
from .bm25 import Bm25Index
from .search import ContextSearch, Hit, open_search

# `rebuild` 는 지연 로드한다 — `python -m master.context_search.rebuild` 로 실행할 때
# 패키지가 먼저 import 되면서 RuntimeWarning 이 뜨는 것을 피한다.


def __getattr__(name):
    if name == "rebuild_all":
        from .rebuild import rebuild_all
        return rebuild_all
    raise AttributeError(name)

__all__ = [
    "ProjectPaths", "resolve", "resolve_mounted_only",
    "ContextIndex", "open_index", "Bm25Index",
    "ContextSearch", "Hit", "open_search", "rebuild_all",
]
