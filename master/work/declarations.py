"""생성 프롬프트에 **선언부를 싣는다** (레드마인 #26).

## 왜 — 규범으로는 안 잡히는 실패가 실측됐다

같은 지시·같은 모델로 매니페스트만 바꿔 재봤을 때(리포트 11 §14):

    규범 없음  →  **없는 멤버**를 지어냈다
    규범 있음  →  실재 멤버 4/4 + invariant 준수 … **그런데 철자가 한 글자 틀렸다**
                  `CurrentStep`(실제 `Step`) · `EMissionTaskExecutorState`(실제 `EMissionExecutorState`)

규범은 *무엇을 지킬지*를 준다. **정확한 철자는 헤더에만 있다.** 그래서 헤더 선언을 프롬프트에
직접 싣는다 — 모델이 기억에서 꺼내지 않고 **눈앞의 텍스트를 베끼게** 한다.

[중요] **워커의 Claude 에게는 이 문제가 없다** — 소스를 직접 읽기 때문이다(실측: 첫 파견에서
실재 멤버만 썼다). 이 모듈이 필요한 자리는 **로컬 LLM 에 본문 생성을 위임할 때**다.

## [중요] 못 찾은 것을 조용히 빼지 않는다

헤더를 못 찾은 클래스를 말없이 생략하면 모델은 *"선언부에 없으니 내가 지어내도 되겠다"* 로
읽는다 — 고치려던 실패가 그대로 돌아온다. 그래서 **없으면 없다고 프롬프트에 쓴다.**

## 예산

실측(리포트 11 §14): 규범까지 실은 프롬프트가 **2,824 tok**, `num_ctx` 8192 에서 출력 여유가
**5,368 tok** 남았다. 그 여유 안에서 쓴다 — 2.79~2.85자/tok 이므로 6,000자면 ~2,100 tok 이다.
"""
from __future__ import annotations

import ast
import pathlib

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

PER_CLASS = 1500        # 클래스당 헤더 발췌
TOTAL = 6000            # 전체 상한 (≈2,100 tok — 실측 여유 5,368 안)


class DeclError(RuntimeError):
    """선언부를 모을 수 없다. [중요] 삼키면 grounding 없이 돈 것이 통과로 보인다."""


@dataclass
class Declarations:
    blocks: list = field(default_factory=list)      # [(클래스, 파일, 발췌)]
    missing: list = field(default_factory=list)     # 헤더를 못 찾은 클래스
    truncated: list = field(default_factory=list)   # 예산에 잘린 클래스
    dropped: list = field(default_factory=list)     # 예산이 다 차 아예 못 실은 클래스

    @property
    def ok(self) -> bool:
        return bool(self.blocks)

    @property
    def complete(self) -> bool:
        """층2에서는 발췌의 존재와 전체 grounding의 완전성을 구분한다."""
        return self.ok and not (self.missing or self.truncated or self.dropped)

    @property
    def summary(self) -> str:
        s = f"선언부 {len(self.blocks)}개"
        for label, xs in (("헤더 없음", self.missing), ("잘림", self.truncated),
                          ("예산 초과", self.dropped)):
            if xs:
                s += f" · [중요] {label} {len(xs)}"
        return s

    def render(self, *, for_verification: bool = False) -> str:
        """프롬프트에 넣을 블록. [중요] **결손을 본문에 적는다.**"""
        if not self.blocks and not (self.missing or self.dropped):
            return ""
        out = ["=== DECLARATIONS — COPY THESE NAMES EXACTLY ===",
               "These are the real declarations from this codebase. Member, method and enum "
               "names below are the ONLY spellings that compile.",
               "[중요] If a name you need is not here, do NOT invent it — say so in a comment "
               "instead of guessing.", ""]
        if for_verification:
            out[1:3] = [
                "Frozen declarations are authoritative for the listed modules/types only.",
                "Compare their signatures and enum members. Unlisted external modules/types "
                "are not evidence of an error. Function bodies were deliberately omitted.",
            ]
        for cls, file, text in self.blocks:
            out += [f"--- {cls}  ({file}) ---", text.strip(), ""]
        # [중요] 빠진 것을 숨기지 않는다 — 숨기면 모델이 "없으니 지어내도 된다" 로 읽는다
        for label, xs in (("NOT AVAILABLE (header not found)", self.missing),
                          ("TRUNCATED (excerpt cut by budget)", self.truncated),
                          ("OMITTED (budget exhausted)", self.dropped)):
            if xs:
                out.append(f"[중요] {label}: {', '.join(xs)}")
        out.append("=== END DECLARATIONS ===")
        return "\n".join(out)


