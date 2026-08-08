"""컨텍스트 MD 정제·검증·스탬핑 (소 1.2.2 · 1.2.3).

원본: `AgentTest/watcher/context_md.py`. **순수 함수만** 둔다 — 파일을 읽거나 LLM 을 부르지
않으므로 테스트가 값으로 끝난다.

🔴 **이 모듈이 존재하는 이유는 실측된 사고다.** 원본 σ.7 기록:

> 사무실 실측에서 컨텍스트 MD **1,097개 중 477개(43%)** 가 LLM 응답을 ` ```markdown … ``` `
> 펜스째 저장한 손상 파일로 발견. `_inject_content_hash` 가 `^---` frontmatter 매치 실패 시
> 그대로 return 하는 약점이 원인.

그래서 방어가 **두 겹**이다.

- `strip_wrapper` — 펜스와 자연어 도입부를 벗긴다 (σ.7)
- `check` — **저장 전 게이트.** 벗긴 뒤에도 형식이 아니면 **저장을 거부**하고 기존 파일을
  남긴다 (σ.7-B). 손상 응답이 정상 MD 를 덮어쓰는 것이 진짜 사고였다 — 거부하면 다음
  사이클에 자연 재시도된다

🔴 **`source_commit` 은 장식이 아니다.** 중 1.3 의 stale 판정이 *"온톨로지에 저장된
source_commit ≠ 이 문서의 source_commit"* 으로 이뤄진다(Phase η.8 이 dirty 플래그를 없애고
이 워터마크로 대체했다). 이 스탬프가 빠지면 **온톨로지는 자기가 낡은 줄 모른다.**
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# 개발자가 직접 쓰는 섹션. 재생성이 **덮어써서는 안 되고**, 해시에도 넣지 않는다 —
# 코멘트를 고쳤다고 재색인이 돌면 40초를 태워 같은 것을 넣는다.
COMMENTS_HEADING = "## 코멘트"
_COMMENTS_RE = re.compile(r"(## 코멘트\s*\n.*)", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", re.DOTALL | re.IGNORECASE)

# 게이트 임계값. 원본과 같은 50자 — frontmatter 껍데기조차 안 되는 길이다.
MIN_CHARS = 50


def extract_comments(md: str) -> str:
    """`## 코멘트` 섹션. 없으면 빈 문자열."""
    m = _COMMENTS_RE.search(md or "")
    return m.group(1).rstrip() if m else ""


def strip_comments(md: str) -> str:
    return _COMMENTS_RE.sub("", md or "").rstrip()


def strip_wrapper(md: str) -> str:
    """σ.7 — 펜스와 자연어 도입부를 벗긴다.

    ⑴ 전체를 감싼 ```` ```markdown … ``` ```` 제거
    ⑵ 그래도 `---` 로 시작하지 않으면 **첫 `---` 줄부터** 잘라낸다 ("아래에 MD 를
      작성했습니다" 같은 도입부가 붙는 경우)
    ⑶ frontmatter 를 닫는 `---` 가 빠졌으면 넣는다 (`repair_frontmatter`)
    """
    s = (md or "").strip()
    fence = _FENCE_RE.match(s)
    if fence:
        s = fence.group(1).strip()
    if not s.startswith("---"):
        m = re.search(r"^---\s*$", s, re.MULTILINE)
        if m:
            s = s[m.start():]
    return repair_frontmatter(s)


def repair_frontmatter(md: str) -> str:
    """frontmatter 를 닫는 두 번째 `---` 가 빠진 경우만 **결정적으로** 복구한다.

    🔴 실측(2026-08-08): `qwen2.5-coder:14b` 가 여는 `---` 와 필드는 쓰고 닫는 `---` 없이
    바로 `## 요약` 으로 넘어간다. 사실 오류가 아니라 형식 슬립인데, 닫히지 않으면 스탬프
    (`content_hash`·`source_commit`)가 안 붙고 게이트가 문서를 통째로 버린다.

    **좁게 고친다** — ⑴ `---` 로 시작하고 ⑵ 닫는 `---` 가 **없고** ⑶ 뒤에 `## ` 제목이
    있을 때만, 그 제목 **직전에** 닫는 줄을 넣는다. 이 셋이 다 맞으면 경계가 모호하지 않다.
    조건을 넓히면 진짜 손상을 정상으로 위장하게 되므로 넓히지 않는다.
    """
    s = (md or "").strip()
    if not s.startswith("---"):
        return s
    if _FRONTMATTER_RE.match(s):
        return s                      # 이미 닫혀 있다
    m = re.search(r"^##\s", s, re.MULTILINE)
    if not m:
        return s                      # 경계를 알 수 없다 — 손대지 않는다
    head, rest = s[:m.start()].rstrip(), s[m.start():]
    if head.count("\n---") > 0:       # 닫는 표시가 있는데 정규식이 안 맞았다 = 이상하다
        return s
    return f"{head}\n---\n\n{rest}"


@dataclass(frozen=True)
class Check:
    """게이트 결과. **`ok` 가 아니면 저장하지 않는다.**"""

    ok: bool
    reason: str = ""
    preview: str = ""

    @property
    def summary(self) -> str:
        return "통과" if self.ok else f"거부 — {self.reason}"


def check(md: str) -> Check:
    """σ.7-B 저장 전 게이트.

    거부는 **실패가 아니라 보류**다 — 기존 파일이 남고 다음 사이클에 다시 시도된다.
    그래서 사유를 반드시 남긴다. 조용히 건너뛰면 "왜 문서가 안 생기지" 가 된다.
    """
    s = (md or "").strip()
    if len(s) < MIN_CHARS:
        return Check(False, f"응답이 너무 짧다 ({len(s)}자 < {MIN_CHARS})", s[:80])
    if not s.startswith("---"):
        return Check(False, "frontmatter 가 없다 (펜스 잔존·파싱 실패)",
                     s[:80].replace("\n", " "))
    if not _FRONTMATTER_RE.match(s):
        return Check(False, "frontmatter 가 닫히지 않았다", s[:80].replace("\n", " "))
    return Check(True)


def _set_field(md: str, key: str, value: str) -> str:
    """frontmatter 의 한 줄을 넣거나 갱신한다. frontmatter 가 없으면 **그대로 둔다** —
    여기까지 온 문서는 `check` 를 통과했으므로 이 경로는 방어용이다."""
    m = _FRONTMATTER_RE.match(md)
    if not m:
        return md
    head, body, tail = m.group(1), m.group(2), m.group(3)
    rest = md[m.end():]
    line_re = re.compile(rf"^{re.escape(key)}:\s*\S*\s*$", re.MULTILINE)
    if line_re.search(body):
        body = line_re.sub(f"{key}: {value}", body)
    else:
        body = body.rstrip() + f"\n{key}: {value}"
    return head + body + tail + rest


def content_hash(md: str) -> str:
    """본문(frontmatter·코멘트 제외)의 MD5 16자.

    코멘트를 제외하는 이유: 개발자가 코멘트를 고쳤다고 재색인이 돌면 안 된다.
    """
    m = _FRONTMATTER_RE.match(md)
    body = md[m.end():] if m else md
    return hashlib.md5(strip_comments(body).encode("utf-8")).hexdigest()[:16]


def stamp(md: str, *, commit: str = "") -> str:
    """`content_hash` + `source_commit` 을 frontmatter 에 새긴다.

    🔴 `source_commit` 이 **중 1.3 stale 판정의 한쪽**이다. `commit` 이 비면 그 줄은
    건드리지 않는다 — 수동 재생성이 실제 리비전 정보를 **지우면** 온톨로지가 영영
    stale 을 감지하지 못한다.
    """
    out = _set_field(md, "content_hash", content_hash(md))
    if commit:
        out = _set_field(out, "source_commit", commit)
    return out


def read_field(md: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(\S+)\s*$", md or "", re.MULTILINE)
    return m.group(1) if m else ""


def read_source_commit(md: str) -> str:
    """이 문서가 반영한 리비전. 없으면 `-1`.

    원본과 같은 규약이다 — 값을 못 가져오면 `-1`. git 을 직접 보지 않고 **문서를 carrier 로
    쓰는** 이유가 여기 있다: 레거시 문서가 `-1` 을 유지해 첫 배포에 전체 재합성이 폭주하는
    것을 막는다. 실제 커밋이 올라와 문서가 재생성될 때 비로소 실 리비전을 얻는다.
    """
    return read_field(md, "source_commit") or "-1"


def merge_comments(new_md: str, existing_md: str) -> str:
    """개발자 코멘트를 재생성된 문서로 이월한다.

    🔴 LLM 에게 "코멘트를 만들지 말라" 고 지시하지만 **지시를 믿지 않는다** — 새 문서에
    코멘트 섹션이 있으면 지우고, 기존 것을 붙인다.
    """
    comments = extract_comments(existing_md or "")
    if not comments:
        return new_md
    return strip_comments(new_md) + "\n\n" + comments + "\n"


def finalize(raw: str, *, existing: str = "", commit: str = "") -> tuple[str, Check]:
    """LLM 원문 → 저장할 문서. **한 곳에서 순서를 고정한다.**

        벗기기(σ.7) → 게이트(σ.7-B) → 코멘트 이월 → 스탬프

    게이트가 스탬프보다 **앞**인 것이 요점이다. 원본의 사고가 정확히 "스탬프 함수가
    frontmatter 매치에 실패하고도 그대로 통과시킨" 것이었다.
    """
    stripped = strip_wrapper(raw)
    verdict = check(stripped)
    if not verdict.ok:
        return "", verdict
    return stamp(merge_comments(stripped, existing), commit=commit), verdict
