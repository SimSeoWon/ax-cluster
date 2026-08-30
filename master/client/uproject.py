"""요청자 에디터 플러그인 — `.uproject` 의 `Plugins` 를 계획하고, 동의 뒤에만 쓴다 (`#335`).

## 왜 배달이 아니라 별도 명령인가

`.uproject` 는 **게임 소스**다. `deliver` 가 만지는 표면(`.ax/`·스킬·MCP 설정·`.claude/`)
밖이고, §0.05(게임 소스는 계획을 말하고 동의를 받는다)의 대상이다. 배달이 조용히 켜면
규약 위반이므로 **동의 게이트가 있는 자리**를 따로 만든다 — 이 저장소 관례대로 `plan` 이
기본이고 `--confirm` 이 트리거다(`finalize_work` · `cleanup` 과 같은 모양).

## [중요] `TargetAllowList: ["Editor"]` 는 선택이 아니다

`ModelContextProtocol` 은 Runtime 모듈도 갖고 있다. 안 묶으면 **인증 없는 MCP 서버가 패키징에
실려 나간다**(런북 §14.2-5). 그래서 이 모듈은 `targets` 가 빈 항목을 **거부**한다.

## [주의] 자동화해도 절반만이다

에디터 GUI 단계 셋이 남는다 — Auto Start Server · GenerateClientConfig · 에디터 재시작.
그래서 출력이 그 셋을 **반드시 찍는다**(`#335` 완료 조건 3). 찍지 않으면 사람이 「끝났다」고
읽고 다음 세션이 *"MCP 가 왜 안 붙나"* 로 한 시간을 태운다.

## [주의] 판정은 선언이 아니라 실측이다

`.uproject` 가 실제로 있는 기계·경로에만 쓴다. 없으면 **아무것도 하지 않는다**(비-UE5
프로젝트에서 조용히 파일을 만들지 않는다 — 런북 §14.2-2 의 LFS 판정과 같은 규칙).
"""
from __future__ import annotations

import json

from . import bundle, spec

# [중요] 자동화가 못 하는 GUI 단계 — 출력이 이것을 반드시 찍는다 (`#335` 완료 조건 3)
HUMAN_STEPS = (
    "에디터 Project Settings → Model Context Protocol → **Auto Start Server** 를 켠다",
    "같은 화면의 **GenerateClientConfig** 로 `.mcp.json` 항목을 만든다 "
    "(마스터가 쓴 `ax-client` 항목은 보존된다 — 실측 2026-08-29)",
    "**에디터를 재시작**한다 — 플러그인 활성화는 재시작 뒤에 듣는다",
)


class UprojectError(Exception):
    pass


def _entry(p: dict) -> dict:
    name = str(p.get("name") or "").strip()
    targets = tuple(p.get("targets") or ())
    if not name:
        raise UprojectError("플러그인 이름이 비었다")
    if not targets:
        # [중요] 여기서 막는다 — 빈 값을 허용하면 패키징에 Runtime 모듈이 실린다
        raise UprojectError(
            f"{name}: `targets` 가 비었다 — `TargetAllowList` 없이 켜지 않는다 (`#335`)")
    return {"Name": name, "Enabled": True, "TargetAllowList": list(targets)}


def merge(prev_text: str, plugins) -> tuple:
    """기존 `.uproject` 에 관리 플러그인만 넣는다 — **사람이 켠 나머지는 보존**한다.

    반환 `(새 본문, 바뀐 이름들)`. 바뀐 것이 없으면 두 번째가 빈 튜플이다.

    [중요] 깨진 JSON 이면 **덮지 않고 멈춘다** — `merge_mcp_json` 과 같은 판단이고, 여기서
    덮으면 **프로젝트가 아예 안 열린다.**
    """
    txt = (prev_text or "").strip()
    if not txt:
        raise UprojectError("`.uproject` 가 비었다 — 덮지 않는다")
    try:
        data = json.loads(txt)
    except ValueError as e:
        raise UprojectError(f"`.uproject` 가 깨진 JSON 이다 — 덮지 않는다. 사람이 확인할 것 ({e})")
    if not isinstance(data, dict):
        raise UprojectError("`.uproject` 최상위가 객체가 아니다 — 덮지 않는다")

    cur = data.get("Plugins")
    if cur is None:
        cur = []
    if not isinstance(cur, list):
        raise UprojectError("`.uproject` 의 `Plugins` 가 배열이 아니다 — 덮지 않는다")

    changed = []
    for p in plugins:
        want = _entry(p)
        for i, got in enumerate(cur):
            if isinstance(got, dict) and str(got.get("Name") or "") == want["Name"]:
                if got != want:
                    cur[i] = want
                    changed.append(want["Name"])
                break
        else:
            cur.append(want)
            changed.append(want["Name"])
    if not changed:
        return txt + ("\n" if not txt.endswith("\n") else ""), ()
    data["Plugins"] = cur
    # UE 가 쓰는 모양에 맞춘다 — 탭 들여쓰기가 아니라 공백 4칸이 에디터 저장본과 가깝다
    return json.dumps(data, ensure_ascii=False, indent=4) + "\n", tuple(changed)


