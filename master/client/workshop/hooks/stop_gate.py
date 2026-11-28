"""Stop 훅 — 일감 진행 중에 정당한 사유 없이 턴을 끝내면 막는다 (`#1040` ②).

## 왜

#1039 (11-28 00:27): `plan_start` 가 `resume` 을 줬는데 지휘자가 「재개했습니다」라고 답하고 아무것도 하지 않고
턴을 끝냈다. 판정을 따를지는 모델이 골랐고, 멈추는 쪽을 막는 장치가 없었다.

## 계약

- 입력: Claude Code·Codex 공통 `Stop` JSON — `session_id`·`stop_hook_active`·`cwd`(Codex 0.172.0
  `stop.command.input` 실측).
- 판정은 **서버 한 곳**이다: 8101 `POST /api/v1/interview/stop`(`master/interview_ledger.stop_check`). 막는 조건은
  일감 잠금 활성 + 판정 resume/next + 정당 사유(답 대기 질문 · 판정 stop · 사용자 멈춤 지시) 없음.
- 막을 때: stdout `{"decision": "block", "reason": …}` (두 CLI 공통 출력 형식). reason 은 **사실만** —
  자동 경로 글의 명령형은 주입으로 거부된다(CLAUDE.md). 무엇을 할지는 `ax-plan` 스킬이 말한다.
- [중요] **fail-open** — 마스터가 죽었거나 판정이 실패하면 막지 않는다(stderr 한 줄). 같은 세션 연속 차단은
  서버가 3회로 끊는다(무한 반복 방지).
- 워커에는 배달하지 않는다 — 사람이 없는 경로에서 Stop 을 막으면 안 된다.
- [중요] **그 일감을 다룬 세션만 막는다** — 마스터의 훅은 사용자 설정이라 모든 세션에 걸린다. 서버가 block 을
  줘도 이 세션의 대화 기록(`transcript_path`)에 그 일감 번호(`"issue_id": N`)가 없으면 막지 않는다(다른 일을 하는
  옆 세션). 기록을 못 읽으면 막지 않는다(fail-open).
"""
import re
import json
import sys
from pathlib import Path

HTTP_TIMEOUT_SEC = 15
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_ledger import _args, _load_client       # noqa: E402 — 같은 배선(클라 찾기·--root)을 쓴다


def _session_touched(data: dict, issue_id) -> bool:
    """이 세션 대화 기록에 그 일감 번호가 도구 인자로 나왔나. 못 읽으면 False(막지 않음)."""
    path = str(data.get("transcript_path") or "")
    if not path or issue_id is None:
        return False
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return re.search(r'\\?"issue_id\\?"\s*:\s*' + str(int(issue_id)) + r"\b", text) is not None


def main(argv=None, stdin=None) -> int:
    opts = _args(sys.argv[1:] if argv is None else argv)
    try:
        data = json.load(stdin or sys.stdin)
    except ValueError:
        return 0
    if opts.get("root"):
        root = Path(opts["root"]).expanduser()
    else:
        from hook_paths import checkout_root           # noqa: PLC0415
        root = checkout_root(data.get("cwd"))
    try:
        client = _load_client(root)
        client.HTTP_TIMEOUT = HTTP_TIMEOUT_SEC
        got = client.queue_api(root)("POST", "/api/v1/interview/stop", {
            "session": str(data.get("session_id") or ""), "stop_hook_active": bool(data.get("stop_hook_active"))})
    except Exception as e:                              # noqa: BLE001 — fail-open
        print(f"[멈춤 판정] 건너뜀 — {str(e).splitlines()[0][:160] if str(e) else type(e).__name__}",
              file=sys.stderr)
        return 0
    if (isinstance(got, dict) and got.get("block") and got.get("session_bound") is not True
            and not _session_touched(data, got.get("issue_id"))):
        print(f"[멈춤 판정] #{got.get('issue_id')} 을 다룬 기록이 이 세션에 없다 — 막지 않음", file=sys.stderr)
        return 0
    if isinstance(got, dict) and got.get("block"):
        # ensure_ascii — 윈도우 콘솔(CP949)에서 한글 print 가 죽지 않게 \u 로 내보낸다(JSON 으로는 같다)
        print(json.dumps({"decision": "block", "reason": str(got.get("reason") or "")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
