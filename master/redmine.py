"""Redmine 이슈 **갱신** — 원전 `executor_helpers._redmine_update_issue` 이식 (중 2.1 `#135`).

[주의] **이슈 생성은 이미 있다** — `work/integrate.py` 의 `report_to_redmine`(소 2.3.3, 빌드 실패
등재). 이 모듈은 **기존 이슈에 코멘트·상태·완료율을 붙이는** 다른 능력이다. 둘을 합치지 않은
이유: 생성은 파이프라인(통합자)이 하고, 갱신은 검수 흐름(`work/review.py`)이 한다.

## [중요] 키는 이 저장소에도 `~/.config` 에도 없다

원전은 프로젝트 `config.json` 의 `redmine_api_key` 를 읽는다. 우리는 그러지 않는다 —
키는 **마스터의 컨테이너 DB** 에만 있다(`docs/10-references.md` §10.1). 그래서:

    ① `.33`(요청자)에는 키가 없다 → 검수 도구는 **본문만 만들고** 마스터를 거친다
       (사용자 결정 2026-08-16: *"마스터 경유 (토큰 인증)"*)
    ② [중요] **키 값을 로그·문서·커밋에 적지 않는다** — 이 모듈은 값을 절대 반환하지 않는다

## [중요] 조용한 실패를 만들지 않는다 — 원전과 다른 한 곳

원전은 실패 시 `False` 를 돌려준다(*"실패는 silent"*). 우리 σ 감사가 잡는 부류라
**사유 문자열**을 돌려준다 — `report_to_redmine` 이 이미 그 관례다. *"이슈 추적이 안 된 것"*
과 *"게이트가 통과한 것"* 은 다르고, 그 차이가 보이지 않으면 나중에 구분할 수 없다.

## [중요] 상태 이름은 환경마다 다르다 — 그래서 이름→id 를 **동적 조회**한다

원전이 그렇게 해 둔 이유가 우리에게 그대로 적용된다: 이 Redmine 은 **한국어**다
(신규·진행·해결·피드백·완료). [주의] 그리고 우리 규약에서 **닫힌 상태는 「완료」뿐이고 「해결」은
아직 열린 것**이다(`CLAUDE.md`). 원전도 finalize 에서 `Closed` 로 보내지 않는다 —
*"Closed 는 사람 결정"*. 두 규약이 같은 방향이므로 기본값을 **해결**로 둔다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

DEFAULT_URL = "http://192.168.0.57:8080"

# [중요] **이 Redmine 의 실제 상태 목록** (실측 2026-08-16 — 추측하지 않았다):
#
#     신규(1) · 진행(2) · 해결(3) · 검토(5) · 완료(4 = is_closed)
#
# [주의] 처음에 반려 기본값을 「피드백」으로 적어 뒀다가 **실측에 반박당했다** — 그런 상태는
#    없다. 그대로 뒀으면 상태 변경이 **영원히 조용히 건너뛰어졌을** 것이다(코드가 사유는
#    남기지만, 아무도 안 읽는 사유는 없는 것과 같다).
STATUS_ON_FINALIZE = "완료"     # 🔴 마감은 닫는다 (사용자 2026-09-04: *"레드마인 닫고
#                              메인에 머지해야지"*). [주의] 종전 값은 「해결」이었고 근거가
#                              *"닫는 것은 사람"* 이었는데, 마감 호출 자체가 사람의 승인으로만
#                              도는 자리다 — 자동으로 닫히는 것이 아니다.
# [중요] **반려에 해당하는 상태가 우리 Redmine 에 없다.** 원전은 `Rejected` 를 쓰지만 그건 그쪽
#    환경의 상태다. 없는 것을 억지로 고르면(예: 「검토」) **상태가 거짓말을 한다** — 반려된
#    일감이 「검토 중」으로 보인다. 그래서 기본은 **상태를 안 바꾸고 코멘트만** 남긴다.
#    [주의] 상태를 새로 만들지 말 것 — 트래커·상태 구성은 게임 프로젝트와 공유한다.
STATUS_ON_REJECT = ""
HTTP_TIMEOUT = 30


def base_url() -> str:
    return (os.environ.get("AX_REDMINE_URL") or DEFAULT_URL).rstrip("/")


def api_key(*, reader=None) -> str:
    """API 키. 환경변수 → 컨테이너 DB 순. [중요] **없으면 빈 문자열** (예외를 던지지 않는다).

    [주의] [중요] **이 값을 로그에 남기지 말 것.** 호출자는 있음/없음만 보고한다.
    `reader` 는 테스트 주입 자리다 — 실 컨테이너를 두드리지 않는다.
    """
    env = (os.environ.get("AX_REDMINE_API_KEY") or "").strip()
    if env:
        return env
    if reader is not None:
        return (reader() or "").strip()
    try:
        r = subprocess.run(
            ["docker", "exec", "redmine-db-1", "psql", "-U", "redmine", "-d", "redmine",
             "-tAc", "select value from tokens where action='api' limit 1"],
            capture_output=True, text=True, timeout=20)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _request(method: str, url: str, key: str, payload=None, *, sender=None):
    if sender is not None:
        return sender(method, url, payload)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Redmine-API-Key", key)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        body = r.read().decode("utf-8", "replace").strip()
        return json.loads(body) if body else {}


def resolve_status_id(name: str, *, key: str = "", url: str = "", sender=None):
    """상태 **이름 → id**. 못 찾으면 `None`.

    [중요] id 를 코드에 박지 않는 이유(원전 주석): 환경마다 다르다. 우리는 거기에 하나 더 있다 —
    이 Redmine 의 상태 이름이 **한국어**라 원전 기본값(`Resolved`)이 애초에 안 맞는다.
    """
    if not name:
        return None
    try:
        got = _request("GET", f"{url or base_url()}/issue_statuses.json", key, sender=sender)
    except Exception:                                        # noqa: BLE001
        return None
    for s in (got or {}).get("issue_statuses") or []:
        if str(s.get("name", "")).strip() == name.strip():
            return s.get("id")
    return None


def resolve_tracker_id(name: str, *, key: str = "", url: str = "", sender=None):
    """트래커 **이름 → id** (resolve_status_id 와 같은 결 — id 를 코드에 박지 않는다)."""
    if not name:
        return None
    try:
        got = _request("GET", f"{url or base_url()}/trackers.json", key, sender=sender)
    except Exception:                                        # noqa: BLE001
        return None
    for t in (got or {}).get("trackers") or []:
        if str(t.get("name", "")).strip() == name.strip():
            return t.get("id")
    return None


def resolve_priority_id(name: str, *, key: str = "", url: str = "", sender=None):
    """우선순위 **이름 → id** (enumerations API)."""
    if not name:
        return None
    try:
        got = _request("GET", f"{url or base_url()}/enumerations/issue_priorities.json",
                       key, sender=sender)
    except Exception:                                        # noqa: BLE001
        return None
    for p in (got or {}).get("issue_priorities") or []:
        if str(p.get("name", "")).strip() == name.strip():
            return p.get("id")
    return None


# [중요] **AX 인프라 이슈의 자리 — 전용 프로젝트 `ax-cluster`** (사용자 결정 2026-09-28,
#   `docs/10` §10.1). 종전 결정(2026-08-09 「게임 프로젝트와 분리하지 않는다 · `[AX]` 접두어로
#   구분」)은 **폐기됐다** — 비UE 유틸 프로젝트(`kimodo`)가 들어오며 AX 가 한 게임의 도구가
#   아니게 됐다. 열린 `[AX]` 69건은 옮겼고, 닫힌 것은 `modularstage` 에 기록으로 남는다.
#   마일스톤 버전은 **전체 공유(`system`)** 로 바꿔 두 프로젝트에서 같은 버전을 쓴다.
#
# [주의] 이 상수는 **AX 인프라 축의 기본값**이다. 게임·유틸 소스 일감이 어디로 갈지는
#   `<트윈>/config.yaml` 의 `redmine.project` 가 정한다(`#293`) — 폴백하지 않는다.
AX_PROJECT_ID = "ax-cluster"
PROJECT_ID = AX_PROJECT_ID      # 하위 호환 — 기존 호출자가 이 이름을 쓴다


def project_of(project: str, *, registry=None) -> str:
    """게임 프로젝트 이름 → 그 일감이 등재될 레드마인 프로젝트 식별자 (`#293`).

    [중요] **폴백하지 않는다.** 미설정이면 사유를 문자열로 돌려주고 호출자가 멈춘다 —
    조용히 `modularstage` 로 떨어지면 **남의 프로젝트를 오염시킨다**(`#257` 이 태그에서
    내린 것과 같은 판단: 없는 것을 가정으로 메우지 않는다).
    """
    if not (project or "").strip():
        return ""
    try:
        from .projects.config import Registry
        reg = registry or Registry.load()
        return (reg.config_of(project).redmine_project or "").strip()
    except Exception:                                        # noqa: BLE001
        return ""


def _stamp_fields(issue: dict, fixed_version: str, parent_issue_id, *,
                  project: str, key: str, base: str, sender=None) -> list:
    """마일스톤·부모를 `issue` 에 채운다. 돌려주는 것은 **못 붙인 것의 사유 목록** (`#303`).

    [중요] create 와 update 가 **같은 규칙**을 써야 한다 — 두 벌로 쓰면 한쪽만 부분 일치를
    허용하는 식으로 조용히 갈린다. 이름→id 는 `resolve_version_id` 하나뿐이다.
    """
    skipped = []
    if fixed_version:
        vid = resolve_version_id(fixed_version, project=project, key=key, url=base,
                                 sender=sender)
        if vid:
            issue["fixed_version_id"] = vid
        else:
            skipped.append(f"마일스톤 `{fixed_version}` 을 이 프로젝트(`{project}`)에서 "
                           "찾지 못해 생략")
    if parent_issue_id not in (None, "", 0):
        try:
            issue["parent_issue_id"] = int(parent_issue_id)
        except (TypeError, ValueError):
            skipped.append(f"부모 `{parent_issue_id!r}` 가 이슈 번호가 아니어서 생략")
    return skipped


def create_issue(subject: str, description: str = "", *, tracker_name: str = "",
                 priority_name: str = "", project: str = PROJECT_ID,
                 fixed_version: str = "", parent_issue_id=None,
                 key: str = "", url: str = "", sender=None) -> dict:
    """이슈를 새로 만든다. 반환: `{"id": int}` 또는 `{"error": 사유}`.

    원전 plan_register 의 생성부와 같은 결: 트래커·우선순위는 이름으로 해석하고, 해석이
    안 되면 그 필드만 생략한다 (생성 자체를 막지 않는다). [중요] update_issue 와 달리
    dict 를 돌려준다 — 호출자(플랜 등록)가 발급 id 를 frontmatter 에 되적어야 한다.

    [중요] **`fixed_version`·`parent_issue_id` 는 원전에 없던 추가다** (`#303`). 원전
    `redmine_tracker/server.py:549 create_issue` 도 버전·부모를 안 받고, 계층은 읽기
    (`list_child_issues`)만 썼다 — 사람이 UI 에서 붙이는 방식이다. 우리가 추가하는 근거는
    우리 규약이다: 「항목·진행은 레드마인만」 + 마일스톤을 **버전**으로 관리 + 「자동화를
    전제로」(사용자 2026-08-22). 안 붙이면 등재가 반쪽이고 무버전 버킷으로 떨어진다(실측 13건).
    [주의] **해석 실패는 그 필드만 생략하고 `skipped` 에 사유를 담는다** — 트래커·우선순위와
    같은 관례다. 생성 자체를 막지 않되 조용히 넘어가지도 않는다.
    """
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if sender is None and not k:
        return {"error": "API 키가 없다 (`AX_REDMINE_API_KEY` 또는 컨테이너 DB, §10.1)"}
    if not (subject or "").strip():
        return {"error": "subject 가 비었다"}

    issue: dict = {"project_id": project, "subject": subject.strip()[:250],
                   "description": description or ""}
    tid = resolve_tracker_id(tracker_name, key=k, url=base, sender=sender)
    if tid:
        issue["tracker_id"] = tid
    pid = resolve_priority_id(priority_name, key=k, url=base, sender=sender)
    if pid:
        issue["priority_id"] = pid
    skipped = _stamp_fields(issue, fixed_version, parent_issue_id,
                            project=project, key=k, base=base, sender=sender)

    try:
        got = _request("POST", f"{base}/issues.json", k, {"issue": issue}, sender=sender)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    new_id = ((got or {}).get("issue") or {}).get("id")
    if not new_id:
        return {"error": "생성 응답에 id 없음", "raw": got}
    out = {"id": int(new_id)}
    if skipped:
        out["skipped"] = skipped        # [중요] 붙지 않은 것은 말한다 — 조용한 생략 금지
    return out


def update_issue(issue_id, *, notes: str = "", status_name: str = "", done_ratio=None,
                 fixed_version: str = "", parent_issue_id=None,
                 priority_name: str = "", subject: str = "", description: str = "",
                 project: str = PROJECT_ID, key: str = "", url: str = "",
                 sender=None) -> str:
    """기존 이슈에 코멘트·상태·완료율을 붙인다. **사람이 읽을 결과 문자열**을 돌려준다.

    [중요] 실패해도 예외를 던지지 않는다 — 검수 흐름은 이것 때문에 멈추면 안 된다. 다만
    **조용히 넘어가지도 않는다**: 무엇이 안 됐는지 문장으로 남는다.

    [주의] `fixed_version` 을 쓸 때는 `project` 도 줘야 한다 (`#303`) — 버전은 **프로젝트에
    속하므로** 기본값(AX 프로젝트)으로 `ns` 이슈의 마일스톤을 찾으면 못 찾는다. 못 찾으면
    그 필드만 생략하고 결과 문장에 사유가 붙는다.

    `priority_name`·`subject`·`description` 은 비우면 안 바꾼다 (`#752`). 우선순위는 상태와
    같은 결 — 이름으로 해석하고, 없으면 그 필드만 건너뛰고 말한다. `description` 은 본문
    **전체 교체**다(차이는 Redmine 이 저널에 남긴다).
    """
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    try:
        iid = int(issue_id)
    except (TypeError, ValueError):
        return f"[주의] 레드마인 갱신 건너뜀 — 이슈 번호가 아니다: {issue_id!r}"
    if sender is None and not k:
        return ("[주의] 레드마인 갱신 건너뜀 — API 키가 없다 "
                "(`AX_REDMINE_API_KEY` 또는 컨테이너 DB, §10.1)")

    issue: dict = {}
    if notes:
        issue["notes"] = notes
    if done_ratio is not None:
        issue["done_ratio"] = int(done_ratio)
    status_note = ""
    if status_name:
        sid = resolve_status_id(status_name, key=k, url=base, sender=sender)
        if sid is None:
            # [주의] 원전과 같다 — 상태만 건너뛰고 코멘트는 남긴다. [중요] 다만 **말은 한다.**
            status_note = f" (상태 `{status_name}` 은 이 Redmine 에 없어 건너뜀)"
        else:
            issue["status_id"] = sid
    priority_note = ""
    if priority_name:
        pid = resolve_priority_id(priority_name, key=k, url=base, sender=sender)
        if pid is None:
            priority_note = f" (우선순위 `{priority_name}` 은 이 Redmine 에 없어 건너뜀)"
        else:
            issue["priority_id"] = pid
    if (subject or "").strip():
        issue["subject"] = subject.strip()[:250]       # create_issue 와 같은 한도
    if description:
        issue["description"] = description
    stamp_note = ""
    sk = _stamp_fields(issue, fixed_version, parent_issue_id,
                       project=project, key=k, base=base, sender=sender)
    if sk:
        stamp_note = " (" + " · ".join(sk) + ")"
    if not issue:
        return ("[주의] 레드마인 갱신 건너뜀 — 바꿀 것이 없다"
                + status_note + priority_note + stamp_note)

    try:
        _request("PUT", f"{base}/issues/{iid}.json", k, {"issue": issue}, sender=sender)
    except urllib.error.HTTPError as e:
        return f"[주의] 레드마인 #{iid} 갱신 실패 — HTTP {e.code}"
    except Exception as e:                                   # noqa: BLE001
        return f"[주의] 레드마인 #{iid} 갱신 실패 — {type(e).__name__}: {e}"
    what = ", ".join(k2 for k2 in ("notes", "status_id", "done_ratio", "priority_id",
                                   "subject", "description",
                                   "fixed_version_id", "parent_issue_id") if k2 in issue)
    return f"레드마인 #{iid} 갱신 ({what}){status_note}{priority_note}{stamp_note}"


# ─────────────────────────────────────────
# 읽기 — 원전 `redmine_tracker` 의 조회 도구 이식 (#226 위임 구멍 ①)
#
# [중요] **이 자리는 8103 이 아니라 큐(8101)** 다. 8103 의 `/api/v1/*` 는 무인증 공개라
#    (실측 2026-08-20: 토큰 없이 200) 일감 본문·검수 이력이 LAN 아무에게나 열린다.
#    읽기라는 사실이 「공개 표면에 두라」는 뜻이 아니다.
# [중요] 원전과 같은 **요약 형태**를 지킨다 — 이슈 원본 json 을 그대로 흘리지 않는다.
#    작업장 세션이 쓰는 필드만 남기면 컨텍스트도 아끼고, 필드 이름이 절차 문서와 어긋나지 않는다.
# ─────────────────────────────────────────

def _issue_row(iss: dict, base: str) -> dict:
    """목록 한 줄 (원전 `list_issues` 의 필드 구성 그대로)."""
    return {
        "id": iss.get("id"),
        "subject": iss.get("subject"),
        "tracker": (iss.get("tracker") or {}).get("name"),
        "status": (iss.get("status") or {}).get("name"),
        "priority": (iss.get("priority") or {}).get("name"),
        "assigned_to": (iss.get("assigned_to") or {}).get("name", ""),
        "author": (iss.get("author") or {}).get("name", ""),
        "fixed_version": (iss.get("fixed_version") or {}).get("name", ""),
        "updated_on": iss.get("updated_on"),
        # [중요] **진행률을 목록에도 싣는다** (`#366`). 없으면 목록으로 감사할 때 전부
        #    `None` 으로 보여 **닫힌 이슈가 0% 인 것처럼** 읽힌다(실측 2026-09-07: 그 착시로
        #    100건을 「진행률 미달」로 셀 뻔했다 — 개별 조회로는 전부 100 이었다).
        #    [주의] 원전 필드 구성에 없던 것을 **더한** 것이다. 화면·소비자는 모르는 키를
        #    무시하므로 안전하고, 없으면 관측이 거짓이 된다.
        "done_ratio": iss.get("done_ratio"),
        "url": f"{base}/issues/{iss.get('id')}",
    }


def list_issues(*, project: str = PROJECT_ID, status: str = "open", tracker: str = "",
                fixed_version: str = "", limit: int = 25, offset: int = 0,
                sort: str = "updated_on:desc", key: str = "", url: str = "",
                sender=None) -> dict:
    """이슈 목록. 반환 `{"total_count", "issues":[...]}` 또는 `{"error": 사유}`.

    [주의] `status` 기본값은 원전과 같은 `"open"` 이다 — 우리 규약에서 **「해결」도 열린 것**
    이므로(닫힌 상태는 「완료」뿐) 이 기본값이 규약과 같은 방향이다.
    """
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if not k:
        return {"error": "레드마인 API 키를 찾지 못했다 — 마스터 컨테이너 DB 확인"}
    params = [f"limit={max(1, min(int(limit), 100))}", f"offset={max(0, int(offset))}",
              f"sort={sort}"]
    if project:
        params.append(f"project_id={project}")
    if status and status != "*":
        params.append(f"status_id={status}")
    if tracker:
        tid = resolve_tracker_id(tracker, key=k, url=base, sender=sender)
        if tid is None:
            # [중요] 조용히 전체를 돌려주지 않는다 — 필터가 안 걸린 목록은 거짓말이다.
            return {"error": f"트래커 `{tracker}` 를 이 Redmine 에서 찾지 못했다"}
        params.append(f"tracker_id={tid}")
    if fixed_version:
        vid = resolve_version_id(fixed_version, project=project, key=k, url=base, sender=sender)
        if vid is None:
            return {"error": f"마일스톤(버전) `{fixed_version}` 을 찾지 못했다"}
        params.append(f"fixed_version_id={vid}")
    try:
        got = _request("GET", f"{base}/issues.json?{'&'.join(params)}", k, sender=sender)
    except urllib.error.HTTPError as e:
        return {"error": f"레드마인 조회 실패 — HTTP {e.code}"}
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"레드마인 조회 실패 — {type(e).__name__}: {e}"}
    rows = [_issue_row(i, base) for i in (got or {}).get("issues") or []]
    return {"total_count": (got or {}).get("total_count", len(rows)), "issues": rows}


def get_issue(issue_id, *, key: str = "", url: str = "", sender=None) -> dict:
    """이슈 1건 상세 + 노트 이력(원전과 같이 `journals` 중 **본문 있는 것만**)."""
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if not k:
        return {"error": "레드마인 API 키를 찾지 못했다 — 마스터 컨테이너 DB 확인"}
    try:
        got = _request("GET", f"{base}/issues/{int(issue_id)}.json?include=journals",
                       k, sender=sender)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"#{issue_id} 없음 (404)"}
        return {"error": f"레드마인 #{issue_id} 조회 실패 — HTTP {e.code}"}
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"레드마인 #{issue_id} 조회 실패 — {type(e).__name__}: {e}"}
    iss = (got or {}).get("issue") or {}
    out = _issue_row(iss, base)
    out.update({
        "description": iss.get("description", ""),
        "done_ratio": iss.get("done_ratio", 0),
        "created_on": iss.get("created_on"),
        "parent": (iss.get("parent") or {}).get("id"),
        "journals": [{"user": (j.get("user") or {}).get("name", ""),
                      "notes": j.get("notes"),
                      "created_on": j.get("created_on")}
                     for j in iss.get("journals") or [] if j.get("notes")],
    })
    return out


# [중요] **실측값이다** (2026-09-20 `#652`) — 추측이 아니다. 255 는 통과하고 256 은
#    `422 {"errors":["설명 은 너무 깁니다 (최대 255자 까지)"]}` 로 거절된다.
DESCRIPTION_MAX = 255


def _http_error_reasons(err) -> str:
    """레드마인 오류 본문의 `errors` 배열을 한 줄로. 못 읽으면 빈 문자열.

    [중요] **읽기 실패가 원래 오류를 덮지 않는다** — 호출자는 이미 `HTTP <code>` 를 쥐고
    있고, 이 함수는 거기에 **사유를 더하기만** 한다.
    """
    try:
        body = err.read().decode("utf-8", "replace")
    except Exception:                                        # noqa: BLE001
        return ""
    try:
        errs = (json.loads(body) or {}).get("errors")
    except ValueError:
        return body.strip()[:200]
    if isinstance(errs, list) and errs:
        return " · ".join(str(x) for x in errs)[:300]
    return body.strip()[:200]


def list_versions(*, project: str = PROJECT_ID, key: str = "", url: str = "",
                  sender=None) -> list:
    """그 프로젝트의 마일스톤(버전) 원본 목록. 실패하면 **빈 목록**이다.

    [중요] **버전은 프로젝트에 속한다** (`#652`) — 이 함수를 부르는 쪽은 언제나 어느
    프로젝트인지 말해야 한다. 종전에는 `meta` 가 이 조회를 `PROJECT_ID` 로 박아 두어,
    `ns` 작업장이 물으면 **`modularstage` 의 마일스톤 6개**가 돌아왔다(실측 2026-09-20).
    """
    try:
        got = _request("GET",
                       f"{(url or base_url()).rstrip('/')}/projects/{project}/versions.json",
                       key or api_key(), sender=sender)
    except Exception:                                        # noqa: BLE001
        return []
    return list((got or {}).get("versions") or [])


def create_version(name: str, *, project: str = PROJECT_ID, due_date: str = "",
                   description: str = "", status: str = "open", sharing: str = "none",
                   key: str = "", url: str = "", sender=None) -> dict:
    """마일스톤(버전)을 만든다. 반환: `{"id": int, "name": str}` 또는 `{"error": 사유}`.

    [중요] **원전에 없던 능력이다** (`#652`). 원전 `redmine_tracker` 는 버전을 **읽기만** 했고
    (`create_issue` 도 버전을 안 받았다) 사람이 웹 UI 에서 만드는 방식이었다. 우리가 여는 근거는
    `#303` 이 `fixed_version` 을 연 것과 **같다**: 요청자(`.33`)에게는 레드마인 키가 없고
    (키는 마스터의 컨테이너 DB 에만 있다) 마일스톤을 만들 유일한 길이 **웹 UI 를 사람이 여는
    것**뿐이면, 「항목·진행은 레드마인만」 규약이 사실상 지켜지지 않는다 — 실측이 그랬다:
    `ns` 이슈 24건 중 마일스톤이 붙은 것 **0건**.

    [중요] **같은 이름이 이미 있으면 만들지 않고 그 id 를 돌려준다** (`existing: True`).
    버전은 이름으로 참조되는데(`resolve_version_id` 가 부분 일치까지 허용한다) 동명이 둘이면
    **어느 것에 붙었는지 아무도 모른다.** 조용히 중복을 만드는 것이 여기서는 가장 비싸다.
    [주의] 이름 충돌 판정은 **정확 일치**다 — `resolve_version_id` 의 부분 일치를 쓰면
    「마일스톤 1」을 만들려는데 「마일스톤 10」이 있다고 거절한다.
    """
    nm = (name or "").strip()
    if not nm:
        return {"error": "마일스톤 이름이 비었다"}
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if sender is None and not k:
        return {"error": "API 키가 없다 (`AX_REDMINE_API_KEY` 또는 컨테이너 DB, §10.1)"}
    if not (project or "").strip():
        return {"error": "project 가 비었다 — 버전은 프로젝트에 속한다"}
    if status not in ("open", "locked", "closed"):
        return {"error": f"status 는 open·locked·closed 중 하나다 — `{status}` 가 왔다"}
    # [중요] **설명 255자는 실측값이다** (2026-09-20, `#652`): 256자를 보내면 레드마인이
    #    `{"errors":["설명 은 너무 깁니다 (최대 255자 까지)"]}` 로 거절한다. 자르지 않고
    #    **거절한다** — 마일스톤 설명은 규약을 적는 자리라 조용히 잘리면 규약이 반쪽이 된다.
    #    [주의] 이름(60자)은 레드마인이 자르지 않고 받으므로 여기서도 건드리지 않는다.
    if len(description or "") > DESCRIPTION_MAX:
        return {"error": f"description 이 {len(description)}자다 — 레드마인 한계는 "
                         f"{DESCRIPTION_MAX}자다 (실측). 줄여서 다시 보내라"}

    for v in list_versions(project=project, key=k, url=base, sender=sender):
        if str(v.get("name", "")).strip() == nm:
            return {"id": v.get("id"), "name": nm, "existing": True,
                    "note": f"이미 있다 — `{project}` 의 마일스톤 `{nm}`. 새로 만들지 않았다"}

    ver: dict = {"name": nm[:60], "status": status, "sharing": sharing}
    if description:
        ver["description"] = description
    if (due_date or "").strip():
        # [주의] 형식이 틀리면 레드마인이 422 로 거절한다 — 여기서 **먼저** 말한다.
        #    깊은 곳의 `HTTP 422` 는 무엇이 틀렸는지 알려 주지 않는다(이 저장소 관례).
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date.strip()):
            return {"error": f"due_date 는 `YYYY-MM-DD` 다 — `{due_date}` 가 왔다"}
        ver["due_date"] = due_date.strip()

    try:
        got = _request("POST", f"{base}/projects/{project}/versions.json", k,
                       {"version": ver}, sender=sender)
    except urllib.error.HTTPError as e:
        # [주의] 404 는 「그 프로젝트가 없다」이고 403 은 「그 키에 권한이 없다」다 — 둘은
        #    사람이 할 일이 다르다. 코드만 흘리면 요청자가 고칠 근거가 없다.
        # 🔴 [중요] **422 는 레드마인이 사유를 본문에 담아 준다 — 버리지 않는다.**
        #    실측 2026-09-20: 설명 256자를 보냈더니 `HTTP 422` 만 돌려받아 무엇이 틀렸는지
        #    알 수 없었다. 본문에는 `{"errors":["설명 은 너무 깁니다 (최대 255자 까지)"]}`
        #    가 그대로 있었다. 이 함수의 독스트링이 *"깊은 곳의 HTTP 422 는 무엇이 틀렸는지
        #    알려 주지 않는다"* 고 적어 놓고 **정작 이 자리가 그러고 있었다.**
        hint = {404: f"레드마인에 `{project}` 프로젝트가 없다",
                403: "이 API 키에 버전 관리 권한이 없다"}.get(e.code, "")
        if not hint:
            hint = _http_error_reasons(e)
        return {"error": f"HTTP {e.code}" + (f" — {hint}" if hint else "")}
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    new_id = ((got or {}).get("version") or {}).get("id")
    if not new_id:
        return {"error": "생성 응답에 id 없음", "raw": got}
    return {"id": int(new_id), "name": nm, "project": project, "existing": False}


def update_version(name: str, *, project: str = PROJECT_ID, new_name: str = "",
                   description=None, due_date=None, status: str = "",
                   key: str = "", url: str = "", sender=None) -> dict:
    """마일스톤(버전)의 이름·설명·마감일을 고친다. 반환: `{"id", "name", "changed"}` 또는 error.

    🔴 [중요] **대상 해석은 `resolve_version_id` 를 쓰지 않는다 — 정확 일치다** (`#652`).
    그쪽은 부분 일치를 허용하는데(사람이 「마일스톤 6」만 친다) 그것은 **읽기·부착**의 편의다.
    이름을 **바꾸는** 자리에서 부분 일치를 허용하면 「마일스톤 1」을 고치려다 「마일스톤 10」을
    고친다. 잘못 붙은 것은 떼면 되지만 **잘못 바뀐 이름은 무엇이었는지 아무도 모른다.**
    같은 이유로 `create_version` 의 중복 판정도 정확 일치다.

    [중요] **못 찾으면 있는 이름을 같이 준다** — 요청자는 `redmine_meta` 로 목록을 보지만,
    거절 응답이 스스로 고칠 근거를 실어야 왕복이 준다(이 저장소의 거절 관례).

    [주의] `description`·`due_date` 는 **`None` 이면 안 바꾸고 `""` 이면 비운다.** 빈 문자열을
    「안 바꿈」으로 접으면 **지울 방법이 없어진다.**
    [주의] `status` 는 받되 기본은 빈 값(안 바꿈)이다 — 마일스톤을 잠그거나 닫는 것은
    사람의 결정이라 **호출자가 명시해야만** 움직인다.
    """
    cur = (name or "").strip()
    if not cur:
        return {"error": "고칠 마일스톤 이름이 비었다"}
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if sender is None and not k:
        return {"error": "API 키가 없다 (`AX_REDMINE_API_KEY` 또는 컨테이너 DB, §10.1)"}
    if not (project or "").strip():
        return {"error": "project 가 비었다 — 버전은 프로젝트에 속한다"}

    vs = list_versions(project=project, key=k, url=base, sender=sender)
    target = next((v for v in vs if str(v.get("name", "")).strip() == cur), None)
    if target is None:
        names = [str(v.get("name", "")) for v in vs]
        return {"error": f"`{project}` 에 마일스톤 `{cur}` 이 없다 (정확히 일치해야 한다)",
                "available": names}

    ver: dict = {}
    changed = []
    nn = (new_name or "").strip()
    if nn and nn != cur:
        # [중요] 같은 이름이 이미 있으면 **바꾸지 않는다** — 레드마인도 422 로 막지만,
        #    여기서 먼저 말해야 호출자가 무엇과 부딪혔는지 안다.
        clash = next((v for v in vs if str(v.get("name", "")).strip() == nn), None)
        if clash is not None:
            return {"error": f"`{project}` 에 마일스톤 `{nn}` 이 이미 있다 (id {clash.get('id')}) "
                             "— 이름은 겹칠 수 없다"}
        ver["name"] = nn
        changed.append(f"name `{cur}` → `{nn}`")
    if description is not None:
        if len(description) > DESCRIPTION_MAX:
            return {"error": f"description 이 {len(description)}자다 — 레드마인 한계는 "
                             f"{DESCRIPTION_MAX}자다 (실측). 줄여서 다시 보내라"}
        ver["description"] = description
        changed.append("description" + (" 비움" if not description else ""))
    if due_date is not None:
        d = (due_date or "").strip()
        if d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            return {"error": f"due_date 는 `YYYY-MM-DD` 다 — `{due_date}` 가 왔다"}
        ver["due_date"] = d or None
        changed.append("due_date " + (d or "비움"))
    if status:
        if status not in ("open", "locked", "closed"):
            return {"error": f"status 는 open·locked·closed 중 하나다 — `{status}` 가 왔다"}
        ver["status"] = status
        changed.append(f"status → {status}")

    if not ver:
        return {"error": "바꿀 것이 없다 — new_name·description·due_date·status 중 하나는 줘야 한다",
                "id": target.get("id"), "name": cur}

    try:
        _request("PUT", f"{base}/versions/{int(target['id'])}.json", k, {"version": ver},
                 sender=sender)
    except urllib.error.HTTPError as e:
        hint = {404: f"버전 {target.get('id')} 가 없다 (경합?)",
                403: "이 API 키에 버전 관리 권한이 없다"}.get(e.code, "") or _http_error_reasons(e)
        return {"error": f"HTTP {e.code}" + (f" — {hint}" if hint else "")}
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    return {"id": int(target["id"]), "name": nn or cur, "project": project, "changed": changed}


def count_issues_in_version(version_id, *, project: str = PROJECT_ID, key: str = "",
                            url: str = "", sender=None) -> int:
    """그 마일스톤에 붙은 이슈 수 (**닫힌 것 포함**). 못 세면 `-1`.

    [중요] **`-1` 은 0 이 아니다.** 삭제 판정이 이 값을 쓰는데, 못 센 것을 0 으로 접으면
    **「붙은 게 없다」로 읽혀 지운다.** 미확인은 통과가 아니다(이 저장소의 관례).
    """
    try:
        got = _request("GET",
                       f"{(url or base_url()).rstrip('/')}/issues.json?project_id={project}"
                       f"&status_id=*&fixed_version_id={int(version_id)}&limit=1",
                       key or api_key(), sender=sender)
    except Exception:                                        # noqa: BLE001
        return -1
    n = (got or {}).get("total_count")
    return int(n) if isinstance(n, int) else -1


def delete_version(name: str, *, project: str = PROJECT_ID, confirm: bool = False,
                   key: str = "", url: str = "", sender=None) -> dict:
    """마일스톤(버전)을 지운다. **되돌릴 수 없다.**

    🔴 [중요] **`confirm=False` 가 기본이다** — 안 주면 **무엇이 지워질지만** 돌려주고
    지우지 않는다. `finalize_work`·`advance_work` 와 같은 관례다(사용자 결정 2026-09-04:
    승인 발화가 곧 트리거). 버전에는 이슈 같은 변경 이력이 **없어서** 지우고 나면 그것이
    무엇이었는지 남는 곳이 로그뿐이다.

    🔴 [중요] **붙은 이슈가 있으면 거절한다 — 레드마인이 이미 그런다(실측 2026-09-20).**
    그런데 그쪽의 `422` 는 **본문이 비어 있다.** 사유를 하나도 안 주므로 여기서 **먼저 세고
    먼저 말한다**: 몇 건이 걸려 있고 어떤 번호인지. [주의] 붙은 것을 **대신 떼어 주지
    않는다** — 어느 마일스톤으로 옮길지는 사람의 판단이고, 17건을 말없이 무버전으로
    떨구는 것이 이 일에서 가장 비싼 실수다.

    [주의] 대상 해석은 `update_version` 과 같은 **정확 일치**다. 지우는 자리에서 부분
    일치를 허용하면 「마일스톤 1」을 지우려다 「마일스톤 10」을 지운다.
    """
    cur = (name or "").strip()
    if not cur:
        return {"error": "지울 마일스톤 이름이 비었다"}
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if sender is None and not k:
        return {"error": "API 키가 없다 (`AX_REDMINE_API_KEY` 또는 컨테이너 DB, §10.1)"}
    if not (project or "").strip():
        return {"error": "project 가 비었다 — 버전은 프로젝트에 속한다"}

    vs = list_versions(project=project, key=k, url=base, sender=sender)
    target = next((v for v in vs if str(v.get("name", "")).strip() == cur), None)
    if target is None:
        return {"error": f"`{project}` 에 마일스톤 `{cur}` 이 없다 (정확히 일치해야 한다)",
                "available": [str(v.get("name", "")) for v in vs]}
    vid = int(target["id"])

    n = count_issues_in_version(vid, project=project, key=k, url=base, sender=sender)
    if n < 0:
        return {"error": f"마일스톤 `{cur}` 에 붙은 이슈 수를 세지 못했다 — 세기 전에는 "
                         "지우지 않는다 (미확인은 통과가 아니다)", "id": vid}
    if n > 0:
        ids = []
        try:
            got = _request("GET", f"{base}/issues.json?project_id={project}&status_id=*"
                                  f"&fixed_version_id={vid}&limit=10", k, sender=sender)
            ids = [x.get("id") for x in (got or {}).get("issues") or []]
        except Exception:                                    # noqa: BLE001
            pass
        return {"error": f"마일스톤 `{cur}` 에 이슈 {n}건이 붙어 있어 지울 수 없다 "
                         "— 먼저 다른 마일스톤으로 옮기거나 떼어라 (여기서 대신 떼지 않는다)",
                "id": vid, "issue_count": n, "sample_issue_ids": ids}

    if not confirm:
        return {"id": vid, "name": cur, "project": project, "issue_count": 0,
                "confirm_required": True,
                "note": f"`{project}` 의 마일스톤 `{cur}` 을 지운다. 붙은 이슈 0건. "
                        "되돌릴 수 없다 — 지우려면 `confirm=true` 로 다시 불러라"}

    try:
        _request("DELETE", f"{base}/versions/{vid}.json", k, sender=sender)
    except urllib.error.HTTPError as e:
        # [주의] 실측: 붙은 이슈가 있을 때의 422 는 **본문이 비어 있다.** 위에서 세어 걸렀지만
        #    경합(세는 사이에 누가 붙임)이면 여기로 온다 — 그때도 빈 사유를 내보내지 않는다.
        hint = _http_error_reasons(e) or (
            "레드마인이 거절했다 (사유 본문이 비어 있다) — 보통 그 사이에 이슈가 붙었다는 뜻이다"
            if e.code == 422 else "")
        return {"error": f"HTTP {e.code}" + (f" — {hint}" if hint else ""), "id": vid}
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "id": vid}
    return {"id": vid, "name": cur, "project": project, "deleted": True}


def resolve_version_id(name: str, *, project: str = PROJECT_ID, key: str = "",
                       url: str = "", sender=None):
    """마일스톤(버전) **이름 → id**. 부분 일치를 허용한다 — 우리 버전명은
    *"마일스톤 6 — 개선·확장"* 처럼 길어서 사람이 `마일스톤 6` 만 쓴다(실측)."""
    if not name:
        return None
    vs = list_versions(project=project, key=key, url=url, sender=sender)
    for v in vs:                                             # 정확 일치 우선
        if str(v.get("name", "")).strip() == name.strip():
            return v.get("id")
    for v in vs:
        if name.strip() in str(v.get("name", "")):
            return v.get("id")
    return None


def meta(*, project: str = PROJECT_ID, key: str = "", url: str = "", sender=None) -> dict:
    """상태·트래커·우선순위·버전 카탈로그 (원전 `list_statuses`·`list_trackers` 자리).

    [중요] **한 번에 준다** — 원전은 도구 두 개였지만 절차는 늘 둘을 같이 쓴다
    (`update_issue` 전에 상태 이름을 확인하는 흐름). 나누면 왕복만 는다.

    🔴 [중요] **버전만 프로젝트 축을 탄다** (`#652`). 상태·트래커·우선순위는 레드마인 전역
    설정이라 프로젝트와 무관하지만 **버전은 프로젝트에 속한다.** 종전에는 이 한 줄이
    `PROJECT_ID` 로 박혀 있어서, `ns` 작업장의 `.33` 이 마일스톤을 물으면 **`modularstage` 의
    것 6개**가 왔고 자기 프로젝트의 1개는 안 보였다(실측 2026-09-20). 클라이언트는 그때도
    `project=` 를 보내고 있었다(`queue_api` 가 모든 GET 에 붙인다) — **받는 쪽이 없었다.**
    [주의] 그래서 응답에 `versions_project` 를 같이 싣는다: 「무엇을 봤는지 말한다」는
    `redmine/issues` 와 같은 관례다. 빈 목록이 「없다」인지 「남의 것을 봤다」인지 갈린다.
    """
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    if not k:
        return {"error": "레드마인 API 키를 찾지 못했다 — 마스터 컨테이너 DB 확인"}
    out: dict = {}
    for field, ep, arr in (("statuses", "issue_statuses.json", "issue_statuses"),
                           ("trackers", "trackers.json", "trackers"),
                           ("priorities", "enumerations/issue_priorities.json",
                            "issue_priorities")):
        try:
            got = _request("GET", f"{base}/{ep}", k, sender=sender)
            out[field] = [str(x.get("name", "")) for x in (got or {}).get(arr) or []]
        except Exception as e:                               # noqa: BLE001
            out[field] = []
            out.setdefault("errors", []).append(f"{field}: {type(e).__name__}")
    target = (project or "").strip() or PROJECT_ID
    out["versions_project"] = target          # [중요] 무엇을 봤는지 말한다
    out["versions"] = [{"name": v.get("name"), "status": v.get("status"),
                        "due_date": v.get("due_date")}
                       for v in list_versions(project=target, key=k, url=base, sender=sender)]
    # [중요] 닫힌 상태가 무엇인지 **말해 준다** — 우리 규약(「완료」만 닫힘, 「해결」은 열림)을
    #    도구 응답이 스스로 실어야 작업장 세션이 상태를 잘못 고르지 않는다.
    out["note"] = "닫힌 상태는 「완료」뿐이다 — 「해결」은 아직 열린 것으로 센다"
    return out


def link_commit(issue_id, commit_hash: str, message: str = "", *,
                key: str = "", url: str = "", sender=None) -> str:
    """커밋 해시를 이슈에 노트로 연결한다 (원전 `link_commit` 의 문구 형식 그대로).

    [주의] 새 능력이 아니라 **형식**이다 — `update_issue(notes=...)` 를 부르지만, 원전과 같은
    `커밋 연결: \\`<hash>\\`` 문장을 써야 이력을 나중에 한 규칙으로 훑을 수 있다.
    """
    h = (commit_hash or "").strip()
    if not h:
        return "[주의] 커밋 연결 건너뜀 — 해시가 비었다"
    lines = [f"커밋 연결: `{h}`"]
    if message:
        lines.append(message)
    return update_issue(issue_id, notes="\n".join(lines), key=key, url=url, sender=sender)
