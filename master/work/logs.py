"""파견 기록 — **마스터가 이미 들고 있는 것**을 화면이 읽게 한다 (#220 ③-B → `#323`).

## [중요] 이 모듈은 2026-08-28 에 재료가 바뀌었다

종전에는 **작업장의 `claimer` 로그를 SSH 로 걷어왔다.** 그 상주는 `#320` 으로 철거됐고,
그러자 이 경로가 **결과가 정해진 SSH** 가 됐다 — 5분마다 워커에 붙어 `claimer_debug/<task>/…`
를 찾는데 그 파일을 쓰던 주체가 없으니 언제나 「로그 없음」이다. *"BC-250 을 자주 두드리지
않는다"*(`#105`)와 정면으로 어긋났다.

[중요] **재료는 이미 있었다.** push 파견이 워커의 stdout 꼬리를 **스풀에 원자적으로** 쓴다
(`work/infer.py` `spool()`): `worker` · `status` · `at` · `tail` · `files` · `usage`.
「누가·언제·뭘 했나」의 답이 마스터 디스크에 있는데 같은 것을 원격에서 다시 걷고 있었다.

    종전   워커 디스크 → SSH 5분 주기 → 트윈 사본 → 화면
    지금   스풀(파견이 이미 쓴다)     → 화면          [중요] **SSH 0**

## [주의] 그래서 사라진 것

`claimer` 만 쓰던 것들이다 — 심박·LLM stderr 분리 파일·머신별 일별 로그(`_hosts/`).
push 모델에서 워커는 **파일을 남기지 않는다**(추론만 하고 응답을 돌려준다). 남길 주체가
없는 것을 걷는 척하지 않는다.

[중요] **옛 회수 사본은 지우지 않았다** — `<트윈>/worker_logs/` 아래 상주 시절 기록이다.
그것은 역사이지 현재가 아니므로 화면이 더 이상 읽지 않는다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = "worker_logs"           # [주의] 옛 회수 사본이 여기 남아 있다 (역사)
TAIL_LABEL = "워커 stdout 꼬리"      # 화면의 파일 이름 자리에 들어간다
MAX_RUNS = 40                       # 화면에 올릴 상한 (최신부터)


def spool_root(paths) -> Path:
    """스풀 뿌리 = `paths.responses`.

    [주의] `infer.spool_dir(paths)` 을 그대로 쓰면 **틀린다** — 그건 work_id 가 없을 때
    `responses/loose` 를 가리키는 *버킷*이지 뿌리가 아니다(실측 2026-08-28: 그래서 처음에
    0건이 나왔다). 파견이 쓰는 곳과 화면이 읽는 곳의 공통 근거는 `paths.responses` 다.
    """
    return Path(paths.responses)


def read_runs(paths, task_ids=None) -> dict:
    """`{task_id: {"at", "host", "files": {이름: 본문}}}` — **로컬 스풀만 읽는다.**

    반환 모양은 종전 `read_stored` 와 같다 — `status.log_block` 이 그대로 렌더한다.
    `task_ids` 를 주면 그것만, 비우면 전부(최신 `MAX_RUNS` 건).

    [중요] **원격을 타지 않는다.** `/cluster` 는 15초마다 리로드하므로 서빙 순간의 SSH 는
    120초 가드를 깬다 — 그것이 종전 구조가 회수를 5분 타이머에 묶어 둔 이유였고, 스풀을
    읽으면 그 제약 자체가 사라진다.
    """
    root = spool_root(paths)
    if not root.is_dir():
        return {}
    want = {str(t) for t in (task_ids or [])} or None
    recs = []
    for p in root.rglob("*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                # 깨진 스풀 한 건이 화면을 죽이지 않는다
        tid = str(rec.get("task_id") or "")
        if not tid or (want is not None and tid not in want):
            continue
        recs.append((str(rec.get("at") or ""), tid, rec))
    recs.sort(reverse=True)
    out = {}
    for _at, tid, rec in recs[:MAX_RUNS]:
        if tid in out:
            continue                # 같은 태스크가 여러 번이면 **최신 것**만
        files = {}
        tail = str(rec.get("tail") or "").strip()
        if tail:
            files[TAIL_LABEL] = tail
        reason = str(rec.get("reason") or "").strip()
        if reason:
            files["사유"] = reason
        notes = [str(n) for n in (rec.get("notes") or []) if str(n).strip()]
        if notes:
            files["비고"] = "\n".join(notes)
        if not files:
            # [중요] 조용히 넘기지 않는다 — 「기록 없음」이 「파견 안 함」인지 「파견했는데
            #    남긴 것이 없음」인지 구분되지 않으면 사람이 원인을 못 찾는다(종전 모듈이
            #    같은 이유로 `empty` 를 따로 셌다).
            files["(비어 있음)"] = (f"status={rec.get('status')} — 파견은 됐는데 남긴 본문이 "
                                    f"없다. 워커가 stdout 을 못 냈거나 스풀이 잘렸다")
        out[tid] = {"at": str(rec.get("at") or ""), "host": str(rec.get("worker") or ""),
                    "files": files, "status": str(rec.get("status") or "")}
    return out


def summary(paths) -> dict:
    """사람이 읽는 한 줄 — `python -m master.work.logs` 가 쓴다."""
    runs = read_runs(paths)
    hosts = sorted({v["host"] for v in runs.values() if v["host"]})
    return {"runs": len(runs), "hosts": hosts,
            "lines": [f"{tid[:8]} @{v['host']} · {v['status']} · {v['at']}"
                      for tid, v in sorted(runs.items(), key=lambda kv: kv[1]["at"],
                                           reverse=True)]}


def main(argv) -> int:
    from ..context_search.paths import resolve
    paths = resolve(argv[0] if argv else "")
    got = summary(paths)
    print(f"파견 기록 {got['runs']}건 · 워커 {', '.join(got['hosts']) or '(없음)'}")
    for ln in got["lines"][:MAX_RUNS]:
        print("  " + ln)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
