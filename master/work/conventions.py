"""프로젝트 코드 규약 — 🔴 **프로젝트의 `CLAUDE.md` 가 SSOT 다** (소 3.5.7).

## 왜 여기서 읽나 — 하드코딩하지 않는 이유

리포트 14 §14.5 에서 드러난 것: 프로젝트 미러의 `repo/CLAUDE.md` 가 **우리 저장소에서 인용
0회**였는데 이식 설계의 절반을 갖고 있었다. 그 안의 「Code conventions」 는 우리 파이프라인이
코드를 **생성**할 때 지켜야 하는 것이다 — 그런데 매니페스트가 그것을 **전혀 나르지 않았다**
(도메인 규범(온톨로지)만 실었다).

🔴 **베껴 두면 어긋난다.** 프로젝트가 규약을 바꾸면 우리 복사본은 조용히 낡는다. 그래서 파일을
**읽어서** 싣는다 — 미러가 `git pull` 로 갱신되면 다음 매니페스트가 자동으로 새 규약을 나른다.

⚠️ **bounded·curated** (κ.3): 파일 전체(227줄)를 싣지 않는다. 이름을 지정한 절만 뽑는다 —
매니페스트가 부풀면 그것이 곧 토큰 비용이고, 원전이 *"raw 덤프 X"* 라고 못박은 자리다.

## 🔴 그리고 UE 특유의 금지 3종은 **우리가 싣는다**

이것은 프로젝트 문서에 없고 원전의 **리뷰 프롬프트**에 있던 것이다(`watcher-internals.md`).
이유가 UE 특유라 프로젝트가 바뀌어도 유효하다:

    클래스/컴포넌트/함수/UPROPERTY 멤버 **리네이밍 금지**   Blueprint 에셋이 C++ 상속 +
    클래스 **상속 구조 변경 금지**                          UPROPERTY 직렬화 → 이름이 바뀌면 **에셋이 깨진다**
    **모듈 간 코드 이동 금지**                              빌드 의존성 + 에셋 참조 파괴

*"LLM 은 코드만 분석 가능 — UE5 에셋 의존 관계(Blueprint 상속·데이터테이블 참조)는 **파악
불가**"* 이므로 이것은 판단에 맡길 수 없고 **금지로 실어야** 한다.

⚠️ `frozen_decls`(계약 동결)가 리네이밍의 **일부**를 막지만 **모듈 간 이동은 못 막는다** —
동결은 선언이 바뀌었는지만 보고, 파일이 어디로 갔는지는 보지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

# 프로젝트 문서에서 실어 올 절 (이름 그대로). ⚠️ 없으면 조용히 넘기지 않고 보고한다.
WANTED_SECTIONS = ("Code conventions",)

# 🔴 UE 특유라 프로젝트 문서와 무관하게 항상 싣는다 (위 절 참조).
UE_PROHIBITIONS = (
    "클래스·컴포넌트·함수·`UPROPERTY` 멤버를 **리네이밍하지 않는다** — Blueprint 에셋이 C++ 클래스를"
    " 상속하고 `UPROPERTY` 를 직렬화하므로 이름이 바뀌면 **에셋이 깨진다.**",
    "클래스 **상속 구조를 바꾸지 않는다** — 같은 이유.",
    "**모듈 간으로 코드를 옮기지 않는다** — 빌드 의존성과 에셋 참조가 깨진다.",
    "🔴 위 셋은 판단 사항이 아니다. LLM 은 코드만 볼 수 있고 **UE5 에셋 의존 관계(Blueprint 상속·"
    "데이터테이블 참조)는 파악할 수 없다.** 필요해 보이면 그 사실을 보고하고 멈춘다.",
)


def extract_section(text: str, heading: str) -> str:
    """`## <heading>` 절의 본문. 다음 `## ` 또는 끝까지. 없으면 빈 문자열.

    ⚠️ 정규식으로 절을 자를 때 **다음 헤딩까지**로 끊는다 — 파일 끝까지 삼키면 매니페스트가
    부푼다(원전이 *"bounded·curated"* 로 못박은 자리).
    """
    if not text or not heading:
        return ""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return (rest[: nxt.start()] if nxt else rest).strip()


def project_doc(repo: Path) -> tuple:
    """프로젝트 미러의 `CLAUDE.md` 본문. `(text, note)` — 못 읽으면 `note` 에 사유.

    🔴 `CLAUDE.md` 는 프로젝트에서 **gitignore 대상**이다(AgentWatch 가 관리하는 로컬 문서).
    즉 미러에 **있을 수도 없을 수도** 있다 — 없으면 그 사실을 매니페스트에 적는다. 조용히
    비우면 *"규약이 없는 프로젝트"* 와 구별되지 않는다.
    """
    p = Path(repo) / "CLAUDE.md"
    if not p.is_file():
        return "", f"{p} 가 없다 (프로젝트에서 gitignore 대상이라 미러에 없을 수 있다)"
    try:
        return p.read_text(encoding="utf-8", errors="replace"), ""
    except OSError as e:
        return "", f"{p} 를 읽지 못했다: {e}"


def bundle(repo: Path) -> tuple:
    """매니페스트에 실을 「프로젝트 코드 규약」 절 본문. `(body, note)`.

    항상 UE 금지 3종을 싣고, 프로젝트 문서에서 지정 절을 뽑아 덧붙인다.
    """
    lines = ["**UE 특유 — 지킬 것 (판단 사항 아님)**", ""]
    lines += [f"- {x}" for x in UE_PROHIBITIONS]

    text, note = project_doc(repo)
    found = []
    for h in WANTED_SECTIONS:
        body = extract_section(text, h)
        if body:
            found.append(h)
            lines += ["", f"**프로젝트 규약 — `CLAUDE.md` § {h}** (프로젝트가 SSOT)", "", body]
    if not found and not note:
        note = f"`CLAUDE.md` 에서 절을 찾지 못했다: {', '.join(WANTED_SECTIONS)}"
    return "\n".join(lines) + "\n", note
