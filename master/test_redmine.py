"""Redmine 이슈 갱신 이식(`#135`) 계약 테스트 — [중요] **조용히 실패하지 않는가.**

원전은 실패 시 `False` 하나를 돌려준다(*"실패는 silent"*). 이슈 추적이 안 된 것과 게이트가
통과한 것은 다르고, 그 차이가 안 보이면 나중에 구분할 수 없다. 그래서 우리는 **사유 문자열**을
돌려주고, 이 파일이 그 계약을 잰다. [중요] 실 Redmine 을 두드리지 않는다 — `sender` 주입.

실행: python3 master/test_redmine.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import redmine as RM       # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Sender:
    """호출을 기록하는 가짜 전송. 한국어 상태 목록을 돌려준다 — 이 Redmine 이 그렇다."""

    def __init__(self, statuses=("신규", "진행", "해결", "피드백", "완료"), boom=None):
        self.calls: list = []
        self.statuses = statuses
        self.boom = boom

    def __call__(self, method, url, payload=None):
        self.calls.append((method, url, payload))
        if self.boom is not None:
            raise self.boom
        if url.endswith("/issue_statuses.json"):
            return {"issue_statuses": [{"id": i + 1, "name": n}
                                       for i, n in enumerate(self.statuses)]}
        return {}

    @property
    def puts(self):
        return [(u, p) for m, u, p in self.calls if m == "PUT"]


def test_updates_notes_only():
    s = Sender()
    out = RM.update_issue(42, notes="반려합니다", sender=s)
    check("갱신 결과를 문장으로 돌려준다", "레드마인 #42 갱신" in out, out)
    check("PUT 한 번", len(s.puts) == 1, str(s.calls))
    url, payload = s.puts[0]
    check("이슈 번호가 URL 에 들어간다", url.endswith("/issues/42.json"), url)
    check("코멘트가 실린다", payload["issue"]["notes"] == "반려합니다", str(payload))
    check("[중요] 상태를 안 줬으면 건드리지 않는다", "status_id" not in payload["issue"], str(payload))


def test_status_name_resolved_dynamically():
    """[중요] id 를 박지 않는다 — 이 Redmine 의 상태 이름은 **한국어**다."""
    s = Sender()
    out = RM.update_issue(7, notes="완료", status_name="해결", done_ratio=100, sender=s)
    _, payload = s.puts[0]
    check("이름을 id 로 바꿔 싣는다", payload["issue"].get("status_id") == 3, str(payload))
    check("완료율도 실린다", payload["issue"].get("done_ratio") == 100)
    check("무엇을 바꿨는지 말한다", "status_id" in out and "done_ratio" in out, out)


def test_unknown_status_keeps_notes_and_says_so():
    """[주의] 원전처럼 상태만 건너뛴다 — [중요] 다만 **말은 한다**(원전은 조용하다)."""
    s = Sender()
    out = RM.update_issue(7, notes="코멘트", status_name="Resolved", sender=s)
    _, payload = s.puts[0]
    check("코멘트는 그대로 남는다", payload["issue"].get("notes") == "코멘트")
    check("[중요] 없는 상태는 안 싣는다", "status_id" not in payload["issue"], str(payload))
    check("[중요] 건너뛴 사실을 문장에 남긴다", "건너뜀" in out and "Resolved" in out, out)


def test_default_status_names_are_ours():
    """[중요] 실측 2026-08-16: 이 Redmine 은 신규·진행·해결·검토·완료 뿐이다."""
    real = {"신규", "진행", "해결", "검토", "완료"}
    check("🔴 **finalize 는 「완료」로 닫는다** (사용자 2026-09-04) — 마감이 분산 작업의 "
          "끝이고, 그 호출은 사람의 승인으로만 돈다",
          RM.STATUS_ON_FINALIZE == "완료", RM.STATUS_ON_FINALIZE)
    check("[중요] finalize 기본이 **실재하는** 상태다",
          RM.STATUS_ON_FINALIZE in real, RM.STATUS_ON_FINALIZE)
    check("[중요] 반려 기본은 상태를 안 바꾼다 (해당 상태가 없다)",
          RM.STATUS_ON_REJECT == "", repr(RM.STATUS_ON_REJECT))
    # 없는 상태를 기본값으로 두면 조용히 건너뛴다 — 그 회귀를 막는다
    check("[중요] 기본값 중 실재하지 않는 이름이 없다",
          all(n in real for n in (RM.STATUS_ON_FINALIZE, RM.STATUS_ON_REJECT) if n))


def test_nothing_to_change():
    s = Sender()
    out = RM.update_issue(7, sender=s)
    check("바꿀 게 없으면 부르지 않는다", not s.puts, str(s.calls))
    check("그 사실을 말한다", "바꿀 것이 없다" in out, out)


def test_bad_issue_id():
    s = Sender()
    out = RM.update_issue("삼십", notes="x", sender=s)
    check("이슈 번호가 아니면 시작도 안 한다", not s.calls, str(s.calls))
    check("사유를 말한다", "이슈 번호가 아니다" in out, out)


def test_http_failure_is_reported_not_raised():
    s = Sender(boom=RuntimeError("연결 끊김"))
    out = RM.update_issue(7, notes="x", sender=s)
    check("[중요] 예외를 던지지 않는다 (검수 흐름을 막지 않는다)", isinstance(out, str))
    check("[중요] 실패를 문장으로 남긴다", "실패" in out and "#7" in out, out)


def test_missing_key_is_loud():
    """[중요] 키가 없을 때 **조용히 성공처럼** 끝나지 않는다."""
    import os
    old = os.environ.pop("AX_REDMINE_API_KEY", None)
    try:
        out = RM.update_issue(7, notes="x", key="", url="http://127.0.0.1:9",
                              # sender 없음 = 기본 전송 → 키 검사가 걸린다
                              )
        check("키가 없으면 사유를 돌려준다", "API 키가 없다" in out or "실패" in out, out)
        check("[중요] 결과에 '갱신' 만 적히지 않는다", not out.startswith("레드마인 #7 갱신"), out)
    finally:
        if old is not None:
            os.environ["AX_REDMINE_API_KEY"] = old


def test_api_key_never_returned_from_logs():
    """[중요] 키 조회는 **주입 가능**해야 테스트가 실 컨테이너를 안 두드린다."""
    got = RM.api_key(reader=lambda: "  SECRET  ")
    check("주입한 리더에서 읽는다", got == "SECRET", repr(got))
    check("빈 값도 안전", RM.api_key(reader=lambda: None) == "")


# ── 우선순위·제목·본문 (`#752`) ──────────────────────────────────
# 비우면 안 바꾼다 — 기존 호출자의 페이로드가 그대로인 것까지 잰다.

class PriSender(Sender):
    """우선순위 카탈로그(enumerations)까지 답하는 전송."""

    def __call__(self, method, url, payload=None):
        if url.endswith("/enumerations/issue_priorities.json"):
            self.calls.append((method, url, payload))
            return {"issue_priorities": [{"id": 1, "name": "낮음"}, {"id": 2, "name": "보통"},
                                         {"id": 3, "name": "높음"}]}
        return super().__call__(method, url, payload)


def test_update_priority_resolved():
    s = PriSender()
    out = RM.update_issue(752, notes="올림", priority_name="높음", sender=s)
    _, payload = s.puts[0]
    check("우선순위 이름을 id 로 바꿔 싣는다", payload["issue"].get("priority_id") == 3,
          str(payload))
    check("무엇을 바꿨는지 말한다 (priority_id)", "priority_id" in out, out)


def test_update_unknown_priority_keeps_notes_and_says_so():
    s = PriSender()
    out = RM.update_issue(752, notes="코멘트", priority_name="긴급", sender=s)
    check("PUT 은 나간다", len(s.puts) == 1, str(s.calls))
    _, payload = s.puts[0]
    check("코멘트는 그대로 남는다", payload["issue"].get("notes") == "코멘트", str(payload))
    check("[중요] 없는 우선순위는 안 싣는다", "priority_id" not in payload["issue"], str(payload))
    check("[중요] 건너뛴 사실을 문장에 남긴다", "건너뜀" in out and "긴급" in out, out)


def test_update_unknown_priority_alone_is_nothing_to_change():
    s = PriSender()
    out = RM.update_issue(752, priority_name="긴급", sender=s)
    check("바꿀 것이 없으면 PUT 하지 않는다", not s.puts, str(s.calls))
    check("사유가 함께 보인다", "바꿀 것이 없다" in out and "긴급" in out, out)


def test_update_unknown_status_alone_is_nothing_to_change():
    s = Sender()
    out = RM.update_issue(752, status_name="없는상태", sender=s)
    check("바꿀 것이 없으면 PUT 하지 않는다", not s.puts, str(s.calls))
    check("[중요] 건너뛴 상태 사유가 함께 보인다 (R68-1)",
          "바꿀 것이 없다" in out and "없는상태" in out, out)


def test_update_subject_trimmed_and_limited():
    s = Sender()
    out = RM.update_issue(752, subject="  새 제목  ", sender=s)
    _, payload = s.puts[0]
    check("제목은 앞뒤 공백을 걷는다", payload["issue"].get("subject") == "새 제목", str(payload))
    check("notes 없이도 제목만으로 갱신된다", "notes" not in payload["issue"], str(payload))
    check("무엇을 바꿨는지 말한다 (subject)", "subject" in out, out)
    s = Sender()
    RM.update_issue(752, subject="가" * 300, sender=s)
    check("제목은 250자에서 자른다 (create_issue 와 같다)",
          len(s.puts[0][1]["issue"]["subject"]) == 250)
    s = Sender()
    out = RM.update_issue(752, subject="   ", sender=s)
    check("공백뿐인 제목은 안 바꾼다", not s.puts and "바꿀 것이 없다" in out, out)


def test_update_description_replaces_body():
    s = Sender()
    body = "## 목표\n본문 전체"
    out = RM.update_issue(752, notes="본문 교체", description=body, sender=s)
    _, payload = s.puts[0]
    check("본문이 그대로 실린다", payload["issue"].get("description") == body, str(payload))
    check("무엇을 바꿨는지 말한다 (description)", "description" in out, out)


def test_update_omitted_new_fields_payload_unchanged():
    """[중요] 기존 호출자 — 새 필드를 안 주면 페이로드가 종전과 같다."""
    s = PriSender()
    RM.update_issue(7, notes="완료", status_name="해결", done_ratio=100, sender=s)
    _, payload = s.puts[0]
    check("페이로드 키가 종전과 같다",
          set(payload["issue"]) == {"notes", "status_id", "done_ratio"}, str(payload))
    check("우선순위 조회를 하지 않는다",
          not any("issue_priorities" in u for _m, u, _p in s.calls), str(s.calls))


# ── 마일스톤·부모 스탬프 (`#303`) ────────────────────────────────
# [중요] 원전에 없던 추가라 계약을 여기서 못박는다: **못 붙으면 사유가 보인다.**

class VerSender(Sender):
    """버전 카탈로그까지 답하는 전송. `versions.json` 이 프로젝트별 경로인 것이 요점이다."""

    def __init__(self, versions=("마일스톤 6 — 개선·확장",), issue_count=0, **kw):
        super().__init__(**kw)
        self.versions = versions
        self.issue_count = issue_count      # `#652` — 삭제 판정이 쓰는 수

    def __call__(self, method, url, payload=None):
        if "/issues.json?" in url and method == "GET":
            self.calls.append((method, url, payload))
            n = getattr(self, "issue_count", 0)
            return {"total_count": n,
                    "issues": [{"id": 900 + j} for j in range(min(n, 10))]}
        if "/versions/" in url and method == "DELETE":
            self.calls.append((method, url, payload))
            return {}
        if "/versions/" in url and method == "PUT":
            self.calls.append((method, url, payload))
            return {}
        if "/versions.json" in url and method == "POST":
            # `#652` — 버전 생성. 실 Redmine 과 같은 모양으로 답한다
            self.calls.append((method, url, payload))
            return {"version": {"id": 88, "name": (payload or {}).get("version", {}).get("name")}}
        if "/versions.json" in url:
            self.calls.append((method, url, payload))
            return {"versions": [{"id": 70 + i, "name": n}
                                 for i, n in enumerate(self.versions)]}
        if url.endswith("/issues.json") and method == "POST":
            self.calls.append((method, url, payload))
            return {"issue": {"id": 999}}
        return super().__call__(method, url, payload)

    @property
    def posts(self):
        return [(u, p) for m, u, p in self.calls if m == "POST"]


def test_create_stamps_version_and_parent():
    s = VerSender()
    out = RM.create_issue("제목", "본문", fixed_version="마일스톤 6",
                          parent_issue_id=304, project="modularstage", sender=s)
    check("생성 id 를 돌려준다", out.get("id") == 999, str(out))
    check("[중요] 못 붙은 것이 없으면 skipped 를 달지 않는다", "skipped" not in out, str(out))
    iss = s.posts[0][1]["issue"]
    check("부분 일치로 버전 id 를 붙인다", iss.get("fixed_version_id") == 70, str(iss))
    check("부모를 붙인다", iss.get("parent_issue_id") == 304, str(iss))
    vurl = [u for m, u, _ in s.calls if "/versions.json" in u][0]
    check("[중요] 버전은 프로젝트 경로에서 찾는다",
          "/projects/modularstage/versions.json" in vurl, vurl)


def test_create_unknown_version_is_skipped_loudly():
    s = VerSender(versions=("마일스톤 2 — 디지털 트윈 복원",))
    out = RM.create_issue("제목", fixed_version="마일스톤 6", sender=s)
    check("생성 자체는 막지 않는다", out.get("id") == 999, str(out))
    check("[중요] 사유가 실린다", any("마일스톤" in x for x in out.get("skipped") or []), str(out))
    iss = s.posts[0][1]["issue"]
    check("없는 버전은 필드를 안 넣는다", "fixed_version_id" not in iss, str(iss))


def test_create_bad_parent_is_skipped_loudly():
    s = VerSender()
    out = RM.create_issue("제목", parent_issue_id="부모아님", sender=s)
    check("이슈 번호가 아니면 그 필드만 생략", "parent_issue_id" not in s.posts[0][1]["issue"])
    check("[중요] 조용히 넘어가지 않는다",
          any("부모" in x for x in out.get("skipped") or []), str(out))


def test_update_can_stamp_without_notes():
    s = VerSender()
    out = RM.update_issue(305, fixed_version="마일스톤 6", parent_issue_id=304,
                          project="modularstage", sender=s)
    check("코멘트 없이도 갱신이 성립한다", "갱신 건너뜀" not in out, out)
    iss = s.puts[0][1]["issue"]
    check("버전이 실린다", iss.get("fixed_version_id") == 70, str(iss))
    check("부모가 실린다", iss.get("parent_issue_id") == 304, str(iss))
    check("무엇을 바꿨는지 문장에 적는다", "fixed_version_id" in out, out)


def test_update_version_needs_right_project():
    """[주의] 기본 프로젝트로 남의 프로젝트 버전을 찾으면 못 찾는다 — 그 사실이 보여야 한다."""
    s = VerSender(versions=("마일스톤 1 — 입력·UI 토대 (게임패드)",))
    out = RM.update_issue(302, notes="유지 결정", fixed_version="마일스톤 6", sender=s)
    check("코멘트는 그대로 실린다", s.puts[0][1]["issue"].get("notes") == "유지 결정")
    check("[중요] 못 찾았다고 말한다", "찾지 못해 생략" in out, out)


# ── 🔴 마일스톤 생성 (`#652`) — `.33` 에 이 경로가 없어 관리가 통째로 멈췄다 ──────────

def test_create_version_posts_to_that_project():
    """[중요] **버전은 프로젝트에 속한다** — POST 경로에 프로젝트가 들어가야 한다."""
    s = VerSender()
    out = RM.create_version("마일스톤 2 — 전투 재설계", project="ns",
                            due_date="2026-12-01", sender=s)
    check("id 를 돌려준다", out.get("id") == 88, str(out))
    check("새로 만들었다고 말한다", out.get("existing") is False, str(out))
    posts = [(u, p) for u, p in s.posts if "/versions.json" in u]
    check("[중요] 그 프로젝트 경로로 간다", posts and "/projects/ns/versions.json" in posts[0][0],
          str(posts)[:140])
    ver = posts[0][1]["version"] if posts else {}
    check("이름·마감일·상태가 실린다",
          ver.get("name") == "마일스톤 2 — 전투 재설계" and ver.get("due_date") == "2026-12-01"
          and ver.get("status") == "open", str(ver))


def test_create_version_does_not_duplicate():
    """🔴 **동명은 만들지 않는다** — 버전은 이름으로 참조되고, 둘이면 어디 붙었는지 모른다."""
    s = VerSender(versions=("마일스톤 6 — 개선·확장",))
    out = RM.create_version("마일스톤 6 — 개선·확장", project="modularstage", sender=s)
    check("있는 것의 id 를 돌려준다", out.get("id") == 70, str(out))
    check("[중요] 이미 있다고 말한다", out.get("existing") is True, str(out))
    check("🔴 POST 는 0회다", not [u for u, _ in s.posts if "/versions.json" in u],
          str(s.posts)[:140])


def test_create_version_partial_name_is_not_a_duplicate():
    """[주의] 충돌 판정은 **정확 일치**다 — 부분 일치를 쓰면 「마일스톤 1」이 「마일스톤 10」에
    막힌다. `resolve_version_id` 의 규칙을 여기 끌어오지 않는 이유가 이것이다."""
    s = VerSender(versions=("마일스톤 10 — 나중",))
    out = RM.create_version("마일스톤 1", project="ns", sender=s)
    check("막히지 않고 만들어진다", out.get("existing") is False, str(out))


def test_create_version_bad_input_is_loud():
    """[중요] 422 를 받기 전에 **여기서** 말한다 — 깊은 곳의 HTTP 코드는 고칠 근거가 없다."""
    s = VerSender()
    check("이름이 비면 거절", "비었다" in RM.create_version("", project="ns", sender=s).get("error", ""))
    check("프로젝트가 비면 거절",
          "project" in RM.create_version("M", project="", sender=s).get("error", ""))
    bad = RM.create_version("M", project="ns", due_date="2026/12/01", sender=s)
    check("마감일 형식을 먼저 잡는다", "YYYY-MM-DD" in bad.get("error", ""), str(bad))
    st = RM.create_version("M", project="ns", status="열림", sender=s)
    check("모르는 status 를 잡는다", "open" in st.get("error", ""), str(st))
    check("🔴 거절되면 POST 가 0회다", not [u for u, _ in s.posts if "/versions.json" in u],
          str(s.posts)[:140])


def test_create_version_description_limit_is_measured():
    """🔴 **255 는 실측값이다** (`#652`, 2026-09-20) — 256 을 보내면 레드마인이 422 로
    거절한다. 자르지 않고 **거절한다**: 마일스톤 설명은 규약을 적는 자리라 조용히 잘리면
    규약이 반쪽이 된다."""
    s = VerSender()
    ok = RM.create_version("M", project="ns", description="가" * RM.DESCRIPTION_MAX, sender=s)
    check("한계까지는 통과한다", ok.get("id") == 88, str(ok))
    over = RM.create_version("M2", project="ns", description="가" * (RM.DESCRIPTION_MAX + 1),
                             sender=s)
    check("[중요] 넘으면 거절하고 길이를 말한다",
          "256자" in over.get("error", "") and "255" in over.get("error", ""), str(over))
    posts = [u for u, _ in s.posts if "/versions.json" in u]
    check("🔴 거절된 쪽은 POST 가 안 나간다", len(posts) == 1, str(posts))


def test_http_error_carries_redmine_reason():
    """🔴 **422 본문을 버리지 않는다** (`#652`). 종전에는 `HTTP 422` 만 돌려줘서 무엇이
    틀렸는지 알 수 없었다 — 이 함수의 독스트링이 *"깊은 곳의 HTTP 422 는 무엇이 틀렸는지
    알려 주지 않는다"* 고 적어 놓고 정작 그러고 있었다."""
    import urllib.error
    import io

    class Boom(Sender):
        def __call__(self, method, url, payload=None):
            if "/versions.json" in url and method == "POST":
                raise urllib.error.HTTPError(
                    url, 422, "Unprocessable", {},
                    io.BytesIO('{"errors":["설명 은 너무 깁니다 (최대 255자 까지)"]}'
                               .encode("utf-8")))
            if "/versions.json" in url:
                return {"versions": []}
            return super().__call__(method, url, payload)

    out = RM.create_version("M", project="ns", sender=Boom())
    check("코드를 유지한다", "422" in out.get("error", ""), str(out))
    check("[중요] 레드마인이 준 사유가 실린다", "너무 깁니다" in out.get("error", ""), str(out))

    class Weird(Boom):
        def __call__(self, method, url, payload=None):
            if "/versions.json" in url and method == "POST":
                raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b"<html>nope"))
            return Sender.__call__(self, method, url, payload) if "/versions.json" not in url \
                else {"versions": []}

    w = RM.create_version("M", project="ns", sender=Weird())
    check("[주의] JSON 이 아니어도 원래 코드를 잃지 않는다", "500" in w.get("error", ""), str(w))


