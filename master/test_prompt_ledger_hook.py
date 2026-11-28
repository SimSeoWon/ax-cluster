"""입력 장부 훅(`#1040` T2)·멈춤 판정 훅(T5) — [중요] **원문을 8101 로 보내는가, 서버가 막으라 할 때만 막는가,
실패해도 세션을 막지 않는가.**

가짜 클라(`.ax/lib/axmaster/clientside/client_mcp.py`)를 임시 체크아웃에 심어 돌린다 — 실 마스터를 부르지 않는다.
실행: .venv/bin/python master/test_prompt_ledger_hook.py
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent / "client" / "workshop" / "hooks"
HOOK = HOOKS / "prompt_ledger.py"
STOP = HOOKS / "stop_gate.py"
PASS = FAIL = 0

FAKE = '''
import json, os
from pathlib import Path
HTTP_TIMEOUT = 30
def queue_api(root):
    def api(method, path, payload=None):
        Path(os.environ["CALLS"]).write_text(json.dumps({"method": method, "path": path, "payload": payload,
                                                         "timeout": HTTP_TIMEOUT}, ensure_ascii=False))
        mode = os.environ.get("FAKE_MODE", "ok")
        if mode == "raise":
            raise RuntimeError("[미연결] 마스터에 닿지 않는다")
        if mode == "refuse":
            return {"ok": False, "status": "not_mounted"}
        if mode == "block":
            return {"ok": True, "block": True, "issue_id": 1039, "reason": "[AX 멈춤 판정] #1039 판정 resume"}
        return {"ok": True}
    return api
'''


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def run(root: Path, payload, mode: str = "ok", extra=(), hook: Path = HOOK) -> tuple[subprocess.CompletedProcess, dict]:
    calls = root / "calls.json"
    calls.unlink(missing_ok=True)
    env = {"CALLS": str(calls), "FAKE_MODE": mode, "PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, "-I", str(hook), "--root", str(root), *extra],
                       input=payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=30)
    return p, (json.loads(calls.read_text(encoding="utf-8")) if calls.is_file() else {})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ax-hook-") as d:
        root = Path(d)
        pkg = root / ".ax" / "lib" / "axmaster" / "clientside"
        pkg.mkdir(parents=True)
        (root / ".ax" / "lib" / "axmaster" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "client_mcp.py").write_text(FAKE, encoding="utf-8")

        text = "1번으로 가자. 근데 로그도 남겨"
        p, call = run(root, {"prompt": text, "session_id": "s-1", "cwd": str(root),
                             "hook_event_name": "UserPromptSubmit"}, extra=("--source", "codex"))
        check("rc 0 · stdout 비움(모델 컨텍스트에 안 붙는다)", p.returncode == 0 and p.stdout == "", p.stdout + p.stderr)
        check("[중요] 8101 입력 장부로 원문 그대로", call.get("path") == "/api/v1/interview/prompt"
              and call.get("payload", {}).get("text") == text, str(call))
        check("세션·출처", call.get("payload", {}).get("session") == "s-1"
              and call.get("payload", {}).get("source") == "codex", str(call))
        check("훅이 먼저 끊는다(타임아웃 5초)", call.get("timeout") == 5, str(call))

        p, call = run(root, {"prompt": "x"}, mode="raise")
        check("[중요] 마스터 실패 → rc 0(fail-open) + stderr 한 줄", p.returncode == 0 and "[입력 장부]" in p.stderr
              and p.stderr.count("\n") <= 1, p.stderr)
        p, call = run(root, {"prompt": "x"}, mode="refuse")
        check("거절 응답 → rc 0 + 사유 한 줄", p.returncode == 0 and "not_mounted" in p.stderr, p.stderr)
        p, call = run(root, {"prompt": "   "})
        check("빈 입력은 보내지 않는다", p.returncode == 0 and not call, str(call))
        p, call = run(root, "not json")
        check("JSON 아님 → 조용히 rc 0", p.returncode == 0 and not call and p.stderr == "", p.stderr)

        tr = root / "transcript.jsonl"
        tr.write_text(json.dumps({"type": "tool_use", "input": {"issue_id": 1039, "task_id": "T3"}}) + "\n",
                      encoding="utf-8")
        stop = {"session_id": "s-9", "stop_hook_active": True, "hook_event_name": "Stop", "cwd": str(root),
                "transcript_path": str(tr)}
        p, call = run(root, stop, mode="block", hook=STOP)
        out = json.loads(p.stdout or "{}")
        check("[중요] Stop — 서버가 block 이면 decision block + 사실 사유", p.returncode == 0
              and out.get("decision") == "block" and "resume" in out.get("reason", ""), p.stdout + p.stderr)
        check("Stop — 판정 라우트·세션·stop_hook_active 전달", call.get("path") == "/api/v1/interview/stop"
              and call["payload"] == {"session": "s-9", "stop_hook_active": True}, str(call))
        check("Stop — stdout 은 ASCII(윈도우 콘솔 안전)", p.stdout.isascii(), p.stdout)
        other = root / "other.jsonl"
        other.write_text(json.dumps({"input": {"issue_id": 10390}}) + "\n", encoding="utf-8")
        p, _ = run(root, {**stop, "transcript_path": str(other)}, mode="block", hook=STOP)
        check("[중요] Stop — 그 일감을 다루지 않은 옆 세션은 막지 않는다(10390 ≠ 1039)", p.returncode == 0
              and p.stdout == "" and "다룬 기록" in p.stderr, p.stdout + p.stderr)
        p, _ = run(root, {**stop, "transcript_path": str(root / "missing.jsonl")}, mode="block", hook=STOP)
        check("Stop — 대화 기록을 못 읽으면 막지 않는다", p.stdout == "", p.stdout)
        esc = root / "esc.jsonl"
        esc.write_text('{"content": "{\\"issue_id\\": 1039}"}\n', encoding="utf-8")
        p, _ = run(root, {**stop, "transcript_path": str(esc)}, mode="block", hook=STOP)
        check("Stop — 문자열 안에 이스케이프된 issue_id 도 읽는다", '"decision": "block"' in p.stdout, p.stdout + p.stderr)
        p, _ = run(root, stop, mode="ok", hook=STOP)
        check("Stop — block 아님 → stdout 비움", p.returncode == 0 and p.stdout == "", p.stdout)
        p, _ = run(root, stop, mode="raise", hook=STOP)
        check("[중요] Stop — 마스터 실패 → 막지 않음(fail-open) + stderr 한 줄", p.returncode == 0
              and p.stdout == "" and "[멈춤 판정]" in p.stderr, p.stdout + p.stderr)

        bare = root / "bare"
        bare.mkdir()
        p, _ = run(bare, {"prompt": "y"})
        check("배달 클라가 없으면 저장소 클라로(마스터) — 실패해도 rc 0", p.returncode == 0, p.stderr)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_prompt_ledger_hook: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
