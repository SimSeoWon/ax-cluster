"""Redmine 이슈 **갱신** — 원전 `executor_helpers._redmine_update_issue` 이식 (중 2.1 `#135`).

⚠️ **이슈 생성은 이미 있다** — `work/integrate.py` 의 `report_to_redmine`(소 2.3.3, 빌드 실패
등재). 이 모듈은 **기존 이슈에 코멘트·상태·완료율을 붙이는** 다른 능력이다. 둘을 합치지 않은
이유: 생성은 파이프라인(통합자)이 하고, 갱신은 검수 흐름(`work/review.py`)이 한다.

## 🔴 키는 이 저장소에도 `~/.config` 에도 없다

원전은 프로젝트 `config.json` 의 `redmine_api_key` 를 읽는다. 우리는 그러지 않는다 —
키는 **마스터의 컨테이너 DB** 에만 있다(`docs/10-references.md` §10.1). 그래서:

    ① `.33`(요청자)에는 키가 없다 → 검수 도구는 **본문만 만들고** 마스터를 거친다
       (사용자 결정 2026-08-16: *"마스터 경유 (토큰 인증)"*)
    ② 🔴 **키 값을 로그·문서·커밋에 적지 않는다** — 이 모듈은 값을 절대 반환하지 않는다

## 🔴 조용한 실패를 만들지 않는다 — 원전과 다른 한 곳

원전은 실패 시 `False` 를 돌려준다(*"실패는 silent"*). 우리 σ 감사가 잡는 부류라
**사유 문자열**을 돌려준다 — `report_to_redmine` 이 이미 그 관례다. *"이슈 추적이 안 된 것"*
과 *"게이트가 통과한 것"* 은 다르고, 그 차이가 보이지 않으면 나중에 구분할 수 없다.

## 🔴 상태 이름은 환경마다 다르다 — 그래서 이름→id 를 **동적 조회**한다

원전이 그렇게 해 둔 이유가 우리에게 그대로 적용된다: 이 Redmine 은 **한국어**다
(신규·진행·해결·피드백·완료). ⚠️ 그리고 우리 규약에서 **닫힌 상태는 「완료」뿐이고 「해결」은
아직 열린 것**이다(`CLAUDE.md`). 원전도 finalize 에서 `Closed` 로 보내지 않는다 —
*"Closed 는 사람 결정"*. 두 규약이 같은 방향이므로 기본값을 **해결**로 둔다.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

DEFAULT_URL = "http://192.168.0.57:8080"

# 🔴 **이 Redmine 의 실제 상태 목록** (실측 2026-08-16 — 추측하지 않았다):
#
#     신규(1) · 진행(2) · 해결(3) · 검토(5) · 완료(4 = is_closed)
#
# ⚠️ 처음에 반려 기본값을 「피드백」으로 적어 뒀다가 **실측에 반박당했다** — 그런 상태는
#    없다. 그대로 뒀으면 상태 변경이 **영원히 조용히 건너뛰어졌을** 것이다(코드가 사유는
#    남기지만, 아무도 안 읽는 사유는 없는 것과 같다).
STATUS_ON_FINALIZE = "해결"     # 🔴 「완료」로 보내지 않는다 — 닫는 것은 사람이다(원전과 같은 방향)
# 🔴 **반려에 해당하는 상태가 우리 Redmine 에 없다.** 원전은 `Rejected` 를 쓰지만 그건 그쪽
#    환경의 상태다. 없는 것을 억지로 고르면(예: 「검토」) **상태가 거짓말을 한다** — 반려된
#    일감이 「검토 중」으로 보인다. 그래서 기본은 **상태를 안 바꾸고 코멘트만** 남긴다.
#    ⚠️ 상태를 새로 만들지 말 것 — 트래커·상태 구성은 게임 프로젝트와 공유한다.
STATUS_ON_REJECT = ""
HTTP_TIMEOUT = 30


def base_url() -> str:
    return (os.environ.get("AX_REDMINE_URL") or DEFAULT_URL).rstrip("/")


def api_key(*, reader=None) -> str:
    """API 키. 환경변수 → 컨테이너 DB 순. 🔴 **없으면 빈 문자열** (예외를 던지지 않는다).

    ⚠️ 🔴 **이 값을 로그에 남기지 말 것.** 호출자는 있음/없음만 보고한다.
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

    🔴 id 를 코드에 박지 않는 이유(원전 주석): 환경마다 다르다. 우리는 거기에 하나 더 있다 —
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


def update_issue(issue_id, *, notes: str = "", status_name: str = "", done_ratio=None,
                 key: str = "", url: str = "", sender=None) -> str:
    """기존 이슈에 코멘트·상태·완료율을 붙인다. **사람이 읽을 결과 문자열**을 돌려준다.

    🔴 실패해도 예외를 던지지 않는다 — 검수 흐름은 이것 때문에 멈추면 안 된다. 다만
    **조용히 넘어가지도 않는다**: 무엇이 안 됐는지 문장으로 남는다.
    """
    base = (url or base_url()).rstrip("/")
    k = key or api_key()
    try:
        iid = int(issue_id)
    except (TypeError, ValueError):
        return f"⚠️ 레드마인 갱신 건너뜀 — 이슈 번호가 아니다: {issue_id!r}"
    if sender is None and not k:
        return ("⚠️ 레드마인 갱신 건너뜀 — API 키가 없다 "
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
            # ⚠️ 원전과 같다 — 상태만 건너뛰고 코멘트는 남긴다. 🔴 다만 **말은 한다.**
            status_note = f" (상태 `{status_name}` 은 이 Redmine 에 없어 건너뜀)"
        else:
            issue["status_id"] = sid
    if not issue:
        return "⚠️ 레드마인 갱신 건너뜀 — 바꿀 것이 없다"

    try:
        _request("PUT", f"{base}/issues/{iid}.json", k, {"issue": issue}, sender=sender)
    except urllib.error.HTTPError as e:
        return f"⚠️ 레드마인 #{iid} 갱신 실패 — HTTP {e.code}"
    except Exception as e:                                   # noqa: BLE001
        return f"⚠️ 레드마인 #{iid} 갱신 실패 — {type(e).__name__}: {e}"
    what = ", ".join(k2 for k2 in ("notes", "status_id", "done_ratio") if k2 in issue)
    return f"레드마인 #{iid} 갱신 ({what}){status_note}"
