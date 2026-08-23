"""마스터 서비스가 **도는 코드**가 최신인가 (`#301`).

## [중요] 왜 필요한가 — 실측된 사고

    ax-task-queue 기동   2026-08-23 02:19
    `#293` 코드 변경      2026-08-24 00:48  (프로젝트 축 배선)
    → 파일은 새 코드, **도는 것은 옛 코드**

증상: `.33` 이 `project=NS` 를 보냈는데 목록이 **92건(modularstage)** 을 돌려줬다. 옛 코드에는
그 축이 없으니 기본값을 본 것이다. **하루 동안 `.33` 의 태그가 무시되고 있었다.**

[중요] `#277` 과 **같은 병, 다른 주체**다. 그쪽은 워커의 상주(claimer)를 고쳤고 배달이 그것을
본다. 이쪽은 **마스터 자신의 서비스**인데 아무도 안 본다 — 그래서 같은 문장이 다른 자리에서
재현됐다. 리포트 34 §3 이 *"확인은 파일 해시가 아니라 도는 프로세스로 한다"* 를 적었는데,
그 판정을 마스터 쪽에는 두지 않았다.

## [주의] 판정하고 **말하는 것까지**가 범위다

자동 재기동은 하지 않는다 — `docs/11` §11.5(운영 데몬 재기동은 승인)이고, 그 규칙이 생긴 계기가
*"운영 인프라 PC 의 데몬을 승인 없이 재기동해 강한 항의"* 다.

## [중요] 「상주」와 「발동형」은 다르다

`ax-indexer`·`ax-status` 는 oneshot 이라 **다음 발동이 곧 새 코드**다 — 판정 대상이 아니다.
그것을 섞으면 늘 빨간 줄이 하나 있는 화면이 되고, 그러면 아무도 안 본다.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 서비스 → 그 서비스가 읽는 코드 경로 (`ExecStart` 의 모듈에서 왔다).
# [주의] **넓게 잡지 않는다** — 무관한 파일을 넣으면 늘 stale 로 보여 판정이 죽는다.
RESIDENT: dict = {
    "ax-task-queue": ("master/task_queue",),
    "ax-broker": ("master/broker",),
    "ax-projects": ("master/projects", "master/webui", "master/context_search"),
}
# 발동형 — 판정 대상이 **아니다**(다음 발동이 새 코드다). 이름을 적어 두는 이유는
# 「빠뜨린 것」과 「일부러 뺀 것」을 구분하기 위해서다.
TRIGGERED = ("ax-indexer", "ax-status", "ax-batch")


@dataclass
class Verdict:
    unit: str
    started: int = 0            # ExecMainStartTimestamp (epoch)
    newest: int = 0             # 그 서비스가 읽는 코드의 최신 mtime
    newest_file: str = ""
    stale: bool = False
    why: str = ""
    paths: tuple = field(default_factory=tuple)

    @property
    def line(self) -> str:
        if self.why:
            return f"{self.unit}: [주의] {self.why}"
        if self.stale:
            return (f"{self.unit}: [중요] **옛 코드로 돈다** — 기동 뒤에 "
                    f"`{self.newest_file}` 가 바뀌었다. 재기동이 필요하다 "
                    f"(`sudo -n /usr/bin/systemctl restart {self.unit}`)")
        return f"{self.unit}: 도는 것이 지금 코드다"


def _started(unit: str, *, runner=None) -> tuple:
    """`(epoch, 사유)`. [중요] 판정 근거는 **`ExecMainStartTimestamp`** 다 — 종료코드도
    `is-active` 도 아니다(리포트 26 §5: 실패한 재기동이 옛 프로세스를 남겨 `active` 였다)."""
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                                timeout=10))
    r = run(["systemctl", "show", unit, "-p", "ExecMainStartTimestampMonotonic",
             "-p", "ExecMainStartTimestamp", "--value"])
    if r.returncode != 0:
        return 0, f"systemctl 을 읽지 못했다 (rc={r.returncode})"
    lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
    if not lines:
        return 0, "기동 시각이 비어 있다 — 서비스가 한 번도 안 떴을 수 있다"
    # `date -d` 로 파싱한다 — 로케일·형식이 환경마다 다르므로 우리가 추측하지 않는다
    for text in lines:
        p = run(["date", "-d", text, "+%s"])
        if p.returncode == 0 and (p.stdout or "").strip().isdigit():
            return int(p.stdout.strip()), ""
    return 0, f"기동 시각을 파싱하지 못했다: {lines[0][:40]}"


def _newest(paths: tuple) -> tuple:
    """그 코드 경로들의 최신 `.py` mtime `(epoch, 파일)`."""
    best, who = 0, ""
    for rel in paths:
        d = REPO / rel
        if not d.is_dir():
            continue
        for f in d.rglob("*.py"):
            try:
                m = int(f.stat().st_mtime)
            except OSError:
                continue
            if m > best:
                best, who = m, str(f.relative_to(REPO))
    return best, who


def check(unit: str = "", *, runner=None) -> list:
    """상주 서비스별 판정. `unit` 을 주면 그것만."""
    out: list = []
    for name, paths in RESIDENT.items():
        if unit and name != unit:
            continue
        v = Verdict(unit=name, paths=paths)
        v.started, v.why = _started(name, runner=runner)
        v.newest, v.newest_file = _newest(paths)
        if not v.why:
            if not v.newest:
                # [주의] 코드를 못 읽었으면 **「최신이다」로 접지 않는다**
                v.why = f"코드 경로를 읽지 못했다: {', '.join(paths)}"
            else:
                v.stale = v.newest > v.started
        out.append(v)
    return out


def stale_lines(*, runner=None) -> list:
    """사람에게 보일 줄 — **문제 있는 것만.** 조용할 때는 아무 줄도 내지 않는다."""
    return [v.line for v in check(runner=runner) if v.stale or v.why]
