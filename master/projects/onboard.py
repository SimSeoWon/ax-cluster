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
from pathlib import Path

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


def _probe_hook(reg: Registry, name: str) -> tuple:
    """저장소에 우리 훅이 붙어 있는가. [주의] `sim` 은 `gitea` 그룹이라 **읽기는 된다** —
    설치만 root 가 필요하다."""
    from .logic import resolve_bare_path
    try:
        cfg = reg.config_of(name)
        bare = Path(resolve_bare_path(cfg.project_id, cfg.bare_path))
    except Exception as e:                                   # noqa: BLE001
        return False, f"bare 를 풀지 못했다: {e}"
    # [주의] **둘 다 `post-receive.d/` 안**에 있다 — `install_hook.py:82` 가 `hook_dir` 기준으로
    #    쓴다(*"훅 옆에 둔다"*). 처음에 `hooks/ax-project-id` 로 짚어 판정이 늘 [남음] 이었다.
    hook_dir = bare / "hooks" / "post-receive.d"
    hook = hook_dir / "ax-index"
    pid = hook_dir / "ax-project-id"
    missing = [p.name for p in (hook, pid) if not p.is_file()]
    if missing:
        return False, f"없다: {', '.join(missing)} ({hook_dir})"
    return True, str(hook)


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
    """[중요] **문서 없는 그룹 수로 판정한다** (`#274`). 「MD 가 있다」로 재면 **부분 완료가
    「완료」로 읽힌다** — 실측 2026-08-22: NS 가 42그룹 중 13건인 상태에서 `[완료]` 로 찍혔고,
    그 상태로 마운트하면 색인기가 워터마크를 찍어 온보딩이 *"전부 초기화됐다"* 고 거짓 보고했다.

    [주의] **개수 비교로는 안 된다** — ModularStage 는 문서 1,055 > 그룹 909 다(`_archive/`·
    `_domains/`·삭제된 파일의 문서가 쌓인다). 그래서 **그룹마다 문서가 있는지**를 센다.
    실측: ModularStage 0 · NS 42(전부 없음). 비용 6~64ms, LLM 0.

    [주의] 게이트가 거부한 그룹은 문서가 없는 것이 옳다 — 그러면 이 판정은 계속 `[남음]` 이다.
    그것이 정직하다: `skip_existing=True` 라 재실행이 그 그룹만 다시 시도하므로 **남음 = 재시도
    대상**이라는 말이 참이다. 「완료」로 접으면 다시 시도할 근거가 사라진다.
    """
    if not paths.context.is_dir():
        return False, f"context/ 가 없다: {paths.context}"
    from ..context_synth import synth
    from ..graph import class_graph as cg
    try:
        groups = synth.group(cg.list_source_files(paths))
    except Exception as e:                                   # noqa: BLE001
        return False, f"그룹을 세지 못했다: {type(e).__name__}: {e}"
    if not groups:
        return False, "합성할 그룹이 없다 (Source/ 경계를 확인하라)"
    missing = [k for k in groups if not synth.doc_path(paths, k).is_file()]
    have = len(groups) - len(missing)
    unk = unstamped(paths)
    # [중요] **「모른다」를 세어서 말한다** (`#282`, 사용자 지시 2026-08-23). 스탬프 없는 문서는
    #    「최신」이 아니라 **미확인**이다 — 그 값이 최신화 판단의 한쪽이므로, 없으면 그 문서에
    #    대해서는 판단 자체가 불가능하다. [주의] 여기서 **채우지 않는다** — 추정 스탬프는
    #    그 문서를 영구히 「최신」으로 굳혀 재합성을 다시는 안 걸리게 만든다(`#275`).
    tail = f" · [주의] 스탬프 미확인 {unk[0]}/{unk[1]}" if unk[0] else ""
    if missing:
        return False, (f"{have}/{len(groups)} 그룹 — {len(missing)}개 미합성 "
                       f"(예: {', '.join(sorted(missing)[:2])}){tail}")
    return True, f"{have}/{len(groups)} 그룹 완료{tail}"


