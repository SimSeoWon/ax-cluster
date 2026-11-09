"""master.infra.bc250_shutdown — BC-250 (.43) 전용 안전 전원 종료 모듈.

[중요] .43 단독 대상 고정 — .2, .33, .57 비접촉 계약:
- 본 모듈은 오직 .43 (192.168.0.43 / bc250-1)만을 대상으로 동작한다.
- .2(Windows/UE5), .33(사용자 작업/게임 요청자), .57(인프라 마스터 sim-desktop) 등
  허용 목록 외의 대상이 입력되면 즉시 TargetRefusalError(ValueError)를 발생시키고 실행을 거절한다.
- force=True 여도 대상 노드 검증은 절대 해제되지 않는다.

사전 안전 검사 (Pre-flight checks):
1. check_queue: 큐/태스크/워크 진행 중 작업 확인 (claimed, submitted 등 활성 태스크 차단)
2. check_broker_inflight: 브로커 엔드포인트의 inflight 요청 여부 확인 (inflight > 0 차단)
3. check_remote_processes: SSH pgrep으로 원격 작업 프로세스(codex, claude, python, node) 확인
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

ALLOWED_TARGETS: Tuple[str, ...] = ("192.168.0.43", "bc250-1", "bc250", "43", ".43")
FORBIDDEN_TARGETS: Tuple[str, ...] = (
    "192.168.0.2", "192.168.0.33", "192.168.0.57",
    "2", ".2", "33", ".33", "57", ".57",
    "sim-desktop", "desktop", "localhost", "127.0.0.1",
)
DEFAULT_TARGET: str = "192.168.0.43"
DEFAULT_USER: str = "sim"

CLOSED_TASK_STATUSES = frozenset(("verified", "cancelled", "failed"))
CLOSED_WORK_STATUSES = frozenset(("verified", "cancelled", "failed", "merged", "rejected"))


class TargetRefusalError(ValueError):
    """허용되지 않은 대상 노드 접근 시 발생하는 예외 (.2, .33, .57 등 비접촉 계약 위반)."""
    pass


class PreflightCheckError(RuntimeError):
    """사전 안전 점검 실패 시 발생하는 예외 (큐 작업 중, 브로커 inflight, 활성 프로세스 등)."""
    pass


class ShutdownError(RuntimeError):
    """전원 종료 명령 실행 실패 또는 단절 확인 실패 시 발생하는 예외."""
    pass


def validate_target(target: Optional[str]) -> str:
    """대상 노드를 정규화하고 엄격히 검증한다. 오직 .43만 통과한다."""
    if target is None:
        return DEFAULT_TARGET
    cleaned = str(target).strip()
    if not cleaned:
        return DEFAULT_TARGET

    # 금지 목록 직접 확인
    if cleaned in FORBIDDEN_TARGETS or any(f == cleaned for f in FORBIDDEN_TARGETS):
        raise TargetRefusalError(
            f"대상 '{cleaned}' 거절: .2, .33, .57 비접촉 계약 위반. 오직 .43 (192.168.0.43)만 대상이다."
        )

    if cleaned in ALLOWED_TARGETS:
        return DEFAULT_TARGET

    raise TargetRefusalError(
        f"대상 '{cleaned}' 거절: 알 수 없는 노드. 오직 .43 (192.168.0.43 / bc250-1)만 허용된다."
    )


def check_queue(status_data: Optional[Dict[str, Any]] = None,
                *,
                status_fetcher: Optional[Callable[[], Dict[str, Any]]] = None) -> List[str]:
    """활성 큐 작업(task/work) 검사. .43 관련 진행 중 작업이 있으면 PreflightCheckError."""
    if status_data is None:
        if status_fetcher is not None:
            status_data = status_fetcher()
        else:
            try:
                from master.status import fetch_live
                status_data = fetch_live()
            except Exception as e:
                raise PreflightCheckError(f"큐 상태 조회 실패: {e}") from e

    if not isinstance(status_data, dict):
        raise PreflightCheckError(f"큐 상태 데이터 형식 오류: {type(status_data)}")

    err = status_data.get("error")
    if err:
        raise PreflightCheckError(f"큐 상태 오류 보고: {err}")

    active_tasks: List[Dict[str, Any]] = []
    tasks = status_data.get("tasks")
    if isinstance(tasks, list):
        for t in tasks:
            if not isinstance(t, dict):
                continue
            st = str(t.get("status") or "").lower()
            if st in CLOSED_TASK_STATUSES:
                continue
            worker = str(t.get("worker_id") or t.get("assignee") or t.get("worker") or "")
            if "192.168.0.43" in worker or "43" in worker or "bc250" in worker.lower():
                active_tasks.append(t)

    active_works: List[Dict[str, Any]] = []
    works = status_data.get("works")
    if isinstance(works, list):
        for w in works:
            if not isinstance(w, dict):
                continue
            mst = str(w.get("merge_status") or w.get("status") or "").lower()
            if mst in CLOSED_WORK_STATUSES:
                continue
            # work가 열려 있을 때 혹시 43번이 관여되었는지
            active_works.append(w)

    if active_tasks:
        details = ", ".join(
            f"task={t.get('task_id')}(status={t.get('status')}, worker={t.get('worker_id') or t.get('assignee')})"
            for t in active_tasks
        )
        raise PreflightCheckError(f"BC-250에 진행 중인 활성 태스크 {len(active_tasks)}건 존재: {details}")

    return [f"큐 검사 완료: .43 대상 활성 태스크 0건 (전체 열린 work={len(active_works)}건)"]


def check_broker_inflight(status_data: Optional[Dict[str, Any]] = None,
                          *,
                          status_fetcher: Optional[Callable[[], Dict[str, Any]]] = None) -> List[str]:
    """브로커 inflight 작업 검사. .43 엔드포인트의 inflight > 0 이면 PreflightCheckError."""
    if status_data is None:
        if status_fetcher is not None:
            status_data = status_fetcher()
        else:
            try:
                from master.status import fetch_live
                status_data = fetch_live()
            except Exception as e:
                raise PreflightCheckError(f"브로커 상태 조회 실패: {e}") from e

    if not isinstance(status_data, dict):
        raise PreflightCheckError(f"브로커 상태 데이터 형식 오류: {type(status_data)}")

    endpoints = status_data.get("endpoints")
    if not isinstance(endpoints, list):
        # 엔드포인트 정보가 없으면 경고만 남김
        return ["브로커 검사 통과: 엔드포인트 정보 없음 (비활성)"]

    bc250_found = False
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        host = str(ep.get("host") or "")
        name = str(ep.get("name") or "").lower()
        if "192.168.0.43" in host or "bc250" in name:
            bc250_found = True
            inflight = int(ep.get("inflight") or 0)
            if inflight > 0:
                raise PreflightCheckError(
                    f"BC-250 브로커 inflight 작업 진행 중 ({inflight}건). 종료를 중단합니다."
                )

    msg = "BC-250 엔드포인트 inflight 0건" if bc250_found else "BC-250 엔드포인트 미등록/오프라인"
    return [f"브로커 검사 완료: {msg}"]


def check_remote_processes(target: str = DEFAULT_TARGET,
                           *,
                           user: str = DEFAULT_USER,
                           runner: Optional[Callable[..., Any]] = None) -> List[str]:
    """SSH로 .43에 접속하여 원격 작업 프로세스(codex, claude, python, node 등) 검출."""
    target_ip = validate_target(target)
    run_cmd = runner or (lambda cmd, **kwargs: subprocess.run(
        cmd, capture_output=True, text=True, timeout=kwargs.get("timeout", 10), check=False
    ))

    # [c]odex 패턴을 사용하여 grep 자체 매칭 방지, sim 사용자의 프로세스만 조회
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        f"{user}@{target_ip}",
        "pgrep -u sim -l -f '[c]odex|[c]laude|[p]ython|[n]ode' || true"
    ]

    try:
        proc = run_cmd(ssh_cmd, timeout=12)
    except Exception as e:
        # SSH 접속 자체가 안 되면 이미 꺼져 있거나 단절된 상태
        return [f"원격 프로세스 검사 스킵: SSH 접속 실패 ({type(e).__name__}: {e}) — 이미 전원 차단 상태 가능성"]

    if proc.returncode != 0 and proc.returncode != 1:
        # SSH 접속 실패 (255 등)
        return [f"원격 프로세스 검사: SSH 접속 응답 코드 {proc.returncode} — 이미 오프라인 상태 가능성"]

    out = (proc.stdout or "").strip()
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]

    # bash, sh, pgrep 등 셸 래퍼를 제외한 실제 작업 프로세스 선별
    active_procs = []
    for line in lines:
        parts = line.split(maxsplit=1)
        pname = parts[1] if len(parts) > 1 else parts[0]
        # 단순 셸 세션은 제외
        if pname in ("bash", "sh", "sshd"):
            continue
        active_procs.append(line)

    if active_procs:
        raise PreflightCheckError(
            f"BC-250에 작업 프로세스 {len(active_procs)}건 실행 중: {', '.join(active_procs)}"
        )

    return ["원격 프로세스 검사 완료: 잔여 작업 프로세스 0건"]


def run_preflight_checks(target: Optional[str] = DEFAULT_TARGET,
                         *,
                         user: str = DEFAULT_USER,
                         force: bool = False,
                         status_fetcher: Optional[Callable[[], Dict[str, Any]]] = None,
                         runner: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """사전 점검 3종을 순차적으로 수행한다."""
    # 대상 검증은 force 불문 엄격
    target_ip = validate_target(target)

    logs: List[str] = []
    warnings: List[str] = []

    checks = [
        ("큐 검사", lambda: check_queue(status_fetcher=status_fetcher)),
        ("브로커 검사", lambda: check_broker_inflight(status_fetcher=status_fetcher)),
        ("원격 프로세스 검사", lambda: check_remote_processes(target_ip, user=user, runner=runner)),
    ]

    for name, fn in checks:
        try:
            res = fn()
            logs.extend(res)
        except PreflightCheckError as e:
            if force:
                warnings.append(f"[{name} 경고 (force 무시)] {e}")
            else:
                raise

    return {
        "ok": True,
        "target": target_ip,
        "logs": logs,
        "warnings": warnings,
    }


def execute_shutdown(target: Optional[str] = DEFAULT_TARGET,
                     *,
                     user: str = DEFAULT_USER,
                     dry_run: bool = False,
                     runner: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """sudo -n systemctl poweroff 명령을 실행한다."""
    target_ip = validate_target(target)
    poweroff_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        f"{user}@{target_ip}",
        "sudo -n systemctl poweroff"
    ]

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "target": target_ip,
            "command": " ".join(poweroff_cmd),
            "message": f"[DRY-RUN] 실제 전원 종료 명령을 실행하지 않았습니다: {' '.join(poweroff_cmd)}",
        }

    run_cmd = runner or (lambda cmd, **kwargs: subprocess.run(
        cmd, capture_output=True, text=True, timeout=kwargs.get("timeout", 15), check=False
    ))

    try:
        proc = run_cmd(poweroff_cmd, timeout=15)
        if proc.returncode != 0:
            raise ShutdownError(
                f"전원 종료 명령 실행 실패 (rc={proc.returncode}): {proc.stderr or proc.stdout}"
            )
    except Exception as e:
        if isinstance(e, ShutdownError):
            raise
        raise ShutdownError(f"전원 종료 명령 호출 중 예외: {e}") from e

    return {
        "ok": True,
        "dry_run": False,
        "target": target_ip,
        "command": " ".join(poweroff_cmd),
        "message": f"{target_ip} 전원 종료 명령 전송 완료 (rc=0)",
    }


def verify_shutdown(target: Optional[str] = DEFAULT_TARGET,
                    *,
                    user: str = DEFAULT_USER,
                    timeout: int = 30,
                    interval: float = 2.0,
                    runner: Optional[Callable[..., Any]] = None) -> bool:
    """SSH 연결 단절(rc != 0)을 감지하여 전원 차단을 확인한다."""
    target_ip = validate_target(target)
    run_cmd = runner or (lambda cmd, **kwargs: subprocess.run(
        cmd, capture_output=True, text=True, timeout=kwargs.get("timeout", 3), check=False
    ))

    probe_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2",
        f"{user}@{target_ip}", "true"
    ]

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            proc = run_cmd(probe_cmd, timeout=3)
            if proc.returncode != 0:
                # 연결 실패 = 시스템 전원 종료 확인
                return True
        except Exception:
            # 타임아웃 또는 네트워크 에러 = 단절 확인
            return True
        time.sleep(interval)

    raise ShutdownError(
        f"전원 종료 확인 실패: {timeout}초 후에도 {target_ip} SSH 연결이 유지되고 있습니다."
    )


def shutdown(target: Optional[str] = DEFAULT_TARGET,
             *,
             user: str = DEFAULT_USER,
             dry_run: bool = False,
             force: bool = False,
             check_only: bool = False,
             verify_timeout: int = 30,
             status_fetcher: Optional[Callable[[], Dict[str, Any]]] = None,
             runner: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """BC-250 안전 종료 종합 엔트리포인트."""
    target_ip = validate_target(target)

    # 1. 사전 검사
    preflight = run_preflight_checks(
        target_ip,
        user=user,
        force=force,
        status_fetcher=status_fetcher,
        runner=runner,
    )

    if check_only:
        return {
            "ok": True,
            "target": target_ip,
            "check_only": True,
            "preflight": preflight,
            "message": f"{target_ip} 사전 안전 검사 통과 (종료 미실행)",
        }

    # 2. 종료 명령 실행
    exec_res = execute_shutdown(
        target_ip,
        user=user,
        dry_run=dry_run,
        runner=runner,
    )

    # 3. 사후 단절 확인 (dry_run이 아닐 때만)
    verified = False
    if not dry_run:
        verified = verify_shutdown(
            target_ip,
            user=user,
            timeout=verify_timeout,
            runner=runner,
        )

    return {
        "ok": True,
        "target": target_ip,
        "dry_run": dry_run,
        "preflight": preflight,
        "execution": exec_res,
        "verified_shutdown": verified,
        "message": f"{target_ip} 전원 종료 및 단절 확인 완료" if not dry_run else exec_res["message"],
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="bc250_shutdown",
        description="BC-250 (.43) 전용 안전 전원 종료 CLI",
    )
    ap.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"대상 호스트/IP (기본: {DEFAULT_TARGET}, .43 전용)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 종료 명령을 실행하지 않고 사전 점검 및 계획만 출력",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="사전 점검 경고(활성 프로세스 등)를 무시하고 종료 진행 (단 대상 노드 검증은 해제 불가)",
    )
    ap.add_argument(
        "--check-only",
        action="store_true",
        help="사전 점검만 수행하고 종료하지 않음",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="종료 후 단절 확인 대기 시간(초, 기본 30)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="결과를 JSON 형식으로 출력",
    )
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        res = shutdown(
            target=args.target,
            dry_run=args.dry_run,
            force=args.force,
            check_only=args.check_only,
            verify_timeout=args.timeout,
        )
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"[{'DRY-RUN' if args.dry_run else 'SUCCESS'}] {res['message']}")
            for log in res["preflight"]["logs"]:
                print(f"  - {log}")
            for warn in res["preflight"]["warnings"]:
                print(f"  ! {warn}")
        return 0
    except TargetRefusalError as e:
        sys.stderr.write(f"[TARGET REFUSAL] {e}\n")
        return 3
    except PreflightCheckError as e:
        sys.stderr.write(f"[PREFLIGHT FAILED] {e}\n")
        return 1
    except ShutdownError as e:
        sys.stderr.write(f"[SHUTDOWN FAILED] {e}\n")
        return 2
    except Exception as e:
        sys.stderr.write(f"[ERROR] {type(e).__name__}: {e}\n")
        return 99


if __name__ == "__main__":
    sys.exit(main())
