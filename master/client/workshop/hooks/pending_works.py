"""SessionStart 훅 — **승인을 기다리는 분산 작업이 있으면 세션 시작에 고지한다** (`#337`).

## 왜 훅인가 (사용자 결정 ⓑ, 2026-08-30)

파이프라인은 일부러 휴먼 인 루프다 — `finalize_work` 의 기본값이 `confirm=False` 라 **승인이
곧 트리거**다. 그런데 「지금 승인 기다리는 게 있다」를 **사람이 찾아야만** 알 수 있었다:
레드마인 자동 이슈(`task_queue/logic_cleanup.py`)와 상태 화면(`:8103`) 둘 다 **pull** 이고,
머지하지 않은 채 껐다 켜면 아무도 부르지 않는다.

규약(작업장 `CLAUDE.md` 에 「세션 시작에 불러라」 한 줄)으로도 걸 수 있었지만 그것은 **내가
「지금은 해당 없음」이라고 판정할 수 있는 형태**다 — `~/CLAUDE.md` 「판단의 틈」이 지목한 부류이고
2026-08-25 에 같은 부류가 넷 어겨졌다. 훅은 그 판정 자리 자체를 없앤다.

[주의] 이 훅이 돌 수 있게 된 것은 `#337` 이 **등록 배선**을 고친 덕이다(`e5b899f`). 그전까지
`.claude/hooks/` 는 배달돼도 `settings.json` 에 등록되지 않아 아무것도 돌지 않았다.

## 계약 — [중요] 실측이다 (2026-08-30, 실제 `claude -p` 로 측정)

    stdin        {"cwd", "hook_event_name", "session_id", "source", "transcript_path"}
    source       "startup" (측정값) · matcher 가 이 값을 **정규식으로** 가른다
                 실측: matcher="resume" → 미발동 · "startup" → 발동 · "startup|resume|clear" → 발동
    stdout       **세션 컨텍스트에 들어간다** — 실측: 훅이 찍은 토큰을 모델이 그대로 읽었다

그래서 여기서는 stdout 으로 말한다. (`domain_hint` 는 PostToolUse 라 stderr 였다 — 이벤트마다
계약이 다르다. 재지 않고 베끼면 조용히 안 보인다.)

## 무엇을 「미머지」로 보나 — [중요] 정의를 지어내지 않는다

`master/status.py:628` 의 `WORK_OPEN` 을 그대로 쓴다:

    WORK_OPEN = ("in_progress", "ready_for_review", "", None)   # 열린 work (#222)

둘을 갈라 보여 준다. `ready_for_review` 는 **승인 대기**이고, `in_progress` 는 [주의] **상주
클레이머가 0(`#320`)이라 저절로 진행되지 않는다** — 껐다 켠 자리에서 그 둘은 사람에게 다른 뜻이다.

## [주의] 조용한 빈 결과를 만들지 않는다

열린 work 가 없으면 **아무 말도 하지 않는다**(세션마다 「없음」을 찍는 것은 소음이다).
그러나 **못 물어봤을 때는 반드시 말한다** — 침묵이 「없다」로 읽히면 이 훅은 있으나 마나다.
"""
import json
import sys
from pathlib import Path

# [중요] `master/status.py` `WORK_OPEN` 과 같은 정의다. 여기서 새로 정하지 않는다.
OPEN_STATUSES = ("ready_for_review", "in_progress", "", None)
DETAIL_MAX = 3          # get_work 로 task 내역까지 볼 work 수 (세션 시작 지연을 묶는다)

# [중요] `domain_hint` 와 같은 근거 — 훅은 스스로 먼저 끊는다. 클라 기본은 30초이고 등록
#    timeout 은 15초라, 마스터가 죽으면 **세션 시작이 그만큼 멈춘다.**
HTTP_TIMEOUT_SEC = 6


def _load_client(cwd: Path):
    lib = cwd / ".ax" / "lib"
    if not lib.is_dir():
        raise RuntimeError(f".ax/lib 가 없다 — 마스터 배달 전이다 ({lib})")
    sys.path.insert(0, str(lib))
    from axmaster.clientside import client_mcp              # noqa: PLC0415
    return client_mcp


