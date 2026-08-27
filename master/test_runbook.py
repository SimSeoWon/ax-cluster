"""온보딩 런북 (`#256`) — **문서가 실물과 어긋나면 깨진다**.

## 왜 이 테스트가 있나

`#256` 완료 조건: *"산문 설명만 있고 실행할 명령이 없으면 **미완**. 「어느 문서를 보라」로
넘기는 것도 미완"*. 그런데 런북은 시간이 지나면 조용히 낡는다 — 명령 이름이 바뀌고, 단계가
늘고, 도구 인자가 사라진다. 그것을 사람이 눈으로 잡을 수는 없다.

[중요] 실제로 런북을 쓰는 동안 **실행 표면이 없는 자리 둘**이 나왔다(산문으로만 적었으면
안 보였다): `onboard` CLI 가 없었고(라이브러리뿐), MCP 도구가 `role` 을 안 열어 뒀다.
그래서 이 테스트가 재는 것은 *"적힌 명령이 실물로 존재하는가"* 다.

`.venv/bin/python master/test_runbook.py`
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import spec                                     # noqa: E402

DOC = Path(__file__).resolve().parent.parent / "docs" / "14-onboarding-runbook.md"
PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_runbook_exists_and_is_executable() -> None:
    """[중요] `docs/` 에 파일 **하나**가 있고, **명령**이 들어 있다."""
    check("런북이 있다", DOC.is_file(), str(DOC))
    t = _text()
    cmds = re.findall(r"python -m ([\w.]+)", t)
    check("명령이 여럿 적혀 있다", len(cmds) >= 6, f"{len(cmds)}개")
    check("[중요] 산문만이 아니다 — 코드 블록이 있다", t.count("```") >= 8, str(t.count("```")))


def test_every_module_command_is_real() -> None:
    """[중요] **적힌 `python -m X` 가 실물로 존재하고 진입점이 있다.**

    [주의] `onboard` 는 이 검사가 없었다면 계속 없는 명령이었을 것이다 — `run` 의 안내 문구가
    그것을 가리키고 있었는데도(실측 2026-08-23).
    """
    mods = sorted(set(re.findall(r"python -m ([\w.]+)", _text())))
    check("모듈을 읽었다", len(mods) >= 4, str(mods))
    for m in mods:
        try:
            importlib.import_module(m)
            ok = True
        except Exception as e:                              # noqa: BLE001
            ok, why = False, f"{type(e).__name__}: {e}"
        check(f"{m} 를 import 할 수 있다", ok, "" if ok else why)
        if not ok:
            continue
        # 진입점: `__main__.py` 가 있거나 모듈 자체가 `if __name__` 을 갖는다
        parts = m.split(".")
        pkg_main = Path(*parts, "__main__.py")
        mod_file = Path(*parts[:-1], parts[-1] + ".py")
        root = Path(__file__).resolve().parent.parent
        has_entry = (root / pkg_main).is_file() or (
            (root / mod_file).is_file()
            and '__name__ == "__main__"' in (root / mod_file).read_text(encoding="utf-8"))
        check(f"[중요] {m} 에 실행 진입점이 있다", has_entry,
              "라이브러리뿐이라 그 명령은 존재하지 않는다")


def test_every_mcp_tool_named_is_real() -> None:
    """[중요] 런북이 부르는 MCP 도구가 실물이고, **적힌 인자를 받는다.**"""
    import inspect
    from master.projects import mcp_server as M
    t = _text()
    names = sorted(set(re.findall(r"(\w+_tool)\(", t)))
    check("도구 이름을 읽었다", len(names) >= 3, str(names))
    for n in names:
        obj = getattr(M, n, None)
        check(f"{n} 이 있다", obj is not None)
        if obj is None:
            continue
        fn = getattr(obj, "fn", obj)
        params = set(inspect.signature(fn).parameters)
        # 런북이 그 호출에 쓴 키워드가 전부 있어야 한다
        for call in re.findall(rf"{n}\((.*?)\)", t, re.S):
            used = set(re.findall(r"(\w+)\s*=", call))
            missing = used - params
            check(f"[중요] {n} 이 런북의 인자를 받는다", not missing,
                  f"없는 인자 {sorted(missing)} — 문서가 실물과 어긋난다")
    check("[중요] role 을 실제로 열어 뒀다 (사람 기계에 파견되지 않게)",
          "role" in set(inspect.signature(
              getattr(M.set_workshop_tool, "fn", M.set_workshop_tool)).parameters))


def test_every_server_step_is_documented() -> None:
    """[중요] **사양의 단계가 늘면 런북이 깨진다** — `#273` 때 분모가 틀린 사고의 재발 방지.

    실측 2026-08-22: `hook` 단계가 사양에 없어 NS 를 「4/6」으로 보고했다(실제 4/7).
    """
    t = _text()
    for step in spec.SERVER_STEPS:
        check(f"[중요] `{step.key}` 단계가 런북에 있다", f"`{step.key}`" in t,
              "사양에 있는 단계가 문서에 없다")
    check("단계 수를 표로 든다", t.count("| `") >= len(spec.SERVER_STEPS),
          f"{t.count('| `')} < {len(spec.SERVER_STEPS)}")


def _step_table(t: str) -> list[list[str]]:
    """§14.1 서버 단계 표의 **본문 행**만 돌려준다 (헤더·구분선 제외).

    [중요] **범위를 표로 좁힌 이유** (2026-08-28): 종전에는 문서 **전체**에서
    `"안 보이나"`·`"안 됐으면"` 출현 수를 세어 단계 수와 비교했다. 그 프록시는
    **서버 단계와 무관한 절의 산문을 지워도 깨진다** — 실제로 `#320`(상주 철거)으로
    죽은 문장 둘을 클라 절에서 걷어내자 8 < 9 로 실패했다. 잡으려던 것은
    *"사양의 단계가 늘면 런북이 깨진다"*(`#273`)이지 산문의 총량이 아니다.
    """
    rows = []
    for line in t.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != 4 or set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def test_each_step_says_what_you_would_not_see() -> None:
    """[중요] 완료 조건 — 각 단계에 **「안 됐으면 무엇이 안 보이나」**가 붙는다."""
    t = _text()
    rows = _step_table(t)
    check("[중요] 서버 단계 표를 찾았다", bool(rows), "4칸 표가 없다")
    head, body = rows[0], rows[1:]
    check("[중요] 마지막 칸이 「안 됐으면 무엇이 안 보이나」다", "안 보이나" in head[-1],
          f"헤더가 {head[-1]!r} — 이 열이 사라지면 완료 조건이 사라진다")
    check("[중요] 표의 행이 사양의 단계 수와 같다", len(body) == len(spec.SERVER_STEPS),
          f"표 {len(body)}행 vs 사양 {len(spec.SERVER_STEPS)}단계")
    for cells in body:
        check(f"[중요] `{cells[1]}` 단계가 안 되면 무엇이 안 보이는지 적었다",
              len(cells[-1]) >= 10, f"마지막 칸이 비었거나 짧다: {cells[-1]!r}")
    # 침묵으로 실패하는 자리를 명시한다 — 이 프로젝트가 반복해 맞은 부류다
    for phrase in ("침묵", "조용히"):
        check(f"조용한 실패를 말한다 ({phrase})", phrase in t)


def test_it_does_not_delegate_to_other_docs_for_execution() -> None:
    """[중요] *"어느 문서를 보라로 넘기는 것도 미완"* — 실행에 다른 문서가 **필요하지 않다.**

    [주의] *왜* 를 위한 링크는 있어야 한다(두 벌을 만들지 않는 것이 이 저장소 규칙이다).
    구분은 **실행 정보가 링크 뒤에 있는가**다.
    """
    # [주의] **줄바꿈으로 문자열을 끊지 않는다** — 문서는 78열에서 감기고, 그 줄바꿈이
    #    `**필요하지는\n> 않다**` 를 만든다. 문서 검사는 공백을 접고 봐야 한다.
    t = _text()
    #    [주의] 인용 표시(`>`)도 걷어낸다 — 접기만 하면 `**필요하지는 > 않다**` 가 된다.
    flat = re.sub(r"\s+", " ", re.sub(r"(?m)^\s*>\s?", "", t))
    check("실행에 다른 문서가 필요하지 않다고 못박는다",
          "필요하지는 않다" in flat or "필요하지 않다" in flat, "실행 자립성을 선언하지 않았다")
    check("[주의] 그래도 왜 를 위한 포인터는 있다", "12-multi-project" in t and
          "13-request-tagging" in t)
    check("사양의 정본을 코드로 가리킨다 (표를 두 벌로 만들지 않는다)",
          "client/spec.py" in t)
    # 명령 없이 「~를 보라」로만 끝나는 절이 없는지 — 코드 블록이 절마다 있는지로 잰다
    # [주의] **절차 절과 기록 절을 가른다.** 「이 런북이 만들어지며 드러난 구멍」 같은 절은
    #    명령이 없어야 정상이다 — 거기에 명령을 요구하면 규칙이 문서를 왜곡한다.
    #    구분 기준: 제목에 `[주의]`/`[중요]` 가 붙은 절은 기록이다.
    secs = re.split(r"\n## ", t)[1:]
    proc = [s for s in secs if not re.match(r"[\d.]+\s*\[(주의|중요)\]", s)]
    no_cmd = [s.split("\n")[0] for s in proc
              if "```" not in s and "_tool(" not in s]
    check("[중요] 절차 절에 명령이 다 있다", not no_cmd, f"명령 없는 절: {no_cmd}")
    check("[주의] 기록 절도 있다 (구멍을 적어 둔다)", len(proc) < len(secs),
          "기록 절이 없으면 왜 그렇게 됐는지가 사라진다")


if __name__ == "__main__":
    for fn in (test_runbook_exists_and_is_executable, test_every_module_command_is_real,
               test_every_mcp_tool_named_is_real, test_every_server_step_is_documented,
               test_each_step_says_what_you_would_not_see,
               test_it_does_not_delegate_to_other_docs_for_execution):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_runbook: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
