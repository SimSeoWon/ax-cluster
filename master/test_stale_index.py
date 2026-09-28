"""🔴 낡은 Chroma 핸들 복구 (`#693`, 재현 2026-09-29) — 진짜 Chroma · 진짜 별도 프로세스.

오래 사는 프로세스(8103)가 **빈 색인을 한 번 검색**한 뒤 **다른 프로세스**가 첫 색인을 만들면
`hnsw segment reader: Nothing found on disk` 로 죽었다(웹 UI 문서 탭이 재시작 전까지 전부 실패).
흉내(가짜 컬렉션)로는 Chroma 의 프로세스 전역 캐시가 안 보인다 — 그래서 실물로 잰다.
[주의] 문서 원본은 `KimodoMotion_WebUI/context` 에서 20개를 **임시 트윈에 복사**한다. 없으면 건너뛴다.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from master.context_search.paths import ProjectPaths  # noqa: E402

SRC = REPO / "KimodoMotion_WebUI" / "context"
PY = str(REPO / ".venv" / "bin" / "python")
REBUILD = ("import sys; sys.path.insert(0, %r); from pathlib import Path; "
           "from master.context_search.paths import ProjectPaths; "
           "from master.context_search.rebuild import rebuild_all; "
           "print(rebuild_all(ProjectPaths(name='R', root=Path(sys.argv[1]))))")


def twin(tmp: Path) -> ProjectPaths:
    root = tmp / "R"
    (root / "context").mkdir(parents=True)
    (root / "repo" / "Source").mkdir(parents=True)
    for f in sorted(SRC.rglob("*.md"))[:20]:
        dst = root / "context" / f.relative_to(SRC)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, dst)
    return ProjectPaths(name="R", root=root)


def external_rebuild(root: Path) -> str:
    p = subprocess.run([PY, "-c", REBUILD % str(REPO), str(root)], capture_output=True, text=True)
    return (p.stdout.strip().splitlines() or [p.stderr.strip()[-200:]])[-1]


def search(paths) -> str:
    from master.context_search import ContextSearch
    try:
        hits = ContextSearch(paths).search("caption image", limit=3)
        return f"OK {len(hits)}건 {[h.file_id for h in hits][:2]}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR {type(e).__name__}: {str(e)[:110]}"


PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


def run(pre_search: bool, pre_index: bool) -> str:
    tmp = Path(tempfile.mkdtemp())
    try:
        p = twin(tmp)
        if pre_index:
            external_rebuild(p.root)
        if pre_search:
            search(p)
        external_rebuild(p.root)
        return search(p)
    finally:
        shutil.rmtree(tmp)


def main() -> int:
    from master.context_search.index import _is_stale_segment
    check("증상 판정 — Chroma 문구", _is_stale_segment(RuntimeError(
        "Error executing plan: Internal error: Error creating hnsw segment reader: Nothing found on disk")))
    check("  다른 오류는 복구 대상이 아니다", not _is_stale_segment(RuntimeError("disk full")))
    if not SRC.is_dir() or len(list(SRC.rglob("*.md"))) < 3:
        check("원본 문서가 없다 — 실물 재현은 건너뜀", True)
    else:
        got = run(pre_search=True, pre_index=False)
        check("🔴 A 빈 색인 선검색 → 외부 첫 색인 → 같은 프로세스 검색이 된다", got.startswith("OK 3"), got)
        got = run(pre_search=False, pre_index=False)
        check("B 검색 없이 첫 색인 → 검색", got.startswith("OK 3"), got)
        got = run(pre_search=True, pre_index=True)
        check("C 색인 있는 상태의 외부 재색인(세대 교체) → 검색", got.startswith("OK 3"), got)
    print(f"{'OK' if not FAIL else 'FAIL'} test_stale_index: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
