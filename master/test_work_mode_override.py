"""`#392` ② — 「이 work 만」 지휘자 변경 표면 (`conductor.set_work_worker_mode` · MCP 도구 · 잠금 판정).

[DOC] 대상: `work/conductor.set_work_worker_mode` · `work/autodispatch.dispatch_locked` ·
      `projects/mcp_server.set_worker_mode_tool(work_id=)`. 큐는 주입한 api 대역, 잠금 디렉토리는
      임시 경로(`autodispatch.LOCK_DIR` 를 바꿔 끼우고 되돌린다), 준비 검사는 주입 — 실 SSH·실 큐 금지.
      출력 형식은 저장소 관례 `통과 N · 실패 M` + rc.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.work import autodispatch as AD                             # noqa: E402
from master.work import conductor as WC                                # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {name}")
    else:
        FAIL += 1
        print(f"  [중요] 실패: {name}" + (f" — {got}" if got else ""))


# [PSEUDO] #392: [1] dispatch_locked — 잠금 파일 없음 → False · 파일만 있고 아무도 안 잡음 → False(파일을 새로 만들지 않는다) · 다른 fd 로 LOCK_EX 를 잡은 동안 → True · 판정 뒤 그 잠금이 풀리지 않는다.
# [PSEUDO] #392: [2] set_work_worker_mode 성공 — api 대역이 GET 에 {"work": {"worker_mode": "codex", "project": "AXCluster"}}, PATCH 에 ok 를 준다 → 반환 previous codex · mode claude · applies next_dispatch · PATCH 본문이 {"project": "AXCluster", "worker_mode": "claude"}.
# [PSEUDO] #392: [3] 성공 시 stderr 에 "[work-mode] <id> codex→claude" 와 "다음 파견부터" 가 찍힌다.
# [PSEUDO] #392: [4] 거절 — locked 가 True → ValueError 이고 PATCH 가 불리지 않는다.
# [PSEUDO] #392: [5] 거절 — why 빈 값 · 모르는 모드 · 빈 work_id · readiness ok False · GET 에 work 없음 · PATCH 응답 ok False(reason terminal_work) 각각 ValueError, 앞의 다섯은 PATCH 없음.
# [PSEUDO] #392: [6] MCP set_worker_mode_tool(work_id="w") 는 set_work_worker_mode 로 가고(WC 함수를 대역으로 바꿔 확인), work_id 없으면 종전 set_worker 로 간다. ValueError 는 {"ok": false, "reason": …} JSON.

print()
print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
