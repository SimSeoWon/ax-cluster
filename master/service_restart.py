"""승인 뒤 호출하는 AX 서비스 재시작·복구 CLI (`#647` · 복구는 `#360`)."""
from __future__ import annotations

import subprocess
import sys

ALLOWED = (
    "ax-task-queue", "ax-projects", "ax-broker", "ax-indexer",
    "ax-batch", "ax-status", "ax-dispatch", "ax-review-queue",
)
# 🔴 `#360` — **복구 대상은 재시작 대상보다 넓다.** 2026-09-05 사고에서 죽은 것은
#    `ax-dispatch.service` 와 `ax-dispatch.path` **둘 다**였고, 트리거가 죽으면 골조 push·
#    등재 신호가 있어도 파견이 안 걸린다(10분 catchup 만 남는다).
#    [중요] `reset-failed` 는 **상태만 지운다 — 무엇도 기동하지 않는다.** 그래서 `restart`
#    보다 좁은 권한이고, `.path`·`.timer` 까지 여는 근거가 그것이다.
RECOVERABLE = ALLOWED + ("ax-dispatch-catchup",)
SUFFIXES = ("service", "path", "timer")
RESIDENT = {"ax-task-queue", "ax-projects", "ax-broker"}
HELPER = "/usr/local/sbin/ax-service-restart-root"


def state(unit: str, *, run=subprocess.run) -> dict:
    r = run(["systemctl", "show", unit, "--property=ExecMainStartTimestampMonotonic,"
             "ExecMainStartTimestamp,ActiveState,SubState,Result,ExecMainStatus"], capture_output=True,
            text=True, timeout=15)
    if r.returncode:
        raise RuntimeError(f"systemctl show 실패 (rc={r.returncode})")
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


def units_of(base: str, *, run=subprocess.run) -> list[str]:
    """그 기반 이름으로 **실제 존재하는** 유닛들. 없는 것에 `reset-failed` 를 쏘지 않는다."""
    r = run(["systemctl", "list-unit-files", f"{base}.*", "--no-legend", "--no-pager"],
            capture_output=True, text=True, timeout=15)
    if r.returncode:
        raise RuntimeError(f"systemctl list-unit-files 실패 (rc={r.returncode})")
    out = []
    for line in (r.stdout or "").splitlines():
        name = line.split()[0] if line.split() else ""
        # [주의] `ax-dispatch.*` 는 `ax-dispatch-catchup.service` 도 물어 온다 — 기반 이름이
        #    정확히 같은 것만 남긴다. 안 그러면 남의 유닛을 내 복구에 끌어들인다.
        if name.count(".") == 1 and name.rsplit(".", 1)[0] == base \
                and name.rsplit(".", 1)[1] in SUFFIXES:
            out.append(name)
    return sorted(out)


def reset_failed(unit: str, *, run=subprocess.run) -> dict:
    """유닛 하나의 실패 상태를 지운다 (`#360`). 되돌려 주는 것은 **전후 상태**다.

    [중요] **무엇도 기동하지 않는다.** 이 호출이 하는 일은 systemd 가 기억하는
    「실패했다 · 너무 자주 시작했다」를 지우는 것뿐이다. 다시 돌리는 것은 트리거의 몫이다.
    """
    base = unit.rsplit(".", 1)[0] if unit.rsplit(".", 1)[-1] in SUFFIXES else unit
    if base not in RECOVERABLE:
        raise ValueError(f"복구가 허용되지 않은 유닛: {unit}")
    before = state(unit, run=run)
    r = run(["sudo", "-n", HELPER, "reset-failed", unit],
            capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"reset-failed helper 실패 (rc={r.returncode}): "
                           f"{(r.stderr or '').strip()}")
    after = state(unit, run=run)
    # 🔴 [중요] **rc 로 판정하지 않는다** — `#647` 이 재시작에서 배운 것과 같다(기동 시각을
    #    본다). 여기서는 **여전히 failed 면 실패**다.
    if after.get("ActiveState") == "failed":
        raise RuntimeError(f"{unit}: reset-failed 뒤에도 failed 다 "
                           f"(result={after.get('Result')})")
    return {"unit": unit,
            "before": f"{before.get('ActiveState')}/{before.get('Result')}",
            "after": f"{after.get('ActiveState')}/{after.get('Result')}",
            "was_failed": before.get("ActiveState") == "failed"}


