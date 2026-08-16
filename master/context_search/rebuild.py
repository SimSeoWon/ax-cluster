"""전체 재색인 — **두 채널을 함께 뒤집는다** (PLAN §5.4.6).

🔴 **왜 조정자가 따로 필요한가.** 벡터와 BM25 는 각자 재색인할 수 있지만, 각자 뒤집으면
그 사이에 **벡터는 새 세대·BM25 는 옛 세대**인 순간이 생긴다. 검색은 둘을 RRF 로 섞으므로
그 순간의 결과는 **어느 세대도 아닌 것**이 된다. 그래서 순서를 고정한다:

    ① 벡터를 work 세대에 쌓는다   (swap 하지 않는다)
    ② BM25 를 work 세대에 쌓는다  (swap 하지 않는다)
    ③ 마커를 한 번 뒤집는다        ← 여기서만 Live 가 바뀐다

**①·② 중 어디서 죽어도 마커가 그대로이므로 옛 세대가 온전히 살아 있다.** 실패가
빈 색인을 노출하지 않는다 — 이 저장소의 fail-closed 와 같은 방향이다(§9.5.6).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import domain_index, generation
from .bm25 import FTS5_AVAILABLE, Bm25Index
from .index import ContextIndex
from .paths import ProjectPaths, resolve


@dataclass
class RebuildStats:
    project: str
    vector_docs: int
    bm25_docs: int
    generation: str
    elapsed_sec: float
    domains: int = 0            # 도메인 색인 건수 (소 2.1.1)
    domain_note: str = ""       # 건너뛴·실패한 사유

    def summary(self) -> str:
        bm = f"{self.bm25_docs}건" if FTS5_AVAILABLE else "없음(FTS5 미지원)"
        s = (f"{self.project}: 벡터 {self.vector_docs}건 · BM25 {bm} "
             f"→ 세대 {self.generation} ({self.elapsed_sec:.1f}s)")
        s += f" · 도메인 {self.domains}건"
        if self.domain_note:
            s += f" ({self.domain_note})"
        return s


def _canary(paths: ProjectPaths, note: str) -> None:
    """🔴 **여기서 삼킨 실패는 self-heal 되지 않는다** (소 3.5.6 · `#182`).

    위 `try` 는 도메인 색인 실패를 `note` 로 바꾸고 **정상 반환**한다 — 그래서 호출자
    (`events/consumer`)는 재색인을 성공으로 보고 **digest 와 워터마크를 전진시킨다.**
    그리고 재색인은 *"컨텍스트 MD 가 바뀔 때만"* 도므로, 소스만 바뀌는 푸시가 이어지는 동안
    도메인 색인은 **깨진 채로 남는다.** 원전의 승격 기준(*"skip 후 워터마크가 전진하느냐"*)에
    정확히 걸리는 자리다.

    ⚠️ **fail-soft 는 그대로 둔다** — 도메인 색인이 죽어도 컨텍스트 검색은 멀쩡하고, 그래서
    여기가 fail-soft 인 것은 옳다. 바꾸는 것은 *"조용히"* 뿐이다.
    """
    from ..canary import KIND_DOMAIN_INDEX_GAP, append_canary
    append_canary(paths, kind=KIND_DOMAIN_INDEX_GAP, detail=note)


def rebuild_all(paths: ProjectPaths, *, progress=None) -> RebuildStats:
    """벡터·BM25 를 work 세대에 모두 쌓은 뒤 **한 번만** 뒤집는다."""
    missing = paths.missing_sources()
    if missing:
        # 있는 그대로 막는다 — 원본이 없는데 빈 색인을 만들면 "검색해도 안 나온다" 가
        # 색인 실패인지 정말 없는 것인지 구분되지 않는다.
        raise FileNotFoundError("색인할 수 없다:\n  - " + "\n  - ".join(missing))

    t0 = time.monotonic()
    vector = ContextIndex(paths)
    work = vector.work_name

    if progress:
        progress(f"벡터 → 세대 {work}")
    v_stats = vector.rebuild(swap=False)

    bm = Bm25Index(paths, gen=vector.live_name)
    try:
        if progress:
            progress(f"BM25 → 세대 {work}")
        n_bm = bm.rebuild_into(work)
    finally:
        bm.close()

    # ③ 여기서만 Live 가 바뀐다.
    generation.write(paths.root, work)
    if progress:
        progress(f"세대 전환 {vector.live_name} → {work}")

    # ④ 도메인(온톨로지) 색인 — 소 2.1.1. **별도 DB·별도 컬렉션**이라 위 세대 전환과
    #    무관하고, 실패해도 컨텍스트 검색은 멀쩡하다. 그래서 여기서만 fail-soft 다.
    #    🔴 **삼키지는 않는다** — 사유를 `domain_note` 로 들고 나와 요약에 찍는다.
    #    지문이 같으면 스스로 건너뛴다(소 2.1.3) — 매 푸시마다 다시 만들지 않는다.
    domains, note = 0, ""
    try:
        d = domain_index.sync(paths, progress=progress)
        domains = d.synced or d.bm25_count
        note = " / ".join(d.notes[:1])
    except domain_index.DomainIndexError as e:
        note = f"🔴 도메인 색인 실패: {e}"
        _canary(paths, note)
    except Exception as e:                              # noqa: BLE001
        note = f"🔴 도메인 색인 오류: {type(e).__name__}: {e}"
        _canary(paths, note)
    if progress and note:
        progress(f"도메인 색인 — {note}")

    return RebuildStats(project=paths.name, vector_docs=v_stats.documents,
                        bm25_docs=n_bm, generation=work,
                        elapsed_sec=time.monotonic() - t0,
                        domains=domains, domain_note=note)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="컨텍스트 색인 전체 재구축 (벡터 + BM25)")
    ap.add_argument("project", nargs="?", default="", help="비우면 마운트된 프로젝트")
    args = ap.parse_args(argv)

    paths = resolve(args.project)
    print(f"[재색인] {paths.name} — {paths.context}")
    stats = rebuild_all(paths, progress=lambda m: print(f"  {m}"))
    print(f"[완료] {stats.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
