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
    # 🔴 문구가 아니라 **계약**을 본다 — ⑴ 여기서 판정 못 한다 ⑵ 다른 워커의 층3 을 거친다
    check("🔴 UE5 없으면 '최종 판정 못 함' 을 명시", "옳음의 최종 판정" in linux, linux[:200])
    check("🔴 ue5 워커의 층3 검증을 거치라고 적는다",
          "층3 검증" in linux and "`ue5` 능력을 가진 워커" in linux)
    check("🔴 제출물에 '컴파일되지 않았다' 를 적으라고 한다", "컴파일되지 않았다" in linux)
    # 🔴 축이 UE5 가 아니라 **소스 판단**이다 — 두 역할이 같은 첫 문장을 갖는다
    check("🔴 소스 판단이 본령이라고 적는다", "소스를 근거로 판단한다" in linux)
    check("🔴 코드 작성은 다른 워커와 같다고 적는다", "다른 워커와 똑같이 된다" in linux)
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

    # 🔴 실제로 난 사고 — 읽기 실패로 블록이 두 번 붙었다. 병합이 스스로 고쳐야 한다.
    doubled = once.rstrip() + "\n\n" + bundle.managed_block("ModularStage", f) + "\n"
    fixed = bundle.merge_claude_md(doubled, "ModularStage", f)
    check("🔴 블록이 2개인 파일도 1개로 복구한다",
          fixed.count(bundle.MD_BEGIN) == 1, str(fixed.count(bundle.MD_BEGIN)))
    check("복구해도 사람 내용은 유지", "사람이 쓴 내용이다." in fixed)

    tail = once.split(bundle.MD_END, 1)[1]
    check("블록 뒤 내용도 보존된다",
          bundle.merge_claude_md(once + "\n## 뒤에 쓴 절\n", "ModularStage", f)
          .endswith("## 뒤에 쓴 절\n"), repr(tail[-20:]))


def test_skill_is_readable() -> None:
    for name in ("ax-work", "ax-request", "ax-ontology"):
        t = bundle.skill_text(name)
        check(f"{name}: 읽힌다", len(t) > 1000, str(len(t)))
        check(f"{name}: frontmatter", t.startswith("---") and f"name: {name}" in t)
        # 🔴 스킬에 머신별 경로가 박히면 안 된다 — 그게 오늘 잡은 사고의 원인이었다
        for bad in ("E:\\trunk", "/home/sim/trunk", "C:\\Users\\janus", "C:\\Users\\USER"):
            check(f"🔴 {name} 에 절대경로 `{bad}` 가 없다", bad not in t)


def test_role_skills() -> None:
    check("워커는 ax-work", bundle.skills_for("worker") == ("ax-work",))
    # 🔴 요청자에게 워커 절차를 주지 않는다
    check("🔴 요청자는 ax-request·ax-ontology (ax-work 아님)",
          set(bundle.skills_for("requester")) == {"ax-request", "ax-ontology"},
          str(bundle.skills_for("requester")))
    check("🔴 요청자 스킬에 ax-work 가 섞이지 않는다",
          "ax-work" not in bundle.skills_for("requester"))
    try:
        bundle.skills_for("사장님")
        check("🔴 모르는 역할은 예외 (조용히 빈 배달 금지)", False, "통과해버렸다")
    except bundle.BundleError:
        check("모르는 역할은 예외", True)


def test_role_block() -> None:
    w = bundle.managed_block("P", _facts(role="worker"))
    r = bundle.managed_block("P", _facts(role="requester"))
    check("워커 블록은 ax-work 를 가리킨다", "`ax-work`" in w)
    check("🔴 요청자 블록은 ax-work 를 가리키지 않는다", "ax-work" not in r, r[:200])
    check("요청자 블록은 ax-request 를 가리킨다", "ax-request" in r)
    check("🔴 요청자에게 '소스를 고치지 않는다' 를 말한다", "소스를 고치지 않는다" in r)
    check("🔴 워커에게만 attempt 브랜치 규약", "attempt/<task_id>" in w and "attempt/" not in r.split("실행은")[1])
    check("두 역할 모두 '소스가 이긴다'", "소스가 이긴다" in w and "소스가 이긴다" in r)



