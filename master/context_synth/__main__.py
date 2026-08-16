"""컨텍스트 MD 합성 CLI (중 1.2).

    python -m master.context_synth one   <Source/경로/파일.h>   # 한 그룹만 (검증용)
    python -m master.context_synth fill  [--limit N]            # 문서 없는 그룹만 보충
    python -m master.context_synth all   [--limit N]            # 전체 재생성
    python -m master.context_synth sample [N]                   # [중요] dry-run N개 — 통과율 측정
    python -m master.context_synth status                       # 문서/소스 대비

공통 플래그: --model <이름> · --fallback(.2 의 14b) · --content-limit N · --limit N

[중요] **`--limit` 없이 `all` 을 돌리기 전에 한 그룹으로 품질을 확인할 것.** 1,600 그룹이고
그룹당 수십 초라 전체는 시간 단위 작업이다. 그리고 나쁜 문서 1,600개는 좋은 문서 0개보다
나쁘다 — RAG 가 그걸 근거로 코드를 짜게 된다.
"""
from __future__ import annotations

import sys

from ..context_search.paths import resolve
from ..graph import class_graph as cg
from . import synth


def _status(paths) -> int:
    try:
        srcs = cg.list_source_files(paths)
    except Exception as e:
        print(f"[실패] 소스 목록 실패: {e}")
        return 1
    groups = synth.group(srcs)
    have = sum(1 for k in groups if synth.doc_path(paths, k).is_file())
    docs = len(list(paths.context.rglob("*.md"))) if paths.context.is_dir() else 0
    print(f"[{paths.name}] {paths.context}")
    print(f"  소스 그룹     : {len(groups)}")
    print(f"  문서 있는 그룹: {have}  ({have}/{len(groups)})")
    print(f"  context/ 전체 : {docs} 개 (받아온 스냅샷 포함)")
    print(f"  합성 모델     : {synth.SYNTH_MODEL}")
    return 0


def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "status").lower()
    rest = argv[1:]
    limit = 0
    model = synth.SYNTH_MODEL
    climit = synth.prompt_mod.CONTENT_LIMIT

    def _flag(name, cast, cur):
        nonlocal rest
        if name in rest:
            i = rest.index(name)
            val = cast(rest[i + 1])
            rest = rest[:i] + rest[i + 2:]
            return val
        return cur

    limit = _flag("--limit", int, limit)
    climit = _flag("--content-limit", int, climit)
    model = _flag("--model", str, model)
    if "--fallback" in rest:            # 35B 노드가 죽었을 때 .2 의 14b 로
        rest = [r for r in rest if r != "--fallback"]
        model = synth.FALLBACK_MODEL
    try:
        paths = resolve("")
    except Exception as e:
        print(f"[실패] 프로젝트 해석 실패: {e}")
        return 2

    if cmd == "status":
        return _status(paths)

    if cmd == "one":
        if not rest:
            print("사용법: one <Source/경로/파일.h>")
            return 2
        key = str(__import__("pathlib").Path(rest[0]).parent
                  / __import__("pathlib").Path(rest[0]).stem)
        files = sorted(synth.group([rest[0]])[key])
        r = synth.synthesize_group(paths, key, files, model=model, content_limit=climit)
        if not r.written:
            print(f"[실패] {key} — {r.reason}")
            return 1
        out = synth.doc_path(paths, key)
        print(f"[완료] {out} · {r.chars}자 · 프롬프트 {r.prompt_chars}자 · {r.elapsed_ms}ms")
        print("─" * 60)
        print(out.read_text(encoding="utf-8"))
        return 0

    if cmd == "sample":
        n = int(rest[0]) if rest else 8
        # [중요] 쓰지 않는다 — 받아온 스냅샷을 지키면서 모델 적합도만 잰다.
        st = synth.run(paths, limit=n, dry_run=True, model=model, content_limit=climit,
                       progress=lambda m: print(m, flush=True))
        print(f"\n사실 게이트 통과율: {st.pass_rate}  ({st.summary})")
        for r in st.results:
            if r.lost:
                print(f"   [중요] {r.key} — {r.reason[:150]}")
        return 0

    if cmd in ("fill", "all"):
        try:
            st = synth.run(paths, skip_existing=(cmd == "fill"), limit=limit, model=model,
                           content_limit=climit, progress=lambda m: print(m, flush=True))
        except (synth.SynthError, Exception) as e:
            if isinstance(e, synth.SynthError):
                print(f"[실패] {e}")
                return 1
            raise
        print(f"{'[주의]' if st.lost else '[완료]'} [{paths.name}] {st.summary}")
        # [중요] 유실을 목록으로 남긴다 — 숫자만 보면 어느 문서가 없는지 모른다.
        for r in st.results:
            if r.lost:
                print(f"   [중요] {r.key} — {r.reason[:140]}")
        return 1 if (st.lost or st.aborted) else 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
