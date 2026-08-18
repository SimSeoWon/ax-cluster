"""워커 로그 회수 — 작업장에 쌓인 claimer 로그를 마스터로 걷어와 화면이 읽게 한다 (#220 ③-B).

## 왜 회수가 필요한가

`claimer` 는 작업마다 `.ax/logs/claimer_debug/<task_id>/` 에 진행 기록을 쌓는다(#220 ①) —
심박·LLM stdout/stderr·빌드 꼬리. 그런데 그 파일은 **작업장 기계 로컬에만** 있어서, 마스터의
`/cluster` 는 「실패했다」까지만 알고 그 근거의 원문을 보여줄 수 없었다. 사용자 지적이 그 자리다:
*"로그 없는데"* — 축적만 하고 열람을 안 만들었다(리포트 24 §6).

## [중요] 브라우저 새로고침이 scp 를 유발하면 안 된다

`/cluster` 는 15초마다 자동 리로드한다. 서빙 순간에 원격을 읽으면 **BC-250 을 자주 두드리지
않는다**(#105, 120초 가드)는 원칙이 무너진다. 그래서 회수는 **이미 SSH 를 타는 순간**에만 한다:

    ax-status.timer (5분)  → `master.status html` → collect() 안에서 이 모듈을 부른다
    수동                    → `python -m master.work.logs collect`

화면은 **회수된 사본만** 읽는다(로컬 파일). 나이는 `meta.json` 의 `at` 이 말하고, 낡았으면
낡았다고 적는다 — 조용히 최신인 척하지 않는다.

## 운송 규약은 기존과 같다

읽기는 `bundle._remote_read`(scp) 를 **그대로 쓴다** — 셸 경유 읽기가 조용히 빈 문자열을
돌려준 실측이 있어서(그 함수의 머리말) 이 자리에 새 경로를 만들지 않는다. 파일 목록을 원격에서
**나열하지 않는다**: 이름이 규약으로 고정돼 있으므로(`NAMES`) 그대로 시도하고, 없으면 scp 가
*No such file* 로 답한다 = 없는 것이다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from ..client import bundle

# claimer 가 쓰는 이름들 (claimer._debug_dir 의 규약과 같아야 한다)
NAMES = ("heartbeat.log", "llm_stdout.log", "llm_stderr.log", "build.log")
DEBUG_REL = ".ax/logs/claimer_debug"
STORE_DIR = "worker_logs"           # 트윈 루트 아래 — 파생물이다
META_NAME = "meta.json"
TAIL_BYTES = 16 * 1024              # 파일당 보관 꼬리 (화면은 이보다 더 줄여 보여 준다)
# 어떤 상태의 태스크를 걷나 — 진행 중(왜 안 끝나나)과 실패(왜 실패했나)가 로그를 볼 이유다.
WANT_STATUS = ("claimed", "submitted", "failed")
MAX_TASKS = 20                      # 한 번에 걷는 태스크 상한 (오래된 것부터 버린다)


HOSTS_DIR = "_hosts"                # 머신별 데몬 로그 (태스크가 없어도 볼 것이 있다)


def store_dir(paths, task_id: str) -> Path:
    return Path(paths.root) / STORE_DIR / str(task_id)


def host_store(paths, host: str) -> Path:
    return Path(paths.root) / STORE_DIR / HOSTS_DIR / f"{host}.log"


def _remote_daily(facts, day: str) -> str:
    """작업장의 일별 claimer 로그 경로 (claimer._log_path 규약과 같아야 한다)."""
    base = str(getattr(facts, "path", "") or "").rstrip("/\\")
    sep = "\\" if getattr(facts, "windows", False) else "/"
    rel = f".ax/logs/claimer_{day}.log"
    if sep == "\\":
        rel = rel.replace("/", "\\")
    return f"{base}{sep}{rel}"


HOST_LOG_LOOKBACK = 3               # 오늘 없으면 며칠까지 되짚나


def collect_host_log(paths, facts, *, reader=None, day: str = "",
                     lookback: int = HOST_LOG_LOOKBACK) -> int:
    """머신의 데몬 로그 꼬리를 걷는다 — 오늘자부터 시작해 없으면 며칠 되짚는다.
    반환은 저장한 바이트(없으면 0).

    태스크 로그와 별도인 이유: 태스크가 하나도 없어도 *"데몬이 살아 있나, 뭘 했나"* 는 물을
    수 있고, 그 답이 이 파일에 있다.

    [중요] **되짚는 이유** (실측 2026-08-19): 상주 claimer 는 **일이 있을 때만** 기록한다
    (폴링 자체는 조용하다) — 그래서 오늘자 파일이 하루 종일 없는 것이 **정상**이고, 오늘만
    보면 화면이 대부분 빈칸이 된다. [주의] 대신 **어느 날짜 파일인지 본문 머리에 적는다** —
    낡은 것을 최신인 척 보여 주지 않는다.
    """
    from datetime import timedelta
    r = reader or bundle._remote_read
    start = datetime.strptime(day, "%Y-%m-%d") if day else datetime.now()
    for back in range(max(1, lookback)):
        d = (start - timedelta(days=back)).strftime("%Y-%m-%d")
        text = r(facts, _remote_daily(facts, d))
        if not text:
            continue
        p = host_store(paths, str(getattr(facts, "host", "") or "unknown"))
        p.parent.mkdir(parents=True, exist_ok=True)
        stale = "" if back == 0 else f"  ← [주의] 오늘자가 아니다 ({back}일 전 파일)"
        body = (f"# {getattr(facts, 'host', '')} · claimer_{d}.log{stale} · 회수 "
                f"{datetime.now().astimezone().isoformat(timespec='seconds')}\n" + _tail(text))
        p.write_text(body, encoding="utf-8")
        return len(text.encode("utf-8", "replace"))
    return 0


def read_host_logs(paths) -> dict:
    """회수된 머신별 데몬 로그 — `{host: text}`. **로컬 사본만 읽는다.**"""
    d = Path(paths.root) / STORE_DIR / HOSTS_DIR
    if not d.is_dir():
        return {}
    out = {}
    for p in sorted(d.glob("*.log")):
        try:
            out[p.stem] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def _remote_path(facts, task_id: str, name: str) -> str:
    base = str(getattr(facts, "path", "") or "").rstrip("/\\")
    sep = "\\" if getattr(facts, "windows", False) else "/"
    rel = f"{DEBUG_REL}/{task_id}/{name}"
    if sep == "\\":
        rel = rel.replace("/", "\\")
    return f"{base}{sep}{rel}"


def _tail(text: str, limit: int = TAIL_BYTES) -> str:
    """뒤에서 limit 바이트. 잘랐으면 **잘랐다고 적는다** — 조용한 절단은 「이게 전부」로 읽힌다."""
    b = text.encode("utf-8", "replace")
    if len(b) <= limit:
        return text
    cut = b[-limit:]
    nl = cut.find(b"\n")
    kept = cut[nl + 1:] if nl >= 0 else cut
    return ("(...앞부분 잘림 — 원문은 워커의 .ax/logs/claimer_debug/ 에 있다)\n"
            + kept.decode("utf-8", "replace"))


def collect_task_logs(paths, facts, task_id: str, *, reader=None, now: str = "") -> dict:
    """태스크 하나의 로그를 걷어 트윈에 보관. 반환은 `{name: bytes}` (없으면 빈 dict).

    [중요] 못 읽은 것과 없는 것을 섞지 않는다 — `_remote_read` 가 예외를 던지면 그대로
    올린다(호출자가 사유를 기록한다). 빈 문자열은 「없다」이고 그것은 정상이다.
    """
    r = reader or bundle._remote_read
    got = {}
    for name in NAMES:
        text = r(facts, _remote_path(facts, task_id, name))
        if not text:
            continue
        d = store_dir(paths, task_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(_tail(text), encoding="utf-8")
        got[name] = len(text.encode("utf-8", "replace"))
    if got:
        meta = {"task_id": task_id, "host": getattr(facts, "host", ""),
                "at": now or datetime.now().astimezone().isoformat(timespec="seconds"),
                "bytes": got}
        (store_dir(paths, task_id) / META_NAME).write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return got


def collect(paths, *, project: str = "", facts=None, api=None, reader=None) -> dict:
    """진행 중·실패한 태스크의 워커 로그를 걷는다. 반환은 사람이 읽는 요약.

    [주의] **큐를 읽지 못하면 아무것도 걷지 않는다** — 어느 태스크가 어느 워커에 있는지가
    큐에만 있다. 조용히 넘기지 않고 사유를 반환한다.
    """
    from . import runner
    api = api or runner._api
    out = {"tasks": 0, "files": 0, "targets": 0, "empty": 0, "hosts": 0, "lines": []}
    try:
        tasks = api("GET", "/api/v1/tasks") or []
    except Exception as e:                                  # noqa: BLE001
        out["lines"].append(f"[주의] 큐를 못 읽었다 — {type(e).__name__}: {e}")
        return out
    if facts is None:
        facts = [bundle.probe(h, u, p, d, r)
                 for h, u, p, d, r in bundle.workshops(project or paths.name)]
    by_host = {f.host: f for f in facts}
    targets = [t for t in tasks if isinstance(t, dict)
               and str(t.get("status")) in WANT_STATUS
               and (t.get("worker_id") or t.get("assignee"))]
    # 최신부터 — 상한을 넘으면 오래된 것을 버린다 (버린 사실을 요약에 적는다)
    targets.sort(key=lambda t: str(t.get("claimed_at") or t.get("created") or ""),
                 reverse=True)
    dropped = max(0, len(targets) - MAX_TASKS)
    out["targets"] = len(targets)
    for t in targets[:MAX_TASKS]:
        tid = str(t.get("task_id") or "")
        host = str(t.get("worker_id") or t.get("assignee") or "")
        f = by_host.get(host)
        if f is None:
            out["lines"].append(f"{tid[:8]}: 워커 {host!r} 가 레지스트리에 없다 — 회수 안 함")
            continue
        try:
            got = collect_task_logs(paths, f, tid, reader=reader)
        except Exception as e:                              # noqa: BLE001
            out["lines"].append(f"{tid[:8]}: [주의] 회수 실패 — {type(e).__name__}: {e}")
            continue
        if got:
            out["tasks"] += 1
            out["files"] += len(got)
            out["lines"].append(f"{tid[:8]} @{host}: " + ", ".join(sorted(got)))
        else:
            # [중요] 조용히 넘기지 않는다 — 「파일 0」이 「대상 없음」인지 「대상은 있는데
            #    로그가 없음」인지 구별되지 않으면 사람이 원인을 못 찾는다 (실측 2026-08-19:
            #    첫 라이브 회수가 한 줄도 안 내놓아 이유를 알 수 없었다).
            out["empty"] += 1
            out["lines"].append(f"{tid[:8]} @{host}: 로그 없음 "
                                f"(작업장에 claimer_debug/{tid[:8]}… 가 아직 없다)")
    if dropped:
        out["lines"].append(f"[주의] 상한 {MAX_TASKS}건을 넘어 오래된 {dropped}건은 걷지 않았다")
    if not targets:
        out["lines"].append("걷을 태스크가 없다 (진행 중·실패 상태가 없다)")
    # 머신별 데몬 로그 — 태스크가 없어도 볼 것이 있다. 워커 역할만 (요청자는 데몬이 없다)
    for f in facts:
        if str(getattr(f, "role", "worker") or "worker") == "requester":
            continue
        try:
            n = collect_host_log(paths, f, reader=reader)
        except Exception as e:                              # noqa: BLE001
            out["lines"].append(f"{getattr(f, 'host', '?')}: [주의] 데몬 로그 회수 실패 — "
                                f"{type(e).__name__}: {e}")
            continue
        if n:
            out["hosts"] = out.get("hosts", 0) + 1
            out["lines"].append(f"{getattr(f, 'host', '?')}: 데몬 로그 {n}B")
        else:
            out["lines"].append(f"{getattr(f, 'host', '?')}: 데몬 로그 없음 "
                                f"(최근 {HOST_LOG_LOOKBACK}일 파일 모두 없다)")
    return out


def read_stored(paths, task_ids) -> dict:
    """회수된 사본을 읽는다 — **화면이 쓰는 경로. 원격을 타지 않는다.**

    반환: `{task_id: {"at": iso, "host": str, "files": {name: text}}}`.
    """
    out = {}
    for tid in task_ids or []:
        d = store_dir(paths, str(tid))
        if not d.is_dir():
            continue
        files = {}
        for name in NAMES:
            p = d / name
            if p.is_file():
                try:
                    files[name] = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
        if not files:
            continue
        meta = {}
        try:
            meta = json.loads((d / META_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass                    # 메타가 없어도 파일은 보여 준다 (나이만 모른다)
        out[str(tid)] = {"at": str(meta.get("at") or ""),
                         "host": str(meta.get("host") or ""), "files": files}
    return out


def main(argv=None) -> int:
    from ..context_search.paths import resolve
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "collect":
        print(__doc__.split("## 운송 규약")[0])
        print("  python -m master.work.logs collect [<프로젝트>]")
        return 2
    paths = resolve(argv[1] if len(argv) > 1 else "")
    got = collect(paths)
    for ln in got["lines"]:
        print(" ", ln)
    print(f"대상 {got['targets']} · 회수 {got['tasks']} · 파일 {got['files']}"
          + (f" · 로그 없음 {got['empty']}" if got["empty"] else "")
          + f" → {paths.root}/{STORE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
