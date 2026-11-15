"""이슈 본문의 **스펙 영역** — `#960` T3.

사용자 결정(2026-11-15): 「본문 자체를 고치지 말고 플랜처럼 영역을 잡아야지」 · 「파급 측정 끝나고 마지막에
스펙 영역 써」. 등록자가 쓴 본문은 글자 그대로 두고, 착수 전 인터뷰로 확정한 스펙(#911 여섯 항목)만
표지 사이에 둔다.

    ## 확정 스펙 (착수 전 인터뷰)

    <!-- ax:spec:begin v=1 -->
    ### 문제·맥락
    …
    <!-- ax:spec:end -->

- 영역이 있으면 = 인터뷰를 다 거쳤다는 뜻이다. `plan_start` 는 이 영역의 유무로 인터뷰/플랜을 가른다(T4).
- 이 모듈은 형식만 안다(파싱·누락 항목·끼우기). **언제 쓸 수 있는지**(파급 측정 뒤)는 `master/interview.py`
  의 `write_spec` 이 정한다.
- 플랜 영역이 이미 있는 본문에는 그 앞에 끼운다 — 스펙이 플랜보다 먼저 읽히게.
"""
from __future__ import annotations

import re

from master import plan_block as PB

FORMAT_VERSION = 1
BEGIN_RE = re.compile(r"<!-- ax:spec:begin v=(\d+) -->")
END_TAG = "<!-- ax:spec:end -->"
HEADING = "## 확정 스펙 (착수 전 인터뷰)"


class SpecError(ValueError):
    """스펙 영역 형식 오류."""


def _region(body: str) -> tuple[int, int, int] | None:
    """(시작 태그 시작, 영역 안 시작, 영역 안 끝). 없으면 None."""
    begins = list(BEGIN_RE.finditer(body))
    ends = [m.start() for m in re.finditer(re.escape(END_TAG), body)]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise SpecError(f"스펙 태그가 한 쌍이 아니다 — 시작 {len(begins)}개 · 끝 {len(ends)}개")
    if ends[0] < begins[0].end():
        raise SpecError("스펙 끝 태그가 시작 태그보다 앞에 있다")
    if int(begins[0].group(1)) != FORMAT_VERSION:
        raise SpecError(f"모르는 스펙 형식 v={begins[0].group(1)}")
    return begins[0].start(), begins[0].end(), ends[0]


def parse(body: str) -> str | None:
    """영역 안 글. 영역이 없으면 None, 깨졌으면 `SpecError`."""
    r = _region(body or "")
    return None if r is None else body[r[1]:r[2]].strip()


def exists(body: str) -> bool:
    return parse(body) is not None


def missing(content: str) -> list[str]:
    """여섯 항목(docs/issue-spec.md §2) 중 제목 줄에 없는 것의 키."""
    from master.plan_start import SPEC_SECTIONS
    heads = [ln.lstrip().lstrip("#").strip().lower()
             for ln in (content or "").splitlines() if ln.lstrip().startswith("#")]
    return [key for key, words in SPEC_SECTIONS if not any(w in h for h in heads for w in words)]


def put(body: str, content: str) -> str:
    """영역을 만들거나 안을 바꾼다. 영역 밖 글자는 그대로 둔다."""
    body = body or ""
    content = (content or "").strip()
    if BEGIN_RE.search(content) or END_TAG in content or PB.BEGIN_RE.search(content) or PB.END_TAG in content:
        raise SpecError("스펙 글에 스펙·플랜 표지를 넣을 수 없다")
    nl = "\r\n" if "\r\n" in body else "\n"
    inner = ("\n" + content + "\n").replace("\n", nl)
    r = _region(body)
    if r is not None:
        return body[:r[1]] + inner + body[r[2]:]
    block = (f"{HEADING}\n\n<!-- ax:spec:begin v={FORMAT_VERSION} -->").replace("\n", nl) + inner + END_TAG
    plan = PB._region(body)
    if plan is None:
        base = body.rstrip("\r\n")
        return (base + nl + nl if base else "") + block + nl
    # 플랜 제목 줄(태그 바로 앞의 `#` 줄)이 있으면 그 앞에 끼운다
    cut = plan[0]
    head = body.rfind(nl + "#", 0, cut)
    if head != -1 and body[head + len(nl):cut].strip().startswith("#") and \
            "\n" not in body[head + len(nl):cut].strip():
        cut = head + len(nl)
    return body[:cut] + block + nl + nl + body[cut:]
