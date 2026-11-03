"""자동 코드리뷰 생산자 — 유저 커밋이 원료다 (소 3.3.5 · `#205`).

원전 흐름의 이식: 커밋 감지 → **변경 diff 기반** 리뷰 → `reviews/<작성자>/` 저장.
그 리포트들이 되먹임 소비자(#155~#158: 수집 → 분류 → 주간 플랜 → Redmine)의 원료가 된다.

## [중요] 왜 이것이 핵심 생산자인가 — 게이트 없는 유일한 경로를 덮는다

파이프라인 커밋은 3층 게이트(층1 결정적 · 층2 grounded LLM · 층3 빌드/RunTests)를 지난다.
**유저가 `.33` 에서 손으로 커밋한 코드는 그 어느 게이트도 지나지 않는다** — 자동 리뷰가
그 구멍을 덮는 장치다. 그래서 작성자 제외의 기본값이 파이프라인 신원(`ax-cluster`)이다:
게이트를 지난 코드를 또 리뷰하는 것은 낭비이고, 사람 커밋이 과녁이다.

## 원전 규약 그대로 옮긴 것

    리뷰 범위      변경 diff + 영향 분석만. 무관한 기존 코드 지적 금지(주간 플랜 담당)
    trivial 스킵   변경 라인이 전부 주석/로그/include/공백이면 생략 — 정규식 셋을 글자대로 이식
    작성자 제외    review_exclude_authors — 컨텍스트·색인은 정상, 리뷰만 생략
    리포트 형식    [중요] **소비자(`review_collector`)가 파싱하는 계약**이다:
                   `커밋: \\`<hash>\\`` · `### <모듈>` 절 · 컨벤션 표(파일|항목|위반 내용|라인|심각도)
                   · 안전성 표(파일|위험도|라인|설명|권장 수정). 형식을 바꾸면 소비자가 못 읽는다

## 우리와 다른 것

    실행 자리     원전은 와처가 컨텍스트+리뷰를 LLM 1콜로 통합했다. 우리 합성기는 이미 다른
                  모양으로 실측·확정돼 있어(조각·grounding·게이트) 리뷰를 **합성 다음의 별도
                  스텝**으로 둔다 — 같은 소비자 체인(ax-indexer), 같은 브로커
    유실 처리     리뷰 생성 실패는 색인을 막지 않는다(fail-soft). [중요] 다만 조용하지 않다 —
                  그 커밋의 리뷰는 다시 생기지 않으므로(워터마크 전진) **카나리 대상**이다
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import synth

REVIEWS_DIRNAME = "reviews"
# [주의] 아래 상용 체인은 `review_commit()` 직접 호출의 하위 호환 기본값이다.
# 커밋 리뷰 큐(`#638`)는 `review_runner.agy_only`를 주입하므로 Claude로 폴백하지 않는다.
#   원전 context.py:373 은 task_type="context_review" 로 _call_llm 을 부르고, 로컬 화이트리스트
#   (config.local_llm_tasks)가 없으면 **기본 Claude** 다 — 저장소엔 그 화이트리스트가 없다.
#   처음엔 qwen2.5-coder:14b 로 임의 대체했다가 라이브 실측(2026-08-17, 실 유저 커밋 9efbfc1)에서
#   **예시 골격을 앞세운 재시도까지 2회 모두 산문**을 냈다 — 소비자 파서 기준 이슈 0건.
#   층2에서 "로컬은 못 쓴다"를 측정한 것과 같은 결이고, 원전이 이 일을 Claude 에 두었던
#   이유가 실측으로 재확인된 셈이다. 체인 순서(agy 먼저)는 bench_layer2 실측을 따른다.
REVIEW_TIMEOUT = 240
DEFAULT_EXCLUDE_AUTHORS = ("ax-cluster",)  # 파이프라인 신원 — 게이트를 이미 지났다

# 원전 정규식 — 글자대로 (common_utils.py:30-37)
_TRIVIAL_LOG_RE = re.compile(
    r'\b(?:UE_LOG|UE_LOGFMT|UE_CLOG|LOG_(?:INFO|WARN|WARNING|ERROR|DEBUG|TRACE|VERBOSE)|'
    r'console\.(?:log|info|warn|error|debug)|'
    r'Debug\.(?:Log|LogError|LogWarning|LogFormat)|'
    r'printf|fprintf|cout\s*<<|cerr\s*<<|System\.out\.print)\s*')
_TRIVIAL_COMMENT_RE = re.compile(r'^\s*(?://|/\*|\*/|\*\s|\*$|---|===)')
_TRIVIAL_INCLUDE_RE = re.compile(r'^\s*#\s*include\b')

_SAFE_AUTHOR = re.compile(r'[\\/:*?"<>|\s]+')

# 소비자(원전 review_collector)의 표 정규식 — 검증기가 같은 눈으로 본다
_TABLE_ROW = re.compile(
    r'\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*'
    r'\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|')


def parseable_rows(body: str) -> int:
    """소비자가 뽑아 갈 데이터 행 수. [중요] **소비자와 같은 정규식**으로 센다 — 다른 눈으로
    세면 검증기가 통과시킨 것을 소비자가 못 읽는다."""
    n = 0
    for blk in re.split(r'^###\s+', body, flags=re.M)[1:]:
        for m in _TABLE_ROW.finditer(blk):
            head = m.group(1).strip()
            if head in ("파일", "") or "---" in head or "---" in m.group(2):
                continue
            n += 1
    return n


_CONV_HEADER = "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |"
_SAFETY_HEADER = "| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |"
# `#815` ④ — 골조 지시 이행 (사용자 결정 2026-10-18: 층2 차단이 아니라 리뷰 큐 지적으로 모은다).
#    구분은 둘 — `불이행`(지시를 안 따랐다) · `골조 모순`(지시가 동결 선언·다른 지시와 충돌, 코드는 한쪽을 따랐다)
_INTENT_HEADER = "| 파일 | 지시([PSEUDO]) | 실제 구현 | 라인 | 구분 |"
INTENT_KINDS = ("불이행", "골조 모순")
_DIFF_FILE_HEAD = re.compile(r'^--- (?:a/|/dev/null)')


def removed_pseudo_lines(diff: str) -> int:
    """diff 에서 **지워진** `[PSEUDO]` 줄 수 — 골조 지시가 본문으로 바뀐 조각 커밋의 흔적.

    결정적 판정이다(LLM 무관). 0 보다 크면 리뷰에 「4. 골조 지시 이행」 절을 요청한다.
    [주의] 일반 diff 의 첫 열만 본다 — 머지 결합 diff(`--cc`)는 조각 커밋이 이미 리뷰했다.
    """
    n = 0
    for line in (diff or "").split("\n"):
        if line.startswith("-") and not _DIFF_FILE_HEAD.match(line) and "[PSEUDO]" in line:
            n += 1
    return n


def format_ok(body: str, *, intent: bool = False) -> bool:
    """`### 모듈` 절 + 두 표 헤더가 있으면 형식 준수 — **데이터 행 0개도 정상이다**
    (위반 없는 커밋의 표는 헤더만 남는다, 원전 규약).

    [중요] 「(없음)」 자리표시 행은 내 발명이었고 소비자(#156)에서 `file="(없음)"` 쓰레기
    이슈가 되는 것이 확인됐다(2026-08-17) — 원전 프롬프트에 그런 규약은 없다. 빈 표는
    비워 둔다.

    `intent` (`#815` ④) — 4절을 **요청한** 리뷰만 그 표 헤더를 요구한다(fail-closed, 1·2절과
    같은 대우). 요청하지 않은 리뷰(옛 리뷰·사람 커밋)는 종전 그대로다."""
    return (bool(re.search(r'^###\s+', body, flags=re.M))
            and _CONV_HEADER in body and _SAFETY_HEADER in body
            and (not intent or _INTENT_HEADER in body))


_FORMAT_EXAMPLE = (
    "### Source/ModularStage/Mission\n\n"
    "## 1. 변경분 코딩 컨벤션\n"
    f"{_CONV_HEADER}\n"
    "|---|---|---|---|---|\n"
    "| Source/ModularStage/Mission/X.cpp | 네이밍 | bFlag 접두 누락 | 12 | 낮음 |\n\n"
    "## 2. 변경분 버그·안전성\n"
    f"{_SAFETY_HEADER}\n"
    "|---|---|---|---|---|\n\n"
    "## 3. 영향 분석\n"
    "호출부 영향 없음.\n\n"
    "(위반·위험이 없으면 위 안전성 표처럼 **헤더만 두고 행을 비워 둔다** — "
    "「없음」 같은 자리표시 행을 만들지 않는다)\n")
_EXAMPLE_ANCHOR = "호출부 영향 없음.\n\n"
# [주의] 예시 표는 비워 둔다 — 행을 보여 주면 과생성을 부른다(review_runner 실측 1.9~6x).
_INTENT_EXAMPLE = (
    "## 4. 골조 지시 이행\n"
    f"{_INTENT_HEADER}\n"
    "|---|---|---|---|---|\n\n")

# `#815` ④ — 측정한 문구(scratchpad l2intent `INTENT_AXIS`, 회수 6/6 · 음성 1/36)를 표 계약에 맞춰 옮겼다
_INTENT_RULES = (
    "  ## 4. 골조 지시 이행 (이 커밋은 골조 지시를 본문으로 바꾼 조각이다 — 각 `### ` 절에 이 표도 쓴다)\n"
    f"  {_INTENT_HEADER}\n"
    "- 골조 지시 이행은 지적만 한다(차단·판정이 아니다). DIFF 에서 **지워진** `[PSEUDO]`·`[DOC]` "
    "주석이 이 변경의 작업 지시서다. 지시 하나하나를 그 자리에 **추가된** 코드와 대조한다.\n"
    "  - 지시가 요구한 동작을 코드가 실제로 구현했는지 본다: 필요한 단계, 반환값과 모양, 조건, "
    "더하거나 지울 이름, 그리고 「하지 말라」고 한 것.\n"
    "  - 어긋난 지시마다 한 행: `지시([PSEUDO])` 칸에 지시 요지, `실제 구현` 칸에 코드가 대신 한 것, "
    "`구분` 은 `불이행`.\n"
    "  - 지시가 선언부(동결된 시그니처·선언)나 다른 지시와 모순되면 `구분` 을 `골조 모순` 으로 하고, "
    "`실제 구현` 칸에 코드가 어느 쪽을 따랐는지 적는다.\n"
    "  - 지시가 요구한 것을 넘어서는 스타일·명명·설계 취향은 이 표에 적지 않는다.\n"
    "  - 모든 지시가 이행됐으면 표 헤더만 두고 행을 비운다. 자리표시 행은 쓰지 않는다. 칸 안에 `|` 를 쓰지 않는다.\n"
)


# 🔴 `#846` — 퇴고 백엔드(agy)는 도구를 쓰는 에이전트다. 지시가 없으면 저장소를 뒤지고 테스트를
#    돌리다 240초 한도에 걸렸다(실측 10-11~10-30 퇴고 90건: 200초 이상 37건은 평균 도구 호출 25.5회·
#    테스트 실행 23/37, 120초 미만 34건은 6.0회·7/34 · 10-01 이후 260회 중 타임아웃 63회). 판단에 필요한
#    것(골격·예시·diff·선언부)은 이미 프롬프트에 있으므로 작업 범위를 그만큼으로 적는다.
_SCOPE_RULES = (
    "- 작업 범위: 판단 근거는 아래 DIFF·실측 근거·변경 파일 목록으로 충분하다. 파일을 열어야 하면 "
    "변경 파일과 그 직접 호출부만 필요한 만큼 본다.\n"
    "- 테스트·린트·빌드·타입 검사를 실행하지 않는다. 저장소 전체나 홈 디렉터리를 검색(find·grep -r 등)"
    "하지 않는다. 출력 형식은 아래 골격이 전부다 — 다른 리뷰 파일이나 예시를 찾지 않는다.\n"
    "- 근거가 모이면 바로 리뷰를 출력한다.\n"
)


def _git(repo: Path, *args: str) -> tuple:
    """미러 클론에서 **로컬 객체만** 읽는다 — fetch 가 아니라서 `gitea` 그룹이 필요 없다.

    [주의] fetch 를 여기서 하면 안 된다: bare 저장소 접근은 그룹 판정이 필요하고 그 실패는
    *"저장소가 아니다"* 로 원인을 감춘다. fetch 는 색인기(`events.consumer`)의 일이고,
    이 모듈이 도는 시점에는 커밋이 이미 로컬에 있다.
    """
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def parent_count(repo: Path, commit: str) -> int:
    """커밋의 부모 수. 읽지 못하면 -1 (`#744` ①).

    [주의] 실패를 0(루트)이나 1(일반)로 접지 않는다 — 호출자가 「머지가 아니다」로 읽고
    결정적 실패 경로(diff 없음)로 가는 것이 맞다. 「머지라서 스킵」으로 새면 안 된다.
    """
    rc, out = _git(repo, "rev-list", "--parents", "-n", "1", commit)
    toks = out.split() if rc == 0 else []
    return len(toks) - 1 if toks else -1


def _show_diff(repo: Path, files: list, commit: str, *, unified: int, merge: bool) -> tuple:
    """`git show` 의 diff 부분. 머지는 **결합 diff(`--cc`)** 를 명시한다 (`#744` ①).

    [중요] 머지의 `git show` 는 원래 결합 diff 다 — 어느 부모에서도 그대로 온 hunk 는 빠지고
    **충돌 해소·머지 안에서 고친 것**만 남는다. 깨끗한 머지면 비어 있다. 명시하는 이유는
    그 뜻을 코드에 남기기 위해서다(기본값에 기대면 「왜 비었나」가 안 보인다 — 15건이 그랬다).
    """
    args = ["show", "--pretty=format:", f"--unified={unified}", "--no-color"]
    if merge:
        args.append("--cc")
    return _git(repo, *args, commit, "--", *files)


def is_trivial_diff(repo: Path, files: list, commit: str) -> bool:
    """변경 라인이 전부 주석/로그/include/공백이면 True — 원전 로직 글자대로.

    새 파일·삭제·git 실패·빈 diff 는 보수적으로 False(정상 리뷰 진행).
    [주의] 머지의 결합 diff 는 줄 머리가 **부모 수만큼의 열**이다(`++`·` +`·`- `) — 첫 글자만
    보면 한쪽 부모 대비 변경을 문맥으로 읽어 판정이 틀어진다 (`#744` ①).
    """
    if not files:
        return False
    n = parent_count(repo, commit)
    width = n if n >= 2 else 1
    rc, diff = _show_diff(repo, files, commit, unified=0, merge=width >= 2)
    if rc != 0 or not diff.strip():
        return False
    for line in diff.split("\n"):
        if line.startswith("--- /dev/null") or line.startswith("+++ /dev/null"):
            return False
    found = False
    for line in diff.split("\n"):
        if not line:
            continue
        if line.startswith(("+++", "---", "@@", "diff ", "index ", "new file",
                            "deleted file", "similarity ", "rename ", "mode ")):
            continue
        head = line[:width]
        if not any(ch in "+-" for ch in head):
            continue
        content = line[width:]
        if not content.strip():
            continue
        found = True
        if _TRIVIAL_COMMENT_RE.match(content):
            continue
        if _TRIVIAL_INCLUDE_RE.match(content):
            continue
        if _TRIVIAL_LOG_RE.search(content):
            continue
        return False
    return found


def commit_author(repo: Path, commit: str) -> str:
    rc, out = _git(repo, "log", "-1", "--format=%an", commit)
    return out.strip() if rc == 0 else ""


MERGE_DIFF_HEADER = ("(머지 커밋의 결합 diff(`--cc`) — 충돌 해소·머지 안에서 고친 부분만이다. "
                     "줄 머리의 열 하나가 부모 하나다. 각 부모의 일반 변경은 조각 커밋이 따로 리뷰했다)")
MERGE_SKIP_NOTE = "스킵: 머지 — 조각 커밋이 리뷰했다"


def is_clean_merge(repo: Path, files: list, commit: str) -> bool:
    """머지이고 그 파일들의 결합 diff 가 **읽혔는데 비었으면** True (`#744` ①).

    [주의] git 실패는 False 다 — 실패를 「깨끗한 머지」로 읽으면 리뷰가 조용히 「완료」로
    사라진다. 그때는 종전처럼 결정적 실패(「diff 를 읽지 못했다」)로 남아야 사람이 본다.
    """
    if parent_count(repo, commit) < 2:
        return False
    rc, out = _show_diff(repo, files, commit, unified=3, merge=True)
    return rc == 0 and not out.strip()


def commit_diff(repo: Path, files: list, commit: str, *, max_chars: int = 24000) -> str:
    """리뷰 프롬프트에 실을 diff (unified=3). [중요] 상한을 두고 자르면 **잘렸다고 말한다**.

    머지(부모 둘 이상)는 결합 diff 만 돌려준다 — 비어 있으면 빈 문자열이고, 그것은 실패가
    아니라 「깨끗한 머지」다(`#744` ①). 그 판정은 호출자가 `parent_count` 로 가른다. 비어 있지
    않으면 머리에 `MERGE_DIFF_HEADER` 를 붙인다 — 초고·퇴고 모델이 결합 형식을 일반 diff 로
    읽지 않게.
    """
    merge = parent_count(repo, commit) >= 2
    rc, out = _show_diff(repo, files, commit, unified=3, merge=merge)
    if rc != 0:
        return ""
    d = out.strip()
    if len(d) > max_chars:
        d = d[:max_chars] + "\n... (diff 가 잘렸다 — 여기까지만 리뷰 대상이다)"
    if merge and d:
        d = MERGE_DIFF_HEADER + "\n\n" + d
    return d


def domain_hint(paths, files: list) -> str:
    """변경 파일이 속한 도메인의 요약 한 줄 — 원전의 「도메인 컨텍스트 주입」 대응.

    베스트에포트 — 못 찾으면 빈 문자열(리뷰를 막지 않는다).
    """
    try:
        from ..ontology import yaml_io
    except ImportError:
        return ""
    stems = {Path(f).stem for f in files}
    hints = []
    droot = Path(paths.ontology) / "domains"
    if not droot.is_dir():
        return ""
    for man in sorted(droot.glob("*/domain.yaml")):
        try:
            data = yaml_io.read(man) or {}
        except Exception:                                     # noqa: BLE001
            continue
        text = man.read_text(encoding="utf-8", errors="replace")
        if any(stem in text for stem in stems):
            summ = str(data.get("summary") or "")[:200]
            hints.append(f"- {data.get('domain', man.parent.name)}: {summ}")
        if len(hints) >= 2:
            break
    return "\n".join(hints)


def build_prompt(*, diff: str, files: list, commit: str, domains: str = "",
                 grounding: str = "", kind: str = "unreal", intent: bool = False,
                 subject: str = "", history: str = "") -> str:
    """리뷰 프롬프트. [중요] 표 형식은 소비자의 파싱 계약이다 — 열 순서를 바꾸지 말 것.

    `intent` (`#815` ④) — 지워진 `[PSEUDO]` 가 있을 때만 4절 규칙·예시를 싣는다.
    False 면 종전과 **바이트 단위로 같다**(테스트가 해시로 지킨다).
    `subject` (`#879`) — 범위 리뷰의 대상 이름(예 「일감 #879 범위 a..b (커밋 3건)」). 비우면 종전과
    바이트 단위로 같다.
    `history` (`#879`) — 범위 리뷰의 수정 기록(커밋 순서·제목·본문). 비우면 종전과 바이트 단위로 같다."""
    python = kind == "code"
    role = "Python" if python else "Unreal Engine 5 C++"
    example = format_example(kind, intent=intent)
    return (
        f"당신은 {role} 코드 리뷰어다. 아래 "
        + ("범위(여러 커밋을 합친 diff)" if subject else "커밋")
        + "의 **변경분만** 리뷰하라.\n\n"
        "규칙 (어기면 리포트가 못 쓰게 된다):\n"
        "- 리뷰 범위는 변경된 라인과 그 직접 영향뿐이다. 변경되지 않은 기존 코드의 무관한 "
        "이슈는 보고 금지.\n"
        "- 지적할 것이 없는 섹션은 표 헤더만 두고 데이터 행은 비운다. 자리표시 행은 쓰지 않는다.\n"
        "- 심각도/위험도는 높음·중간·낮음 셋 중 하나.\n"
        + _SCOPE_RULES
        +
        "- 모듈(디렉토리) 단위로 `### <모듈>` 절을 만들고, 각 절 안에 아래 두 표를 쓴다.\n"
        "- 표 형식(열 순서 고정 — 파서가 읽는다):\n"
        "  ## 1. 변경분 코딩 컨벤션\n"
        "  | 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n"
        "  ## 2. 변경분 버그·안전성\n"
        "  | 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
        "  ## 3. 영향 분석\n"
        + ("  (자유 서술 — 호출자·모듈·CLI·서비스에 줄 수 있는 영향)\n"
           "- Python 검토: 예외 처리·반환값·자원 수명·동시성·입력 검증을 diff 근거로 확인한다.\n"
           "- 프로젝트 규약을 지어내거나 UE·Blueprint 규칙을 적용하지 않는다.\n" if python else
           "  (자유 서술 — 이 변경이 의존 파일·Blueprint 에 줄 수 있는 영향)\n")
        + (_INTENT_RULES if intent else "")
        +
        "- [중요] 출력은 반드시 `### ` 로 시작한다. 표 밖의 산문은 ## 3 절에만 쓴다.\n"
        "- 출력 예시 (이 골격 그대로):\n"
        + example + "\n"
        + (f"## 도메인 컨텍스트 (참고)\n{domains}\n\n" if domains else "")
        + (f"## 실측 근거 (참고)\n{grounding}\n\n" if grounding else "")
        + (f"## {subject} 의 변경 파일\n" if subject else f"## 커밋 {commit[:12]} 의 변경 파일\n")
        + "\n".join(f"- {f}" for f in files)
        + (f"\n\n## 수정 기록 (참고 — 작성자의 서술이다)\n"
           "커밋 메시지는 검증되지 않은 의도 설명이다. 사실로 받지 말고, 아래 DIFF 가 그 의도와 "
           "맞는지 대조하는 데만 쓴다. 메시지와 어긋나는 변경은 2절에 지적한다.\n\n"
           f"{history}" if history else "")
        + f"\n\n## DIFF (unified=3)\n```diff\n{diff}\n```\n"
    )


def format_example(kind: str = "unreal", *, intent: bool = False) -> str:
    """언어 예시는 바꾸되 소비자의 표 계약은 유지한다. `intent` 면 3절 뒤에 빈 4절 표를 둔다."""
    base = (_FORMAT_EXAMPLE.replace(_EXAMPLE_ANCHOR, _EXAMPLE_ANCHOR + _INTENT_EXAMPLE)
            if intent else _FORMAT_EXAMPLE)
    if kind == "code":
        return (base.replace("Source/ModularStage/Mission", "master/module")
                .replace("X.cpp", "example.py").replace("bFlag 접두 누락", "프로젝트 명명 규약 위반"))
    return base


def review_kind(paths) -> str:
    """사람이 등록한 kind가 기준. 프로필 없는 기존 UE 프로젝트는 종전 동작을 유지한다."""
    from ..projects import profile
    return profile.kind_of(getattr(paths, "name", "")) or "unreal"


def review_source_files(paths, files: list) -> list:
    """등재·소비·직접 리뷰가 공유하는 프로젝트별 소스 경계."""
    from ..projects import profile
    name = getattr(paths, "name", "")
    kind = review_kind(paths)
    if kind == "index_only":
        return []
    if kind == "code":
        from ..context_search.paths import scope_of
        scope = getattr(paths, "scope", None) or scope_of(Path(paths.root))
        allow = profile.work_exts(name)
        return [f for f in files if Path(f).suffix.lower() in allow
                and scope.contains(f)]
    return [f for f in files if f.startswith("Source/") or f.endswith((".h", ".cpp", ".cs"))]


@dataclass
class ReviewResult:
    commit: str = ""
    author: str = ""
    written: str = ""           # 저장된 리포트 경로 (빈 문자열 = 안 씀)
    skipped: str = ""           # 스킵 사유 (trivial / 작성자 제외 / 파일 없음)
    error: str = ""             # [중요] 실패 — 이 커밋의 리뷰는 다시 생기지 않는다 (카나리 대상)
    format_ok: bool = True      # [중요] False = 사람은 읽어도 **소비자는 0건으로 읽는다** (카나리)
    retried: bool = False
    pseudo_removed: int = 0     # `#815` ④ — 지워진 [PSEUDO] 줄 수. >0 이면 4절을 요청했다
    serial: str = ""            # 수정 항목 번호 (`#627` — R35). 비면 부여 실패 → `serial_error`
    serial_error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def commercial_chat(prompt: str, *, timeout: int = REVIEW_TIMEOUT,
                    workdir=None) -> str:
    """직접 호출 하위 호환용 상용 체인. 리뷰 큐는 이 함수를 쓰지 않는다.

    `workdir` (`#825`) — 상용 CLI 는 파일을 읽는 에이전트다. 소스를 프롬프트에 싣는 대신 그
    디렉터리를 작업 디렉터리로 준다. 원전 `master_orchestrator/common.py:418`
    `call_cli_llm(prompt, cwd=...)` 와 호출부(`llm_tools.py:52,76,126` 의 `cwd=repo_path`)가
    선례인데 이식에서 빠졌다. 우리는 더 좁다 — 고정 SHA 의 분리 worktree 를 준다
    (`pinned_tree.pinned_worktree`). [주의] `None` 이면 종전 그대로 `fn(prompt, timeout=…)` 로
    부른다 — `WHY_BACKENDS` 를 바꿔 끼운 가짜가 그 모양만 받는다.

    [중요] **실패 사유를 예외에 싣는다** (`#285`, 사용자 지적 2026-08-23). 종전 메시지는
    *"둘 다 응답 없음"* 이었는데, 실측된 진짜 원인은 **systemd 유닛에 PATH 가 없어 `which` 가
    실패**한 것이었다(NS 리뷰 26건). 「응답 없음」은 서비스 장애로 읽히므로 **엉뚱한 곳을
    파게 만든다** — 없는 로그보다 틀린 로그가 비싸다. 원전 `call_agy` 는 처음부터 갈라 놨다.
    """
    from .. import layer2_verify as l2
    whys = []
    for name, fn in l2.WHY_BACKENDS:
        kw = {} if workdir is None else {"workdir": str(workdir)}
        out, why = fn(prompt, timeout=timeout, **kw)
        if out and out.strip():
            return out
        whys.append(f"{name}: {why or '사유 미기록'}")
    raise ReviewChatError("상용 체인(agy → claude) 실패 — " + " · ".join(whys))


class ReviewChatError(RuntimeError):
    pass


def _recorded_chat(paths, commit: str):
    """기본 체인(`commercial_chat`)을 그 트윈의 `usage_log.jsonl` 에 `review` 로 남기며 부른다 (`#733`).

    [중요] `commercial_chat` 자체에는 트윈도 커밋도 없다 — 그래서 커밋이 보이는 이 자리에서 감싼다.
    task_id 는 리뷰 큐와 같은 `commit[:12]` 다. [주의] `chat` 을 주입한 경로(리뷰 큐의 `agy_only`)는
    여기를 타지 않는다 — 그쪽은 `review_runner` 가 같은 모양으로 이미 감싼다.
    [주의] 계획·레시피(`plan_generator`·`recipes_synthesizer`)의 직접 호출은 트윈을 모르므로 남지 않는다.
    """
    log = getattr(paths, "usage_log", None)
    if log is None:
        return commercial_chat

    def _ask(prompt: str) -> str:
        from ..work import usage as usage_mod                    # noqa: PLC0415
        with usage_mod.sink(log, source="review", task_id=str(commit)[:12]):
            return commercial_chat(prompt)
    return _ask


def review_commit(paths, commit: str, files: list, *,
                  exclude_authors: tuple = DEFAULT_EXCLUDE_AUTHORS,
                  chat=None, logf=None, grounding: str = "",
                  provenance: dict | None = None) -> ReviewResult:
    """커밋 하나의 변경분을 리뷰해 `reviews/<작성자>/` 에 쓴다.

    `chat(prompt) -> str` 주입은 테스트와 리뷰 큐의 백엔드 선택 자리다. 리뷰 큐는
    `review_runner.agy_only`를 주입해 Antigravity만 호출한다.

    [중요] **`grounding` 은 프롬프트에 자리만 있고 실전에서 비어 있었다** (`#636` 이 채운다).
    리뷰 큐 소비자가 **로컬 초고 + 선언부**를 여기로 넘긴다. 층2 실측(2026-08-12)이 잰 것이
    바로 이 축이다 — 선언부가 없으면 후보 5개 중 4개가 지어낸 enum 을 못 잡았고, 넣으면
    전부 잡았다.
    🔴 [주의] **초고는 사실 게이트를 안 받은 글이다.** 그대로 받아 적히면 「참조」가 아니라
    「지시」가 된다 — 호출자가 미검증임을 명시해서 넘긴다(`review_runner.GROUNDING_HEADER`).
    """
    log = logf or (lambda s, m: None)
    r = ReviewResult(commit=commit)
    src_files = review_source_files(paths, files)
    if not src_files:
        r.skipped = "소스 변경 없음"
        return r

    repo = Path(paths.repo)
    r.author = commit_author(repo, commit)
    if r.author in (exclude_authors or ()):
        # 파이프라인 커밋 — 3층 게이트를 이미 지났다. 리뷰 생략, 컨텍스트·색인은 정상.
        r.skipped = f"작성자 제외: {r.author}"
        return r
    if is_trivial_diff(repo, src_files, commit):
        r.skipped = "trivial (주석/로그/include 만)"
        return r

    diff = commit_diff(repo, src_files, commit)
    if not diff and is_clean_merge(repo, src_files, commit):
        # `#744` ① (사용자 결정 2026-10-05) — 깨끗한 머지. 들어온 변경은 조각 커밋이 리뷰했다.
        r.skipped = MERGE_SKIP_NOTE.removeprefix("스킵: ")
        log("review", f"{commit[:8]} 머지 — 결합 diff 없음, 스킵")
        return r
    if not diff:
        r.error = "diff 를 읽지 못했다 — 리뷰 없이 넘기지 않고 기록한다"
        return r

    r.pseudo_removed = removed_pseudo_lines(diff)
    intent = r.pseudo_removed > 0
    log("review", f"{commit[:8]} 골조 지시 이행 절 {'요청' if intent else '미요청'} "
                  f"— 지워진 [PSEUDO] {r.pseudo_removed}줄")
    prompt = build_prompt(diff=diff, files=src_files, commit=commit,
                          domains=domain_hint(paths, src_files), grounding=grounding,
                          kind=review_kind(paths), intent=intent)
    _ask = chat if chat is not None else _recorded_chat(paths, commit)

    try:
        body = _ask(prompt)
        # [중요] 형식 검증은 어떤 백엔드에도 그대로 둔다 — 첫 라이브 런(2026-08-17)의 교훈은
        #    "형식은 지시가 아니라 검증이 지킨다"였고, 그 결은 모델과 무관하다.
        #    grounding 과 같은 자리: 계약 위반은 조용히 통과시키지 않는다.
        if not format_ok(body or "", intent=intent):
            r.retried = True
            log("review", f"{commit[:8]} 형식 위반 — 예시를 앞세워 1회 재시도")
            body = _ask("직전 응답이 형식을 어겼다. 아래 골격 **그대로**, `### ` 로 시작해 "
                        "표만으로 다시 써라. 표 밖 산문은 ## 3 에만.\n\n"
                        + format_example(review_kind(paths), intent=intent) + "\n\n" + prompt)
    except ReviewChatError as e:
        r.error = f"리뷰 생성 실패: {e}"
        return r
    if not (body or "").strip():
        r.error = "리뷰 응답이 비었다"
        return r
    r.format_ok = format_ok(body, intent=intent)

    from datetime import datetime
    ts = datetime.now()
    safe = _SAFE_AUTHOR.sub("_", r.author or "unknown").strip("_") or "unknown"
    out_dir = Path(paths.root) / REVIEWS_DIRNAME / safe
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{ts.strftime('%Y-%m-%d_%H%M')}_{commit[:8]}.md"
    trace = ""
    if provenance:
        if provenance.get("draft_model"):
            trace += f"- 초안 모델: {provenance['draft_model']}\n"
        if provenance.get("review_model"):
            trace += f"- 검증 모델: {provenance['review_model']}\n"
    head = (f"# 자동 코드 리뷰 — {commit[:12]}\n\n"
            f"- 커밋: `{commit}`\n- 작성자: {r.author}\n"
            f"- 파일: {len(src_files)}개\n- 생성: {ts.strftime('%Y-%m-%d %H:%M')}\n\n")
    if trace:
        head = head.rstrip() + "\n" + trace + "\n"
    path = out_dir / fname
    # 같은 디렉토리의 임시 파일을 원자적으로 교체한다. 중간 종료 때 반쪽 리뷰가 게시판과
    # 주말 플랜에 보이는 일을 막는다.
    tmp = path.with_name("_writing_" + path.name)
    tmp.write_text(head + body.strip() + "\n", encoding="utf-8")
    tmp.replace(path)
    r.written = str(path)
    if not r.format_ok:
        # 사람은 읽을 수 있으니 버리지 않는다 — 다만 소비자에겐 0건이므로 시끄럽게 남긴다
        log("review", f"[중요] {path.name} 형식 위반 — 소비자 파서 기준 이슈 0건")
    else:
        log("review", f"{r.author} {commit[:8]} → {path.name} (행 {parseable_rows(body)})")
    # 번호(`#627`)는 여기서 바로 준다 — 저널에 「이 커밋 = R35」가 남아야 사람이 번호로 찾는다.
    #    [주의] **로그가 아니라 결과 필드로 올린다.** 소비자가 이 함수를 `logf` 없이 불러 위의
    #    `log` 는 빈 함수다(실측 2026-09-16 — 처음엔 로그로 넣었고 저널에 한 줄도 안 찍혔다).
    #    소비자가 `rv.serial` 을 요약 줄에 싣는다. 실패해도 리뷰는 저장됐다 — 다음 목록 조회가 붙인다.
    try:
        from .fix_index import serial_for_commit, sweep
        sweep(paths.root)
        r.serial = serial_for_commit(paths.root, commit)
        if not r.serial:
            r.serial_error = "색인에서 이 커밋을 찾지 못했다"
    except Exception as e:                                   # noqa: BLE001
        r.serial_error = type(e).__name__
    log("review", f"[fix] 번호 {r.serial or '없음(' + r.serial_error + ')'} ← {path.name}")
    return r


# ── 범위 리뷰 (`#879`) ───────────────────────────────────────────────────────
#
# 일감 하나의 시작~끝 커밋을 합친 diff 를 한 번 리뷰한다. 사용자 결정(2026-11-03):
# 커밋 단위 리뷰는 그대로 두고 **둘 다** 만든다 · 게시판에는 번호(R)로 올리되 **주간 플랜 집계에서는
# 뺀다** — 같은 지적이 두 번 세지지 않게. 그래서 `reviews/_range/` 에 둔다: `_` 접두 디렉토리는
# 작성자가 아니라서 planner·plan_archive 가 안 읽고, `fix_index` 만 따로 읽는다.
# [중요] 파일명은 `<시각>_issue<N>_<시작8>-<끝8>.md` 다 — `*_<커밋8>.md` 로 끝나면 색인기의
#    「이미 정상 리뷰가 있다」 판정(`events.consumer`)과 `find_final_review` 가 이 파일을 끝 커밋의
#    리뷰로 읽고 **커밋 리뷰를 조용히 건너뛴다.**
# [중요] diff 에 크기 상한을 두지 않는다 — 상용 LLM 경로에 상한 금지(사용자 결정 2026-11-03).

RANGE_DIRNAME = "_range"
RANGE_TITLE = "# 자동 범위 리뷰 —"


def range_commits(repo: Path, base: str, end: str) -> list | None:
    """`base..end` 의 커밋(오래된 것부터). 읽지 못하면 None — 빈 범위(`[]`)와 구분한다."""
    rc, out = _git(repo, "rev-list", "--reverse", f"{base}..{end}")
    return out.split() if rc == 0 else None


def range_files(repo: Path, base: str, end: str) -> list | None:
    rc, out = _git(repo, "diff", "--name-only", "--no-renames", base, end)
    return [x for x in out.splitlines() if x.strip()] if rc == 0 else None


def range_history(repo: Path, base: str, end: str) -> str:
    """수정 기록 — 오래된 커밋부터 `### <해시12> <제목>` + 본문. 읽지 못하면 빈 문자열.

    [주의] **본문의 `Co-Authored-By` 줄은 뺀다** — 리뷰에 쓸모없는 서명이다. 자르지 않는다.
    """
    sep = "\x1e"
    rc, out = _git(repo, "log", "--reverse", f"--format=%H%x1f%s%x1f%b{sep}", f"{base}..{end}")
    if rc != 0:
        return ""
    parts = []
    for rec in out.split(sep):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        h, _, rest = rec.partition("\x1f")
        subj, _, body = rest.partition("\x1f")
        body = "\n".join(ln for ln in body.strip().splitlines()
                         if not ln.lower().startswith("co-authored-by:")).strip()
        parts.append(f"### {h.strip()[:12]} {subj.strip()}" + (f"\n{body}" if body else ""))
    return "\n\n".join(parts)


def range_diff(repo: Path, files: list, base: str, end: str) -> str:
    """`base` 와 `end` 사이 합친 diff (unified=3). 실패·빈 diff 는 빈 문자열. **자르지 않는다.**"""
    rc, out = _git(repo, "diff", "--unified=3", "--no-color", base, end, "--", *files)
    return out.strip() if rc == 0 else ""


def range_review_name(issue_id, base: str, end: str, ts) -> str:
    return f"{ts.strftime('%Y-%m-%d_%H%M')}_issue{int(issue_id)}_{base[:8]}-{end[:8]}.md"


def find_range_review(paths, base: str, end: str) -> Path | None:
    """이미 게시된 정상 범위 리뷰 — 재시도 때 모델 중복 호출을 막는다."""
    d = Path(paths.root) / REVIEWS_DIRNAME / RANGE_DIRNAME
    if not d.is_dir():
        return None
    for path in sorted(d.glob(f"*_{base[:8]}-{end[:8]}.md"), reverse=True):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text.startswith(RANGE_TITLE) and f"`{base}..{end}`" in text and format_ok(text):
            return path
    return None


def review_range(paths, issue_id, base: str, end: str, files: list, *,
                 chat=None, logf=None, grounding: str = "",
                 provenance: dict | None = None, commits: int = 0) -> ReviewResult:
    """일감 범위 `base..end` 의 합친 변경분을 리뷰해 `reviews/_range/` 에 쓴다.

    커밋 리뷰(`review_commit`)와 같은 프롬프트·형식 검증·1회 재시도를 쓴다. 작성자 제외·trivial·
    머지 갈래는 없다 — 사람이 일감을 마치며 **요청한** 리뷰라서 거르지 않는다.
    """
    log = logf or (lambda s, m: None)
    r = ReviewResult(commit=end)
    src_files = review_source_files(paths, files)
    if not src_files:
        r.skipped = "소스 변경 없음"
        return r
    repo = Path(paths.repo)
    r.author = commit_author(repo, end)
    diff = range_diff(repo, src_files, base, end)
    if not diff:
        r.error = "범위 diff 를 읽지 못했다 — 리뷰 없이 넘기지 않고 기록한다"
        return r
    r.pseudo_removed = removed_pseudo_lines(diff)
    intent = r.pseudo_removed > 0
    subject = (f"일감 #{int(issue_id)} 범위 {base[:12]}..{end[:12]}"
               + (f" (커밋 {commits}건)" if commits else ""))
    log("review", f"{subject} — diff {len(diff)}자 · 파일 {len(src_files)} · "
                  f"골조 지시 이행 절 {'요청' if intent else '미요청'}")
    history = range_history(repo, base, end)
    log("review", f"{subject} — 수정 기록 {history.count(chr(10) + '### ') + (1 if history else 0)}건 · "
                  f"{len(history)}자")
    prompt = build_prompt(diff=diff, files=src_files, commit=end,
                          domains=domain_hint(paths, src_files), grounding=grounding,
                          kind=review_kind(paths), intent=intent, subject=subject,
                          history=history)
    _ask = chat if chat is not None else _recorded_chat(paths, end)
    try:
        body = _ask(prompt)
        if not format_ok(body or "", intent=intent):
            r.retried = True
            log("review", f"{subject} 형식 위반 — 예시를 앞세워 1회 재시도")
            body = _ask("직전 응답이 형식을 어겼다. 아래 골격 **그대로**, `### ` 로 시작해 "
                        "표만으로 다시 써라. 표 밖 산문은 ## 3 에만.\n\n"
                        + format_example(review_kind(paths), intent=intent) + "\n\n" + prompt)
    except ReviewChatError as e:
        r.error = f"리뷰 생성 실패: {e}"
        return r
    if not (body or "").strip():
        r.error = "리뷰 응답이 비었다"
        return r
    r.format_ok = format_ok(body, intent=intent)

    from datetime import datetime
    ts = datetime.now()
    out_dir = Path(paths.root) / REVIEWS_DIRNAME / RANGE_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / range_review_name(issue_id, base, end, ts)
    trace = ""
    if provenance:
        if provenance.get("draft_model"):
            trace += f"- 초안 모델: {provenance['draft_model']}\n"
        if provenance.get("review_model"):
            trace += f"- 검증 모델: {provenance['review_model']}\n"
    # [주의] 「- 커밋: `<해시>`」 줄을 쓰지 않는다 — fix_index·collector 가 그 줄로 커밋 리뷰를 묶는다.
    head = (f"{RANGE_TITLE} 일감 #{int(issue_id)}\n\n"
            f"- 범위: `{base}..{end}`\n- 일감: #{int(issue_id)}\n"
            f"- 커밋 수: {commits}\n- 작성자: {r.author}\n"
            f"- 파일: {len(src_files)}개\n- 생성: {ts.strftime('%Y-%m-%d %H:%M')}\n" + trace + "\n")
    tmp = path.with_name("_writing_" + path.name)
    tmp.write_text(head + body.strip() + "\n", encoding="utf-8")
    tmp.replace(path)
    r.written = str(path)
    log("review", f"{subject} → {path.name} (행 {parseable_rows(body)}"
                  + ("" if r.format_ok else " · [중요] 형식 위반") + ")")
    try:
        from .fix_index import serial_for_range, sweep
        sweep(paths.root)
        r.serial = serial_for_range(paths.root, base, end)
        if not r.serial:
            r.serial_error = "색인에서 이 범위를 찾지 못했다"
    except Exception as e:                                   # noqa: BLE001
        r.serial_error = type(e).__name__
    log("review", f"[fix] 번호 {r.serial or '없음(' + r.serial_error + ')'} ← {path.name}")
    return r
