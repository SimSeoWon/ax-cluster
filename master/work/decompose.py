"""분해 — 요청 하나를 **파견 가능한 조각들**로 (중 1.2, §4.5).

## 무엇을 정하나 — §3 의 미결이 여기서 닫힌다

`docs/3-open-items.md` 가 *"적용 순서(의존 순서 vs 임의) · 분할 입도"* 를 미결로 남겨 뒀다.
답은 셋이다:

    분할 입도   **파일 불가분 단위** — `batching.units()` 가 이미 정했다(모듈+경로+stem)
    적용 순서   [중요] **의존이 먼저** — `#include` 그래프로 정한다. 추측하지 않는다
    파일 내     `[PSEUDO:N]` 뎁스 — 한 파일이 1회 출력 한계를 넘을 때만

## [중요] 두 종류의 "쪼갬" 을 구분한다

    묶음 (동시)   서로 **다른 파일**을 맡는다 → 병렬 파견 가능 → `check_disjoint` 가 지킨다
    뎁스 (순차)   **같은 파일**을 단계로 나눈다 → `depends_on` 으로 줄을 선다

[주의] 이 구분을 놓치면 `check_disjoint` 가 뎁스를 위반으로 잡는다 — 같은 파일이 여러 조각에
나오니까. 하지만 **뎁스는 동시에 돌지 않으므로 충돌이 아니다.** 그래서 검사는
*"동시에 파견될 수 있는 것들"* 끼리만 본다.

## [중요] 적용 순서는 의존 방향 그대로다

A 가 B 를 `#include` 하면 **B 가 먼저** 적용돼야 한다 — A 를 먼저 넣으면 B 의 선언이 없어
컴파일이 깨진다. 즉 위상 정렬에서 **의존 대상이 앞**이다.

[주의] **순환은 실재한다.** C++ 헤더는 서로 물 수 있고(전방 선언으로 푸는 것이 정석이지만 늘
그렇지는 않다), `dependency.py` 의 역방향 매칭은 **basename 근사**라 없는 간선을 만들 수도
있다. 그래서 순환을 만나면 **막지 않고 보고**한다 — 근사가 만든 가짜 순환 때문에 정상 작업을
차단하는 것이 더 나쁘다(사실 게이트에서 이미 내린 판단). 순환 안에서는 안정 정렬로 둔다.

## [중요] 사람이 보고 자른다

`preview()` 가 있는 이유다. 원전도 Step 2 에서 플랜을 **사용자 승인**에 걸었다. 자동으로
파견하지 않는다 — 분해가 틀리면 N개 조각이 전부 헛일이 되고, 그건 골조가 틀린 것 다음으로 비싸다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from . import batching

MAX_DEPTH_LOOKUP = 1        # include 는 직접 의존만 본다 — 깊이를 늘리면 전부가 전부에 걸린다


@dataclass
class Piece:
    """파견 단위 하나 = 태스크 하나.

    [중요] `depth` 가 0 이면 파일 전체를 한 번에, 1 이상이면 **그 파일의 N번째 단계**다.
    """

    stem: str
    classes: list = field(default_factory=list)
    files: list = field(default_factory=list)
    depth: int = 0                                  # 0 = 뎁스 없음
    depends_on: list = field(default_factory=list)  # 앞 조각의 stem (파견 때 task_id 로 바뀐다)
    order: int = 0                                  # 적용 순서 — 작을수록 먼저

    @property
    def concurrent_key(self) -> str:
        """동시성 판정의 열쇠. [중요] **뎁스는 같은 파일이라도 동시에 돌지 않는다.**"""
        return self.stem if self.depth == 0 else f"{self.stem}#depth"

    @property
    def label(self) -> str:
        return self.stem if self.depth == 0 else f"{self.stem} (뎁스 {self.depth})"


@dataclass
class Plan:
    pieces: list = field(default_factory=list)
    cycles: list = field(default_factory=list)      # [주의] 순환 — 보고만 한다
    notes: list = field(default_factory=list)
    ungraphed: list = field(default_factory=list)   # 그래프에 없는 파일 (신규 파일이면 정상)

    @property
    def ok(self) -> bool:
        # [중요] 순환은 막지 않는다(근사가 만든 가짜일 수 있다). **파일 겹침만** 막는다.
        return not self.violations()

    def ordered(self) -> list:
        """적용 순서대로. 같은 순서면 stem·뎁스로 안정 정렬."""
        return sorted(self.pieces, key=lambda p: (p.order, p.stem, p.depth))

    def waves(self) -> list:
        """동시에 파견 가능한 묶음들 — [중요] **뎁스는 절대 같은 물결에 없다.**"""
        out: list = []
        for p in self.ordered():
            if p.depth > 1:
                # 뎁스 2 이상은 앞 뎁스가 끝나야 시작한다 — 물결을 새로 연다
                out.append([p])
                continue
            if out and all(q.depth == 0 or q.stem != p.stem for q in out[-1]) \
                    and out[-1] and out[-1][0].order == p.order:
                out[-1].append(p)
            else:
                out.append([p])
        return out

    def violations(self) -> list:
        """[중요] **동시에 돌 수 있는 것들끼리** 파일이 겹치나. 뎁스는 제외한다."""
        bad: list = []
        for wave in self.waves():
            seen: dict = {}
            for p in wave:
                for f in p.files:
                    if f in seen and seen[f] != p.stem:
                        bad.append(f"{f}: {seen[f]} 와 {p.stem} 가 같은 물결에서 함께 고친다")
                    seen[f] = p.stem
        return bad

    def preview(self) -> str:
        """[중요] **사람이 보고 자른다.** 무엇이 어떤 순서로 나가는지, 위험이 무엇인지."""
        out = [f"분해 계획 — 조각 {len(self.pieces)} · 물결 {len(self.waves())}"]
        for i, wave in enumerate(self.waves(), 1):
            tag = "동시" if len(wave) > 1 else "단독"
            out.append(f"  물결 {i} ({tag} {len(wave)}):")
            for p in wave:
                dep = f" ← {', '.join(p.depends_on)}" if p.depends_on else ""
                out.append(f"    {p.label}{dep}")
                for f in p.files:
                    out.append(f"        {f}")
        v = self.violations()
        if v:
            out += ["", "[중요] **파견하면 안 된다 — 같은 파일을 두 조각이 동시에 고친다:**"]
            out += [f"    {x}" for x in v]
        else:
            out.append("  [완료] 같은 물결 안에 파일 겹침 없음")
        if self.cycles:
            # [주의] 막지는 않는다 — basename 근사가 만든 가짜 순환일 수 있다
            out += ["", f"[주의] 순환 의존 {len(self.cycles)}건 — 그 안은 순서를 보장하지 못한다 "
                        "(막지 않는다: include 역추적이 근사라 가짜일 수 있다):"]
            out += [f"    {' → '.join(c)}" for c in self.cycles[:5]]
        if self.ungraphed:
            out.append(f"  [주의] 그래프에 없는 파일 {len(self.ungraphed)} — 신규 파일이면 정상 "
                       f"(예: {', '.join(self.ungraphed[:3])})")
        for n in self.notes:
            out.append(f"  {n}")
        return "\n".join(out)


def pieces_from(items: list) -> list:
    """`[(클래스, 파일)]` → 조각들. [중요] **파일 불가분**은 `batching` 이 이미 보장한다."""
    return [Piece(stem=u.key, classes=list(u.classes), files=list(u.files))
            for u in batching.units(items)]


def split_by_depth(piece: Piece, skeleton_text: str) -> list:
    """`[PSEUDO:N]` 이 있으면 뎁스별 조각으로 가른다 (소 1.2.4).

    [중요] **파일 불가분과 충돌하지 않는다** — 뎁스는 `depends_on` 으로 줄을 서므로 같은 파일을
    두 워커가 *동시에* 만지는 일이 없다. 원전이 이걸 쓴 이유는 하나다: **한 파일이 LLM 1회
    출력 한계를 넘을 때.**
    """
    from .skeleton import depths
    ds = depths(skeleton_text or "")
    if not ds:
        return [piece]
    out: list = []
    prev = ""
    for d in ds:
        p = Piece(stem=f"{piece.stem}.d{d}", classes=list(piece.classes),
                  files=list(piece.files), depth=d, order=piece.order,
                  depends_on=[prev] if prev else [])
        out.append(p)
        prev = p.stem
    return out


def _order_by_includes(paths: ProjectPaths, pieces: list) -> tuple:
    """의존이 먼저 오도록 순서를 매긴다. `(순환들, 그래프에 없는 파일들, 조회 실패 수)`.

    [중요] **A 가 B 를 include 하면 B 가 먼저다.** A 를 먼저 넣으면 B 의 선언이 없다.

    [중요] **조회 실패를 "의존 없음" 으로 뭉개지 않는다.** 처음엔 예외를 잡아 `[]` 로 두었는데,
    그러면 그래프가 통째로 죽어도 **순서가 임의로 정해지고 아무도 모른다** — 이 저장소가
    반복해 물린 *조용히 틀리는* 유형이다. 실패는 세어서 호출자가 말하게 한다.
    """
    from ..graph import dependency as dep

    owner: dict = {}                       # 파일 → 조각 stem
    for p in pieces:
        for f in p.files:
            owner[f] = p.stem
    edges: dict = {p.stem: set() for p in pieces}   # stem → 먼저 와야 할 stem 들
    ungraphed: list = []
    failures = 0
    for p in pieces:
        for f in p.files:
            try:
                deps = dep.dependencies(paths, f, depth=MAX_DEPTH_LOOKUP)
            except Exception:                        # noqa: BLE001
                # [중요] 실패는 "의존이 없다" 가 아니다 — 세어 둔다
                failures += 1
                continue
            if not deps and f not in ungraphed:
                ungraphed.append(f)
            for d in deps:
                other = owner.get(d)
                # 자기 자신(같은 조각의 `.h`↔`.cpp`)은 간선이 아니다
                if other and other != p.stem:
                    edges[p.stem].add(other)

    # 위상 정렬 — 들어오는 간선이 없는 것부터. 남으면 순환이다.
    order: dict = {}
    remaining = dict(edges)
    wave = 0
    while remaining:
        ready = sorted(k for k, v in remaining.items() if not (v & set(remaining)))
        if not ready:
            break                                    # [중요] 순환 — 아래에서 보고한다
        for k in ready:
            order[k] = wave
            del remaining[k]
        wave += 1
    cycles: list = []
    if remaining:
        # 남은 것들이 순환에 얽혀 있다. **막지 않고** 뒤에 안정 정렬로 붙인다.
        for k in sorted(remaining):
            order[k] = wave
        cycles = [sorted(remaining)]
    for p in pieces:
        p.order = order.get(p.stem, 0)
    return cycles, ungraphed, failures


def plan(paths: ProjectPaths, items: list, *, skeletons: dict | None = None,
         order: bool = True) -> Plan:
    """분해 계획을 세운다. **읽기 전용이고 LLM 을 쓰지 않는다.**

    `items` — `[(클래스, 파일)]`. `skeletons` — `{stem: 골조텍스트}`(뎁스 분할용, 선택).

    [중요] **파견하지 않는다.** 계획을 돌려줄 뿐이고, `preview()` 를 사람이 본 뒤에 나간다.
    """
    p = Plan(pieces=pieces_from(items))
    if not p.pieces:
        p.notes.append("[중요] 조각이 없다 — 분해할 대상이 비었다")
        return p
    if order:
        try:
            from ..graph import dependency as dep
            if not dep.exists(paths):
                # [중요] 그래프가 아예 없으면 **순서를 정한 것이 아니다** — 그렇게 말한다
                p.notes.append("[주의] include 그래프가 없다 — 순서를 못 정했다(이름순). "
                               "`python -m master.graph build` 가 선행이다")
            p.cycles, p.ungraphed, fails = _order_by_includes(paths, p.pieces)
            if fails:
                # [주의] 순서를 못 정한 것과 순서가 없는 것은 다르다 — 말로 적는다
                p.notes.append(f"[주의] include 조회 실패 {fails}건 — 그만큼은 순서 근거가 없다")
        except Exception as e:                       # noqa: BLE001
            p.notes.append(f"[주의] include 그래프로 순서를 못 정했다 — 이름순으로 둔다: {e}")
    if skeletons:
        out: list = []
        for piece in p.pieces:
            out.extend(split_by_depth(piece, skeletons.get(piece.stem, "")))
        n_split = len(out) - len(p.pieces)
        p.pieces = out
        if n_split:
            p.notes.append(f"뎁스 분할로 조각이 {n_split}개 늘었다 — [중요] 순차로만 돈다")
    return p


def to_specs(p: Plan, *, instruction: str = "", requires: list | None = None) -> list:
    """계획 → `register.TaskSpec` 들. [중요] **위반이 있으면 만들지 않는다.**"""
    from .register import RegisterError, TaskSpec
    v = p.violations()
    if v:
        raise RegisterError("분해가 불변식을 깬다 — 파견하지 않는다: " + "; ".join(v[:3]))
    specs: list = []
    for piece in p.ordered():
        specs.append(TaskSpec(
            stem=piece.stem, classes=list(piece.classes),
            target_files=list(piece.files), instruction=instruction,
            requires=list(requires or []),
            # [중요] 순서가 곧 우선순위다 — 먼저 적용될 것이 먼저 나간다
            priority=max(0, 100 - piece.order),
            depends_on=list(piece.depends_on),
        ))
    return specs


# ── 🔴 정본 ⑷ — 조각의 파일 집합을 **골조 파일 기준으로** 채운다 ─────────────────────────
#
# [중요] **이것이 없어서 라운드 하나가 4/4 죽었다** (실측 2026-09-03 23:12~23:16).
#
#     태스크 target   Source/NS/Interaction/NSInteractable.h
#     워커가 고친 것  Source/NS/Interaction/NSInteractable.cpp   ← 조각의 집합 밖
#     커밋            대상 파일만 스테이징 → `.h` 는 무변경 → "no changes added to commit"
#                     → rc=1 → BLOCKED. **실제 산출물이 통째로 버려졌다.**
#
# 왜 났나: 조각 나눔은 요청자(`.33`)가 `specs_json` 으로 보내고(`register_work_tool` 계약이
# *"이미 클래스 단위로 쪼개진 것"*), 그 명세에 `.h` 만 실려 있었다. 골조 커밋에는 `.h` 4개와
# `.cpp` 4개가 **다 있었는데** 등재가 절반만 실었다. 앞 라운드는 `target_file=.cpp` +
# `header_file=.h` 라 둘이 갔고 그래서 통과했다 — **짝이 붙으면 되고 갈리면 죽는다.**
#
# [중요] **왜 등재가 아니라 여기인가.** 등재 시점에는 골조가 아직 push 되지 않았다
# (실측: 등재 23:07:21 → 골조 push 23:12). 골조 파일을 실제로 볼 수 있는 첫 자리가 파견이고,
# 정본 ⑷ 이 *"마스터가 **골조 파일 기준으로** 서브태스크를 만든다"* 고 한 그 자리다.
#
# [주의] **골조 커밋이 건드린 파일만** 후보로 본다. 아무 짝이나 끌어오면 `batching` 이 막던
# 반대편 사고가 난다 — 실측 2026-08-10: 다른 모듈·같은 이름 9건(파일 36개)은 **갈라야** 한다.
# 골조 diff 안으로 한정하면 그 위험이 사라진다(그 커밋이 만든 짝만 붙는다).

_PAIR = {".h": (".cpp",), ".hpp": (".cpp", ".cxx"), ".cpp": (".h", ".hpp"),
         ".cxx": (".hpp", ".h")}


def _siblings(rel: str) -> list:
    """`rel` 의 짝 후보 경로들. 같은 폴더 먼저, 그 다음 UE `Public/`↔`Private/`."""
    import posixpath
    rel = str(rel or "").replace("\\", "/")
    stem, ext = posixpath.splitext(rel)
    out: list = []
    for e in _PAIR.get(ext.lower(), ()):  # 같은 폴더
        out.append(stem + e)
        # UE 는 선언을 `Public/`, 정의를 `Private/` 에 두는 배치가 흔하다 (실측 50쌍)
        for a, b in (("/Public/", "/Private/"), ("/Private/", "/Public/")):
            if a in stem:
                out.append(stem.replace(a, b) + e)
    return out


def complete_pairs(paths, commit: str, want: list, *, main_branch: str = "main") -> tuple:
    """`(채운 want, 추가된 것, 사유)`. **읽기 전용** — git 을 쓰기로 만지지 않는다.

    [주의] 실패해도 파견을 막지 않는다 — 짝을 못 채운 것과 조각이 틀린 것은 다르다.
    사유를 돌려주고 호출자가 로그에 남긴다(조용히 비지 않게).
    """
    base_want = [str(w).replace("\\", "/") for w in (want or []) if str(w or "").strip()]
    if not (commit or "").strip():
        return base_want, [], "기준 커밋이 없다 — 짝을 못 찾는다"
    try:
        from . import declarations as D
        D.ensure_commit(paths, commit)
        out = D._mirror_git(paths, "diff", "--name-only", f"{main_branch}...{commit}")
        changed = {ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()}
    except Exception as e:                                   # noqa: BLE001
        return base_want, [], f"골조 파일 목록을 못 읽었다 — {type(e).__name__}: {e}"
    if not changed:
        return base_want, [], f"골조 커밋이 바꾼 파일이 없다 ({main_branch}...{commit[:8]})"

    have = set(base_want)
    added: list = []
    for w in base_want:
        for cand in _siblings(w):
            if cand in changed and cand not in have:
                have.add(cand)
                added.append(cand)
                break                     # 짝은 하나면 된다
    return base_want + added, added, ""