def test_meta_versions_follow_the_project():
    """🔴 **`#652` 의 뿌리** — `meta` 가 늘 AX 프로젝트의 버전을 돌려줬다. `ns` 작업장이
    마일스톤을 물으면 남의 것 6개가 오고 자기 것은 안 보였다(실측 2026-09-20)."""
    s = VerSender(versions=("마일스톤 1 — 입력·UI 토대 (게임패드)",))
    out = RM.meta(project="ns", sender=s)
    names = [v["name"] for v in out.get("versions") or []]
    check("그 프로젝트의 버전이 온다", names == ["마일스톤 1 — 입력·UI 토대 (게임패드)"], str(names))
    check("[중요] 무엇을 봤는지 말한다", out.get("versions_project") == "ns", str(out.get("versions_project")))
    gets = [u for m, u, _ in s.calls if m == "GET" and "/versions.json" in u]
    check("🔴 조회 경로가 그 프로젝트다", gets and "/projects/ns/versions.json" in gets[0], str(gets))


# ── 🔴 마일스톤 수정 (`#652` 후속) — 이름을 바꾸는 자리라 판정이 더 엄하다 ──────────

def _puts(sender):
    return [(u, p) for m, u, p in sender.calls if m == "PUT"]


def test_update_version_renames_by_exact_name():
    s = VerSender(versions=("마일스톤 1 — 기본 전투 구조",))
    out = RM.update_version("마일스톤 1 — 기본 전투 구조", project="ns",
                            new_name="마일스톤 1 — 전투 토대", sender=s)
    check("바뀐 것을 말한다", out.get("changed") and "name" in out["changed"][0], str(out))
    check("새 이름을 돌려준다", out.get("name") == "마일스톤 1 — 전투 토대", str(out))
    u, pay = _puts(s)[0]
    check("[중요] 그 버전 id 로 PUT 한다", u.endswith("/versions/70.json"), u)
    check("이름만 싣는다 (안 준 필드는 안 건드린다)",
          pay["version"] == {"name": "마일스톤 1 — 전투 토대"}, str(pay))