def _files_for(paths: ProjectPaths, classes: list) -> dict:
    """`{클래스: 헤더 경로}`. 클래스 그래프가 근거다 — **소스 실측**이라 가장 신선하다."""
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return {}
    conn = gdb.connect(paths)
    try:
        want = {c for c in classes if c}
        return {r["name"]: (r["file"] or "") for r in conn.execute("SELECT name, file FROM classes")
                if r["name"] in want}
    finally:
        conn.close()


HEADER_SUFFIXES = (".h", ".hpp")


def _mirror_git(paths, *args, check: bool = True) -> str:
    """미러에서 git 한 번. [주의] 실패를 조용히 빈 문자열로 접지 않는다 — 호출부가 사유를 싣는다."""
    import subprocess
    r = subprocess.run(["git", "-C", str(paths.repo), *args],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        if check:
            raise DeclError(f"git {' '.join(args)} 실패 (rc={r.returncode}): "
                            f"{(r.stderr or b'').decode('utf-8', 'replace')[:200]}")
        return ""
    from ..source_text import decode
    return decode(r.stdout).text


def work_headers(paths, commit: str, *, main_branch: str = "main") -> list:
    """`commit`(작업 브랜치 base)이 `main` 대비 **추가·수정한 헤더 경로**.

    [중요] 이것이 그 work 의 **동결 계약 전체**다 — 골조가 한 커밋으로 올린 것이고, 조각들이
    서로를 참조할 때 필요한 선언이 다 여기 있다. 클래스 그래프로는 얻을 수 없다(신규 클래스는
    그래프에 없고, 색인은 분산 작업 중 의도적으로 멈춘다 — 실측 2026-09-01).
    """
    out = _mirror_git(paths, "diff", "--name-only", f"{main_branch}...{commit}")
    return sorted({ln.strip() for ln in out.splitlines()
                   if ln.strip().lower().endswith(HEADER_SUFFIXES)})


def from_commit(paths: ProjectPaths, commit: str, *, main_branch: str = "main",
                per_class=PER_CLASS, total=TOTAL,
                kind: str = "unreal", work_exts=None, target_files=None) -> Declarations:
    """그 work 의 동결 계약 헤더를 **base 커밋에서** 읽는다. **읽기 전용.**

    [중요] `per_class`/`total` 이 `None` 이면 **글자 예산이 없다** (`#780`, 2026-10-10). 예산은
    로컬 LLM `num_ctx` 를 위한 것이고(모듈 머리 §예산), 클라우드 판정에는 근거가 없다 —
    실측: agy 는 `--add-dir` 1M자 파일의 중간·끝 표지를 정확히 읽었다(16K~1M 5/5).

    ## 왜 커밋에서 읽나 — 실패가 두 겹이었다 (실측 2026-09-01)

        `_files_for`      → 클래스 그래프 `classes` 표.  NS 61개 중 `NSInteract%` **0개**
        `excerpt_header`  → `paths.repo / file` = 미러 워킹트리 = `main`.  파일 자체가 없다

    그래프를 채워도 두 번째가 남고, 색인은 분산 작업 중 멈춘다. 선언부는 **있었는데 안 봤다** —
    `e3aa6ab7:…/NSInteractableComponent.h` 에 `CanBeInteractedBy` 가 그대로 있었다. 그래서
    층2 가 `[주의] 선언부 없이 돌렸다` 로 돌았고, 그것은 실측 4/5 가 「없는 열거값」을 놓친 조건이다.

    [주의] 실패는 예외로 낸다 — 호출자가 `l2_grounded=False` 와 **사유**를 싣는다.
    """
    from ..source_text import decode as _dec                      # noqa: F401  (의도 명시)

    d = Declarations()
    if not (commit or "").strip():
        raise DeclError("기준 커밋이 비었다 — 무엇의 선언부인지 모른다")
    ensure_commit(paths, commit)
    used = 0
    selection = _work_declaration_selection(paths, commit, main_branch=main_branch, kind=kind,
                                            work_exts=work_exts, target_files=target_files)
    for rel in sorted(selection):
        if total is not None and used >= total:
            d.dropped.append(rel)                     # [중요] 조용히 빼지 않는다
            continue
        caps = [c for c in (per_class, None if total is None else total - used) if c is not None]
        room = min(caps) if caps else None
        text = _mirror_git(paths, "show", f"{commit}:{rel}", check=False)
        if not (text or "").strip():
            d.missing.append(rel)
            continue
        want = selection[rel]
        if rel.lower().endswith(".py"):
            if want is None:
                text = python_declarations(text, filename=rel)
            else:
                # 🔴 import 로만 끌려온 모듈은 **실제로 가져다 쓴 이름만** 싣는다 (#780).
                source = text
                text, miss = python_named_declarations(
                    source, want["names"] | want["attrs"], filename=rel)
                # `from X import a` 의 a 가 X 에 없으면 결손으로 적는다 — 조용히 빼지 않는다.
                d.missing.extend(f"{rel}:{n}" for n in miss if n in want["names"])
                # `X.attr` 사용이 선언에서 안 보이면(동적 속성·하위 모듈) 모듈 전체로 되돌린다.
                if any(n not in want["names"] for n in miss):
                    text = python_declarations(source, filename=rel)
        if room is not None and len(text) > room:
            text = text[:room]
            d.truncated.append(rel)
        # [주의] 「클래스」 칸에 **파일 stem** 을 쓴다 — 이 경로는 클래스 이름을 모른다(파싱하지
        #    않는다). 프롬프트에는 경로가 같이 찍히므로 모델이 무엇인지 알 수 있다.
        d.blocks.append((pathlib.PurePosixPath(rel).stem, rel, text.rstrip()))
        used += len(text)
    return d


def _parse_python(source: str, filename: str):
    try:
        return ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise DeclError(f"Python 기준 선언 파싱 실패: {filename}:{e.lineno}: {e.msg}") from e


def _clone(node):
    """노드를 `_fields`·`_attributes` 만 따라 복제한다 (`#834`).

    🔴 `copy.deepcopy` 를 쓰지 않는다. CPython 의 `ast.Load`/`ast.Store` 는 프로세스 전역 싱글턴이고,
    층1 이 같은 프로세스에서 pyflakes 를 돌리면 그 싱글턴에도 `_pyflakes_parent` 를 붙인다. deepcopy 는
    그 속성을 따라 **다른 조각의 트리 전체**를 복사하다가, 병렬 조각의 pyflakes 가 노드에 속성을 붙이는
    순간 `dictionary changed size during iteration` 으로 죽었다(실측 2026-10-18, #831 work).
    ctx 는 복사하지 않고 그대로 공유한다 — `ast.parse` 가 하는 것과 같다.
    """
    if isinstance(node, ast.expr_context):
        return node
    if isinstance(node, ast.AST):
        new = type(node)()
        for name in node._fields:
            if hasattr(node, name):
                setattr(new, name, _clone(getattr(node, name)))
        for name in node._attributes:
            if hasattr(node, name):
                setattr(new, name, getattr(node, name))
        return new
    if isinstance(node, list):
        return [_clone(item) for item in node]
    return node


def _declare(nodes, *, in_class: bool = False, keep_assign: bool = False) -> list:
    """선언 노드만 남긴다. `keep_assign` 은 이름으로 고른 대입(소문자 포함)을 살린다."""
    out = []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signature = _clone(node)
            signature.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
            out.append(signature)
        elif isinstance(node, ast.ClassDef):
            cls = _clone(node)
            fields = {}
            for method in node.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if any((isinstance(dec, ast.Name) and dec.id == "staticmethod")
                       or (isinstance(dec, ast.Attribute) and dec.attr == "staticmethod")
                       for dec in method.decorator_list):
                    continue
                args = method.args.posonlyargs + method.args.args
                if not args or args[0].arg not in ("self", "cls"):
                    continue
                receiver = args[0].arg
                for assignment in ast.walk(method):
                    if isinstance(assignment, ast.Assign):
                        targets = assignment.targets
                    elif isinstance(assignment, ast.AnnAssign):
                        targets = [assignment.target]
                    else:
                        continue
                    for target in targets:
                        if not (isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == receiver):
                            continue
                        name = ast.Name(id=target.attr, ctx=ast.Store())
                        if isinstance(assignment, ast.AnnAssign):
                            fields[target.attr] = ast.AnnAssign(
                                target=name, annotation=assignment.annotation,
                                value=None, simple=1)
                        elif target.attr not in fields:
                            fields[target.attr] = ast.Assign(
                                targets=[name], value=ast.Constant(value=Ellipsis))
            cls.body = list(fields.values()) + _declare(node.body, in_class=True)
            cls.body = cls.body or [ast.Pass()]
            out.append(cls)
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.AnnAssign)):
            out.append(node)
        elif isinstance(node, ast.Assign):
            names = [n.id for target in node.targets for n in ast.walk(target)
                     if isinstance(n, ast.Name)]
            if keep_assign or in_class or any(name.isupper() for name in names):
                out.append(node)
    return out