def unstamped(paths) -> tuple:
    """컨텍스트 MD 중 `source_commit` 이 **없는** 것 `(미확인, 전체)` (`#282`).

    [중요] 이 값이 0 이 아니면 그만큼은 **최신인지 알 수 없다.** `stale` 판정이 저장 스탬프와
    문서 스탬프를 비교하므로, 문서 쪽이 없으면 `-1 == -1` 로 조용히 통과한다(`#275` 가 도메인
    축에서 잰 그 구멍이 컨텍스트 축에도 있다 — 실측 2026-08-23 ModularStage 1,010/1,055).

    [주의] **채우는 함수가 아니다.** 세는 함수다.
    """
    from ..context_synth import md as md_mod

    ctx = paths.context
    if not ctx.is_dir():
        return 0, 0
    total = miss = 0
    for f in ctx.rglob("*.md"):
        total += 1
        try:
            if md_mod.read_source_commit(f.read_text(encoding="utf-8", errors="replace")) == "-1":
                miss += 1
        except OSError:
            miss += 1
    return miss, total


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
    "hook": _probe_hook,
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
        if step.key in ("bare", "register", "hook"):
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
        # [주의] clone 의 인덱스가 밀렸다 — 이름으로 찾는다(위치로 세면 단계가 늘 때 조용히 깨진다)
        _clone_done = next((s.done for s in out if s.key == "clone"), False)
        if step.key != "clone" and not _clone_done:
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


# ── 실행기 ─────────────────────────────────────────────────────────
#
# [중요] **`confirm=False` 가 기본이다.** 승인이 곧 트리거이므로 코드의 기본값은 안 하는 쪽이다
# (`finalize_work` 선례). 그리고 `only=` 로 단계를 끊을 수 있다 — `synth` 는 LLM 을 태우므로
# 돈과 시간이 들고, 저장소 관례가 *"단계마다 사람이 끊는다"* 다.

# [중요] 마스터는 소스 저장소에 push 하지 않는다(§2.1). URL 이 아닌 **센티넬**을 넣어 시도 자체가
#    시끄럽게 실패하게 한다 — 기존 `ModularStage/repo` 가 그렇게 되어 있고 그 관례를 복제한다.
PUSH_DISABLED = "DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1"
WRITE_REMOTE = "gitea-write"


def _git(cwd, *args, timeout: int = 600, env_extra=None) -> tuple:
    import os as _os
    import subprocess
    env = None
    if env_extra:
        env = dict(_os.environ)
        env.update(env_extra)
    r = subprocess.run(["git", *(["-C", str(cwd)] if cwd else []), *args],
                       capture_output=True, text=True, timeout=timeout, check=False, env=env)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _ensure_safe_directory(bare: str) -> str:
    """[중요] §5.5.3-a — bare 는 `gitea` 소유라 global config 의 `safe.directory` 가 **유일한
    방법**이다. `-c` 도 `GIT_CONFIG_*` 환경변수도 무시된다(git 2.34.1 실측)."""
    rc, out = _git(None, "config", "--global", "--get-all", "safe.directory")
    if bare in (out or "").splitlines():
        return "이미 등록됨"
    rc, out = _git(None, "config", "--global", "--add", "safe.directory", bare)
    if rc != 0:
        raise ConfigError(f"safe.directory 등록 실패: {out[:200]}")
    return "등록함"


HOOK_WRAPPER = "/usr/local/bin/ax-install-hook"


def do_hook(paths) -> str:
    """훅 설치 — **무인으로 돈다** (sudoers NOPASSWD, 사용자 결정 2026-08-22).

    [중요] root 가 필요한 단계인데 `pkexec` 로 두면 **사람이 인증창을 눌러야** 하고 그것은
    자동이 아니다. 이 프로젝트는 자동화를 전제로 구성된다 — 그래서 래퍼 한 경로만 허용하는
    sudoers 규칙을 등록했다(`/etc/sudoers.d/ax-install-hook`).

    [주의] 실패를 삼키지 않는다 — 규칙이 없거나 지워지면 `sudo -n` 이 즉시 실패하고, 그
    사유를 그대로 낸다(조용히 건너뛰면 훅 없는 프로젝트가 「완료」로 보인다).
    """
    import subprocess
    if not Path(HOOK_WRAPPER).is_file():
        raise ConfigError(f"훅 설치 래퍼가 없다: {HOOK_WRAPPER} — sudoers 등록이 풀렸다")
    r = subprocess.run(["sudo", "-n", HOOK_WRAPPER, "--apply"],
                       capture_output=True, text=True, timeout=300, check=False)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        raise ConfigError(f"훅 설치 실패(rc={r.returncode}) — {out[:300]}")
    done = [l.strip() for l in out.splitlines() if "[완료]" in l]
    return f"{len(done)}개 설치/확인" + (f" · {done[-1][:80]}" if done else "")