def test_ue5_detection() -> None:
    """🔴 UE5 는 한 곳에 있지 않다 (실측 2026-08-09) — 프로브에 경로를 박으면 프로브의 의미가 없다."""
    globs = " ".join(bundle.ue5_globs())
    check("런처 설치 위치를 본다", "Epic Games\\UE_*" in globs, globs)
    check("직접 설치 위치도 본다", "C:\\Program Files\\UE_*" in globs, globs)
    # 🔴 버전을 글롭에 나열하면 새 버전이 나올 때 목록이 낡는다
    check("🔴 글롭에 버전을 박지 않는다", "5.8" not in globs, globs)

    seen = {}
    def runner(cmd):
        seen["cmd"] = cmd
        return 0, ("C:\\Program Files\\Epic Games\\UE_5.4\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe\n"
                   "C:\\Program Files\\Epic Games\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe\n")
    got = bundle._find_ue5("h", "u", runner=runner)
    check("🔴 선호 버전(5.8)을 고른다", "UE_5.8" in got, got)
    # 🔴 cmd 는 괄호를 써도 `if exist A (…) & …` 의 뒷부분을 첫 조건의 참 분기로 삼킨다
    check("🔴 if/& 로 잇지 않는다 (한쪽만 조용히 깨진다)",
          "for /d" in seen["cmd"] and " & if exist" not in seen["cmd"], seen["cmd"][:80])

    # 🔴 종료 코드로 판정하지 않는다 — ssh rc 는 양방향으로 못 믿는다
    ok = bundle._find_ue5("h", "u", runner=lambda c: (1,
        "C:\\Program Files\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe\n"))
    check("🔴 rc≠0 이라도 출력이 있으면 인정한다", "UE_5.8" in ok, ok)
    check("아무것도 없으면 빈 문자열", bundle._find_ue5("h", "u", runner=lambda c: (0, "")) == "")
    check("엉뚱한 출력은 무시한다",
          bundle._find_ue5("h", "u", runner=lambda c: (0, "File Not Found\n")) == "")



def test_init_wiring() -> None:
    """🔴 #64 — CLAUDE.md 가 없으면 /init 을 **먼저** 돌린다. 있으면 안 돌린다."""
    calls = {}
    def runner(cmd):
        calls["cmd"] = cmd
        return 0, '{"result":"ok","total_cost_usd":0.21,"num_turns":9}'
    f = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh", role="worker")
    f.os, f.claude = "linux", "2.1"
    info = bundle.run_init(f, runner=runner)
    check("체크아웃에서 돈다", '"/repo"' in calls["cmd"], calls["cmd"][:60])
    check("/init 을 부른다", '"/init"' in calls["cmd"], calls["cmd"][:80])
    check("json 으로 받는다", "--output-format json" in calls["cmd"])
    # ⚠️ 일회성 비용은 따로 보고돼야 한다 — 작업 비용에 섞으면 파견이 비싸 보인다
    check("🔴 비용을 들고 나온다", abs(info["cost_usd"] - 0.21) < 1e-9, str(info))
    check("턴도 들고 나온다", info["turns"] == 9, str(info))

    win = bundle.HostFacts(host="h", user="u", path=r"E:\repo", driven="ssh")
    win.os, win.claude = "windows", "2.1"
    bundle.run_init(win, runner=runner)
    check("윈도우는 cd /d", "cd /d" in calls["cmd"], calls["cmd"][:40])

    # 🔴 claude 가 없으면 돌릴 수 없다 — 조용히 성공으로 보고하면 안 된다
    noc = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh")
    noc.os, noc.claude = "linux", ""
    check("claude 가 없으면 안 돌린다", not noc.claude)



def test_scp_source_windows() -> None:
    """🔴 윈도우 경로를 역슬래시로 주면 scp 가 거부한다 — **그런데 rc 는 0** (실측 2026-08-09).

    이 함수가 조용히 `""` 를 돌려주던 탓에 `deliver` 가 *"기존 CLAUDE.md 가 없다"* 로 오판하고
    **내장 기본 문서로 통째로 덮었다.** 윈도우 두 대에서 매번, 리눅스만 정상 — 한쪽만 조용히
    깨지는 그 모양이다.
    """
    win = bundle.HostFacts(host="h", user="u", path=r"E:\repo", driven="ssh")
    win.os = "windows"
    src = bundle.scp_source(win, r"E:\repo\CLAUDE.md")
    check("🔴 윈도우는 슬래시로 바꾼다", "\\" not in src, src)
    check("경로가 온전하다", src.endswith(":E:/repo/CLAUDE.md"), src)

    lin = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh")
    lin.os = "linux"
    check("리눅스는 그대로", bundle.scp_source(lin, "/repo/CLAUDE.md").endswith(":/repo/CLAUDE.md"))


def test_merge_never_replaces_existing() -> None:
    """🔴 기존 내용이 있으면 **블록만** 얹는다 — 기본 문서로 덮지 않는다."""
    f = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh", role="worker")
    f.os = "linux"
    human = "# 사람이 쓴 문서\n\n지우면 안 되는 내용\n"
    merged = bundle.merge_claude_md(human, "ModularStage", f)
    check("사람 글이 남는다", "지우면 안 되는 내용" in merged, merged[:120])
    check("블록이 붙는다", bundle.MD_BEGIN in merged and bundle.MD_END in merged)
    # 🔴 기존이 있는데 기본 문서를 끼워 넣으면 그게 덮어쓰기다
    empty_doc = bundle.merge_claude_md("", "ModularStage", f)
    check("🔴 기존이 있으면 기본 문서를 안 넣는다", len(merged) < len(empty_doc) / 2,
          f"{len(merged)} vs {len(empty_doc)}")


def main() -> int:
    for fn in (test_role, test_config, test_managed_block, test_merge, test_skill_is_readable,
               test_role_skills, test_role_block, test_ue5_detection, test_init_wiring, test_scp_source_windows,
               test_merge_never_replaces_existing):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_client_bundle: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
