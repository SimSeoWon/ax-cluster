"""시소러스 — 대괄호 토큰을 실제 클래스명으로 잇는다 (중 1.4).

## 무엇을 푸는가

사용자가 `[몬스터]` 라고 쓰면 검색은 **「몬스터」라는 한글 토큰**을 찾는다. 문서에 그
단어가 없으면 0건이다. 실제로 찾아야 할 것은 `AMonster` 인데 **문자가 하나도 겹치지 않아**
trigram 으로도, 다국어 임베딩으로도 이어지지 않는다. 별칭표가 그 다리다.

## [중요] 마스터는 사람에게 묻지 않는다 — 물을 재료를 돌려준다

마스터는 화면도 사람도 없는 인프라다(§2). 검색 도중 입력을 기다리면 서비스가 멈춘다.
그래서 역할을 가른다:

    이 모듈   →  "「몬스터」는 등록된 게 없다 + 후보 N개" 를 **구조화해 반환**
    작업 PC 의 Claude →  그걸 보고 사용자에게 묻는다 ("혹시 `AMonster` 를 말하는 건가요?")
    Claude   →  답을 받아 `register()` 를 부른다
    다음 검색 →  자동 확장. **영구히 남는다**

원본의 하드룰과도 맞는다 — *"silently auto-add 금지, 사용자가 명시 선언한 것만"*.
묻고 나서 등록하므로 그 원칙을 지킨다.

## 후보는 실측에서 만든다

백지로 "어느 클래스인가요?" 라고 묻는 것은 나쁘다. 사용자가 **고르게** 한다:

1. **클래스 그래프**(중 1.1, tree-sitter 실측 1,806개) — 이름에 그 말이 들어가는 클래스
2. **검색 상위 문서의 `related_classes`** — 합성기가 협력 관계로 지목한 것
3. 둘 다 없으면 후보 없이 "모른다" 고 정직하게 말한다 (지어내지 않는다)

## [중요] 등록은 병합이다 — 덮어쓰면 기존 별칭이 사라진다

원본 배포 규약이 **실제 함정으로 기록**해 뒀다: `edit_ontology_item(objects, {"aliases": […]})`
는 top-level 얕은 덮어쓰기라 **기존 별칭 전체가 날아간다**(Phase η.11 에서 발견). 그래서
여기서는 항상 **읽어서 합친다.** 이미 있으면 `noop` 으로 조용히 넘어간다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import ProjectPaths

# object yaml 의 `aliases:` 블록. PyYAML 없이 읽는다 — 원본도 수제 리더를 쓴다
# (`ontology_md_parse.py`), 프론트매터 생성 쪽과 짝이 맞춰져 있어서다.
_ALIASES_BLOCK = re.compile(r"^aliases:\s*\n((?:\s*-\s*.+\n?)*)", re.MULTILINE)
_ALIASES_INLINE = re.compile(r"^aliases:\s*\[(.*?)\]\s*$", re.MULTILINE)
_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


# [중요] **규약: 대괄호는 클래스에만 쓴다** (사용자 확정 2026-08-08).
#
# 실측에서 이 규약이 필요해진 이유: `[완료]`·`[연출]` 처럼 **상태·개념**에 대괄호를 쓰면
# 대응 클래스가 없는데도 후보 생성기가 어휘상 가까운 무관한 클래스(`FNMLocalization` 등)를
# 내민다. 규약이 그 입구를 막는다 — 클래스가 아니면 대괄호를 쓰지 않는다.
#
# 이 파일은 **규약을 어겼을 때의 안전망**이다. 사람은 습관으로 실수하고, 기록해 두지 않으면
# 같은 말을 매번 다시 묻게 되어 사용자가 기능을 꺼 버린다. 온톨로지 yaml 이 아니라 별도
# 파일에 두는 이유는 클래스의 속성이 아니라 **어휘 판단**이라서다.
IGNORE_FILE = "_thesaurus_ignore.txt"

# [중요] **온톨로지 밖 클래스의 별칭을 담는 곳.** 실측(2026-08-08): 클래스는 1,806개인데
# 온톨로지 object yaml 은 **7 도메인 112개뿐**이다. 원본은 별칭을 object yaml 에 넣지만
# 그건 온톨로지가 코드베이스를 덮은 환경의 전제다 — 우리는 아직 6% 만 덮었고, 그래서
# `add_alias` 가 `not_found` 로 실패해 **루프가 닫히지 않았다.**
#
# 그래서 폴백 저장소를 둔다. 우선순위는 **object yaml 이 먼저** — 그게 원본과 호환되는
# 정본이고, `--export-state` 로 오갈 때 함께 실린다. 이 파일은 온톨로지가 자랄 때까지의
# 임시 거처이며, 해당 클래스의 yaml 이 생기면 그때 옮기면 된다.
SIDE_FILE = "_thesaurus.tsv"          # <클래스><탭><별칭> 한 줄에 하나. 사람이 읽고 고칠 수 있게


def _ignore_path(paths: ProjectPaths) -> Path:
    return paths.ontology / IGNORE_FILE


def load_ignored(paths: ProjectPaths) -> set[str]:
    f = _ignore_path(paths)
    if not f.is_file():
        return set()
    try:
        return {ln.strip().casefold() for ln in f.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")}
    except OSError:
        return set()


def ignore(paths: ProjectPaths, term: str) -> str:
    """`이건 클래스가 아니다` 를 기억한다. 다음부터 묻지 않는다."""
    term = (term or "").strip()
    if not term:
        return "not_found"
    known = load_ignored(paths)
    if term.casefold() in known:
        return "noop"
    f = _ignore_path(paths)
    f.parent.mkdir(parents=True, exist_ok=True)
    header = "" if f.is_file() else "# 클래스가 아닌 표현 — 시소러스가 다시 묻지 않는다\n"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(header + term + "\n")
    return "added"


@dataclass
class Alias:
    term: str
    class_name: str
    domain: str
    path: Path


@dataclass
class Candidate:
    class_name: str
    why: str                     # 왜 후보인지 — 사용자가 판단할 근거
    file: str = ""


@dataclass
class Unresolved:
    term: str
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def question(self) -> str:
        """작업 PC 의 Claude 가 사용자에게 던질 문장. **후보가 없으면 그렇다고 말한다.**"""
        if not self.candidates:
            return (f"`[{self.term}]` 은 시소러스에 등록된 것이 없고 **후보도 찾지 못했다.** "
                    f"어느 클래스를 말하는지 알려주면 등록한다. "
                    f"(클래스가 아니라면 대괄호를 쓰지 않는 것이 규약이다)")
        top = " · ".join(f"`{c.class_name}`({c.why})" for c in self.candidates[:5])
        return (f"`[{self.term}]` 은 아직 등록된 것이 없다. 혹시 이 중 하나인가? — {top}. "
                f"맞으면 등록해 두면 다음부터 자동으로 확장된다. "
                f"클래스가 아니면 그렇다고 답해 달라 — **대괄호는 클래스에만 쓴다**.")


@dataclass
class Resolution:
    known: dict[str, str] = field(default_factory=dict)       # term → class_name
    unresolved: list[Unresolved] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)          # 클래스가 아니라고 확인된 말

    @property
    def needs_user(self) -> bool:
        return bool(self.unresolved)

    @property
    def expansion(self) -> list[str]:
        """질의에 덧붙일 토큰 — 아는 것만."""
        return sorted(set(self.known.values()))

    @property
    def summary(self) -> str:
        s = f"등록됨 {len(self.known)} · 미등록 {len(self.unresolved)}"
        if self.ignored:
            s += f" · 클래스 아님 {len(self.ignored)}"
        if self.unresolved:
            s += f" ({', '.join(u.term for u in self.unresolved[:5])})"
        return s


def _parse_aliases(text: str) -> list[str]:
    m = _ALIASES_INLINE.search(text)
    if m:
        return [x.strip().strip("\"'") for x in m.group(1).split(",") if x.strip()]
    m = _ALIASES_BLOCK.search(text)
    if m:
        return [re.sub(r"^\s*-\s*", "", ln).strip().strip("\"'")
                for ln in m.group(1).splitlines() if ln.strip()]
    return []


def object_files(paths: ProjectPaths):
    """도메인 패키지의 object yaml 들. `L{1,2,3}/objects/<Class>.yaml`."""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return
    for f in sorted(root.glob("*/L*/objects/*.yaml")):
        yield f


def _side_path(paths: ProjectPaths) -> Path:
    return paths.ontology / SIDE_FILE


def load_side(paths: ProjectPaths) -> dict[str, Alias]:
    """폴백 저장소. `<클래스>\t<별칭>` 한 줄에 하나."""
    f = _side_path(paths)
    out: dict[str, Alias] = {}
    if not f.is_file():
        return out
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip() or ln.startswith("#") or "\t" not in ln:
            continue
        cls, term = ln.split("\t", 1)
        cls, term = cls.strip(), term.strip()
        if cls and term:
            out[term.casefold()] = Alias(term, cls, "", f)
    return out


def load(paths: ProjectPaths) -> dict[str, Alias]:
    """별칭표. **casefold 로 찾는다** — 사용자가 대소문자를 맞춰 줄 이유가 없다.

    폴백 저장소를 먼저 깔고 object yaml 로 덮는다 — **yaml 이 정본**이다.
    """
    table: dict[str, Alias] = dict(load_side(paths))
    for f in object_files(paths):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _NAME_RE.search(text)
        cls = m.group(1) if m else f.stem
        domain = f.parts[-4] if len(f.parts) >= 4 else ""
        for term in _parse_aliases(text):
            if term:
                table[term.casefold()] = Alias(term, cls, domain, f)
    return table


def candidates_for(paths: ProjectPaths, term: str, *, searcher=None,
                   limit: int = 5) -> list[Candidate]:
    """후보를 실측에서 만든다. **지어내지 않는다** — 없으면 빈 목록이다."""
    out: list[Candidate] = []
    seen: set[str] = set()

    # ① 클래스 그래프 — 이름에 그 말이 들어가는 클래스 (영문 별칭·부분 일치에 강하다)
    try:
        from ..graph import db as gdb
        if gdb.exists(paths):
            conn = gdb.connect(paths)
            try:
                rows = conn.execute(
                    "SELECT name, file FROM classes WHERE name LIKE ? COLLATE NOCASE "
                    "ORDER BY LENGTH(name) LIMIT ?", (f"%{term}%", limit)).fetchall()
            finally:
                conn.close()
            for r in rows:
                if r["name"] not in seen:
                    seen.add(r["name"])
                    out.append(Candidate(r["name"], "클래스명 일치", r["file"]))
    except Exception:                                   # noqa: BLE001
        pass

    # ② 검색 상위 문서가 지목한 협력 클래스 — 한글 별칭은 대개 여기서 잡힌다
    if searcher is not None and len(out) < limit:
        try:
            for hit in searcher.search(term, limit=3):
                rc = (hit.meta or {}).get("related_classes") or ""
                for name in [x.strip() for x in str(rc).split(",") if x.strip()]:
                    if name not in seen and len(out) < limit:
                        seen.add(name)
                        out.append(Candidate(name, "관련 문서가 지목", hit.file_id))
        except Exception:                               # noqa: BLE001
            pass
    return out[:limit]


def resolve(paths: ProjectPaths, terms: list[str], *, searcher=None) -> Resolution:
    """대괄호 토큰들 → 아는 것/모르는 것. 모르는 것에는 **후보를 붙인다.**"""
    table = load(paths)
    ignored = load_ignored(paths)
    res = Resolution()
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        hit = table.get(t.casefold())
        if hit:
            res.known[t] = hit.class_name
        elif t.casefold() in ignored:
            # [중요] 클래스가 아니라고 사용자가 이미 말했다 — 다시 묻지 않는다.
            res.ignored.append(t)
        else:
            res.unresolved.append(
                Unresolved(t, candidates_for(paths, t, searcher=searcher)))
    return res


def _class_exists(paths: ProjectPaths, class_name: str) -> bool:
    """클래스 그래프에 실재하는가. **오타를 영구 저장하지 않기 위한 게이트.**"""
    try:
        from ..graph import db as gdb
        if not gdb.exists(paths):
            return True          # 그래프가 없으면 판정할 수 없다 — 막지 않는다
        conn = gdb.connect(paths)
        try:
            return conn.execute("SELECT 1 FROM classes WHERE name = ? LIMIT 1",
                                (class_name,)).fetchone() is not None
        finally:
            conn.close()
    except Exception:                                   # noqa: BLE001
        return True


def register(paths: ProjectPaths, class_name: str, term: str) -> str:
    """별칭 하나를 등록한다. **읽어서 합친다 — 덮어쓰지 않는다.**

    반환: `added` · `noop`(이미 있음) · `not_found`(그 클래스의 yaml 이 없다)

    [중요] 덮어쓰기 금지가 이 함수의 존재 이유다. 원본이 top-level 얕은 덮어쓰기로 **기존
    별칭 전체를 날린 사고**를 기록해 뒀다.
    """
    term = (term or "").strip()
    if not term or not class_name:
        return "not_found"
    target = None
    for f in object_files(paths):
        m = _NAME_RE.search(f.read_text(encoding="utf-8", errors="replace"))
        if (m.group(1) if m else f.stem) == class_name:
            target = f
            break
    if target is None:
        # [중요] 온톨로지에 그 클래스의 yaml 이 없다. **거부하지 않고 폴백에 적는다** —
        # 여기서 막으면 클래스의 94% 에 대해 별칭을 못 만들고 루프가 닫히지 않는다.
        # 다만 그 클래스가 **실재하는지**는 확인한다. 오타를 영구 저장하지 않기 위해서다.
        if not _class_exists(paths, class_name):
            return "not_found"
        f = _side_path(paths)
        f.parent.mkdir(parents=True, exist_ok=True)
        header = "" if f.is_file() else "# <클래스>\t<별칭> — 온톨로지 yaml 이 없는 클래스용\n"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(header + f"{class_name}\t{term}\n")
        return "added_side"

    text = target.read_text(encoding="utf-8", errors="replace")
    existing = _parse_aliases(text)
    if any(e.casefold() == term.casefold() for e in existing):
        return "noop"
    merged = existing + [term]
    block = "aliases:\n" + "".join(f"  - {a}\n" for a in merged)
    if _ALIASES_INLINE.search(text):
        text = _ALIASES_INLINE.sub(block.rstrip("\n"), text, count=1)
    elif _ALIASES_BLOCK.search(text):
        text = _ALIASES_BLOCK.sub(block, text, count=1)
    else:
        text = text.rstrip("\n") + "\n" + block
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)          # 원자적 — 반쯤 쓰인 yaml 을 합성기가 읽지 않게
    return "added"
