"""작업 경계 판정 (`#942` T4) — 무엇이 「작업 하나」의 시작이고 끝인가.

지금은 **AX 일감** 하나가 작업 하나다(`AxIssueBoundary`):

    candidates()      고를 수 있는 열린 일감
    may_open(N)       세션을 열어도 되나 — 다른 일감이 작업 중(일감 잠금 활성)이면 거절
    closable(N)       마무리해도 되나 — 일감이 「완료」이고, 작업 보고서가 있고, 잠금이 풀렸을 때만

[중요] **이 모듈은 일감을 닫지 않는다.** 마감은 기존 절차(`issue_finish`)가 하고, 여기는 읽기만 한다.
[중요] **조회 실패는 「아니다」가 아니라 「모른다」다** — `ok=False` 와 사유를 돌려주고 추정하지 않는다.
`.33` 언리얼 작업의 판정은 같은 세 메서드를 가진 클래스를 옆에 더한다 — 콘솔은 이 세 메서드만 쓴다.
"""
from __future__ import annotations

from pathlib import Path

CLOSED_STATUS = "완료"


def _default_reports() -> Path:
    return Path(__file__).resolve().parents[2] / "reports"


class AxIssueBoundary:
    """AX 인프라 일감 기준. 조회 함수는 주입할 수 있다(검사용) — 비우면 실제 Redmine·일감 잠금을 읽는다."""

    name = "ax-issue"

    def __init__(self, *, lister=None, getter=None, lock_current=None, reports_dir=None, dbg=None):
        self._lister = lister
        self._getter = getter
        self._lock_current = lock_current
        self.reports_dir = Path(reports_dir) if reports_dir else _default_reports()
        self.dbg = dbg or (lambda where, msg: None)

    # ── 읽기 ──
    def _list(self) -> dict:
        if self._lister:
            return self._lister()
        from master import redmine
        return redmine.list_issues(limit=100)

    def _get(self, issue_id) -> dict:
        if self._getter:
            return self._getter(issue_id)
        from master import redmine
        return redmine.get_issue(issue_id)

    def active_issue(self) -> tuple:
        """(활성 일감 번호 또는 None, 조회 실패 사유)."""
        try:
            if self._lock_current:
                cur = self._lock_current()
            else:
                from master import issue_lock
                cur = issue_lock.current(issue_lock.default_root())
        except Exception as e:                          # noqa: BLE001 — 사유를 돌려준다
            why = f"일감 잠금 조회 실패 — {type(e).__name__}: {e}"
            self.dbg("boundary.lock", why)
            return None, why
        if not cur:
            return None, ""
        try:
            return int(cur.get("issue_id") if "issue_id" in cur else cur.get("issue")), ""
        except (TypeError, ValueError):
            why = f"일감 잠금 기록에서 번호를 읽지 못했다: {cur!r}"
            self.dbg("boundary.lock", why)
            return None, why

    def reports_for(self, issue_id) -> list:
        """파일 이름에 일감 번호가 든 작업 보고서 (`<순번>-<N>-<설명>.md`)."""
        if not self.reports_dir.is_dir():
            return []
        return sorted(str(p) for p in self.reports_dir.glob(f"[0-9]*-{int(issue_id)}-*.md"))

    # ── 판정 ──
    def candidates(self) -> dict:
        got = self._list()
        if not isinstance(got, dict) or got.get("error"):
            why = (got or {}).get("error") if isinstance(got, dict) else f"형식 오류: {got!r}"
            self.dbg("boundary.candidates", f"일감 목록 조회 실패 — {why}")
            return {"ok": False, "why": f"일감 목록 조회 실패 — {why}", "issues": []}
        active, lock_why = self.active_issue()
        rows = [{"id": i.get("id"), "subject": i.get("subject", ""), "status": i.get("status", ""),
                 "active": i.get("id") == active} for i in got.get("issues") or []]
        self.dbg("boundary.candidates", f"열린 일감 {len(rows)}건 · 잠금 활성 {active or '없음'}"
                                        + (f" · {lock_why}" if lock_why else ""))
        return {"ok": True, "why": lock_why, "issues": rows, "active": active}

    def may_open(self, issue_id) -> dict:
        n = int(issue_id)
        active, lock_why = self.active_issue()
        if lock_why:
            r = {"ok": False, "why": lock_why}
        elif active and active != n:
            r = {"ok": False, "why": f"#{active} 작업이 진행 중이다 — 그 일감을 완료·보류·취소한 뒤 #{n} 을 연다",
                 "active": active}
        else:
            got = self._get(n)
            if not isinstance(got, dict) or got.get("error"):
                r = {"ok": False, "why": f"#{n} 조회 실패 — {(got or {}).get('error') if isinstance(got, dict) else got!r}"}
            elif got.get("status") == CLOSED_STATUS:
                r = {"ok": False, "why": f"#{n} 은 이미 「{CLOSED_STATUS}」다 — 새 작업 세션을 열지 않는다"}
            else:
                r = {"ok": True, "why": "", "subject": got.get("subject", ""), "status": got.get("status", ""),
                     "active": active}
        self.dbg("boundary.may_open", f"#{n} → {'허용' if r['ok'] else '거절: ' + r['why']}")
        return r

    def closable(self, issue_id) -> dict:
        n = int(issue_id)
        got = self._get(n)
        if not isinstance(got, dict) or got.get("error"):
            r = {"ok": False, "why": f"#{n} 조회 실패 — {(got or {}).get('error') if isinstance(got, dict) else got!r}",
                 "status": "", "reports": []}
            self.dbg("boundary.closable", f"#{n} → 거절: {r['why']}")
            return r
        status = got.get("status", "")
        reports = self.reports_for(n)
        active, lock_why = self.active_issue()
        missing = []
        if status != CLOSED_STATUS:
            missing.append(f"일감 상태가 「{status or '?'}」다(「{CLOSED_STATUS}」가 아니다)")
        if not reports:
            missing.append(f"작업 보고서가 없다({self.reports_dir}/*-{n}-*.md)")
        if lock_why:
            missing.append(lock_why)
        elif active == n:
            missing.append("일감 잠금이 아직 활성이다")
        r = {"ok": not missing, "why": " · ".join(missing), "status": status, "reports": reports}
        self.dbg("boundary.closable", f"#{n} → {'마무리 가능' if r['ok'] else '거절: ' + r['why']} "
                                      f"(상태={status} 보고서={len(reports)}건 잠금활성={active})")
        return r
