"""UserPromptSubmit 훅 — 사용자의 **실제 입력 원문**을 마스터 입력 장부에 적는다 (`#1040`).

## 왜 훅인가

인터뷰·플랜 기록 도구는 `user_answer` 를 받는데, 그 값은 지휘 모델이 채운다. #1037(11-27 22:15)에서
분류 질문에 답하지 않은 문장이 분류 승인으로 기록됐다. 모델이 쓰지 않는 기록 — 사람이 친 그 문장 — 이
있어야 서버가 「그 답이 질문 뒤 실제 입력인가」를 대조할 수 있다(`master/interview_ledger.judge`).

## 계약

- 입력: Claude Code·Codex 공통 `UserPromptSubmit` JSON — `prompt`·`session_id`·`cwd`(Codex 0.172.0 스키마
  `user-prompt-submit.command.input` 실측).
- 경로: 배달된 클라(`client_mcp.queue_api`) → 8101 `POST /api/v1/interview/prompt`(프로젝트 태그는 클라가 붙인다).
- [중요] **세션을 막지 않는다(fail-open)** — 마스터가 죽어도 사용자의 입력은 그대로 모델에 간다. 실패는
  stderr 한 줄. 관문이 켜진 프로젝트에서는 장부가 비어 기록이 거절되므로 실패가 조용히 묻히지 않는다.
- stdout 에는 아무것도 쓰지 않는다 — `UserPromptSubmit` 의 stdout 은 모델 컨텍스트에 붙는다.
- 마스터 자신은 배달된 `.ax/lib` 이 없다 → `--root`(ax-client 설정 디렉토리)를 받고 저장소의 클라를 쓴다.
"""
import json
import sys
from pathlib import Path

HTTP_TIMEOUT_SEC = 5
REPO_CLIENT = Path(__file__).resolve().parents[3] / "client" / "runtime"


def _args(argv: list[str]) -> dict:
    out = {}
    it = iter(argv)
    for a in it:
        if a in ("--root", "--source"):
            out[a[2:]] = next(it, "")
    return out


def _load_client(root: Path):
    lib = root / ".ax" / "lib"
    if (lib / "axmaster" / "clientside" / "client_mcp.py").is_file():
        sys.path.insert(0, str(lib))
        from axmaster.clientside import client_mcp     # noqa: PLC0415
        return client_mcp
    if (REPO_CLIENT / "client_mcp.py").is_file():
        sys.path.insert(0, str(REPO_CLIENT))
        import client_mcp                              # noqa: PLC0415
        return client_mcp
    raise RuntimeError(f"클라가 없다 ({lib} · {REPO_CLIENT})")


def main(argv=None, stdin=None) -> int:
    opts = _args(sys.argv[1:] if argv is None else argv)
    try:
        data = json.load(stdin or sys.stdin)
    except ValueError:
        return 0
    text = data.get("prompt")
    if not isinstance(text, str) or not text.strip():
        return 0
    if opts.get("root"):
        root = Path(opts["root"]).expanduser()
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from hook_paths import checkout_root           # noqa: PLC0415
        root = checkout_root(data.get("cwd"))
    try:
        client = _load_client(root)
        client.HTTP_TIMEOUT = HTTP_TIMEOUT_SEC
        got = client.queue_api(root)("POST", "/api/v1/interview/prompt", {
            "text": text, "session": str(data.get("session_id") or ""),
            "source": opts.get("source") or "claude"})
        if not (isinstance(got, dict) and got.get("ok")):
            why = got.get("why") or got.get("status") if isinstance(got, dict) else got
            print(f"[입력 장부] 기록 안 됨 — {str(why)[:160]}", file=sys.stderr)
    except Exception as e:                              # noqa: BLE001 — fail-open
        print(f"[입력 장부] 건너뜀 — {str(e).splitlines()[0][:160] if str(e) else type(e).__name__}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
