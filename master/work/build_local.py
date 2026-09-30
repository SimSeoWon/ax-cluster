"""요청자(`.33`)의 검수 빌드 — `review_work(build_fn=…)` 에 꽂는 어댑터 (중 2.1 `#135`).

[중요] **여기에 새 판정이 없다.** 명령은 `layer3_verify.build_build_command`, 판정은
`parse_build_log`, 경로 유도는 `skeleton_gate.build_bat_from_editor` 를 **그대로 쓴다.**
이 파일이 하는 일은 셋뿐이다: 검수 트리에서 `.uproject` 를 찾고 · 그 셋을 잇고 ·
`review_work` 가 기대하는 dict 로 바꾼다.

## 왜 로컬인가 (사용자 결정 2026-08-16)

    마스터   UE5 가 없다 → `.2` 에 SSH 로 위임 (`run_build_on_workshop`)
    요청자   [중요] UE5 가 **있고** 검수 worktree 가 자기 디스크에 있다 → 로컬로 돈다

*".33 로컬 (원전 그대로)"* — 원전도 리더 PC 에서 직접 빌드한다. `.2` 위임은 **리눅스가
강제한 변경**이고 여기엔 해당이 없다.

## [중요] 판정을 못 받으면 통과가 아니다

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
    """빌드를 **시작조차** 할 수 없다. [중요] 조용히 skip 하지 않는다 — 그건 통과로 읽힌다."""


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
    ([중요] 경로를 손으로 적지 말 것 — 마스터가 **프로브해서** 넣은 값이다).

    [중요] **엔진을 못 찾으면 만들 때 죽는다.** 검수를 절반 돌린 뒤 *"빌드는 못 했지만 통과"* 로
    끝나는 것이 최악이라, 그 사실을 **착수 전에** 드러낸다.
    """
    bb = (build_bat or "").strip() or build_bat_from_editor(ue5_cmd)
    if not bb:
        raise BuildSetupError(
            "UE5 Build.bat 을 찾지 못했다 — `.ax/config.json` 의 `backends.ue5_cmd` 를 확인할 것 "
            "(비어 있으면 마스터에 배달을 다시 요청한다). [중요] 확인 불가는 통과가 아니다")
    tgt = (target or "").strip() or target_name(project)
    run = builder or run_build_local

    def _fn(tree) -> dict:
        up = Path(tree) / f"{project}.uproject"
        if not up.is_file():
            # [주의] 검수 트리에 `.uproject` 가 없다 = 프로젝트 루트가 아니다. 빌드가 조용히
            #    엉뚱한 것을 세우게 두지 않는다.
            return {"ok": False, "passed": False,
                    "failure": f"검수 트리에 {up.name} 이 없다: {tree}",
                    "summary": "BLOCKED(uproject 없음)"}
        return result_to_dict(run(bb, tgt, str(up), config=config, timeout=timeout))

    _fn.build_bat = bb          # 사람이 무엇으로 빌드하는지 볼 수 있게
    _fn.target = tgt
    return _fn


# ── 🔴 `kind: code` 의 통합 검사 — `.py` 판 (`#695` P5 · 사용자 결정 D3) ──────────────────
#
# UE 의 ⑦ 통합 빌드 자리에 Python 은 **테스트 스위트**가 선다. 원전도 통합 단계가 cross-file
# 정합성을 잡는 자리였다 — 조각 검증은 정적 검사뿐이다(층1 · 파견 전 골조 게이트).
# [중요] 계약은 `local_build_fn` 과 **같다** — `build_fn(tree) -> dict`, 판정 키는 `passed`/`ok`,
#    읽는 쪽은 `review.build_verdict` 하나다. 두 판이 같은 자리에 꽂힌다.
#
# 실측 2026-09-30 `.33` Gitea 클론(`6b7e725`): `py -3.12 -m unittest discover -s webui/tests
#    -p "*_test.py"` → **78개 · OK · 13.4초** · 실행 뒤 작업 트리 깨끗. `-t .` 을 주면
#    `webui/tests` 가 패키지가 아니라서 **발견 단계에서 죽는다**(그것도 실측) — 그래서 `-t` 를 안 준다.

import re as _re

_RAN = _re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", _re.M)
_FAILED = _re.compile(r"^FAILED \((.*)\)\s*$", _re.M)