def _line(w: dict, detail: dict | None) -> str:
    wid = w.get("work_id") or "(id 없음)"
    out = f"  · {wid}\n    {w.get('title') or '(제목 없음)'}"
    if w.get("target_branch"):
        out += f"\n    브랜치 {w['target_branch']}"
    if detail is not None:
        tasks = detail.get("tasks") or []
        by = {}
        for t in tasks:
            by[t.get("status") or "?"] = by.get(t.get("status") or "?", 0) + 1
        if by:
            out += "\n    태스크 " + " · ".join(f"{k} {v}" for k, v in sorted(by.items()))
    elif w.get("total"):
        out += f"\n    태스크 {w['total']}건"
    return out


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    cwd = Path(str(data.get("cwd") or "."))

    try:
        client_mcp = _load_client(cwd)
    except Exception as e:                                  # noqa: BLE001
        # [주의] 배달 전 체크아웃에서는 조용히 넘어간다 — 이 훅의 문제가 아니다
        print(f"[분산 작업] 점검 못 함 — {e}")
        return
    try:
        from axmaster import utf8                           # noqa: PLC0415
        utf8.enforce()
    except Exception:                                       # noqa: BLE001
        pass

    client_mcp.HTTP_TIMEOUT = HTTP_TIMEOUT_SEC
    try:
        api = client_mcp.queue_api(cwd)
        got = client_mcp.tool_list_works(api)
        # [중요] **「왜 멈췄나」를 같이 묻는다** (사용자 지시 2026-09-01). work 목록만 보면
        #    `in_progress · claimed 4` 까지만 보이고, 그것이 세션 한도로 멈춘 것인지 고장인지
        #    사람이 구분할 수 없다 — 오늘 이틀을 잃은 것과 같은 모양이다.
        #    [주의] 이 조회가 실패해도 위의 고지는 살린다(아래 try 를 따로 둔 이유).
        hold = {}
        try:
            hold = (api("GET", "/api/v1/status") or {}).get("dispatch_hold") or {}
        except Exception:                                   # noqa: BLE001,S110
            hold = {}
    except Exception as e:                                  # noqa: BLE001
        # [중요] **침묵하지 않는다.** 못 물어본 것을 「없다」로 읽으면 이 훅은 있으나 마나다.
        print(f"[분산 작업] [주의] 미머지 점검을 못 했다 — {str(e).splitlines()[0]}\n"
              f"  승인 대기가 있는지 **모르는 상태**다. 마스터가 살아나면 "
              f"`list_works(status=\"ready_for_review\")` 로 직접 확인할 것.")
        return

    works = [w for w in (got.get("works") or [])
             if w.get("merge_status") in OPEN_STATUSES]
    if not works:
        return                       # 열린 work 0 — 세션마다 「없음」을 찍는 것은 소음이다

    ready = [w for w in works if w.get("merge_status") == "ready_for_review"]
    running = [w for w in works if w not in ready]

    # [중요] **보류를 맨 앞에 말한다** — 그것이 「지금 왜 안 도나」의 답이고, 재개 지시가
    #    사람 몫이기 때문이다(사용자 결정 2026-09-01: 공지 → 사람이 지시 → 이어서 진행).
    if hold.get("state") == "awaiting_resume":
        print(f"[분산 작업] 🔴 **재개 대기** — 세션 한도로 멈췄고 한도는 이미 풀렸다"
              f"({hold.get('until') or '?'}).\n"
              f"  work {hold.get('work_id') or '?'} · 사유: {hold.get('reason') or '?'}\n"
              f"  [중요] 자동으로 이어가지 않는다 — 사용자가 시작을 지시해야 한다.\n"
              f"  마스터에서: python -m master.work.autodispatch --resume "
              f"{hold.get('project') or '<프로젝트>'} {hold.get('work_id') or ''}".rstrip())
    elif hold.get("blocked"):
        print(f"[분산 작업] [주의] 자동 파견이 멈춰 있다 — {hold.get('line') or '사유 미상'}")

    details: dict = {}
    for w in (ready + running)[:DETAIL_MAX]:
        try:
            details[w.get("work_id")] = client_mcp.tool_get_work(api, str(w.get("work_id")))
        except Exception:                                   # noqa: BLE001
            pass                     # 상세는 덤이다 — 없다고 고지를 접지 않는다

    out = ["[분산 작업] 머지되지 않은 work 가 있다 — 세션 시작 점검 (`#337`)"]
    if ready:
        out.append(f"\n■ 승인 대기 {len(ready)}건 — **사람의 승인이 곧 트리거다**")
        out += [_line(w, details.get(w.get("work_id"))) for w in ready]
        out.append("  → 통합이 끝났으면 `finalize_work(confirm=True)`. 기본값은 "
                   "`confirm=False`(통합만 하고 멈춤)다.")
    if running:
        out.append(f"\n■ 진행 중 {len(running)}건")
        out += [_line(w, details.get(w.get("work_id"))) for w in running]
        out.append("  → [주의] 상주 클레이머는 0이다(`#320`). 저절로 진행되지 않으니 "
                   "파견·통합은 마스터에서 이어서 한다.")
    out.append("\n[주의] 사용자가 묻기 전에 이 내용을 먼저 알린다. 임의로 머지하지 않는다 — "
               "승인은 사람이 한다.")
    print("\n".join(out))


if __name__ == "__main__":
    main()
