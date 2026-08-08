"""관계 그래프 CLI.

    .venv/bin/python -m master.graph build        # 풀 스캔 (마운트된 프로젝트)
    .venv/bin/python -m master.graph status       # 건수만

`data-schema.md` 가 이 DB 의 복구를 *"파일 삭제 → 재기동 시 풀 스캔"* 이라고 적어 둔 것을
여기서는 **명시 명령**으로 바꿨다. 우리 색인기는 상주 데몬이 아니라 이벤트로 깨어나는
oneshot 이라 "재기동" 이라는 순간이 없다 — 자동 감지에 기대면 영영 안 돈다(도메인 색인이
`sync_domain_index` 명시 호출을 놓쳐 검색 0건이 된 것과 같은 함정이다).
"""
from __future__ import annotations

import sys

from ..context_search.paths import resolve
from . import class_graph as cg, db, parse


def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "status").lower()
    name = argv[1] if len(argv) > 1 else ""
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
        print(f"  domains     : {c['domains']}        ← 중 1.3 이 채운다")
        print(f"  class_ontology: {c['class_ontology']}      ← 중 1.3 이 채운다")
        print(f"  tree-sitter : {'있음' if parse.TREE_SITTER_AVAILABLE else '🔴 없음'}")
        return 0

    if cmd == "build":
        try:
            st = cg.build_full(paths, progress=lambda m: print(m, flush=True))
        except (parse.ParserUnavailable, cg.GraphError) as e:
            # 🔴 조용히 0 을 남기지 않는다. 종료 코드로도 알린다.
            print(f"❌ {e}")
            return 1
        print(f"✅ [{paths.name}] {st.summary}")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