def do_clone(paths, cfg) -> str:
    """소스 클론 — 기존 `ModularStage/repo` 의 리모트 구성을 **복제한다**.

    [주의] 클론 자체보다 **리모트 구성이 계약이다**: `origin` 은 로컬 bare 에서 fetch 하고
    push 는 센티넬로 막히며, attempt push 는 `gitea-write` 로만 나간다.
    """
    notes = [f"safe.directory {_ensure_safe_directory(cfg.bare_path)}"]
    if paths.repo.exists() and any(paths.repo.iterdir()):
        raise ConfigError(f"이미 무언가 있다: {paths.repo} — 덮지 않는다")
    # [중요] **LFS smudge 를 끈다** (실측 2026-08-22, NS 라이브 런에서 잡혔다).
    #    NS 의 `.gitattributes` 가 `*.uasset filter=lfs` 라, 로컬 bare 경로에서 클론하면 LFS
    #    엔드포인트가 없어 *"Smudge error: Error downloading …"* 로 클론이 실패한다.
    #    [중요] 그런데 **마스터는 그 바이트가 필요 없다** — `Content/**` 는 색인 제외이고 트윈의
    #    범위는 source-only 다. 포인터만 받으면 되고, 그 편이 137MB+ 를 안 내려받아 더 낫다.
    #    [주의] ModularStage 는 LFS 를 쓰지 않아(매칭 0건) 이 함정이 지금까지 안 드러났다 —
    #    그 클론은 `cp -a` 로 만들어졌다(§5.5.3-a).
    rc, out = _git(None, "clone", "--branch", cfg.branch or "main",
                   cfg.bare_path, str(paths.repo), timeout=1800,
                   env_extra={"GIT_LFS_SKIP_SMUDGE": "1"})
    if rc != 0:
        raise ConfigError(f"클론 실패: {out[:300]}")
    notes.append("LFS smudge 생략(포인터만 — Content/ 는 색인 제외)")
    rc, out = _git(paths.repo, "remote", "set-url", "--push", "origin", PUSH_DISABLED)
    if rc != 0:
        raise ConfigError(f"origin push 차단 실패: {out[:200]}")
    notes.append("origin push 차단(센티넬)")
    if cfg.clone_url:
        rc, out = _git(paths.repo, "remote", "add", WRITE_REMOTE, cfg.clone_url)
        notes.append(f"{WRITE_REMOTE} 추가" if rc == 0 else f"{WRITE_REMOTE} 실패: {out[:80]}")
    else:
        notes.append(f"[주의] clone_url 이 비어 {WRITE_REMOTE} 를 못 만들었다 — attempt push 불가")
    rc, head = _git(paths.repo, "rev-parse", "--short", "HEAD")
    return f"{head} · " + " · ".join(notes)


def do_graph(paths) -> str:
    """그래프 전체 구축 — LLM 0. 결정적이라 싸다."""
    from ..graph import class_graph as cg, dependency as dep
    a = cg.build_full(paths)
    b = dep.build_full(paths)
    return f"class_graph {getattr(a, 'classes', '?')} · dependency {getattr(b, 'files', '?')}"


