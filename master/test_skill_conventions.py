"""스킬 작성 규약 검사 (`#890` T7) — 규약 정본은 `docs/skill-authoring.md`.

스킬을 만들 때마다 지키는 규약이다(사용자 2026-11-07). 절차서로 두면 「이번엔 해당 없음」 판정이 생기므로
이 검사가 **모든 스킬 폴더를 훑어** 강제한다 — 새 스킬도 자동으로 대상이 된다.

    ① frontmatter — YAML 파싱 · name == 폴더 · 형식 · description 1,024자 · 꺾쇠 없음
    ② 구획 — `# 제목` 다음 곧바로 `## 목차` · 목차 == 뒤의 `## 제목`(순서·글자) · 제목 없는 서문 없음
    ③ 길이 — SKILL.md 500줄 미만 · 100줄 초과면 앞 100줄 안에 목차와 사용 예(또는 호출 방법)
    ④ 번들 — SKILL.md + reference/·scripts/ 한 단계 · reference 링크 실재 · 100줄 넘는 reference 는 목차
    ⑤ 인라인 `python -c` 없음
    ⑥ MCP 도구 이름은 `서버:도구`
    ⑦ 규약을 어긴 표본(임시 스킬)이 항목별로 잡힌다 — 검사 자체의 검사
    ⑧ 배달 스킬의 MCP 호출은 해당 역할에 배달되는 서버·실재 도구만 쓴다 (`#898`)

    .venv/bin/python master/test_skill_conventions.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from master.client import spec

ROOTS = (REPO / "master/skills", REPO / "master/client/skills", REPO / "master/client/workshop/skills")
BUNDLE_DIRS = ("reference", "scripts")
FENCE = re.compile(r"\s*(```|~~~)")
NAME = re.compile(r"^[a-z0-9-]{1,64}$")

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def tool_names() -> dict:
    proj = re.findall(r"@mcp\.tool\(\)\s*\ndef (\w+)", (REPO / "master/projects/mcp_server.py").read_text(encoding="utf-8"))
    cli = re.findall(r'\{"name": "(\w+)",', (REPO / "client/runtime/client_mcp.py").read_text(encoding="utf-8"))
    return {**{n: "ax-projects" for n in proj}, **{n: "ax-client" for n in cli}}


def role_servers(d: Path) -> tuple | None:
    """마스터 스킬은 제한하지 않고 배달 스킬은 역할별 서버와 대조한다."""
    if d.parent not in ROOTS[1:]:
        return None
    tables = (spec.SKILLS_BY_ROLE, spec.INDEX_ONLY_SKILLS, spec.CODE_SKILLS)
    roles = {role for table in tables for role, names in table.items() if d.name in names}
    # 작업장 스킬은 요청자 작업장 자산이다. 표에 아직 없는 새 배달 스킬도 열린
    # 마스터 서버를 허용하지 않고 설치 가능한 클라이언트 서버만 허용한다.
    if not roles:
        roles = {"requester"}
    # 같은 스킬이 여러 역할에 배달되면 어느 역할에서도 부를 수 있어야 한다.
    available = [set(spec.MCP_BY_ROLE[role]) for role in roles]
    return tuple(sorted(set.intersection(*available)))


def role_tool_problems(text: str, tools: dict, servers: tuple) -> list:
    """호출 안내의 서버·도구를 검사한다. 명시적으로 금지한 이름은 실행 안내가 아니다."""
    bad = []
    for m in re.finditer(r"(?<![\w-])(ax-[a-z0-9-]+):(\w+)", text):
        server, name = m.groups()
        # 예: 「`ax-projects:register_work_tool` 이 아니다」라는 교정 설명은 보존한다.
        # 같은 줄의 다른 호출까지 제외하지 않고 이 참조 바로 뒤의 부정만 읽는다.
        if re.match(r"[`*]*\s*(?:이|가)?\s*아니다", text[m.end():]):
            continue
        if server not in servers:
            bad.append(f"역할에 없는 MCP 서버 {server}:{name}")
        elif tools.get(name) != server:
            bad.append(f"서버에 없는 MCP 도구 {server}:{name}")
    return sorted(set(bad))


def headings(lines: list) -> list:
    """`(줄 번호, 단계, 제목)` — 펜스 안은 세지 않는다."""
    out, fence = [], False
    for i, l in enumerate(lines):
        if FENCE.match(l):
            fence = not fence
            continue
        m = re.match(r"(#{1,6}) (.*)", l)
        if not fence and m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def toc_problems(lines: list, *, need_h1: bool = True) -> list:
    """② 구획 규약 위반 목록."""
    hs = headings(lines)
    h1 = [h for h in hs if h[1] == 1]
    bad = []
    if need_h1 and len(h1) != 1:
        return [f"# 제목이 {len(h1)}개(1개여야 한다)"]
    start = h1[0][0] if h1 else -1
    h2 = [h for h in hs if h[1] == 2]
    if not h2:
        return bad
    if h2[0][2] != "목차":
        return [f"첫 ## 구획이 「목차」가 아니다: {h2[0][2]!r}"]
    between = [l for l in lines[start + 1:h2[0][0]] if l.strip() and not l.startswith(">")]
    if between:
        bad.append(f"# 제목과 ## 목차 사이에 제목 없는 본문 {len(between)}줄")
    toc_end = h2[1][0] if len(h2) > 1 else len(lines)
    items = [l for l in lines[h2[0][0] + 1:toc_end] if l.strip() and not l.startswith(">")]
    listed = [re.sub(r"^- ", "", l).strip() for l in items if l.startswith("- ")]
    if len(listed) != len(items):
        bad.append("목차 구획에 `- 제목` 이 아닌 줄이 있다")
    actual = [h[2] for h in h2[1:]]
    if listed != actual:
        bad.append(f"목차 ≠ ## 제목 — 목차 {len(listed)}개 · 실제 {len(actual)}개 · "
                   f"첫 차이 {next((f'{a!r}≠{b!r}' for a, b in zip(listed, actual) if a != b), '개수')}")
    return bad


def skill_problems(d: Path, tools: dict) -> list:
    bad = []
    f = d / "SKILL.md"
    if not f.is_file():
        return ["SKILL.md 없음"]
    text = f.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return ["frontmatter 없음"]
    try:
        end = text.index("\n---", 3)
        fm = yaml.safe_load(text[4:end])
    except Exception as e:                                   # noqa: BLE001
        return [f"frontmatter YAML 파싱 실패 — {type(e).__name__}"]
    name, desc = str((fm or {}).get("name", "")), str((fm or {}).get("description", ""))
    if name != d.name:
        bad.append(f"name {name!r} ≠ 폴더 {d.name!r}")
    if not NAME.match(name):
        bad.append(f"name 형식 {name!r}")
    if not desc.strip() or len(desc) > 1024:
        bad.append(f"description 길이 {len(desc)}")
    if re.search(r"<[^>]+>", desc):
        bad.append("description 에 꺾쇠 자리표시")
    body = text[text.index("\n", end + 1) + 1:]
    lines = body.split("\n")
    total = len(text.split("\n"))
    bad += toc_problems(lines)
    if total >= 500:
        bad.append(f"SKILL.md {total}줄(500줄 미만) — reference/ 로 옮긴다")
    if total > 100:
        off = total - len(lines)
        hs = [(i + off, h) for i, lv, h in headings(lines) if lv == 2]
        toc_at = next((i for i, h in hs if h == "목차"), None)
        ex_at = next((i for i, h in hs if h in ("사용 예", "호출 방법")), None)
        if toc_at is None or toc_at > 100 or ex_at is None or ex_at > 100:
            bad.append("100줄 초과인데 앞 100줄 안에 목차·사용 예(또는 호출 방법)가 없다")
    files = [f] + [p for sub in BUNDLE_DIRS if (d / sub).is_dir() for p in (d / sub).iterdir() if p.is_file()]
    for x in d.iterdir():
        if x.name.startswith(".") or x.name == "__pycache__" or x.name == "SKILL.md":
            continue
        if x.is_file() or x.name not in BUNDLE_DIRS:
            bad.append(f"번들 밖 {'파일' if x.is_file() else '폴더'} {x.name}")
        else:
            for y in x.iterdir():
                if y.is_dir() and y.name != "__pycache__":
                    bad.append(f"번들 두 단계 {x.name}/{y.name}/")
    for link in re.findall(r"\]\((reference/[^)#\s]+)", body):
        if not (d / link).is_file():
            bad.append(f"없는 참조 {link}")
        elif link.count("/") != 1:
            bad.append(f"참조가 한 단계가 아니다 {link}")
    pat = re.compile(r"(?<![\w:.\-/])(" + "|".join(sorted(tools, key=len, reverse=True)) + r")(?![\w])")
    for p in files:
        if p.suffix not in (".md", ".py", ".sh", ".txt"):
            continue
        t = p.read_text(encoding="utf-8")
        rel = p.relative_to(d)
        if re.search(r"python[0-9.]*\s+-c\s", t) and p.suffix == ".md":
            bad.append(f"{rel}: 인라인 python -c")
        if p.suffix == ".md":
            seg = t if p != f else body
            hits = sorted(set(pat.findall(seg)))
            if hits:
                bad.append(f"{rel}: 서버 없는 MCP 도구 이름 {hits[:4]}")
            servers = role_servers(d)
            if servers is not None:
                bad += [f"{rel}: {problem}" for problem in role_tool_problems(seg, tools, servers)]
        if p != f and p.suffix == ".md" and len(t.split("\n")) > 100:
            rl = t.replace("\r\n", "\n").split("\n")
            bad += [f"{rel}: {x}" for x in toc_problems(rl)]
    return bad


def all_skills() -> list:
    return sorted(d for r in ROOTS if r.is_dir() for d in r.iterdir() if d.is_dir() and not d.name.startswith("."))


def test_real_skills() -> None:
    print("\n[1] 저장소의 모든 스킬이 규약을 지킨다")
    tools = tool_names()
    skills = all_skills()
    check("스킬이 있다(경로 확인)", len(skills) >= 20, str(len(skills)))
    for d in skills:
        probs = skill_problems(d, tools)
        check(f"{d.relative_to(REPO)}", not probs, " · ".join(probs))


def _sample(tmp: Path, name: str, fm: str, body: str) -> Path:
    d = tmp / name
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\n{fm}\n---\n\n{body}", encoding="utf-8")
    return d


def test_violations_are_caught() -> None:
    print("\n[2] 규약을 어긴 표본이 항목별로 잡힌다")
    tools = tool_names()
    tmp = Path(tempfile.mkdtemp(prefix="ax-skillconv-"))
    good = "# t\n\n## 목차\n\n- 개요\n\n## 개요\n\n본문\n"
    d = _sample(tmp, "ok", "name: ok\ndescription: 무엇을 한다. 이럴 때 쓴다.", good)
    check("규약을 지킨 표본은 통과", skill_problems(d, tools) == [], str(skill_problems(d, tools)))
    cases = [
        ("yaml", "name: yaml\ndescription: `백틱 시작`", good, "YAML"),
        ("angle", "name: angle\ndescription: issue/<N> 에서 한다", good, "꺾쇠"),
        ("wrongname", "name: other\ndescription: d", good, "폴더"),
        ("notoc", "name: notoc\ndescription: d", "# t\n\n## 개요\n\n본문\n", "목차"),
        ("tocdiff", "name: tocdiff\ndescription: d", "# t\n\n## 목차\n\n- 개요\n\n## 개요\n\n## 둘\n", "목차 ≠"),
        ("preamble", "name: preamble\ndescription: d", "# t\n\n서문\n\n## 목차\n\n- 개요\n\n## 개요\n", "사이에"),
        ("pyc", "name: pyc\ndescription: d", good + "\n    .venv/bin/python -c \"print(1)\"\n", "python -c"),
        ("tool", "name: tool\ndescription: d", good + "\n`issue_start_tool` 을 부른다\n", "서버 없는"),
        ("long", "name: long\ndescription: d", good + "x\n" * 520, "500줄"),
        ("noex", "name: noex\ndescription: d", good + "x\n" * 120, "사용 예"),
        ("deadref", "name: deadref\ndescription: d", good + "\n[a](reference/none.md)\n", "없는 참조"),
    ]
    for name, fm, body, key in cases:
        d = _sample(tmp, name, fm, body)
        probs = skill_problems(d, tools)
        check(f"표본 {name} → 「{key}」", any(key in p for p in probs), str(probs))
    d = _sample(tmp, "stray", "name: stray\ndescription: d", good)
    (d / "notes.md").write_text("x", encoding="utf-8")
    (d / "reference" / "deep").mkdir(parents=True)
    probs = skill_problems(d, tools)
    check("표본 stray → 번들 밖 파일 · 두 단계", any("번들 밖" in p for p in probs)
          and any("두 단계" in p for p in probs), str(probs))
    d = _sample(tmp, "fenced", "name: fenced\ndescription: d", good + "\n```\n# 펜스 안 제목\n## 펜스 안\n```\n")
    check("펜스 안 # 줄은 제목으로 세지 않는다", skill_problems(d, tools) == [], str(skill_problems(d, tools)))


def test_role_tool_calls() -> None:
    print("\n[3] 역할별 MCP 서버·실재 도구 호출")
    tools = tool_names()
    check("요청자·워커 역할 서버는 배달 명세에서 읽는다",
          role_servers(ROOTS[1] / "ax-request") == spec.MCP_BY_ROLE["requester"]
          and role_servers(ROOTS[1] / "ax-work") == spec.MCP_BY_ROLE["worker"])
    check("마스터 스킬은 요청자 서버 제한을 받지 않는다", role_servers(ROOTS[0] / "ax-plan") is None)
    cases = [
        ("기존 클라이언트 호출", "ax-client:search_context(query, n=5)", False),
        ("잘못된 서버의 실행 안내", "    ax-projects:resolve_terms_tool(terms)", True),
        ("잘못 붙인 서버 이름", "ax-client:resolve_terms_tool(terms)", True),
        ("존재하지 않는 도구", "ax-client:missing_ontology_tool()", True),
        ("금지 대상을 설명한 문장", "**`ax-projects:register_work_tool` 이 아니다.**", False),
        ("부정 설명 뒤 다른 호출", "`ax-projects:register_work_tool` 이 아니다. ax-projects:resolve_terms_tool(terms)", True),
    ]
    for name, text, fails in cases:
        got = role_tool_problems(text, tools, spec.MCP_BY_ROLE["requester"])
        check(name, bool(got) == fails, str(got))


def main() -> int:
    for fn in (test_real_skills, test_violations_are_caught, test_role_tool_calls):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_skill_conventions: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
