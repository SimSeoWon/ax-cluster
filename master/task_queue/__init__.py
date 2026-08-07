"""task_queue — 잡 분배 큐 (AgentTest `mcp/task_queue/` 이식, 2026-08-08).

실행:
    python -m master.task_queue --serve <state_root> [port=8101] [host=0.0.0.0]

주 모드는 systemd 로 도는 HTTP 서버다(PLAN.md §5.4.4). MCP stdio 모드는 `mcp` 패키지를
요구하므로 `mcp_server` 로 분리해 **지연 import** 한다 — HTTP 서비스가 MCP SDK 미설치로
기동 실패하지 않게.

이식 시 바뀐 것 (원본과의 차이):
  · 플랫 import → 패키지 상대 import
  · `_project_root()` 파일 위치 역산 → `AX_TASK_QUEUE_ROOT` 명시 설정 (없으면 즉시 실패)
  · `admin_reset(cleanup_branches=True)` → **거부**. 마스터 root 는 큐 상태 저장소지
    UE5 저장소가 아니라 조용한 no-op 이 된다 (PLAN.md §2.1)
"""
