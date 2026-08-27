"""프로젝트 등록·전환 로직 (PLAN §5.5).

등록 순서는 **설정 파일 생성이 먼저다**:

    1. 디렉토리 생성            <root>/<Name>/
    2. config.yaml 작성         무엇을 추적하는지 — 이게 없으면 나머지가 의미가 없다
    3. 루트 목록 등록           projects.yaml 의 projects 에 추가
    4. .gitignore 한 줄         ax-cluster 에 커밋되지 않도록 (§5.5.3-① 유지보수 함정)
    5. git init                 원본(context/·ontology/)을 잠근다. 원격 없음·훅 없음

2 번이 실패하면 1 번에서 만든 빈 디렉토리를 되돌린다 — 목록에 없는 유령 디렉토리가
남으면 3자 일치 검사가 계속 걸린다.

[중요] 5 번의 "원격 없음·훅 없음"은 취향이 아니라 **불변식**이다(§5.5.3-d). 색인 산출물이
훅 이벤트를 만들면 무한 재귀가 된다.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from .config import (ROLE_WORKER,
    DISPATCH_UNSET,
    DRIVEN_INTERACTIVE,
    DRIVEN_SSH,
    GITEA_REPO_ROOT,
    PROJECT_CONFIG,
    ConfigError,
    ProjectConfig,
    Registry,
    Workshop,
    project_id_disk_path,
    validate_name,
    write_project_config,
)

DEFAULT_INCLUDE = ["Source/**/*.cpp", "Source/**/*.h", "Source/**/*.cs", "Config/**"]
# UE5 프로젝트는 용량의 대부분이 uasset 바이너리다 (ModularStage 실측: 1,021MB / 93%).
DEFAULT_EXCLUDE = ["Content/**"]

GITIGNORE = ".gitignore"


def resolve_bare_path(project_id: str, bare_path: str = "") -> str:
    """추적할 bare 저장소 경로를 확정한다. 존재하지 않으면 실패 — 추측하지 않는다."""
    if bare_path:
        p = Path(bare_path)
    else:
        if "/" not in project_id:
            raise ConfigError(
                f"project_id 는 '<owner>/<repo>' 형태여야 한다: {project_id!r}"
            )
        # [중요] 디스크는 소문자다 (§5.5.4-④). `Sim/ModularStage` 를 그대로 쓰면 없는 경로가 된다.
        p = GITEA_REPO_ROOT / f"{project_id_disk_path(project_id)}.git"
    if not (p / "HEAD").is_file():
        raise ConfigError(
            f"bare 저장소가 아니다(또는 읽을 수 없다): {p}\n"
            "Gitea ROOT 는 /var/lib/gitea/gitea-repositories 이고 표준 배치의 "
            "'data/' 세그먼트가 없다. 읽기에는 sim 이 gitea 그룹에 있어야 한다."
        )
    return str(p)


def register_project(
    name: str,
    project_id: str,
    *,
    bare_path: str = "",
    clone_url: str = "",
    branch: str = "main",
    engine: str = "",
    registry: Registry | None = None,
) -> dict:
    """프로젝트를 새로 등록한다. 디지털 트윈 정보를 담을 디렉토리가 여기서 생긴다."""
    reg = registry or Registry.load()
    validate_name(name)

    if name in reg.names:
        raise ConfigError(f"이미 등록된 프로젝트다: {name}")
    target = reg.dir_of(name)
    if target.exists():
        raise ConfigError(f"디렉토리가 이미 있다: {target}")

    resolved_bare = resolve_bare_path(project_id, bare_path)

    # 1. 디렉토리
    target.mkdir(parents=True)
    created_dir = True
    try:
        # 2. config.yaml — 먼저 만든다
        # [중요] **기본 설정을 등록 시점에 적는다** (#266, 사용자 2026-08-22:
        #    *"마스터가 설치해주려고 규격을 정하고 디폴트 설정을 저장하는거잖아"*).
        #    `include`/`exclude` 가 이미 그 관례다 — 사양의 기본값도 같은 자리에 적어야
        #    **사람이 보고 고칠 수 있다.** 비워 두면 「선언할 수 있다」는 사실이 숨는다.
        #    [주의] 값은 그대로가 기본이므로 **동작은 안 바뀐다** — 보이게 하는 것이 목적이다.
        from ..client import spec as _spec
        cfg = ProjectConfig(
            name=name,
            project_id=project_id,
            bare_path=resolved_bare,
            clone_url=clone_url,
            branch=branch,
            engine=engine,
            include=list(DEFAULT_INCLUDE),
            exclude=list(DEFAULT_EXCLUDE),
            # [중요] **레드마인 프로젝트 기본값도 등록 시점에 적는다** (`#293`). 손으로 넣으면
            #    다음 프로젝트에서 또 비고, 그러면 등재가 거부된다(폴백이 없으므로 그것이
            #    설계다 — 조용히 남의 프로젝트에 쓰는 것보다 낫다). 규약은 **소문자 식별자**다
            #    (레드마인 `identifier`: `ModularStage`→`modularstage` · `NS`→`ns`).
            #    [주의] 이 값이 가리키는 레드마인 프로젝트를 **사람이 만들어야** 등재가 된다 —
            #    그 사실은 반환값의 `next` 가 말한다.
            redmine_project=name.lower(),
            raw={"init": {
                "domains": list(_spec.DEFAULT_DOMAINS),
                "convention_sections": list(_spec.DEFAULT_CONVENTION_SECTIONS),
                "extra_skills": {},
                "extra_mcp": {},
            }},
        )
        write_project_config(target / PROJECT_CONFIG, cfg)
        (target / "context").mkdir(exist_ok=True)
        (target / "ontology" / "domains").mkdir(parents=True, exist_ok=True)
    except Exception:
        if created_dir:
            _rmtree_quiet(target)
        raise

    # 3. 루트 목록
    reg.names.append(name)
    if not reg.active:
        reg.active = name
    reg.save()

    # 4. .gitignore
    ignored = _ensure_gitignore(reg.root, name)

    # 5. 원본 잠금 (원격 없음 · 훅 없음)
    git_ok, git_note = _git_init_lock(target, name, project_id)

    return {
        "ok": True,
        "name": name,
        "dir": str(target),
        "config": str(target / PROJECT_CONFIG),
        "bare_path": resolved_bare,
        "active": reg.active,
        "gitignore_added": ignored,
        "git_locked": git_ok,
        "note": git_note,
        "next": ("소스 클론과 최초 색인은 아직이다 — last_indexed_commit 이 비어 있다. "
                 f"[중요] 레드마인 프로젝트 `{cfg.redmine_project}` 는 **사람이 만들어야** "
                 "일감 등재가 된다(없으면 등재가 거부된다 — 폴백하지 않는다, `#293`)."),
    }


def open_works_in_queue(*, fetcher=None) -> list:
    """큐의 **미종결** work 목록 (#210 전환 가드의 눈). 큐에 못 닿으면 예외 — 판단 불가를
    빈 목록으로 접지 않는다 (fail-closed)."""
    import json as _json
    import urllib.request
    if fetcher is not None:
        works = fetcher()
    else:
        from ..auth import auth_headers
        req = urllib.request.Request("http://localhost:8101/api/v1/works",
                                     headers=auth_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            works = _json.loads(r.read().decode("utf-8"))
    terminal = {"merged", "rejected", "cancelled"}      # task_queue.logic 과 같은 집합
    return [w for w in (works or [])
            if (w.get("merge_status") or "in_progress") not in terminal]


def sync_check(name: str, *, align: bool = False, checker=None, deliverer=None,
               bootstrapper=None) -> dict:
    """이 프로젝트의 등재된 기계들이 **마스터와 같은 버전인지** 본다 (#266, 사용자 2026-08-22).

    > *"마운트 하지 않은 프로젝트를 불필요하게 동기화 할 필요는 없지만 마운트 대상을 바꿀때
    > 체크 한번 해서 맞추면 되는거잖아."*

    [중요] **경계가 그것이다** — 주기 동기도, 미마운트 프로젝트 순회도 하지 않는다. 전환이
    일어나는 그 한 번만 본다. 클러스터는 버전이 하나이므로(`version.compare`) 다르면 맞춘다.

    `align=False`(기본)는 **보고만** 한다 — `finalize_work(confirm=False)` 와 같은 모양이다.
    `align=True` 면 어긋난 기계에 재배달한다. [주의] 남의 기계에 쓰는 동작이라 기본이 아니다.

    `checker`/`deliverer` 는 주입 자리 — 테스트가 SSH 를 타지 않는다.
    """
    from ..client import bundle as _b
    check = checker or (lambda f: _b.compare_version(f))
    deliver = deliverer or (lambda f: _b.deliver(name, f))
    # [중요] **체크아웃이 없는 기계는 배달 대상이 아니라 부트스트랩 대상이다** (`#254`).
    #    종전에는 그렇게 **보고만** 했다 — `align=True` 가 「맞춘다」인데 맞추지 않았다.
    bootstrap = bootstrapper or (lambda f: _b.bootstrap_checkout(name, f))

    hosts, aligned, failed = [], [], []
    try:
        shops = _b.workshops(name)
    except Exception as e:                                   # noqa: BLE001
        return {"checked": False, "reason": f"작업장 목록을 읽지 못했다: {e}"}

    for host, user, path, driven, role, dispatch in shops:
        if driven != DRIVEN_SSH or not user or not path:
            continue                     # 몰 수 없는 기계는 대상이 아니다 (.33 도 배달은 SSH 다)
        try:
            facts = _b.probe(host, user, path, driven, role, dispatch)
        except Exception as e:                               # noqa: BLE001
            hosts.append({"host": host, "ok": False, "reason": f"프로브 실패: {e}"})
            continue
        if not facts.checkout_ok:
            entry = {"host": host, "role": role, "ok": False, "verdict": "no_checkout",
                     "reason": "체크아웃 없음 — 부트스트랩 대상"}
            if align:
                # [중요] 놓고 → **다시 재서** → 배달한다. `bootstrap_checkout` 이 스스로
                #    되재므로(「했다」를 믿지 않는다) 여기서는 그 결과로 facts 를 갱신한다.
                try:
                    entry["bootstrapped"] = bootstrap(facts)
                    facts2 = _b.probe(host, user, path, driven, role, dispatch)
                    if not facts2.checkout_ok:
                        raise RuntimeError("부트스트랩 뒤에도 체크아웃을 못 읽는다")
                    deliver(facts2)
                    entry["aligned"] = True
                    aligned.append(host)
                except Exception as e:                       # noqa: BLE001
                    entry["aligned"] = False
                    entry["align_error"] = f"{type(e).__name__}: {e}"
                    failed.append(host)
            hosts.append(entry)
            continue
        v = check(facts)
        entry = {"host": host, "role": role, "ok": v["ok"], "verdict": v.get("verdict"),
                 "behind": v.get("behind"), "reason": v["reason"]}
        if not v["ok"] and align:
            try:
                deliver(facts)
                entry["aligned"] = True
                aligned.append(host)
            except Exception as e:                           # noqa: BLE001
                entry["aligned"] = False
                entry["align_error"] = f"{type(e).__name__}: {e}"
                failed.append(host)
        hosts.append(entry)

    drifted = [h["host"] for h in hosts if not h["ok"]]
    # [중요] **맞췄는데도 FAIL 로 남는 경우가 하나 있다: 마스터 트리가 dirty 일 때.**
    #    커밋이 같아도(`verdict=same`) 그 커밋이 배달 내용을 다 말하지 못하므로 `ok=False` 다.
    #    판정은 옳지만 사유를 말하지 않으면 *"align 했는데 왜 FAIL?"* 로 읽힌다 — 실측
    #    2026-08-22 에 내가 그렇게 읽었다. 그래서 **무엇을 하면 통과하는지** 함께 낸다.
    dirty_only = bool(drifted) and all(
        (h.get("verdict") == "same") for h in hosts if not h["ok"])
    return {
        "checked": True,
        "hosts": hosts,
        "drifted": drifted,
        "aligned": aligned,
        "align_failed": failed,
        # [중요] 맞추지 않았으면 **사람이 실행할 명령을 돌려준다** (finalize_work 관례).
        "commands": ([] if align or not drifted
                     else [f"python -m master.client deliver {name}"]),
        # [중요] 「맞췄다」와 「맞출 수 없다」를 가른다 — 고칠 곳이 다르다(#276 의 사유 셋과 같은 결).
        "dirty_master": dirty_only,
        "note": ("전부 마스터와 같은 버전이다" if not drifted
                 else (f"커밋은 맞췄다({len(drifted)}대) — 남은 FAIL 은 **마스터 트리가 dirty**"
                       f" 이기 때문이다. 커밋한 뒤 다시 재면 통과한다"
                       if dirty_only and align else
                       f"버전이 다른 기계 {len(drifted)}대 — 클러스터는 버전이 하나다"
                       + ("" if align else ". 맞추려면 align=True 또는 위 명령"))),
    }


def _handover_lines(rep: dict) -> str:
    """거절 메시지에 붙일 **짧은** 인계 요약. [중요] 셈만 주지 않는다 — 이름을 조금이라도 낸다.

    [주의] 전체 보고는 `work/handover.render()` 다. 여기서 그것을 다 쏟으면 예외 메시지가
    화면을 덮는다 — 사람이 읽을 것은 *"무엇이 걸려 있나"* 와 *"어디를 보면 되나"* 다.
    """
    if rep.get("error"):
        return f"  [주의] 인계 조사를 못 했다 — {rep['error']}"
    out = []
    for kind, k in (rep.get("kinds") or {}).items():
        if k.get("error"):
            out.append(f"  [{kind}] 판정 불가 — {k['error']}")
        elif k.get("count"):
            head = ", ".join(str(n) for n in k["names"][:3])
            more = f" … +{k['count'] - 3}" if k["count"] > 3 else ""
            out.append(f"  [{kind}] {k['count']}건 — {head}{more}")
    if not out:
        return "  [인계] 남은 것 없음 (큐의 미종결 work 만 걸려 있다)"
    return "남은 것 (전환하면 잔재가 된다):\n" + "\n".join(out)


def set_active(name: str, *, registry: Registry | None = None,
               force: bool = False, works_fetcher=None,
               sync: bool = True, align: bool = False, sync_fn=None,
               handover_fn=None) -> dict:
    """가리키는 프로젝트를 바꾼다. 디렉토리는 전부 남고 마운트 대상만 바뀐다.

    [중요] 전환 가드 (#210, 사용자 전제 점검 2026-08-17): 큐에 미종결 work 가 있으면
    거부한다 — 원전 데몬은 프로젝트 안에 살아 이 부류가 불가능했지만, 중앙 큐에서 활성을
    바꾸면 미종결 work 의 종결 기록·신호·매니페스트가 **다른 프로젝트 트윈**에 착지한다.
    큐가 죽어 확인이 불가한 것도 거부다 (모르는 채 바꾸지 않는다). `force=True` 는 사람이
    결과를 감수하겠다는 뜻 — 그래도 무엇이 걸려 있었는지는 결과에 남긴다.
    """
    reg = registry or Registry.load()
    validate_name(name)
    if name not in reg.names:
        raise ConfigError(
            f"등록되지 않은 프로젝트다: {name}. 등록된 것: {', '.join(reg.names) or '(없음)'}"
        )
    problems = _check_one(reg, name)
    if problems:
        raise ConfigError("전환할 수 없다 — " + " / ".join(problems))

    # [중요] **전환은 인계다** (`#253`, 사용자 정정 2026-08-22: *"그냥 바라보는 레포만
    #    바꾸는건 잘못된거지"*). 떠나는 프로젝트에 남는 것을 **다섯 부류 전부 이름으로** 낸다 —
    #    거절할 때도, 넘어갈 때도. [주의] 이 도구는 **조사만** 한다: 지우는 주체·범위는
    #    `#253` 의 [미결] 이고 사람 결정 자리다.
    def _handover(of: str) -> dict:
        if handover_fn is not None:
            return handover_fn(of)
        try:
            from ..work import handover as H
            return H.survey_project(of)
        except Exception as e:                           # noqa: BLE001
            return {"project": of, "error": f"인계 조사 실패: {e}", "clean": False}

    forced_over: list = []
    leaving = reg.active if (reg.active and reg.active != name) else ""
    if reg.active and reg.active != name:
        try:
            open_works = open_works_in_queue(fetcher=works_fetcher)
        except Exception as e:                           # noqa: BLE001
            if not force:
                raise ConfigError(
                    f"전환할 수 없다 — 큐의 미종결 work 를 확인하지 못했다 ({e}). "
                    f"모르는 채 바꾸지 않는다. 감수하려면 force") from e
            forced_over = [f"(확인 불가: {e})"]
        else:
            if open_works and not force:
                ids = ", ".join(str(w.get("work_id") or "?") for w in open_works[:5])
                # [중요] **거절만 하지 않는다 — 무엇을 치워야 하는지 이름으로 말한다** (`#253`).
                #    종전에는 문을 잠그기만 했고 잠긴 문 안을 보는 도구가 없었다.
                rep = _handover(leaving or reg.active)
                raise ConfigError(
                    f"전환할 수 없다 — 미종결 work {len(open_works)}건이 큐에 있다 ({ids}"
                    + (" …" if len(open_works) > 5 else "") + "). 종결시키거나 force. "
                    f"[중요] 그냥 바꾸면 그 work 의 기록·신호가 새 프로젝트 트윈에 착지한다\n"
                    + _handover_lines(rep))
            if open_works:
                forced_over = [str(w.get("work_id") or "?") for w in open_works]

    previous = reg.active
    changed = previous != name
    reg.active = name
    reg.save()

    cfg = reg.config_of(name)
    out_forced = ({"forced_over_open_works": forced_over,
                   "warning": "[중요] 미종결 work 를 둔 채 강제 전환했다 — 그 work 의 "
                              "기록·신호는 스탬프(#210)가 있으면 제 프로젝트로, 없으면 "
                              "새 활성 트윈으로 간다"} if forced_over else {})
    # [중요] **전환이 동기화 지점이다** (사용자 2026-08-22). 마운트가 실제로 바뀔 때만 본다 —
    #    같은 프로젝트를 다시 가리키는 호출에 SSH 를 태우지 않고, 미마운트 프로젝트는 순회하지
    #    않는다. 기본은 **보고**이고 `align=True` 가 맞춘다(남의 기계에 쓰는 동작이라 기본 아님).
    handover_out: dict = {}
    if changed and leaving:
        # [중요] 넘어간 뒤에도 남은 것을 낸다 — 「전환됨」만 보고하면 잔재가 조용히 남는다.
        handover_out = _handover(leaving)
    sync_out: dict = {}
    if sync and changed:
        runner = sync_fn or (lambda: sync_check(name, align=align))
        try:
            sync_out = {"sync": runner()}
        except Exception as e:                               # noqa: BLE001
            # [주의] 전환은 이미 됐다 — 동기 확인 실패로 전환을 되돌리지 않는다. 사유만 싣는다.
            sync_out = {"sync": {"checked": False, "reason": f"{type(e).__name__}: {e}"}}

    return {
        "ok": True,
        "previous": previous,
        "active": name,
        **out_forced,
        **sync_out,
        # [중요] **떠난 프로젝트에 남은 것**을 다섯 부류 이름으로 (`#253`). 없으면 키도 없다.
        **({"handover": handover_out} if handover_out else {}),
        "project_id": cfg.project_id,
        "branch": cfg.branch,
        "last_indexed_commit": cfg.last_indexed_commit,
        # [중요] 이 문구는 `#242` 로 **참이 됐다.** 그 전에는 색인기가 마운트를 보지 않아
        #    *"멈춰 있었다"* 가 없는 동작을 전제했다(`#241` 이 그것을 적발했다).
        # [주의] 따라잡는 **기준은 `last_indexed_commit` 이 아니라 미러 HEAD** 다 —
        #    `process_event` 가 `rev-parse HEAD` → `fetch` → 그 사이를 diff 한다. 마운트 밖이면
        #    fetch 를 안 하므로 미러가 그대로 있고, 재개 시 그 지점부터 전부 들어온다.
        #    워터마크는 색인한 것이 있을 때만 전진하므로(`#244`) 따라잡기 기준이 될 수 없다.
        "note": (
            "가리키는 프로젝트가 다른 동안에는 이 프로젝트의 문서 갱신이 멈춰 있었다(#242). "
            "재개하면 미러 HEAD 부터 따라잡는다."
            if cfg.last_indexed_commit
            else "아직 한 번도 색인하지 않았다(last_indexed_commit 이 비어 있다)."
        ),
    }


def list_projects(*, registry: Registry | None = None) -> dict:
    reg = registry or Registry.load()
    items = []
    for name in reg.names:
        entry: dict = {"name": name, "active": name == reg.active}
        try:
            cfg = reg.config_of(name)
            entry.update(
                project_id=cfg.project_id,
                branch=cfg.branch,
                last_indexed_commit=cfg.last_indexed_commit,
                last_indexed_at=cfg.last_indexed_at,
                workshops={h: w.to_dict() for h, w in cfg.workshops.items()},
            )
        except ConfigError as e:
            entry["error"] = str(e)
        items.append(entry)
    return {"active": reg.active, "projects": items, "problems": reg.check()}


# ─────────────────────────────────────────
# 워크숍 (§5.5.4)
# ─────────────────────────────────────────

def set_workshop(
    name: str,
    host: str,
    *,
    driven: str = DRIVEN_INTERACTIVE,
    path: str = "",
    user: str = "",
    role: str = ROLE_WORKER,
    note: str = "",
    dispatch: str = DISPATCH_UNSET,
    registry: Registry | None = None,
) -> dict:
    """작업장 한 대의 체크아웃을 등록하거나 갱신한다 (§5.5.4).

    같은 host 로 다시 부르면 **통째로 교체**한다 — 부분 병합하지 않는다.
    병합하면 "driven 을 interactive 로 바꿨는데 예전 path 가 남아 있는" 상태가 생기고,
    그 상태는 파일만 봐서는 의도인지 사고인지 구분되지 않는다.
    """
    reg = registry or Registry.load()
    validate_name(name)
    if name not in reg.names:
        raise ConfigError(
            f"등록되지 않은 프로젝트다: {name}. 등록된 것: {', '.join(reg.names) or '(없음)'}"
        )
    cfg_path = reg.dir_of(name) / PROJECT_CONFIG
    cfg = ProjectConfig.load(cfg_path)

    shop = Workshop(
        host=str(host).strip(),
        driven=str(driven).strip(),
        path=str(path).strip(),
        user=str(user).strip(),
        role=str(role).strip(),
        note=str(note).strip(),
        dispatch=str(dispatch).strip(),
    )
    shop.validate()  # fail-closed — 검증 전에 파일을 건드리지 않는다

    previous = cfg.workshops.get(shop.host)
    cfg.workshops[shop.host] = shop
    write_project_config(cfg_path, cfg)

    return {
        "ok": True,
        "project": name,
        "host": shop.host,
        "workshop": shop.to_dict(),
        "replaced": previous.to_dict() if previous else None,
        "drivable": shop.drivable,
        "dispatch": shop.dispatch or "(미지정 — role 에서 유도)",
        "note": (
            f"마스터가 {shop.user}@{shop.host}:{shop.path} 로 밀어넣을 수 있다."
            if shop.drivable
            else "대화형 워크숍이다 — 마스터는 이 머신을 원격으로 몰지 않는다 (§5.5.4-②)."
        ),
    }


def remove_workshop(
    name: str, host: str, *, registry: Registry | None = None
) -> dict:
    """워크숍 등록을 해제한다. 원격 디렉토리는 건드리지 않는다 — 레지스트리에서만 뺀다."""
    reg = registry or Registry.load()
    validate_name(name)
    if name not in reg.names:
        raise ConfigError(f"등록되지 않은 프로젝트다: {name}")
    cfg_path = reg.dir_of(name) / PROJECT_CONFIG
    cfg = ProjectConfig.load(cfg_path)

    host = str(host).strip()
    if host not in cfg.workshops:
        raise ConfigError(
            f"{name} 에 등록된 워크숍이 아니다: {host}. "
            f"등록된 것: {', '.join(cfg.workshops) or '(없음)'}"
        )
    removed = cfg.workshops.pop(host)
    write_project_config(cfg_path, cfg)
    return {
        "ok": True,
        "project": name,
        "host": host,
        "removed": removed.to_dict(),
        "note": "레지스트리에서만 뺐다. 원격 디렉토리는 그대로 있다.",
    }


def list_workshops(name: str = "", *, registry: Registry | None = None) -> dict:
    """워크숍 목록. `name` 을 비우면 지금 마운트된 프로젝트를 본다."""
    reg = registry or Registry.load()
    target = name or reg.active
    if not target:
        raise ConfigError("active 가 비어 있고 name 도 주지 않았다.")
    validate_name(target)
    if target not in reg.names:
        raise ConfigError(f"등록되지 않은 프로젝트다: {target}")
    cfg = reg.config_of(target)
    shops = [dict(host=h, **w.to_dict()) for h, w in cfg.workshops.items()]
    return {
        "project": target,
        "active": target == reg.active,
        "workshops": shops,
        "drivable_hosts": [w.host for w in cfg.workshops.values() if w.drivable],
    }


# ─────────────────────────────────────────
# 내부
# ─────────────────────────────────────────

def _check_one(reg: Registry, name: str) -> list[str]:
    problems = []
    d = reg.dir_of(name)
    if not d.is_dir():
        problems.append(f"디렉토리가 없다: {d}")
    elif not (d / PROJECT_CONFIG).is_file():
        problems.append(f"{PROJECT_CONFIG} 가 없다")
    else:
        cfg = ProjectConfig.load(d / PROJECT_CONFIG)
        if cfg.name != name:
            problems.append(f"config.yaml 의 name 이 {cfg.name!r} 이다")
    return problems


def _ensure_gitignore(root: Path, name: str) -> bool:
    """`ax-cluster/.gitignore` 에 `/<Name>/` 한 줄을 넣는다. 이미 있으면 그대로 둔다."""
    path = root / GITIGNORE
    line = f"/{name}/"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if line in existing.splitlines():
        return False
    with path.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"{line}\n")
    return True


def _git_init_lock(target: Path, name: str, project_id: str) -> tuple[bool, str]:
    """원본을 잠그는 로컬 저장소. **원격도 훅도 붙이지 않는다** (§5.5.3-d)."""
    try:
        (target / GITIGNORE).write_text(
            "# 파생 자산 — 재색인으로 복구된다 (PLAN §5.4.7)\n"
            "vector_db/\nbm25.db\nclass_graph.db\ndependency_graph.db\n\n"
            "# 소스 클론 — 원본은 Gitea 에 있다\nrepo/\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target, check=True)
        subprocess.run(["git", "add", "-A"], cwd=target, check=True)
        subprocess.run(
            [
                "git", "commit", "-q", "-m",
                f"등록: {name} ({project_id}) — 디지털 트윈 디렉토리 생성\n\n"
                f"생성 시각 {datetime.now().isoformat(timespec='seconds')}\n"
                "원격 없음 · 훅 없음 (PLAN §5.5.3-d 자기 유발 재귀 금지).",
            ],
            cwd=target,
            check=True,
        )
        return True, "원본 잠금 완료(로컬 git, 원격 없음·훅 없음)."
    except (OSError, subprocess.CalledProcessError) as e:
        return False, f"git 잠금 실패(등록 자체는 유효): {e}"


def _rmtree_quiet(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
