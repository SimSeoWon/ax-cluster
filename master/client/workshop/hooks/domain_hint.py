"""PostToolUse 훅 — 편집한 파일의 이웃 컨텍스트를 **마스터에서** 찾아 세션에 물려준다.

## [중요] 원전 훅은 우리 이식본에서 한 번도 작동할 수 없었다 (실측 2026-08-30)

원전(`~/AgentTest`)의 이 훅은 로컬 `.claude/mcp/context_search.exe` 를 불렀다. 그 exe 는
**2026-08-20 에 은퇴했다** — 온톨로지가 마스터로 옮겨져 로컬 인덱스가 낡았기 때문이다
(`workshop/CLAUDE.md` MCP 표 · `workshop/README.md` §1 표: 대응물은 *"마스터
`ax-projects`(8103) + `ax-client` 조회 9종"*). 그런데 훅 본문은 그대로 배달됐다:

    exe = Path(cwd) / ".claude" / "mcp" / "context_search.exe"
    if not exe.exists():
        return                      # ← `.33` 에 `.claude/mcp/` 자체가 없다 (Test-Path False)

`#337` 이 등록 배선을 고쳐 훅이 **실제로 돌기 시작했고**(실측: rc=0), 그러자 안쪽의 이
빈 껍데기가 드러났다. 이 파일은 그 본문을 마스터 호출로 바꾼 것이다.

## 배선 — 새로 만들지 않고 **배달된 것**을 쓴다

`.ax/lib/axmaster/clientside/client_mcp.py` 가 이미 이 체크아웃에 있다(마스터가 배달한다).
거기 `projects_api()` 가 `.ax/config.json` 에서 마스터 주소를 읽고, `tool_search_context()`
가 8103 의 `/api/v1/search/combined` 를 부른다. HTTP 를 여기서 다시 짜면 주소·태그·오류
문구가 **두 벌**이 된다 — 이 저장소가 `mcp_for` 에서 값을 치른 그 실수다.

## [중요] 원전의 `_domains/` 필터는 버렸다 — 실측이 그렇게 시켰다

원전은 결과에서 `"_domains/" in file` 인 것만 골랐다(그 기계의 로컬 인덱스 레이아웃이다).
마스터 응답에는 **그런 경로가 없다** (실측 2026-08-30, `n=8`):

    Source/NS/Variant_Combat/Interfaces/CombatActivatable.md   [전투 시스템/인터페이스/상호작용 계약]
    Source/NS/Variant_Combat/AI/CombatEnemy.md                 [전투/AI/적 개체]

경로는 소스 트리를 따르고 **도메인 축은 `category` 필드**다. 원전 필터를 그대로 옮겼으면
언제나 0건이었을 것이다. 응답 항목의 키도 실측이다 — `file`·`score`·`source`·`category`·
`tags`·`body`. [주의] 원전이 읽던 `content_preview` 는 **우리 응답에 없다.**

## [주의] 실패하면 한 줄로 말한다 — 조용히 넘어가지 않는다

원전은 `except Exception: pass` 였다. 이 저장소의 규약은 반대다(*"조용한 빈 결과 금지"* —
`client_mcp._call` 의 `[미연결]` 안내가 그 형태다). 다만 편집마다 도는 자리라 **한 줄**로
줄인다. stderr 로 나간 것은 세션이 읽는다.
"""
import json
import sys
from pathlib import Path

N_RESULTS = 3
BODY_CHARS = 300

# [중요] **훅은 편집마다 돈다 — 스스로 먼저 끊는다.** 실측 2026-08-30: 정상 왕복 ~1.3초.
#    그런데 클라의 `HTTP_TIMEOUT` 은 30초이고 우리가 등록한 훅 timeout 은 10초라, 마스터가
#    죽으면 **편집마다 10초를 끌다 강제 종료**된다(사람의 기계에서 그 비용이 가장 비싸다).
#    여기서 먼저 끊으면 한 줄 사유를 남기고 정상 종료한다 — 죽는 것과 말하고 멈추는 것은 다르다.
HTTP_TIMEOUT_SEC = 5


def _load_client(cwd: Path):
    """배달된 클라 페이로드를 끌어온다. 페이로드 독스트링이 지시한 방식 그대로."""
    lib = cwd / ".ax" / "lib"
    if not lib.is_dir():
        raise RuntimeError(f".ax/lib 가 없다 — 마스터 배달 전이다 ({lib})")
    sys.path.insert(0, str(lib))
    from axmaster.clientside import client_mcp          # noqa: PLC0415
    return client_mcp


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return                       # 훅 입력이 JSON 이 아니면 우리가 낄 자리가 아니다
    file_path = str((data.get("tool_input") or {}).get("file_path") or "")
    if not file_path:
        return
    cwd = Path(str(data.get("cwd") or "."))

    try:
        client_mcp = _load_client(cwd)
    except Exception as e:                              # noqa: BLE001
        print(f"[도메인 힌트] 건너뜀 — {e}", file=sys.stderr)
        return

    # [중요] 콘솔 UTF-8 강제 — 한글 윈도우(CP949)에서 카테고리·본문을 print 하면
    #    UnicodeEncodeError 로 **한 줄도 없이 즉사**한다 (`master/utf8.py` 참조).
    try:
        from axmaster import utf8                       # noqa: PLC0415
        utf8.enforce()
    except Exception:                                   # noqa: BLE001
        pass                                            # 강제 실패가 힌트를 막을 이유는 없다

    query = Path(file_path).stem
    if not query:
        return
    client_mcp.HTTP_TIMEOUT = HTTP_TIMEOUT_SEC          # 위 상수의 근거 참조
    try:
        got = client_mcp.tool_search_context(
            client_mcp.projects_api(cwd), query, n=N_RESULTS)
    except Exception as e:                              # noqa: BLE001
        # [주의] 첫 줄만 — `[미연결]` 안내는 여러 줄이고, 편집마다 도는 자리다
        print(f"[도메인 힌트] {str(e).splitlines()[0]}", file=sys.stderr)
        return

    results = (got or {}).get("results") or []
    if not results:
        return                       # 이웃이 없는 파일은 흔하다 — 그것은 실패가 아니다
    top = results[0]
    lines = [f"[도메인 힌트] {query} 와 가까운 컨텍스트"]
    if got.get("_stale"):
        # [중요] 낡은 응답임을 숨기지 않는다 (#162 계약)
        lines[0] += f"  [주의] 캐시된 응답 — {got.get('_note') or '마스터 미연결'}"
    for r in results:
        lines.append(f"  · {r.get('file', '')}"
                     + (f"  [{r.get('category')}]" if r.get("category") else ""))
    body = str(top.get("body") or "")[:BODY_CHARS]
    if body:
        lines.append(body)
    print("\n".join(lines), file=sys.stderr)


if __name__ == "__main__":
    main()
