"""마운트된 프로젝트 → 데이터 디렉토리 해석 (PLAN §5.5.2, §5.2-E).

🔴 **이것이 이식의 핵심 변경점이다.**

AgentTest 는 루트를 **기동 시 인자로 고정**했다 — `run_http_server(project_root, port)` 가
`register_*_routes(app, project_root, ...)` 로 전 라우트를 클로저에 캡처하므로
**요청 단위로 프로젝트를 고를 방법이 없었다**(§5.5.1 실측).

여기서는 뒤집는다:

> **기능은 공용이고, 어느 프로젝트를 바라보는가에 따라 어느 디렉토리를 읽을지 분기한다**
> (사용자 지시 2026-08-08).

경로 해석이 **상수가 아니라 함수**다. 그래서:

- 마운트 전환에 **서비스 재기동이 필요 없다** — 다음 호출이 새 경로를 본다
- 두 번째 프로젝트가 생겨도 **정책만 풀면 된다.** 아키텍처를 고칠 필요가 없다
  (§5.5.2 가 "요청 단위 라우팅은 비용이 동일하다" 고 판단한 그 지점)

**레이아웃** — AgentTest 와 다르다. 거기는 `<UE5프로젝트>/.claude/` 안에 데이터가 있었고
(그래서 "위치가 곧 격리" 였다, §5.5.1), 여기는 마스터의 디지털 트윈 디렉토리다:

    ~/ax-cluster/<Name>/
        config.yaml     추적 대상 + 색인 워터마크
        context/        원본 · 컨텍스트 MD
        ontology/       원본 · 도메인 yaml
        repo/           소스 클론 — 🔴 **색인 대상은 여기의 Source/** 뿐이다** (§5.2-E)
        vector_db/      파생 · 벡터 색인
        bm25.db         파생
        class_graph.db  파생

🔴 **파생물은 프로젝트 디렉토리 안에 있다.** 컬렉션 이름(`context_a`/`context_b`)이 고정이어도
**디렉토리가 갈리므로 프로젝트끼리 섞이지 않는다** — §5.5.1 이 지적한 "컬렉션명에 프로젝트
식별자가 없다" 는 문제가 경로 분기로 해소된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..projects.config import ConfigError, ProjectConfig, Registry

# 파생 자산 이름 — `<Name>/.gitignore` 와 짝을 맞춘다. 바꾸면 양쪽을 같이 바꿀 것.
VECTOR_DB = "vector_db"
BM25_DB = "bm25.db"
BM25_DOMAINS_DB = "bm25_domains.db"      # 🔴 도메인 색인은 **별도 DB** — 소 2.1.1
CLASS_GRAPH_DB = "class_graph.db"
DEPENDENCY_GRAPH_DB = "dependency_graph.db"

# 소스 클론 안에서 색인할 하위 경로. §5.2-E — 소스 한정.
SOURCE_SUBDIR = "Source"


@dataclass(frozen=True)
class ProjectPaths:
    """한 프로젝트의 데이터 위치. **불변** — 해석 결과를 들고 다니되 고쳐 쓰지 않는다."""

    name: str
    root: Path

    @property
    def config(self) -> Path: return self.root / "config.yaml"
    @property
    def context(self) -> Path: return self.root / "context"
    @property
    def ontology(self) -> Path: return self.root / "ontology"
    @property
    def repo(self) -> Path: return self.root / "repo"
    @property
    def source(self) -> Path:
        """🔴 색인 대상. `Content/`(uasset, 워킹트리의 93%)는 여기 들어오지 않는다 (§5.2-E)."""
        return self.repo / SOURCE_SUBDIR

    @property
    def manifests(self) -> Path:
        """태스크별 컨텍스트 매니페스트. 파생물이다 — 재수집으로 복구된다 (§4.2)."""
        return self.root / "manifests"

    @property
    def responses(self) -> Path:
        """워커 추론 응답의 스풀 (소 1.3.2). 🔴 **파생물이 아니다.**

        매니페스트는 지우면 재수집되지만 이것은 **돈을 낸 LLM 출력**이다 — 지우면 같은 추론을
        다시 산다. 그리고 통합자가 적용할 때까지 **유일한 사본**이라, 이것이 곧 *"어디까지
        진행됐나"* 의 답이다(소 1.3.3). 청소 대상에 넣지 말 것.
        """
        return self.root / "responses"

    @property
    def vector_db(self) -> Path: return self.root / VECTOR_DB
    @property
    def bm25_db(self) -> Path: return self.root / BM25_DB
    @property
    def bm25_domains_db(self) -> Path:
        """도메인(온톨로지) BM25. 🔴 컨텍스트 MD 색인과 **파일이 다르다** — 도메인은 광범위
        신호라 같은 표에 넣으면 일반 검색 결과를 밀어낸다(원본이 같은 이유로 분리했다)."""
        return self.root / BM25_DOMAINS_DB

    @property
    def class_graph_db(self) -> Path: return self.root / CLASS_GRAPH_DB
    @property
    def dependency_graph_db(self) -> Path: return self.root / DEPENDENCY_GRAPH_DB

    def ensure_derived(self) -> None:
        """파생물 디렉토리를 만든다. 원본(`context/`·`ontology/`)은 **만들지 않는다** —
        없다면 이관이 안 된 것이고, 조용히 빈 디렉토리를 만들면 그걸 감춘다."""
        self.vector_db.mkdir(parents=True, exist_ok=True)

    def missing_sources(self) -> list[str]:
        """색인에 필요한데 없는 것. 있는 그대로 보고한다 — 추측해서 채우지 않는다."""
        out = []
        if not self.root.is_dir():
            out.append(f"프로젝트 디렉토리 없음: {self.root}")
            return out
        if not self.context.is_dir():
            out.append(f"컨텍스트 원본 없음: {self.context}")
        if not self.repo.is_dir():
            out.append(f"소스 클론 없음: {self.repo}")
        elif not self.source.is_dir():
            out.append(f"`{SOURCE_SUBDIR}/` 없음: {self.source} — 색인할 소스가 없다")
        return out

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "root": str(self.root),
            "source": str(self.source),
            "vector_db": str(self.vector_db),
        }


def resolve(name: str = "", *, registry: Registry | None = None) -> ProjectPaths:
    """프로젝트명 → 경로. **`name` 을 비우면 지금 마운트된 프로젝트**를 쓴다.

    🔴 매 호출마다 레지스트리를 읽는다. 캐시하지 않는 이유는 그게 이 설계의 요점이기
    때문이다 — 마운트가 바뀌면 **다음 호출이 바로 새 경로를 본다.**
    """
    reg = registry or Registry.load()
    target = (name or reg.active or "").strip()
    if not target:
        raise ConfigError("마운트된 프로젝트가 없다(active 가 비었다). 먼저 전환할 것.")
    if target not in reg.names:
        raise ConfigError(
            f"등록되지 않은 프로젝트다: {target}. 등록된 것: {', '.join(reg.names) or '(없음)'}"
        )
    return ProjectPaths(name=target, root=reg.dir_of(target))


def resolve_mounted_only(name: str = "", *, registry: Registry | None = None) -> ProjectPaths:
    """§5.5.2 의 **단일 마운트 정책**을 강제한다 — 마운트되지 않은 프로젝트는 거부.

    `resolve()` 와 나눠 둔 이유: 경로 해석(아키텍처)과 마운트 정책(운영 규칙)은 다른 층이다.
    두 번째 프로젝트를 동시에 열기로 하면 **이 함수만 안 쓰면 된다** — `resolve()` 는 그대로다.
    """
    reg = registry or Registry.load()
    target = (name or reg.active or "").strip()
    if name and reg.active and name != reg.active:
        raise ConfigError(
            f"마운트되지 않은 프로젝트다: {name} (마운트: {reg.active}). "
            "동시에 하나만 연다 (§5.5.2) — 전환 후 다시 요청할 것."
        )
    return resolve(target, registry=reg)


def project_config(paths: ProjectPaths) -> ProjectConfig:
    return ProjectConfig.load(paths.config)
