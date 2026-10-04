"""사실 게이트의 파일 형식별 주석 규칙 (`#732`) — 회귀 칸.

[중요] 실측 사례: `master/webui/routes.py:102` 의 파이썬 주석 `# … static/*.html …` 안의 `/*` 를
C++ 규칙이 블록 주석 시작으로 읽어 실제 코드를 삼켰고, 진짜 상수 셋이 「주석에만 있다」로
분류돼 정상 문서가 거부됐다(인덱서 정지). 형식마다 ① 주석에만 있는 이름은 **여전히 잡고**
② 문자열·CDATA·속성 안의 주석 표지가 **코드를 삼키지 않는지** 잰다.

`.venv/bin/python -B master/test_verify_filetypes.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from master.context_synth import verify as V                        # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _doc(*names: str) -> str:
    return "---\ntags: [x]\n---\n## 요약\n" + " ".join(f"`{n}`" for n in names) + " 를 쓴다.\n"


def test_lang_for() -> None:
    print("\n[1] 확장자 → 규칙")
    for p, want in [("a/b.h", "cpp"), ("x.HPP", "cpp"), ("x.inl", "cpp"), ("x.c", "cpp"),
                    ("x.cc", "cpp"), ("x.cpp", "cpp"), ("M.Build.cs", "cs"),
                    ("A.java", "java"), ("p/routes.py", "python"), ("i.html", "html"),
                    ("i.htm", "html"), ("Foo_UPL.xml", "xml"),
                    ("Config/DefaultEngine.ini", "ini"), ("a.json", "json"),
                    ("P.uplugin", "json"), ("G.uproject", "json"),
                    ("x.rs", None), ("Makefile", None), ("a.b/noext", None), ("", None)]:
        check(f"lang_for({p!r}) == {want!r}", V.lang_for(p) == want, str(V.lang_for(p)))


def test_python() -> None:
    print("\n[2] 파이썬 — `#` 주석 · 문자열/docstring 은 주석이 아니다")
    SRC = '''"""모듈 설명 — /* 여기는 docstring */ 이고 // 이것도 docstring 이다."""
# 정적 파일은 static/*.html 에서 읽는다
_SIDE_VARS = {"a": 1}
URL = "http://x/y"   # 끝 주석 GhostAfterUrl
_SHELL_CSS = """/* css */ body { color: red; } // not comment"""
def real_func():
    return '# not a comment' + _SIDE_VARS["a"]
# class LegacyThing: 주석 처리됨
'''
    live, dead = V.strip_comments(SRC, lang="python")
    only = V.comment_only(SRC, lang="python")
    check("🔴 `# static/*.html` 뒤 정의가 live 다", "_SIDE_VARS" in V.identifiers(live)
          and "_SIDE_VARS" not in only, str(sorted(only)))
    check("URL 문자열의 `//` 가 코드를 삼키지 않는다",
          "_SHELL_CSS" in live and "real_func" in live, live)
    check("docstring 안 `/*`·`//` 가 코드를 삼키지 않는다", "_SIDE_VARS" in live)
    check("문자열 안 `#` 은 주석이 아니다", "# not a comment" in live)
    check("문자열 내용은 live 에 남는다 (C++ 경로와 같은 판단)", "http://x/y" in live)
    check("🔴 `#` 주석에만 있는 이름은 여전히 유령이다",
          {"LegacyThing", "GhostAfterUrl"} <= only, str(sorted(only)))
    check("[주의] C++ 규칙이면 같은 소스에서 삼켜진다 (재현 전제)",
          "_SHELL_CSS" in V.comment_only(SRC), str(sorted(V.comment_only(SRC))))
    r = V.verify(_doc("LegacyThing"), sources={"pkg/mod.py": SRC})
    check("verify() 가 .py 경로로 잡는다", not r.ok and "LegacyThing" in r.ghosts, str(r.ghosts))
    r = V.verify(_doc("_SIDE_VARS", "_SHELL_CSS"), sources={"pkg/mod.py": SRC})
    check("verify() 가 .py 의 살아 있는 상수를 통과시킨다", r.ok, r.reason)


def test_routes_py_real() -> None:
    print("\n[3] 🔴 실측 파일 `master/webui/routes.py` — 세 상수가 유령 풀에 없다")
    path = "master/webui/routes.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    names = {"_SIDE_VARS", "_CONTEXT_SHELL_CSS", "_ONTOLOGY_SHELL_CSS"}
    check("  전제: C++ 규칙으로는 셋이 유령이었다", names <= V.comment_only(text),
          str(names & V.comment_only(text)))
    got = V.comment_only(text, lang=V.lang_for(path)) & names
    check("🔴 경로 규칙(파이썬)으로는 셋 다 유령이 아니다", not got, str(got))
    r = V.verify(_doc(*sorted(names)), sources={path: text})
    check("🔴 verify() 가 셋을 유령으로 세지 않는다", not (set(r.ghosts) & names), str(r.ghosts))


def test_cpp_unchanged() -> None:
    print("\n[4] C++ — 종전 동작 그대로 + raw 문자열")
    SRC = """
// class ULegacyLoader : public UObject {};
/* struct FOldPayload { int32 Count; }; */
class UActiveThing : public UObject {
    void DoWork();
    const char* note = "// not a comment /* nor this */";
    char c = '"';
    void AfterChar();
};
"""
    check("기본(lang 없음) == lang='cpp'", V.strip_comments(SRC) == V.strip_comments(SRC, lang="cpp"))
    only = V.comment_only(SRC)
    check("주석 전용을 잡는다", {"ULegacyLoader", "FOldPayload"} <= only, str(sorted(only)))
    check("문자·문자열 리터럴이 코드를 삼키지 않는다",
          not ({"UActiveThing", "DoWork", "AfterChar"} & only))
    RAW = 'auto s = R"xx(text " // /* )" still)xx";\nvoid AfterRaw();\n// FGhostRaw\n'
    live, _ = V.strip_comments(RAW, lang="cpp")
    only = V.comment_only(RAW, lang="cpp")
    check("raw 문자열 안 `\"`·`//`·`/*` 가 코드를 삼키지 않는다", "AfterRaw" in live, live)
    check("raw 문자열 뒤 주석 전용은 여전히 잡는다", only == {"FGhostRaw"}, str(only))
    check("이름 끝의 R 은 raw 접두가 아니다",
          "AfterQ" in V.strip_comments('FOO_R"x" ; void AfterQ();', lang="cpp")[0])


def test_csharp() -> None:
    print("\n[5] C# — verbatim `@\"…\"` · 보간 `$\"…\"`")
    SRC = '''// Copyright Epic Games, Inc. All Rights Reserved.
