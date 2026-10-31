"""플랜 태스크의 **빌드 단계**(7단계 중 1·5) — `#861` T2(= `#857` T7).

마스터는 **로컬에서** 빌드하지 않는다. 빌드는 UE5 를 가진 워커에서 돌고, 그것을 마스터가
SSH 로 직접 구동한다(`layer3_verify.run_build_on_workshop`) — 워커에 상주 데몬은 없다
(사용자 확정 2026-10-31, `#860`·`#861`). [주의] 종전의 `buildjob` 큐 + 워커 상주 데몬 경로
(`#857` T4 `03af704`)는 **철회됐다** — 다시 살리지 않는다.

판정은 결정적이다:

    1 기준 리비전   빌드 **전에** 워커 트리의 HEAD 가 기대 커밋과 같은가 (조회만 — 체크아웃하지 않는다)
                    추적 파일이 더러우면 그 빌드는 커밋의 빌드가 아니므로 **빌드하지 않는다**
                    빌드 **뒤에** HEAD 를 다시 읽어 움직였으면 실패다
    5 빌드          `BuildResult.passed` — 시간 초과도 `failure` 로 와서 FAIL 이다

[중요] **둘 중 하나라도 아니면 실패다** — 다른 커밋을 빌드해 통과한 것은 그 태스크의 근거가
아니다. 조회 실패는 일치로 읽지 않는다.
[주의] 플랜 마킹은 하지 않는다 — 돌려주는 `evidence` 를 호출자가 `plan_transition` 의 근거로 쓴다.
"""
from __future__ import annotations

import re

from master import layer3_verify
from master.work import skeleton_gate

UNREAL = "unreal"

_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")


class BuildStepError(ValueError):
    """빌드 단계를 시작할 수 없다 — 사유 문장을 담는다."""


def _same_commit(a: str, b: str) -> bool:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    return bool(a and b) and (a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) >= 7


def _head(ssh, host: str, user: str, tree: str) -> tuple:
    """`(commit, 사유)`. 조회 실패면 commit 이 빈 문자열이다 — 일치로 읽지 않는다."""
    rc, out = ssh(host, user, f'git -C "{tree}" rev-parse HEAD')
    line = (out or "").strip().splitlines()[-1].strip() if (out or "").strip() else ""
    if rc != 0 or not _SHA.match(line):
        return "", f"HEAD 조회 실패 rc={rc} {(out or '').strip()[:80]}"
    return line.lower(), ""


def _dirty(ssh, host: str, user: str, tree: str) -> tuple:
    """`(더러운가, 사유)`. 조회 실패면 `(None, 사유)`."""
    rc, out = ssh(host, user, f'git -C "{tree}" status --porcelain --untracked-files=no')
    if rc != 0:
        return None, f"작업 트리 상태 조회 실패 rc={rc} {(out or '').strip()[:80]}"
    return bool((out or "").strip()), (out or "").strip()[:120]


def _default_facts(project: str) -> list:
    from master.client import bundle
    return [bundle.probe(*w) for w in bundle.workshops(project)]


