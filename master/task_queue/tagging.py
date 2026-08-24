"""요청 태그 — **모든 통신 표면이 「어느 프로젝트의 요청인가」를 말한다** (`#257`·`#258`).

## 왜 표인가

사용자 요구(2026-08-22): *"기존에 서버랑 통신하는 부분들 모두 태그 추가해. 그래서 무슨
프로젝트의 요청인지 알 수 있잖아"* + *"인프라 서버는 단일 하나의 프로젝트만 관리한다.
그거 이외의 작업은 모두 거절"*.

[중요] **엔드포인트마다 `if` 를 뿌리면 다음에 추가되는 엔드포인트는 태그가 없다** — 실측이
그렇게 났다. `#243` 이 시소러스 둘만 배선했고, 그래서 `signals`·`history`·`claim` 은 그대로
남았다. 그리고 `ax-task-queue.service` 는 프로젝트 이름이 **유닛에 박혀** 있었다(`#276`).
둘 다 같은 병이다: **선언이 한곳에 없다.**

그래서 여기 표 하나를 둔다. `master/client/spec.py` 와 같은 역할이고, 같은 이유로
**테스트가 「선언되지 않은 라우트」를 실패로 만든다** — 새 엔드포인트는 정책을 고르지 않고는
추가할 수 없다.

## 네 정책 — [중요] 이 축은 둘이 아니라 넷이다

    OPEN    프로젝트 축이 없다. 건강·상태·관리자 표면. 태그를 받지도 않는다
    TAG     **귀속만.** 트윈에 쓰지 않는다 → 태그는 기록·필터용이고 거부하지 않는다
    MOUNT   **요청자가 태그를 고른다** → 마운트와 다르면 **거부**한다 (§5.5.2 · §12.5-c)
    STAMP   **큐가 등재 시점에 스탬프한 값으로 푼다** (`#210`) → 태그는 **대조만** 한다

[중요] `MOUNT` 와 `STAMP` 를 가르는 것이 이 표의 핵심이다. `#210` 이
*"활성이 아니라 work 의 스탬프로 푼다"* 를 정한 이유는 **미종결 work 를 둔 채 활성을 바꿨을 때
산출물이 원래 프로젝트로 가야** 하기 때문이다. 그러니 `STAMP` 표면에서 마운트를 강제하면
`#210` 을 깨뜨린다 — 거기서는 태그가 **스탬프와 어긋났는지**만 본다(어긋나면 요청자가 착각한
것이므로 거부하되, 마운트와의 비교로 거부하지 않는다).

[주의] 거부 형태는 **200 + `ok:false` + 사유**다 — 409·500 이 아니다(§12.5-c 확정).
`ax-client` 는 [미연결] 시 지난 스냅샷으로 폴백하므로 거절을 장애로 오인하면 **낡은 결과를
돌려준다.** 500 은 더 나쁘다: 사유가 없다.
"""
from __future__ import annotations

OPEN, TAG, MOUNT, STAMP = "open", "tag", "mount", "stamp"