def parse_unittest(text: str, rc: int) -> dict:
    """`unittest` 출력 → 판정 dict. **정확한 신호만 믿는다** — `layer3_verify` 와 같은 계약.

    통과 = `Ran N` (N ≥ 1) **그리고** 마지막 상태줄이 `OK` **그리고** rc == 0.
    [중요] **0개 실행은 통과가 아니다** — 발견이 조용히 비면 「테스트를 안 돌렸다」와 같다
    (`#694` 따라가기 스크립트와 같은 원칙). `Ran` 줄이 없으면 발견/import 단계에서 죽은 것이다.
    """
    text = text or ""
    m = _RAN.search(text)
    tail = "\n".join(text.strip().splitlines()[-15:])
    if not m:
        return {"ok": False, "passed": False, "failure": "`Ran N tests` 줄이 없다 — 발견/import 에서 죽었다",
                "result": "", "detail": "NoRun", "summary": "BLOCKED(테스트를 못 돌렸다)",
                "raw_tail": tail}
    n = int(m.group(1))
    after = text[m.end():]
    ok_line = _re.search(r"^OK\b", after, _re.M) is not None
    failed = _FAILED.search(after)
    if n == 0:
        return {"ok": False, "passed": False, "failure": "0개 실행 — 통과가 아니다",
                "result": "", "detail": "NoTests", "summary": "BLOCKED(테스트 0개)", "raw_tail": tail}
    passed = bool(ok_line and not failed and rc == 0)
    detail = failed.group(1) if failed else ("" if passed else f"rc={rc}")
    return {"ok": passed, "passed": passed, "failure": None,
            "result": "Succeeded" if passed else "Failed", "detail": detail,
            "summary": (f"TESTS OK ({n})" if passed else f"TESTS FAILED ({n} · {detail})"),
            "raw_tail": tail}


def local_test_fn(*, start_dir: str, pattern: str, python: str = "", timeout: int = 1800,
                  runner=None):
    """`build_fn(tree) -> dict` 의 **Python 판**. 트리에서 `unittest discover` 를 한 번 돈다.

    `start_dir`·`pattern` 은 **프로젝트가 정한다** — 코드에 특정 프로젝트 경로를 박지 않는다.
    `python` 은 배달된 `.ax/config.json` 의 `backends.python`(마스터가 프로브한 절대 경로)을
    그대로 넣는다. 비우면 지금 도는 인터프리터다.
    [중요] **트리가 없거나 시작 디렉토리가 없으면 만들 때가 아니라 부를 때 BLOCKED 다** —
    검수 트리는 `advance_work` 가 세운 뒤에야 생긴다.
    """
    import subprocess
    import sys
    import time

    if not (start_dir or "").strip() or not (pattern or "").strip():
        raise BuildSetupError("start_dir·pattern 이 비었다 — 무엇을 돌릴지 모른다 "
                              "(프로젝트 프로필·배달 설정에서 온다). [중요] 확인 불가는 통과가 아니다")
    exe = (python or "").strip() or sys.executable
    run = runner or (lambda argv, cwd, t: subprocess.run(argv, cwd=cwd, capture_output=True,
                                                         timeout=t))

    def _fn(tree) -> dict:
        root = Path(tree)
        if not (root / start_dir).is_dir():
            return {"ok": False, "passed": False, "failure": f"검수 트리에 {start_dir} 이 없다: {tree}",
                    "summary": "BLOCKED(테스트 디렉토리 없음)"}
        # [중요] `-B` — 바이트코드를 쓰지 않는다. 실측(단위 테스트): 같은 1초 안에 같은 크기로
        #    고친 파일을 **낡은 `.pyc` 가 가렸다** — 실패해야 할 테스트가 통과했다. 검수 트리도
        #    머지로 파일이 바뀌므로 같은 부류다. 트리도 덜 더럽힌다.
        argv = [exe, "-B", "-m", "unittest", "discover", "-s", start_dir, "-p", pattern]
        t0 = time.monotonic()
        try:
            r = run(argv, str(root), timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "passed": False, "failure": f"타임아웃 {timeout}초",
                    "summary": "BLOCKED(타임아웃)"}
        except OSError as e:
            return {"ok": False, "passed": False, "failure": f"실행 실패 — {e}",
                    "summary": "BLOCKED(실행 실패)"}
        out = r.stdout if isinstance(r.stdout, str) else (r.stdout or b"").decode("utf-8", "replace")
        err = r.stderr if isinstance(r.stderr, str) else (r.stderr or b"").decode("utf-8", "replace")
        d = parse_unittest(err + "\n" + out, r.returncode)
        d["seconds"] = round(time.monotonic() - t0, 1)
        return d

    _fn.command = f"{exe} -B -m unittest discover -s {start_dir} -p {pattern}"
    return _fn
