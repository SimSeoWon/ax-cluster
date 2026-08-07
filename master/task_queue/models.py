from typing import Optional
from pydantic import BaseModel

# ─────────────────────────────────────────
# 상수
# ─────────────────────────────────────────

# verify backpressure 임계 — submitted 후 verified 까지 이 시간 내 못 가면 verify 정체로 판정.
# verify-loop 가 30s 주기라 6회 시도분. UE5 컴파일 같은 무거운 verify 가 들어가면 늘려야 함.
_VERIFY_BACKPRESSURE_SEC = 180

# 허용되는 directive (관리자가 push 가능한 명령어 화이트리스트)
_VALID_DIRECTIVES = ("abort", "pause", "resume", "drain")

_VERIFY_RESULT_TO_STATUS = {
    "pass": "verified",
    "revise": "needs_revision",
    "reject": "failed",
    "superseded": "cancelled",
}


class WorkRegisterReq(BaseModel):
    title: str
    target_repo: str
    reference_repo: str = ""
    target_branch: str = ""
    branch_isolation: bool = True
    created_branch_at: str = ""
    original_request: str = ""
    decomposition: str = ""
    max_extensions_per_work: int = 5
    slug: str = ""
    review_scheduled: str = ""
    distribution_mode: str = "pull"   # Plan v5 C.6 — pull(기본)/push. 마스터가 config 따라 설정. (전환기 플래그)
    # 동일 slug + target_repo 의 active work (merge 안 된 상태) 가 있으면
    # 기본은 거절하고 duplicates 정보 반환. 사용자가 confirm 후 True 로 재호출.
    force_duplicate: bool = False


class TaskRegisterReq(BaseModel):
    work_id: str
    type: str
    task_data: dict
    base_commit: str = ""
    target_file: str = ""
    header_file: str = ""
    depends_on: list = []
    hierarchy_level: int = 0
    priority: int = 0
    stem: str = ""
    origin: str = "master"
    parent_attempt: Optional[str] = None


class ClaimReq(BaseModel):
    worker_id: str
    # Plan v5 C.3 — 워커가 상용 모델 검증 자격(verifier_model 설정됨)을 신고. True 면 claim 이
    # verify job(submitted && author≠me && push)도 후보에 넣음. 빈값 워커는 write 전용.
    verify_capable: bool = False


class HeartbeatReq(BaseModel):
    worker_id: str


class SubmitReq(BaseModel):
    branch: str
    head_commit: str
    self_check: dict
    escalation_questions: list = []
    metrics: dict = {}
    epoch: Optional[int] = None   # Plan v5 C.2 — fencing: 배정 시 받은 epoch. stale 면 거부. (구 워커는 None)


class SubmitFailReq(BaseModel):
    reason: str
    detail: str = ""


class VerifyReq(BaseModel):
    passed: bool = True   # 하위 호환 (result 우선)
    feedback: str = ""
    result: str = ""       # "pass" | "revise" | "reject" | "superseded"
    new_base_commit: str = ""  # revise: worker 브랜치에 feedback 박은 새 HEAD
    # Plan v5 C.3 — 검증 워커가 verdict 제출 시 자기 verify lease epoch 동봉. 재배정으로
    # epoch 가 올라간 뒤 들어온 zombie 검증자의 verdict 거부(notify 게이트 fencing). 구 경로(서버
    # verify-loop)는 None — fencing skip(하위호환).
    verify_epoch: Optional[int] = None


class AdminResetReq(BaseModel):
    purge: bool = False
    cleanup_branches: bool = False


class WorkerPollReq(BaseModel):
    worker_id: str


class DirectiveReq(BaseModel):
    directive: str


class AntiPatternNotifyReq(BaseModel):
    """리더가 머지한 새 안티패턴 엔트리 알림.

    finalize_work_impl 가 머지 commit 의 .claude/recipes/_distribute_failures.md 변경을 감지하면
    호출. 서버는 audit log 에 한 줄 기록 — 이후 audit 추적 용도.
    """
    work_id: str
    repo: str = ""
    commit_sha: str = ""
    titles: list = []     # 새로 추가된 엔트리 헤더 목록 (## 제목)
    summary: str = ""     # 한 줄 요약 (선택)


class WorkPatchReq(BaseModel):
    """work 메타 부분 갱신. Phase 2 — finalize_work / auto_cleanup 가 사용.

    - merge_status: 워커 완료 후 ready_for_review (auto_cleanup), 리더 머지 후 merged (finalize_work)
    - redmine_issue_id: ready_for_review 시 자동 생성된 Redmine 이슈 번호
    - review_decision: 리더 결정 메타 (decided_at/decided_by/result/notes)
    필드는 모두 Optional — 명시된 키만 patch.
    """
    merge_status: Optional[str] = None
    redmine_issue_id: Optional[int] = None
    review_decision: Optional[dict] = None