def build_step(project: str, *, expected_commit: str, kind: str = "", tree: str = "",
               timeout: int = layer3_verify.DEFAULT_TIMEOUT, kind_of=None, facts=None,
               ssh=None, build_runner=None) -> dict:
    """UE5 워커를 골라 리비전을 확인하고 SSH 로 빌드한 뒤 판정한다. `evidence` 가 플랜 근거 한 줄이다."""
    if not (expected_commit or "").strip():
        raise BuildStepError("expected_commit 이 비었다 — 기준 리비전 없이 빌드 결과를 근거로 쓰지 않는다")
    if not kind:
        if kind_of is None:
            from master.projects.profile import kind_of
        kind = kind_of(project)
    if kind != UNREAL:
        raise BuildStepError(f"kind={kind or '(없음)'} — UE 빌드 단계는 unreal 프로젝트만이다 "
                             "(code 의 5단계는 정적·통합 검사다)")
    if ssh is None:
        from master.client import bundle
        ssh = bundle._ssh
    if facts is None:
        facts = _default_facts(project)

    from master.work.runner import pick_worker
    pick = pick_worker(list(facts), requires=("ue5",))
    if pick.chosen is None:
        why = " · ".join(f"{h}: {r}" for h, r in pick.rejected) or "워크숍 없음"
        return {"ok": False, "stage": "pick", "evidence": f"빌드할 UE5 워커가 없다 — {why}"}
    f = pick.chosen
    host, user = f.host, f.user
    tree = tree or f.path
    base = {"host": host, "tree": tree}
    exp8 = expected_commit.strip()[:8]

    # 1 기준 리비전 — 빌드 전
    commit, why = _head(ssh, host, user, tree)
    if not commit:
        return {**base, "ok": False, "stage": "revision", "passed": False, "revision_ok": False,
                "commit": "", "evidence": f"빌드 {host} · 리비전 조회 실패 — {why} (빌드 안 함)"}
    if not _same_commit(commit, expected_commit):
        return {**base, "ok": False, "stage": "revision", "passed": False, "revision_ok": False,
                "commit": commit,
                "evidence": f"빌드 {host} · 커밋 {commit[:8]} · [리비전 불일치 — 기대 {exp8}] (빌드 안 함)"}
    dirty, detail = _dirty(ssh, host, user, tree)
    if dirty is None:
        return {**base, "ok": False, "stage": "revision", "passed": False, "revision_ok": False,
                "commit": commit, "evidence": f"빌드 {host} · 작업 트리 조회 실패 — {detail} (빌드 안 함)"}
    if dirty:
        return {**base, "ok": False, "stage": "revision", "passed": False, "revision_ok": False,
                "commit": commit,
                "evidence": f"빌드 {host} · 커밋 {commit[:8]} · 추적 파일이 더럽다 — 커밋의 빌드가 "
                            f"아니다 (빌드 안 함) · {detail}"}

    # 5 빌드
    build_bat = skeleton_gate._build_bat_from(f)
    if not build_bat:
        return {**base, "ok": False, "stage": "build", "passed": False, "revision_ok": True,
                "commit": commit,
                "evidence": f"빌드 {host} · Build.bat 을 유도하지 못했다 (ue5={f.ue5 or '없음'}) — 빌드 안 함"}
    target = skeleton_gate.target_name(project)
    uproject = skeleton_gate._win_join(tree, f"{project}.uproject")
    kw = {"timeout": timeout}
    if build_runner is not None:
        kw["runner"] = build_runner
    res = layer3_verify.run_build_on_workshop(host, user, build_bat, target, uproject, **kw)
    build = res.to_dict()
    build.pop("raw_tail", None)
    passed = res.passed is True

    # 빌드 뒤 HEAD 재확인
    after, why = _head(ssh, host, user, tree)
    moved = not _same_commit(after, commit)
    rev_ok = not moved
    parts = [f"빌드 {host}", f"커밋 {commit[:8]}", "PASS" if passed else "FAIL",
             f"{res.seconds:.0f}초" if isinstance(res.seconds, (int, float)) else "",
             res.summary()[:60]]
    if not passed and res.failure:
        parts.append(str(res.failure)[:120])
    elif not passed:
        # UBT 가 판정을 낸 실패는 `failure` 가 없다 — 첫 에러 줄을 근거로 싣는다
        err = next((ln.strip() for ln in (res.raw_tail or "").splitlines()
                    if "error" in ln.lower()), "")
        if err:
            parts.append(err[:120])
    if moved:
        parts.append(f"[리비전 변동] 빌드 뒤 HEAD {after[:8] or '조회 실패'}"
                     + (f" — {why}" if why else "") + f" (기대 {exp8})")
    return {**base, "ok": passed and rev_ok, "stage": "done", "passed": passed,
            "revision_ok": rev_ok, "commit": commit, "build": build,
            "evidence": " · ".join(p for p in parts if p)}
