"""요청자(`.33`)의 검수 빌드 — `review_work(build_fn=…)` 에 꽂는 어댑터 (중 2.1 `#135`).

🔴 **여기에 새 판정이 없다.** 명령은 `layer3_verify.build_build_command`, 판정은
`parse_build_log`, 경로 유도는 `skeleton_gate.build_bat_from_editor` 를 **그대로 쓴다.**
이 파일이 하는 일은 셋뿐이다: 검수 트리에서 `.uproject` 를 찾고 · 그 셋을 잇고 ·
`review_work` 가 기대하는 dict 로 바꾼다.

## 왜 로컬인가 (사용자 결정 2026-08-16)

    마스터   UE5 가 없다 → `.2` 에 SSH 로 위임 (`run_build_on_workshop`)
    요청자   🔴 UE5 가 **있고** 검수 worktree 가 자기 디스크에 있다 → 로컬로 돈다

*".33 로컬 (원전 그대로)"* — 원전도 리더 PC 에서 직접 빌드한다. `.2` 위임은 **리눅스가
강제한 변경**이고 여기엔 해당이 없다.

## 🔴 판정을 못 받으면 통과가 아니다

`layer3_verify` 의 계약을 그대로 물려받는다 — **종료 코드를 보지 않는다**(`Build.bat` 은
실패해도 0 을 낸 실측이 있다). 타임아웃·실행 실패도 `passed=False` 이고, 그 이유는
`failure` 로 남는다: **확인하지 못한 것과 통과한 것은 다르다.**
"""
from __future__ import annotations

from pathlib import Path

from ..layer3_verify import BuildResult, run_build_local
from .skeleton_gate import build_bat_from_editor, target_name

DEFAULT_CONFIG = "Development"


class BuildSetupError(RuntimeError):
    """빌드를 **시작조차** 할 수 없다. 🔴 조용히 skip 하지 않는다 — 그건 통과로 읽힌다."""


def result_to_dict(res: BuildResult) -> dict:
    """`review_work` 의 계약(`{"ok": …}`)으로 옮긴다. 나머지는 사람이 읽을 근거다."""
    d = res.to_dict()
    d["ok"] = bool(res.passed)
    return d


def local_build_fn(*, project: str, ue5_cmd: str = "", build_bat: str = "",
                   target: str = "", config: str = DEFAULT_CONFIG,
                   timeout: int = 1800, builder=None):
    """`build_fn(tree) -> dict` 를 만든다.

    `ue5_cmd` 는 배달된 `.ax/config.json` 의 `backends.ue5_cmd` 를 그대로 넣으면 된다
    (🔴 경로를 손으로 적지 말 것 — 마스터가 **프로브해서** 넣은 값이다).

    🔴 **엔진을 못 찾으면 만들 때 죽는다.** 검수를 절반 돌린 뒤 *"빌드는 못 했지만 통과"* 로
    끝나는 것이 최악이라, 그 사실을 **착수 전에** 드러낸다.
    """
    bb = (build_bat or "").strip() or build_bat_from_editor(ue5_cmd)
    if not bb:
        raise BuildSetupError(
            "UE5 Build.bat 을 찾지 못했다 — `.ax/config.json` 의 `backends.ue5_cmd` 를 확인할 것 "
            "(비어 있으면 마스터에 배달을 다시 요청한다). 🔴 확인 불가는 통과가 아니다")
    tgt = (target or "").strip() or target_name(project)
    run = builder or run_build_local

    def _fn(tree) -> dict:
        up = Path(tree) / f"{project}.uproject"
        if not up.is_file():
            # ⚠️ 검수 트리에 `.uproject` 가 없다 = 프로젝트 루트가 아니다. 빌드가 조용히
            #    엉뚱한 것을 세우게 두지 않는다.
            return {"ok": False, "passed": False,
                    "failure": f"검수 트리에 {up.name} 이 없다: {tree}",
                    "summary": "BLOCKED(uproject 없음)"}
        return result_to_dict(run(bb, tgt, str(up), config=config, timeout=timeout))

    _fn.build_bat = bb          # 사람이 무엇으로 빌드하는지 볼 수 있게
    _fn.target = tgt
    return _fn
