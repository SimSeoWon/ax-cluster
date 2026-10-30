"""도메인 클래스 컨텍스트 수집 — 재합성 프롬프트의 근거 (LLM 0).

원본: `watcher/ontology_invariants.py` 의 `collect_domain_class_contexts` ·
`extract_cpp_excerpt`.

## [중요] 원본 상수를 그대로 옮기면 노드가 죽는다

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

[중요] **`num_ctx` 와 이 예산은 함께 움직인다.** `context_synth/synth.py` 가 같은 규칙을
주석으로 못박아 뒀다: *발췌만 늘리면 컨텍스트 창을 넘어 뒤가 잘린다.*

## 무엇을 싣나 — 지도가 아니라 소스다

`docs/3-open-items.md` 가 지적한 구멍이 여기에도 걸린다: **추론 노드는 파일을 못 읽는다.**
그러니 "어느 클래스가 있다" 만 주면 액션·invariant 를 지어낼 수밖에 없다. 그래서
**선언부(.h)와 신호 인근(.cpp)** 을 직접 싣는다 — 원본이 같은 이유로 같은 선택을 했다.

`.cpp` 는 전체가 아니라 **invariant 신호 인근만** 발췌한다(원본 휴리스틱):
함수 정의 · `check()`/`ensure()`/`verify()` · lock/RAII · 스마트 포인터 선언 ·
`@invariant`/`@precondition` 주석.

## 언어는 파일 확장자가 고른다 (`#850`)

`.py` 멤버에 위 규칙을 그대로 걸면 **대상 클래스 본문이 안 실린다** — 선언부는 파일 앞
1,200자(대개 모듈 docstring)이고, 본문은 `.h` 가 아니라 빈 문자열이다(실측:
`master/ontology/synth.py` 의 `DomainResult` 가 발췌에 없었다). 그래서 `.py` 는 `ast` 로
**그 클래스**를 찾아 선언부(클래스 시그니처·docstring·필드·메서드 시그니처)와 클래스 범위
안의 신호 인근을 싣는다. 혼합 프로젝트가 있으므로(MotionForge = unreal + Python 웹 UI)
프로젝트 kind 가 아니라 **파일마다** 고른다.

[중요] `excerpt_header` 의 동작은 바꾸지 않는다 — 층2 그라운딩(`work/declarations.py`)과
골조(`work/skeleton.py`)도 부른다. 갈림은 이 모듈의 `_build_one` 한 곳에서만 한다.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .. import source_text
from ..context_search.paths import ProjectPaths
from ..graph import class_graph as cg, dependency as dep
from . import collect

# [중요] 예산 — **실측으로 정한다. 원본 값이 아니다.**
# 원본: 클래스 10 × (.h 3000 + .cpp 2500). 상용 API 전제라 우리보다 한 자리 크다.
MAX_CLASSES = 6               # 조각당 프롬프트에 싣는 클래스 수
HEADER_CHARS = 1200           # 클래스당 .h 발췌
BODY_CHARS = 900              # 클래스당 .cpp 발췌

# [중요] **실측으로 정한 값이다** (2026-08-09, `/api/generate` 의 `prompt_eval_count`):
#
#   프롬프트 17,315자 → 35B 6,070 tok (2.85자/tok) · 14b 6,200 tok (2.79자/tok)
#
# `num_ctx` 는 양쪽 노드 실측 상한이 **8192** 다. 출력에 JSON 5~15건(description·flow 포함)
# 이 들어가려면 **2,500~3,000 토큰**을 남겨야 하므로 프롬프트는 **5,000 토큰 ≈ 14,000자**가
# 상한이다. 규칙 블록(~4,500자) + 도메인 서술(~1,800자) + 클래스 목록이 먼저 먹으므로
# **발췌에 쓸 수 있는 것은 ~7,000자**다.
#
# [중요] 넘치면 **조용히 뒤가 잘린다** — 모델은 그 사실을 말하지 않고 앞부분만 보고 답한다.
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

# 파이썬 클래스 범위 안의 「표시된 주석」. 이 저장소의 규약 표식과 원본의 `@invariant` 류다.
# [주의] 주석 전부를 신호로 세지 않는다 — 주석이 촘촘한 코드에서는 예산을 주석이 다 먹는다.
_PY_COMMENT = re.compile(
    r"^\s*#.*(?:@(?:invariant|precondition|postcondition|note)\b|\[중요\]|\[주의\]|🔴)", re.I)
PY_BODY_AFTER = 3             # 파이썬 신호 줄 뒤에 붙이는 문맥 줄 수 (.cpp 는 8 — 줄이 짧다)

CPP_EXTS = (".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".c", ".cc", ".cpp", ".cxx")


def lang_of(file: str) -> str:
    """발췌·프롬프트 언어 — **파일 확장자로만** 정한다. 모르는 확장자는 빈 문자열(종전 동작)."""
    f = (file or "").lower()
    if f.endswith(".py"):
        return "python"
    if f.endswith(CPP_EXTS):
        return "cpp"
    return ""


@dataclass
class ClassContext:
    """프롬프트에 실릴 클래스 하나."""
    name: str
    file: str = ""
    ancestors: list = field(default_factory=list)
    neighbours: list = field(default_factory=list)     # `#include` 로 얽힌 도메인 밖 클래스
    header: str = ""
    body: str = ""
    lang: str = ""                # `lang_of(file)` — 라벨과 프롬프트 언어 블록이 이것을 본다
    excerpt: str = ""             # [중요] 어떤 발췌 경로를 탔나 · 폴백 사유 (`plan` 이 찍는다)

    @property
    def chars(self) -> int:
        return len(self.header) + len(self.body)

    def block(self) -> str:
        out = [f"클래스: {self.name}", f"  파일: {self.file or '-'}"]
        if self.ancestors:
            out.append(f"  조상: {', '.join(self.ancestors[:ANCESTORS_SHOWN])}")
        if self.neighbours:
            out.append(f"  도메인 밖 include: {', '.join(self.neighbours[:NEIGHBOURS_SHOWN])}")
        py = self.lang == "python"
        if self.header:
            out.append("  [선언부]" if py else "  [.h 선언부]")
            out += [f"    {ln}" for ln in self.header.splitlines()]
        if self.body:
            out.append("  [신호 인근]" if py else "  [.cpp 신호 인근]")
            out += [f"    {ln}" for ln in self.body.splitlines()]
        return "\n".join(out)


@dataclass
class DomainContexts:
    domain: str
    items: list = field(default_factory=list)
    members_total: int = 0
    truncated: list = field(default_factory=list)   # [중요] 예산 때문에 뺀 클래스 이름
    chars: int = 0
    part: tuple = (1, 1)                            # (조각 번호, 전체 조각 수)
    kind: str = ""                                  # `profile.kind_of` — 빈 값은 종전(UE) 동작

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
            s += f" · [중요] 예산으로 제외 {len(self.truncated)}"
        return s

    @property
    def note(self) -> str:
        """[중요] 프롬프트 본문에 넣을 결손 고지. **안 보이는 것을 숨기지 않는다.**

        조각으로 나뉜 경우가 특히 중요하다 — 모델은 자기가 받은 것이 전부라고 가정하고,
        빈칸을 지어내 채운다. **"이건 일부다" 를 말해 주면 그 압력이 줄어든다.**
        """
        i, n = self.part
        lines: list = []
        if n > 1:
            lines.append(
                f"[주의] 이것은 `{self.domain}` 도메인의 **{n}조각 중 {i}번째**다 "
                f"(도메인 전체 클래스 {self.members_total}개). 여기 실린 클래스만 다루고, "
                f"다른 조각에 있을 클래스는 추측하지 말 것 — 나머지는 따로 처리된다.")
        if self.truncated:
            shown = ", ".join(self.truncated[:10])
            more = "" if len(self.truncated) <= 10 else f" 외 {len(self.truncated) - 10}개"
            lines.append(f"[주의] 예산으로 실리지 않은 클래스: {shown}{more}. "
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
    return _render_hits(lines, hits, limit)


def _render_hits(lines: list, hits: list, limit: int) -> str:
    """신호 구간 `(시작, 끝)` 들을 합쳐 **줄번호와 생략 표시**로 그린다. C++·파이썬 공용."""
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


def _py_class(tree, name: str):
    """모듈 최상위 `ClassDef` 중 이름이 맞는 것. 모듈 접두가 붙은 이름은 **마지막 마디**로 찾는다
    (`graph/pyparse.disambiguate` 가 겹친 이름에 `pkg.mod.` 을 붙인다)."""
    short = name.rsplit(".", 1)[-1]
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == short:
            return node
    return None


def _first_line(node) -> int:
    """데코레이터까지 포함한 시작 줄 (1부터)."""
    decos = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decos])


def _signature_end(node, lines: list) -> int:
    """`def`/`class` 시그니처의 끝 줄 (1부터). 본문 첫 문장 앞까지이되, 뒤에 붙은 빈 줄·주석은 뺀다."""
    end = max(node.lineno, node.body[0].lineno - 1) if node.body else node.lineno
    while end > node.lineno and (not lines[end - 1].strip()
                                 or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return end


def _py_header(node, lines: list, limit: int) -> list:
    """선언부 줄 번호(1부터) — 클래스 시그니처 · docstring · 메서드 시그니처, 남는 예산에 필드.

    [주의] 필드는 **뒤순위**다. 필드가 많은 `@dataclass` 는 필드만으로 예산을 다 먹어 메서드
    시그니처가 안 보였다(실측: `synth.DomainResult` 필드 29개 > 1,200자).
    """
    keep: set = set()
    end = _signature_end(node, lines)
    body = node.body
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        end = body[0].end_lineno
        body = body[1:]
    keep.update(range(_first_line(node), end + 1))
    fields: list = []
    for st in body:
        if isinstance(st, (ast.AnnAssign, ast.Assign)):
            fields.append(range(st.lineno, st.end_lineno + 1))
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            keep.update(range(_first_line(st), _signature_end(st, lines) + 1))
    used = sum(len(lines[i - 1]) + 1 for i in keep)
    for rng in fields:
        cost = sum(len(lines[i - 1]) + 1 for i in rng)
        if used + cost > limit:
            break
        keep.update(rng)
        used += cost
    return sorted(keep)


def _py_signal_lines(node, lines: list) -> list:
    """클래스 범위 안의 신호 줄(0부터) — assert · raise · with · early return · 표시된 주석."""
    hits: set = set()
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Assert, ast.Raise, ast.With, ast.AsyncWith)):
            hits.add(sub.lineno - 1)
        elif isinstance(sub, ast.If):
            # early return — `if …:` 바로 아래가 return/raise 인 가드절
            if sub.body and isinstance(sub.body[0], (ast.Return, ast.Raise)):
                hits.add(sub.lineno - 1)
    for i in range(node.lineno - 1, node.end_lineno):
        if _PY_COMMENT.match(lines[i]):
            hits.add(i)
    return sorted(hits)


def excerpt_python(paths: ProjectPaths, file: str, name: str, header_limit: int = HEADER_CHARS,
                   body_limit: int = BODY_CHARS) -> tuple:
    """`.py` 의 **대상 클래스** 발췌 → `(선언부, 신호 인근, 경로 설명)`.

    [중요] AST 파싱이 실패하거나 클래스를 못 찾으면 **종전 동작으로 떨어지고 그 사실을
    설명에 적는다** — 조용히 파일 앞부분을 실으면 모델은 그것이 그 클래스인 줄 안다.
    """
    d = source_text.read(paths.repo / file) if file else None
    if d is None:
        return "", "", "python → 폴백: 파일을 못 읽음"
    try:
        tree = ast.parse(d.text)
    except (SyntaxError, ValueError) as e:
        why = f"AST 파싱 실패 ({type(e).__name__})"
        return excerpt_header(paths, file, header_limit), "", f"python → 폴백: {why}"
    node = _py_class(tree, name)
    if node is None:
        return (excerpt_header(paths, file, header_limit), "",
                f"python → 폴백: 클래스 못 찾음 ({name.rsplit('.', 1)[-1]})")
    lines = d.text.splitlines()
    shown = _py_header(node, lines, header_limit)
    header = "\n".join(lines[i - 1] for i in shown)[:header_limit].rstrip()
    sig = _py_signal_lines(node, lines)
    hi = node.end_lineno
    if sig:
        hits = [(max(node.lineno - 1, i - 1), min(hi, i + 1 + PY_BODY_AFTER)) for i in sig]
        return header, _render_hits(lines, hits, body_limit), "python(ast)"
    # 신호가 없으면 선언부에 안 실린 클래스 본문 앞 40줄 — `.cpp` 의 「앞 40줄」과 같은 취지
    # [주의] **메서드 본문이 먼저다** — 앞에서부터 채우면 선언부에 못 실린 필드 줄이 자리를 먹어
    #    `synth.DomainResult` 는 `ok`·`summary` 본문 대신 필드 한 줄이 실렸다(실측 `#850`).
    seen = set(shown)
    in_method = {i for st in node.body if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef))
                 for i in range(st.body[0].lineno, st.end_lineno + 1)}
    cand = [i for i in range(node.lineno, hi + 1) if i not in seen and lines[i - 1].strip()]
    rest = sorted(([i for i in cand if i in in_method] + [i for i in cand if i not in in_method])[:40])
    body = _render_hits(lines, [(i - 1, i) for i in rest], body_limit) if rest else ""
    what = "메서드 본문 앞부분" if in_method & set(rest) else "본문 앞부분"
    return header, body, f"python(ast) · 신호 없음 → {what}"


def _neighbours(paths: ProjectPaths, file: str, inside: set) -> list:
    """`#include` 로 얽힌 **도메인 밖** 클래스. 협력 신호이자 cross-domain 경고다.

    [주의] 역방향은 basename 근사다(중 1.1 의 알려진 한계) — 그래서 **참고로만** 싣고
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
    lang = lang_of(file)
    if lang == "python":
        header, body, route = excerpt_python(paths, file, name, header_chars, body_chars)
    else:
        header = excerpt_header(paths, file, header_chars)
        body = excerpt_body(paths, file, body_chars)
        route = "c++(.h+.cpp)" if lang == "cpp" else f"기본({file.rsplit('.', 1)[-1] if '.' in file else '확장자 없음'})"
    return ClassContext(
        name=name,
        file=file,
        ancestors=cg.find_ancestors(paths, name, max_depth=3),
        neighbours=_neighbours(paths, file, inside),
        header=header,
        body=body,
        lang=lang,
        excerpt=f"발췌 {route} · 선언 {len(header)}자 · 본문 {len(body)}자",
    )