def do_synth(paths, *, limit: int = 0) -> str:
    """컨텍스트 MD 최초 합성 — [중요] **LLM 을 태운다.** 원전 `initial_context_build` 대응.

    `skip_existing=True` 라 중단 후 재실행이 누락분만 채운다(원전과 같은 계약).

    [중요] **`commit` 을 반드시 넘긴다** (사용자 지적 2026-08-22: *"컨텍스트 문서 작성할 때
    해시값 처리 안한 것도 문제"*). 처음엔 안 넘겨서 **최초 합성 문서 전부가 `source_commit`
    없이** 만들어졌다 — `md.py:153` 이 *"`commit` 이 비면 그 줄이 안 붙는다"* 고 적어 뒀고,
    `md.py:19` 는 그 값이 **중 1.3 stale 판정의 한쪽**이라고 못박았다. 즉 신규 프로젝트가
    처음부터 「어느 커밋 기준인지 모르는 문서」로 시작하게 되는 것이었다
    (`#275` 가 ModularStage 이관물에서 지적한 그 상태를 새 프로젝트에 재생산하는 코드였다).
    [주의] 훅 경로(`consumer._synthesize`)는 `commit=r.to_commit` 을 넘긴다 — 두 경로가
    달랐다. **같은 계약이어야 한다.**
    """
    from ..context_synth import synth
    rc, head = _git(paths.repo, "rev-parse", "HEAD")
    if rc != 0 or not (head or "").strip():
        raise ConfigError("HEAD 를 읽지 못해 합성하지 않는다 — source_commit 없는 문서를 "
                          "만들면 stale 판정이 그 문서에 영원히 안 먹는다")
    s = synth.run(paths, changed=None, skip_existing=True, limit=limit,
                  commit=head.strip())
    return (f"{head.strip()[:7]} · 그룹 {s.groups} · 작성 {s.written} · 건너뜀 {s.skipped} "
            f"· 거부 {s.refused} · 사실게이트 {s.unfactual} · 실패 {s.failed}"
            + (f" · [중요] {s.aborted}" if s.aborted else ""))


def do_index(paths) -> str:
    """색인 전체 구축 + 워터마크 기입. [중요] 워터마크가 이 흐름의 완료 지표다."""
    from ..context_search.rebuild import rebuild_all
    from ..events.consumer import _update_watermark
    st = rebuild_all(paths)
    rc, head = _git(paths.repo, "rev-parse", "HEAD")
    if rc != 0 or not head:
        raise ConfigError("HEAD 를 읽지 못해 워터마크를 찍지 않는다 — 색인만 됐다")
    _update_watermark(paths, head.strip())
    return f"vector {getattr(st, 'vector_docs', '?')} · 워터마크 {head.strip()[:7]}"


RUNNERS = {"hook": do_hook, "clone": do_clone, "graph": do_graph,
           "synth": do_synth, "index": do_index}


def run(name: str, *, confirm: bool = False, only=None, registry: Registry | None = None,
        limit: int = 0) -> dict:
    """서버 절을 이어서 실행한다. [중요] **`confirm=False` 는 계획만 낸다.**

    `only` — 실행할 단계 이름들. 없으면 남은 것 전부. `synth` 는 LLM 을 태우므로 끊을 수 있게 뒀다.
    """
    reg = registry or Registry.load()
    from ..context_search.paths import resolve
    from .config import ProjectConfig

    steps = probe_server(name, registry=reg)
    remaining = [s.key for s in steps if not s.done and s.key in RUNNERS]
    todo = [k for k in remaining if not only or k in set(only)]
    out = {"project": name, "confirm": confirm, "remaining": remaining, "todo": todo,
           "done": [], "results": {}, "error": ""}
    blockers = [s.key for s in steps if not s.done and s.key not in RUNNERS]
    if blockers:
        out["error"] = (f"이 흐름이 만들 수 없는 단계가 남았다: {', '.join(blockers)} "
                        f"— `bare` 는 Gitea 에, `register` 는 register_project 가 만든다")
        return out
    if not confirm:
        out["commands"] = [f"python -m master.projects.onboard {name} --confirm"
                           + (f" --only {','.join(todo)}" if only else "")]
        out["note"] = ("할 것이 없다" if not todo
                       else f"실행할 단계: {', '.join(todo)} — confirm=True 가 이어서 한다")
        return out

    paths = resolve(name, registry=reg)
    cfg = ProjectConfig.load(paths.config)
    for key in todo:
        fn = RUNNERS[key]
        try:
            if key == "clone":
                detail = fn(paths, cfg)
            elif key == "hook":
                detail = fn(paths)
            elif key == "synth":
                detail = fn(paths, limit=limit)
            else:
                detail = fn(paths)
        except Exception as e:                               # noqa: BLE001
            # [중요] 뒤 단계를 태우지 않는다 — 클론이 없는데 그래프를 돌리면 0건으로 덮는다.
            out["error"] = f"{key} 실패: {type(e).__name__}: {e}"
            out["results"][key] = f"실패: {e}"
            return out
        out["done"].append(key)
        out["results"][key] = detail
        if key == "clone":
            paths = resolve(name, registry=Registry.load())   # local_clone 재해석
    out["note"] = f"완료: {', '.join(out['done']) or '(없음)'}"
    return out