def test_update_version_refuses_partial_match():
    """🔴 **이름을 바꾸는 자리에서 부분 일치는 안 된다** — 「마일스톤 1」로 「마일스톤 10」을
    고치면 무엇이었는지 아무도 모른다. `resolve_version_id` 의 규칙을 여기 끌어오지 않는다."""
    s = VerSender(versions=("마일스톤 10 — 나중",))
    out = RM.update_version("마일스톤 1", project="ns", new_name="X", sender=s)
    check("[중요] 부분 일치로 안 잡힌다", "없다" in out.get("error", ""), str(out))
    check("  있는 이름을 알려 준다", out.get("available") == ["마일스톤 10 — 나중"], str(out))
    check("🔴 PUT 이 안 나간다", not _puts(s), str(_puts(s)))


def test_update_version_refuses_name_clash():
    s = VerSender(versions=("A", "B"))
    out = RM.update_version("A", project="ns", new_name="B", sender=s)
    check("[중요] 이미 있는 이름으로 못 바꾼다", "이미 있다" in out.get("error", ""), str(out))
    check("🔴 PUT 이 안 나간다", not _puts(s), str(_puts(s)))


def test_update_version_none_keeps_empty_clears():
    """[주의] **빈 문자열을 「안 바꿈」으로 접으면 지울 방법이 없어진다.**"""
    s = VerSender(versions=("A",))
    RM.update_version("A", project="ns", description="새 설명", sender=s)
    check("설명을 준 대로 싣는다", _puts(s)[0][1]["version"] == {"description": "새 설명"},
          str(_puts(s)[0][1]))
    s2 = VerSender(versions=("A",))
    RM.update_version("A", project="ns", due_date="", sender=s2)
    check("[중요] 빈 문자열은 **비운다**(null)",
          _puts(s2)[0][1]["version"] == {"due_date": None}, str(_puts(s2)[0][1]))
    s3 = VerSender(versions=("A",))
    out = RM.update_version("A", project="ns", sender=s3)
    check("아무것도 안 주면 거절한다", "바꿀 것이 없다" in out.get("error", ""), str(out))
    check("🔴 그때 PUT 이 안 나간다", not _puts(s3), str(_puts(s3)))


