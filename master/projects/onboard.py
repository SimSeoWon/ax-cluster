"""신규 프로젝트 온보딩 — **등록 한 번으로 서버·클라 전부** (`#259`, §12.5-d).

## 왜 이 파일이 있나

사용자 2026-08-22: *"마스터에 레포 등록해서 신규 프로젝트 설정하면 서버는 등록된 워커와 작업 PC에
알아서 설정해야지"* · *"신규 프로젝트 등록해서 인프라 서버에서 먼저 레포를 받고, 각 워커들 설정
하는 부분에 이 기능이 있냐고"*.

실측 2026-08-22 — **등록 하나만 있고 그 뒤가 전부 비어 있었다**:

    [완료] register_project        트윈 디렉토리 · config.yaml · gitignore · git 잠금
    [실패] Gitea bare 만들기        `init --bare`·Gitea API 호출 **0건**
    [실패] 소스 클론               클론 코드 **0건** (`spec.py` 의 단계 *문자열*이 유일한 히트였다)
    [실패] 그래프·합성·색인         부품은 다 있는데 **이어 주는 것이 없다**
    [실패] 워커에 레포 놓기         `probe` 는 `checkout_ok` 를 **재기만** 한다
    [완료] 배달(deliver)           단, **등록이 부르지 않는다** — 사람이 CLI 를 실행했다
    [실패] claimer 상주 등록        `schtasks`/`crontab` 을 **실행하는** 코드 0건 (주석만 있었다)

ModularStage 가 도는 이유는 일회성 경로였다 — `#227` 본문: *"`cp -a` + `infra_state_20260808.zip`
이관이라는 **일회성 경로**로 채웠다"*. 두 번째 프로젝트에 재현할 절차가 없었다.

## 모양 — `finalize_work` 선례

[중요] **기본은 계획만 내고 멈춘다** (`confirm=False`). `confirm=True` 가 이어서 한다.
승인이 곧 트리거이므로 코드의 기본값은 **안 하는 쪽**이어야 한다.

[중요] **단계 선언은 `client/spec.py` 의 `SERVER_STEPS` 다.** 여기는 그 선언의 **판정기와
실행기**다 — 단계 목록을 여기 다시 적으면 두 벌이 되고 다음에 갈린다(`#266` 의 요점).

## [주의] 이 파일이 하지 않는 것

    마운트 전환      §12.5-b 의 되묻기 계약을 타야 한다 — 초기화가 조용히 바꾸지 않는다
    claimer 상주     [중요] 코드는 `#255` 지만 **두 번째 프로젝트에 켜지 않는다.** claim 에
                     프로젝트 축이 없어(`ClaimReq` 에 필드 없음 · `claimer.py:93` 이 읽고도
                     안 보낸다) 두 프로젝트의 claimer 가 동시에 돌면 **남의 태스크를 집는다.**
                     3단계(`#248`) 가 켜진 뒤에 켠다 — 사용자 승인 순서 A→B
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..client import spec
from ..context_search.paths import SOURCE_SUBDIR
from .config import ConfigError, Registry


@dataclass
class StepState:
    """단계 하나의 현재 상태. `done` 은 **실측**이고 `detail` 은 그 근거다."""

    key: str
    what: str
    done: bool
    detail: str = ""
    blocked: str = ""          # 비어 있지 않으면 이 단계를 지금 할 수 없다 (선결 미충족)

    def to_dict(self) -> dict:
        out = {"step": self.key, "what": self.what, "done": self.done}
        if self.detail:
            out["detail"] = self.detail
        if self.blocked:
            out["blocked"] = self.blocked
        return out


@dataclass
class Plan:
    """온보딩 계획. [중요] **무엇이 남았는지를 이름으로** 답한다 (§12.6)."""

    project: str
    steps: list = field(default_factory=list)
    hosts: list = field(default_factory=list)
    error: str = ""

    @property
    def remaining(self) -> list:
        return [s.key for s in self.steps if not s.done]

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "ok": not self.error,
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
            "remaining": self.remaining,
            "hosts": self.hosts,
            "note": ("전부 초기화됐다" if not self.remaining and not self.error
                     else f"남은 단계: {', '.join(self.remaining)}" if self.remaining
                     else self.error),
        }


# ── 단계별 판정 ─────────────────────────────────────────────────────
#
# [중요] 각 함수는 **읽기 전용**이고 `(done, detail)` 을 돌려준다. 판정이 실행과 같은 함수에
# 있으면 `confirm=False` 가 의미를 잃는다 — 계획을 내려면 판정만 돌아야 한다.


def _probe_bare(reg: Registry, name: str) -> tuple:
    from .logic import resolve_bare_path
    try:
        cfg = reg.config_of(name)
    except Exception:                                        # noqa: BLE001
        return False, "프로젝트가 등록되지 않았다 — bare 를 확인할 대상이 없다"
    try:
        p = resolve_bare_path(cfg.project_id, cfg.bare_path)
        return True, p
    except ConfigError as e:
        return False, str(e).splitlines()[0]


def _probe_register(reg: Registry, name: str) -> tuple:
    if name not in reg.names:
        return False, "레지스트리에 없다"
    d = reg.dir_of(name)
    cfg = d / "config.yaml"
    if not cfg.is_file():
        return False, f"config.yaml 이 없다: {cfg}"
    return True, str(cfg)


def _probe_clone(paths) -> tuple:
    """[주의] 「디렉토리가 있다」로 판정하지 않는다 — 빈 디렉토리를 통과시킨다."""
    if not paths.repo.is_dir():
        return False, f"소스 클론이 없다: {paths.repo}"
    if not (paths.repo / ".git").exists():
        return False, f"git 저장소가 아니다: {paths.repo}"
    if not paths.source.is_dir():
        return False, f"`{SOURCE_SUBDIR}/` 가 없다: {paths.source} — 색인할 소스가 없다"
    return True, str(paths.repo)


def _probe_graph(paths) -> tuple:
    from ..graph import db as gdb, dependency as dep
    c = gdb.counts(paths)
    d = dep.counts(paths)
    if not c.get("classes") and not d.get("files"):
        return False, "class_graph·dependency 둘 다 비었다"
    missing = [n for n, v in (("classes", c.get("classes")), ("files", d.get("files"))) if not v]
    if missing:
        return False, (f"한쪽이 비었다: {', '.join(missing)} "
                       f"(classes={c.get('classes')} files={d.get('files')})")
    return True, f"classes={c['classes']} methods={c['methods']} files={d['files']}"


def _probe_synth(paths) -> tuple:
    """[중요] **재귀로 센다.** `context/*.md` 로 세면 0 이 나온다 — 실물은 하위 디렉토리에
    있다(실측 2026-08-22: `Source/` 927 · `_archive/` 101 · `_domains/` 18 · `Content/` 8)."""
    if not paths.context.is_dir():
        return False, f"context/ 가 없다: {paths.context}"
    n = sum(1 for _ in paths.context.rglob("*.md"))
    if not n:
        return False, "context/ 에 MD 가 없다 — 최초 합성이 아직이다"
    return True, f"MD {n}건"


def _probe_index(paths) -> tuple:
    from .config import ProjectConfig
    try:
        cfg = ProjectConfig.load(paths.config)
    except ConfigError as e:
        return False, str(e)
    c = (cfg.last_indexed_commit or "").strip()
    if not c:
        return False, "last_indexed_commit 이 비어 있다 (register 의 `next` 가 가리키는 그 값)"
    return True, f"{c[:7]} @ {cfg.last_indexed_at or '?'}"


PROBES = {
    "bare": _probe_bare,
    "register": _probe_register,
    "clone": _probe_clone,
    "graph": _probe_graph,
    "synth": _probe_synth,
    "index": _probe_index,
}


def probe_server(name: str, *, registry: Registry | None = None) -> list:
    """서버 절 여섯 단계의 현재 상태. **읽기 전용.**

    [중요] 선결이 깨진 단계는 `blocked` 로 표시하고 **판정을 시도하지 않는다** — 클론이 없는데
    그래프를 재면 "비었다" 가 나오고, 그것은 *"안 만들었다"* 와 *"만들 수 없었다"* 를 섞는다.
    """
    reg = registry or Registry.load()
    out: list = []
    paths = None
    reg_ok = False
    for step in spec.SERVER_STEPS:
        fn = PROBES[step.key]
        if step.key in ("bare", "register"):
            done, detail = fn(reg, name)
            if step.key == "register":
                reg_ok = done
                if done:
                    from ..context_search.paths import resolve
                    try:
                        paths = resolve(name, registry=reg)
                    except ConfigError as e:
                        done, detail = False, f"경로를 풀 수 없다: {e}"
            out.append(StepState(step.key, step.what, done, detail))
            continue
        if not reg_ok or paths is None:
            out.append(StepState(step.key, step.what, False, "",
                                 blocked="register 가 아직이다 — 이 단계는 잴 수 없다"))
            continue
        if step.key != "clone" and not out[2].done:
            out.append(StepState(step.key, step.what, False, "",
                                 blocked="clone 이 아직이다 — 이 단계는 잴 수 없다"))
            continue
        done, detail = fn(paths)
        out.append(StepState(step.key, step.what, done, detail))
    return out


def plan(name: str, *, registry: Registry | None = None, hosts: bool = True) -> Plan:
    """온보딩 계획 — **아무것도 쓰지 않는다.**

    `hosts=False` 로 기계 조회를 끈다(SSH 를 타지 않는다 — 유닛·빠른 확인용).
    """
    p = Plan(project=name)
    reg = registry or Registry.load()
    try:
        p.steps = probe_server(name, registry=reg)
    except Exception as e:                                   # noqa: BLE001
        p.error = f"서버 절 판정 실패: {type(e).__name__}: {e}"
        return p
    if hosts:
        try:
            from .logic import sync_check
            got = sync_check(name)
            p.hosts = got.get("hosts", []) if got.get("checked") else []
            if not got.get("checked"):
                p.error = got.get("reason", "기계 조회 실패")
        except Exception as e:                               # noqa: BLE001
            p.error = f"기계 조회 실패: {type(e).__name__}: {e}"
    return p
