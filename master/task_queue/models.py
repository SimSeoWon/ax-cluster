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
# [중요] 화이트리스트인 이유: `requires` 는 등록 시점에 검증하지 않으면 오타 하나로
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
    # [중요] 프로젝트 귀속 스탬프 (#210) — 원전 데몬은 프로젝트 안에 살아 귀속이 물리적이었다.
    #    중앙 큐에서는 이 스탬프가 그 자리다: 종결 기록·신호가 활성이 아니라 **이 값**으로
    #    트윈을 푼다. 빈 값 = 옛 등록 호환 (활성으로 해석).
    project: str = ""
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
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
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
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    worker_id: str
    # Plan v5 C.3 — 워커가 상용 모델 검증 자격(verifier_model 설정됨)을 신고. True 면 claim 이
    # verify job(submitted && author≠me && push)도 후보에 넣음. 빈값 워커는 write 전용.
    verify_capable: bool = False
    # PLAN §5.2-C — 워커가 신고하는 보유 능력. **미신고(기본 빈값) = 능력 없음**이므로
    # `requires` 가 붙은 task 는 집지 못한다. 구 워커는 지금과 똑같이 동작한다(하위호환).
    capabilities: list = []
    # [중요] #204 — 유형 필터. requires 는 "이 태스크에 필요한 능력"이지 "이 워커가 다룰 줄
    #    아는 유형"이 아니다: ue5 능력을 신고한 빌드 claimer 가 requires 빈 infer 태스크를
    #    집어가면 Flow Y 파이프라인의 일감을 훔친다. None = 전 유형(하위호환, 기존 호출자).
    types: Optional[list] = None


class HeartbeatReq(BaseModel):
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    worker_id: str
    # 워커의 「지금 하는 일」 한 줄 (#220 ③) — /cluster 실시간 층이 보여 준다.
    # 로그 파일이 아니라 상태 표시다: 마지막 줄만 남고, 길이는 서버가 자른다.
    note: str = ""


class SubmitReq(BaseModel):
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    branch: str
    head_commit: str
    self_check: dict
    escalation_questions: list = []
    metrics: dict = {}
    epoch: Optional[int] = None   # Plan v5 C.2 — fencing: 배정 시 받은 epoch. stale 면 거부. (구 워커는 None)


class SubmitFailReq(BaseModel):
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    reason: str
    detail: str = ""


class VerifyReq(BaseModel):
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
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
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    worker_id: str


class DirectiveReq(BaseModel):
    directive: str


class RedmineNoteReq(BaseModel):
    """[중요] **마스터 경유 Redmine 갱신** (중 2.1 `#135`, 사용자 결정 2026-08-16).

    요청자 `.33` 의 `/review-work` 는 코멘트 **본문만** 만든다 — 우리 Redmine API 키는
    저장소에도 `~/.config` 에도 없고 마스터의 컨테이너 DB 에만 있기 때문이다(§10.1).
    [주의] 키를 `.33` 에 복사하는 대신 이 자리를 뒀다. 이 엔드포인트는 다른 것들과 같이
    **bearer 토큰이 필수**다(fail-closed).
    """
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    issue_id: int
    notes: str = ""
    status_name: str = ""      # 빈 문자열이면 상태를 안 바꾼다 (반려의 기본값)
    done_ratio: Optional[int] = None
    work_id: str = ""          # 감사 로그용 (선택)
    # [중요] 사후 스탬프 (`#303`) — 이미 만들어진 일감에 마일스톤·부모를 붙인다.
    #    [주의] 버전은 프로젝트에 속하므로 위 `project` 태그가 그 조회 대상을 정한다.
    fixed_version: str = ""
    parent_issue_id: Optional[int] = None


class RedmineIssueReq(BaseModel):
    """이슈 생성 대행 (#226 — 원전 `redmine_tracker.create_issue`·`create_review_issue`).

    [중요] **레드마인 프로젝트를 직접 받지 않는다** — 아래 `project` **태그**(`#257`)가 정하고,
    그 태그 → 레드마인 식별자 변환은 `<트윈>/config.yaml` 의 `redmine.project` 가 한다(`#293`).
    [주의] 종전 서술은 *"`ModularStage` 하나이고 새 프로젝트를 만들지 않는 것이 규칙"* 이었다.
    사용자가 정한 것은 「**AX 인프라 이슈**를 게임 프로젝트와 분리하지 않는다」(2026-08-09)이고
    「레드마인 프로젝트는 하나다」가 아니었다 — 게임 프로젝트가 늘면 그 일감의 자리도 늘어난다.
    """
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    subject: str
    description: str = ""
    tracker_name: str = ""     # 비우면 Redmine 기본 트래커
    priority_name: str = ""
    # [중요] 등재를 완결시키는 둘 (`#303`). 안 주면 무버전·부모 없음으로 떨어진다 —
    #    그 상태가 실제로 13건 쌓였다. 이름 해석 실패는 응답의 `skipped` 에 사유가 온다.
    fixed_version: str = ""            # 마일스톤 이름. 부분 일치 허용 (`마일스톤 6`)
    parent_issue_id: Optional[int] = None


