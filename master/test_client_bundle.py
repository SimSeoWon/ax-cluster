"""워커 번들 — 역할(`role`) · CLAUDE.md 병합 · config 내용 (레드마인 #21).

**SSH 를 타지 않는다.** 여기서 지키는 계약은 전송이 아니라 **무엇을 누구에게 주는가**다:
요청자에게 파견하지 않는가 · 사람이 쓴 문서를 덮지 않는가 · config 에 비밀이 없는가.

`python3 master/test_client_bundle.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import bundle                                    # noqa: E402
from master.projects.config import ROLE_REQUESTER, ROLE_WORKER, Workshop, ConfigError  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


# ── 역할 ────────────────────────────────────────────────────────

def test_role() -> None:
    w = Workshop(host="h", driven="ssh", path="/p", user="u", role=ROLE_WORKER)
    check("워커는 파견 대상", w.drivable and w.reachable)

    r = Workshop(host="h", driven="ssh", path="/p", user="u", role=ROLE_REQUESTER)
    # 🔴 이 테스트가 이 필드의 존재 이유다 — 사람의 기계에 일감을 밀어넣지 않는다
    check("🔴 요청자는 SSH 가 열려 있어도 파견 대상이 아니다", not r.drivable, "drivable=True")
    check("요청자도 닿기는 한다 (번들 배달·조회)", r.reachable)

    i = Workshop(host="h", driven="interactive", role=ROLE_WORKER)
    check("interactive 는 파견 불가", not i.drivable and not i.reachable)

    try:
        Workshop(host="h", driven="ssh", path="/p", user="u", role="보스").validate()
        check("🔴 모르는 role 은 거부", False, "통과해버렸다")
    except ConfigError:
        check("모르는 role 은 거부", True)

    d = Workshop.from_dict("h", {"driven": "ssh", "path": "/p", "user": "u"})
    check("role 미기재는 worker 로 (기존 파일 호환)", d.role == ROLE_WORKER, d.role)
    check("to_dict 에 role 이 실린다", Workshop(host="h").to_dict().get("role") == ROLE_WORKER)


# ── config 내용 ─────────────────────────────────────────────────

def _facts(**over):
    f = bundle.HostFacts(host="192.168.0.43", user="sim", path="/home/sim/trunk/ModularStage",
                         driven="ssh", os="linux", home="/home/sim",
                         claude="2.1.222", agy=False, ollama_models=4, ue5="",
                         checkout_ok=True, commit="bc4b38f")
    for k, v in over.items():
        setattr(f, k, v)
    return f


def test_config() -> None:
    cfg = bundle.config_for("ModularStage", _facts())
    # 🔴 비밀이 들어가면 이 파일이 유출 경로가 된다
    blob = str(cfg).lower()
    check("🔴 config 에 비밀이 없다",
          not any(k in blob for k in ("token", "bearer", "password", "secret")), blob[:80])
    check("체크아웃 경로가 실린다", cfg["checkout"]["path"] == "/home/sim/trunk/ModularStage")
    check("UE5 없으면 능력이 비어 있다", cfg["capabilities"] == [], str(cfg["capabilities"]))
    check("백엔드는 실측값", cfg["backends"]["ollama_models"] == 4 and cfg["backends"]["agy"] is False)
    check("부산물 경로를 알려준다", ".ax/work" in cfg["_layout"]["work"])

    win = bundle.config_for("ModularStage", _facts(
        os="windows", ue5=r"C:\UE\UnrealEditor-Cmd.exe", agy=True, ollama_models=7))
    check("UE5 있으면 ue5 능력", "ue5" in win["capabilities"], str(win["capabilities"]))
    check("윈도우면 windows 능력", "windows" in win["capabilities"])


def test_managed_block() -> None:
    linux = bundle.managed_block("ModularStage", _facts())
    check("마커가 있다", bundle.MD_BEGIN in linux and bundle.MD_END in linux)
    # 🔴 능력의 **결과**를 적는다 — "ue5 ❌" 만으로는 무슨 뜻인지 알 수 없다
    check("🔴 UE5 없으면 '층3 검증 불가' 를 명시", "층3 검증을 여기서 할 수 없다" in linux)
    check("🔴 uasset 손대지 말라고 적는다", "uasset" in linux and "손대지 말 것" in linux)
    check("판단 기준이 소스임을 적는다", "소스가 이긴다" in linux)
    check("경로를 박지 않고 실측값을 넣는다", "/home/sim/trunk/ModularStage" in linux)

    win = bundle.managed_block("ModularStage", _facts(
        os="windows", ue5=r"C:\UE\UnrealEditor-Cmd.exe"))
    check("UE5 있으면 층3 검증 가능이라 적는다", "층3 결정적 검증" in win)
    check("UE5 있으면 '할 수 없는 것' 이 없다", "(없음)" in win)


# ── CLAUDE.md 병합 ──────────────────────────────────────────────

def test_merge() -> None:
    f = _facts()

    made = bundle.merge_claude_md("", "ModularStage", f)
    check("없으면 정본 본문 + 블록을 만든다",
          "# CLAUDE.md" in made and bundle.MD_BEGIN in made, made[:60])

    human = "# 내 프로젝트\n\n사람이 쓴 내용이다.\n"
    once = bundle.merge_claude_md(human, "ModularStage", f)
    # 🔴 이게 핵심이다 — 사람이 쓴 것을 덮으면 안 된다
    check("🔴 기존 문서를 덮지 않고 블록만 덧붙인다",
          once.startswith("# 내 프로젝트") and "사람이 쓴 내용이다." in once)
    check("블록이 뒤에 붙는다", once.index("사람이 쓴 내용") < once.index(bundle.MD_BEGIN))

    twice = bundle.merge_claude_md(once, "ModularStage", f)
    check("🔴 두 번 돌려도 블록이 하나다 (멱등)",
          twice.count(bundle.MD_BEGIN) == 1, str(twice.count(bundle.MD_BEGIN)))
    check("사람 내용은 그대로", "사람이 쓴 내용이다." in twice)

    changed = bundle.merge_claude_md(once, "ModularStage",
                                     _facts(ue5=r"C:\UE\x.exe", os="windows"))
    check("블록 내용은 갱신된다", "층3 결정적 검증" in changed)
    check("갱신해도 사람 내용은 유지", "사람이 쓴 내용이다." in changed)

    tail = once.split(bundle.MD_END, 1)[1]
    check("블록 뒤 내용도 보존된다",
          bundle.merge_claude_md(once + "\n## 뒤에 쓴 절\n", "ModularStage", f)
          .endswith("## 뒤에 쓴 절\n"), repr(tail[-20:]))


def test_skill_is_readable() -> None:
    t = bundle.skill_text()
    check("스킬 원본이 읽힌다", len(t) > 1000, str(len(t)))
    check("frontmatter 가 있다", t.startswith("---") and "name: ax-work" in t)
    # 🔴 스킬에 머신별 경로가 박히면 안 된다 — 그게 오늘 잡은 사고의 원인이었다
    for bad in ("E:\\trunk", "/home/sim/trunk", "C:\\Users\\janus", "C:\\Users\\USER"):
        check(f"🔴 스킬에 절대경로 `{bad}` 가 없다", bad not in t)


def main() -> int:
    for fn in (test_role, test_config, test_managed_block, test_merge, test_skill_is_readable):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_client_bundle: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