# ── CLI (`#256`) ──────────────────────────────────────────────────────────────
#
# [중요] **이 진입점이 없었다.** 실측 2026-08-23: `run` 이 안내 문구로
# *"python -m master.projects.onboard <name> --confirm"* 을 돌려주는데 **그 명령이 존재하지
# 않았다** — `plan`·`run` 은 라이브러리뿐이라 파이썬 세션에서만 부를 수 있었다. 그래서 절차가
# 문서가 아니라 **사람(또는 세션)의 기억**에 살았고, 그것이 `#256` 이 말한 병이다.
# [주의] 관례를 따른다 — `plan` 이 기본, `--confirm` 이 트리거(`finalize_work`·`cleanup`·
# `handover` 와 같은 모양).

def render(plan_or_run) -> str:
    """사람이 읽을 보고. [중요] **남은 것을 이름으로** 낸다 — 셈만 주면 판단할 수 없다."""
    d = plan_or_run.to_dict() if hasattr(plan_or_run, "to_dict") else plan_or_run
    lines = [f"온보딩 — {d.get('project')}"]
    for s in d.get("steps", []):
        mark = "[완료]" if s.get("done") else ("[막힘]" if s.get("blocked") else "[남음]")
        why = s.get("detail") or s.get("blocked") or ""
        # [주의] 실물 키는 `step` 이다 — `key` 로 추측했다가 `None` 서식 오류가 났다.
        #    `to_dict` 를 확인해서 쓴다(이번 세션 세 번째 「추측한 이름」이다).
        lines.append(f"  {mark} {s.get('step', '?'):9} {s.get('what', '')}"
                     + (f" — {why}" if why else ""))
    for h in d.get("hosts", []):
        if isinstance(h, str):
            lines.append(f"  · {h}")
            continue
        # [주의] raw dict 를 그대로 찍으면 사람이 못 읽는다 — 무엇이 안 됐는지가 가려진다
        mark = "[완료]" if h.get("ok") else "[남음]"
        lines.append(f"  {mark} {str(h.get('host', '?')):16} {h.get('role', ''):9}"
                     f" {h.get('reason', '')[:70]}")
    if d.get("error"):
        lines.append(f"  [주의] {d['error']}")
    if d.get("note"):
        lines.append(f"  → {d['note']}")
    for c in d.get("commands", []) or []:
        lines.append(f"  실행: {c}")
    return "\n".join(lines)


def main(argv) -> int:
    """`python -m master.projects.onboard <프로젝트> [--confirm] [--only a,b] [--limit N]`

    인자 없이 부르면 사용법. [중요] **`--confirm` 없이는 아무것도 쓰지 않는다.**
    """
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(main.__doc__)
        print("\n  단계:", ", ".join(s.key for s in spec.SERVER_STEPS))
        return 2
    name = args[0]
    confirm = "--confirm" in argv
    only = None
    limit = 0
    for a in argv:
        if a.startswith("--only"):
            v = a.split("=", 1)[1] if "=" in a else ""
            if not v:                       # `--only a,b` 형태
                i = list(argv).index(a)
                v = argv[i + 1] if i + 1 < len(argv) else ""
            only = [x.strip() for x in v.split(",") if x.strip()]
        elif a.startswith("--limit"):
            v = a.split("=", 1)[1] if "=" in a else ""
            if not v:
                i = list(argv).index(a)
                v = argv[i + 1] if i + 1 < len(argv) else "0"
            limit = int(v or 0)
    if not confirm:
        # [중요] 계획은 **호스트까지** 본다 — 서버 절만 보고 「됐다」 하면 클라가 빠진다
        print(render(plan(name)))
        return 0
    out = run(name, confirm=True, only=only, limit=limit)
    print(f"온보딩 실행 — {out['project']} · 남은 단계 {out['remaining']} · 이번 실행 {out['todo']}")
    for k, v in (out.get("results") or {}).items():
        print(f"  [{k}] {str(v)[:160]}")
    if out.get("error"):
        print(f"  [주의] {out['error']}")
        return 1
    print(f"  → 완료 {out.get('done')}")
    # [중요] **하고 나서 다시 잰다** — 「했다」를 믿지 않는다(저장소 하드룰)
    print(render(plan(name)))
    return 0


if __name__ == "__main__":
    import sys as _s
    _s.exit(main(_s.argv[1:]))