public class MyGame : ModuleRules {
    string p = @"C:\\dir\\"; string q = @"say ""//hi"" /* x";
    string r = $"{Name} // not comment";
    string s = $@"C:\\{Name}\\"; void AfterStrings() {}
    // PublicDependencyModuleNames.Add("OldModule_Ghost");
    /* FOldCsThing */
}
'''
    live, _ = V.strip_comments(SRC, lang="cs")
    only = V.comment_only(SRC, lang="cs")
    check("verbatim·보간 문자열이 코드를 삼키지 않는다", "AfterStrings" in live, live)
    check("주석 전용을 잡는다", {"OldModule_Ghost", "FOldCsThing"} <= only, str(sorted(only)))
    check("live 이름은 유령이 아니다", not ({"MyGame", "ModuleRules", "AfterStrings"} & only))
    check("저작권 머리말은 빠진다", "Rights" not in only and "Epic" not in only, str(sorted(only)))


def test_java() -> None:
    print("\n[6] 자바 — `//`·`/* */`·문자·문자열·텍스트 블록")
    SRC = '''package com.epicgames;
public class GameActivity {
    String u = "http://example.com/*";
    char c = '"';
    String t = """
        // not a comment " still text /* nor this
        """;
    void afterBlock() {}
    // void legacyHelper_Ghost() {}
}
'''
    live, _ = V.strip_comments(SRC, lang="java")
    only = V.comment_only(SRC, lang="java")
    check("문자열·문자·텍스트 블록이 코드를 삼키지 않는다", "afterBlock" in live, live)
    check("주석 전용을 잡는다", "legacyHelper_Ghost" in only, str(sorted(only)))
    check("live 이름은 유령이 아니다", "GameActivity" not in only and "afterBlock" not in only)


def test_html() -> None:
    print("\n[7] HTML — `<!-- -->` · `<script>` JS · `<style>` CSS · 속성")
    SRC = '''<!doctype html>
<!-- <div id="OldPanel_Ghost"></div> -->
<a href="http://example.com/x" data-x="/* not */">link</a>
<span id="after_attr"></span>
<script>
  const url = "http://a/b"; // ScriptGhost_Line
  /* ScriptGhost_Block */
  const tpl = `a // b /* c`; function afterScript() {}
