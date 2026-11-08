"""클러스터의 지휘 상태 표시. 서버 측 조회만 수행하고 인증값은 HTML에 넣지 않는다.

[중요] **예외 문자열을 이 화면에 그대로 쓰지 않는다.** 8103 은 `/api/v1` 까지 무인증
공개라(실측 2026-08-25) `str(OSError)` 를 실으면 절대 경로가 그대로 찍힌다 —
`api_history` 가 본문·절대 경로를 의도적으로 빼는 것과 같은 자리다. 사유는 **고정 문구**로
적고, 실제 예외는 호출자(`conductor.snapshot`)와 로그에 남긴다.
"""
from html import escape
from ..work import conductor

def section():
    try:
        state = conductor.snapshot()
    except (ValueError, OSError) as exc:
        # [중요] `exc` 를 찍지 않는다 — 위 머리말 참조. 갈래는 로그가 가진다.
        return '<section><h2>지휘 상태</h2><p>조회 실패 — 마스터 로그를 본다.</p></section>'
    master, worker = state["master"], state["worker"]
    labels = {"claude": "Claude", "codex": "Codex", "antigravity": "Antigravity",
              "agy": "Antigravity", "lane": "lane", "unknown": "미등록"}
    agent = labels.get(master.get("agent"), "미등록")
    selected = labels.get(worker.get("mode"), "미확인")
    at = escape(str(master.get("at") or "기록 없음"))
    # [중요] `note` 는 예외 문자열이 들어올 수 있는 자리다 — 화면에 올리지 않는다.
    why = escape(str(master.get("why") or ""))
    if not why and master.get("agent") == "unknown":
        why = "담당 기록이 없거나 읽지 못했습니다."
    source = escape(str(worker.get("source") or ""))
    return (f'<section class="card"><h2>지휘 상태</h2>'
            f'<p><strong>마스터 담당: {agent}</strong> · 마지막 기록 {at}</p>'
            f'<p>{why}</p><p class="sub">담당 기록이며, 현재 세션의 실행 여부는 미확인입니다.</p>'
            f'<p><strong>워커 실행 모드: {selected}</strong> · 출처 {source}</p>'
            '<p class="sub">마스터 전역 설정 · 다음 조각부터 적용 · 실행 중인 조각은 유지됩니다.</p>'
            '<p>.33에서 “워커 모드를 코덱스로 변경해” 또는 “지휘 상태를 보여줘”라고 요청할 수 있습니다.</p></section>')
