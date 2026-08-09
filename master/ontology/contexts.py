"""도메인 클래스 컨텍스트 수집 — 재합성 프롬프트의 근거 (LLM 0).

원본: `watcher/ontology_invariants.py` 의 `collect_domain_class_contexts` ·
`extract_cpp_excerpt`.

## 🔴 원본 상수를 그대로 옮기면 노드가 죽는다

원본은 도메인당 클래스 10개 × (`.h` 3,000자 + `.cpp` 2,500자) = **최대 55KB** 를 한
프롬프트에 싣는다. 원본의 소비자는 **상용 API** 였다. 우리 노드는 BC-250(통합 메모리
15.6GiB, 35B 상주 후 여유 ~2GB)이고, **프롬프트 크기 때문에 이미 한 번 죽었다**
(리포트 10 §8 — `num_ctx` 미지정 → 256K 전제 KV 할당 → zram 스래싱 → 커널 정지).

실측 2026-08-09 — 도메인별 소스 총량:

    ProjectAlpha_UiViewManagement   멤버 67 · .h 281KB · .cpp 879KB
    MissionRuntime                  멤버 11 · .h  18KB · .cpp  39KB
    AlphaCoreGameFramework          멤버  1 · .h   1KB · .cpp   4KB

**한 도메인이 1MB를 넘는다.** 그래서 예산을 **글자 수로 못박고**, 넘으면 자르되
**자른 사실을 결과에 적는다**(`Budget.truncated`). 조용히 앞부분만 보내면 모델은
그 사실을 말하지 않는다 — 뒤를 못 본 채 "다 봤다" 는 톤으로 답한다.

🔴 **`num_ctx` 와 이 예산은 함께 움직인다.** `context_synth/synth.py` 가 같은 규칙을
주석으로 못박아 뒀다: *발췌만 늘리면 컨텍스트 창을 넘어 뒤가 잘린다.*

## 무엇을 싣나 — 지도가 아니라 소스다

`docs/3-open-items.md` 가 지적한 구멍이 여기에도 걸린다: **추론 노드는 파일을 못 읽는다.**
그러니 "어느 클래스가 있다" 만 주면 액션·invariant 를 지어낼 수밖에 없다. 그래서
**선언부(.h)와 신호 인근(.cpp)** 을 직접 싣는다 — 원본이 같은 이유로 같은 선택을 했다.

`.cpp` 는 전체가 아니라 **invariant 신호 인근만** 발췌한다(원본 휴리스틱):
함수 정의 · `check()`/`ensure()`/`verify()` · lock/RAII · 스마트 포인터 선언 ·
`@invariant`/`@precondition` 주석.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import source_text
from ..context_search.paths import ProjectPaths
from ..graph import class_graph as cg, dependency as dep
from . import collect

# 🔴 예산 — **실측으로 정한다. 원본 값이 아니다.**
# 원본: 클래스 10 × (.h 3000 + .cpp 2500). 상용 API 전제라 우리보다 한 자리 크다.
MAX_CLASSES = 6               # 조각당 프롬프트에 싣는 클래스 수
HEADER_CHARS = 1200           # 클래스당 .h 발췌
BODY_CHARS = 900              # 클래스당 .cpp 발췌

# 🔴 **실측으로 정한 값이다** (2026-08-09, `/api/generate` 의 `prompt_eval_count`):
#
#   프롬프트 17,315자 → 35B 6,070 tok (2.85자/tok) · 14b 6,200 tok (2.79자/tok)
#
# `num_ctx` 는 양쪽 노드 실측 상한이 **8192** 다. 출력에 JSON 5~15건(description·flow 포함)
# 이 들어가려면 **2,500~3,000 토큰**을 남겨야 하므로 프롬프트는 **5,000 토큰 ≈ 14,000자**가
# 상한이다. 규칙 블록(~4,500자) + 도메인 서술(~1,800자) + 클래스 목록이 먼저 먹으므로
# **발췌에 쓸 수 있는 것은 ~7,000자**다.
#
# 🔴 넘치면 **조용히 뒤가 잘린다** — 모델은 그 사실을 말하지 않고 앞부분만 보고 답한다.
# 올리려면 `num_ctx` 와 **양쪽 노드의 여유를 함께** 재라 (`synth.NUM_CTX` 주석 참조).
TOTAL_CHARS = 7000
ANCESTORS_SHOWN = 4
NEIGHBOURS_SHOWN = 6

_FUNC_DEF = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_:<>&*\s]*?)\s+"
    r"[A-Za-z_][A-Za-z0-9_]*::[A-Za-z_][A-Za-z0-9_]*\s*\(", re.M)

_SIGNAL = re.compile(
    r"^\s*(?:"
    r"check(?:Slow|f|NoEntry)?\s*\("
    r"|ensure(?:Always|MsgF)?\s*\("
    r"|verify(?:f|Slow)?\s*\("
    r"|FScopeLock\b|FCriticalSection\b"
    r"|std::(?:lock_guard|unique_lock|scoped_lock)\b"
    r"|TSharedPtr<|TWeakPtr<|TUniquePtr<|TSharedRef<"
    r"|//\s*@(?:invariant|precondition|postcondition|note)\b"
    r")", re.I)


@dataclass
class ClassContext:
    """프롬프트에 실릴 클래스 하나."""
    name: str
    file: str = ""
    ancestors: list = field(default_factory=list)
    neighbours: list = field(default_factory=list)     # `#include` 로 얽힌 도메인 밖 클래스
    header: str = ""
    body: str = ""

    @property
    def chars(self) -> int:
        return len(self.header) + len(self.body)

    def block(self) -> str:
        out = [f"클래스: {self.name}", f"  파일: {self.file or '-'}"]
        if self.ancestors:
            out.append(f"  조상: {', '.join(self.ancestors[:ANCESTORS_SHOWN])}")
        if self.neighbours:
            out.append(f"  도메인 밖 include: {', '.join(self.neighbours[:NEIGHBOURS_SHOWN])}")
        if self.header:
            out.append("  [.h 선언부]")
            out += [f"    {ln}" for ln in self.header.splitlines()]
        if self.body:
            out.append("  [.cpp 신호 인근]")
            out += [f"    {ln}" for ln in self.body.splitlines()]
        return "\n".join(out)


@dataclass
class DomainContexts:
    domain: str
    items: list = field(default_factory=list)
    members_total: int = 0
    truncated: list = field(default_factory=list)   # 🔴 예산 때문에 뺀 클래스 이름
    chars: int = 0
    part: tuple = (1, 1)                            # (조각 번호, 전체 조각 수)

    @property
    def names(self) -> set:
        """`allowed_classes` — 프롬프트가 다루도록 허용된 클래스. 필터의 기준이다."""
        return {c.name for c in self.items}

    @property
    def empty(self) -> bool:
        return not self.items

    @property
    def summary(self) -> str:
        i, n = self.part
        head = f"{self.domain}" + (f" [{i}/{n}]" if n > 1 else "")
        s = f"{head}: 클래스 {len(self.items)}/{self.members_total} · {self.chars}자"
        if self.truncated:
            s += f" · 🔴 예산으로 제외 {len(self.truncated)}"
        return s

    @property
    def note(self) -> str:
        """🔴 프롬프트 본문에 넣을 결손 고지. **안 보이는 것을 숨기지 않는다.**

        조각으로 나뉜 경우가 특히 중요하다 — 모델은 자기가 받은 것이 전부라고 가정하고,
        빈칸을 지어내 채운다. **"이건 일부다" 를 말해 주면 그 압력이 줄어든다.**
        """
        i, n = self.part
        lines: list = []
        if n > 1:
            lines.append(
                f"⚠️ 이것은 `{self.domain}` 도메인의 **{n}조각 중 {i}번째**다 "
                f"(도메인 전체 클래스 {self.members_total}개). 여기 실린 클래스만 다루고, "
                f"다른 조각에 있을 클래스는 추측하지 말 것 — 나머지는 따로 처리된다.")
        if self.truncated:
            shown = ", ".join(self.truncated[:10])
            more = "" if len(self.truncated) <= 10 else f" 외 {len(self.truncated) - 10}개"
            lines.append(f"⚠️ 예산으로 실리지 않은 클래스: {shown}{more}. "
                         f"보이지 않는 클래스에 대해서는 추측하지 말 것.")
        return "\n".join(lines)


def excerpt_header(paths: ProjectPaths, file: str, limit: int = HEADER_CHARS) -> str:
    """`.h` 선언부 발췌. **CP949 를 거친다** — 한글 주석이 최고 신호원이다."""
    if not file:
        return ""
    d = source_text.read(paths.repo / file)
    if d is None:
        return ""
    return d.text[:limit].rstrip()


def excerpt_body(paths: ProjectPaths, file: str, limit: int = BODY_CHARS) -> str:
    """같은 stem 의 `.cpp` 중 **신호 인근만**. 없으면 빈 문자열."""
    if not file or not file.endswith(".h"):
        return ""
    d = source_text.read(paths.repo / (file[:-2] + ".cpp"))
    if d is None:
        return ""
    lines = d.text.splitlines()
    hits: list = []
    for i, ln in enumerate(lines):
        if _FUNC_DEF.match(ln) or _SIGNAL.match(ln):
            hits.append((max(0, i - 1), min(len(lines), i + 8)))
    if not hits:
        return "\n".join(lines[:40])[:limit].rstrip()
    merged: list = []
    for s, e in sorted(hits):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out: list = []
    prev = -1
    for s, e in merged:
        if prev >= 0 and s > prev:
            out.append(f"... ({s - prev}줄 생략) ...")
        out += [f"{i + 1:>5}: {lines[i]}" for i in range(s, e)]
        prev = e
        if sum(len(x) for x in out) > limit:
            break
    body = "\n".join(out)
    return body[:limit].rstrip() + ("\n..." if len(body) > limit else "")


def _neighbours(paths: ProjectPaths, file: str, inside: set) -> list:
    """`#include` 로 얽힌 **도메인 밖** 클래스. 협력 신호이자 cross-domain 경고다.

    ⚠️ 역방향은 basename 근사다(중 1.1 의 알려진 한계) — 그래서 **참고로만** 싣고
    액션 본문 추출의 근거로는 쓰지 않는다.
    """
    if not file or not dep.exists(paths):
        return []
    files = list(dep.dependencies(paths, file, depth=1))[:6]
    if not files:
        return []
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return []
    conn = gdb.connect(paths)
    try:
        marks = ",".join("?" * len(files))
        rows = conn.execute(f"SELECT name FROM classes WHERE file IN ({marks})", tuple(files))
        return sorted({r["name"] for r in rows} - inside)[:NEIGHBOURS_SHOWN]
    finally:
        conn.close()


def _build_one(paths: ProjectPaths, name: str, members: dict, inside: set,
               header_chars: int, body_chars: int) -> ClassContext:
    file = members.get(name) or ""
    return ClassContext(
        name=name,
        file=file,
        ancestors=cg.find_ancestors(paths, name, max_depth=3),
        neighbours=_neighbours(paths, file, inside),
        header=excerpt_header(paths, file, header_chars),
        body=excerpt_body(paths, file, body_chars),
    )


def collect_domain(paths: ProjectPaths, domain: str, *, members: dict | None = None,
                   max_classes: int = MAX_CLASSES, header_chars: int = HEADER_CHARS,
                   body_chars: int = BODY_CHARS,
                   total_chars: int = TOTAL_CHARS) -> DomainContexts:
    """도메인 하나를 **한 프롬프트 분량으로** 자른 컨텍스트.

    🔴 이건 단일 요청용이다. 도메인 전체를 다루려면 `chunk_domain` 을 쓴다 — 그쪽이
    기본 경로이고, 이 함수는 첫 조각만 필요한 곳(미리보기·비교 측정)에서 쓴다.

    멤버 순서는 이름순이다 — `confidence` 로 정렬하던 원본과 다르다. 우리
    `class_ontology` 는 아직 비어 있어(중 1.3 이 채운다) 정렬 근거가 없고, **없는 근거로
    정렬하는 척하지 않는다.** 채워지면 그때 정렬을 바꾼다.
    """
    members = collect.members_of(paths, domain) if members is None else members
    ctx = DomainContexts(domain=domain, members_total=len(members))
    inside = set(members)
    for name in sorted(members):
        if len(ctx.items) >= max_classes or ctx.chars >= total_chars:
            ctx.truncated.append(name)
            continue
        item = _build_one(paths, name, members, inside, header_chars, body_chars)
        if ctx.chars + item.chars > total_chars and ctx.items:
            ctx.truncated.append(name)
            continue
        ctx.items.append(item)
        ctx.chars += item.chars
    return ctx


def cohesion_order(paths: ProjectPaths, members: dict) -> list:
    """멤버를 **응집 순서**로 늘어놓는다 — `#include` 로 얽힌 것끼리 이웃하게.

    🔴 **쪼갤 때 이 순서가 품질을 좌우한다.** 액션은 클래스 *사이*의 관계이므로, 이름순으로
    자르면 한 액션의 참여자가 서로 다른 조각으로 흩어져 **어느 조각에서도 안 보인다.**
    같은 기능을 함께 담아야 그 액션이 한 요청 안에서 보인다.

    그래프가 없으면 이름순으로 떨어진다 — 근사가 실패해도 **작업이 멈추지는 않는다**
    (마일스톤의 판단 기준: *"맞는 자리를 찾을 수 있나"*).
    """
    names = sorted(members)
    if not dep.exists(paths) or len(names) <= 2:
        return names
    file_of = {n: (members.get(n) or "") for n in names}
    by_file: dict = {}
    for n in names:
        if file_of[n]:
            by_file.setdefault(file_of[n], []).append(n)

    adj: dict = {n: set() for n in names}
    for n in names:
        f = file_of[n]
        if not f:
            continue
        for g in list(dep.dependencies(paths, f, depth=1))[:12]:
            for m in by_file.get(g, ()):
                if m != n:
                    adj[n].add(m)
                    adj[m].add(n)

    out: list = []
    seen: set = set()
    # 연결이 많은 것부터 시작해 이웃을 따라간다 — 허브 주변이 한 조각에 모인다.
    for start in sorted(names, key=lambda x: (-len(adj[x]), x)):
        if start in seen:
            continue
        queue = [start]
        while queue:
            cur = queue.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            queue += sorted(adj[cur] - seen, key=lambda x: (-len(adj[x]), x))
    return out


def chunk_domain(paths: ProjectPaths, domain: str, *, members: dict | None = None,
                 max_classes: int = MAX_CLASSES, header_chars: int = HEADER_CHARS,
                 body_chars: int = BODY_CHARS,
                 total_chars: int = TOTAL_CHARS) -> list:
    """도메인 전체를 **여러 프롬프트 분량으로 쪼갠다.** 반환은 `DomainContexts` 리스트.

    사용자 지시(2026-08-09): *"컨텍스트 용량을 줄이진 않지만 페이로드를 분리해서 보내고
    그걸 재합성할 수 있는 물리 성능이 있잖아."*

    🔴 **이게 기본 경로다.** 한 요청만 쓰면 `ProjectAlpha_UiViewManagement` 는 67개 중
    8개만 보이고 59개가 영영 안 보인다 — 창을 못 늘리는 것과 **데이터를 못 보는 것은
    다른 문제**이고, 후자는 요청을 나누면 풀린다.

    조각 하나는 단일 요청 예산 안에 든다. 클래스 하나가 혼자 예산을 넘으면 **그 클래스만으로
    한 조각**을 만든다 — 버리지 않는다(발췌 상한이 이미 걸려 있어 무한히 크지 않다).
    """
    members = collect.members_of(paths, domain) if members is None else members
    inside = set(members)
    order = cohesion_order(paths, members)

    chunks: list = []
    cur = DomainContexts(domain=domain, members_total=len(members))
    for name in order:
        item = _build_one(paths, name, members, inside, header_chars, body_chars)
        over = (len(cur.items) >= max_classes
                or (cur.items and cur.chars + item.chars > total_chars))
        if over:
            chunks.append(cur)
            cur = DomainContexts(domain=domain, members_total=len(members))
        cur.items.append(item)
        cur.chars += item.chars
    if cur.items:
        chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        c.part = (i, len(chunks))
    return chunks
