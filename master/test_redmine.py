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


# ── 마일스톤·부모 스탬프 (`#303`) ────────────────────────────────
# [중요] 원전에 없던 추가라 계약을 여기서 못박는다: **못 붙으면 사유가 보인다.**

class VerSender(Sender):
    """버전 카탈로그까지 답하는 전송. `versions.json` 이 프로젝트별 경로인 것이 요점이다."""

    def __init__(self, versions=("마일스톤 6 — 개선·확장",), **kw):
        super().__init__(**kw)
        self.versions = versions

    def __call__(self, method, url, payload=None):
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


def main() -> int:
    for fn in (test_updates_notes_only, test_status_name_resolved_dynamically,
               test_unknown_status_keeps_notes_and_says_so, test_default_status_names_are_ours,
               test_nothing_to_change, test_bad_issue_id,
               test_http_failure_is_reported_not_raised, test_missing_key_is_loud,
               test_api_key_never_returned_from_logs,
               test_create_stamps_version_and_parent,
               test_create_unknown_version_is_skipped_loudly,
               test_create_bad_parent_is_skipped_loudly,
               test_update_can_stamp_without_notes,
               test_update_version_needs_right_project):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_redmine: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
