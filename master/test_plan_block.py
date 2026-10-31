"""플랜 영역(`#826` T1) 계약 테스트 — [중요] **영역 밖을 건드리지 않는가, 어긋난 형식을 거절하는가.**

실 Redmine 을 두드리지 않는다. 실제 #826 본문 왕복은 따로 잰다(되읽기만, 쓰기 없음).

실행: python3 master/test_plan_block.py   (순수 로직이라 venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import plan_block as PB    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


HEAD = "## 목적\n\n사람이 쓴 스펙 *그대로*\n\n## 플랜\n\n범위: 파일럿\n\n"
TABLE = ("| ID | 상태 | 목표 | 대상 | 선행 | 검증 | 근거 |\n"
         "|---|---|---|---|---|---|---|\n"
         "| T1 | 완료 | 읽기 함수 | master/plan_block.py | — | 단위 검사 | abc1234 |\n"
         "| T2 | 대기 | 상태 전이 | 새 모듈 | T1 | 거절 검사 | |\n"
         "| T3 | 대기 | 진입점 | 새 모듈 | T1·T2 | 경우별 | |\n")
BODY = (HEAD + "<!-- ax:plan:begin v=1 -->\n" + TABLE + "<!-- ax:plan:end -->\n"
        + "\n## 꼬리\n\n뒤에 붙은 사람 글\n")


def _err(fn) -> str:
    try:
        fn()
    except PB.PlanError as e:
        return str(e)
    return ""


def test_parse_reads_tasks():
    plan = PB.parse(BODY)
    check("영역을 찾는다", plan is not None)
    check("태스크 셋", [t.id for t in plan.tasks] == ["T1", "T2", "T3"], str(plan))
    t3 = plan.task("T3")
    check("선행을 목록으로 읽는다", t3.deps == ["T1", "T2"], str(t3))
    check("선행 없음 표기는 빈 목록", plan.task("T1").deps == [])
    check("근거 칸", plan.task("T1").evidence == "abc1234")
    check("없는 ID 는 None", plan.task("T9") is None)


def test_no_region_is_none():
    check("영역이 없으면 None — 오류가 아니다", PB.parse("## 스펙만 있다\n") is None)
    check("빈 본문도 None", PB.parse("") is None)


def test_roundtrip_is_byte_identical():
    for nl in ("\n", "\r\n"):
        body = BODY.replace("\n", nl)
        out = PB.replace(body, PB.parse(body).tasks)
        check(f"읽고 그대로 쓰면 바이트가 같다 ({nl!r})", out == body, repr(out[-200:]))


def test_replace_keeps_outside_bytes():
    for nl in ("\n", "\r\n"):
        body = BODY.replace("\n", nl)
        plan = PB.parse(body)
        plan.task("T2").state = "작업중"
        out = PB.replace(body, plan.tasks)
        before, after = body.split("<!-- ax:plan:end -->")
        o_before, o_after = out.split("<!-- ax:plan:end -->")
        check(f"영역 앞은 그대로 ({nl!r})",
              o_before.split("<!-- ax:plan:begin v=1 -->")[0]
              == before.split("<!-- ax:plan:begin v=1 -->")[0])
        check(f"영역 뒤는 그대로 ({nl!r})", o_after == after)
        check(f"바뀐 상태가 들어간다 ({nl!r})", PB.parse(out).task("T2").state == "작업중")
        if nl == "\r\n":
            check("CRLF 본문에 LF 단독 줄을 섞지 않는다",
                  "\n" not in out.replace("\r\n", ""), repr(out))


def test_pipe_in_cell_roundtrips():
    plan = PB.parse(BODY)
    plan.task("T2").goal = "a | b 를 나눈다"
    out = PB.replace(BODY, plan.tasks)
    check("칸 안 | 는 이스케이프되어 왕복한다",
          PB.parse(out).task("T2").goal == "a | b 를 나눈다", out)


def test_newline_in_cell_is_refused():
    plan = PB.parse(BODY)
    plan.task("T2").goal = "두\n줄"
    check("칸 안 줄바꿈은 거절", "줄바꿈" in _err(lambda: PB.replace(BODY, plan.tasks)))


def test_bad_formats_are_refused():
    begin, end = "<!-- ax:plan:begin v=1 -->", "<!-- ax:plan:end -->"
    cases = {
        "시작 태그 둘": BODY + begin + "\n",
        "끝 태그만": "x\n" + end + "\n",
        "시작 태그만": "x\n" + begin + "\n" + TABLE,
        "끝이 앞": end + "\n" + begin + "\n" + TABLE,
        "모르는 버전": BODY.replace("v=1", "v=2"),
        "머리줄 다름": BODY.replace("| 근거 |\n|---", "| 메모 |\n|---"),
        "구분줄 없음": BODY.replace("|---|---|---|---|---|---|---|\n", ""),
        "칸 수 다름": BODY.replace("| 거절 검사 | |", "| 거절 검사 |"),
        "모르는 상태": BODY.replace("| T2 | 대기 |", "| T2 | 진행 |"),
        "ID 중복": BODY.replace("| T3 | 대기 |", "| T2 | 대기 |"),
        "없는 선행": BODY.replace("| T1·T2 |", "| T1·T7 |"),
        "빈 ID": BODY.replace("| T3 | 대기 |", "|  | 대기 |"),
    }
    for name, body in cases.items():
        msg = _err(lambda b=body: PB.parse(b))
        check(f"{name} → 거절", bool(msg), "통과해 버렸다")


def test_replace_needs_region_append_needs_none():
    tasks = PB.parse(BODY).tasks
    check("영역 없는 본문의 replace 는 거절", "append" in _err(lambda: PB.replace("## 스펙\n", tasks)))
    check("영역 있는 본문의 append 는 거절", "replace" in _err(lambda: PB.append(BODY, tasks)))


def test_append_creates_region():
    for nl in ("\n", "\r\n"):
        spec = "## 스펙\n\n요구 한 줄\n".replace("\n", nl)
        out = PB.append(spec, PB.parse(BODY).tasks)
        check(f"앞 본문 보존 ({nl!r})", out.startswith(spec.rstrip("\r\n")))
        plan = PB.parse(out)
        check(f"붙인 영역을 다시 읽는다 ({nl!r})",
              plan is not None and [t.id for t in plan.tasks] == ["T1", "T2", "T3"])
        if nl == "\r\n":
            check("CRLF 본문에 붙여도 LF 단독 줄이 없다", "\n" not in out.replace("\r\n", ""))
    out = PB.append("", [PB.Task("T1", "대기", "목표")])
    check("빈 본문에도 붙인다", PB.parse(out).task("T1").goal == "목표", out)


def test_render_refuses_unknown_state():
    check("모르는 상태는 쓰지 않는다",
          bool(_err(lambda: PB.render([PB.Task("T1", "진행", "x")]))))


def main() -> int:
    for fn in (test_parse_reads_tasks,
               test_no_region_is_none,
               test_roundtrip_is_byte_identical,
               test_replace_keeps_outside_bytes,
               test_pipe_in_cell_roundtrips,
               test_newline_in_cell_is_refused,
               test_bad_formats_are_refused,
               test_replace_needs_region_append_needs_none,
               test_append_creates_region,
               test_render_refuses_unknown_state):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_plan_block: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
