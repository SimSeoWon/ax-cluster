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
# [중요] 리뷰 백엔드는 상용 체인(agy → claude) — 원전 기본값의 이식이다.
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


def format_ok(body: str) -> bool:
    """`### 모듈` 절 + 두 표 헤더가 있으면 형식 준수 — **데이터 행 0개도 정상이다**
    (위반 없는 커밋의 표는 헤더만 남는다, 원전 규약).

    [중요] 「(없음)」 자리표시 행은 내 발명이었고 소비자(#156)에서 `file="(없음)"` 쓰레기
    이슈가 되는 것이 확인됐다(2026-08-17) — 원전 프롬프트에 그런 규약은 없다. 빈 표는
    비워 둔다."""
    return (bool(re.search(r'^###\s+', body, flags=re.M))
            and _CONV_HEADER in body and _SAFETY_HEADER in body)


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


def is_trivial_diff(repo: Path, files: list, commit: str) -> bool:
    """변경 라인이 전부 주석/로그/include/공백이면 True — 원전 로직 글자대로.

    새 파일·삭제·git 실패·빈 diff 는 보수적으로 False(정상 리뷰 진행).
    """
    if not files:
        return False
    rc, diff = _git(repo, "show", "--pretty=format:", "--unified=0", "--no-color",
                    commit, "--", *files)
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
                            "deleted file", "similarity ", "rename ")):
            continue
        if line[0] not in ("+", "-"):
            continue
        content = line[1:]
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


def commit_diff(repo: Path, files: list, commit: str, *, max_chars: int = 24000) -> str:
    """리뷰 프롬프트에 실을 diff (unified=3). [중요] 상한을 두고 자르면 **잘렸다고 말한다**."""
    rc, out = _git(repo, "show", "--pretty=format:", "--unified=3", "--no-color",
                   commit, "--", *files)
    if rc != 0:
        return ""
    d = out.strip()
    if len(d) > max_chars:
        d = d[:max_chars] + "\n... (diff 가 잘렸다 — 여기까지만 리뷰 대상이다)"
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
                 grounding: str = "") -> str:
    """리뷰 프롬프트. [중요] 표 형식은 소비자의 파싱 계약이다 — 열 순서를 바꾸지 말 것."""
    return (
        "당신은 Unreal Engine 5 C++ 코드 리뷰어다. 아래 커밋의 **변경분만** 리뷰하라.\n\n"
        "규칙 (어기면 리포트가 못 쓰게 된다):\n"
        "- 리뷰 범위는 변경된 라인과 그 직접 영향뿐이다. 변경되지 않은 기존 코드의 무관한 "
        "이슈는 보고 금지.\n"
        "- 지적할 것이 없는 섹션은 표에 `| (없음) | - | - | - | - |` 한 줄만 쓴다.\n"
        "- 심각도/위험도는 높음·중간·낮음 셋 중 하나.\n"
        "- 모듈(디렉토리) 단위로 `### <모듈>` 절을 만들고, 각 절 안에 아래 두 표를 쓴다.\n"
        "- 표 형식(열 순서 고정 — 파서가 읽는다):\n"
        "  ## 1. 변경분 코딩 컨벤션\n"
        "  | 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n"
        "  ## 2. 변경분 버그·안전성\n"
        "  | 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
        "  ## 3. 영향 분석\n"
        "  (자유 서술 — 이 변경이 의존 파일·Blueprint 에 줄 수 있는 영향)\n"
        "- [중요] 출력은 반드시 `### ` 로 시작한다. 표 밖의 산문은 ## 3 절에만 쓴다.\n"
        "- 출력 예시 (이 골격 그대로):\n"
        + _FORMAT_EXAMPLE + "\n"
        + (f"## 도메인 컨텍스트 (참고)\n{domains}\n\n" if domains else "")
        + (f"## 실측 근거 (참고)\n{grounding}\n\n" if grounding else "")
        + f"## 커밋 {commit[:12]} 의 변경 파일\n" + "\n".join(f"- {f}" for f in files)
        + f"\n\n## DIFF (unified=3)\n```diff\n{diff}\n```\n"
    )


@dataclass
class ReviewResult:
    commit: str = ""
    author: str = ""
    written: str = ""           # 저장된 리포트 경로 (빈 문자열 = 안 씀)
    skipped: str = ""           # 스킵 사유 (trivial / 작성자 제외 / 파일 없음)
    error: str = ""             # [중요] 실패 — 이 커밋의 리뷰는 다시 생기지 않는다 (카나리 대상)
    format_ok: bool = True      # [중요] False = 사람은 읽어도 **소비자는 0건으로 읽는다** (카나리)
    retried: bool = False

    @property
    def ok(self) -> bool:
        return not self.error


