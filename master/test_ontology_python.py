"""`#850` 온톨로지 합성의 파이썬 대응 — 발췌 · 이름 분리 · 프롬프트 언어 블록 (LLM 0).

    .venv/bin/python -B master/test_ontology_python.py

[중요] **실물로 잰다.** 발췌 대상은 이 저장소의 실제 `.py` 다(`master/ontology/synth.py` 의
`DomainResult` — 재현 당시 선언 1,199자 · 본문 0자 · 클래스가 발췌에 없었다).

[중요] **unreal 의 C++ 조각은 종전과 바이트 단위로 같아야 한다.** 아래 해시는 변경 직전
`32de69b` 의 문자열·출력에서 잰 고정본이다 — 규칙 문구를 고치면 여기가 먼저 깨진다.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths                  # noqa: E402
from master.ontology import contexts as C, descriptions as dm, parse, prompt as P, synth  # noqa: E402
from master.ontology.contexts import ClassContext, DomainContexts     # noqa: E402

PASS = FAIL = 0

# 변경 직전(`32de69b`)에 잰 sha256 — [중요] 손으로 고치지 않는다
_OLD_ACTIONS_RULES = "c78a7b793ff501ce2621dc3a66b9c609a8be5e438822df79b89663f7bbffeaf3"
_OLD_INVARIANTS_RULES = "a93574e23b2e23df9bb0a2ee688549bc79f0926784b8c08d5a21276457ea9312"
_OLD_DESC_HEADER = "e029d1b98b47d90f14b46799cd920c0610bbe241ec206211e96b29dd1affc9ff"
_OLD_ACTIONS_PROMPT = "570b627c28ec2af5962eb1bcc6ffd361cc289014854e3ba5f95981ef8d5e63a1"
_OLD_INVARIANTS_PROMPT = "5e5484b6fa740a323db12d658fb99888c8d62afa3c21e30457fe60df18d1ea1d"
_OLD_DESC_PROMPT = "528a4888142c8caec74375d5de0afb1f45bd49ffc9adba622d59148e6f0daca6"
_OLD_CPP_EXCERPT = "49527af42f52214c7df6cc9ed70bdb9c751e67f2db63b2b9b678897c58fca809"

_SYNTH = "master/ontology/synth.py"
_QUAL = "master.ontology.synth.DomainResult"
_LINE_NO = re.compile(r"^\s*\d+: ", re.M)


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _repo_paths(tmp: Path) -> ProjectPaths:
    """이 저장소를 `repo/` 로 보는 임시 프로젝트 — 그래프는 없다(조상·이웃은 빈 값)."""
    os.symlink(_ROOT, tmp / "repo")
    return ProjectPaths(name="T850", root=tmp)


def _sample_ctx(kind: str = "") -> DomainContexts:
    """변경 직전 해시를 잰 것과 같은 표본."""
    return DomainContexts(
        domain="D", members_total=3, part=(1, 2), truncated=["UZ"], kind=kind,
        items=[ClassContext(name="UA", file="Source/X/A.h", ancestors=["UObject"],
                            neighbours=["UQ"], header="class UA : public UObject {};",
                            body="   10: void UA::F() {\n   11:   check(x);"),
               ClassContext(name="UB", file="Source/X/B.h", header="class UB {};")])


# ── 바이트 동일성 ──────────────────────────────────────────────

def test_unreal_byte_identical():
    check("actions 규칙 = 종전", _sha(P._ACTIONS_RULES) == _OLD_ACTIONS_RULES)
    check("invariants 규칙 = 종전", _sha(P._INVARIANTS_RULES) == _OLD_INVARIANTS_RULES)
    check("actions_rules(cpp, ue) = 종전", _sha(P.actions_rules(("cpp",), True)) == _OLD_ACTIONS_RULES)
    check("invariants_rules(cpp, ue) = 종전",
          _sha(P.invariants_rules(("cpp",), True)) == _OLD_INVARIANTS_RULES)
    for kind in ("", "unreal"):
        ctx = _sample_ctx(kind)
        check(f"actions 프롬프트 = 종전 (kind={kind!r})", _sha(P.actions(None, ctx)) == _OLD_ACTIONS_PROMPT)
        check(f"invariants 프롬프트 = 종전 (kind={kind!r})",
              _sha(P.invariants(None, ctx)) == _OLD_INVARIANTS_PROMPT)
    # 파일이 비어 있는 조각(종전 테스트의 ClassContext(name=…))도 종전 동작이다
    bare = DomainContexts(domain="D", items=[ClassContext(name="UA")])
    check("파일 없는 조각 → C++ 규칙", P.actions(None, bare).startswith(P._ACTIONS_RULES))

    check("서술 헤더 상수 = 종전", _sha(dm.PROMPT_HEADER) == _OLD_DESC_HEADER)
    mem = {1: {"objects": ["UA"], "actions": ["DoA"], "invariants": []}, 2: {}, 3: {"objects": ["UB"]}}
    for kind in ("", "unreal"):
        check(f"서술 프롬프트 = 종전 (kind={kind!r})",
              _sha(dm.build_prompt("D", "요약", ["책임"], mem, kind=kind)) == _OLD_DESC_PROMPT)
    check("서술 프롬프트 kind 생략 = 종전", _sha(dm.build_prompt("D", "요약", ["책임"], mem)) == _OLD_DESC_PROMPT)


def test_cpp_excerpt_identical():
    """`.h`+`.cpp` 발췌와 블록 렌더가 종전과 같다 — `_render_hits` 로 뺀 리팩터의 고정."""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "repo" / "Source" / "X").mkdir(parents=True)
        h = ("#pragma once\n// 한글 주석\nclass UFoo : public UObject {\npublic:\n"
             "  void Run();\n  int32 Count = 0;\n};\n") * 30
        cpp: list = []
        for i in range(40):
            cpp += [f"void UFoo::M{i}()", "{", "    check(Count >= 0);", "    FScopeLock L(&Cs);",
                    "    Count++;", "    // 일반 주석", "    Other();", "}", "", ""]
        (tmp / "repo/Source/X/Foo.h").write_text(h, encoding="utf-8")
        (tmp / "repo/Source/X/Foo.cpp").write_text("\n".join(cpp), encoding="utf-8")
        p = ProjectPaths(name="O", root=tmp)
        it = C._build_one(p, "UFoo", {"UFoo": "Source/X/Foo.h"}, {"UFoo"},
                          C.HEADER_CHARS, C.BODY_CHARS)
        got = (C.excerpt_header(p, "Source/X/Foo.h") + "\n====\n"
               + C.excerpt_body(p, "Source/X/Foo.h") + "\n====\n" + it.block())
        check("C++ 발췌·블록 = 종전", _sha(got) == _OLD_CPP_EXCERPT)
        check("C++ 라벨 그대로", "  [.h 선언부]" in it.block() and "  [.cpp 신호 인근]" in it.block())
        check("C++ 경로 기록", it.lang == "cpp" and it.excerpt.startswith("발췌 c++(.h+.cpp)"), it.excerpt)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 파이썬 발췌 (실물) ─────────────────────────────────────────

def test_python_excerpt_real():
    tmp = Path(tempfile.mkdtemp())
    try:
        p = _repo_paths(tmp)
        for name in ("DomainResult", _QUAL):
            h, b, route = C.excerpt_python(p, _SYNTH, name)
            check(f"선언부에 class DomainResult ({name})", "class DomainResult" in h, h[:120])
            check(f"선언부에 메서드 시그니처 ({name})",
                  "def ok(self) -> bool:" in h and "def summary(self) -> str:" in h, h[-200:])
            check(f"본문 비지 않음·줄번호 ({name})", bool(b) and bool(_LINE_NO.search(b)), b[:120])
            check(f"예산 안 ({name})", len(h) <= C.HEADER_CHARS and len(b) <= C.BODY_CHARS + 4,
                  f"{len(h)}/{len(b)}")
            check(f"경로 python(ast) ({name})", route.startswith("python(ast)"), route)
            check(f"모듈 docstring 아님 ({name})", not h.startswith('"""'), h[:60])
            # 신호 없는 클래스는 **메서드 본문이 먼저** — 남은 필드 줄이 자리를 먹지 않는다
            check(f"신호 없음 → 메서드 본문 ({name})",
                  "return bool(self.actions or self.invariants)" in b
                  and route.endswith("메서드 본문 앞부분"), f"{route} | {b[:160]}")

        # 신호가 있는 실물 클래스 — `projects/config.Workshop` 에 raise 가 여럿 있다
        h, b, route = C.excerpt_python(p, "master/projects/config.py", "Workshop")
        check("신호 경로", route == "python(ast)", route)
        check("raise 줄이 줄번호와 본문에", bool(re.search(r"^\s*\d+: \s*raise\b", b, re.M)), b[:200])
        check("선언부에 class Workshop", "class Workshop" in h, h[:120])

        # [중요] `excerpt_header` 는 그대로다 — 층2 그라운딩·골조가 같은 함수를 부른다
        raw = (_ROOT / _SYNTH).read_text(encoding="utf-8")
        check("excerpt_header 동작 불변(.py 앞 1200자)",
              C.excerpt_header(p, _SYNTH) == raw[:C.HEADER_CHARS].rstrip())
        check("excerpt_body 는 .py 에 빈 값(불변)", C.excerpt_body(p, _SYNTH) == "")

        # 조각 수집 경로 — `_build_one` 이 갈라 준다
        chunks = C.chunk_domain(p, "D", members={_QUAL: _SYNTH})
        it = chunks[0].items[0]
        check("ClassContext.lang", it.lang == "python", it.lang)
        check("ClassContext.excerpt 기록",
              it.excerpt.startswith("발췌 python(ast)") and "선언 " in it.excerpt
              and "본문 " in it.excerpt, it.excerpt)
        blk = it.block()
        check("파이썬 라벨", "  [선언부]" in blk and "  [신호 인근]" in blk
              and "[.h 선언부]" not in blk, blk[:200])
        print(f"  [기록] {it.name}: {it.excerpt}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_python_fallback_visible():
    tmp = Path(tempfile.mkdtemp())
    try:
        p = _repo_paths(tmp)
        h, b, route = C.excerpt_python(p, _SYNTH, "NoSuchClass")
        check("클래스 못 찾음 → 폴백 기록", route == "python → 폴백: 클래스 못 찾음 (NoSuchClass)", route)
        check("폴백 = 종전 선언부", h == C.excerpt_header(p, _SYNTH) and b == "")

        bad = tmp / "bad"
        bad.mkdir()
        (bad / "repo").mkdir()
        (bad / "repo" / "broken.py").write_text("class Broken(:\n    pass\n", encoding="utf-8")
        bp = ProjectPaths(name="B", root=bad)
        h, b, route = C.excerpt_python(bp, "broken.py", "Broken")
        check("AST 실패 → 폴백 기록", route.startswith("python → 폴백: AST 파싱 실패"), route)
        check("AST 실패 → 종전 선언부", h == C.excerpt_header(bp, "broken.py") and b == "")
        it = C._build_one(bp, "Broken", {"Broken": "broken.py"}, {"Broken"},
                          C.HEADER_CHARS, C.BODY_CHARS)
        check("폴백이 ClassContext 에 보인다", "폴백" in it.excerpt, it.excerpt)

        h, b, route = C.excerpt_python(bp, "missing.py", "X")
        check("파일 없음 → 폴백 기록", route == "python → 폴백: 파일을 못 읽음" and not h and not b)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 이름 분리 ──────────────────────────────────────────────────

def _action(primary, related=()):
    import json
    return json.dumps({"actions": [{"name": "A", "evidence": "f:1", "confidence": 0.9,
                                    "implementation": {"primary": primary,
                                                       "related": list(related)}}]})


def test_name_split():
    o = parse.owner_class
    check("점 구분", o("DomainResult.summary", {"DomainResult"}) == "DomainResult")
    check("모듈 접두", o(f"{_QUAL}.summary", {_QUAL, "DomainResult"}) == _QUAL)
    check("가장 긴 접두", o("pkg.A.B.m", {"pkg.A", "pkg.A.B"}) == "pkg.A.B")
    check("C++ ::", o("UFoo::Run", {"UFoo"}) == "UFoo")
    check("이름 경계 — 접두만 같은 것 안 맞음", o("DomainResultX.y", {"DomainResult"}) == "")
    check("구분자 없는 단독 이름은 owner 아님", o("DomainResult", {"DomainResult"}) == "")

    ok = lambda prim, allowed, rel=(): parse.actions(_action(prim, rel), allowed=allowed)  # noqa: E731
    check("parse: DomainResult.summary 허용", len(ok("DomainResult.summary", {"DomainResult"}).items) == 1)
    check("parse: 모듈 접두 허용", len(ok(f"{_QUAL}.summary", {_QUAL}).items) == 1)
    check("parse: DomainResult::summary 허용", len(ok("DomainResult::summary", {"DomainResult"}).items) == 1)
    check("parse: 도메인 밖 .", len(ok("Other.run", {"DomainResult"}).items) == 0)
    check("parse: C++ 허용(종전)", len(ok("UFoo::Run", {"UFoo"}).items) == 1)
    check("parse: C++ 도메인 밖(종전)", len(ok("UBar::Run", {"UFoo"}).items) == 0)
    check("parse: 단독 클래스명(종전)", len(ok("UFoo", {"UFoo"}).items) == 1)
    got = ok("DomainResult.summary", {"DomainResult"}, ["DomainResult.ok", "Other.x"]).items
    check("parse: related 도 같은 규칙",
          got and got[0]["implementation"].get("related") == ["DomainResult.ok"], got)

    lay = {"DomainResult": 1, _QUAL: 2, "UFoo": 1, "UBar": 2}
    def layer(prim, affected=()):
        item = {"implementation": {"primary": prim}, "objects_affected": list(affected)}
        synth._assign_layer(item, lay)
        return item["layer"]
    check("synth: 점 구분", layer("DomainResult.summary") == 1)
    check("synth: 모듈 접두", layer(f"{_QUAL}.summary") == 2)
    check("synth: C++ 종전", layer("UFoo::Run") == 1)
    check("synth: 모르는 C++ → L3(종전)", layer("UZed::Run", ["UBar"]) == 3)
    check("synth: 구분자 없음 → objects_affected(종전)", layer("UFoo", ["UBar"]) == 2)
    check("synth: 모르는 점 이름 → objects_affected", layer("Other.run", ["UBar"]) == 2)


# ── 프롬프트 언어 블록 ─────────────────────────────────────────

def test_prompt_blocks():
    py = DomainContexts(domain="D", kind="code",
                        items=[ClassContext(name=_QUAL, file=_SYNTH, lang="python")])
    a, i = P.actions(None, py), P.invariants(None, py)
    check("code+py: UE 문구 없음", "Unreal" not in a and "Unreal" not in i)
    check("code+py: UE 이벤트·통신 없음", "AddDynamic" not in a and "FSocket" not in a)
    check("code+py: primary 형식 점", '"클래스명.메서드명"' in a and "<클래스.메서드>" in a)
    check("code+py: 파이썬 신호", "assert / 조건 위반 시 raise" in i and "threading.Lock" in i
          and "check()" not in i)
    for sig in parse.VALID_SIGNALS:
        check(f"신호 이름 유지 {sig}", f"  {sig}" in i and sig in i.split("source_signal")[-1])

    mixed = DomainContexts(domain="D", kind="code", items=[
        ClassContext(name="Web", file="web/app.py"), ClassContext(name="Core", file="native/core.h")])
    a = P.actions(None, mixed)
    check("혼합: 두 블록", "(C++ 소스)" in a and "(Python 소스)" in a, a[:200])
    check("혼합(code): 범용 C++ — UE 없음", "Unreal" not in a and "AddDynamic" not in a)
    check("혼합: primary 형식 둘", "클래스::메서드 또는 클래스.메서드" in a)

    ue_py = DomainContexts(domain="D", kind="unreal",
                           items=[ClassContext(name="WebUi", file="WebUI/server.py")])
    a = P.actions(None, ue_py)
    check("unreal+py 조각: 파이썬 블록", "add_listener" in a and "AddDynamic" not in a)
    ue_mixed = DomainContexts(domain="D", kind="unreal", items=[
        ClassContext(name="WebUi", file="WebUI/server.py"), ClassContext(name="UA", file="Source/A.h")])
    a = P.actions(None, ue_mixed)
    check("unreal 혼합: UE C++ + Python", "AddDynamic" in a and "add_listener" in a
          and a.startswith("당신은 Unreal Engine 5"))

    code_cpp = DomainContexts(domain="D", kind="code", items=[ClassContext(name="K", file="sub/k.cpp")])
    i = P.invariants(None, code_cpp)
    check("code+C++: 범용 C++", "std::mutex" in i and "FScopeLock" not in i and "Unreal" not in i)

    mem = {1: {"objects": ["A"], "actions": [], "invariants": []}}
    for kind in ("code", "index_only"):
        d = dm.build_prompt("D", "", [], mem, kind=kind)
        check(f"서술 헤더 중립 ({kind})", "Unreal" not in d and d.startswith("당신은 소프트웨어 프로젝트의 도메인을"))
    check("서술 헤더 나머지 동일",
          dm.prompt_header("code").split("\n", 1)[1] == dm.PROMPT_HEADER.split("\n", 1)[1])


def main() -> int:
    for fn in (test_unreal_byte_identical, test_cpp_excerpt_identical, test_python_excerpt_real,
               test_python_fallback_visible, test_name_split, test_prompt_blocks):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_ontology_python: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