def python_declarations(source: str, *, filename: str = "<module>") -> str:
    """Python AST의 선언 계약만 싣는다. 함수 본문은 구현이므로 생략한다."""
    tree = _parse_python(source, filename)
    tree.body = _declare(tree.body)
    # 선언이 없는 유틸리티 모듈도 조회했다는 근거를 유지한다.
    return ast.unparse(ast.fix_missing_locations(tree)) or "# No module-level declarations"


def _bound_names(node) -> set:
    """최상위 문장이 모듈 이름공간에 묶는 이름."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {n.id for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    if isinstance(node, ast.AnnAssign):
        return {node.target.id} if isinstance(node.target, ast.Name) else set()
    if isinstance(node, ast.Import):
        return {a.asname or a.name.split(".")[0] for a in node.names}
    if isinstance(node, ast.ImportFrom):
        return {a.asname or a.name for a in node.names if a.name != "*"}
    return set()


def _module_statements(nodes):
    """최상위 문장과 최상위 `if`/`try` 안의 문장 (`TYPE_CHECKING`·폴백 import 자리)."""
    for node in nodes:
        if isinstance(node, ast.If):
            yield from _module_statements(node.body + node.orelse)
        elif isinstance(node, ast.Try):
            yield from _module_statements(node.body + node.orelse + node.finalbody
                                          + [s for h in node.handlers for s in h.body])
        else:
            yield node


def python_named_declarations(source: str, names, *,
                              filename: str = "<module>") -> tuple[str, list]:
    """모듈에서 **이름으로 고른** 선언만 싣는다 (#780). `(텍스트, 못 찾은 이름)`.

    `from X import a` 의 `a` 가 X 에서 다시 import 된 것(재수출)이면 그 import 줄을 싣는다 —
    정의가 다른 곳에 있다는 근거이고 결손이 아니다. `from Y import *` 가 있으면 못 찾은 이름은
    그 줄로 넘어온 것일 수 있어 결손으로 세지 않고 그 줄과 이름을 함께 적는다.
    """
    tree = _parse_python(source, filename)
    want = {n for n in names if n}
    chosen, found, stars = [], set(), []
    for node in _module_statements(tree.body):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            stars.append(node)
        bound = _bound_names(node) & want
        if bound:
            chosen.append(node)
            found |= bound
    missing = sorted(want - found)
    note = (f"# imported names only: {', '.join(sorted(want))}" if want
            else "# imported as a module; no attributes referenced")
    if missing and stars:
        chosen += stars
        note += f"\n# not defined here, possibly via star import: {', '.join(missing)}"
        missing = []
    body = _declare(chosen, keep_assign=True)
    text = ast.unparse(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])))
    return (note + ("\n" + text if text else "")), missing


def _attribute_uses(tree, bound: str):
    """`bound.attr` 로만 쓰였으면 속성 이름 집합, 다른 식으로 쓰였으면 `None`(전체)."""
    attrs, consumed = set(), set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == bound):
            attrs.add(node.attr)
            consumed.add(id(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == bound and id(node) not in consumed:
            return None                       # 통째로 넘기거나 재바인딩 — 좁히지 않는다
    return attrs


def _module_file(module: str, available: set):
    for dependency in (module + ".py", module + "/__init__.py"):
        if dependency in available:
            return dependency
    return None


def _work_declaration_selection(paths, commit: str, *, main_branch: str = "main",
                                kind: str = "unreal", work_exts=None,
                                target_files=None) -> dict:
    """`{경로: None(모듈 전체) | {"names": 이름, "attrs": 속성}}`.

    🔴 import 확장은 **이 조각의 대상 파일에서만** 시작한다 (#780, 실측 2026-10-10). 종전에는
    골조가 바꾼 모든 파일의 import 를 따라가 다른 조각이 쓰는 모듈(`client_mcp.py` 22,332자)까지
    실었고, 그것이 잘려 모든 조각이 `grounding_incomplete` 로 막혔다. 골조가 바꾼 파일 자체는
    동결 계약이므로 그대로 싣는다.
    """
    suffixes = HEADER_SUFFIXES + ((".py",) if kind == "code" else ())
    if work_exts is not None:
        allowed = {str(ext).lower() for ext in work_exts}
        suffixes = tuple(ext for ext in suffixes if ext in allowed)
    changed = _mirror_git(paths, "diff", "--name-only", f"{main_branch}...{commit}")
    selected: dict = {rel.strip(): None for rel in changed.splitlines()
                      if rel.strip().lower().endswith(suffixes)} if suffixes else {}
    if not target_files:
        return selected
    available = set(_mirror_git(paths, "ls-tree", "-r", "--name-only", commit).splitlines())
    roots = []
    for target in target_files:
        rel = str(target).replace("\\", "/")
        if suffixes and rel.lower().endswith(suffixes):
            selected[rel] = None
            roots.append(rel)
        elif pathlib.PurePosixPath(rel).suffix.lower() in (".cpp", ".cc", ".cxx", ".c"):
            for ext in HEADER_SUFFIXES:
                sibling = str(pathlib.PurePosixPath(rel).with_suffix(ext))
                if ext in suffixes and sibling in available:
                    selected[sibling] = None
    if ".py" not in suffixes:
        return selected

    def want(dependency, *, names=(), attrs=None):
        """import 로만 들어온 모듈의 요구를 합친다. `attrs=None` 은 모듈 전체."""
        if dependency in selected and selected[dependency] is None:
            return
        if attrs is None and not names:
            selected[dependency] = None
            return
        slot = selected.setdefault(dependency, {"names": set(), "attrs": set()})
        slot["names"] |= set(names)
        slot["attrs"] |= set(attrs or ())

    # 대상이 참조하는 기존 모듈도 동결 커밋에서 읽는다. 외부 패키지는 tree에 없으므로 제외.
    for rel in roots:
        if not rel.endswith(".py") or rel not in available:
            continue
        tree = _parse_python(_mirror_git(paths, "show", f"{commit}:{rel}"), rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependency = _module_file(alias.name.replace(".", "/"), available)
                    if not dependency:
                        continue
                    if alias.asname or "." not in alias.name:
                        want(dependency, attrs=_attribute_uses(tree, alias.asname or alias.name))
                    else:
                        want(dependency)              # `import a.b` — 좁히지 않는다
            elif isinstance(node, ast.ImportFrom):
                prefix = (node.module or "").replace(".", "/")
                if node.level:
                    parent = pathlib.PurePosixPath(rel).parent
                    for _ in range(node.level - 1):
                        parent = parent.parent
                    prefix = str(parent / prefix).strip("./")
                package = _module_file(prefix, available) if prefix else None
                for alias in node.names:
                    if alias.name == "*":
                        if package:
                            want(package)
                        continue
                    submodule = _module_file(f"{prefix}/{alias.name}".strip("/"), available)
                    if submodule:                     # `from pkg import module`
                        want(submodule,
                             attrs=_attribute_uses(tree, alias.asname or alias.name))
                    elif package:                     # `from X import a` — a 의 선언만
                        want(package, names=[alias.name])
    return selected


def work_declaration_files(paths, commit: str, *, main_branch: str = "main",
                           kind: str = "unreal", work_exts=None,
                           target_files=None) -> list[str]:
    """동결 변경 선언과 검증 대상의 기준 선언. 기본은 기존 헤더-only 계약."""
    return sorted(_work_declaration_selection(paths, commit, main_branch=main_branch,
                                              kind=kind, work_exts=work_exts,
                                              target_files=target_files))


def ensure_commit(paths: ProjectPaths, commit: str, *, remote: str = "gitea-write") -> None:
    """미러에 그 커밋이 없으면 fetch 한다. 선례: `carry.py` 의 base fetch (`#341`).

    [주의] **이미 있으면 건드리지 않는다** — 네트워크 실패를 치명으로 만들지 않기 위해서다.
    """
    if _mirror_git(paths, "cat-file", "-t", commit, check=False).strip() == "commit":
        return
    _mirror_git(paths, "fetch", remote, commit)
    if _mirror_git(paths, "cat-file", "-t", commit, check=False).strip() != "commit":
        raise DeclError(f"기준 커밋을 미러로 가져오지 못했다 — {commit} ({remote})")


def collect(paths: ProjectPaths, classes: list, *, per_class: int = PER_CLASS,
            total: int = TOTAL) -> Declarations:
    """대상 클래스들의 헤더 선언을 모은다. **읽기 전용.**"""
    from ..ontology import contexts

    d = Declarations()
    names = [c for c in (classes or []) if c and c.strip()]
    if not names:
        return d
    files = _files_for(paths, names)
    used = 0
    for cls in names:
        f = files.get(cls, "")
        if not f:
            d.missing.append(cls)
            continue
        if used >= total:
            d.dropped.append(cls)                   # [중요] 조용히 빼지 않는다
            continue
        room = min(per_class, total - used)
        text = contexts.excerpt_header(paths, f, limit=room)
        if not (text or "").strip():
            d.missing.append(cls)
            continue
        if len(text) >= room:
            d.truncated.append(cls)
        d.blocks.append((cls, f, text))
        used += len(text)
    return d