def _kind(paths: ProjectPaths) -> str:
    """프로젝트 kind. 읽지 못하면 빈 값 — 프롬프트는 그것을 종전(UE) 동작으로 읽는다."""
    try:
        from ..projects import profile                      # noqa: PLC0415
        return profile.kind_of(getattr(paths, "name", "") or "")
    except Exception:                                       # noqa: BLE001
        return ""


def collect_domain(paths: ProjectPaths, domain: str, *, members: dict | None = None,
                   max_classes: int = MAX_CLASSES, header_chars: int = HEADER_CHARS,
                   body_chars: int = BODY_CHARS,
                   total_chars: int = TOTAL_CHARS) -> DomainContexts:
    """도메인 하나를 **한 프롬프트 분량으로** 자른 컨텍스트.

    [중요] 이건 단일 요청용이다. 도메인 전체를 다루려면 `chunk_domain` 을 쓴다 — 그쪽이
    기본 경로이고, 이 함수는 첫 조각만 필요한 곳(미리보기·비교 측정)에서 쓴다.

    멤버 순서는 이름순이다 — `confidence` 로 정렬하던 원본과 다르다. 우리
    `class_ontology` 는 아직 비어 있어(중 1.3 이 채운다) 정렬 근거가 없고, **없는 근거로
    정렬하는 척하지 않는다.** 채워지면 그때 정렬을 바꾼다.
    """
    members = collect.members_of(paths, domain) if members is None else members
    ctx = DomainContexts(domain=domain, members_total=len(members), kind=_kind(paths))
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

    [중요] **쪼갤 때 이 순서가 품질을 좌우한다.** 액션은 클래스 *사이*의 관계이므로, 이름순으로
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

    [중요] **이게 기본 경로다.** 한 요청만 쓰면 `ProjectAlpha_UiViewManagement` 는 67개 중
    8개만 보이고 59개가 영영 안 보인다 — 창을 못 늘리는 것과 **데이터를 못 보는 것은
    다른 문제**이고, 후자는 요청을 나누면 풀린다.

    조각 하나는 단일 요청 예산 안에 든다. 클래스 하나가 혼자 예산을 넘으면 **그 클래스만으로
    한 조각**을 만든다 — 버리지 않는다(발췌 상한이 이미 걸려 있어 무한히 크지 않다).
    """
    members = collect.members_of(paths, domain) if members is None else members
    inside = set(members)
    order = cohesion_order(paths, members)

    kind = _kind(paths)
    chunks: list = []
    cur = DomainContexts(domain=domain, members_total=len(members), kind=kind)
    for name in order:
        item = _build_one(paths, name, members, inside, header_chars, body_chars)
        over = (len(cur.items) >= max_classes
                or (cur.items and cur.chars + item.chars > total_chars))
        if over:
            chunks.append(cur)
            cur = DomainContexts(domain=domain, members_total=len(members), kind=kind)
        cur.items.append(item)
        cur.chars += item.chars
    if cur.items:
        chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        c.part = (i, len(chunks))
    return chunks
