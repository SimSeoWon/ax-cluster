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

# PLAN §5.2-C — 능력 기반 라우팅. task 의 `requires` 와 워커가 claim 시 신고하는
# `capabilities` 를 **부분집합 매칭**한다 (requires ⊆ capabilities 여야 claim 가능).
#
# 🔴 화이트리스트인 이유: `requires` 는 등록 시점에 검증하지 않으면 오타 하나로
# **아무 워커도 만족시킬 수 없는 task** 가 되어 영구 pending 으로 굶는다. 조용한 기아보다
# 등록 실패가 낫다. 새 능력이 필요하면 여기 한 줄 추가하는 것이 정상 경로다.
_KNOWN_CAPABILITIES = (
    "ue5",       # UE5 에디터 + 빌드 툴체인 보유 (윈도우 작업장 2대). 층3 빌드 게이트·커맨드릿
    "windows",   # 윈도우 전용 실행물(.bat/.ps1 등)이 필요한 잡
)


def normalize_capabilities(values) -> list[str]:
    """능력 태그 정규화 — 소문자·공백제거·빈값제거·중복제거(정렬)."""
    if not values:
        return []
    out = {str(v).strip().lower() for v in values}
    return sorted(v for v in out if v)

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
    # PLAN §5.2-C — 이 task 를 실행하려면 워커가 갖춰야 하는 능력. 빈 리스트 = 아무나.
    # `_KNOWN_CAPABILITIES` 밖의 값은 등록 자체를 거부한다(오타 → 영구 기아 방지).
    requires: list = []


class ClaimReq(BaseModel):
    worker_id: str
    # Plan v5 C.3 — 워커가 상용 모델 검증 자격(verifier_model 설정됨)을 신고. True 면 claim 이
    # verify job(submitted && author≠me && push)도 후보에 넣음. 빈값 워커는 write 전용.
    verify_capable: bool = False
    # PLAN §5.2-C — 워커가 신고하는 보유 능력. **미신고(기본 빈값) = 능력 없음**이므로
    # `requires` 가 붙은 task 는 집지 못한다. 구 워커는 지금과 똑같이 동작한다(하위호환).
    capabilities: list = []


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
