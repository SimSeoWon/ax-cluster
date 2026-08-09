"""컨텍스트 매니페스트 — 태스크 등록 시 **한 번** 수집한다 (AgentTest C.2 ④ 이식).

**왜 있는가.** 로컬 LLM(코드 생성 담당)은 MCP 도구를 못 부른다. 매 라운드 작업장이 검색을
다시 돌리면 ① 로컬 LLM 은 아예 grounding 을 못 받고 ② 도구를 쓸 수 있는 상용 모델도
같은 검색을 N번 반복해 토큰을 태운다. 그래서 **마스터가 등록 시 1회 수집해 고정**하고,
작업장은 **읽기만** 한다. "비싼 작업 1회 → 싼 매체로 재사용" 이라는 git-as-feedback-bus 의 정신과 같다.

🔴 **원본과 다른 점 — 매니페스트를 git 에 싣지 않는다.**

원본은 서버가 골조를 push 하면서 `.claude/tasks/<id>/context.md` 를 함께 실어 보냈다.
**우리 마스터는 소스 저장소에 push 할 수 없다**(pushurl 비활성, §8). 그래서 매니페스트를
**디지털 트윈의 파생물**로 둔다 — `<Project>/manifests/<task_id>.md`. `vector_db` 와 같은
성격이고(재수집으로 복구 가능), 작업장은 마스터에서 받아 간다.

**잃는 것은 없다.** git-carried 였던 이유는 서버가 어차피 push 하고 있었기 때문이지
git 자체가 필요해서가 아니었다. "1회 수집 → 다회 소비" 라는 성질은 그대로다.

**채널이 둘이다 (소 2.3.1 완료, 2026-08-09).** RAG(컨텍스트 문서) + **도메인 규범**(온톨로지).
후자가 목표 ②의 종점이고, `work/norms.py` 가 `domain_index.search_norms` 를 소비해 만든다.
🔴 **규범이 비면 비었다고 본문에 쓴다** — 빈 섹션을 감추면 작업장은 규칙이 없는 줄 알고,
다음 세션은 그것을 버그로 오해한다.

**베스트에포트다.** 검색이 실패하거나 결과가 비어도 태스크 등록을 막지 않는다. 다만
**조용히 넘어가지 않고** 매니페스트에 그 사실을 적는다 — 작업장이 grounding 없이 일하고
있다는 것을 알아야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..context_search.paths import ProjectPaths
from . import norms as norms_mod

MANIFEST_DIR = "manifests"

# 매니페스트에 실을 검색 히트 수. 원본 기본값(5)과 같다.
DEFAULT_HITS = 5
# 발췌 길이 — 넘치면 프롬프트를 잡아먹는다. 원본과 같은 160자.
EXCERPT = 160


class ManifestError(Exception):
    pass


@dataclass
class Manifest:
    task_id: str
    project: str
    body: str
    hits: int = 0
    norm_domains: int = 0        # 실린 도메인 수 (소 2.3.1)
    norm_items: int = 0          # invariant + action 수
    degraded: list[str] = field(default_factory=list)   # 비어 있으면 온전히 수집된 것

    @property
    def ok(self) -> bool:
        return not self.degraded


def manifest_dir(paths: ProjectPaths) -> Path:
    return paths.root / MANIFEST_DIR


def manifest_path(paths: ProjectPaths, task_id: str) -> Path:
    safe = task_id.strip().replace("/", "_")
    if not safe:
        raise ManifestError("task_id 가 비었다")
    return manifest_dir(paths) / f"{safe}.md"


def _query(classes: list[str], stem: str, extra: str) -> str:
    """검색 질의 조립. 클래스명이 가장 강한 신호라 앞에 둔다 (BM25 가 식별자에 강하다)."""
    parts = [" ".join(c for c in classes if c), stem or "", extra or ""]
    return " ".join(p.strip() for p in parts if p and p.strip())


def _format_hits(hits: list) -> list[str]:
    out = []
    for h in hits:
        excerpt = (h.excerpt or "").strip().replace("\n", " ")
        if len(excerpt) > EXCERPT:
            excerpt = excerpt[:EXCERPT] + "…"
        line = f"- `{h.file_id}` (rrf={h.rrf_score:.4f}, {h.source})"
        out.append(f"{line}\n  {excerpt}" if excerpt else line)
    return out


def build(
    paths: ProjectPaths,
    task_id: str,
    *,
    classes: list[str] | None = None,
    stem: str = "",
    contracts: str = "",
    skeleton: str = "",
    extra_query: str = "",
    hits: int = DEFAULT_HITS,
    searcher=None,
    norms=None,
    now: datetime | None = None,
) -> Manifest:
    """매니페스트를 조립한다. **디스크에 쓰지는 않는다** — `write()` 가 따로 한다.

    `searcher` 를 주입받는 이유는 테스트다. 실제로는 `ContextSearch` 가 들어온다.
    """
    classes = [c for c in (classes or []) if c and c.strip()]
    query = _query(classes, stem, extra_query)
    degraded: list[str] = []
    lines: list[str] = []

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%SZ")
    lines.append(f"# 컨텍스트 매니페스트 — `{task_id}`\n")
    lines.append(f"> 프로젝트 `{paths.name}` · 수집 {stamp}")
    lines.append("> **마스터가 등록 시 1회 수집했다. 이 문서를 읽고 작업할 것 — 재검색 불필요.**\n")

    if classes:
        lines.append("## 대상 클래스\n")
        lines.extend(f"- `{c}`" for c in classes)
        lines.append("")
    if contracts.strip():
        lines.append("## 계약 (동결 — 바꾸지 말 것)\n")
        lines.append(contracts.strip())
        lines.append("")
    if skeleton.strip():
        # 🔴 골조가 여기 실리는 이유: 원본은 서버가 골조를 **git 에 커밋해** 보냈지만
        # 우리 마스터는 push 를 못 한다(§4.7 ④). `task_data` 는 태스크 마크다운 본문으로만
        # 저장되고 JSON API 로 안 나온다(`task_queue/logic.py:202`) — 전송 수단이 아니다.
        # 매니페스트가 마스터→작업장 텍스트 채널이므로 골조도 여기로 간다.
        lines.append("## 골조 (이 파일을 만들 것 — `[PSEUDO]` 본문만 채운다)\n")
        lines.append("```cpp")
        lines.append(skeleton.strip())
        lines.append("```")
        lines.append("")

    found = []
    if not query:
        degraded.append("검색 질의를 만들 수 없었다 (classes·stem 이 모두 비었다)")
    elif searcher is None:
        degraded.append("검색기가 없다")
    else:
        try:
            found = searcher.search(query, limit=hits)
        except Exception as e:                       # noqa: BLE001 — 등록을 막지 않는다
            degraded.append(f"검색 실패: {type(e).__name__}: {e}")
        if not found and not degraded:
            degraded.append("검색 결과가 없다")

    lines.append("## 관련 코드 (RAG)\n")
    if found:
        lines.extend(_format_hits(found))
    else:
        lines.append("_(없음)_")
    lines.append("")

    # 🔴 빈 채로 숨기지 않는다 — 없다는 사실 자체가 정보다.
    lines.append("## 도메인 규범 (온톨로지)\n")
    if norms is None:
        try:
            norms = norms_mod.attach(paths, classes=classes, stem=stem,
                                     extra_query=extra_query)
        except Exception as e:                       # noqa: BLE001 — 등록을 막지 않는다
            norms = norms_mod.NormBundle(
                degraded=[f"규범 수집 실패: {type(e).__name__}: {e}"])
    lines.extend(norms.render())
    lines.append("")
    if not norms.ok:
        degraded.extend(norms.degraded)

    if degraded:
        lines.append("## ⚠️ 수집이 온전하지 않다\n")
        lines.extend(f"- {d}" for d in degraded)
        lines.append("")
        lines.append("작업장은 이 매니페스트만 믿지 말고 필요하면 직접 확인할 것.")
        lines.append("")

    nd, ni, na = norms.counts
    return Manifest(task_id=task_id, project=paths.name, body="\n".join(lines),
                    hits=len(found), norm_domains=nd, norm_items=ni + na,
                    degraded=degraded)


def write(paths: ProjectPaths, m: Manifest) -> Path:
    """원자적으로 쓴다 — 작업장이 반쯤 쓰인 매니페스트를 읽으면 안 된다."""
    p = manifest_path(paths, m.task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(m.body, encoding="utf-8")
    tmp.replace(p)
    return p


def read(paths: ProjectPaths, task_id: str) -> str | None:
    """작업장에 건넬 본문. 없으면 `None` — **빈 문자열과 구분한다.**"""
    p = manifest_path(paths, task_id)
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def collect(paths: ProjectPaths, task_id: str, **kw) -> tuple[Path, Manifest]:
    """수집 + 저장. 태스크 등록 경로가 부르는 진입점."""
    searcher = kw.pop("searcher", None)
    if searcher is None:
        try:
            from ..context_search import ContextSearch
            searcher = ContextSearch(paths)
        except Exception as e:                       # noqa: BLE001
            # 검색을 못 열어도 등록은 진행한다. build() 가 degraded 로 기록한다.
            searcher = _BrokenSearcher(e)
    m = build(paths, task_id, searcher=searcher, **kw)
    return write(paths, m), m


class _BrokenSearcher:
    """검색기를 못 연 상태를 **값으로** 표현한다 — `None` 이면 '검색기가 없다' 와 구분이 안 된다."""

    def __init__(self, exc: Exception):
        self._exc = exc

    def search(self, *_a, **_kw):
        raise self._exc