# ─── 라우트별 정책 ────────────────────────────────────────────────────────────
# [중요] **키는 `"<METHOD> <path>"` 이고 서버의 데코레이터와 글자까지 같아야 한다** —
#    `test_tagging.py` 가 실물 라우트를 열거해 이 표와 맞춘다. 하나라도 빠지면 실패한다.
POLICY = {
    # 프로젝트 축이 없는 표면
    "GET /livez":                                   OPEN,
    "GET /api/v1/health":                           OPEN,
    "GET /api/v1/status":                           OPEN,
    "POST /api/v1/admin/reset":                     OPEN,
    "GET /api/v1/admin/workers":                    OPEN,
    "POST /api/v1/admin/workers/{worker_id}/directive": OPEN,

    # work 등재 — [중요] **여기가 스탬프의 출처다.** 태그가 이후 모든 STAMP 표면을 결정한다
    "POST /api/v1/works":                           MOUNT,

    # 조회·필터 — 트윈에 쓰지 않는다
    "GET /api/v1/works":                            TAG,
    "GET /api/v1/works/duplicates":                 TAG,
    "GET /api/v1/tasks":                            TAG,

    # work·task 스탬프로 푸는 표면 (#210 — 마운트를 강제하지 않는다)
    "GET /api/v1/works/{work_id}":                  STAMP,
    "PATCH /api/v1/works/{work_id}":                STAMP,
    "GET /api/v1/works/{work_id}/summary":          STAMP,
    "POST /api/v1/works/{work_id}/rebase-pending":  STAMP,
    "POST /api/v1/tasks":                           STAMP,
    "GET /api/v1/tasks/{task_id}":                  STAMP,
    "POST /api/v1/tasks/{task_id}/heartbeat":       STAMP,
    "POST /api/v1/tasks/{task_id}/submit":          STAMP,
    "POST /api/v1/tasks/{task_id}/submit-fail":     STAMP,
    "POST /api/v1/tasks/{task_id}/verify":          STAMP,
    "POST /api/v1/tasks/{task_id}/cancel":          STAMP,
    "POST /api/v1/tasks/{task_id}/reverify":        STAMP,

    # [중요] 파견 표면 — **claim 은 마운트를 본다** (`#248`). 워커가 자기 프로젝트를 말하고,
    #    큐는 그 프로젝트의 태스크만 넘긴다. 한 기계에 두 프로젝트의 claimer 가 돌아도
    #    남의 태스크를 집지 않는 근거가 여기다.
    "POST /api/v1/tasks/claim":                     MOUNT,
    "POST /api/v1/workers/{worker_id}/poll":        MOUNT,

    # 트윈 쓰기 대행 — work 가 있으면 스탬프, 없으면 마운트 (`_twin_policy` 참조)
    "POST /api/v1/history":                         STAMP,
    "POST /api/v1/signals":                         STAMP,
    "POST /api/v1/thesaurus/alias":                 MOUNT,
    "POST /api/v1/thesaurus/not-a-class":           MOUNT,

    # Redmine 대행 — 트윈이 아니다. 태그는 **어느 레드마인 프로젝트에 등재하는가**를 정한다
    #    (`#293` — `<트윈>/config.yaml` 의 `redmine.project` 가 변환하고 폴백은 없다).
    #    [주의] 종전 주석은 *"Redmine 프로젝트는 하나(`ModularStage` id 1)"* 였다 — `ns` 가
    #    생긴 뒤로 거짓이다. 마운트를 강제하지 않는 이유는 여전히 「트윈에 쓰지 않아서」다
    "POST /api/v1/redmine/note":                    TAG,
    "POST /api/v1/redmine/issue":                   TAG,
    "POST /api/v1/redmine/link-commit":             TAG,
    "GET /api/v1/redmine/issues":                   TAG,
    "GET /api/v1/redmine/meta":                     OPEN,
    "GET /api/v1/redmine/issue/{issue_id}":         TAG,

    # 감사 로그 — ax-state 에 쓴다(트윈이 아니다) → 귀속만
    "POST /api/v1/anti_patterns/notify":            TAG,

    # [중요] 레시피·안티패턴 **읽기** (`#267`) — 읽기인데 `MOUNT` 다. 오염은 없지만
    #    **답의 정확성이 프로젝트에 달렸다**: 마운트가 A 인데 B 의 레시피를 돌려주면 그것은
    #    빈 결과보다 나쁘다(남의 프로젝트 관습을 이 프로젝트의 것으로 읽는다).
    #    [주의] 태그를 **요구하지는** 않는다 — 없으면 마운트로 해석되고 그것이 곧 정답이다.
    # [주의] **질의는 본문으로 보낸다 — URL 에 한글을 넣지 않는다.** 사용자 지적 2026-08-23.
    #    이 저장소 관례가 이미 그쪽이다(`POST /api/v1/search/combined`). 퍼센트 인코딩된 URL 은
    #    저널에 알아볼 수 없는 문자열로 남고, 손으로 curl 하면 그냥 깨진다(실측: raw 한글 GET 이
    #    `Invalid HTTP request`). 읽기지만 POST 인 이유가 그것이다.
    # [중요] history **읽기** (`#306`) — 레시피와 같은 이유로 `MOUNT` 다: 오염은 없지만
    #    남의 프로젝트 결정 이력을 이 프로젝트의 것으로 읽으면 빈 결과보다 나쁘다.
    "POST /api/v1/history/search":                  MOUNT,
    "POST /api/v1/recipes/search":                  MOUNT,
    "GET /api/v1/anti_patterns":                    MOUNT,
}

# [중요] 태그를 **받아야** 하는 정책 — `OPEN` 만 예외다.
NEEDS_FIELD = (TAG, MOUNT, STAMP)

# [중요] **태그가 없으면 거절하는 표면** (사용자 2026-08-22:
#    *"태그 없으면 동일하게 마운트 다름으로 처리해야지 그러다가 엉뚱한 데이터로 오염되는거잖아"*).
#
# 판정 근거를 정리하면 오염 경로는 하나다: **태그가 없어 마운트로 「가정」하는 자리.**
# 그래서 아래 규칙이 사용자의 사유에서 그대로 나온다.
#
#     쓰고 · 마운트로 푼다   → **필수**   태그가 없으면 가정이 된다 (여기가 오염 경로다)
#     쓰고 · 스탬프로 푼다   → 선택      스탬프가 판정한다 — 가정이 아니다 (`#210`)
#     읽는다                 → 선택      오염이 없다. 태그는 필터로만 쓴다
#
# [주의] 그래서 `POST /api/v1/history`·`signals` 는 **여기 없다** — 그 둘은 `work_id` 가 있으면
#    스탬프로 풀리고, 없으면 서버가 `_mount_gate(require=True)` 를 따로 건다(조건부다).
REQUIRE_TAG = (
    "POST /api/v1/works",                       # 등재 — 스탬프의 출처다. 여기가 비면 전부 빈다
    "POST /api/v1/tasks/claim",                 # 파견 (#248)
    "POST /api/v1/workers/{worker_id}/poll",
    "POST /api/v1/thesaurus/alias",
    "POST /api/v1/thesaurus/not-a-class",
)