def recover(base: str, *, run=subprocess.run) -> list[dict]:
    """기반 이름 하나의 **모든 유닛**을 복구한다 (`#360` 의 실제 요구).

    사고 당시 명령이 `systemctl reset-failed ax-dispatch.service ax-dispatch.path` 였다 —
    **둘 다** 죽었기 때문이다. 사람이 유닛 이름을 외우게 하지 않는다.

    [주의] failed 가 아닌 유닛도 그냥 지나가지 않고 **지나갔다고 기록한다** — 「무엇을 봤고
    무엇을 손댔나」가 남아야 다음 사고에서 이 출력을 근거로 쓸 수 있다.
    """
    if base not in RECOVERABLE:
        raise ValueError(f"복구가 허용되지 않은 유닛: {base}")
    units = units_of(base, run=run)
    if not units:
        raise RuntimeError(f"`{base}` 로 존재하는 유닛이 없다")
    return [reset_failed(u, run=run) for u in units]


def restart(unit: str, *, run=subprocess.run) -> tuple[dict, dict]:
    if unit not in ALLOWED:
        raise ValueError(f"허용되지 않은 유닛: {unit}")
    before = state(unit, run=run)
    r = run(["sudo", "-n", HELPER, unit], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError(f"재시작 helper 실패 (rc={r.returncode}): {(r.stderr or '').strip()}")
    after = state(unit, run=run)
    old = before.get("ExecMainStartTimestampMonotonic", "")
    new = after.get("ExecMainStartTimestampMonotonic", "")
    if not old or not new or old == new:
        raise RuntimeError(f"기동 시각이 바뀌지 않았다: {old!r} → {new!r}")
    if unit in RESIDENT:
        good = after.get("ActiveState") == "active" and after.get("SubState") == "running"
    else:
        good = after.get("Result") == "success" and after.get("ExecMainStatus") == "0"
    if not good:
        raise RuntimeError("재시작 뒤 비정상 상태: "
                           f"{after.get('ActiveState')}/{after.get('SubState')} · "
                           f"result={after.get('Result')} status={after.get('ExecMainStatus')}")
    return before, after


USAGE = ("사용법:\n"
         "  {p} <유닛>                재시작 (`#647`)\n"
         "  {p} --reset-failed <유닛>  실패 상태만 지운다 (`#360`)\n"
         "  {p} --recover <기반이름>   그 이름의 .service/.path/.timer 를 전부 (`#360`)\n"
         "\n재시작: {a}\n복구:   {r}  (+ .service/.path/.timer)")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    usage = USAGE.format(p=sys.argv[0], a="|".join(ALLOWED), r="|".join(RECOVERABLE))
    if len(args) == 2 and args[0] in ("--reset-failed", "--recover"):
        try:
            rows = ([reset_failed(args[1])] if args[0] == "--reset-failed"
                    else recover(args[1]))
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"[실패] {exc}", file=sys.stderr)
            return 1
        touched = sum(1 for r in rows if r["was_failed"])
        for r in rows:
            mark = "[완료]" if r["was_failed"] else "[주의]"
            tail = "" if r["was_failed"] else " — failed 가 아니었다 (손대지 않은 것과 같다)"
            print(f"{mark} {r['unit']}: {r['before']} → {r['after']}{tail}")
        # [중요] **0건도 말한다** — 「복구했다」와 「복구할 게 없었다」는 다르다.
        print(f"[완료] {len(rows)}개 중 {touched}개가 failed 였다")
        return 0
    if len(args) != 1 or args[0].startswith("-"):
        print(usage, file=sys.stderr)
        return 2
    try:
        before, after = restart(args[0])
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 1
    print(f"[완료] {args[0]}: {before.get('ExecMainStartTimestamp')} → "
          f"{after.get('ExecMainStartTimestamp')} · "
          f"{after.get('ActiveState')}/{after.get('SubState')} · result={after.get('Result')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
