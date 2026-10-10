"""SessionStart 훅 — **승인을 기다리는 분산 작업이 있으면 세션 시작에 고지한다** (`#337`).

[주의] 이 훅은 **고지를 둘** 낸다. 두 번째는 에디터(Unreal MCP) 접근 가능 여부(`#374`)이고
판정은 `editor_mcp.py` 에 있다 — 훅을 하나 더 등록하지 않은 이유는 이미 세션 시작과 매 턴에
도는 자리가 여기라서다(같은 이벤트에 두 번째 프로세스를 띄우면 사람의 턴만 더 붙잡는다).

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

from hook_paths import checkout_root, cwd_notice

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
    if w.get("notification_error"):
        out += f"\n    통보 실패: {w['notification_error']}"
        if w.get("termination_required"):
            out += "\n    통보 복구 또는 강제 종결에 사람 판단이 필요한 상태"
    if detail is not None:
        tasks = detail.get("tasks") or []
        by = {}
        for t in tasks:
            by[t.get("status") or "?"] = by.get(t.get("status") or "?", 0) + 1
        if by:
            out += "\n    태스크 " + " · ".join(f"{k} {v}" for k, v in sorted(by.items()))
        for task in tasks:
            if task.get("status") in ("failed", "needs_revision"):
                why = str(task.get("fail_detail") or task.get("last_feedback") or
                          task.get("verdict_feedback") or task.get("fail_reason") or "사유 없음")[:500]
                out += f"\n    {task.get('status')} {task.get('task_id')}: {why}"
    elif w.get("total"):
        out += f"\n    태스크 {w['total']}건"
    return out


def _load_followup():
    """배달된 `axmaster.work.followup` (`#798`). `.ax/lib` 는 `_load_client` 가 경로에 넣었다."""
    from axmaster.work import followup                      # noqa: PLC0415
    return followup


def _followup_block(cwd: Path, w: dict, detail: dict | None) -> str:
    """⑦ 준비 기록(완료 훅·60초 타이머가 남긴 것)을 **사실로만** 붙인다 (`#798` ⓑ).

    🔴 이 훅의 stdout 은 세션 컨텍스트에 들어간다 — 여기 붙는 글은 `followup.render` 그대로이고
    명령형을 싣지 않는다. 기록을 못 읽은 것은 「없다」와 다르게 말한다(조용한 빈 결과 금지).
    """
    wid = str(w.get("work_id") or "")
    try:
        fu = _load_followup()
    except Exception as e:                                  # noqa: BLE001
        return f"    ⑦ 준비 기록 조회 불가 — {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
    rnd = ((detail or {}).get("work") or {}).get("round") or w.get("round")
    try:
        rec = fu.recorded_for(cwd, wid, int(rnd) if rnd else None)
    except Exception as e:                                  # noqa: BLE001
        return f"    ⑦ 준비 기록 조회 불가 — {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
    if not rec:
        return (f"    ⑦ 준비 기록 없음 — 라운드 {rnd or '?'} 에 대해 완료 훅·타이머가 남긴 "
                "준비 결과가 이 기계에 없다")
    return "\n".join("    " + ln for ln in fu.render(rec).splitlines())


def _editor_notice(data: dict) -> None:
    """에디터(Unreal MCP) 접근 가능 여부 한 줄 (`#374`).

    [중요] **맨 앞에서, 아래 어떤 `return` 보다 먼저 낸다.** 이 함수 아래로는 마스터를 못
    물어봤을 때 빠져나가는 길이 셋인데, 그 뒤에 두면 마스터가 죽은 날 이 고지도 같이 죽는다.
    두 점검은 서로 독립이다 — 하나가 실패해도 다른 하나는 사실을 낸다.
    """
    try:
        # [주의] **사람의 `.claude/hooks/` 에 `__pycache__` 를 남기지 않는다** — 배달 표면이라
        #    다음 배달의 비교 대상에 쓰레기가 낀다. 훅은 한 번 돌고 끝이라 캐시 이득도 없다.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import editor_mcp                                    # noqa: PLC0415
        out = editor_mcp.notice(data)
    except Exception as e:                                   # noqa: BLE001
        print(f"[에디터 MCP] [주의] 점검 못 함 — {str(e).splitlines()[0]}")
        return
    if out:
        print(out)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    session_cwd = Path(str(data.get("cwd") or "."))
    # 🔴 [중요] 체크아웃 루트는 **훅이 놓인 자리**가 안다 — 세션 cwd 가 아니다 (`hook_paths`).
    #    사람이 하위 폴더에서 세션을 열면 그 둘이 갈라지고, 종전에는 갈라진 채로
    #    `.ax/lib` 를 찾다 「점검 못 함」만 찍었다 (실측 2026-09-20 `.33`).
    cwd = checkout_root(session_cwd)
    notice = cwd_notice(session_cwd, cwd)
    if notice:
        print(notice)
    _editor_notice(data)

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
        hold, hold_err = {}, ""
        try:
            hold = (api("GET", "/api/v1/status") or {}).get("dispatch_hold") or {}
        except Exception as e:                              # noqa: BLE001
            # [중요] **삼키지 않는다.** 처음에 `except: pass` 로 뒀더니 스코프에 경로가 없어
            #    403 이 났는데 훅이 **아무 말도 안 했다**(실측 2026-09-01). 이 파일 머리말이
            #    금지한 「조용한 빈 결과」를 내가 만든 자리다.
            hold_err = str(e).splitlines()[0]
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
    elif hold_err:
        print(f"[분산 작업] [주의] 자동 파견이 멈춰 있는지 **확인하지 못했다** — {hold_err}\n"
              f"  침묵을 「정상」으로 읽지 말 것. 마스터에서: "
              f"journalctl -u ax-dispatch -u ax-dispatch-catchup -n 30 --no-pager")

    details: dict = {}
    for w in (ready + running)[:DETAIL_MAX]:
        try:
            details[w.get("work_id")] = client_mcp.tool_get_work(api, str(w.get("work_id")))
        except Exception:                                   # noqa: BLE001
            pass                     # 상세는 덤이다 — 없다고 고지를 접지 않는다

    out = ["[분산 작업] 머지되지 않은 work 가 있다 — 세션 시작 점검 (`#337`)"]
    if ready:
        out.append(f"\n■ 라운드 종결 대기 {len(ready)}건 — **작업 브랜치를 한 칸 전진**"
                   f"시키는 자리다 (`main` 이 아니다)")
        for w in ready:
            out.append(_line(w, details.get(w.get("work_id"))))
            out.append(_followup_block(cwd, w, details.get(w.get("work_id"))))
        out.append("  → `ax-advance`: 서브 브랜치를 전부 작업 브랜치에 머지 → 거기서 "
                   "**한 번** UE5 빌드")
        out.append("     · 빌드가 실패하면 고치고 **다시 빌드한다** — 통과를 재기 전에는 "
                   "전진하지 않는다")
        out.append("     · 통과하면 사람에게 묻는다 — **추가 개선인가, 마감인가**")
        out.append("        추가 개선 → 전진(push) 뒤 `.h`/`.cpp` 에 지시 주석 → 재등재")
        out.append("        마감      → 그때만 `ax-review` → `finalize_work(confirm=True)`")
    if running:
        out.append(f"\n■ 진행 중 {len(running)}건")
        out += [_line(w, details.get(w.get("work_id"))) for w in running]
        out.append("  → 파견은 자동이다 (`ax-dispatch.path` — 골조 push 가 트리거). "
                   "조각이 전부 끝나면 여기 「라운드 종결 대기」로 올라온다.")
    out.append("\n[주의] 사용자가 묻기 전에 이 내용을 먼저 알린다. 임의로 머지하지 않는다 — "
               "승인은 사람이 한다.")
    print("\n".join(out))


if __name__ == "__main__":
    main()