_TEMPLATES = None


def normalize_path(path: str) -> str:
    """실제 경로 → 표의 템플릿. `/api/v1/tasks/abc/submit` → `/api/v1/tasks/{task_id}/submit`.

    [중요] 발신자는 실제 id 를 쓰고 표는 템플릿을 쓴다 — 맞춰 주는 자리가 없으면 발신자마다
    문자열을 짜게 되고, 그 순간 표는 정본이 아니게 된다. 쿼리는 떼어낸다.
    """
    global _TEMPLATES
    path = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if _TEMPLATES is None:
        _TEMPLATES = []
        for key in POLICY:
            tpl = key.split(" ", 1)[1]
            _TEMPLATES.append((tpl, tpl.split("/")))
    parts = path.split("/")
    # [중요] **정확 일치를 먼저 본다** — 아니면 `/tasks/claim` 이 `/tasks/{task_id}` 로 삼켜진다
    #    (실측 2026-08-22: 그래서 claim 이 필수 표면에서 빠졌다).
    for tpl, tp in _TEMPLATES:
        if tpl == path:
            return tpl
    for tpl, tp in _TEMPLATES:
        if len(tp) != len(parts):
            continue
        if all(t.startswith("{") or t == g for t, g in zip(tp, parts)):
            return tpl
    return path


def requires_tag(method: str, path: str) -> bool:
    """이 라우트는 태그가 **필수**인가. [주의] `policy_for` 를 먼저 통과시켜 선언을 강제한다."""
    tpl = normalize_path(path)
    policy_for(method, tpl)
    return f"{method.upper()} {tpl}" in REQUIRE_TAG


def reject_untagged(mounted: str = "") -> dict:
    """태그 없음 거절. [중요] **거절 사유를 마운트 불일치와 갈라 준다** — 「태그를 안 보냈다」와
    「다른 프로젝트다」는 고칠 곳이 다르다(전자는 발신자 배선, 후자는 마운트 전환)."""
    return {"ok": False, "status": "no_project_tag",
            "reason": ("요청에 project 태그가 없다 — 어느 프로젝트의 요청인지 판정할 근거가 "
                       "없으면 마운트로 가정하게 되고, 그것이 엉뚱한 트윈을 오염시킨다. "
                       "`.ax/config.json` 의 project 를 실어 보낼 것"
                       + (f" (지금 마운트: {mounted})" if mounted else "")),
            "mounted": mounted}


def policy_for(method: str, path: str) -> str:
    """라우트의 정책. 선언이 없으면 **에러다** — 조용히 통과시키지 않는다."""
    key = f"{method.upper()} {path}"
    try:
        return POLICY[key]
    except KeyError:
        raise KeyError(
            f"태그 정책이 선언되지 않은 라우트다: {key} — `master/task_queue/tagging.py` 의 "
            f"POLICY 에 넷 중 하나({OPEN}/{TAG}/{MOUNT}/{STAMP})를 고를 것") from None


def reject(reason: str, *, project: str = "", mounted: str = "", **extra) -> dict:
    """[중요] **거부 형태는 하나다** — 200 + `ok:false` + 사유 (§12.5-c).

    [주의] 예외를 올리지 않는다. FastAPI 의 `HTTPException` 은 4xx/5xx 를 내고,
    `ax-client` 가 그것을 [미연결]로 읽어 **낡은 스냅샷을 정답처럼 돌려준다**.
    """
    out = {"ok": False, "status": "not_mounted", "reason": reason}
    if project:
        out["project"] = project
    if mounted:
        out["mounted"] = mounted
    out.update(extra)
    return out


def check_stamp(tag: str, stamped: str) -> str:
    """`STAMP` 표면의 대조. 어긋난 사유를 돌려주고, 맞으면 빈 문자열.

    [중요] **마운트와 비교하지 않는다** (`#210`) — 미종결 work 를 둔 채 활성을 바꿨을 때
    그 work 의 요청은 계속 처리돼야 한다. 여기서 잡는 것은 **요청자의 착각**이다:
    태그가 스탬프와 다르면 요청자가 다른 프로젝트의 work 를 자기 것으로 알고 있다.
    """
    tag, stamped = (tag or "").strip(), (stamped or "").strip()
    if not tag or not stamped or tag == stamped:
        return ""
    return (f"요청 태그({tag})가 이 work 의 프로젝트({stamped})와 다르다 — "
            f"work 의 산출물은 등재 시점 스탬프를 따른다(#210). 태그를 확인할 것")