def commercial_chat(prompt: str, *, timeout: int = REVIEW_TIMEOUT) -> str:
    """상용 체인 agy → claude (층2와 같은 체인·같은 순서). 둘 다 실패하면 예외.

    [중요] **실패 사유를 예외에 싣는다** (`#285`, 사용자 지적 2026-08-23). 종전 메시지는
    *"둘 다 응답 없음"* 이었는데, 실측된 진짜 원인은 **systemd 유닛에 PATH 가 없어 `which` 가
    실패**한 것이었다(NS 리뷰 26건). 「응답 없음」은 서비스 장애로 읽히므로 **엉뚱한 곳을
    파게 만든다** — 없는 로그보다 틀린 로그가 비싸다. 원전 `call_agy` 는 처음부터 갈라 놨다.
    """
    from .. import layer2_verify as l2
    whys = []
    for name, fn in l2.WHY_BACKENDS:
        out, why = fn(prompt, timeout=timeout)
        if out and out.strip():
            return out
        whys.append(f"{name}: {why or '사유 미기록'}")
    raise ReviewChatError("상용 체인(agy → claude) 실패 — " + " · ".join(whys))


class ReviewChatError(RuntimeError):
    pass


def review_commit(paths, commit: str, files: list, *,
                  exclude_authors: tuple = DEFAULT_EXCLUDE_AUTHORS,
                  chat=None, logf=None) -> ReviewResult:
    """커밋 하나의 변경분을 리뷰해 `reviews/<작성자>/` 에 쓴다.

    `chat(prompt) -> str` 주입은 테스트 자리 — 실전은 상용 체인(agy → claude)이다.
    """
    log = logf or (lambda s, m: None)
    r = ReviewResult(commit=commit)
    src_files = [f for f in files if f.startswith("Source/") or f.endswith((".h", ".cpp", ".cs"))]
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
    if not diff:
        r.error = "diff 를 읽지 못했다 — 리뷰 없이 넘기지 않고 기록한다"
        return r

    prompt = build_prompt(diff=diff, files=src_files, commit=commit,
                          domains=domain_hint(paths, src_files))
    _ask = chat if chat is not None else commercial_chat

    try:
        body = _ask(prompt)
        # [중요] 형식 검증은 상용 체인에도 그대로 둔다 — 첫 라이브 런(2026-08-17)의 교훈은
        #    "형식은 지시가 아니라 검증이 지킨다"였고, 그 결은 모델과 무관하다.
        #    grounding 과 같은 자리: 계약 위반은 조용히 통과시키지 않는다.
        if not format_ok(body or ""):
            r.retried = True
            log("review", f"{commit[:8]} 형식 위반 — 예시를 앞세워 1회 재시도")
            body = _ask("직전 응답이 형식을 어겼다. 아래 골격 **그대로**, `### ` 로 시작해 "
                        "표만으로 다시 써라. 표 밖 산문은 ## 3 에만.\n\n"
                        + _FORMAT_EXAMPLE + "\n\n" + prompt)
    except ReviewChatError as e:
        r.error = f"리뷰 생성 실패: {e}"
        return r
    if not (body or "").strip():
        r.error = "리뷰 응답이 비었다"
        return r
    r.format_ok = format_ok(body)

    from datetime import datetime
    ts = datetime.now()
    safe = _SAFE_AUTHOR.sub("_", r.author or "unknown").strip("_") or "unknown"
    out_dir = Path(paths.root) / REVIEWS_DIRNAME / safe
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{ts.strftime('%Y-%m-%d_%H%M')}_{commit[:8]}.md"
    head = (f"# 자동 코드 리뷰 — {commit[:12]}\n\n"
            f"- 커밋: `{commit}`\n- 작성자: {r.author}\n"
            f"- 파일: {len(src_files)}개\n- 생성: {ts.strftime('%Y-%m-%d %H:%M')}\n\n")
    path = out_dir / fname
    path.write_text(head + body.strip() + "\n", encoding="utf-8")
    r.written = str(path)
    if not r.format_ok:
        # 사람은 읽을 수 있으니 버리지 않는다 — 다만 소비자에겐 0건이므로 시끄럽게 남긴다
        log("review", f"[중요] {path.name} 형식 위반 — 소비자 파서 기준 이슈 0건")
    else:
        log("review", f"{r.author} {commit[:8]} → {path.name} (행 {parseable_rows(body)})")
    return r
