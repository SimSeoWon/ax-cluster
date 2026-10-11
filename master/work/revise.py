"""🔴 **상한 있는 재시도** — 층1 이 막은 조각에 「고칠 기회」를 준다 (`#388` · 원전 이식).

## [중요] 이것은 새 계층이 아니다 — 원전에 있는데 우리가 안 옮긴 것이다

    ~/AgentTest/mcp/master_orchestrator/verifier.py:55
      _DEFAULT_MAX_ATTEMPTS = 3
      _classify_verify_issues(issues, attempt_count, max_attempts) → pass/revise/reject

원전 독스트링이 **우리의 종전 상태를 그대로 서술한다**:

    "이전엔 「마크다운 펜스/영어 prose/0줄」 만나자마자 reject(=terminal failed) 로 즉시
     종료 → **워커가 feedback 받아 고칠 기회조차 없었음.** 정책 전환: 모든 issue 는 기본
     **revise** … attempt_count >= max_attempts (기본 3) 도달 시에만 reject 로 escalate."

즉 **원전도 한때 우리와 같았고 2026-05-10 에 고쳤다.** 우리는 그 고침 이전 상태를 이식했다.
더 결정적으로 `verifier.py:396~432` 는 **우리 실패 케이스를 이름으로** 다룬다:
*"PSEUDO 있었는데 변경 없음 — 워커가 [PSEUDO] 마커를 놔둔 채 종료한 case. 재시도 가능하면
revise, max 이상이면 reject."*

## [중요] 배관은 이미 있었다 — 판정만 없었다

    models.py:36        `revise` → `needs_revision`          이식돼 있었다
    logic_claim.py:162  클레임 후보 = pending + needs_revision  이식돼 있었다
    🔴 그런데 `needs_revision` 을 **만드는 코드가 0건**이었다

층1 은 마스터 `wcommit` 안에서 돈다 — **위치는 원전 ①(워커 디스크 검증)인데 하는 일은
원전 ②(검증 워커의 diff 검사)** 다. 그래서 ①의 정책(즉시 종료)을 물려받았다.
`infer.py` 가 `submit_fail(BLOCKED)` 로 직행했고 `submit_fail` 은 `quota_exhausted` 만
살려 준다. **검사를 앞으로 옮기면서 「고칠 기회를 준다」는 정책을 같이 안 옮긴 것이다.**

## [중요] 피드백은 **파일 안에** 실린다 — 메시지가 아니다

원전 `_embed_feedback_in_worker_branch` 가 하는 일을 그대로 한다: 사유를 대상 파일 맨 위에
주석으로 박고 **커밋·push** 한다. 그래서

  - **다른 기계**가 그 조각을 집어도 지시가 따라간다 (`.2` 가 실패한 것을 `.43` 이 받아도 보인다)
  - 마스터가 「누구에게 뭘 말해줬는지」를 기억할 필요가 없다 — git 이 나른다
  - 다음 시도의 워커는 파일을 여는 순간 그것을 읽는다

[주의] **피드백 없는 재시도는 반쪽이다** — 같은 실수를 반복할 뿐이고, 원전이 그 함수를 만든
이유가 정확히 그것이다.

## [주의] 원전과 갈린 자리 하나 — 붙일 커밋이 없다

원전은 **워커가 attempt 를 push 한 뒤** 그 브랜치에 피드백을 얹는다. 우리 층1 은 **커밋 전**에
막으므로 서브 브랜치가 base 그대로다(실측: 조각 `f4db3ad4` 의 서브 브랜치 = base `e37b8ece`).
→ 우리는 **마스터 미러에 worktree 를 세워 피드백 커밋을 만든다.** 그 커밋이 서브 브랜치의
첫 커밋이 되고, 다음 파견의 워커가 그 위에서 시작한다. `subbranch.create` 가 *"얹을 내용이
없어 ref 만 세운다"* 고 적은 그 자리에, **처음으로 얹을 내용이 생긴 것**이다.

## [주의] 원전과 갈린 자리 둘 — 의도한 것이고, 근거를 적는다

**⑴ 피드백을 대상 파일 *전부*에 박는다.** 원전은 `target_file or header_file` **하나**에만
얹는다. 우리는 조각의 `want` 전부에 얹는다 — 워커가 `.h` 를 먼저 열었을 때 아무것도 못 보는
경우를 없애기 위해서다. 블록 내용은 **양쪽이 같다**(이슈 전체 목록)이므로 어느 쪽을 열어도
할 일이 전부 보인다. [주의] 선언 동결과 충돌하지 않는다 — 층1 이 보는 것은 **선언**이고
앞머리 주석은 선언이 아니다(테스트 `[5]` 가 본문 보존을 잰다).

**⑵ 판정 자리가 `verify` 가 아니라 `submit-fail` 이다.** 원전은 워커가 attempt 를 push 한
**뒤** 검증 워커가 verdict 를 낸다(그때 상태가 `submitted`). 우리 층1 은 **커밋 전**에 막으므로
그 시점 상태가 `claimed` 이고 `verify_task` 는 `submitted` 만 받는다. 그래서 이미 같은 두
게이트(epoch fencing · `#318` 신원)를 갖고 있는 `submit_fail` 에 갈래를 넣었다 — 새 엔드포인트를
만들면 그 게이트를 **한 벌 더** 짜야 하고, 그것이 조용히 갈라지는 것이 이 저장소가 물린 유형이다.

## [중요] 상한은 협상 대상이 아니다

리포트 51 이 「하루 종일 헛돌던 고리」였다. 같은 모양이 이미 저장소에 있다 —
`master/context_synth/pending.py` 의 `MAX_ATTEMPTS = 3`, *"상한이 있는 재시도"*.
원전 값과 같다. **무한 재시도는 만들지 않는다.**
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import branch_names
from .attempt import WRITE_REMOTE, GitError, _git
from .attempt import guard_or_reason as _guard_or_reason
from .coordinator import _git_rc

# 🔴 원전 `_DEFAULT_MAX_ATTEMPTS` 와 같은 값이다. 바꾸려면 원전 근거부터 바꾼다.
MAX_ATTEMPTS = 3

PASS, REVISE, REJECT = "pass", "revise", "reject"

# [중요] 주석 여는 줄은 **판정 표식**이다 — 다음 시도에서 이전 잔재를 걷어낼 때 이것으로 찾는다.
#    원전과 같은 문자열을 쓴다(`/* AUTO-VERIFY FEEDBACK`).
FEEDBACK_OPEN = "/* AUTO-VERIFY FEEDBACK"
FEEDBACK_CLOSE = "*/"
# 🔴 [중요] **`.py` 는 C 주석을 못 쓴다** (`#806`, 실측 2026-10-11 — `SyntaxError: invalid
#    character '—'`). 원전은 UE5/C++ 만 받아서 C 모양 하나였다. `#695` 로 `.py` 조각이 생겨
#    확장자로 고른다 — `.py` 는 `#` 줄 주석 블록, 나머지는 원전 모양 그대로다.
PY_FEEDBACK_OPEN = "# AUTO-VERIFY FEEDBACK"
PY_FEEDBACK_CLOSE = "# END AUTO-VERIFY FEEDBACK"
# [중요] 피드백 커밋의 제목 접두어 — **워커에게 가는 지시**이지 결과가 아니다. 재작업 통합
#    (`review.integrate_durables(rework=True)`)이 이 접두어로 결과 커밋과 가른다(#805).
#    만드는 곳(`embed_feedback`)과 가르는 곳이 이 상수 하나를 쓴다.
FEEDBACK_COMMIT_PREFIX = "[revise] "


# 🔴 **실행 환경이 죽은 신호** (`#391` 완결 · 실측 2026-09-12) ─────────────────────────
#
# [중요] **환경 실패를 코드 실패로 읽으면 상한을 태운다.** `#391` 이 이미 적어 둔 것이
# 그대로 재현됐다 — *"실패의 「받을 곳」이 셋인데 갈래가 둘뿐이라 환경 실패가 코드 실패로
# 위장돼 상한 3회를 태웠다"*. 2026-09-12 실물: `.2` 의 codex 가 SSH(세션 0)에서
# `ax-work` SKILL.md 조차 못 읽고(`0xC0000142`) 계약 없이 본문을 썼고, 층1 이 `[PSEUDO]`
# 잔재로 막았다. 시스템은 그것을 「코드를 덜 썼다」로 읽고 **세 번 더 태웠다.**
#
# [중요] **피드백으로 고칠 수 없는 실패다.** 워커에게 *"[PSEUDO] 를 채워라"* 를 다시 보내도
# 그 기계에서는 스킬을 읽을 수 없다. 재시도는 토큰만 쓴다 — 그래서 **첫 번째에 멈춘다.**
# [주의] 판정 근거는 **지휘자가 자기 입으로 한 말**이다(`#391` 이 남기게 만든 그 출력).
#    새 신호를 지어내지 않는다.
ENV_MARKERS = (
    "0xC0000142",          # DLL 초기화 실패 — Windows Session 0 에서 샌드박스 자식이 죽는다
    "-1073741502",         # 같은 값의 10진 표현 (`exit_code` 필드에 이렇게 찍힌다)
    "CreateProcessAsUserW failed",
    "connecting runner pipe-in",   # elevated runner 가 세션 9 파이프를 못 잡을 때
)

# 🔴 **자원이 떨어진 신호** (사용자 지적 2026-09-12: *"토큰 부족이라던지 하는 상황에도
# 동일한 배선이 필요해보여"*) ────────────────────────────────────────────────────
#
# [중요] **환경 실패와 같은 부류다** — 코드 실패가 아니고, 재시도하면 **한도를 더 태운다.**
# 실측 2026-09-04(`lanes.py` 머리말): *"`429 You've hit your session limit` 을 맞자 4조각 중
# 3이 동시에 죽고 라운드가 02:30 까지 보류됐다"* — 한도가 **공용 자원**이라 그렇다.
#
# 🔴 [중요] **환경 실패와 다른 점 하나: 조각을 죽이지 않는다.** 다른 워커는 멀쩡할 수 있으므로
# `pending` 으로 되돌려 남이 집게 한다. 큐가 이미 그 동작을 갖고 있다 —
# `logic_lifecycle.py:196` 이 `reason == "quota_exhausted"` 를 받으면 `pending` 으로 되돌리고
# 그 워커를 **5시간 차단**한다(`quota_blocked_workers`).
#
# 🔴 [주의] **그런데 그 사유를 아무도 보내지 않고 있었다** — 배관은 있는데 만드는 코드가
# 0건이었다. `#388` 이 `needs_revision` 에서 겪은 것과 **같은 병**이고, `revise.py` 주석이
# 그 사실을 적어 두기까지 했다. 이 상수가 그 빈 칸을 메운다.
QUOTA_MARKERS = (
    "429",                          # HTTP 상태 — claude/codex 공통
    "session limit",                # `You've hit your session limit`
    "usage limit",
    "rate limit",
    "quota",
    "insufficient_quota",
)

QUOTA = "quota"            # 다섯 번째 갈래 — 죽이지 않고 **다른 워커에게 넘긴다**


def quota_exhausted(texts) -> str:
    """지휘자 출력에서 **자원이 떨어진 증거**를 찾는다. 없으면 빈 문자열.

    [주의] `429` 는 흔한 숫자라 오탐이 날 수 있다 — 그래서 **`\"429\"` 로 굳어진 형태**나
    상태 코드 문맥만 본다. 나머지 표지는 문구 자체가 충분히 특정적이다.
    """
    for t in texts or ():
        s = str(t or "")
        low = s.lower()
        for m in QUOTA_MARKERS:
            if m == "429":
                if "429" in s and any(k in low for k in ("limit", "quota", "too many", "retry")):
                    return "429"
                continue
            if m in low:
                return m
    return ""


ENV = "environment"        # `pass`/`revise`/`reject` 와 나란한 네 번째 갈래


AUTH_MARKERS = (
    "AX_CLAUDE_AUTH_FAILED",
    "Failed to authenticate: OAuth session expired and could not be refreshed",
)


def authentication_failure(texts) -> str:
    """AX 사전 검사 표식과 실제 Claude OAuth 만료 오류만 판정한다."""
    for text in texts or ():
        for marker in AUTH_MARKERS:
            if marker in str(text or ""):
                return marker
    return ""


def environment_failure(texts) -> str:
    """지휘자 출력에서 **실행 환경이 죽은 증거**를 찾는다. 없으면 빈 문자열.

    [중요] **텍스트 매칭이다** — 이 값들은 OS·codex 가 내는 고정 문자열이고, 우리가 만드는
    것이 아니다. 다른 신호를 지어내지 않는다.
    """
    for t in texts or ():
        s = str(t or "")
        for m in ENV_MARKERS:
            if m in s:
                return m
    return ""


# 🔴 **출력이 직전 시도와 같으면 재시도는 무의미하다** (`#615` · 사용자 결정 2026-10-03 (가)) ──
#
# [DOC] 실측 2026-09-12(`#401` 라운드 1·2): 지휘자가 승인을 요구하며 `RESULT: BLOCKED` 했고,
#    **세 시도의 출력이 글자도 토큰 수도 동일**했다 — 조각 2건 × 3시도 = 6회를 같은 거절에 썼다.
#    한도(QUOTA)·환경(ENV) 어느 갈래에도 안 걸려 `classify` 로 떨어졌기 때문이다.
# [DOC] 원인 표지 목록을 두지 않는다(그건 (나)안 — 기각). 원인과 무관하게 「직전과 같은 출력」
#    하나로 멈춘다. 다음에 올 다른 종류의 거절에도 같은 규칙이 듣는다.
# [DOC] 지문은 큐가 이미 저장하는 `last_feedback`(submit_fail detail 의 앞 600자, revise 일 때만)
#    에 실려 다음 시도로 넘어간다 — 큐 스키마를 바꾸지 않는다. 형식은 `FP_PREFIX` + 12 hex + `]`.
FP_PREFIX = "[fp:"
REPEAT = "repeat"          # 여섯 번째 갈래 — 같은 출력의 반복이다. 재시도하지 않고 종결한다


def output_fingerprint(texts) -> str:
    """지휘자 출력의 지문 — 정규화한 본문의 sha256 앞 12자리. 출력이 비면 빈 문자열.

    [DOC] 정규화: 각 항목을 str 로 바꾸고 공백 연속을 한 칸으로 접어 앞뒤를 다듬은 뒤, 빈 항목을
       버리고 줄바꿈으로 잇는다. 남은 것이 없으면 `""` — **빈 출력은 비교하지 않는다**(지문 없음 =
       판정 안 함). 같은 글자의 출력은 언제나 같은 지문이어야 한다.
    """
    parts = [" ".join(str(t if t is not None else "").split()) for t in (texts or ())]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def repeated_output(prev_feedback: str, fp: str) -> bool:
    """직전 시도의 `last_feedback` 에 **같은 지문**이 실려 있는가.

    [DOC] `fp` 가 비면 False(판정 안 함). `prev_feedback` 이 `FP_PREFIX` 로 시작하고 그 뒤 12자가
       `fp` 와 같을 때만 True. 지문이 없는 옛 피드백·형식이 다른 문자열은 False — 모르는 것을
       반복으로 접지 않는다.
    """
    prev = str(prev_feedback or "")
    if not fp or not prev.startswith(FP_PREFIX):
        return False
    start = len(FP_PREFIX)
    return prev[start:start + 12] == fp and prev[start + 12:start + 13] == "]"


def tag_detail(detail: str, fp: str, limit: int = 500) -> str:
    """submit_fail detail 앞에 지문을 붙인다 — `[fp:<12hex>] ` + 요약(최대 `limit` 자).

    [DOC] 서버는 detail 의 **앞 600자**를 `last_feedback` 으로, 러너는 **뒤 2000자**를 보낸다.
       요약을 `limit`(500) 자로 잘라 둘 다에서 지문이 살아남게 한다. `fp` 가 비면 detail 을
       그대로 돌려준다(자르지도 않는다 — 종전 동작).
    """
    if not fp:
        return detail
    return f"{FP_PREFIX}{fp}] " + str(detail or "")[:limit]


def classify(issues, attempt_count: int = 1, max_attempts: int = MAX_ATTEMPTS) -> str:
    """이슈 목록 → `pass` / `revise` / `reject`. **원전 `_classify_verify_issues` 이식.**

    [중요] **기본이 `revise` 다.** 이슈가 있다고 곧바로 죽이지 않는다 — 층1 이 내는 사유는
    *"[PSEUDO] 가 남았다"* 처럼 **명시하면 고칠 수 있는** 것들이다.
    [중요] `pass` 는 이슈가 **비었을 때만**이다. 모르는 것을 통과로 접지 않는다.
    """
    if not issues:
        return PASS
    if int(attempt_count or 0) >= int(max_attempts or MAX_ATTEMPTS):
        return REJECT
    return REVISE


def strip_feedback(text: str) -> str:
    """이전 시도가 박아 둔 피드백 블록을 걷는다(C 모양·`#` 모양 둘 다). 없으면 그대로 돌려준다.

    [주의] **누적되면 파일이 피드백으로 뒤덮인다** — 원전이 같은 자리에서 같은 일을 한다.
    """
    s = (text or "").lstrip()
    if s.startswith(PY_FEEDBACK_OPEN):
        # [중요] 여는 줄부터 END 줄까지만 걷는다 — 뒤따르는 일반 주석은 본문이다.
        lines = s.splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if ln.strip() == PY_FEEDBACK_CLOSE:
                return "".join(lines[i + 1:]).lstrip()
            if not ln.lstrip().startswith("#"):
                break               # END 전에 주석 아닌 줄 — 잘린 블록이다
        # [주의] END 줄이 없다 — 잘린 파일이다. 손대지 않는다(C 모양과 같은 규칙).
        return text
    if not s.startswith(FEEDBACK_OPEN):
        return text
    end = s.find(FEEDBACK_CLOSE)
    if end < 0:
        # [주의] 여는 줄만 있고 닫는 줄이 없다 — 잘린 파일이다. 손대지 않고 그대로 둔다
        #    (여기서 지우면 본문까지 날아갈 수 있다).
        return text
    return s[end + len(FEEDBACK_CLOSE):].lstrip()


def build_block(issues, attempt: int, path: str = "") -> str:
    """피드백 주석 블록. 기본은 **원전과 같은 모양**(`/* AUTO-VERIFY FEEDBACK (attempt #N) …`).

    `path` 가 `.py` 면 `#` 줄 주석 블록이다(`#806`). 이슈는 한 줄로 접으므로 블록을 깨지 못한다.
    """
    head = (f"(attempt #{int(attempt)}) — address ALL items and "
            f"REMOVE this block before next submit:")
    ones = [" ".join(str(iss).split()) for iss in issues]
    if str(path or "").lower().endswith(".py"):
        return "\n".join([f"{PY_FEEDBACK_OPEN} {head}"]
                         + [f"# - {one}" for one in ones] + [PY_FEEDBACK_CLOSE])
    lines = [f"{FEEDBACK_OPEN} {head}"]
    for one in ones:
        lines.append(f" * - {one}")
    lines.append(f" {FEEDBACK_CLOSE}")
    return "\n".join(lines)


@dataclass
class Embedded:
    task_id: str = ""
    branch: str = ""
    head: str = ""                                  # 피드백 커밋
    files: list = field(default_factory=list)       # 실제로 박은 파일
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.head) and not self.error


def embed(paths, work_id: str, task_id: str, *, issues, attempt: int, targets,
          round_no: int = 0, remote: str = WRITE_REMOTE, logf=None,
          git=None, git_rc=None) -> Embedded:
    """피드백을 서브 브랜치의 대상 파일에 박아 커밋·push 한다.

    `targets` 는 `[상대경로, …]` 다 — 층1 위반이 난 파일들. 하나도 못 찾으면 실패로 돌려준다
    (**조용히 성공으로 접지 않는다**).

    [중요] **worktree 로 격리한다** — 마스터의 작업 트리를 건드리면 다른 작업이 물린다.
    [주의] `git`·`git_rc` 주입은 테스트 자리다. 실 저장소를 두드리지 않게 한다.
    """
    log = logf or (lambda m: None)
    g, grc = (git or _git), (git_rc or _git_rc)
    e = Embedded(task_id=task_id)
    try:
        e.branch = branch_names.durable_branch(work_id, task_id, round_no)
    except branch_names.BranchNameError as ex:
        e.error = str(ex)
        return e

    rel = [str(t).strip() for t in (targets or []) if str(t).strip()]
    if not rel:
        e.error = "피드백을 박을 대상 파일이 없다 — 어디에 남길지 모른 채 커밋하지 않는다"
        return e
    if not issues:
        e.error = "피드백 내용이 비었다 — 빈 주석을 커밋하지 않는다"
        return e

    # [주의] **push 하기 전에 쓰기 가드를 확인한다** (`#329`) — `subbranch.create` 와 같은 자리다.
    guard = _guard_or_reason(paths)
    if guard:
        e.error = guard
        return e

    repo = Path(paths.repo)
    wt = repo.parent / f".revise-{task_id[:8]}"
    rc, _out = grc(repo, "worktree", "remove", "--force", str(wt))    # 잔재 정리 (없으면 rc≠0, 무시)
    rc, out = grc(repo, "fetch", remote, f"+refs/heads/{e.branch}:refs/ax/revise/{task_id}")
    if rc != 0:
        e.error = f"서브 브랜치를 가져오지 못했다 ({e.branch}) — {out[:200]}"
        return e
    rc, out = grc(repo, "worktree", "add", "--detach", str(wt), f"refs/ax/revise/{task_id}")
    if rc != 0:
        e.error = f"worktree 를 세우지 못했다 — {out[:200]}"
        return e

    try:
        for r in rel:
            p = wt / r
            if not p.exists():
                # [주의] 조용히 넘기지 않는다 — 어느 파일을 못 찾았는지 남긴다.
                log(f"[revise] [주의] {task_id} 대상 없음 — {r}")
                continue
            block = build_block(issues, attempt, r)     # 파일마다 그 언어의 주석 모양
            body = strip_feedback(p.read_text(encoding="utf-8", errors="replace"))
            p.write_text(block + "\n\n" + body, encoding="utf-8")
            e.files.append(r)
        if not e.files:
            e.error = f"대상 파일을 하나도 못 찾았다 — {', '.join(rel)}"
            return e

        for r in e.files:
            rc, out = grc(wt, "add", "--", r)
            if rc != 0:
                e.error = f"스테이징 실패 ({r}) — {out[:200]}"
                return e
        rc, out = grc(wt, "commit", "-m",
                      f"{FEEDBACK_COMMIT_PREFIX}{task_id} attempt #{int(attempt)} 피드백 — 층1 이 막은 사유를 싣는다")
        if rc != 0:
            # [주의] **문구로 판정하지 않는다** (이 기계는 ko_KR 이라 git 메시지가 번역된다).
            #    rc≠0 이면 그대로 사유로 낸다.
            e.error = f"커밋 실패 — {out[:200]}"
            return e
        rc, out = grc(wt, "push", remote, f"HEAD:refs/heads/{e.branch}")
        if rc != 0:
            e.error = f"push 실패 ({e.branch}) — {out[:200]}"
            return e
        e.head = g(wt, "rev-parse", "HEAD")
        log(f"[revise] {task_id} 피드백을 {e.branch} 에 실었다 "
            f"(attempt #{int(attempt)} · 파일 {len(e.files)} · {e.head[:8]})")
        return e
    except (GitError, OSError) as ex:
        e.error = f"{type(ex).__name__}: {ex}"
        return e
    finally:
        grc(repo, "worktree", "remove", "--force", str(wt))