</script>
<style>
  .box { background: url(http://cdn/x.png); } /* StyleGhost_Block */
  .after_style { color: red; }
</style>
<p class="after_all"></p>
'''
    live, _ = V.strip_comments(SRC, lang="html")
    only = V.comment_only(SRC, lang="html")
    check("`<!-- -->` 주석 전용을 잡는다", "OldPanel_Ghost" in only, str(sorted(only)))
    check("속성의 `//`·`/*` 가 코드를 삼키지 않는다", "after_attr" in live, live)
    check("script `//`·`/* */` 주석을 잡는다",
          {"ScriptGhost_Line", "ScriptGhost_Block"} <= only, str(sorted(only)))
    check("script 문자열·템플릿이 코드를 삼키지 않는다", "afterScript" in live)
    check("style `/* */` 를 잡는다", "StyleGhost_Block" in only)
    check("[중요] CSS 에서 `url(http://…)` 의 `//` 는 주석이 아니다", "after_style" in live, live)
    check("닫는 태그 뒤도 live 다", "after_all" in live)


def test_xml() -> None:
    print("\n[8] XML — `<!-- -->` · CDATA 는 내용 · 속성")
    SRC = '''<?xml version="1.0" encoding="utf-8"?>
<root xmlns:android="http://schemas.android.com/apk/res/android">
  <!-- <insert>OldUplHook_Ghost</insert> -->
  <gameActivityImportAdditions>
    <insertValue value="// not a comment /* either"/>
    <insert><![CDATA[ import foo; <!-- not a comment --> // nor this ]]></insert>
    <after_cdata/>
  </gameActivityImportAdditions>
</root>
'''
    live, _ = V.strip_comments(SRC, lang="xml")
    only = V.comment_only(SRC, lang="xml")
    check("주석 전용을 잡는다", only == {"OldUplHook_Ghost"}, str(sorted(only)))
    check("CDATA 안 `<!--` 는 내용이다", "<!-- not a comment -->" in live, live)
    check("CDATA·속성 뒤가 live 다", "after_cdata" in live)


def test_ini() -> None:
    print("\n[9] INI — 줄 전체 `;` 만 주석 · 값 안 `;`·경로·URL 은 live")
    SRC = """; Copyright Epic Games, Inc. All Rights Reserved.
[/Script/EngineSettings.GameMapsSettings]
; GameDefaultMap=/Game/Maps/OldMap_Ghost
  ; +ActiveGameNameRedirects=(OldGameName="LegacyName_Ghost")
GameDefaultMap=/Game/Maps/MainMap_Live.MainMap_Live
ServerUrl=http://example.com/api/* ; NotAComment_Inline
# HashLine_Live
[After_Section]
"""
    live, _ = V.strip_comments(SRC, lang="ini")
    only = V.comment_only(SRC, lang="ini")
    check("`;` 줄 주석 전용을 잡는다", {"OldMap_Ghost", "LegacyName_Ghost"} <= only, str(sorted(only)))
    check("`/Game/…` 값은 live 다", "MainMap_Live" in live and "MainMap_Live" not in only)
    check("값 뒤 `;` 는 주석이 아니다 · URL 의 `/*` 가 삼키지 않는다",
          "NotAComment_Inline" in live and "After_Section" in live, live)
    check("[주의] `#` 줄은 주석으로 보지 않는다 (근거 미확인 — 보수적)", "HashLine_Live" in live)
    check("저작권 머리말은 빠진다", "Rights" not in only and "Epic" not in only, str(sorted(only)))
    r = V.verify(_doc("OldMap_Ghost"), sources={"Config/DefaultEngine.ini": SRC})
    check("verify() 가 .ini 경로로 잡는다", not r.ok and "OldMap_Ghost" in r.ghosts, str(r.ghosts))


def test_json() -> None:
    print("\n[10] JSON (`.json`·`.uplugin`·`.uproject`) — 주석 없음 · 전부 live")
    SRC = """{
  "FriendlyName": "My /* Plugin",
  "DocsURL": "http://example.com//docs",
  "Modules": [ { "Name": "MyPlugin_Runtime", "LoadingPhase": "Default" } ],
  "After_Key": "*/ end"
}
"""
    live, dead = V.strip_comments(SRC, lang="json")
    check("문자열 안 `/*`·`//` 가 키를 삼키지 않는다", live == SRC and dead == "")
    check("유령 0", V.comment_only(SRC, lang="json") == set())
    r = V.verify(_doc("MyPlugin_Runtime"), sources={"Plugins/My/My.uplugin": SRC})
    check(".uplugin 이 JSON 으로 처리돼 통과한다", r.ok, r.reason)


def test_unknown_extension() -> None:
    print("\n[11] 모르는 확장자 — 판정하지 않는다 (사용자 결정 ⓐ)")
    SRC = "// FUnknownGhost\nfn real_thing() {}\n"
    check("lang=None 이면 유령 0", V.comment_only(SRC, lang=None) == set())
    check("lang=None 이면 원문 전체 live", V.strip_comments(SRC, lang=None) == (SRC, ""))
    r = V.verify(_doc("FUnknownGhost"), sources={"src/lib.rs": SRC})
    check("🔴 모르는 형식 파일은 유령을 보태지 않는다", r.ok and not r.ghosts, r.reason)
    CPP = "// FUnknownGhost\nclass ALive {};\n"
    r = V.verify(_doc("FUnknownGhost"), sources={"a.h": CPP})
    check("  같은 이름이 .h 주석에만 있으면 여전히 잡는다", not r.ok, str(r.ghosts))
    r = V.verify(_doc("FUnknownGhost"), sources={"a.h": CPP, "src/lib.rs": SRC})
    check("[주의] 그 대가 — 모르는 형식 파일의 원문이 live 로 세져 유령을 지운다 (오탐 0 쪽)",
          r.ok, str(r.ghosts))


if __name__ == "__main__":
    test_lang_for()
    test_python()
    test_routes_py_real()
    test_cpp_unchanged()
    test_csharp()
    test_java()
    test_html()
    test_xml()
    test_ini()
    test_json()
    test_unknown_extension()
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
