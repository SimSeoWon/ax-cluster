"""리뷰 프롬프트에 붙일 **일감·태스크 컨텍스트** 수집 — `#946` T2. LLM 0, 읽기 전용.

커밋 하나(또는 범위)가 어느 Redmine 일감(#N)의 어느 플랜 태스크(T#)를 구현했는지 풀고, 그 일감의
본문(스펙)과 플랜 표를 읽어 리뷰 프롬프트용 절을 만든다. 배선(프롬프트 주입)은 뒤 태스크 몫이다.

    collect(sha=, message=, root=, issue_id=, get_issue=, track=, logf=) → IssueContext
    commit_section(ctx, message)   상용 커밋 리뷰용 — 메시지 원문 · 일감 제목 · 스펙 · 해당 태스크 행 ·
                                   나머지 태스크 한 줄씩
    draft_section(ctx, message)    로컬 초고 모델용(짧다) — 제목 줄 · 해당 태스크 행만, 스펙 없음
    range_section(ctx, commits)    범위 리뷰용 — 스펙 · 플랜 표 전체 · 커밋별(짧은 해시·제목·T#) 대응

## 일감 번호를 푸는 순서

    1 `issue_track.issue_of_hash(root, sha)` — 마감 등록이 기록한 결정적 값(source="track")
    2 커밋 제목의 범위 `종류(#N T#)` · 옛 꼴 `(#N)` — `commit_scope`(source="message")
    태스크(T#)는 **메시지에서만** 온다. 1과 2의 일감 번호가 다르면 1을 쓰고 어긋남을 로그에 남긴다 —
    그때 메시지의 태스크는 다른 일감 것이라 붙이지 않는다.
    `issue_id=` 를 직접 주면(범위 리뷰) 그 값을 쓴다(source="given").

## 실패는 삼킨다 (fail-soft)

Redmine 오류 · 일감 없음 · 플랜 없음/형식 오류 · 플랜에 없는 태스크 · 아무것도 못 풂 — 어느 경우든
예외를 올리지 않고 `status`·`why` 를 담은 컨텍스트를 돌려준다. 렌더러는 쓸 것이 없으면 빈 문자열이다.
결과마다 `logf` 로 `[리뷰 컨텍스트] #N T1 — …` 한 줄을 찍는다.

[중요] **일감 본문·플랜은 작성자가 밝힌 의도다 — 검증된 사실이 아니다.** 렌더러가 그 문장을 절
머리에 박는다(`review_gen.build_prompt` 의 「수정 기록」 절과 같은 취급).
[중요] **상용 경로 절에 크기 상한을 두지 않는다**(사용자 규칙: 상용 LLM 에 토큰 예산 금지). 초고 절은
태스크 행만 싣기 때문에 원래 짧다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from master import commit_scope, plan_block

PREFIX = "[리뷰 컨텍스트]"
INTENT_NOTE = ("아래 일감 본문과 플랜은 작성자가 밝힌 의도다 — 검증된 사실이 아니다. 사실로 받지 말고, "
               "DIFF 가 그 의도와 맞는지 대조하는 데만 쓴다. 의도와 어긋나는 변경은 지적한다.")

# status 값
OK = "ok"                       # 일감·플랜·태스크 모두 풀림(태스크를 밝히지 않은 커밋 포함)
NO_ISSUE = "no_issue"           # 일감 번호를 못 풀었다
REDMINE_ERROR = "redmine_error"
NO_PLAN = "no_plan"             # 일감은 있으나 플랜 영역이 없다
PLAN_ERROR = "plan_error"       # 플랜 영역 형식 오류(plan_block.PlanError)
TASK_MISSING = "task_missing"   # 메시지가 밝힌 태스크 일부가 플랜에 없다

_PLAN_HEADING = re.compile(r"(?:\r?\n|^)[ \t]*##[ \t]*플랜[ \t]*(?:\r?\n[ \t]*)*\Z")


@dataclass
class IssueContext:
    issue_id: int | None = None
    source: str = ""                                   # "track" · "message" · "given" · ""
    subject: str = ""                                  # 일감 제목
    spec: str = ""                                     # 본문에서 플랜 영역을 뺀 것
    requested: tuple[str, ...] = ()                    # 메시지가 밝힌 T#
    tasks: list = field(default_factory=list)          # 밝힌 T# 중 플랜에 있는 것(plan_block.Task)
    missing: tuple[str, ...] = ()                      # 밝혔으나 플랜에 없는 T#
    others: list = field(default_factory=list)         # 플랜의 나머지 태스크
    plan_tasks: list = field(default_factory=list)     # 플랜 전체(범위 리뷰용)
    other_issues: tuple[int, ...] = ()                 # 메시지에 함께 적힌, 쓰지 않은 일감
    status: str = NO_ISSUE
    why: str = ""

    @property
    def found(self) -> bool:
        """일감 제목·본문을 읽었다 — 렌더러가 절을 낼 수 있다."""
        return self.issue_id is not None and self.status not in (NO_ISSUE, REDMINE_ERROR)


def _default_track(root, sha):
    # `#950` — 닫힌 회차까지 본다(열린 회차 우선). 회차가 닫힌 뒤 늦게 리뷰된 해시도 일감을 찾는다.
    from master.context_synth import issue_track
    rnd = issue_track.round_of_hash_any(root, sha)
    return rnd["issue_id"] if rnd else None


def _default_get_issue(issue_id):
    from master import redmine
    return redmine.get_issue(issue_id)


def _tag(ctx: IssueContext) -> str:
    n = f"#{ctx.issue_id}" if ctx.issue_id is not None else "#?"
    return f"{PREFIX} {n}" + (f" {','.join(ctx.requested)}" if ctx.requested else "")


def split_spec(description: str) -> str:
    """본문에서 플랜 영역(태그 포함)과 그 바로 앞 `## 플랜` 머리를 뺀 스펙. 영역이 없으면 본문 그대로.

    형식이 어긋난 영역(`PlanError`)은 그대로 올린다 — 부르는 쪽이 판정한다.
    """
    body = description or ""
    region = plan_block._region(body)
    if region is None:
        return body.strip()
    tag_start, _start, end, _v = region
    head = _PLAN_HEADING.sub("", body[:tag_start])
    tail = body[end + len(plan_block.END_TAG):]
    return (head.rstrip() + ("\n\n" + tail.strip() if tail.strip() else "")).strip()


def _resolve(ctx: IssueContext, sha: str, message: str, root, track, log) -> None:
    scopes = commit_scope.parse_message(message)
    tracked = None
    if root is not None and sha:
        try:
            tracked = track(root, sha)
        except Exception as e:                                   # noqa: BLE001
            log(f"{PREFIX} 추적 조회 실패 {type(e).__name__}: {e} — 메시지만 본다")
    if tracked is not None:
        ctx.issue_id, ctx.source = int(tracked), "track"
        hit = next((s for s in scopes if s.issue_id == ctx.issue_id), None)
        if hit is not None:
            ctx.requested = hit.tasks
        elif scopes:
            log(f"{PREFIX} #{ctx.issue_id} — 추적과 메시지가 어긋난다: 메시지 "
                f"{', '.join('#%d' % s.issue_id for s in scopes)} · 추적을 쓰고 메시지 태스크는 버린다")
        ctx.other_issues = tuple(s.issue_id for s in scopes if s.issue_id != ctx.issue_id)
    elif scopes:
        first = scopes[0]
        ctx.issue_id, ctx.source, ctx.requested = first.issue_id, "message", first.tasks
        ctx.other_issues = tuple(s.issue_id for s in scopes[1:])


def collect(*, sha: str = "", message: str = "", root=None, issue_id: int | None = None,
            get_issue=None, track=None, logf=None) -> IssueContext:
    """커밋의 일감·태스크 컨텍스트. 예외를 올리지 않는다 — 실패는 `status`·`why` 로 담는다."""
    log = logf or (lambda m: None)
    track = track or _default_track
    get_issue = get_issue or _default_get_issue
    ctx = IssueContext()
    try:
        if issue_id is not None:
            ctx.issue_id, ctx.source = int(issue_id), "given"
            ctx.requested = next((s.tasks for s in commit_scope.parse_message(message)
                                  if s.issue_id == ctx.issue_id), ())
        else:
            _resolve(ctx, sha, message, root, track, log)
        if ctx.issue_id is None:
            ctx.status, ctx.why = NO_ISSUE, "일감 번호를 못 풀었다(추적 기록 없음 · 제목 범위 없음)"
            log(f"{_tag(ctx)} — {ctx.why} · 컨텍스트 없이 진행")
            return ctx
        _fill(ctx, get_issue)
    except Exception as e:                                       # noqa: BLE001 — 리뷰를 막지 않는다
        ctx.status, ctx.why = REDMINE_ERROR, f"수집 중 예외 {type(e).__name__}: {e}"
    extra = f" · 함께 적힌 일감 {', '.join('#%d' % n for n in ctx.other_issues)} 은 안 붙였다" \
        if ctx.other_issues else ""
    log(f"{_tag(ctx)} — {ctx.status} ({ctx.source or '출처 없음'}) {ctx.why}{extra}".rstrip())
    return ctx


def _fill(ctx: IssueContext, get_issue) -> None:
    try:
        got = get_issue(ctx.issue_id)
    except Exception as e:                                       # noqa: BLE001
        ctx.status, ctx.why = REDMINE_ERROR, f"Redmine 조회 예외 {type(e).__name__}: {e}"
        return
    if not isinstance(got, dict) or got.get("error") or got.get("id") is None:
        err = got.get("error") if isinstance(got, dict) else f"응답 형식 {type(got).__name__}"
        ctx.status, ctx.why = REDMINE_ERROR, f"Redmine 조회 실패 — {err or '일감 없음'}"
        return
    ctx.subject = str(got.get("subject") or "")
    desc = str(got.get("description") or "")
    try:
        ctx.spec = split_spec(desc)
        plan = plan_block.parse(desc)
    except plan_block.PlanError as e:
        ctx.spec = ctx.spec or desc.strip()
        ctx.status, ctx.why = PLAN_ERROR, f"플랜 형식 오류 — {e} · 스펙만 싣는다"
        return
    if plan is None:
        ctx.status, ctx.why = NO_PLAN, "플랜 영역 없음 · 스펙만 싣는다"
        return
    ctx.plan_tasks = list(plan.tasks)
    ctx.tasks = [t for t in (plan.task(tid) for tid in ctx.requested) if t is not None]
    ctx.missing = tuple(tid for tid in ctx.requested if plan.task(tid) is None)
    picked = {t.id for t in ctx.tasks}
    ctx.others = [t for t in plan.tasks if t.id not in picked]
    if ctx.missing:
        ctx.status, ctx.why = TASK_MISSING, f"플랜에 없는 태스크 {', '.join(ctx.missing)}"
    else:
        ctx.status = OK
        ctx.why = f"태스크 {len(ctx.tasks)}건" if ctx.requested else "태스크를 밝히지 않은 커밋"


# ── 렌더러 ─────────────────────────────────────────────────────────────────

def _task_row(t) -> str:
    return (f"- {t.id} [{t.state}] 목표: {t.goal or '—'}\n"
            f"  대상: {t.target or '—'}\n"
            f"  검증: {t.check or '—'}")


def _task_line(t) -> str:
    return f"- {t.id} [{t.state}] {t.goal or '—'}"


def _missing_note(ctx: IssueContext) -> str:
    return (f"\n(메시지가 밝힌 {', '.join(ctx.missing)} 은 플랜에 없다 — 작성자 표기 오류일 수 있다)"
            if ctx.missing else "")


def _head(ctx: IssueContext) -> str:
    return (f"## 일감·태스크 컨텍스트 (참고 — 작성자가 밝힌 의도다)\n{INTENT_NOTE}\n\n"
            f"### 일감 #{ctx.issue_id} {ctx.subject}\n")


def commit_section(ctx: IssueContext, message: str) -> str:
    """상용 커밋 리뷰용 절 — 상한 없음. 일감을 못 읽었으면 빈 문자열."""
    if not ctx.found:
        return ""
    parts = [_head(ctx),
             "### 커밋 메시지 (원문)\n" + (message or "").strip() + "\n",
             "### 일감 본문 (스펙)\n" + (ctx.spec or "(본문 없음)") + "\n"]
    if ctx.tasks or ctx.missing:
        parts.append("### 이 커밋이 밝힌 태스크\n"
                     + "\n".join(_task_row(t) for t in ctx.tasks) + _missing_note(ctx) + "\n")
    elif ctx.plan_tasks:
        parts.append("### 이 커밋이 밝힌 태스크\n(메시지에 T# 가 없다)\n")
    if ctx.others:
        parts.append("### 플랜의 나머지 태스크\n" + "\n".join(_task_line(t) for t in ctx.others) + "\n")
    return "\n".join(parts).rstrip() + "\n"


def draft_section(ctx: IssueContext, message: str) -> str:
    """로컬 초고 모델용 짧은 절 — 제목 줄과 밝힌 태스크 행만(스펙·나머지 태스크 없음)."""
    if not ctx.found or not ctx.tasks:
        return ""
    return ("## 이 커밋의 의도 (작성자 서술 — 사실로 받지 않는다)\n"
            f"커밋: {commit_scope.subject_of(message)}\n"
            + "\n".join(_task_row(t) for t in ctx.tasks) + "\n")


def _commit_rows(commits) -> list[tuple[str, str]]:
    out = []
    for c in commits or ():
        if isinstance(c, dict):
            h = str(c.get("hash") or c.get("sha") or "")
            msg = str(c.get("message") or c.get("subject") or "")
        else:
            h, msg = str(c[0]), str(c[1] if len(c) > 1 else "")
        out.append((h, msg))
    return out


def range_section(ctx: IssueContext, commits) -> str:
    """범위 리뷰용 절 — 스펙 · 플랜 표 전체 · 커밋별 대응. commits 는 (해시, 메시지) 또는
    {"hash"|"sha", "message"|"subject"} 의 나열. 상한 없음."""
    if not ctx.found:
        return ""
    parts = [_head(ctx), "### 일감 본문 (스펙)\n" + (ctx.spec or "(본문 없음)") + "\n"]
    if ctx.plan_tasks:
        parts.append("### 플랜\n" + "\n".join(_task_row(t) for t in ctx.plan_tasks) + "\n")
    rows = []
    for h, msg in _commit_rows(commits):
        subj = commit_scope.subject_of(msg)
        mine = next((s for s in commit_scope.parse(subj) if s.issue_id == ctx.issue_id), None)
        tasks = ",".join(mine.tasks) if mine and mine.tasks else "—"
        rows.append(f"- {h[:10]} [{tasks}] {subj}")
    if rows:
        parts.append("### 커밋별 태스크 (제목 범위에서 읽음 — 작성자 표기)\n" + "\n".join(rows) + "\n")
    return "\n".join(parts).rstrip() + "\n"
