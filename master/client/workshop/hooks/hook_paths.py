"""훅이 **자기 체크아웃 루트**를 잡는 자리 — [중요] 선언은 여기 하나다.

🔴 [중요] **세션의 cwd 는 체크아웃 루트가 아니다** (실측 2026-09-20 `.33`).
그리고 그것은 **세션 도중에도 움직인다** — `.33` 에서 cwd 를 하위 폴더로 옮긴 것은 사람이
아니라 세션의 모델이었다(Bash `cd …\\Source\\NS`, 11:22:55 → 32초 뒤 첫 차단).
하위 폴더에서 `claude` 를 **열어** 재 보면 훅이 받는 값 셋이 **전부** 그 하위 폴더다:

    PROJDIR='C:/Users/USER/Documents/NS/Source/NS'   ← $CLAUDE_PROJECT_DIR 도 마찬가지다
    CWD    ='C:\\Users\\USER\\Documents\\NS\\Source\\NS'
    PAYLOAD_CWD='C:\\Users\\USER\\Documents\\NS\\Source\\NS'

그 자리에는 `.ax/lib` 도 `.ax/config.json` 도 없다. 그래서 훅 셋이 **각자 조용히 반쯤
죽었다** — `pending_works`·`domain_hint` 는 「점검 못 함」 한 줄만 찍었고, `work_completion`
은 **엉뚱한 `Source/NS/.ax/work-notices`** 에 완주 고지를 썼다(⑹ 깨우기는 체크아웃 루트의
그 폴더를 본다).

[중요] **훅 파일이 놓이는 자리는 배달이 정한다** — `<체크아웃>/.claude/hooks/<이름>.py`
(`bundle.workshop_files`). 그러니 루트를 아는 것은 **자기 위치**다. payload 의 `cwd` 는
「사람이 어디서 열었나」이지 「체크아웃이 어디냐」가 아니다 — 둘을 같은 것으로 쓴 것이
이 고장의 본체였다.

[주의] **이것만으로는 안 고쳐진다.** 훅이 아예 못 뜨면(상대경로로 등록돼 인터프리터가
파일을 못 열면) 이 코드는 돌 기회가 없다. 짝은 `bundle.hook_command_for` 의 절대경로다.
"""
from pathlib import Path


def checkout_root(payload_cwd=None) -> Path:
    """이 훅이 속한 체크아웃 루트. 배달된 배치가 아니면 payload 의 `cwd` 로 물러난다.

    [주의] 물러나는 길을 남기는 이유는 **저장소 안에서 도는 테스트** 때문이다 —
    저장소의 `master/client/workshop/hooks/` 는 체크아웃 배치가 아니고, 거기서는
    종전 동작(payload `cwd`)이 맞다.
    """
    here = Path(__file__).resolve()
    if len(here.parents) >= 3:
        root = here.parents[2]                 # <체크아웃>/.claude/hooks/<이름>.py
        if (root / ".claude" / "hooks").is_dir():
            return root
    return Path(str(payload_cwd or "."))


def cwd_notice(payload_cwd, root: Path) -> str:
    """세션을 연 자리가 체크아웃 루트가 아닐 때 낼 한 줄. 같으면 빈 문자열.

    🔴 [중요] **사실만 싣는다 — 명령형을 쓰지 않는다** (`~/CLAUDE.md`, 실측 2026-09-10).
    훅은 사람이 치지 않은 경로라 *"…하세요"* 는 주입으로 거부된 전례가 있다. 그래서
    「무엇이 왔나」만 말하고, 「그래서 무엇을 하나」는 작업장 `CLAUDE.md` 가 말한다.
    [주의] **막지 않는다.** 이 조건은 사람이 고를 수 있는 것이고, 판정이 아니다.
    """
    try:
        here = Path(str(payload_cwd or ".")).resolve()
    except Exception:                                       # noqa: BLE001
        return ""
    try:
        if here == root.resolve():
            return ""
    except Exception:                                       # noqa: BLE001
        return ""
    # [주의] **「열렸다」로 단정하지 않는다** — cwd 는 세션 도중 `cd` 로도 움직인다.
    #    `.33` 의 실제 발단이 그쪽이었다(모델이 Bash 로 `cd`). 둘 다 참인 말만 싣는다.
    return (f"[작업 위치] 이 세션의 작업 디렉터리가 체크아웃 루트가 아니다 — {here}\n"
            f"           체크아웃 루트: {root}\n"
            f"           [주의] 이 자리에서 세션을 **열었다면** `.mcp.json` 의 `ax-client` 가 "
            f"승인 밖이라 붙지 않는다\n"
            f"                  (실측 2026-09-20: 루트 `√ Connected` · "
            f"하위 폴더 `⏸ Pending approval`) — 그러면 `search_context` 등\n"
            f"                  RAG·온톨로지 조회 도구가 이 세션에 없다.")
