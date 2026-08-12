"""포팅 모드 — 원본에서 **의도만** 읽는다 (소 1.3.5).

## 🔴 이 프로젝트가 포팅 프로젝트다

`ModularStage` 는 `Project_Alpha` 에서 코드를 **옮겨 오는 중**이고, 두 모듈이 **같은 체크아웃
안에** 나란히 있다(`Source/Project_Alpha/` · `Source/ModularStage/`). 그래서 원본 대응 파일을
찾는 일은 원격 저장소를 뒤지는 것이 아니라 **경로 계산**이다.

## 🔴 실측 — 동명 매칭만으로는 절반도 못 잡는다 (2026-08-12)

    파일 1,654개 (`.h`/`.hpp`/`.cpp`)
    stem 그대로 같은 쌍            9      ← 문서에 적혀 있던 그 9쌍
    🔴 접두사 정규화 후 같은 쌍     21     ← 2.3배. 전부 진짜 대응이었다

포팅이 **개명을 거쳤기** 때문이다 — 측정으로 확인된 대응 형태:

    AlphaManager_Mission  ↔  Manager_Mission        접두사 `Alpha`
    AlphaTableEnum        ↔  TableEnum
    AlphaCharacter        ↔  ModularStageCharacter  접두사가 **양쪽에** 다르게 붙는다
    Alpha_HexagonTileItem ↔  Alpha_HexagonTileItem  🔴 그대로 옮긴 것은 접두사가 **남아 있다**

⚠️ **퍼지 매칭은 하지 않는다.** 접두사 정규화까지가 결정적으로 방어할 수 있는 선이고, 편집
거리 같은 것을 넣으면 **틀린 원본을 붙인다.** 원본이 없는 것보다 나쁘다 — 관계없는 코드에서
의도를 읽으면 모델은 자신 있게 엉뚱한 것을 만든다. 그래서 **매칭 규칙을 결과에 실어** 사람이
가늠할 수 있게 한다(`exact` / `prefix`).

## 🔴 경로만 댄다 — 내용을 싣지 않는다

골조 생성(소 1.1.5 ③)에서는 반대였다: *"이름만 대고 내용을 안 줬더니 모델이 열거값을
지어냈다."* 여기서 경로만 대도 되는 이유는 **읽는 주체가 다르기 때문**이다.

    골조 생성   마스터의 LLM — 파일 접근이 **없다** → 🔴 내용을 실어야 한다
    추론 파견   워커의 Claude — 자기 체크아웃을 **읽는다** → 경로를 대면 충분하다

그래서 이 모듈은 파일을 열지 않고 **목록만** 만든다. 그리고 그 목록에 못박는다:
🔴 **읽기 전용 · 복사 금지 · 원본 Edit/Write 금지.** 원본은 참조이고, 고칠 곳은 대상뿐이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

SOURCE_SUFFIXES = (".h", ".hpp", ".cpp")

# 🔴 실측으로 고른 접두사 (위 § 참조). **긴 것이 먼저** — `Alpha_` 가 `Alpha` 보다 앞이어야
#    `Alpha_HexagonTileItem` 에서 밑줄이 남지 않는다.
PREFIXES = ("ModularStage", "Alpha_", "Alpha", "MS")

# 원본 모듈. 🔴 코드에 박지 않고 기본값으로만 둔다 — 다른 프로젝트는 다른 이름을 쓴다.
DEFAULT_SOURCE_DIRS = ("Project_Alpha", "Project_AlphaEditor")

EXACT, PREFIX = "exact", "prefix"


def normalize_stem(stem: str) -> str:
    """접두사를 떼고 소문자로. **결정적 · LLM 0.**

    한 번만 뗀다 — `AlphaAlphaFoo` 같은 것을 상상해 두 번 떼면 없는 대응을 만든다.
    """
    s = str(stem or "")
    for p in PREFIXES:
        if s.startswith(p) and len(s) > len(p):
            s = s[len(p):].lstrip("_")
            break
    return s.lower()


@dataclass
class Match:
    """대상 파일 하나에 붙는 원본들. 🔴 **어떻게 맞췄는지**까지 들고 다닌다."""

    target: str
    sources: list = field(default_factory=list)
    rule: str = EXACT

    @property
    def confident(self) -> bool:
        """`exact` 는 우연이 아니다. `prefix` 는 사람이 한 번 봐야 한다."""
        return self.rule == EXACT


@dataclass
class Porting:
    matches: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.matches)

    def all_sources(self) -> list:
        out: list = []
        for m in self.matches:
            for s in m.sources:
                if s not in out:
                    out.append(s)
        return out

    def summary(self) -> str:
        if not self.matches:
            return "포팅 원본 대응 없음 — " + ("; ".join(self.notes) or "신규 코드로 본다")
        ex = sum(1 for m in self.matches if m.confident)
        s = (f"포팅 원본 {len(self.all_sources())}개 · 대상 {len(self.matches)}개 "
             f"(exact {ex} · prefix {len(self.matches) - ex})")
        return s + ("" if not self.notes else " · " + "; ".join(self.notes))


_INDEX_CACHE: dict = {}


def _index(root, source_dirs: tuple) -> tuple:
    """`(원본 stem→[경로], 원본 정규stem→[경로])`. 🔴 **읽기 전용 — 열지 않고 이름만 본다.**

    ⚠️ 한 번 등록에 태스크가 여러 개면 같은 스캔이 반복된다(파일 1,654개). 프로세스 수명 동안
    캐시한다 — 마스터의 색인 클론은 인덱서가 갱신하고, 그 사이 새 프로세스가 뜬다.
    """
    key = (str(root), source_dirs)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    exact: dict = {}
    norm: dict = {}
    if root is None or not root.is_dir():
        return exact, norm
    for d in source_dirs:
        sub = root / d
        if not sub.is_dir():
            continue
        for f in sub.rglob("*"):
            if f.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            try:
                rel = "Source/" + str(f.relative_to(root)).replace("\\", "/")
            except ValueError:                       # noqa: PERF203 — 경로 밖은 건너뛴다
                continue
            exact.setdefault(f.stem, []).append(rel)
            norm.setdefault(normalize_stem(f.stem), []).append(rel)
    _INDEX_CACHE[key] = (exact, norm)
    return exact, norm


def counterparts(paths, target_files: list, *, source_dirs=DEFAULT_SOURCE_DIRS,
                 max_each: int = 4) -> Porting:
    """대상 파일들의 **원본 대응**을 찾는다. `exact` 를 먼저, 없으면 `prefix`.

    🔴 **못 찾은 것은 못 찾았다고 둔다.** 억지로 붙이지 않는다 — 관계없는 원본에서 의도를
    읽으면 모델은 자신 있게 엉뚱한 것을 만들고, 그건 원본이 없는 것보다 나쁘다.
    """
    out = Porting()
    root = getattr(paths, "source", None)
    exact, norm = _index(root, tuple(source_dirs))
    if not exact:
        out.notes.append(f"원본 모듈을 못 찾았다 ({', '.join(source_dirs)}) — 포팅 대상이 아니거나 "
                         f"소스 트리가 없다")
        return out

    for t in [f for f in (target_files or []) if f]:
        stem = PurePosixPath(str(t).replace("\\", "/")).stem
        # 🔴 원본 자기 자신을 자기 원본으로 붙이지 않는다
        in_source = any(f"/{d}/" in f"/{str(t).replace(chr(92), '/')}" for d in source_dirs)
        if in_source:
            continue
        hits = [p for p in exact.get(stem, []) if p != t]
        rule = EXACT
        if not hits:
            hits = [p for p in norm.get(normalize_stem(stem), []) if p != t]
            rule = PREFIX
        if not hits:
            continue
        out.matches.append(Match(target=t, sources=sorted(hits)[:max_each], rule=rule))
        if len(hits) > max_each:
            # ⚠️ 자른 것을 말한다 — 조용한 절단은 "다 봤다" 로 읽힌다
            out.notes.append(f"{stem}: 원본 후보 {len(hits)}개 중 {max_each}개만 실었다")
    if not out.matches:
        out.notes.append("대상 파일에 대응하는 원본이 없다 — 신규 코드로 본다")
    return out


MANIFEST_HEADING = "## 포팅 원본 — 🔴 **읽기 전용 · 의도 파악 전용**"


def manifest_section(p: Porting) -> list:
    """매니페스트에 실을 절. 🔴 **경로만** 싣는다 — 워커가 자기 체크아웃에서 연다."""
    if not p.matches:
        return []
    lines = [MANIFEST_HEADING, ""]
    lines.append("이 작업은 **포팅**이다. 아래 원본이 *무엇을 하려던 것인지* 읽고, 그 의도를 "
                 "대상 파일에 **현재 구조로** 다시 쓴다.")
    lines.append("")
    lines.append("🔴 **금지 셋** — 원본은 참조일 뿐이다:")
    lines.append("")
    lines.append("    ① 원본을 Edit·Write 하지 않는다      ② 원본을 복사해 붙이지 않는다")
    lines.append("    ③ 원본을 대상 파일 목록에 넣지 않는다")
    lines.append("")
    lines.append("원본은 구 엔진 규약(`BuildSettingsVersion.V5`·`EngineIncludeOrderVersion."
                 "Unreal5_4`) 위에 있고 빌드 대상도 아니다. **베끼면 낡은 것이 새로 들어온다** — "
                 "그래서 옮기는 것은 코드가 아니라 의도다.")
    lines.append("")
    for m in p.matches:
        tag = "" if m.confident else " ⚠️ (접두사 정규화로 맞췄다 — 대응이 맞는지 먼저 확인)"
        lines.append(f"- 대상 `{m.target}`{tag}")
        for s in m.sources:
            lines.append(f"    - 원본 `{s}`")
    if p.notes:
        lines.append("")
        lines.extend(f"⚠️ {n}" for n in p.notes)
    return lines


# ── CLI ──────────────────────────────────────────────────────────────────────────
#
#   python -m master.work.porting pairs [프로젝트]        원본↔대상 동명 쌍 전부 (실측)
#   python -m master.work.porting find  [프로젝트] <파일…> 그 파일들의 원본 대응

def _all_pairs(paths, source_dirs=DEFAULT_SOURCE_DIRS) -> None:
    root = getattr(paths, "source", None)
    exact, norm = _index(root, tuple(source_dirs))
    if not exact:
        print("🔴 원본 모듈을 못 찾았다")
        return
    tgt_exact: dict = {}
    tgt_norm: dict = {}
    for f in root.rglob("*"):
        if f.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        rel = "Source/" + str(f.relative_to(root)).replace("\\", "/")
        if any(f"/{d}/" in f"/{rel}" for d in source_dirs):
            continue
        tgt_exact.setdefault(f.stem, []).append(rel)
        tgt_norm.setdefault(normalize_stem(f.stem), []).append(rel)
    e = sorted(set(exact) & set(tgt_exact))
    n = sorted(set(norm) & set(tgt_norm))
    print(f"원본 파일 {sum(len(v) for v in exact.values())} · "
          f"대상 파일 {sum(len(v) for v in tgt_exact.values())}")
    print(f"stem 그대로 같은 것 {len(e)} · 🔴 접두사 정규화 후 {len(n)}")
    exact_norm = {normalize_stem(x) for x in e}
    for k in n:
        # `=` 는 stem 그대로 같은 것, `~` 는 접두사 정규화로 맞춘 것
        mark = "=" if k in exact_norm else "~"
        print(f"  {mark} {k}: {sorted(norm[k])[0]} <-> {sorted(tgt_norm[k])[0]}")


def main(argv) -> int:
    from ..context_search.paths import resolve
    cmd = (argv[0] if argv else "pairs").strip()
    project = argv[1] if len(argv) > 1 else ""
    paths = resolve(project)
    if cmd == "pairs":
        _all_pairs(paths)
        return 0
    if cmd == "find":
        p = counterparts(paths, argv[2:])
        print(p.summary())
        for line in manifest_section(p):
            print(line)
        return 0
    print("  pairs | find <파일…>")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
