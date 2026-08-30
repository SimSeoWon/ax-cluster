"""자동 파견 — 골조가 올라오면 마스터가 끝까지 배당한다 (`#340`).

## 왜 이것이 없었나

원전은 **워커 데몬이 30초마다 `claim`** 했다(`worker/worker.py`: poll → claim → LLM →
commit·push → submit → 다시 claim). 그 루프가 배당 엔진이었다. `#320`(2026-08-27)이 상주를
철거하면서 **그 엔진이 사라졌는데, 대체를 만들지 않았다** — `#320` 의 완료 조건은
*"빌드가 SSH 로 도는가"* 뿐이었고 파견을 라이브로 확인하지 않았다.

3일간 안 드러난 이유는 그 뒤 실제 분산 작업이 **파견 단계까지 간 적이 없어서**다. 2026-08-30
첫 완주 시도에서 골조가 올라오자 그제서야 「아무도 안 집는다」가 보였다. 사용자:
*"워커 데몬 안쓴다고 자동으로 등록된 모든 일 처리해야 된다는 말이잖아 —
작업완료되었다면 다음 일 할당시키라고"*.

## [중요] 「끝나면 다음 배당」은 이미 있다

`infer.run_many` 가 **워커가 빌 때마다 다음 태스크를 집는** 루프다(`while True` + 빈 워커
판정). 여기서 만드는 것은 그 루프를 **시작시키는 자리** 하나뿐이다 — 새 배당 엔진이 아니다.

## 트리거는 골조 push 다 — 등재가 아니다

등재 시점에는 골조가 아직 없다(`#317` ① 순서: 0 등재 → 1 브랜치 → 2 골조 → 3 태스크).
`task/<work_id>/base` 가 원격에 **나타나는 것**이 「요청자가 자기 몫을 끝냈다」는 유일한
관측 가능한 신호다. 그것은 이미 스풀에 이벤트로 들어온다(`post-receive` → `Event.ref`).

## [주의] 가드 넷 — 돈이 나가는 자리다

    멱등     pending 태스크가 있는 work 만. 이미 파견 중이면 물러난다
    base     `twin_base.resolve().exists` 가 참일 때만 (`#331` 과 같은 판정)
    동시성    파일 잠금 — 같은 work 을 두 프로세스가 밀지 않는다
    보고     걸었는지·왜 안 걸었는지를 **둘 다** 저널에 남긴다

[중요] **안 건 이유도 찍는다.** 오늘 `[register]` 로그가 없었으면 등재 실패를 못 찾았다 —
파견은 그보다 조용한 자리라 「안 걸렸다」가 안 보이면 사람이 영원히 기다린다.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

LOCK_DIR = Path.home() / ".cache" / "ax-dispatch"
# `refs/heads/task/<work_id>/base` — `#319` 계층형 이름. leaf 가 `base` 인 것만 신호다.
BASE_REF = re.compile(r"^refs/heads/(task/(?P<work>[^/]+)/base)$")


def work_id_from_ref(ref: str) -> str:
    """골조 push 인가. 아니면 빈 문자열.

    [주의] 조각 durable(`task/<W>/<T>`)은 신호가 아니다 — 그것은 통합자가 미는 것이고,
    그때 파견을 다시 걸면 무한 루프다.
    """
    m = BASE_REF.match((ref or "").strip())
    return m.group("work") if m else ""


def _log(msg: str) -> None:
    print(f"[dispatch] {msg}", flush=True)


class _Lock:
    """work 하나당 잠금. **같은 work 을 두 번 밀지 않는다.**

    [주의] 소비자의 flock 과 같은 결이다 — 잡히면 **기다리지 않고 물러난다.** 파견은 분 단위라
    줄 세우면 뒤엣것이 리스 만료를 본다.
    """

    def __init__(self, work_id: str):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOCK_DIR / f"{work_id}.lock"
        self.fd = None

    def __enter__(self):
        import fcntl
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.fd)
            self.fd = None
            return None
        os.write(self.fd, f"{os.getpid()} {time.time():.0f}\n".encode())
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            import fcntl
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


def pending_tasks(work_id: str, *, api=None) -> list:
    """아직 아무도 안 집은 태스크. [중요] **이것이 비면 파견하지 않는다** (멱등)."""
    from . import runner
    call = api or runner._api
    got = call("GET", f"/api/v1/works/{work_id}")
    tasks = (got or {}).get("tasks") or []
    return [t for t in tasks if str(t.get("status") or "") == "pending"]


def should_dispatch(paths, work_id: str, *, api=None) -> tuple:
    """`(걸까, 사유)`. **안 거는 이유도 문장으로 낸다** — 조용히 넘기지 않는다."""
    from . import runner, twin_base
    call = api or runner._api
    try:
        got = call("GET", f"/api/v1/works/{work_id}")
    except Exception as e:                                   # noqa: BLE001
        return False, f"work 조회 실패 — {type(e).__name__}: {e}"
    work = (got or {}).get("work") or {}
    if not work:
        return False, f"큐에 없는 work 이다 ({work_id})"
    status = str(work.get("merge_status") or "")
    if status not in ("in_progress", ""):
        return False, f"merge_status={status!r} — 진행 중인 work 만 민다"

    pend = [t for t in (got.get("tasks") or []) if str(t.get("status") or "") == "pending"]
    if not pend:
        return False, "pending 태스크가 없다 — 이미 파견됐거나 끝났다 (멱등)"

    # [중요] `#331` 과 같은 판정 — base 가 없으면 조각이 갈라질 자리가 없다
    b = twin_base.resolve(paths, work_id)
    if not b.checked:
        return False, f"base 확인 실패 — {b.error} (확인 실패는 통과가 아니다)"
    if not b.exists:
        return False, f"base 가 원격에 없다 — {b.branch}. 요청자가 먼저 올려야 한다"
    return True, f"pending {len(pend)}건 · base {b.commit[:8]}"


def dispatch(paths, work_id: str, *, limit: int = 0, api=None, runner_many=None) -> dict:
    """한 work 을 **끝까지** 민다. `run_many` 가 워커가 빌 때마다 다음 조각을 집는다.

    [중요] 여기서 배당 루프를 새로 짜지 않는다 — `infer.run_many` 가 이미 그것이고,
    *"워커가 빌 때만 집는다"* 는 실측된 규칙(집어놓고 못 돌리면 리스가 1200초 묶인다)이다.
    """
    ok, why = should_dispatch(paths, work_id, api=api)
    if not ok:
        _log(f"{work_id} 안 건다 — {why}")
        return {"dispatched": False, "reason": why}

    with _Lock(work_id) as lk:
        if lk is None:
            _log(f"{work_id} 안 건다 — 이미 파견이 돌고 있다 (잠금)")
            return {"dispatched": False, "reason": "이미 파견 중"}
        n = limit or len(pending_tasks(work_id, api=api))
        _log(f"{work_id} 파견 시작 — {why} · limit={n}")
        fn = runner_many
        if fn is None:
            from .infer import run_many as fn                # noqa: PLC0415
        hand = fn(paths, limit=n, project=paths.name, work_id=work_id)
        # [중요] **필드 이름을 확인하고 읽는다** (`#342`, 실측 2026-08-30). 처음에
        #    `hand.responses` 를 읽어 **성공을 「응답 0건」으로 보고**했다 — 실제로는
        #    `Handoff.items` 다(`[(order, Response), …]`). 만들고 확인하지 않은 자리다.
        note = getattr(hand, "note", "") or ""
        items = list(getattr(hand, "items", []) or [])
        skipped = list(getattr(hand, "skipped", []) or [])
        ok = [r for _o, r in items if str(getattr(r, "status", "")) == "DONE"]
        bad = [r for _o, r in items if str(getattr(r, "status", "")) != "DONE"]
        _log(f"{work_id} 파견 끝 — 성공 {len(ok)} · 실패 {len(bad)} · 건너뜀 {len(skipped)}"
             + (f" · {note}" if note else ""))
        # [중요] **실패·건너뜀은 한 줄씩 찍는다** — 수를 세는 것만으로는 왜 멈췄는지 모른다.
        for r in bad:
            _log(f"  [실패] {getattr(r,'task_id','?')} @ {getattr(r,'worker','?')} — "
                 f"{str(getattr(r,'reason',''))[:200]}")
        for tid, why in skipped:
            _log(f"  [건너뜀] {tid} — {why}")
        return {"dispatched": True, "ok": len(ok), "failed": len(bad),
                "skipped": len(skipped), "note": note}


def on_push(paths_for, ref: str, *, api=None) -> dict:
    """스풀 이벤트 하나를 본다. 골조 push 가 아니면 아무것도 안 한다.

    `paths_for(work_id)` 는 프로젝트 경로 해석기 — 호출부가 준다(이벤트가 프로젝트를 안다).
    """
    work_id = work_id_from_ref(ref)
    if not work_id:
        return {"dispatched": False, "reason": "골조 push 가 아니다"}
    return dispatch(paths_for(work_id), work_id, api=api)


def main(argv) -> int:
    """`python -m master.work.autodispatch <프로젝트> [work_id]`

    work_id 를 안 주면 그 프로젝트의 **열린 work 전부**를 훑는다 — 트리거를 놓쳤을 때의
    따라잡기다(`ax-indexer.timer` 가 같은 이유로 있다).
    """
    from ..context_search.paths import resolve
    from . import runner
    if not argv:
        print(__doc__)
        return 2
    paths = resolve(argv[0])
    if len(argv) > 1:
        r = dispatch(paths, argv[1])
        return 0 if r.get("dispatched") else 1
    works = runner._api("GET", f"/api/v1/works?project={paths.name}")
    open_ids = [w["work_id"] for w in (works if isinstance(works, list) else [])
                if str(w.get("merge_status") or "") in ("in_progress", "")]
    if not open_ids:
        _log(f"{paths.name}: 열린 work 없음")
        return 0
    for wid in open_ids:
        dispatch(paths, wid)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