class RedmineLinkCommitReq(BaseModel):
    """커밋 해시 연결 (#226 — 원전과 같은 노트 문구 형식을 서버가 만든다)."""
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    issue_id: int
    commit_hash: str
    message: str = ""


class WriterSignalReq(BaseModel):
    """code-writer 신호 (#206) — 원전 `log_writer_signal` 인자 그대로.

    신호 파일(`recipes/_signals.jsonl`)은 마스터의 트윈 디렉토리에 있으므로 요청자(`.33`)는
    본문만 만들고 이 자리를 부른다 — `redmine/note` 와 같은 마스터 대행 구조다.
    [중요] 저장하는 것은 코드가 아니라 **작업 과정**이다 (intent·검색·읽은/고친 파일·피드백·
    거절·에러 복구). 서술 속 코드 식별자는 [대괄호]로 감싼다 (원전 규약).
    """
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    intent: str
    queries: list = []
    files_read: list = []
    files_modified: list = []          # [{"path": ..., "summary": ...}]
    iterations: int = 1
    feedback_notes: str = ""
    rejected_approaches: list = []     # [{"approach": ..., "reason": ...}]
    error_recoveries: list = []        # [{"error": 증상, "fix": 해결}]
    session_id: str = ""
    work_id: str = ""


class HistoryReq(BaseModel):
    """작업 기록 (#207) — 원전 α′ frontmatter 규약의 요청자 자리.

    비자명한 의사결정·아키텍처 변경 직후 요청자(`.33`) 세션이 부른다 (trivial 은 안 쓴다 —
    원전 규약 그대로). history 파일은 마스터의 트윈 디렉토리에 있으므로 마스터가 대행한다.
    파이프라인 종결 기록은 큐가 자동으로 남기므로 이 자리를 지나지 않는다.
    """
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    title: str
    decision_type: str = "feature"     # 원전 enum + feature (history_gen.DECISION_TYPES)
    body: str = ""                     # 본문 구조는 자유 — frontmatter 만 의무 (원전 규약)
    work_id: str = ""
    session_id: str = ""
    affected_classes: list = []        # CamelCase 식별자만
    affected_domains: list = []
    supersedes: str = ""               # 이전 결정을 뒤집을 때만 (drift 추적용)
    alternatives_considered: list = [] # 검토했으나 채택 안 한 옵션 (negative knowledge)
    tags: list = []
    user_quote: str = ""               # 사용자 직접 발화 1~3줄 — WHY 신호, 본문보다 강함


class AliasReq(BaseModel):
    """[중요] **별칭 등록 대행** (2026-08-20) — 원전 `add_object_alias` 의 자리.

    별칭은 온톨로지 yaml(없는 클래스는 폴백 저장소)에 쓰이고 그 파일은 **마스터에만** 있다.
    [중요] 범용어 가드(#213: 4자 미만 · 정확 구 DF 2.5% 초과 거부)는 `thesaurus.register`
    **안**에 있어서 이 경로도 그것을 탄다 — 가드를 우회하는 두 번째 입구를 만들지 않는 것이
    이 자리를 8103 이 아니라 여기(토큰 잠김 큐)에 둔 이유다. 8103 의 `/api/v1/*` 는
    **무인증 공개**다(실측 2026-08-20: 토큰 없이 200) — 쓰기가 갈 자리가 아니다.
    """
    class_name: str
    term: str
    project: str = ""          # 비면 활성. 요청자 config 는 project 를 알므로 보통 채워 보낸다


class NotAClassReq(BaseModel):
    """`그건 클래스가 아니다` 를 기억한다 — 원전 `mark_not_a_class` 의 자리.

    [중요] 별칭 등록과 **같은 대화의 반쪽**이다. 기록하지 않으면 `[완료]` 같은 상태어를
    매번 다시 묻게 되고, 그러면 사람이 이 기능을 꺼 버린다(원전이 그렇게 기록해 뒀다).
    """
    term: str
    project: str = ""


class AntiPatternNotifyReq(BaseModel):
    """리더가 머지한 새 안티패턴 엔트리 알림.

    finalize_work_impl 가 머지 commit 의 .claude/recipes/_distribute_failures.md 변경을 감지하면
    호출. 서버는 audit log 에 한 줄 기록 — 이후 audit 추적 용도.
    """
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
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
    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다 — 정책은
    #    `tagging.POLICY` 가 라우트별로 선언한다(MOUNT 는 거부, STAMP 는 대조).
    project: str = ""
    merge_status: Optional[str] = None
    redmine_issue_id: Optional[int] = None
    review_decision: Optional[dict] = None


class RecipeSearchReq(BaseModel):
    """레시피 검색 (`#267`). [중요] **질의를 본문으로 받는다 — URL 에 한글을 넣지 않는다**
    (사용자 지적 2026-08-23). 이 저장소 관례가 이미 본문이다(`search/combined`)."""

    # [중요] 어느 프로젝트의 요청인가 (#257). 비면 마운트로 해석한다.
    project: str = ""
    query: str
    n: int = 3