def test_update_version_gates_are_the_same_as_create():
    """[중요] 생성과 **같은 게이트**를 쓴다 — 두 벌로 쓰면 한쪽만 느슨해진다."""
    s = VerSender(versions=("A",))
    bad = RM.update_version("A", project="ns", due_date="2026/12/01", sender=s)
    check("마감일 형식", "YYYY-MM-DD" in bad.get("error", ""), str(bad))
    long = RM.update_version("A", project="ns", description="가" * (RM.DESCRIPTION_MAX + 1),
                             sender=s)
    check("설명 길이", "255" in long.get("error", ""), str(long))
    st = RM.update_version("A", project="ns", status="열림", sender=s)
    check("status 값", "open" in st.get("error", ""), str(st))
    check("🔴 거절되면 PUT 이 0회다", not _puts(s), str(_puts(s)))


# ── 🔴 마일스톤 삭제 (`#652` 후속) — 되돌릴 수 없는 유일한 조작 ────────────────────

def _dels(sender):
    return [u for m, u, _ in sender.calls if m == "DELETE"]


def test_delete_version_needs_confirm():
    """🔴 **`confirm=False` 가 기본이다** — `finalize_work`·`advance_work` 와 같은 관례.
    버전에는 변경 이력이 없어 지우고 나면 무엇이었는지 남는 곳이 로그뿐이다."""
    s = VerSender(versions=("버릴 것",), issue_count=0)
    out = RM.delete_version("버릴 것", project="ns", sender=s)
    check("[중요] 승인을 요구한다", out.get("confirm_required") is True, str(out))
    check("  무엇이 지워지는지 말한다", out.get("id") == 70 and out.get("issue_count") == 0,
          str(out))
    check("🔴 DELETE 가 안 나간다", not _dels(s), str(_dels(s)))

    s2 = VerSender(versions=("버릴 것",), issue_count=0)
    out2 = RM.delete_version("버릴 것", project="ns", confirm=True, sender=s2)
    check("승인하면 지운다", out2.get("deleted") is True, str(out2))
    check("  그 버전 id 로 DELETE 한다", _dels(s2) and _dels(s2)[0].endswith("/versions/70.json"),
          str(_dels(s2)))


