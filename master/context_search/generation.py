"""색인 세대 포인터 — 벡터·BM25 **두 채널이 공유한다** (PLAN §5.4.6).

[중요] **원본에 없던 것을 더했다. 두 가지 이유가 있다.**

**① 프로세스가 갈렸다.** AgentTest 는 부팅 때 무조건 `context_a` 를 Live 로 잡는다
(`double_buffered_index.py:40~42`). 거기서는 문제가 안 됐다 — 상주 데몬이라 기동 직후
재색인하고 스왑하므로 포인터가 프로세스 수명 안에서만 의미가 있었다. 여기서는
**색인하는 쪽(이벤트 큐 소비자)과 검색하는 쪽이 다른 프로세스**다. 그대로 두면 재색인 후
서비스가 재기동되는 순간 **빈 `context_a` 를 보고 검색이 0건을 반환한다** — 실측했다
(2026-08-08, 961건 색인 직후 새 프로세스에서 `count()==0`). 조용히 실패하는 종류다.

**② 두 채널의 세대가 어긋나면 안 된다.** 검색은 벡터와 BM25 를 RRF 로 융합한다.
채널마다 포인터를 따로 두면 벡터는 새 세대, BM25 는 옛 세대를 보는 상태가 생기고
**융합 결과가 어느 세대도 아닌 것이 된다.** 포인터를 하나로 묶어 그 상태를 없앤다.

그래서 재색인은 **두 채널을 모두 work 세대에 쌓은 뒤 마지막에 한 번 뒤집는다**
(`rebuild.py`). 중간에 죽으면 포인터가 안 바뀌었으므로 **옛 세대가 그대로 살아 있다** —
fail-closed 와 같은 방향이다.
"""
from __future__ import annotations

import json
from pathlib import Path

MARKER = "index_live.json"

A = "a"
B = "b"


def other(name: str) -> str:
    return B if name == A else A


def marker_path(root: Path) -> Path:
    return root / MARKER


def read(root: Path) -> str | None:
    """현재 Live 세대. 마커가 없거나 깨졌으면 `None` — **추측하지 않는다.**

    호출자가 실제 데이터를 보고 자가 복구한다(어느 컬렉션에 문서가 많은지 등).
    여기서 임의로 `"a"` 를 돌려주면 그 복구 기회를 뺏는다.
    """
    try:
        name = json.loads(marker_path(root).read_text(encoding="utf-8"))["live"]
    except Exception:
        return None
    return name if name in (A, B) else None


def write(root: Path, name: str) -> None:
    """원자적 교체 — 쓰는 도중 죽어도 반쪽 파일이 남지 않는다."""
    if name not in (A, B):
        raise ValueError(f"세대 이름이 잘못됐다: {name!r}")
    root.mkdir(parents=True, exist_ok=True)
    tmp = marker_path(root).with_suffix(".tmp")
    tmp.write_text(json.dumps({"live": name}), encoding="utf-8")
    tmp.replace(marker_path(root))
