"""공용 일감 테스트 픽스처 — `#963` T9.

사용자 2026-11-15: 「테스트 플로우를 개선하는게 근본을 고치는거지?」 — 검사들이 일감 상태(스펙·제안·플랜)를
파일마다 **손으로** 만들어서, 흐름에 단계가 하나 늘 때마다(#960 스펙 영역 · #963 플랜 제안) 준비 코드가 있는
모든 검사가 한꺼번에 깨졌다. 이 모듈이 **실제 흐름 함수로** 그 상태를 만든다 — 다음에 흐름이 바뀌면 여기만 고친다.

    iss = FakeIssue(spec_body())                       # 스펙 영역이 있는 일감(인터뷰가 끝난 상태)
    register(iss, 1, tasks)                            # 제안 → 동의 → 등록 (plan_proposal → plan_tools.set_plan)
    iss = issue_with_plan(tasks, checklist=["…"])      # 위 둘을 한 번에

[중요] 거절을 검사하려는 호출(제안 없는 등록 등)은 이 헬퍼를 쓰지 말고 도구를 직접 부른다 — 헬퍼는 「정상
경로로 준비된 상태」만 만든다.
"""
from __future__ import annotations

from master import plan_block as PB
from master import plan_proposal as PP
from master import plan_tools as PT
from master import spec_block as SB

BARE = "## 스펙\n\n요구와 완료 조건\n"
SPEC_CONTENT = "### 문제\n\n확정 스펙"


def spec_body(base: str = BARE, content: str = SPEC_CONTENT) -> str:
    """스펙 영역이 있는 본문 — 착수 전 인터뷰(#960)가 끝난 일감."""
    return SB.put(base, content)


class FakeIssue:
    """Redmine 이슈 하나. 본문은 CRLF 로 저장하고(실측과 같다) 노트는 시간순으로 쌓는다.

    `answer` 를 주면 모든 쓰기가 그 문장을 돌려주고 아무것도 바꾸지 않는다(쓰기 실패 흉내).
    """

    def __init__(self, body: str = "", *, crlf: bool = True, answer: str = "", subject: str = "제목",
                 notes=()):
        self.body = body.replace("\n", "\r\n") if crlf else body
        self.subject = subject
        self.answer = answer
        self.writes: list = []                         # (description | None, notes)
        self.journals = [{"notes": n, "created_on": f"t{i}"} for i, n in enumerate(notes)]

    @property
    def notes(self) -> list[str]:
        return [j["notes"] for j in self.journals]

    def get(self, iid):
        return {"id": iid, "subject": self.subject, "description": self.body, "journals": list(self.journals)}

    def _journal(self, notes: str) -> None:
        if notes:
            self.journals.append({"notes": notes, "created_on": f"t{len(self.journals)}"})

    def update(self, iid, *, description, notes):
        self.writes.append((description, notes))
        if self.answer:
            return self.answer
        self.body = description
        self._journal(notes)
        return f"레드마인 #{iid} 갱신 (notes, description)"

    def note(self, iid, notes):
        self.writes.append((None, notes))
        if self.answer:
            return self.answer
        self._journal(notes)
        return f"레드마인 #{iid} 갱신 (notes)"


def propose(iss: FakeIssue, iid, tasks, *, checklist=(), autonomy=None, why: str = "제안") -> dict:
    return PP.propose(iid, tasks, list(checklist), why, autonomy=autonomy, getter=iss.get, noter=iss.note)


def register(iss: FakeIssue, iid, tasks, why: str = "등록", *, checklist=(), autonomy=None,
             user_answer: str = "동의", **kw) -> dict:
    """정상 경로 — 제안을 남기고 그 목록 그대로 동의를 실어 등록한다."""
    propose(iss, iid, tasks, checklist=checklist, autonomy=autonomy, why=why)
    return PT.set_plan(iid, tasks, why, user_answer=user_answer, getter=iss.get, updater=iss.update, **kw)


def issue_with_plan(tasks, *, iid=1, checklist=(), autonomy=None, base: str = BARE) -> FakeIssue:
    iss = FakeIssue(spec_body(base))
    register(iss, iid, tasks, checklist=checklist, autonomy=autonomy)
    return iss


def plan_of(iss: FakeIssue) -> PB.Plan | None:
    return PB.parse(iss.body)