def test_delete_version_refuses_when_issues_attached():
    """🔴 **붙은 이슈가 있으면 거절한다.** 레드마인도 422 로 막지만 그 응답은 **본문이
    비어 있다**(실측 2026-09-20) — 사유를 여기서 만든다. [주의] **대신 떼어 주지 않는다.**"""
    s = VerSender(versions=("쓰는 것",), issue_count=17)
    out = RM.delete_version("쓰는 것", project="ns", confirm=True, sender=s)
    check("[중요] 건수를 말한다", out.get("issue_count") == 17 and "17건" in out.get("error", ""),
          str(out))
    check("  어느 이슈인지 표본을 준다", len(out.get("sample_issue_ids") or []) == 10, str(out))
    check("🔴 승인했어도 DELETE 가 안 나간다", not _dels(s), str(_dels(s)))


def test_delete_version_unknown_count_is_not_zero():
    """🔴 **미확인은 통과가 아니다** — 못 센 것을 0 으로 접으면 「붙은 게 없다」로 읽혀 지운다."""
    class NoCount(VerSender):
        def __call__(self, method, url, payload=None):
            if "/issues.json?" in url:
                raise OSError("네트워크")
            return super().__call__(method, url, payload)

    s = NoCount(versions=("버릴 것",))
    out = RM.delete_version("버릴 것", project="ns", confirm=True, sender=s)
    check("[중요] 세지 못하면 거절한다", "세지 못했다" in out.get("error", ""), str(out))
    check("🔴 DELETE 가 안 나간다", not _dels(s), str(_dels(s)))


