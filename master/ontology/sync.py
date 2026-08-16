"""소스와 온톨로지를 맞춘다 — `path_sync` · `declared` (소 1.3.9).

## 무엇이 어긋나는가

object yaml 은 `file:` 로 소스를 가리킨다. 파일이 옮겨지거나 이름이 바뀌면 그 값은 **조용히
낡는다** — 에러가 나지 않는다. 매니페스트는 그 경로를 워커에게 주고, 워커는 없는 파일을 읽지
못한 채 *"매니페스트가 주는 대로"* 짠다. 사실 게이트가 잡는 것은 **호출 관계**지 경로가 아니다.

    path_sync   `file:`            ← 클래스 그래프(소스 실측)
    declared    `declared_methods:` ← methods 표(6,380행 실측)

## [중요] 이 둘은 **기계의 사실**이지 사람의 내용이 아니다

그래서 `verified_by_user` 로 잠긴 항목에도 **넣는다.** 잠금이 지키는 것은 사람이 쓴 설명·
의도이지, *이 클래스가 어느 파일에 있는가* 가 아니다. 잠갔다고 경로가 낡은 채로 남으면
잠금이 오히려 문서를 썩힌다. [중요] **대신 그 두 필드 말고는 아무것도 건드리지 않는다.**

## [중요] 없는 클래스를 지우지 않는다

그래프에 없는 클래스는 ⑴ 정말 삭제됐거나 ⑵ 그래프가 낡았거나 ⑶ 파서가 못 읽은 것이다.
셋을 구분할 수단이 여기엔 없다. **보고만 하고 남긴다** — 지우는 것은 사람이 판단한다.

## 왜 `declared` 가 중요한가 (실측)

규범만 주고 로컬 모델에 코드를 시켰더니 실재 멤버 4/4 를 쓰고도 `CurrentStep`(실제 `Step`)
처럼 **한 글자 차이로 지어낸 이름**이 남았다. 정확한 철자는 헤더에만 있다. `declared_methods`
는 그 철자를 **온톨로지 안으로** 들여놓는다 — 매니페스트가 실어 보낼 수 있는 형태로.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from . import yaml_io
from .package import LAYER_DIRS, MANIFEST

PATH_FIELD = "file"
DECLARED_FIELD = "declared_methods"
MAX_DECLARED = 60           # [중요] 상한이 걸리면 본문에 그렇게 적는다


@dataclass
class SyncStats:
    domain: str = ""
    checked: int = 0
    path_fixed: list = field(default_factory=list)      # [(클래스, 옛경로, 새경로)]
    declared_set: list = field(default_factory=list)    # [(클래스, 개수)]
    missing: list = field(default_factory=list)         # 그래프에 없는 클래스
    truncated: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = (f"{self.domain or '전체'}: 검사 {self.checked} · 경로 수정 {len(self.path_fixed)}"
             f" · declared {len(self.declared_set)}")
        if self.missing:
            # [중요] 지우지 않았다는 것까지 말한다
            s += f" · [주의] 그래프에 없음 {len(self.missing)}(남겨 둠)"
        if self.truncated:
            s += f" · 상한 적용 {len(self.truncated)}"
        if self.notes:
            s += " · " + "; ".join(self.notes[:2])
        return s


def _graph(paths: ProjectPaths) -> tuple:
    """`({클래스: 파일}, {클래스: [메서드…]})`. 그래프가 없으면 `(None, None)`."""
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return None, None
    conn = gdb.connect(paths)
    try:
        files = {r["name"]: (r["file"] or "") for r in conn.execute(
            "SELECT name, file FROM classes")}
        methods: dict = {}
        for r in conn.execute(
                "SELECT class_name, method_name FROM methods ORDER BY class_name, method_name"):
            methods.setdefault(r["class_name"], []).append(r["method_name"])
        return files, methods
    finally:
        conn.close()


def _object_files(paths: ProjectPaths, domain: str):
    """도메인의 object yaml 경로들. manifest 를 근거로 삼는다(패키지의 진실)."""
    root = paths.ontology / "domains" / domain
    man = yaml_io.read(root / MANIFEST) or {}
    out = []
    for rel in man.get("objects") or []:
        p = root / str(rel)
        if p.is_file():
            out.append(p)
    if out:
        return out
    # manifest 가 비었으면 파일 시스템으로 떨어진다 — 조용히 0건을 내지 않는다
    for layer in LAYER_DIRS:
        d = root / layer / "objects"
        if d.is_dir():
            out += sorted(d.glob("*.yaml"))
    return out


def sync_domain(paths: ProjectPaths, domain: str, *, files=None, methods=None,
                declared: bool = True, apply: bool = True) -> SyncStats:
    """도메인 하나를 맞춘다. `apply=False` 면 **계획만** (아무것도 쓰지 않는다)."""
    st = SyncStats(domain=domain)
    if files is None or methods is None:
        files, methods = _graph(paths)
    if files is None:
        st.notes.append("[중요] 클래스 그래프가 없다 — `python -m master.graph build` 먼저")
        return st

    from . import hierarchy
    for p in _object_files(paths, domain):
        item = yaml_io.read(p)
        if not isinstance(item, dict) or hierarchy.is_domain_ref(item):
            continue
        name = str(item.get("name") or p.stem)
        st.checked += 1
        if name not in files:
            # [중요] 지우지 않는다 — 삭제됐는지 그래프가 낡았는지 여기선 모른다
            st.missing.append(name)
            continue

        changed = False
        real = files[name]
        if real and item.get(PATH_FIELD) != real:
            st.path_fixed.append((name, str(item.get(PATH_FIELD) or ""), real))
            item[PATH_FIELD] = real
            changed = True

        if declared:
            ms = methods.get(name) or []
            if len(ms) > MAX_DECLARED:
                st.truncated.append(name)
                ms = ms[:MAX_DECLARED]
            if ms and item.get(DECLARED_FIELD) != ms:
                item[DECLARED_FIELD] = ms
                st.declared_set.append((name, len(ms)))
                changed = True

        if changed and apply:
            yaml_io.write(p, item)      # [중요] 이 두 필드만 바뀐 dict 다
    return st


def sync_all(paths: ProjectPaths, *, declared: bool = True, apply: bool = True) -> list:
    """모든 도메인. 도메인별 통계를 돌려준다."""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return []
    files, methods = _graph(paths)
    out = []
    for d in sorted(x for x in root.iterdir() if x.is_dir()):
        if not (d / MANIFEST).is_file():
            continue
        out.append(sync_domain(paths, d.name, files=files, methods=methods,
                               declared=declared, apply=apply))
    return out
