"""분산 work·조각의 **읽기 전용 래퍼** — Redmine `#363` 1단계 (사용자 설계 2026-10-11).

## 왜 있나

큐는 work·조각을 날 dict 로 준다(`GET /api/v1/works/{id}` → `{"work":…, "tasks":[…]}`).
그 dict 를 여러 모듈이 **제각각** 읽었고 결함이 거기서 났다 — 라운드 브랜치 이름(`#362`),
followup 이 큐에 없는 사유 키를 읽어 「사유 없음」만 찍던 것(`e81abfd`). 해석을 한 자리에 둔다.

## 조각 상태 넷 (사용자 결정) — 큐 값은 `task_queue/` 에서 읽었다

    pending                    대기
    claimed · submitted        작업중      (`logic_claim.py:240` · `logic_lifecycle.py:120`)
    verified                   성공
    failed · cancelled         실패        재시도 없음
    needs_revision             실패        **재시도 예정** (시도 n/MAX — `logic_claim.py:178` 후보)
    stuck                      실패        재시도 없음 — `reclaim.py:215` 리스 재회수 3회 초과,
                                           큐가 다시 집지 않는다(후보는 pending·needs_revision 뿐)
    그 밖                      미상        [중요] 「대기」로 접지 않는다 — kind `unknown`

## 실패 종류 — 큐의 사유 필드에서 **읽기만** 해서 가른다

판정 순서는 `infer.commit_task` 와 같다: 인증 → 한도 → 환경 → 출력 반복 → (골조) → 상한 → 코드.
표지 목록은 `revise.py` 의 것을 그대로 쓴다 — 여기서 다시 만들지 않는다.

    code         층1·층2 지적 — 피드백 재시도로 고칠 수 있다            → retry
    quota        한도 소진 — 다른 워커에게                              → reassign
    environment  실행 환경 실패 — 같은 기계 재시도 무의미               → reassign
    auth         인증 실패 — 재로그인은 사람 몫                         → notify_human
    repeat       직전 시도와 같은 출력 지문                              → stop
    cap          시도 상한 도달                                         → notify_human
    cancelled    사람 취소 · no_work · requester_handoff                → none
    skeleton     같은 동결 위반이 반복 — 골조 결함                       → notify_human
    unknown      표지 없음 · 미상 상태 · stuck                          → notify_human

🔴 **골조 결함 규칙** (사용자 결정 2026-10-11 — 「같은 위반의 반복」): 이번 라운드 조각이
`needs_revision`/`failed` 이고 사유에 층1 의 동결 위반 문구가 있는데 ⑴ `attempt_count ≥ 2`
이거나 ⑵ 같은 라운드에 동결 위반으로 막힌 조각이 **둘 이상**이면 `skeleton`. 한 조각의 첫
위반은 워커 실수로 보고 `code` 로 둔다.

[중요] **1단계는 권고만 한다** — `decide()` 는 큐·파견에 아무것도 쓰지 않는다. 2단계에서
`infer.commit_task` 의 판정이 여기로 온다. 권고 문구는 사실만 싣는다(명령형 없음 — `followup.render`
머리말과 같은 규칙).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import revise as _RV

# ── 네 상태 ─────────────────────────────────────────────────────────────────
WAITING, WORKING, SUCCESS, FAILED, UNKNOWN_STATE = "대기", "작업중", "성공", "실패", "미상"
STATES = (WAITING, WORKING, SUCCESS, FAILED)

STATUS_STATE = {
    "pending": WAITING,
    "claimed": WORKING,
    "submitted": WORKING,
    "verified": SUCCESS,
    "failed": FAILED,
    "cancelled": FAILED,
    "needs_revision": FAILED,
    "stuck": FAILED,
}
RETRYABLE_STATUSES = ("needs_revision",)
MAX_ATTEMPTS = _RV.MAX_ATTEMPTS

# ── 실패 종류 · 권고 ────────────────────────────────────────────────────────
CODE, QUOTA, ENVIRONMENT, AUTH = "code", "quota", "environment", "auth"
REPEAT, CAP, CANCELLED, SKELETON, UNKNOWN = "repeat", "cap", "cancelled", "skeleton", "unknown"
KINDS = (CODE, QUOTA, ENVIRONMENT, AUTH, REPEAT, CAP, CANCELLED, SKELETON, UNKNOWN)

RETRY, REASSIGN, NOTIFY_HUMAN, STOP, NONE = "retry", "reassign", "notify_human", "stop", "none"
ACTION_OF = {
    CODE: RETRY, QUOTA: REASSIGN, ENVIRONMENT: REASSIGN, AUTH: NOTIFY_HUMAN,
    REPEAT: STOP, CAP: NOTIFY_HUMAN, CANCELLED: NONE, SKELETON: NOTIFY_HUMAN,
    UNKNOWN: NOTIFY_HUMAN,
}

# 층1 이 동결 위반을 적는 문구 — `layer1.check` 의 `f"{path}: 동결 위반 — {why}"`
# (`.h` 는 `skeleton.violation`, `.py` 는 `pyskel.violation` 이 `why` 를 낸다).
FROZEN_MARK = "동결 위반"
# 층1·층2 가 코드를 지적한 문구 — `layer1.Layer1.summary`(「층1 위반 N:」) · `infer` 의 층2 단계명
CODE_MARKS = ("층1 위반", "층1 이 막았다", "층2")
BLOCK_STATUSES = ("needs_revision", "failed")

# ── 사유 키 — 큐가 상태별로 적는 자리 (`task_queue/logic_lifecycle.py`, 실측 2026-10-11) ──
#   failed          `fail_reason`(≤120) + `fail_detail`(≤600)   submit 실패 · `verify:<result>`
#   cancelled       `cancel_reason`(≤300)                       취소 API
#   needs_revision  `last_feedback`(≤600)                       층1 revise · verify revise
# [주의] 옛 키는 폴백으로만 남긴다 (주입 테스트·옛 레코드). `followup` 이 이 이름을 다시 내보낸다.
REASON_KEYS = {
    "failed": ("fail_reason", "fail_detail"),
    "cancelled": ("cancel_reason",),
    "needs_revision": ("last_feedback",),
}
LEGACY_REASON_KEYS = ("failure", "error", "reason")


def reason_texts(t: dict) -> list:
    """그 상태에서 큐가 쓰는 사유 원문들(자르지 않는다). 없으면 옛 키 하나. 비면 []."""
    parts = []
    for k in REASON_KEYS.get(str((t or {}).get("status") or ""), ()):
        v = str(t.get(k) or "").strip()
        if v and v not in parts:
            parts.append(v)
    if not parts:
        for k in LEGACY_REASON_KEYS:
            v = str((t or {}).get(k) or "").strip()
            if v:
                parts.append(v)
                break
    return parts


def task_reason(t: dict, limit: int = 300) -> str:
    """조각 하나의 사유 — 그 상태에서 큐가 쓰는 키를 먼저, 없으면 옛 키. 비면 ""."""
    return " — ".join(reason_texts(t))[:limit]


def round_filter(work: dict, tasks) -> list:
    """`advance_work` 와 **같은** 라운드 거르기 — 스탬프 없는 옛 레코드는 거르지 않는다."""
    cur = int((work or {}).get("round", 1) or 1)
    tasks = list(tasks or [])
    if any(int(t.get("round") or 0) > 0 for t in tasks):
        tasks = [t for t in tasks if int(t.get("round") or 0) in (0, cur)]
    return tasks


def _fp_of(detail: str) -> str:
    """`revise.tag_detail` 이 앞에 붙인 지문(`[fp:<12hex>] `). 없으면 ""."""
    s = str(detail or "")
    n = len(_RV.FP_PREFIX)
    if s.startswith(_RV.FP_PREFIX) and s[n + 12:n + 13] == "]":
        return s[n:n + 12]
    return ""


# ─────────────────────────────────────────────────────────────
# Task
# ─────────────────────────────────────────────────────────────

@dataclass
class Task:
    """조각 하나. `raw` 는 큐의 dict 그대로다(복사본)."""

    raw: dict = field(default_factory=dict)

    # ── 사실 ──
    @property
    def task_id(self) -> str:
        return str(self.raw.get("task_id") or self.raw.get("id") or "")

    @property
    def status(self) -> str:
        return str(self.raw.get("status") or "")

    @property
    def round(self) -> int:
        return int(self.raw.get("round") or 0)

    @property
    def worker(self) -> str:
        """`worker_id`, 없으면 `assignee` — revise·취소 뒤엔 `worker_id` 가 비워진다."""
        return str(self.raw.get("worker_id") or self.raw.get("assignee") or "")

    @property
    def attempt(self) -> int | None:
        v = self.raw.get("attempt_count")
        return int(v or 0) if v is not None else None

    @property
    def reason(self) -> str:
        return task_reason(self.raw)

    # ── 네 상태 ──
    @property
    def state(self) -> str:
        return STATUS_STATE.get(self.status, UNKNOWN_STATE)

    @property
    def known(self) -> bool:
        return self.status in STATUS_STATE

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE_STATUSES

    @property
    def state_label(self) -> str:
        if not self.known:
            return f"{UNKNOWN_STATE}(큐 상태 `{self.status or '비어 있음'}`)"
        if self.retryable:
            return f"{FAILED}·재시도 예정 (시도 {self.attempt or 0}/{MAX_ATTEMPTS})"
        return self.state

    @property
    def frozen(self) -> bool:
        """막힌 상태이고 사유에 층1 동결 위반 문구가 있다."""
        return self.status in BLOCK_STATUSES and any(FROZEN_MARK in s for s in reason_texts(self.raw))

    # ── 실패 종류 (단독 판정 — 라운드 규칙 ⑵ 는 `Work.decide` 가 얹는다) ──
    def classify(self, *, peers_frozen: int = 0) -> tuple:
        """`(kind, 근거)`. 실패가 아니면 `("", "")`. `peers_frozen` = 같은 라운드에서
        동결 위반으로 막힌 조각 수(자기 포함)."""
        if self.state not in (FAILED, UNKNOWN_STATE):
            return "", ""
        if not self.known:
            return UNKNOWN, f"큐 상태 `{self.status or '비어 있음'}` 를 모른다 — 대기로 접지 않는다"
        st, raw = self.status, self.raw
        if st == "cancelled":
            if raw.get("no_work"):
                return CANCELLED, "할 일 없음(no_work) — 골조에 `[PSEUDO]` 가 없던 조각"
            if raw.get("requester_handoff"):
                return CANCELLED, "요청자가 ⑦ 통합에서 맡기로 한 조각(requester_handoff)"
            why = str(raw.get("cancel_reason") or "").strip()
            return CANCELLED, "사람이 취소" + (f" — {why[:200]}" if why else " — 사유 기록 없음")
        if st == "stuck":
            return UNKNOWN, (f"stuck — 리스 만료 재회수 {int(raw.get('reclaim_count') or 0)}회 "
                             "(상한 3 초과), 큐가 자동으로 다시 집지 않는다")
        texts = reason_texts(raw)
        hit = _RV.authentication_failure(texts)
        if hit:
            return AUTH, f"인증 실패(표지 `{hit}`) — 재로그인은 사람 몫"
        hit = _RV.quota_exhausted(texts)
        if hit:
            return QUOTA, f"한도 소진(표지 `{hit}`) — 다른 워커 재할당 대상"
        hit = _RV.environment_failure(texts)
        if hit:
            return ENVIRONMENT, f"실행 환경 실패(표지 `{hit}`) — 같은 기계 재시도 무의미, 다른 워커 재할당 대상"
        if st == "failed":
            fp = _fp_of(raw.get("fail_detail"))
            if fp and _RV.repeated_output(raw.get("last_feedback") or "", fp):
                return REPEAT, f"직전 시도와 같은 출력(fp={fp}) — 재시도 무의미"
        attempt = self.attempt or 0
        if self.frozen and (attempt >= 2 or peers_frozen >= 2):
            why = (f"같은 조각이 시도 {attempt}회째에도 동결 위반" if attempt >= 2
                   else f"같은 라운드 조각 {peers_frozen}건이 동시에 동결 위반")
            return SKELETON, f"골조 결함 의심 — {why} · 재할당·재시도로 고칠 수 없다 — 골조 변경 결정 필요"
        if st == "failed" and attempt >= MAX_ATTEMPTS:
            return CAP, f"시도 상한 도달 ({attempt}/{MAX_ATTEMPTS})"
        if st == "needs_revision":
            return CODE, f"층1·층2 지적 — 피드백 재시도 대상 (큐의 자동 재시도 후보, 시도 {attempt}/{MAX_ATTEMPTS})"
        if any(m in s for s in texts for m in CODE_MARKS):
            return CODE, f"층1·층2 지적 — terminal 로 종결됨 (시도 {attempt}/{MAX_ATTEMPTS}) · 재시도 여부는 사람 결정"
        return UNKNOWN, "분류 표지 없음 — 사람 판단 필요"

    def facts(self) -> dict:
        d = {"task_id": self.task_id, "status": self.status, "state": self.state,
             "state_label": self.state_label, "retryable": self.retryable,
             "reason": self.reason}
        if self.worker:
            d["worker"] = self.worker
        if self.attempt is not None:
            d["attempt_count"] = self.attempt
        return d


# ─────────────────────────────────────────────────────────────
# Work
# ─────────────────────────────────────────────────────────────

@dataclass
class Work:
    """분산 work 하나. `Work.load` 는 큐에서 읽고, `Work.from_record` 는 이미 읽은 dict 를 감싼다."""

    raw: dict = field(default_factory=dict)
    tasks: list = field(default_factory=list)       # [Task]

    @classmethod
    def from_record(cls, work: dict, tasks) -> "Work":
        return cls(raw=dict(work or {}), tasks=[Task(dict(t or {})) for t in (tasks or [])])

    @classmethod
    def load(cls, work_id: str, api=None, *, fetch=None) -> "Work":
        """큐에서 읽는다. 기본 호출자는 `review.fetch_work` 와 같다(`runner._api`).
        work 가 없으면 `LookupError` — 빈 work 로 접지 않는다."""
        if fetch is None:
            from . import review as _R                              # noqa: PLC0415
            fetch = _R.fetch_work
        work, tasks = fetch(work_id, api=api)
        if not work:
            raise LookupError(f"큐에 work {work_id} 가 없다")
        return cls.from_record(work, tasks)

    # ── 사실 ──
    @property
    def work_id(self) -> str:
        return str(self.raw.get("work_id") or "")

    @property
    def project(self) -> str:
        return str(self.raw.get("project") or "")

    @property
    def round(self) -> int:
        return int(self.raw.get("round", 1) or 1)

    @property
    def merge_status(self) -> str:
        return str(self.raw.get("merge_status") or "")

    @property
    def base_branch(self) -> str:
        """저장된 `target_branch` 가 이기고, 없으면 work_id 에서 유도 — `review.work_base_branch` 그대로."""
        from . import review as _R                                  # noqa: PLC0415
        return _R.work_base_branch(self.work_id, self.raw)

    def round_tasks(self, n: int | None = None) -> list:
        """라운드 `n`(기본: 지금 라운드)의 조각 — `followup._round_tasks` 와 같은 규칙."""
        w = self.raw if n is None else dict(self.raw, round=int(n))
        by_id = {id(t.raw): t for t in self.tasks}
        return [by_id[id(r)] for r in round_filter(w, [t.raw for t in self.tasks])]

    def counts(self) -> dict:
        """지금 라운드의 네 상태 수. 미상이 있으면 `미상` 키가 붙는다."""
        out = {s: 0 for s in STATES}
        for t in self.round_tasks():
            out[t.state] = out.get(t.state, 0) + 1
        return out

    def blocked(self) -> list:
        return [t for t in self.round_tasks() if t.state == FAILED]

    def running(self) -> list:
        return [t for t in self.round_tasks() if t.state == WORKING]

    def unknown(self) -> list:
        return [t for t in self.round_tasks() if t.state == UNKNOWN_STATE]

    def decide(self) -> list:
        """지금 라운드 조각마다 권고 `{task_id, state, kind, action, reason}`. **읽기 전용** —
        큐·파견에 아무것도 보내지 않는다. 실패·미상이 아닌 조각은 kind `""` · action `none`."""
        rt = self.round_tasks()
        peers = sum(1 for t in rt if t.frozen)
        out = []
        for t in rt:
            kind, why = t.classify(peers_frozen=peers)
            out.append({"task_id": t.task_id, "state": t.state, "kind": kind,
                        "action": ACTION_OF.get(kind, NONE) if kind else NONE,
                        "reason": why})
        return out
