"""생산자③ 작업 기록 (#207) 계약 테스트.

재는 것 넷:
    ① frontmatter 계약   [중요] 산출물을 **원전 미니 파서(history_harvest)의 눈**으로 재파싱 —
                        특히 대시 리스트 (인라인 `[a, b]` 는 그 파서가 못 읽는다, 실측)
    ② 종결 자동 기록     work merged/rejected → 사실 기록 (제목·판정·파일·user_quote=검수 노트)
    ③ 클라 자리          .33 MCP log_history 가 마스터 대행 POST 를 올바른 본문으로
    ④ 검증               title 필수 · decision_type enum · 파일명 규약

실행: .venv/bin/python master/test_history_gen.py   (LLM 0 · 네트워크 0)
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import history_gen as HG       # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        self.root = root


def fixture():
    return P(Path(tempfile.mkdtemp(prefix="ax-hg-")))


# ── 원전 미니 파서 — history_harvest._parse_simple_frontmatter 글자대로 ──

_FM_BOUNDARY_RE = re.compile(r"^---\s*$", re.M)
_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def _scalar_value(s: str):
    s = s.strip()
    if not s:
        return ""
    if s.lower() == "null":
        return None
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def origin_parse(text: str) -> dict:
    m1 = _FM_BOUNDARY_RE.search(text)
    m2 = _FM_BOUNDARY_RE.search(text, m1.end() + 1)
    lines = text[m1.end():m2.start()].splitlines()
    result, i = {}, 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.strip().startswith("#") or ln.startswith(" "):
            i += 1
            continue
        m = _FM_KEY_RE.match(ln)
        if not m:
            i += 1
            continue
        key, val_raw = m.group(1), m.group(2).strip()
        if val_raw in ("|", ">"):
            i += 1
            block = []
            while i < len(lines):
                nl = lines[i]
                if not nl.strip():
                    block.append("")
                    i += 1
                    continue
                if not nl.startswith(" "):
                    break
                block.append(nl.lstrip())
                i += 1
            result[key] = "\n".join(block).strip()
            continue
        if val_raw:
            result[key] = _scalar_value(val_raw)
            i += 1
            continue
        i += 1
        items = []
        while i < len(lines):
            nl = lines[i]
            if not nl.strip():
                i += 1
                continue
            if not nl.startswith(" "):
                break
            s = nl.lstrip()
            if s.startswith("- "):
                it = s[2:].strip()
                if (it.startswith('"') and it.endswith('"')) or \
                   (it.startswith("'") and it.endswith("'")):
                    it = it[1:-1]
                items.append(it)
            i += 1
        result[key] = items
    return result


# ── ① frontmatter 계약 ────────────────────────────────────────

def test_frontmatter_parseable_by_origin():
    text = HG.render(
        title="스포너 구조 변경",
        decision_type="architecture",
        work_id="w-7",
        affected_classes=["UMissionPropsComponent_Spawner", "ABeacon"],
        alternatives_considered=["델리게이트 유지 — 순환 참조로 기각"],
        tags=["Mission"],
        user_quote="스포너가 에셋 브라우저를 직접 열게 해줘",
        body="## 작업 개요\n스포너 선택 흐름 교체.")
    fm = origin_parse(text)
    check("[중요] 대시 리스트가 원전 파서에서 list 로 살아온다 (인라인이면 통째로 버려진다)",
          fm["affected_classes"] == ["UMissionPropsComponent_Spawner", "ABeacon"],
          str(fm.get("affected_classes")))
    check("빈 리스트는 [] (스칼라 오염 없음)", fm["affected_domains"] == [])
    check("user_quote 블록 스칼라가 살아온다",
          fm["user_quote"] == "스포너가 에셋 브라우저를 직접 열게 해줘", str(fm.get("user_quote")))
    check("null 스칼라 규약 (session_id 미지정)", fm["session_id"] is None)
    check("date 가 원전 형식 (YYYY-MM-DD HH:MM — harvest 는 앞을 자른다)",
          re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", str(fm["date"])), str(fm["date"]))
    check("decision_type 이 실린다", fm["decision_type"] == "architecture")
    check("work_id 따옴표 스칼라", fm["work_id"] == "w-7")
    check("본문이 frontmatter 밖에 있다", "## 작업 개요" in text.split("---")[2])


def test_validation_and_filename():
    p = fixture()
    try:
        HG.render(title=" ")
        check("[중요] title 없으면 ValueError", False)
    except ValueError:
        check("[중요] title 없으면 ValueError", True)
    try:
        HG.render(title="x", decision_type="대충")
        check("[중요] decision_type 은 원전 enum 만", False)
    except ValueError:
        check("[중요] decision_type 은 원전 enum 만", True)
    path = Path(HG.write(p, HG.render(title="빔 이펙트: 교체?"), title="빔 이펙트: 교체?"))
    check("[중요] 파일명 규약 — history/YYYY-MM-DD_HHMM_<작업요약>.md (원전 그대로)",
          re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}_.+\.md", path.name)
          and path.parent.name == "history", str(path))
    check("파일명에 금지 문자가 없다", ":" not in path.name and "?" not in path.name, path.name)
    check("클래스 후보 추출 — CamelCase 스템만",
          HG.classes_from_files(["Source/M/UHitBox.cpp", "Source/M/util_str.cpp",
                                 "Source/M/UHitBox.h"]) == ["UHitBox"])


# ── ② 종결 자동 기록 ──────────────────────────────────────────

def test_record_work_terminal():
    p = fixture()
    work = {"work_id": "w-20260817", "title": "히트박스 판정 추가",
            "review_decision": {"decided_by": "requester(.33)",
                                "decided_at": "2026-08-17T00:00:00",
                                "result": "approve", "notes": "판정 반경이 좁다 — 다음에 보정"}}
    tasks = [{"task_id": "t1", "work_id": "w-20260817",
              "target_file": "Source/M/UHitBox.cpp", "header_file": "Source/M/UHitBox.h"},
             {"task_id": "t2", "work_id": "w-20260817",
              "target_file": "Source/M/UHitBox.cpp"}]        # 중복 파일 — 한 번만
    path = Path(HG.record_work_terminal(p, work, tasks, "merged"))
    text = path.read_text(encoding="utf-8")
    fm = origin_parse(text)
    check("[중요] work_id·태그(pipeline+종결)가 실린다",
          fm["work_id"] == "w-20260817" and fm["tags"] == ["pipeline", "merged"],
          f"{fm.get('work_id')} {fm.get('tags')}")
    check("[중요] user_quote = 검수 노트 (사람의 발화 — WHY 신호)",
          fm["user_quote"] == "판정 반경이 좁다 — 다음에 보정", str(fm.get("user_quote")))
    check("클래스 후보가 파일에서 나온다", fm["affected_classes"] == ["UHitBox"])
    check("파일 목록 중복 제거", text.count("Source/M/UHitBox.cpp") == 1,
          str(text.count("Source/M/UHitBox.cpp")))
    check("판정자·종결이 본문에 있다", "requester(.33)" in text and "**merged**" in text)

    p2 = fixture()
    path2 = Path(HG.record_work_terminal(p2, {"work_id": "w-x"}, [], "rejected"))
    fm2 = origin_parse(path2.read_text(encoding="utf-8"))
    check("메타 없는 work 도 기록된다 (제목=work_id · quote=null)",
          fm2["tags"] == ["pipeline", "rejected"] and fm2["user_quote"] is None)


# ── ③ 클라 자리 (.33 MCP) ─────────────────────────────────────

def _load_client():
    import importlib.util
    f = Path(__file__).parent / "clientside" / "client_mcp.py"
    spec = importlib.util.spec_from_file_location("_cm_h", f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_client_tool():
    cm = _load_client()
    calls = []

    def fake_api(method, path, payload=None):
        calls.append((method, path, payload))
        return {"ok": True, "stored_at": "…", "title": payload["title"]}

    cm.dispatch_tool("log_history", {
        "title": "스포너 구조 변경", "decision_type": "architecture",
        "affected_classes": ["ABeacon"], "user_quote": "직접 열게 해줘",
    }, api=fake_api)
    m, path, payload = calls[0]
    check("[중요] 마스터 대행 POST /api/v1/history",
          (m, path) == ("POST", "/api/v1/history"), f"{m} {path}")
    check("본문에 결정 필드가 실린다",
          payload["decision_type"] == "architecture" and payload["affected_classes"]
          and payload["user_quote"], str(sorted(payload)))
    try:
        cm.dispatch_tool("log_history", {"title": " "}, api=fake_api)
        check("[중요] title 비면 클라에서 막는다", False)
    except cm.ClientError:
        check("[중요] title 비면 클라에서 막는다", True)

    from master.auth import REQUESTER_SCOPE
    check("[중요] requester 스코프가 POST /api/v1/history 를 연다",
          ("POST", "/api/v1/history") in REQUESTER_SCOPE, str(REQUESTER_SCOPE))
    tool = next(t for t in cm.TOOLS if t["name"] == "log_history")
    check("규약이 설명에 있다 — trivial 은 안 쓴다", "trivial" in tool["description"])


def main() -> int:
    for fn in (test_frontmatter_parseable_by_origin, test_validation_and_filename,
               test_record_work_terminal, test_client_tool):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_history_gen: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