def test_delete_version_exact_match_only():
    """[주의] 지우는 자리에서 부분 일치를 허용하면 「마일스톤 1」을 지우려다 「마일스톤 10」을 지운다."""
    s = VerSender(versions=("마일스톤 10 — 나중",))
    out = RM.delete_version("마일스톤 1", project="ns", confirm=True, sender=s)
    check("부분 일치로 안 잡힌다", "없다" in out.get("error", ""), str(out))
    check("  있는 이름을 알려 준다", out.get("available") == ["마일스톤 10 — 나중"], str(out))
    check("🔴 DELETE 가 안 나간다", not _dels(s), str(_dels(s)))


def test_delete_version_empty_422_still_says_something():
    """[주의] 실측: 붙은 이슈가 있을 때의 422 는 **본문이 비어 있다.** 세는 사이에 누가
    붙이면(경합) 여기로 오는데, 그때도 빈 사유를 내보내지 않는다."""
    import urllib.error
    import io

    class Race(VerSender):
        def __call__(self, method, url, payload=None):
            if "/versions/" in url and method == "DELETE":
                raise urllib.error.HTTPError(url, 422, "", {}, io.BytesIO(b""))
            return super().__call__(method, url, payload)

    out = RM.delete_version("버릴 것", project="ns", confirm=True,
                            sender=Race(versions=("버릴 것",), issue_count=0))
    check("코드를 유지한다", "422" in out.get("error", ""), str(out))
    check("[중요] 빈 본문에도 사유를 만든다", "이슈가 붙었다" in out.get("error", ""), str(out))


