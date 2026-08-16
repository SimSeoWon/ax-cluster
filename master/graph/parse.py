"""C++ 파싱 — tree-sitter-cpp (소 1.1.1).

UE 매크로 전처리 + 클래스/구조체/메서드 선언 추출. **자기완결** — 이 모듈은 같은 패키지의
어떤 것도 import 하지 않는다(원본의 분리 의도를 유지한다).

원본: `AgentTest/watcher/class_graph_parse.py`. 파싱 로직은 **그대로** 옮겼다 — UE 매크로
정규식 5개, base clause 추출의 3분기(`type_identifier`/`template_type`/`qualified_identifier`),
메서드 dedupe 정책이 전부 회사 코드베이스에서 검증된 값이라 조정하지 않는다.

[중요] **바꾼 것 하나 — 없을 때 조용히 죽지 않는다.**

원본은 `TREE_SITTER_AVAILABLE=False` 면 `parse_file` 이 빈 리스트를 돌려주고, 호출자
`build_full` 도 로그 한 줄 남기고 `return` 한다. 그러면 **그래프가 0건인 것과 파서가 없는
것이 구분되지 않는다** — "돌았는데 결과 0" 이다. 여기서는 `require()` 가 예외를 던지고,
빈 리스트는 **정말로 클래스가 없을 때만** 나온다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import source_text

try:
    import tree_sitter_cpp
    from tree_sitter import Language, Parser
    _CPP_LANG = Language(tree_sitter_cpp.language())
    TREE_SITTER_AVAILABLE = True
    _IMPORT_ERROR = ""
except Exception as e:                                    # pragma: no cover - 설치 상태 의존
    TREE_SITTER_AVAILABLE = False
    _CPP_LANG = None
    _IMPORT_ERROR = f"{type(e).__name__}: {e}"


class ParserUnavailable(RuntimeError):
    """tree-sitter 가 없다. [중요] 이 예외를 삼키면 안 된다 — 빈 그래프로 보이게 된다."""


def require() -> None:
    """파서가 없으면 던진다. 그래프를 만드는 모든 진입점이 **먼저** 이걸 부른다."""
    if not TREE_SITTER_AVAILABLE:
        raise ParserUnavailable(
            "tree-sitter 미설치 — 클래스 그래프를 만들 수 없다. "
            f"`.venv/bin/pip install tree-sitter tree-sitter-cpp` ({_IMPORT_ERROR})"
        )


PARSE_EXTS = {".h", ".hpp", ".cpp", ".cc", ".cxx"}

# UE 매크로는 tree-sitter-cpp 의 파싱 컨텍스트를 깨뜨리므로 전처리에서 지운다.
_UE_API_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_API\b")
_UE_ATTR_RE = re.compile(
    r"\b(?:UCLASS|USTRUCT|UINTERFACE|UENUM|UPROPERTY|UFUNCTION|UPARAM|UMETA|UDELEGATE)\s*\([^)]*\)",
    re.DOTALL,
)
_GENERATED_RE = re.compile(
    r"\bGENERATED_(?:BODY|USTRUCT_BODY|UINTERFACE_BODY|IINTERFACE_BODY)\s*\(\s*\)"
)
_UE_PREFIX_RE = re.compile(r"^([AUFEST])([A-Z])")


def preprocess_ue_macros(src: str) -> str:
    src = _UE_API_RE.sub("", src)
    src = _UE_ATTR_RE.sub("", src)
    src = _GENERATED_RE.sub("", src)
    return src


def _extract_base_classes(base_clause, src: bytes) -> list[str]:
    """상속 목록. 템플릿 부모는 이름만, 한정 이름은 마지막 조각만 남긴다."""
    parents: list[str] = []
    for child in base_clause.children:
        if child.type == "type_identifier":
            parents.append(src[child.start_byte:child.end_byte].decode())
        elif child.type == "template_type":
            name_node = child.child_by_field_name("name")
            if name_node:
                parents.append(src[name_node.start_byte:name_node.end_byte].decode())
            else:
                for tc in child.children:
                    if tc.type == "type_identifier":
                        parents.append(src[tc.start_byte:tc.end_byte].decode())
                        break
        elif child.type == "qualified_identifier":
            text = src[child.start_byte:child.end_byte].decode()
            parents.append(text.rsplit("::", 1)[-1])
    return parents


# 메서드 소유권 추출 — 온톨로지 추출의 **오탐 교차검증용**(다른 상속 라인의 동명 메서드를
# 잘못 귀속하는 것을 막는다). SSOT 는 헤더 선언이다 — `.cpp` 의 `Class::Method` 정의부는
# 한정자가 이미 명시적이라 따로 뽑을 필요가 없다.
_METHOD_CONTAINER_TYPES = {"field_declaration", "declaration", "function_definition"}
_METHOD_NAME_NODE_TYPES = {"field_identifier", "identifier", "destructor_name", "operator_name"}


# [중요] 재귀를 여기서 멈춘다 — 아래 `_find_function_declarator` 주석 참조.
_NESTED_SCOPES = {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier"}


def _find_function_declarator(node, *, _top: bool = True):
    """포인터/참조/const 래핑을 관통해 첫 `function_declarator` 를 찾는다.

    [중요] **원본과 다른 유일한 지점이다 — 원본 버그를 고쳤다.**

    원본(`class_graph_parse.py:71`)은 자식 전체를 무제한 재귀한다. 그런데 중첩 클래스는
    바깥 클래스 본문의 `field_declaration` **안에** 들어 있다:

        field_declaration
          └ class_specifier (FInner)
              └ field_declaration_list
                  └ field_declaration → function_declarator (InnerOnly)   ← 여기까지 내려간다

    그래서 `_extract_methods_from_body` 가 "직계 자식만 훑는다" 고 해도 소용이 없고,
    **중첩 클래스의 메서드가 바깥 클래스 소유로 기록된다**(실측: `AMonster` 의 메서드
    목록에 `InnerOnly` 가 들어왔다). `methods` 테이블의 존재 이유가 **오탐 교차검증**인데
    그 표에 오탐이 섞이면 게이트가 반대로 작동한다.

    고침: 중첩 스코프를 만나면 내려가지 않는다. 중첩 클래스 자체는 `_walk_classes` 가
    별도 항목으로 잡으므로 **잃는 정보는 없다**(테스트가 둘 다 확인한다).
    """
    if node.type == "function_declarator":
        return node
    if not _top and node.type in _NESTED_SCOPES:
        return None
    for child in node.children:
        found = _find_function_declarator(child, _top=False)
        if found is not None:
            return found
    return None


def _method_name_from_declarator(declarator, src: bytes) -> str | None:
    for child in declarator.children:
        if child.type in _METHOD_NAME_NODE_TYPES:
            return src[child.start_byte:child.end_byte].decode()
    return None


def _extract_methods_from_body(body, src: bytes) -> list[dict]:
    """`field_declaration_list` 의 **직계 자식만** 스캔한다.

    중첩 클래스는 `_walk_classes` 재귀가 따로 처리하므로 여기서 재귀하면 이중 집계가 된다.
    멤버 변수는 `function_declarator` 가 없어 자연 제외. 오버로드는 **이름 레벨에서
    dedupe**(첫 등장 줄만 보관) — 시그니처 구분은 과설계다.
    """
    seen: dict[str, int] = {}
    for child in body.children:
        target = child
        if target.type == "template_declaration":
            inner = next((c for c in target.children if c.type in _METHOD_CONTAINER_TYPES), None)
            if inner is None:
                continue
            target = inner
        if target.type not in _METHOD_CONTAINER_TYPES:
            continue
        declarator = _find_function_declarator(target)
        if declarator is None:
            continue
        name = _method_name_from_declarator(declarator, src)
        if name and name not in seen:
            seen[name] = target.start_point[0] + 1
    return [{"name": n, "line": ln} for n, ln in sorted(seen.items())]


def _walk_classes(node, src: bytes, out: list) -> None:
    if node.type in ("class_specifier", "struct_specifier"):
        name_node = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        if name_node is not None and body is not None:
            name = src[name_node.start_byte:name_node.end_byte].decode()
            parents: list[str] = []
            for child in node.children:
                if child.type == "base_class_clause":
                    parents = _extract_base_classes(child, src)
                    break
            out.append({
                "name": name,
                "parents": parents,
                "line": node.start_point[0] + 1,
                "kind": "struct" if node.type == "struct_specifier" else "class",
                "methods": _extract_methods_from_body(body, src),
            })
    for child in node.children:
        _walk_classes(child, src, out)


def ue_prefix(class_name: str) -> str:
    """`AMonster` → `A`. UE 접두 규약(A/U/F/E/S/T)만 인정한다."""
    m = _UE_PREFIX_RE.match(class_name)
    return m.group(1) if m else ""


def parse_source(text: str) -> list[dict]:
    """문자열에서 클래스 선언 추출. 파일 없이 테스트할 수 있게 분리했다."""
    require()
    cleaned = preprocess_ue_macros(text).encode("utf-8")
    tree = Parser(_CPP_LANG).parse(cleaned)
    raw: list[dict] = []
    _walk_classes(tree.root_node, cleaned, raw)
    for r in raw:
        r["prefix"] = ue_prefix(r["name"])
    return raw


def parse_file(file_path: Path) -> tuple[list[dict], "source_text.Decoded | None"]:
    """단일 파일에서 클래스 선언 추출 + **어떤 인코딩으로 읽었는지**.

    확장자가 다르거나 읽기가 실패하면 빈 리스트다 — 한 파일이 깨졌다고 전체 스캔을
    멈추지 않는다. 호출자가 파일 수·클래스 수·인코딩 분포를 함께 보고하므로 결손이
    숫자에서 드러난다.

    [중요] **인코딩을 왜 돌려주나.** 저장소의 44%(실측 723/1,654)가 CP949 다. 상속 그래프는
    식별자가 ASCII 라 영향이 없지만(실측 확인), **같은 파일을 읽는 컨텍스트 MD 합성은
    한글 주석이 핵심 신호**라 치명적이다. 여기서 분포를 세어 두면 그 위험이 보인다.
    """
    require()
    if file_path.suffix.lower() not in PARSE_EXTS:
        return [], None
    d = source_text.read(file_path)
    if d is None:
        return [], None
    return parse_source(d.text), d