def plan(project: str, *, init=None, workshops=None) -> list:
    """무엇을 어디에 쓸지 **보여만 준다.** 반환: 줄 목록.

    [중요] 요청자만 대상이다 — `.uproject` 를 여는 것은 에디터가 있는 기계뿐이고, 워커는
    빌드만 한다(`run_build_on_workshop` 은 플러그인 설정을 읽지 않는다).
    """
    init = init if init is not None else spec.load_init(project)
    plugins = init.uproject_plugins
    out = [f"[uproject] {project} — 선언된 플러그인 {len(plugins)}개"]
    if not plugins:
        out.append("  (없음 — `config.yaml` 의 `init.uproject_plugins` 가 비었다. "
                   "**자동 활성화는 하지 않는다**)")
        return out
    for p in plugins:
        out.append(f"  · {p['name']}  TargetAllowList={list(p['targets'])}")
    rows = workshops if workshops is not None else bundle.workshops(project)
    for row in rows:
        host, user, path, _driven, role, _dispatch = row
        if role != "requester":
            continue
        out.append(f"  → {host} [{role}] {path}")
    out.append("")
    out.append("[주의] 쓰기 전에 동의를 받는다 (`.uproject` 는 게임 소스 — §0.05). "
               "실행: `python -m master.client uproject <프로젝트> --confirm`")
    out.append("[중요] 자동화가 못 하는 사람 단계 셋:")
    for i, s in enumerate(HUMAN_STEPS, 1):
        out.append(f"  {i}. {s}")
    return out


def apply(project: str, *, init=None, facts=None, reader=None, writer=None) -> list:
    """[중요] **동의 뒤에만 부른다.** 요청자의 `.uproject` 에 관리 플러그인을 넣는다.

    `reader`/`writer` 는 테스트 주입 — 실전은 `bundle._remote_read`/`_remote_write` 다.
    """
    init = init if init is not None else spec.load_init(project)
    plugins = init.uproject_plugins
    out = []
    if not plugins:
        return ["[uproject] 선언이 비었다 — 아무것도 하지 않는다"]
    rd = reader or bundle._remote_read
    wr = writer or bundle._remote_write
    rows = facts if facts is not None else []
    for f in rows:
        if f.role != "requester":
            continue
        # [주의] **실측이다** — 이름을 지어내지 않는다. 트윈 소스에서 잰 `.uproject` 이름을 쓴다.
        up = bundle._uproject_facts(project).get("uproject") or ""
        if not up:
            out.append(f"  [주의] {f.host}: `.uproject` 를 못 찾았다 — 건너뜀 "
                       f"(비-UE5 프로젝트이거나 트윈 미동기)")
            continue
        sep = chr(92) if f.windows else "/"
        prev = rd(f, f"{f.path}{sep}{up}")
        try:
            body, changed = merge(prev, plugins)
        except UprojectError as e:
            # [중요] 실패는 고치는 자리가 아니라 보고하는 자리다 — 여기서 덮지 않는다
            out.append(f"  [실패] {f.host}: {e}")
            continue
        if not changed:
            out.append(f"  [완료] {f.host}: 이미 켜져 있다 ({up}) — 쓰지 않았다")
            continue
        out.append(f"  [완료] {f.host}: {wr(f, up, body, base='checkout')} "
                   f"— 바뀐 플러그인 {', '.join(changed)}")
    out.append("")
    out.append("[중요] 여기까지는 절반이다. 사람이 할 셋:")
    for i, s in enumerate(HUMAN_STEPS, 1):
        out.append(f"  {i}. {s}")
    return out