def main() -> int:
    for fn in (test_updates_notes_only, test_status_name_resolved_dynamically,
               test_unknown_status_keeps_notes_and_says_so, test_default_status_names_are_ours,
               test_nothing_to_change, test_bad_issue_id,
               test_http_failure_is_reported_not_raised, test_missing_key_is_loud,
               test_api_key_never_returned_from_logs,
               test_update_priority_resolved,
               test_update_unknown_priority_keeps_notes_and_says_so,
               test_update_unknown_priority_alone_is_nothing_to_change,
               test_update_unknown_status_alone_is_nothing_to_change,
               test_update_subject_trimmed_and_limited,
               test_update_description_replaces_body,
               test_update_omitted_new_fields_payload_unchanged,
               test_create_stamps_version_and_parent,
               test_create_unknown_version_is_skipped_loudly,
               test_create_bad_parent_is_skipped_loudly,
               test_update_can_stamp_without_notes,
               test_update_version_needs_right_project,
               test_create_version_posts_to_that_project,
               test_create_version_does_not_duplicate,
               test_create_version_partial_name_is_not_a_duplicate,
               test_create_version_bad_input_is_loud,
               test_create_version_description_limit_is_measured,
               test_http_error_carries_redmine_reason,
               test_meta_versions_follow_the_project,
               test_update_version_renames_by_exact_name,
               test_update_version_refuses_partial_match,
               test_update_version_refuses_name_clash,
               test_update_version_none_keeps_empty_clears,
               test_update_version_gates_are_the_same_as_create,
               test_delete_version_needs_confirm,
               test_delete_version_refuses_when_issues_attached,
               test_delete_version_unknown_count_is_not_zero,
               test_delete_version_exact_match_only,
               test_delete_version_empty_422_still_says_something):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_redmine: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
