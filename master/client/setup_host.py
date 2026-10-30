"""워커 한 대를 **새로 놓거나 옮긴다** — 등록부 경로 → 낡은 상주 해제 → 클론 → 배달 → 대조.

## 왜 이 파일이 있나

2026-10-30 `.2` 보드 교체: 프로젝트 SSD(E:)를 뺐고 등록부의 `.2` 경로 4개가 전부 `E:\\trunk\\…`
로 남았다. 상주 과제 4개(`AxConductor_*`·`AxWorker_*`)도 사라진 경로를 가리켰다. 사용자:
*"신규 워커 설치시 레포를 다운로드 받고 초기화하는 로직을 파이썬으로 스킬을 만들고 검증"*.

[중요] **부품은 이미 있다 — 여기는 순서만 강제한다.** 클론은 `bundle.bootstrap_checkout`
(`#254`), 상주·지휘자 등록은 `cmd_deliver` 안의 `residency`(`#255`·`#401`), 대조는 `cmd_check`
다. 이 파일이 새로 하는 일은 둘뿐이다 — **등록부 경로 이전**과 **옛 경로를 가리키는 상주 해제**.

## 범위 — 마운트를 따른다

    등록부 경로   이 호스트가 등재된 **모든** 프로젝트 — 사라진 경로를 남기면 거짓이다
    낡은 상주     옛 경로를 **실제로 가리키는** 과제만 — 실측으로 판정한다(이름으로 지우지 않는다)
    클론·배달     **마운트된 프로젝트 하나** — 나머지는 마운트 전환 때 `set_active` 가 맞춘다

[중요] **기본은 계획만 내고 멈춘다** (`confirm=False`) — `finalize_work`·`onboard` 와 같은 모양.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import bundle
from ..projects import logic
from ..projects.config import DRIVEN_SSH, Registry


@dataclass
class Move:
    """프로젝트 하나에서 이 호스트의 등록이 어떻게 바뀌는가."""

    project: str
    old: str            # 빈 값 = 신규 등재
    new: str
    user: str
    driven: str
    role: str
    note: str
    dispatch: str
    mounted: bool

    @property
    def changed(self) -> bool:
        return self.old != self.new


def is_windows_path(path: str) -> bool:
    return len(path) >= 2 and path[1] == ":" or "\\" in path


def relocate(path: str, root: str) -> str:
    """`E:\\trunk\\NS` + `C:\\trunk` → `C:\\trunk\\NS`. 마지막 이름은 그대로 둔다."""
    leaf = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    sep = "\\" if is_windows_path(root) else "/"
    return root.rstrip("\\/") + sep + leaf


def plan(host: str, root: str, *, user: str = "", registry: Registry | None = None) -> list:
    """이 호스트의 이동 계획. 읽기만 한다.

    [중요] 마운트된 프로젝트에 이 호스트가 없으면 `user` 가 있을 때만 **신규 등재**로 넣는다 —
    없으면 거절한다. 계정을 추측하지 않는다(`.2` 는 `janus` 다, `sim` 이 아니다).
    """
    reg = registry or Registry.load()
    mounted = (reg.active or "").strip()
    if not mounted:
        raise ValueError("마운트된 프로젝트가 없다 — `set_active` 먼저")
    moves = []
    for name in reg.names:
        shop = reg.config_of(name).workshops.get(host)
        if shop is None:
            continue
        moves.append(Move(name, shop.path, relocate(shop.path or name, root), shop.user,
                          shop.driven, shop.role, shop.note, shop.dispatch, name == mounted))
    if not any(m.mounted for m in moves):
        if not user:
            raise ValueError(f"{host} 는 마운트된 {mounted} 에 등재돼 있지 않다 — "
                             f"신규 등재하려면 `--user` 를 준다")
        moves.append(Move(mounted, "", relocate(mounted, root), user, DRIVEN_SSH,
                          "worker", "", "", True))
    return moves


def stale_task_names(project: str, windows: bool) -> list:
    """옛 경로를 가리킬 수 있는 과제 이름. 리눅스(cron)는 배달이 표식으로 다시 쓴다."""
    if not windows:
        return []
    from client.init import residency as R
    return [R.task_name(project), R.conductor_task_name(project)]


def points_at(out: str, old: str) -> bool:
    """과제 정의가 옛 경로를 가리키는가. 대소문자 무시 — 윈도우 경로다."""
    return bool(old) and old.lower() in (out or "").lower()


def render(host: str, root: str, moves: list) -> list:
    lines = [f"[setup-host] {host} → {root}"]
    for m in moves:
        tag = "마운트 · 클론→배달→대조" if m.mounted else "경로만 (마운트 전환 때 맞춘다)"
        if not m.old:
            lines.append(f"  ⊕ {m.project}: 신규 등재 {m.user}@{host}:{m.new}  [{tag}]")
        elif m.changed:
            lines.append(f"  → {m.project}: {m.old}  ⇒  {m.new}  [{tag}]")
        else:
            lines.append(f"  = {m.project}: {m.new} (그대로)  [{tag}]")
    return lines


def run(host: str, root: str, *, user: str = "", confirm: bool = False,
        registry: Registry | None = None, ssh=None, deliver=None, check=None) -> int:
    """계획을 찍고, `confirm` 이면 순서대로 실행한다. 단계 실패에서 멈춘다."""
    ssh = ssh or bundle._ssh
    if deliver is None or check is None:
        from . import __main__ as cli
        deliver = deliver or cli.cmd_deliver
        check = check or cli.cmd_check
    try:
        moves = plan(host, root, user=user, registry=registry)
    except ValueError as e:
        print(f"[setup-host] [실패] {e}")
        return 2
    for line in render(host, root, moves):
        print(line)
    if not confirm:
        print("[setup-host] 계획만 출력했다 — 실행하려면 --confirm")
        return 0

    # 1 등록부 — 나머지 필드는 보존한다(`set_workshop` 은 통째로 교체한다)
    for m in moves:
        if not m.changed:
            continue
        logic.set_workshop(m.project, host, driven=m.driven, path=m.new, user=m.user,
                           role=m.role, note=m.note, dispatch=m.dispatch, registry=registry)
        print(f"  [완료] 등록부 {m.project}: {m.new}")

    # 2 옛 경로를 실제로 가리키는 상주만 해제 — 조회 실패는 「없음」으로 접지 않고 찍는다
    windows = is_windows_path(root)
    for m in moves:
        if not m.old or not m.changed:
            continue
        for name in stale_task_names(m.project, windows):
            rc, out = ssh(host, m.user, f"schtasks /query /tn {name} /v /fo LIST")
            if rc != 0:
                print(f"  [setup-host] {name}: 등록 없음 (rc={rc})")
                continue
            if not points_at(out, m.old):
                print(f"  [setup-host] {name}: 옛 경로를 가리키지 않는다 — 둔다")
                continue
            rc, out = ssh(host, m.user, f"schtasks /delete /f /tn {name}")
            if rc != 0:
                print(f"  [setup-host] [실패] {name} 해제 rc={rc}: {(out or '').strip()[:200]}")
                return 1
            print(f"  [완료] 낡은 상주 해제 {name} (→ {m.old})")

    # 3 마운트된 프로젝트 — 클론(없으면)·배달·상주 등록은 deliver, 판정은 check
    target = next(m for m in moves if m.mounted)
    print(f"[setup-host] deliver {target.project} --host={host}")
    if deliver(target.project, only=host) != 0:
        print("[setup-host] [실패] deliver — 여기서 멈춘다")
        return 1
    print(f"[setup-host] check {target.project} --host={host}")
    rc = check(target.project, only=host)
    print(f"[setup-host] {'[완료]' if rc == 0 else '[실패]'} check rc={rc}")
    return rc
