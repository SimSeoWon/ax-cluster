"""관계 그래프 CLI.

    .venv/bin/python -m master.graph build        # 둘 다 풀 스캔 (마운트된 프로젝트)
    .venv/bin/python -m master.graph status       # 건수만
    .venv/bin/python -m master.graph build class  # 상속 그래프만
    .venv/bin/python -m master.graph build dep    # 의존 그래프만

`data-schema.md` 가 이 DB 의 복구를 *"파일 삭제 → 재기동 시 풀 스캔"* 이라고 적어 둔 것을
여기서는 **명시 명령**으로 바꿨다. 우리 색인기는 상주 데몬이 아니라 이벤트로 깨어나는
oneshot 이라 "재기동" 이라는 순간이 없다 — 자동 감지에 기대면 영영 안 돈다(도메인 색인이
`sync_domain_index` 명시 호출을 놓쳐 검색 0건이 된 것과 같은 함정이다).
"""
from __future__ import annotations

import sys

from ..context_search.paths import resolve
from . import class_graph as cg, db, dependency as dep, parse


def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "status").lower()
    which = (argv[1] if len(argv) > 1 else "all").lower()
    if which not in ("all", "class", "dep"):
        which, name = "all", which
    else:
        name = argv[2] if len(argv) > 2 else ""
    try:
        paths = resolve(name)
    except Exception as e:
        print(f"❌ 프로젝트 해석 실패: {e}")
        return 2

    if cmd == "status":
        c = db.counts(paths)
        print(f"[{paths.name}] {paths.class_graph_db}")
        print(f"  파일 있음   : {db.exists(paths)}")
        print(f"  classes     : {c['classes']}")
        print(f"  methods     : {c['methods']}  (게이트 {'열림' if cg.methods_ready(paths) else '닫힘'})")
        # 🔴 **이 두 표는 일부러 비어 있다** (정정 2026-08-14, 소 3.1.2).
        #
        # 옛 출력은 *"← 중 1.3 이 채운다"* 였는데 **거짓 약속**이었다 — 중 1.3 은 추론 파견이고
        # 이 표를 채우지 않았다. 그리고 **채우지 않는 것이 결정**이다: 소속의 SSOT 는 각 도메인의
        # `objects/*.yaml` 이다(`context_search/infer.py` 머리말 — *"죽은 표를 근거로 삼지 않는다"*).
        #
        # ⚠️ 원전은 DB 표와 MD/YAML **둘**을 갖고 있었고, 그 둘이 어긋나는 것을 잡으려고 η.4
        # drift 감사(*"inactive 도메인 · archive 잔재 · NULL 도메인 분류"*)를 따로 만들어야 했다.
        # 출처를 하나로 두면 **그 문제군이 원천 제거된다** — 되돌리지 말 것.
        print(f"  domains     : {c['domains']}        ← 🔴 일부러 비움 (SSOT 는 ontology/*.yaml)")
        print(f"  class_ontology: {c['class_ontology']}      ← 🔴 일부러 비움 (같음)")
        print(f"  tree-sitter : {'있음' if parse.TREE_SITTER_AVAILABLE else '🔴 없음'}")
        d = dep.counts(paths)
        print(f"[의존] {paths.dependency_graph_db}")
        print(f"  files       : {d['files']}")
        print(f"  includes    : {d['includes']}")
        return 0

    if cmd == "build":
        rc = 0
        if which in ("all", "class"):
            try:
                st = cg.build_full(paths, progress=lambda m: print(m, flush=True))
                print(f"✅ 상속 [{paths.name}] {st.summary}")
            except (parse.ParserUnavailable, cg.GraphError) as e:
                # 🔴 조용히 0 을 남기지 않는다. 종료 코드로도 알린다.
                print(f"❌ 상속: {e}")
                rc = 1
        if which in ("all", "dep"):
            try:
                ds = dep.build_full(paths, progress=lambda m: print(m, flush=True))
                print(f"✅ 의존 [{paths.name}] {ds.summary}")
            except cg.GraphError as e:
                print(f"❌ 의존: {e}")
                rc = 1
        return rc

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
