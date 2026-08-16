"""시소러스 질의 확장 — 한글 말을 실제 식별자로 잇는다 (소 2.2.1).

## 무엇을 푸는가

사용자가 「몬스터 스폰」이라고 쓰면 검색은 **그 한글 토큰**을 찾는다. 문서에 그 단어가 없으면
0건이다. 실제로 찾아야 할 것은 `AMonster`·`UMissionTask_Spawn` 인데 **문자가 하나도 겹치지
않아** trigram 으로도, 다국어 임베딩으로도 잘 이어지지 않는다. 별칭표가 그 다리고,
이 모듈이 **질의 쪽에서** 그 다리를 건넌다.

실측(사본, 리포트 11 §중 1.4): 별칭 6개만 등록해도 「미션 태스크 실행」의 1위가 뒤집히고
「몬스터」가 0건 → 검색됨이 됐다. 그건 **색인 쪽**(tags 채널) 효과였고, 여기는 **질의 쪽**이다.

## [중요] 부분 문자열로 찾는다 — 한국어에 조사가 붙기 때문이다

    "몬스터를 스폰한다"  →  토큰은 「몬스터를」 이지 「몬스터」 가 아니다

형태소 분석기를 두지 않는다(의존이 커지고, 우리 어휘는 사람이 등록한 수십 개다). 대신
**부분 문자열**로 찾는다. 그 대가가 오탐이므로 두 가지로 막는다:

1. [중요] **짧은 별칭은 확장하지 않는다** (`MIN_TERM`). 「적」 같은 한 글자는 어디에나 들어간다
2. [중요] **개수 상한** (`MAX_EXPAND`). 질의 하나가 식별자 수십 개로 불어나면 BM25 가 원래
   의도를 잃는다 — 확장은 거들 뿐이지 질의를 대체하지 않는다

## [중요] 조용히 바꾸지 않는다

무엇을 왜 붙였는지 반환값에 담는다. 검색 결과가 이상할 때 **질의가 바뀐 줄 모르면** 사람은
색인이나 가중치를 의심한다 — 실제 원인은 여기인데.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_TERM = 2            # [중요] 한 글자 별칭은 어디에나 걸린다
MAX_EXPAND = 6          # [중요] 확장은 거들 뿐 — 질의를 대체하지 않는다


@dataclass
class Expansion:
    query: str                                   # 확장된 질의 (원본 + 식별자)
    original: str = ""
    added: list = field(default_factory=list)    # [(별칭, 클래스)]
    skipped_short: list = field(default_factory=list)
    capped: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added)

    @property
    def note(self) -> str:
        """[중요] 무엇을 왜 붙였는지 — 조용히 바꾸면 사람이 엉뚱한 곳을 의심한다."""
        if not self.added:
            return ""
        s = "시소러스 확장: " + ", ".join(f"{t}→{c}" for t, c in self.added)
        if self.capped:
            s += f" (상한으로 {self.capped}개 생략)"
        return s


def expand(query: str, aliases: dict, *, min_term: int = MIN_TERM,
           max_expand: int = MAX_EXPAND) -> Expansion:
    """질의에 별칭이 들어 있으면 **클래스명을 덧붙인다.**

    `aliases` 는 `{소문자 별칭: Alias}` — `thesaurus.load()` 가 주는 형태다.
    [중요] **원본을 지우지 않는다.** 덧붙이기만 한다 — 확장이 틀렸을 때 원래 질의가 남아 있어야
    결과가 0건으로 떨어지지 않는다.
    """
    q = (query or "").strip()
    e = Expansion(query=q, original=q)
    if not q or not aliases:
        return e

    low = q.casefold()
    hits: list = []
    for key, alias in aliases.items():
        term = getattr(alias, "term", None) or str(key)
        cls = getattr(alias, "class_name", "") or ""
        if not cls:
            continue
        if len(term) < min_term:
            e.skipped_short.append(term)
            continue
        if term.casefold() in low:
            hits.append((term, cls))

    # 긴 별칭이 더 구체적이다 — 「미션 태스크」가 「태스크」보다 먼저다
    hits.sort(key=lambda t: (-len(t[0]), t[0]))
    seen: set = set()
    for term, cls in hits:
        if cls in seen or cls.casefold() in low:
            continue                        # 이미 질의에 있는 식별자는 안 붙인다
        if len(e.added) >= max_expand:
            e.capped += 1
            continue
        seen.add(cls)
        e.added.append((term, cls))

    if e.added:
        e.query = q + " " + " ".join(c for _, c in e.added)
    return e


def expand_for(paths, query: str, **kw) -> Expansion:
    """프로젝트의 별칭표를 읽어 확장한다. **별칭이 없으면 원본 그대로.**"""
    try:
        from . import thesaurus
        return expand(query, thesaurus.load(paths), **kw)
    except Exception:                                     # noqa: BLE001 — 검색을 막지 않는다
        return Expansion(query=(query or "").strip(), original=(query or "").strip())
