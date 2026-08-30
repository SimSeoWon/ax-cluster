"""`.uproject` 에디터 플러그인 (`#335`).

[중요] **이 테스트가 지키는 것은 두 계약이다** — ⑴ 선언이 비면 아무것도 하지 않는다(비-UE5
프로젝트의 파일을 조용히 만들지 않는다) ⑵ `TargetAllowList` 없이 켜지 않는다(안 묶으면
**인증 없는 MCP 서버가 패키징에 실려 나간다**).

`python3 master/test_uproject.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import spec, uproject as U                # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


BASE = json.dumps({"FileVersion": 3, "EngineAssociation": "5.8",
                   "Modules": [{"Name": "NS", "Type": "Runtime"}],
                   "Plugins": [{"Name": "ModelingToolsEditorMode", "Enabled": True}]}, indent=4)


def test_merge() -> None:
    plugins = ({"name": "ModelContextProtocol", "targets": ("Editor",)},
               {"name": "EditorToolset", "targets": ("Editor",)})
    body, changed = U.merge(BASE, plugins)
    got = json.loads(body)
    names = [p["Name"] for p in got["Plugins"]]
    check("[중요] 사람이 켠 플러그인은 보존된다", "ModelingToolsEditorMode" in names, str(names))
    check("둘 다 들어간다", changed == ("ModelContextProtocol", "EditorToolset"), str(changed))
    mcp = next(p for p in got["Plugins"] if p["Name"] == "ModelContextProtocol")
    check("[중요] TargetAllowList=Editor 로 묶인다 — 안 묶으면 패키징에 실린다",
          mcp.get("TargetAllowList") == ["Editor"], str(mcp))
    check("Enabled 는 참", mcp.get("Enabled") is True, str(mcp))
    check("나머지 키는 그대로", got.get("EngineAssociation") == "5.8", str(got)[:80])

    # 멱등 — 두 번 적용해도 안 늘고 「바뀐 것 없음」을 낸다
    body2, changed2 = U.merge(body, plugins)
    check("[중요] 재적용이 항목을 늘리지 않는다", not changed2, str(changed2))
    check("본문도 그대로", json.loads(body2)["Plugins"] == got["Plugins"])


def test_refusals() -> None:
    for label, prev in (("깨진 JSON", "{ 이건 JSON 이 아니다"),
                        ("빈 파일", "   "),
                        ("최상위가 배열", "[]")):
        try:
            U.merge(prev, ({"name": "X", "targets": ("Editor",)},))
            check(f"[중요] {label} 은 덮지 않는다", False, "통과해버렸다")
        except U.UprojectError:
            check(f"[중요] {label} 은 덮지 않는다", True)

    try:
        U.merge(BASE, ({"name": "X", "targets": ()},))
        check("[중요] targets 가 비면 거부한다", False, "통과해버렸다")
    except U.UprojectError as e:
        check("[중요] targets 가 비면 거부한다", "TargetAllowList" in str(e), str(e))

    try:
        U.merge(json.dumps({"Plugins": "not a list"}), ({"name": "X", "targets": ("Editor",)},))
        check("Plugins 가 배열이 아니면 거부한다", False, "통과해버렸다")
    except U.UprojectError:
        check("Plugins 가 배열이 아니면 거부한다", True)


def test_declaration() -> None:
    # [중요] 기본값이 **비어 있는 것**이 계약이다 — 선언 안 한 프로젝트를 건드리지 않는다
    check("[중요] 기본값은 빈 튜플 (자동 활성화 금지)",
          spec.ProjectInit().uproject_plugins == ())

    got = spec._plugins(["ModelContextProtocol"])
    check("문자열만 줘도 Editor 로 묶인다",
          got == ({"name": "ModelContextProtocol", "targets": ("Editor",)},), str(got))

    got = spec._plugins([{"name": "A", "targets": "Editor"}])
    check("targets 를 문자열로 줘도 받는다", got[0]["targets"] == ("Editor",), str(got))

    for bad in ([{"targets": ["Editor"]}], [3]):
        try:
            spec._plugins(bad)
            check(f"[주의] 잘못된 항목을 조용히 넘기지 않는다: {bad}", False, "통과해버렸다")
        except ValueError:
            check(f"[주의] 잘못된 항목을 조용히 넘기지 않는다: {bad}", True)

    # [중요] AllToolsets 를 기본값에 넣지 않았는지 — Experimental 25종을 끌어온다
    check("[중요] 기본값에 AllToolsets 가 없다",
          not any("AllToolsets" in str(p) for p in spec.ProjectInit().uproject_plugins))


def test_human_steps_are_printed() -> None:
    """[중요] 자동화는 절반이다 — 남은 GUI 셋을 안 찍으면 사람이 「끝났다」고 읽는다."""
    init = spec.ProjectInit(uproject_plugins=({"name": "A", "targets": ("Editor",)},))
    txt = "\n".join(U.plan("P", init=init, workshops=[]))
    for s in ("Auto Start Server", "GenerateClientConfig", "재시작",
              # [중요] 화면 이름이 정확해야 한다 — `Project Settings` 는 **틀린 이름**이다
              #    (실측 2026-08-30: 그렇게 적어서 사용자가 항목을 못 찾았다)
              "Editor Preferences", "Unreal MCP"):
        check(f"계획이 사람 단계를 찍는다 — {s}", s in txt)
    check("[중요] 재시작이 **첫 단계**다 — 그 전에는 항목이 화면에 없다",
          txt.index("재시작") < txt.index("Auto Start Server"))
    check("[주의] 틀린 화면 이름을 쓰지 않는다", "Project Settings" not in txt)
    # [주의] 개수를 문장에 박지 않는다 — 단계가 늘었는데 「셋」이라고 적혀 있었다(실측 2026-08-30)
    check("[주의] 단계 개수를 세서 찍는다", f"{len(U.HUMAN_STEPS)}개" in txt, txt[-200:])
    check("[주의] 계획은 동의를 요구한다", "--confirm" in txt and "동의" in txt)

    empty = "\n".join(U.plan("P", init=spec.ProjectInit(), workshops=[]))
    check("[중요] 선언이 비면 아무 대상도 안 낸다", "자동 활성화는 하지 않는다" in empty)


def main() -> int:
    for fn in (test_merge, test_refusals, test_declaration, test_human_steps_are_printed):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_uproject: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
