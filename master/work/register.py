"""작업 등록 — `/distribute` 의 마스터 몫 (AgentTest `executor_work_register.py` 이식).

🔴 **원본에서 가장 크게 잘라낸 지점이다. 경계가 다르기 때문이다.**

AgentTest 의 `master_orchestrator` 는 **윈도우 UE5 프로젝트 루트에 함께 배포**됐다(zip 12종).
그래서 등록부가 저장소를 직접 만졌다 — `create_branch_if_needed` · `commit_skeletons` ·
`prepare_work_branch_impl`. 여기서는 **마스터가 파일을 소유하지 않고 소스 저장소에 push 도
못 한다**(§2.1, §8). 그러므로:

| 원본 등록부가 하던 일 | 여기 |
|---|---|
| 작업 브랜치 생성 | ❌ **작업장이 한다** |
| 골조 파일 쓰기 · 커밋 | ❌ **작업장이 한다** — 마스터는 골조 *텍스트*만 실어 보낸다 |
| 중복 검사 · work/task 큐 등록 | ✅ 마스터 |
| 컨텍스트 매니페스트 수집 | ✅ 마스터 (`manifest.py`) |

**이 경계가 §2.1 그대로다** — 마스터는 코드 뭉치를 조립해 건네는 데서 끝난다.

**분해(decomposition)는 여기 없다.** 요청 하나를 클래스 단위 태스크 N개로 쪼개는 것은 §4.5 의
주제이고 LLM 호출이 필요하다. 이 모듈은 **이미 쪼개진 명세를 받아 등록**한다 — 두 관심사를
섞으면 등록을 테스트할 때마다 추론이 필요해진다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from ..auth import auth_headers
from ..context_search.paths import ProjectPaths
from . import manifest as mf

DEFAULT_QUEUE = "http://localhost:8101"
TIMEOUT = 30


class RegisterError(Exception):
    pass


@dataclass
class TaskSpec:
    """등록할 태스크 하나. **이미 클래스 단위로 쪼개진 것**이 들어온다 (§4.5)."""

    stem: str                                  # 조각 이름 (보통 클래스명)
    classes: list[str] = field(default_factory=list)
    contracts: str = ""                        # 🔴 동결 인터페이스 — 병렬 생성의 전제 (§4.5)
    skeleton: str = ""                         # 골조 텍스트. 파일로 쓰는 것은 작업장 몫
    target_file: str = ""            # 큐 레코드용(단수) — 여러 개면 `target_files` 의 첫 번째
    # 🔴 한 태스크가 맡는 파일 전부. **매니페스트에 실린다** — 예전엔 큐에만 있었다(#65).
    target_files: list = field(default_factory=list)
    header_file: str = ""
    depends_on: list = field(default_factory=list)
    requires: list = field(default_factory=list)   # 예: ["ue5"] — 능력 라우팅 (§5.2-C)
    priority: int = 0

    def validate(self) -> None:
        if not (self.stem or "").strip():
            raise RegisterError("stem 이 비었다 — 태스크를 식별할 수 없다")
        if self.target_files and not self.target_file:
            self.target_file = self.target_files[0]
        if self.target_file and self.target_file not in self.target_files:
            self.target_files = [self.target_file] + list(self.target_files)
        if not self.classes and not self.target_file:
            raise RegisterError(
                f"{self.stem}: classes 도 target_file 도 없다 — "
                "매니페스트를 수집할 근거가 없다"
            )


@dataclass
class TaskResult:
    stem: str
    task_id: str = ""
    manifest_path: str = ""
    manifest_hits: int = 0
    error: str = ""
    manifest_degraded: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.task_id) and not self.error


@dataclass
class Registered:
    work_id: str
    tasks: list[TaskResult]

    @property
    def ok(self) -> bool:
        return bool(self.work_id) and all(t.ok for t in self.tasks)

    @property
    def failed(self) -> list[TaskResult]:
        return [t for t in self.tasks if not t.ok]

    def summary(self) -> str:
        n_ok = sum(1 for t in self.tasks if t.ok)
        degraded = sum(1 for t in self.tasks if t.manifest_degraded)
        s = f"work={self.work_id} 태스크 {n_ok}/{len(self.tasks)} 등록"
        if degraded:
            s += f" · 매니페스트 결손 {degraded}건"
        if self.failed:
            s += f" · 🔴 실패 {len(self.failed)}건"
        return s


def _post(url: str, payload: dict, *, token: str | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", **auth_headers(token)},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RegisterError(f"{url} → HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RegisterError(f"{url} → 연결 실패: {e.reason}") from e


def register_work(
    title: str,
    specs: list[TaskSpec],
    *,
    paths: ProjectPaths,
    target_repo: str,
    original_request: str = "",
    target_branch: str = "",
    queue_url: str = DEFAULT_QUEUE,
    token: str | None = None,
    poster=None,
    searcher=None,
) -> Registered:
    """work 를 만들고 태스크를 등록한다. 태스크마다 매니페스트를 1회 수집한다.

    `poster` 를 주입할 수 있는 이유는 테스트다 — 큐를 띄우지 않고 등록 규칙을 검증한다.

    🔴 **명세 검증을 먼저 전부 돌린다.** 절반 등록하고 실패하면 큐에 반쪽 work 가 남는데,
    그건 사람이 치워야 한다. 막을 수 있는 것은 미리 막는다.
    """
    if not (title or "").strip():
        raise RegisterError("title 이 비었다")
    if not specs:
        raise RegisterError("등록할 태스크가 없다")
    seen: set[str] = set()
    for s in specs:
        s.validate()
        if s.stem in seen:
            raise RegisterError(f"stem 이 중복이다: {s.stem} — 매니페스트가 서로를 덮어쓴다")
        seen.add(s.stem)

    post = poster or (lambda u, p: _post(u, p, token=token))

    work = post(f"{queue_url}/api/v1/works", {
        "title": title,
        "target_repo": target_repo,
        "target_branch": target_branch,
        "original_request": original_request or title,
        # 🔴 2-tier 브랜치를 쓴다. 원본의 pull 레거시 경로는 우리에게 없다 (`branch_names.py`).
        "distribution_mode": "push",
    })
    work_id = str(work.get("work_id") or work.get("id") or "")
    if not work_id:
        raise RegisterError(f"work_id 를 받지 못했다: {work}")

    # 검색기는 태스크마다 새로 열지 않는다 — 모델 로딩이 태스크 수만큼 반복된다.
    if searcher is None:
        try:
            from ..context_search import ContextSearch
            searcher = ContextSearch(paths)
        except Exception as e:                       # noqa: BLE001
            searcher = mf._BrokenSearcher(e)

    results: list[TaskResult] = []
    for spec in specs:
        r = TaskResult(stem=spec.stem)
        try:
            reg = post(f"{queue_url}/api/v1/tasks", {
                "work_id": work_id,
                "type": "code",
                "stem": spec.stem,
                "target_file": spec.target_file,
                "header_file": spec.header_file,
                "depends_on": spec.depends_on,
                "requires": spec.requires,
                "priority": spec.priority,
                "origin": "master",
                "task_data": {
                    "stem": spec.stem,
                    "classes": spec.classes,
                    "contracts": spec.contracts,
                    # 골조 텍스트를 실어 보낸다. **파일로 쓰는 것은 작업장 몫이다.**
                    "skeleton": spec.skeleton,
                },
            })
            r.task_id = str(reg.get("task_id") or reg.get("id") or "")
            if not r.task_id:
                r.error = f"task_id 를 받지 못했다: {reg}"
        except RegisterError as e:
            r.error = str(e)

        if r.task_id:
            # 매니페스트는 베스트에포트다 — 실패해도 등록을 되돌리지 않는다.
            # 다만 결손을 결과에 실어 호출자가 알 수 있게 한다.
            # 🔴 골조를 매니페스트에 싣는다 — `task_data` 는 전송 수단이 아니다(§4.7 ④).
            m = mf.build(paths, r.task_id, classes=spec.classes,
                         target_files=spec.target_files, stem=spec.stem,
                         contracts=spec.contracts, skeleton=spec.skeleton,
                         searcher=searcher)
            r.manifest_path = str(mf.write(paths, m))
            r.manifest_hits = m.hits
            r.manifest_degraded = m.degraded
        results.append(r)

    return Registered(work_id=work_id, tasks=results)
