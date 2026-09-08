"""요청자 인증을 거치는 지휘 상태 표면. 공개 /api/v1 아래에 쓰기를 놓지 않는다."""
import json
from .register_route import _read_body, _send_json
from ..work import conductor

PATHS = {"/control/orchestration": "GET", "/control/worker-mode": "POST",
         "/control/master-conductor": "POST"}

class ControlApp:
    def __init__(self, next_app):
        self.next_app = next_app

    async def __call__(self, scope, receive, send):
        path = scope.get("path")
        if scope.get("type") != "http" or path not in PATHS:
            return await self.next_app(scope, receive, send)
        if scope.get("method") != PATHS[path]:
            return await _send_json(send, {"ok": False, "error": "지원하지 않는 메서드"}, 405)
        try:
            if PATHS[path] == "GET":
                result = conductor.snapshot()
            else:
                payload = json.loads(await _read_body(receive))
                if not isinstance(payload, dict):
                    raise ValueError("본문은 JSON 객체여야 한다")
                fn, field = ((conductor.set_worker, "mode") if path.endswith("worker-mode")
                             else (conductor.record_master, "agent"))
                result = fn(payload.get(field), payload.get("why"), payload.get("by", ""))
        except (ValueError, TypeError, OSError) as exc:
            return await _send_json(send, {"ok": False, "error": str(exc)}, 400)
        return await _send_json(send, result)
