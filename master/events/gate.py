"""색인 일시 중지 게이트 — 원전 `watcher/watch_state._has_active_distribute_work` 이식.

[중요] **왜 멈추나** (원전 주석): *"feature 브랜치 작업 중 main 인덱싱 무의미 + **워커들과 git lock
경쟁 방지**"*. 파이프라인이 조각마다 커밋·push 하면 한 work 안에서 색인기가 그만큼 깨어난다 —
실측 2026-08-14: 셀프테스트 3회가 만든 push 로 **15회 깨어나 14회가 `재색인 건너뜀`.**

## [중요] `in_progress` 만 pause 조건이다

원전 docstring 원문 — *"**Phase 2 변경: `in_progress` 만 pause 조건.** `ready_for_review` 는
auto_cleanup 이 이미 main 으로 복귀시킨 시점이라 **watcher 재개해야 함**(리뷰 결정은 비동기 —
main 위에서 다른 작업 진행해도 무방)."*

[주의] **원전에는 「active」가 둘 있고 섞으면 틀린다** — cleanup·중복검사용 집합
(`{merged, rejected, cancelled}` 제외 전부)과 **pause 조건**(`in_progress` 만)은 다른 개념이다.
2026-08-14 에 내가 전자를 후자로 옮겨 적었다가 원전 정독에서 정정했다.

## [주의] 건너뛰어도 유실이 없는 이유 — 우리 소비자는 state-based 다

이벤트는 **깨우는 신호**일 뿐이고, 무엇을 색인할지는 소비자가 **미러 HEAD 를 대조해** 정한다.
그래서 이번에 건너뛰면 미러가 뒤에 남고 **다음 번에 누적분이 한꺼번에** 잡힌다(self-heal).
[중요] 그러나 *"다음 번"* 을 만드는 주체가 있어야 한다 — `ax-indexer.path` 는 스풀에 파일이 생길 때만
깨우므로, 게이트만 두고 타이머를 안 두면 **깨울 주체가 아무도 없다**(리포트 13 §19.3 이 상태
화면에서 똑같이 물린 자리). → `ax-indexer.timer` 가 짝이다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_QUEUE_URL = "http://127.0.0.1:8101"
PAUSE_STATUS = "in_progress"        # [중요] 이것만. 위 절 참조.
HTTP_TIMEOUT = 3


@dataclass
class Verdict:
    paused: bool = False
    reason: str = ""
    works: tuple = ()               # pause 를 유발한 work_id 들
    source: str = ""                # "http" | "disk" | "none"
    degraded: str = ""              # HTTP 실패로 폴백했을 때의 사유

    def line(self) -> str:
        if not self.paused:
            base = "색인 진행 — 진행 중 분산 작업 없음"
        else:
            base = (f"[중요] 색인 일시 중지 — 진행 중 분산 작업 {len(self.works)}건 "
                    f"({', '.join(self.works[:3])}{'…' if len(self.works) > 3 else ''})")
        if self.degraded:
            base += f" · [주의] {self.degraded}"
        return base


def _token() -> str:
    """세 서비스 전부 bearer 토큰이 필수다(fail-closed). 경로는 `auth` 가 SSOT."""
    from ..auth import token_file
    try:
        return token_file().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _from_http(queue_url: str) -> tuple:
    """`(works, err)`. 큐가 답하면 그것이 SSOT 다."""
    tok = _token()
    if not tok:
        return None, "토큰을 읽지 못했다"
    req = urllib.request.Request(
        queue_url.rstrip("/") + "/api/v1/works",
        headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
        data = json.loads(body) if body.strip() else []
        works = data if isinstance(data, list) else data.get("works", [])
        return [w for w in works if isinstance(w, dict)], ""
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"큐 HTTP 실패 ({type(e).__name__}) — 디스크 폴백"


def _from_disk(spool_root: Path) -> tuple:
    """폴백 — 큐의 디스크 표현을 직접 읽는다. 원전도 같은 2단 구조였다.

    [주의] 큐가 답하지 않을 때 **멈추지 않는 쪽으로 기울지 않는다** — 못 읽었으면 그 사실을 싣고
    올려서 호출자가 판단하게 한다. *"모르면 진행"* 은 워커와 경쟁할 위험을 조용히 택하는 것이다.
    """
    d = spool_root / "works"
    if not d.is_dir():
        return None, f"큐 디스크 표현이 없다: {d}"
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            w = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(w, dict):
                out.append(w)
        except (OSError, ValueError):
            continue
    return out, ""


def check(*, queue_url: str = DEFAULT_QUEUE_URL, spool_root: Path | None = None,
          works: list | None = None) -> Verdict:
    """색인을 멈춰야 하나. `works` 를 주면 그것으로 판정한다(테스트용 — HTTP·디스크 미접촉).

    [중요] **큐에도 디스크에도 못 물으면 멈추지 않는다.** 그 대신 `degraded` 에 사유를 실어
    **로그에 남게** 한다 — 항상 멈추는 게이트는 색인을 영구 정지시키고, 그건 게이트가 아니라
    고장이다(*"항상 빨간 게이트는 게이트가 아니다"*).
    """
    degraded = ""
    src = "given"
    if works is None:
        works, err = _from_http(queue_url)
        src = "http"
        if works is None:
            degraded = err
            if spool_root is not None:
                works, err2 = _from_disk(spool_root)
                src = "disk"
                if works is None:
                    degraded = f"{err} · {err2}"
            else:
                works = None
        if works is None:
            return Verdict(paused=False, reason="상태를 확인할 수 없다", source="none",
                           degraded=f"{degraded} — [중요] 멈추지 않고 진행한다(판단 근거 부재)")

    stuck = tuple(str(w.get("work_id", "?")) for w in works
                  if (w.get("merge_status") or "").lower() == PAUSE_STATUS)
    if stuck:
        return Verdict(paused=True, reason=f"{PAUSE_STATUS} work {len(stuck)}건",
                       works=stuck, source=src, degraded=degraded)
    return Verdict(paused=False, reason="진행 중 작업 없음", source=src, degraded=degraded)
