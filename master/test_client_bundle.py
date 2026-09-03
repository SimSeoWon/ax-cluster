"""워커 번들 — 역할(`role`) · CLAUDE.md 병합 · config 내용 (레드마인 #21).

**SSH 를 타지 않는다.** 여기서 지키는 계약은 전송이 아니라 **무엇을 누구에게 주는가**다:
요청자에게 파견하지 않는가 · 사람이 쓴 문서를 덮지 않는가 · config 에 비밀이 없는가.

`python3 master/test_client_bundle.py`
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# 🔴 [중요] **테스트가 스스로 환경을 세운다** (2026-09-04).
#
# `AX_PROJECTS_ROOT` 가 없으면 `managed_block` 이 레지스트리를 못 읽어 **실측 절을 조용히
# 비운다**(`ConfigError` 를 잡는다). 그래서 이 파일은 실행 방법에 따라 결과가 갈렸다 —
# 그냥 돌리면 292/294, 환경변수를 주면 **294/294**.
#
# [주의] 그것을 오늘 세 번 *"기존 실패라 무관"* 으로 넘겼다. 무관한 게 아니라 **테스트가
# 환경을 안 갖추고 돈 것**이었다. 사용자: *"기존에 실패하면 안고칠꺼야? 작업이 끝난뒤 체크해야지"*.
#
# 같은 부류를 오늘 둘 더 봤다 — 재개 안내문의 `AX_PROJECTS_ROOT` 누락 · `#345`(테스트가
# 라이브 큐에 결합). **실행 조건을 파일 안에 박으면 「어떻게 돌렸나」가 결과를 바꾸지 않는다.**
os.environ.setdefault("AX_PROJECTS_ROOT", str(_REPO))

from master.client import bundle, spec                              # noqa: E402
from master.projects.config import ROLE_REQUESTER, ROLE_WORKER, Workshop, ConfigError  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── 역할 ────────────────────────────────────────────────────────

def test_role() -> None:
    w = Workshop(host="h", driven="ssh", path="/p", user="u", role=ROLE_WORKER)
    check("워커는 파견 대상", w.drivable and w.reachable)

    r = Workshop(host="h", driven="ssh", path="/p", user="u", role=ROLE_REQUESTER)
    # [중요] 이 테스트가 이 필드의 존재 이유다 — 사람의 기계에 일감을 밀어넣지 않는다
    check("[중요] 요청자는 SSH 가 열려 있어도 파견 대상이 아니다", not r.drivable, "drivable=True")
    check("요청자도 닿기는 한다 (번들 배달·조회)", r.reachable)

    i = Workshop(host="h", driven="interactive", role=ROLE_WORKER)
    check("interactive 는 파견 불가", not i.drivable and not i.reachable)

    try:
        Workshop(host="h", driven="ssh", path="/p", user="u", role="보스").validate()
        check("[중요] 모르는 role 은 거부", False, "통과해버렸다")
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
    # [중요] 비밀이 들어가면 이 파일이 유출 경로가 된다
    blob = str(cfg).lower()
    check("[중요] config 에 비밀이 없다",
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
    # [중요] 능력의 **결과**를 적는다 — "ue5 [실패]" 만으로는 무슨 뜻인지 알 수 없다
    # [중요] 문구가 아니라 **계약**을 본다 — ⑴ 여기서 판정 못 한다 ⑵ 다른 워커의 층3 을 거친다
    check("[중요] UE5 없으면 '최종 판정 못 함' 을 명시", "옳음의 최종 판정" in linux, linux[:200])
    check("[중요] ue5 워커의 층3 검증을 거치라고 적는다",
          "층3 검증" in linux and "`ue5` 능력을 가진 워커" in linux)
    check("[중요] 제출물에 '컴파일되지 않았다' 를 적으라고 한다", "컴파일되지 않았다" in linux)
    # [중요] 축이 UE5 가 아니라 **소스 판단**이다 — 두 역할이 같은 첫 문장을 갖는다
    check("[중요] 소스 판단이 본령이라고 적는다", "소스를 근거로 판단한다" in linux)
    check("[중요] 코드 작성은 다른 워커와 같다고 적는다", "다른 워커와 똑같이 된다" in linux)
    check("[중요] uasset 손대지 말라고 적는다", "uasset" in linux and "손대지 말 것" in linux)
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
    # [중요] 이게 핵심이다 — 사람이 쓴 것을 덮으면 안 된다
    check("[중요] 기존 문서를 덮지 않고 블록만 덧붙인다",
          once.startswith("# 내 프로젝트") and "사람이 쓴 내용이다." in once)
    check("블록이 뒤에 붙는다", once.index("사람이 쓴 내용") < once.index(bundle.MD_BEGIN))

    twice = bundle.merge_claude_md(once, "ModularStage", f)
    check("[중요] 두 번 돌려도 블록이 하나다 (멱등)",
          twice.count(bundle.MD_BEGIN) == 1, str(twice.count(bundle.MD_BEGIN)))
    check("사람 내용은 그대로", "사람이 쓴 내용이다." in twice)

    changed = bundle.merge_claude_md(once, "ModularStage",
                                     _facts(ue5=r"C:\UE\x.exe", os="windows"))
    check("블록 내용은 갱신된다", "층3 결정적 검증" in changed)
    check("갱신해도 사람 내용은 유지", "사람이 쓴 내용이다." in changed)

    # [중요] 실제로 난 사고 — 읽기 실패로 블록이 두 번 붙었다. 병합이 스스로 고쳐야 한다.
    doubled = once.rstrip() + "\n\n" + bundle.managed_block("ModularStage", f) + "\n"
    fixed = bundle.merge_claude_md(doubled, "ModularStage", f)
    check("[중요] 블록이 2개인 파일도 1개로 복구한다",
          fixed.count(bundle.MD_BEGIN) == 1, str(fixed.count(bundle.MD_BEGIN)))
    check("복구해도 사람 내용은 유지", "사람이 쓴 내용이다." in fixed)

    tail = once.split(bundle.MD_END, 1)[1]
    check("블록 뒤 내용도 보존된다",
          bundle.merge_claude_md(once + "\n## 뒤에 쓴 절\n", "ModularStage", f)
          .endswith("## 뒤에 쓴 절\n"), repr(tail[-20:]))


def test_skill_is_readable() -> None:
    for name in ("ax-work", "ax-infer", "ax-request", "ax-ontology", "ax-review"):
        t = bundle.skill_text(name)
        check(f"{name}: 읽힌다", len(t) > 1000, str(len(t)))
        check(f"{name}: frontmatter", t.startswith("---") and f"name: {name}" in t)
        # [중요] 스킬에 머신별 경로가 박히면 안 된다 — 그게 오늘 잡은 사고의 원인이었다
        for bad in ("E:\\trunk", "/home/sim/trunk", "C:\\Users\\janus", "C:\\Users\\USER"):
            check(f"[중요] {name} 에 절대경로 `{bad}` 가 없다", bad not in t)


def test_role_skills() -> None:
    # 🔴 [중요] 정본 ⑸ (사용자 확정 2026-09-02) — 워커는 **`ax-work`** 계약을 받는다.
    # [주의] 실측 2026-09-02 00:02 의 교훈은 그대로 산다 — 매니페스트를 없앤 뒤 스킬 문구가
    #    남아 4/4 가 `BLOCKED` 됐고 워커가 근거로 스킬을 댔다("Per skill §2/§8").
    #    **명령줄과 문서가 갈리면 문서가 이긴다** — 그래서 `ax-work` SKILL.md 본문도 같이
    #    정본으로 고쳤다(git 금지·`RESULT: DONE` 한 줄).
    check("워커는 ax-work + ax-infer",
          tuple(bundle.skills_for("worker")) == ("ax-work", "ax-infer"),
          str(bundle.skills_for("worker")))
    check("  [중요] 파일은 남아 있다 (되돌릴 수 있음 — §8.4)",
          (Path(bundle.__file__).with_name("skills") / "ax-work" / "SKILL.md").is_file())
    # [중요] 요청자에게 워커 절차를 주지 않는다
    # [중요] `ax-review` 는 원전의 「리더(TD·팀장)」 자리다 — 그 그룹이 없어 요청자가 그 판단을
    #    한다(사용자 확정 2026-08-16). 검수는 **판단**이지 구현이 아니라 이 역할에 맞는다.
    check("[중요] 요청자는 ax-request·ax-ontology·ax-review (ax-work 아님)",
          set(bundle.skills_for("requester")) == {"ax-request", "ax-ontology", "ax-review"},
          str(bundle.skills_for("requester")))
    check("[중요] 요청자 스킬에 ax-work 가 섞이지 않는다",
          "ax-work" not in bundle.skills_for("requester"))
    # [중요] 스킬 원문이 실재해야 배달이 성립한다 — 이름만 등록하면 배달에서 죽는다
    for n in bundle.skills_for("requester") + bundle.skills_for("worker"):
        check(f"스킬 원문이 있다: {n}", bundle.skill_text(n).startswith("---"))


def test_mcp_json_merge() -> None:
    """소 3.8.4 — .mcp.json 은 사람 항목을 보존하고, 깨진 파일은 덮지 않는다."""
    import json as _json
    f = _facts(os="windows")
    e = bundle.mcp_entry_for(f)
    check("[중요] 윈도우는 py 다 (스토어 스텁 함정)", e["command"] == "py", str(e))
    check("경로는 상대·슬래시 (cwd=체크아웃)", e["args"][0].startswith(".ax/lib/"), str(e))
    check("리눅스는 python3", bundle.mcp_entry_for(_facts())["command"] == "python3")

    merged = _json.loads(bundle.merge_mcp_json(
        '{"mcpServers": {"내것": {"command": "x"}}, "다른키": 1}', f))
    check("[중요] 사람이 쓴 항목을 보존한다", merged["mcpServers"]["내것"]["command"] == "x")
    check("다른 최상위 키도 보존", merged.get("다른키") == 1)
    check("ax-client 가 들어간다", merged["mcpServers"]["ax-client"] == e)
    fresh = _json.loads(bundle.merge_mcp_json("", f))
    check("없으면 새로 만든다", fresh["mcpServers"]["ax-client"] == e)
    again = _json.loads(bundle.merge_mcp_json(bundle.merge_mcp_json("", f), f))
    check("두 번 돌려도 항목 하나 (멱등)", list(again["mcpServers"]) == ["ax-client"])
    try:
        bundle.merge_mcp_json("{깨진", f)
        check("[중요] 깨진 JSON 은 덮지 않고 멈춘다", False, "통과해 버렸다")
    except bundle.BundleError:
        check("[중요] 깨진 JSON 은 덮지 않고 멈춘다", True)
    try:
        bundle.merge_mcp_json("[1,2]", f)
        check("최상위가 객체가 아니면 멈춘다", False)
    except bundle.BundleError:
        check("최상위가 객체가 아니면 멈춘다", True)


def test_role_payload() -> None:
    """[중요] 요청자에게는 **파이썬 모듈**도 간다 — 절차를 문서에만 쓰면 로직이 두 벌이 된다."""
    pay = bundle.payloads_for("requester")
    check("[중요] 클라 MCP 가 요청자 페이로드에 있다 (#201)",
          "clientside/client_mcp.py" in pay, str(pay))
    check("요청자에게 review·build 의 의존 폐포가 간다",
          set(pay) == {"clientside/client_mcp.py", "clientside/ontology_cache.py",
                       "layer3_verify.py", "source_text.py", "utf8.py",
                       "work/branch_names.py", "work/coordinator.py",
                       "work/review.py", "work/skeleton_gate.py", "work/build_local.py"},
          str(pay))
    # [주의] 이 칸은 세 번 움직였다: 옛 계약("워커에는 안 간다") → `#204` 로 claimer 폐포 추가
    #    → 2026-08-23 클라 MCP 추가(`#267`·`#261`) → **2026-08-27 claimer 폐포 제거**(`#320`,
    #    상주 전폐). 워커는 이제 마스터의 SSH push 로 돈다.
    check("[중요] 워커에는 클라 MCP + 빌드 사슬이 간다 · **claimer 폐포는 없다** (#320)",
          set(bundle.payloads_for("worker")) == {
              "clientside/client_mcp.py", "clientside/ontology_cache.py",
              "work/build_local.py",
              "work/skeleton_gate.py", "layer3_verify.py", "source_text.py", "utf8.py"},
          str(bundle.payloads_for("worker")))
    check("[중요] 상주 폐포가 워커 payload 에 되살아나지 않는다 (#320 — 되살리려면 결정이 먼저다)",
          not {"work/claimer.py", "work/ax_safety.py"} & set(bundle.payloads_for("worker")),
          str(bundle.payloads_for("worker")))
    check("[중요] MCP 폐포가 함께 간다 (옆 파일이 빠지면 조회 도구가 조용히 죽는다)",
          {"clientside/client_mcp.py", "clientside/ontology_cache.py"}
          <= set(bundle.payloads_for("worker")))
    check("[중요] 워커 페이로드에 판단 모듈(review·coordinator)은 없다 — κ.0 경계",
          not {"work/review.py", "work/coordinator.py"} & set(bundle.payloads_for("worker")))
    # [주의] **원문은 저장소에서, 자리는 배달 경로에서** (#262). 한 값으로 쓰면 재배치 뒤에
    #    「원문이 있다」가 배달 위치를 검사하는 말이 된다.
    for dest, src in bundle.payload_pairs("requester"):
        check(f"배달할 원문이 실재한다: {src} → {dest}",
              len(bundle.payload_text(src)) > 100)
    # [중요] 배치가 저장소를 미러링해야 `from ..layer3_verify import …` 가 산다
    check("[중요] 저장소 배치를 미러링한다 (평면이 아니다)",
          any("/" in n for n in pay) and "layer3_verify.py" in pay, str(pay))
    check("패키지 디렉토리를 빠짐없이 센다",
          set(bundle.payload_dirs("requester")) == {"", "clientside", "work"},
          str(bundle.payload_dirs("requester")))
    # [중요] 폐포 검사 — AST 전수. 첫 판은 `^from \.` 정규식이라 **들여쓰인 지연 임포트**를
    #    못 봤고, #197 실 구동이 그 구멍(layer3 → source_text)에서 죽었다. 어느 깊이든
    #    상대 임포트는 전부 잡고, 배달 안 되는 것은 **가드(try/except ImportError) 안**이어야 한다.
    import ast as _ast
    delivered = {n[:-3].replace("/", ".") for n in pay}          # 예: work.review
    delivered |= {d.rsplit(".", 1)[-1] for d in delivered}       # 단축명도 (from . import x)
    GUARDED_OK = {"runner", "client.bundle", "client"}           # 명시적 가드 화이트리스트
    # [중요] 상대 임포트는 **배달된 트리**에서 해석되므로 `n` 은 배달 경로여야 하고, 파싱할
    #    원문은 **저장소**에서 와야 한다 (#262). 두 값이 같던 때는 구별이 안 보였다.
    for n, src_ in bundle.payload_pairs("requester"):
        tree_ = _ast.parse(bundle.payload_text(src_))
        guarded_nodes = set()
        for t_ in _ast.walk(tree_):
            if isinstance(t_, _ast.Try) and any(
                    isinstance(h.type, _ast.Name) and h.type.id == "ImportError"
                    for h in t_.handlers if h.type is not None):
                for inner in _ast.walk(t_):
                    guarded_nodes.add(id(inner))
        for node in _ast.walk(tree_):
            if not (isinstance(node, _ast.ImportFrom) and node.level):
                continue
            base = ".".join(filter(None, [str(node.module or "")]))
            targets = ([base] if base else []) or [a.name for a in node.names]
            pkg_dir = n.rsplit("/", 1)[0] if "/" in n else ""
            for tgt in targets:
                # 상대 경로를 페이로드 기준으로 해석 (level=1 → 같은 디렉토리, 2 → 상위)
                if node.level == 1 and pkg_dir:
                    resolved = f"{pkg_dir}.{tgt}"
                else:
                    resolved = tgt
                ok = (resolved in delivered or tgt in delivered
                      or tgt in GUARDED_OK and id(node) in guarded_nodes)
                check(f"[중요] {n} L{node.lineno} 상대 임포트 `{tgt}` — 배달되거나 가드됨",
                      ok, f"해석={resolved} · 가드={'예' if id(node) in guarded_nodes else '아니오'}")
    check("패키지 초기화 파일이 「손대지 말 것」을 말한다",
          "손으로 고치지 말 것" in bundle.PAYLOAD_INIT, bundle.PAYLOAD_INIT[:60])
    try:
        bundle.payloads_for("사장님")
        check("[중요] 모르는 역할은 예외", False, "조용히 빈 튜플을 돌려줬다")
    except bundle.BundleError:
        check("[중요] 모르는 역할은 예외", True)
    try:
        bundle.skills_for("사장님")
        check("[중요] 모르는 역할은 예외 (조용히 빈 배달 금지)", False, "통과해버렸다")
    except bundle.BundleError:
        check("모르는 역할은 예외", True)


def test_payload_split() -> None:
    """[중요] **#262 — 저장소 위치와 배달 위치를 갈랐다. 배달 위치는 한 글자도 변하면 안 된다.**

    왜 이 테스트가 있나: 배달 위치는 함부로 못 바꾼다. `.33` 의 `.mcp.json` args 가 그 값이다
    (`mcp_entry_for`). **저장소 재배치(#263·#264)가 이 목록을 흔들면 배달이 죽는다** — 그때 이
    테스트가 먼저 죽어야 한다.
    [주의] 종전에는 이유가 하나 더 있었다 — `.2` schtasks·`.43` cron 이 `axmaster.work.claimer`
    로 상주를 불렀다. 상주는 `#320`(2026-08-27)으로 철거됐다.
    """
    FROZEN = {
        "requester": ("clientside/client_mcp.py", "clientside/ontology_cache.py",
                      "layer3_verify.py", "source_text.py", "utf8.py",
                      "work/branch_names.py", "work/coordinator.py", "work/review.py",
                      "work/skeleton_gate.py", "work/build_local.py"),
        # [주의] 동결값을 **결정으로** 갱신한다 (2026-08-23, `#267`) — 이 동결의 목적은
        #    *사고로* 바뀌는 것을 막는 것이고, 결정된 변경은 기준선을 옮기는 것이 맞다.
        "worker": ("clientside/client_mcp.py", "clientside/ontology_cache.py",
                   "work/build_local.py",
                   "work/skeleton_gate.py", "layer3_verify.py", "source_text.py",
                   "utf8.py"),
    }
    for role, want in FROZEN.items():
        got = bundle.payloads_for(role)
        check(f"[중요] {role} 의 **배달 위치**가 동결값과 순서까지 같다",
              got == want, f"실제={got}")
    f = bundle.HostFacts(host="h", user="u", path="p", driven="ssh", role="requester")
    check("[중요] `.mcp.json` args 가 배달 위치와 맞물린다",
          bundle.mcp_entry_for(f)["args"]
          == [f"{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}/clientside/client_mcp.py"],
          str(bundle.mcp_entry_for(f)))
    # 쌍의 순서 관례 — workshop_files 와 같아야 한다 (한 파일에 관례 둘이면 다음에 갈린다)
    for dest, src in bundle.payload_pairs("worker"):
        check(f"쌍은 (배달, 저장소) 순서다: {dest}", "/" in dest or dest.endswith(".py"))
        check(f"저장소 원문이 실재한다: {src}", len(bundle.payload_text(src)) > 100)
    # [중요] **저장소 위치도 동결한다** (#263 이후). 갈린 곳은 `client/runtime/` 둘뿐이고
    #    나머지는 `master/<배달경로>` 미러링이다 — 사용자 결정 ⓒ(빌드 사슬은 `master/` 에
    #    남는다, `layer3_verify` 를 상대경로로 올려다보기 때문). 의도하지 않은 갈림도 여기서 죽는다.
    SPLIT = {"clientside/client_mcp.py": "client/runtime/client_mcp.py",
             "clientside/ontology_cache.py": "client/runtime/ontology_cache.py"}
    for role in FROZEN:
        for dest, src in bundle.payload_pairs(role):
            want = SPLIT.get(dest, f"master/{dest}")
            check(f"[중요] 저장소 위치가 동결값이다: {dest} ← {src}", src == want, f"기대={want}")
    check("[중요] 빌드 사슬은 master/ 에 남는다 (ⓒ) — layer3_verify 상대 임포트가 산다",
          all(src.startswith("master/work/")
              for dest, src in bundle.payload_pairs("worker")
              if "build_local" in dest or "skeleton_gate" in dest),
          str(bundle.payload_pairs("worker")))
    try:
        bundle.payload_pairs("사장님")
        check("[중요] 모르는 역할은 예외 (payload_pairs)", False, "조용히 돌려줬다")
    except bundle.BundleError:
        check("[중요] 모르는 역할은 예외 (payload_pairs)", True)


def test_deliver_removes_deprecated_skills() -> None:
    """[중요] **`#232` 완결 — `deliver` 가 폐지 스킬을 지운다** (2026-09-02).

    실측: `spec.DEPRECATED_SKILLS` 주석은 *"`deliver` 가 지운다"* 였는데 **구현이 없었다.**
    `plan` 은 *"지우는 것은 아직 하지 않는다 (#232)"* 를 정직하게 찍고 있었고 `check` 는 남은
    것을 이름으로 답했다 — 두 표면은 맞았고 가운데가 비어 있었다. `ax-work` 배달을 멈춘 날
    `check` 가 *"폐지 스킬이 남아 있다: ax-work"* 로 잡아 드러났다.
    """
    calls: list = []

    def fake_ssh(host, user, cmd, *, timeout=None):
        calls.append(cmd)
        # probe 는 「사라졌다」로 답한다 (삭제가 성공한 정상 경로)
        if "GONE" in cmd:
            return 0, "GONE"
        return 0, ""

    saved = bundle._ssh
    bundle._ssh = fake_ssh
    try:
        f = _facts(role="worker")
        got = [bundle._remote_rm_dir(f, f".claude/skills/{n}")
               for n in spec.removals_for("worker")["skills"]]
        check("[중요] 폐지 스킬마다 삭제를 시도한다",
              len(got) == len(spec.removals_for("worker")["skills"]), str(got))
        check("  전부 [완료] 로 답한다", all("[완료]" in g for g in got), str(got))
        # [주의] `ax-work` 는 삭제 대상이 **아니다** — 정본 ⑸ 의 계약이다
        check("[중요] `ax-work` 는 삭제 대상이 아니다",
              not any("ax-work" in g for g in got), str(got))
        check("[주의] 디렉토리째 지운다 (SKILL.md 만 지우면 빈 디렉토리가 남는다)",
              any("rmdir /s /q" in c or "rm -rf" in c for c in calls), str(calls[:3]))
        check("  지운 뒤 되확인한다 (「지웠다」를 확인 없이 말하지 않는다)",
              any("GONE" in c for c in calls), str(calls[:4]))
    finally:
        bundle._ssh = saved

    # [중요] **fail-open** — 삭제 실패가 배달을 막지 않는다. 사유를 문자열로 돌려준다.
    def failing_ssh(host, user, cmd, *, timeout=None):
        if "GONE" in cmd:
            return 0, "LEFT"
        return 1, "권한 없음"

    bundle._ssh = failing_ssh
    try:
        r = bundle._remote_rm_dir(_facts(role="worker"), ".claude/skills/ax-work")
        check("[중요] 실패해도 예외를 던지지 않는다 (fail-open)", isinstance(r, str), repr(r))
        check("  사유를 말한다", "[주의]" in r, r)
    finally:
        bundle._ssh = saved

    # [주의] 오버레이로 되살린 이름은 지우지 않는다 — `removals_for` 가 이미 그렇게 만들어져 있다
    revived = spec.ProjectInit(extra_skills={"worker": ("ax-work",)})
    check("[중요] 오버레이로 되살린 이름은 제거 목록에서 빠진다",
          "ax-work" not in spec.removals_for("worker", revived)["skills"],
          str(spec.removals_for("worker", revived)["skills"]))


def test_role_block() -> None:
    w = bundle.managed_block("P", _facts(role="worker"))
    r = bundle.managed_block("P", _facts(role="requester"))
    # 🔴 정본 ⑸ — 워커 블록은 `ax-work` 를 가리킨다. 요청자에게는 여전히 주지 않는다
    #    (사람이 편집 중인 트리에서 에이전트가 파일을 고치는 것이 더티 체크가 막던 사고다).
    check("워커 블록은 ax-work 를 가리킨다", "ax-work" in w, w[:200])
    check("워커 블록은 ax-infer 도 가리킨다", "ax-infer" in w, w[:200])
    check("[중요] 요청자 블록은 ax-work 를 가리키지 않는다", "ax-work" not in r, r[:200])
    check("요청자 블록은 ax-request 를 가리킨다", "ax-request" in r)
    # [중요] 2026-08-20 계약 변경 (사용자 확정) — 이식본이 「분배」 한 차선으로 좁혔던 것을
    #    원전 규칙으로 되돌렸다. 옛 테스트는 *"요청자에게 소스를 고치지 않는다고 말한다"* 를
    #    고정하고 있었다 — **그 문장이 요구를 좁힌 자리**였다. 지금 고정하는 것은 분기 자체다.
    check("[중요] 요청자 블록이 분기를 말한다 (직접 처리 vs 분해·분배)",
          "직접 처리" in r and "분해·분배" in r, r[-800:])
    check("[중요] 원전의 경계를 그대로 싣는다 (단일 클래스 · 신규 3개 이상 + 관계)",
          "단일 클래스" in r and "신규 파일 3개 이상" in r, r[-800:])
    check("[중요] a/b/c 를 환경 상태로 거르지 말라고 말한다 (원전 BLOCKING)",
          "a/b/c" in r and "자동 거르지 말 것" in r, r[-800:])
    check("[중요] 등재는 마스터 큐 한 곳 (진실의 원천)", "마스터 큐 한 곳으로만" in r)
    check("[주의] 직접 처리해도 사람의 트리라는 경고는 남는다",
          "reset --hard" in r and ".uasset" in r)
    check("[중요] 워커에게만 attempt 작업경로 규약",
          "attempt/<task_id>" in w and "attempt/<task_id>" not in r)
    check("요청자는 attempt 브랜치를 만들지 않는다고 말한다",
          "`attempt/` 브랜치를" in r and "만들지 않는다" in r)
    check("두 역할 모두 '소스가 이긴다'", "소스가 이긴다" in w and "소스가 이긴다" in r)



def test_workshop_delivery() -> None:
    """작업장 자산 배달 (#226 4번) — **손으로 맞추던 것을 배달 경로에 넣었다.**

    3번까지 저장소와 `.33` 을 scp 로 맞췄고, 그 상태로는 조용히 갈린다. 여기서 재는 것:
      ① 역할 게이팅 — 워커에게는 **안 보낸다**(실측: `.2`·`.43` 에 agents·skills 0건)
      ② 무엇을 보내고 무엇을 안 보내는가 (README·mcp.json 은 배달물이 아니다)
      ③ [중요] **개행** — 병합이 CRLF/LF 를 섞는다. 해시 대조는 그걸 못 잡는다
      ④ [중요] **마커 없는 원격은 건드리지 않는다** — 사람 문서를 날리지 않는다
    """
    ws = bundle.workshop_files("requester")
    if not ws:
        check("작업장 자산이 아직 반입되지 않았다 — 건너뜀", True)
        return
    check("요청자는 자산을 받는다 (20개 이상)", len(ws) >= 20, str(len(ws)))
    check("[중요] 워커에게는 안 보낸다 (실측: agents·skills 0건)",
          bundle.workshop_files("worker") == ())
    rels = [r for r, _ in ws]
    check("전부 `.claude/` 아래로 간다", all(r.startswith(".claude/") for r in rels))
    check("네 묶음만 (agents·skills·rules·hooks)",
          {r.split("/")[1] for r in rels} <= {"agents", "skills", "rules", "hooks"},
          str({r.split("/")[1] for r in rels}))
    check("[중요] README·mcp.json 은 배달물이 아니다 (저장소 문서·병합 대상)",
          not any(r.endswith(("README.md", "mcp.json")) for r in rels))
    check("[중요] CLAUDE.md 는 파일째 배달하지 않는다 (마커 병합 대상)",
          ".claude/CLAUDE.md" not in rels)

    # ③ 개행 — 정본이 CRLF 인 파일은 CRLF 로 읽혀야 한다 (read_bytes 계약)
    crlf_src = [src for _r, src in ws if b"\r\n" in src.read_bytes()]
    if crlf_src:
        check("[중요] 정본의 CRLF 가 보존된다 (read_text 는 개행을 번역한다)",
              "\r\n" in bundle.workshop_text(crlf_src[0]))
    check("with_newlines: 윈도우는 CRLF 로 통일",
          bundle.with_newlines("a\nb\r\nc", windows=True) == "a\r\nb\r\nc")
    check("with_newlines: 그 밖은 LF 로 통일",
          bundle.with_newlines("a\r\nb\nc", windows=False) == "a\nb\nc")
    check("[중요] 섞인 입력이 한 종류로 나온다 (병합 산출물이 그렇다)",
          "\n" not in bundle.with_newlines("x\ny", windows=True).replace("\r\n", ""))

    # ④ 마커 병합 — 사람이 쓴 나머지는 그대로, 마커 없으면 안 쓴다
    canon = bundle.workshop_text(bundle.workshop_dir() / "CLAUDE.md")
    check("정본에 관리 마커가 있다", bundle.WS_BEGIN in canon and bundle.WS_END in canon)
    head, tail = "# 사람이 쓴 머리\n\n", "\n\n## 사람이 쓴 꼬리\n"
    fake = head + bundle.WS_BEGIN + "\n옛 블록\n" + bundle.WS_END + tail
    merged = bundle.merge_workshop_md(fake, "requester")
    check("[중요] 마커 밖(사람 문서)은 그대로", merged.startswith(head) and merged.endswith(tail),
          merged[:60])
    check("블록 안은 정본으로 교체됨", "옛 블록" not in merged and bundle.WS_BEGIN in merged)
    check("[중요] 마커가 없으면 **안 쓴다** (사람 문서 보호)",
          bundle.merge_workshop_md("# 사람이 쓴 것뿐\n", "requester") == "")
    check("원격이 비면 정본을 그대로 놓는다",
          bundle.merge_workshop_md("", "requester") == canon)
    check("[중요] 워커에게는 병합도 없다", bundle.merge_workshop_md(fake, "worker") == "")

    dry = bundle.deliver("P", _facts(role="requester"), dry_run=True,
                          project_init=spec.EMPTY_INIT)
    check("plan 이 자산을 노출한다 (안 보이는 산출물은 없는 것으로 읽힌다)",
          len(dry.get("workshop") or []) == len(ws), str(len(dry.get("workshop") or [])))


def test_workshop_assets_reference_only_live_tools() -> None:
    """[중요] **`tools:` 에 없는 서버를 적어 두면 오류가 아니다 — 그 도구 없이 그냥 돈다.**

    #226 에서 원전 exe 등록 5종을 지웠을 때 에이전트 9종의 허용목록이 그것을 계속 가리키고
    있었다. 리포트 27 §9-3 의 「조용히 0」보다 한 단계 조용한 실패다 — **응답이 아니라 능력이**
    사라지고, 그 에이전트는 검색 없이 그럴듯하게 답한다.

    [중요] **「어디서나 0건」은 틀린 규칙이다.** 두 종류의 언급이 정당하게 남는다:
      · `CLAUDE.md` 의 *"로컬 `mcp__context-search__*` 로 부르지 말 것"* — **금지 문장**
      · 원전 로컬 오케스트레이션 스킬 4종 — **은퇴 여부 결정 대기**(#226)
    그래서 강한 규칙은 **에이전트와 모든 `tools:` 줄**에만 걸고, 나머지는 **알려진 목록과
    같은지**를 잰다 — 새 파일이 죽은 참조를 얻으면 그때 빨간불이 된다.
    """
    import re
    root = Path(__file__).resolve().parent / "client" / "workshop"
    if not root.exists():                       # 반입 전 체크아웃 보호
        check("workshop 자산이 아직 없다 — 건너뜀", True)
        return
    from client.runtime.client_mcp import TOOLS       # noqa: PLC0415
    live = {t["name"] for t in TOOLS}
    RETIRED = ("mcp__context-search__", "mcp__redmine-tracker__", "mcp__task-queue__",
               "mcp__master-orchestrator__", "mcp__local-llm-runner__")

    # ① 에이전트 — 죽은 참조 0건 (여기가 허용목록이 사는 곳이다)
    bad = [f"{f.name}:{pre}" for f in sorted((root / "agents").rglob("*.md"))
           for pre in RETIRED if pre in f.read_text(encoding="utf-8")]
    check("[중요] 에이전트에 은퇴한 원전 서버 참조 0건 (조용한 실패 금지)", not bad, str(bad))

    # ② 어디에 있든 `tools:` 줄에는 죽은 항목이 없다
    dead_allow = [f"{f.name}:{l[:60]}" for f in sorted(root.rglob("*.md"))
                  for l in f.read_text(encoding="utf-8").splitlines()
                  if l.startswith("tools:") and any(r in l for r in RETIRED)]
    check("[중요] 허용목록(tools:)에 죽은 항목 0건", not dead_allow, str(dead_allow))

    # ③ 지어낸 이름 금지 — 참조된 ax-client 도구가 전부 실재한다
    used = set()
    for f in root.rglob("*.md"):
        used |= set(re.findall(r"mcp__ax-client__([a-z_]+)", f.read_text(encoding="utf-8")))
    check("[중요] 참조된 ax-client 도구가 전부 실재한다", not (used - live),
          str(sorted(used - live)))
    check("실제로 여러 도구를 쓴다 (치환이 통째로 날아가지 않았다)", len(used) >= 10, str(len(used)))

    # [중요] **배달되는 것만 검사한다.** `root.rglob("*.md")` 로 훑으면 저장소 문서
    #    (`README.md` — 위 §「배달물이 아니다」 칸이 그렇게 단정한다)까지 걸린다. 그 문서는
    #    **무엇을 지웠는지 기록**하려고 죽은 서버 이름을 정당하게 적는다 — 실제로 §5 를 쓰자
    #    이 테스트가 빨간불이 됐다(2026-08-22). 배달 대상은 `workshop_files` 가 정한 네
    #    디렉토리와 병합되는 `CLAUDE.md` 뿐이다.
    def delivered_md():
        for sub in ("agents", "skills", "rules", "hooks"):
            yield from sorted((root / sub).rglob("*.md"))
        cm = root / "CLAUDE.md"
        if cm.is_file(): yield cm

    # ④ 남은 언급은 **알려진 것뿐** — 결정 대기 목록이 조용히 늘어나지 않는다
    # [중요] `review-work`·`distribute` 는 **2026-08-22 삭제**됐다 (사용자 결정: *"교체해야 하면
    #    왜 남겨둬야해?"*). 대응물이 실제로 도는 것을 감사로 확인했다 — `ax-review` 스킬이
    #    `review_work`/`reject_work`/`finalize_work` 를 호출자로 명시하고, 분배는 마스터측
    #    `/distribute` + `ax-request` 가 받는다. 사라진 절차는 `workshop/README.md` §5 가 말한다.
    PENDING = {"CLAUDE.md", "manage-domain",     # 「은퇴했다 · 부르지 말 것」 금지 문장
               "cluster-selftest", "tdd-dryrun"}  # 은퇴 여부 대기 — 대응물이 **부를 수 없다**(#234)
    left = set()
    for f in delivered_md():
        if any(pre in f.read_text(encoding="utf-8") for pre in RETIRED):
            left.add(f.name if f.name == "CLAUDE.md" else f.parent.name)
    check("[주의] 남은 옛 이름은 알려진 결정 대기분뿐 (#226)", left <= PENDING,
          str(sorted(left - PENDING)))
    check("[중요] 삭제한 둘이 되살아나지 않았다",
          not ({"review-work", "distribute"} & left), str(sorted(left)))

    # ⑤ [중요] **호출과 금지 문장을 갈라서** 본다 — ④ 는 파일 단위라 금지 문장이 사는 파일에
    #    새 호출이 들어와도 통과한다. 괄호가 그 둘을 가른다(실측 2026-08-22):
    #        `mcp__master-orchestrator__review_work(`  → **호출** (16줄이 이 모양이었다)
    #        `mcp__context-search__*` 로 부르지 말 것   → **금지 문장** (괄호 없음)
    #    [주의] 괄호만으로는 부족하다 — *"…analyze_skeletons 호출 가능"* 처럼 괄호 없이
    #    호출을 지시하는 줄이 있었다(전부 삭제된 `distribute` 안). 그래서 이것은 **하한**이고,
    #    ④ 의 파일 단위 규칙과 **함께** 걸어야 의미가 있다.
    CALL = re.compile(r"mcp__(?:" + "|".join(
        r[len("mcp__"):-len("__")] for r in RETIRED) + r")__[a-z_0-9]+\(")
    calls = sorted(f"{f.parent.name}/{f.name}" for f in delivered_md()
                   if CALL.search(f.read_text(encoding="utf-8")))
    allowed = {"cluster-selftest/SKILL.md", "tdd-dryrun/SKILL.md"}   # #234 까지 대기
    check("[중요] 죽은 서버를 **호출**하는 파일은 대기분뿐 (조용한 실패)",
          set(calls) <= allowed, str(sorted(set(calls) - allowed)))
    check("대기분이 실제로 남아 있다 — 해소되면 이 목록을 지울 것",
          set(calls) == allowed, f"실제 {calls}")

    # ⑥ 미이식·미위임을 조용히 지우지 않고 **말한다**
    val = (root / "agents" / "code-validator.md").read_text(encoding="utf-8")
    check("[주의] 미이식(create_review_issue)을 말한다",
          "create_review_issue" in val and "미이식" in val)
    ue = (root / "agents" / "ue-editor-operator.md").read_text(encoding="utf-8")
    check("[주의] 미위임(그래프 조회)을 말하고 대안을 준다",
          "위임되지 않았다" in ue and "선언부를 직접" in ue)


def test_ue5_detection() -> None:
    """[중요] UE5 는 한 곳에 있지 않다 (실측 2026-08-09) — 프로브에 경로를 박으면 프로브의 의미가 없다."""
    globs = " ".join(bundle.ue5_globs())
    check("런처 설치 위치를 본다", "Epic Games\\UE_*" in globs, globs)
    check("직접 설치 위치도 본다", "C:\\Program Files\\UE_*" in globs, globs)
    # [중요] 버전을 글롭에 나열하면 새 버전이 나올 때 목록이 낡는다
    check("[중요] 글롭에 버전을 박지 않는다", "5.8" not in globs, globs)

    seen = {}
    def runner(cmd):
        seen["cmd"] = cmd
        return 0, ("C:\\Program Files\\Epic Games\\UE_5.4\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe\n"
                   "C:\\Program Files\\Epic Games\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe\n")
    got = bundle._find_ue5("h", "u", runner=runner)
    check("[중요] 선호 버전(5.8)을 고른다", "UE_5.8" in got, got)
    # [중요] cmd 는 괄호를 써도 `if exist A (…) & …` 의 뒷부분을 첫 조건의 참 분기로 삼킨다
    check("[중요] if/& 로 잇지 않는다 (한쪽만 조용히 깨진다)",
          "for /d" in seen["cmd"] and " & if exist" not in seen["cmd"], seen["cmd"][:80])

    # [중요] 종료 코드로 판정하지 않는다 — ssh rc 는 양방향으로 못 믿는다
    ok = bundle._find_ue5("h", "u", runner=lambda c: (1,
        "C:\\Program Files\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe\n"))
    check("[중요] rc≠0 이라도 출력이 있으면 인정한다", "UE_5.8" in ok, ok)
    check("아무것도 없으면 빈 문자열", bundle._find_ue5("h", "u", runner=lambda c: (0, "")) == "")
    check("엉뚱한 출력은 무시한다",
          bundle._find_ue5("h", "u", runner=lambda c: (0, "File Not Found\n")) == "")



def test_init_wiring() -> None:
    """[중요] #64 — CLAUDE.md 가 없으면 /init 을 **먼저** 돌린다. 있으면 안 돌린다."""
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
    # [주의] 일회성 비용은 따로 보고돼야 한다 — 작업 비용에 섞으면 파견이 비싸 보인다
    check("[중요] 비용을 들고 나온다", abs(info["cost_usd"] - 0.21) < 1e-9, str(info))
    check("턴도 들고 나온다", info["turns"] == 9, str(info))

    win = bundle.HostFacts(host="h", user="u", path=r"E:\repo", driven="ssh")
    win.os, win.claude = "windows", "2.1"
    bundle.run_init(win, runner=runner)
    check("윈도우는 cd /d", "cd /d" in calls["cmd"], calls["cmd"][:40])

    # [중요] claude 가 없으면 돌릴 수 없다 — 조용히 성공으로 보고하면 안 된다
    noc = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh")
    noc.os, noc.claude = "linux", ""
    check("claude 가 없으면 안 돌린다", not noc.claude)



def test_scp_source_windows() -> None:
    """[중요] 윈도우 경로를 역슬래시로 주면 scp 가 거부한다 — **그런데 rc 는 0** (실측 2026-08-09).

    이 함수가 조용히 `""` 를 돌려주던 탓에 `deliver` 가 *"기존 CLAUDE.md 가 없다"* 로 오판하고
    **내장 기본 문서로 통째로 덮었다.** 윈도우 두 대에서 매번, 리눅스만 정상 — 한쪽만 조용히
    깨지는 그 모양이다.
    """
    win = bundle.HostFacts(host="h", user="u", path=r"E:\repo", driven="ssh")
    win.os = "windows"
    src = bundle.scp_source(win, r"E:\repo\CLAUDE.md")
    check("[중요] 윈도우는 슬래시로 바꾼다", "\\" not in src, src)
    check("경로가 온전하다", src.endswith(":E:/repo/CLAUDE.md"), src)

    lin = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh")
    lin.os = "linux"
    check("리눅스는 그대로", bundle.scp_source(lin, "/repo/CLAUDE.md").endswith(":/repo/CLAUDE.md"))


def test_merge_never_replaces_existing() -> None:
    """[중요] 기존 내용이 있으면 **블록만** 얹는다 — 기본 문서로 덮지 않는다."""
    f = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh", role="worker")
    f.os = "linux"
    human = "# 사람이 쓴 문서\n\n지우면 안 되는 내용\n"
    merged = bundle.merge_claude_md(human, "ModularStage", f)
    check("사람 글이 남는다", "지우면 안 되는 내용" in merged, merged[:120])
    check("블록이 붙는다", bundle.MD_BEGIN in merged and bundle.MD_END in merged)
    # [중요] 기존이 있는데 기본 문서를 끼워 넣으면 그게 덮어쓰기다
    empty_doc = bundle.merge_claude_md("", "ModularStage", f)
    check("[중요] 기존이 있으면 기본 문서를 안 넣는다", len(merged) < len(empty_doc) / 2,
          f"{len(merged)} vs {len(empty_doc)}")


def test_claude_md_body_has_a_project_axis() -> None:
    """[중요] **본문에 프로젝트 축이 있어야 한다** (`#290`, 사용자 지적 2026-08-24).

    종전에는 `payload/CLAUDE.md` **한 벌**을 넣었고 그 내용이 ModularStage 문서였다. 주석은
    *"`/init` 산출 정본"* 이라 적었지만 실제로는 **MS 의** 산출물이다 — 프로젝트가 하나일 때는
    구별되지 않았고, NS 를 붙이자 드러났다: NS 체크아웃이 *"ModularStage … mission system …
    hexagonal prefab modules"* 를 받았고 거기엔 그런 것이 없다.
    **매 세션 읽히는 문서의 거짓 서술이 코드가 덜 된 것보다 비싸다**(`docs/12` §12.4).
    """
    print("\n[본문] 프로젝트별로 생성된다 (#290)")

    ns = bundle.claude_md_body("NS")
    check("[중요] NS 본문에 ModularStage 가 없다",
          "ModularStage" not in ns and "hexagonal" not in ns, ns[:200])
    # [중요] **실측은 본문이 아니라 관리 블록에 있다** (사용자 지시 2026-08-24) — 본문은
    #    병합이 건드리지 않으므로 거기 적으면 첫 배달 때 굳어 늙는다. 블록은 배달마다 갈린다.
    check("본문은 실측을 적지 않고 블록을 가리킨다",
          "AX 관리 블록에 있다" in ns and "NS.uproject" not in ns, ns[:400])
    f = bundle.probe("192.168.0.33", "user", r"C:\Users\USER\Documents\NS",
                     "ssh", "requester")
    blk = bundle.managed_block("NS", f)
    check("[중요] 블록이 실측 uproject 를 적는다", "NS.uproject" in blk, blk[:300])
    check("[중요] 블록이 실측 Editor 타깃으로 빌드 명령을 만든다",
          "NSEditor" in blk and "Build.bat" in blk, blk[:300])
    check("  블록에도 ModularStage 가 없다", "ModularStage" not in blk, blk[:300])
    check("[중요] 모르는 것을 **모른다고** 적는다 (지어내지 않는다)",
          "아직 비어 있고" in ns, ns[-400:])
    check("[중요] 이 체크아웃에서 관리하지 않는다고 말한다",
          "마스터가 배달한다" in ns, ns[-300:])

    ms = bundle.claude_md_body("ModularStage")
    check("프로젝트별 정본이 있으면 그것을 쓴다 (MS 228줄 문서 보존)",
          "mission system" in ms and len(ms.splitlines()) > 100,
          f"{len(ms.splitlines())}줄")

    # [주의] 없는 프로젝트는 **골격**으로 답하고 사실을 지어내지 않는다
    unknown = bundle.claude_md_body("없는프로젝트이름")
    check("[주의] 소스를 못 읽으면 본문이 그 사실을 말한다",
          "찾지 못했다" in unknown, unknown[:400])
    rows = "\n".join(bundle._project_facts_rows("없는프로젝트이름"))
    check("[중요] 블록도 빌드 명령을 **지어내지 않는다**",
          "적지 않았다" in rows, rows[:300])
    check("  못 읽었다는 것을 표에 적는다", "찾지 못했다" in rows, rows[:300])


def test_workshop_assets_have_a_project_axis() -> None:
    """[중요] **프로젝트 고유 자산은 그 프로젝트에만 간다** (`#292`, 전수 실측 2026-08-24).

    자산 29개를 **디렉토리 전수로** 셌다(목록을 대상 집합으로 쓰면 목록 밖 파일이 조용히
    빠진다 — `#264` 교훈). 프로젝트 언급 6건이 나왔고 **부류가 둘**이었다:

        발화 예시 5건   code-writer · generate-contract-test · manage-task ·
                        ontology-register · tdd-dryrun → NS 에서 읽어도 거짓이 아니다
        고유 사실 1건   rules/mission-editor-mcp.md — `AMissionPrefab`·`SeptetTiles[0..6]`
                        7개 헥스 타일·`FMissionTaskInfo[]` → **NS 에 없는 것을 사실로 서술**

    하나만 옮겼다. **부류를 가르지 않고 전부 옮기면** 공통 자산이 프로젝트마다 갈린다.
    """
    print("\n[자산] 프로젝트 고유만 갈라 보낸다 (#292)")
    ms = bundle.workshop_files("requester", "ModularStage")
    ns = bundle.workshop_files("requester", "NS")
    common = bundle.workshop_files("requester")
    if not common:
        check("작업장 자산이 아직 반입되지 않았다 — 건너뜀", True)
        return

    ms_rels, ns_rels = {r for r, _ in ms}, {r for r, _ in ns}
    own = ms_rels - ns_rels
    check("[중요] MS 전용 규칙은 MS 에만 간다",
          own == {".claude/rules/mission-editor-mcp.md"}, str(own))
    check("[중요] NS 는 그것을 받지 않는다 (없는 클래스를 사실로 서술하는 문서)",
          not any("mission-editor" in r for r in ns_rels), str(sorted(ns_rels)[:3]))
    check("공통은 둘 다 받는다", len(ns_rels) >= 20 and ns_rels < ms_rels,
          f"{len(ns_rels)} / {len(ms_rels)}")
    check("[주의] 프로젝트를 안 주면 **공통만** (남의 자산을 폴백으로 보내지 않는다)",
          {r for r, _ in common} == ns_rels, str(len({r for r, _ in common})))

    # [중요] **무엇을 받았는지 관리 블록이 답한다** — 공통 표에 적으면 남의 프로젝트에서 거짓이 된다
    rows = "\n".join(bundle._project_facts_rows("ModularStage"))
    check("[중요] 블록이 이 프로젝트만의 자산을 이름으로 적는다",
          "mission-editor-mcp.md" in rows, rows[-200:])
    rows_ns = "\n".join(bundle._project_facts_rows("NS"))
    check("  없으면 「없음」이라고 적는다 (빈칸으로 두지 않는다)",
          "(없음 — 공통만)" in rows_ns, rows_ns[-200:])

    # [주의] 공통 자산에 남은 프로젝트 언급은 **발화 예시**다 — 사실 서술이 아니므로 그대로 둔다.
    #    이 칸은 그 판단을 기록해 둔다: 예시가 늘어도 깨지지 않고, **사실 서술이 새로 들어오면**
    #    사람이 이 주석을 보고 부류를 다시 가른다.
    check("공통 자산에 프로젝트 고유 **사실 서술**이 없다 (예시는 허용)",
          not any("AMissionPrefab" in bundle.workshop_text(src) for _r, src in common),
          "공통에 MS 클래스 사실 서술이 남아 있다")


def test_workshop_assets_reference_only_live_skills() -> None:
    """[중요] **배달 문서가 없는 스킬을 부르면 안 된다** (`#297`, `.33` 라이브가 발견).

    `#232` 가 만든 게이트는 **MCP 서버 이름**만 봤고 **스킬 이름**은 안 봤다. 그래서 `#232` 에서
    `/distribute`·`/review-work` 를 지우고도 그것을 **20회 부르는 문서**가 통과했다
    (`workshop/CLAUDE.md` 9곳 포함). `.33` 세션이 *"위임 대상으로 지시하는데 존재하지 않는다"*
    를 스스로 발견해야 했다.

    [중요] **「어디서나 0건」은 여기서도 틀린 규칙이다.** 정당하게 남는 언급이 셋이다:
      · *"이 기계에 없다 … 자리가 옮겨졌다"* — **부재를 말하는 문장**(지우면 다음 세션이
        「원래 없었다」로 읽는다 — 리포트 27 의 교훈)
      · `ax-review` description 의 `/review-work` — **사용자 발화 트리거**(그 말을 쓸 수 있다)
      · *"원전의 … 를 그대로 옮긴 것"* — **원전 기록**
    그래서 규칙은 **「부르라고 지시하는 문장」**에만 건다.
    """
    import re

    print("\n[참조] 배달 문서가 실재하는 스킬만 부른다 (#297)")
    root = Path(__file__).resolve().parent / "client"
    if not (root / "workshop").exists():
        check("workshop 자산이 아직 없다 — 건너뜀", True)
        return

    # 실재하는 스킬 = 배달분 + 역할별 홈 스킬 (선언이 정본)
    live = {d.name for d in (root / "workshop" / "skills").iterdir() if d.is_dir()}
    live |= {d.name for d in (root / "skills").iterdir() if d.is_dir()}
    for role in ("requester", "worker"):
        live |= set(spec.skills_for(role))

    # [주의] 마스터 전용 스킬은 **요청자 문서가 부르면 안 된다** — 그 기계엔 없다.
    #    실재 여부와 별개로 「누구의 것인가」가 축이다.
    MASTER_ONLY = {"distribute", "debate"}

    bad: list = []
    for f in sorted((root / "workshop").rglob("*.md")):
        if f.name == "README.md":          # 원전 대조 감사표 — 기록이고 배달물이 아니다
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(k in line for k in ("이 기계에 없다", "자리가 옮겨졌다", "로 읽는다",
                                       "그대로 옮긴 것", "기록이다", "트리거", "발화에 발동")):
                continue                    # 부재·기록·트리거 서술
            for m in re.finditer(r"`?/([a-z][a-z0-9-]{2,})`?\s*(스킬|을 부른다|로 분산|사용)", line):
                name = m.group(1)
                if name in MASTER_ONLY:
                    bad.append(f"{f.name}:{i} 마스터 전용 `{name}` 을 이 기계에서 부른다")
                elif name not in live:
                    bad.append(f"{f.name}:{i} 없는 스킬 `{name}`")
    check("[중요] 배달 문서에 죽은/남의 스킬 지시가 없다", not bad, "; ".join(bad[:4]))

    # 홈 스킬(요청자·워커 절차서)도 같은 규칙
    bad2: list = []
    for f in sorted((root / "skills").rglob("SKILL.md")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(k in line for k in ("그대로 옮긴 것", "발화에 발동", "description:")):
                continue
            for m in re.finditer(r"`?/([a-z][a-z0-9-]{2,})`?\s*(스킬|을 부른다|로 분산)", line):
                if m.group(1) in MASTER_ONLY or m.group(1) not in live:
                    bad2.append(f"{f.parent.name}:{i} `{m.group(1)}`")
    check("  홈 스킬도 같다", not bad2, "; ".join(bad2[:4]))


def test_registration_doc_matches_reality() -> None:
    """[중요] **절차서·도구 설명이 실제 도구와 맞는가** (`#339`, 실측 2026-08-30).

    오늘 실전 등재가 네 번 막혔고 **넷 다 설명이 없거나 틀려서**였다:
    `summary` 를 지어냄 · `contracts` 를 리스트로 · `depth_set` 을 문자열로 ·
    `target_branch=main` · 타임아웃을 실패로 읽고 재시도(중복 실행).

    [중요] 절차서 §3 은 **없는 도구를 잘못된 시그니처로** 지시하고 있었다
    (`register_work_tool(… specs_json …)`) — `#297` 부류다.
    """
    print("\n[등재 문서] 절차서·도구 설명이 실물과 맞는가 (#339)")
    root = Path(__file__).resolve().parent / "client"
    skill = (root / "skills" / "ax-request" / "SKILL.md").read_text(encoding="utf-8")

    # [주의] 이름을 **부르는 형태**(`(`)만 잡는다 — "이건 `register_work_tool` 이 아니다"
    #    라는 경고 문장은 남아 있어야 한다(다음 세션이 옛 이름을 다시 쓰지 않게).
    check("[중요] 없는 도구를 **호출하라고** 적지 않는다",
          "register_work_tool(" not in skill)
    check("[주의] 대신 옛 이름이 틀렸다는 경고는 남아 있다",
          "register_work_tool` 이 아니다" in skill)
    check("실제 도구 이름을 적는다", "register_work(" in skill)
    check("[중요] `target_branch` 를 보내지 말라고 말한다",
          "target_branch" in skill and "보내지 마라" in skill)
    check("[중요] 골조는 마스터가 만들지 않는다고 말한다",
          "골조는 마스터가 만들지 않는다" in skill)
    check("[주의] 타임아웃이 실패가 아니라고 말한다",
          "타임아웃" in skill and "실패가 아니다" in skill)
    check("[주의] 재시도가 중복이라고 말한다", "중복 등재" in skill)

    # 도구 스키마 쪽 — 세션이 실제로 읽는 곳
    import importlib.util
    sp = importlib.util.spec_from_file_location(
        "cm", Path(__file__).resolve().parent.parent / "client" / "runtime" / "client_mcp.py")
    cm = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(cm)
    tool = next(t for t in cm.TOOLS if t["name"] == "register_work")
    desc = tool["description"]
    specs = tool["inputSchema"]["properties"]["specs"]["description"]

    check("[중요] 도구 설명이 「마스터가 골조를 만든다」고 말하지 않는다",
          "마스터가 분해·골조" not in desc, desc[:120])
    check("도구 설명이 골조는 요청자 몫이라고 말한다", "골조는 마스터가 만들지 않는다" in desc)
    check("도구 설명이 target_branch 를 비우라고 말한다", "보내지 마라" in desc)
    check("[주의] 도구 설명이 타임아웃≠실패를 말한다", "실패가 아니다" in desc)
    check("[중요] specs 설명이 contracts 의 **형**을 말한다", "한 문자열" in specs)
    check("[중요] specs 설명이 depth_set 의 **형과 뜻**을 말한다",
          "정수 배열" in specs and "PSEUDO:N" in specs)

    # [중요] **조각 독립성** — 실측 2026-08-30: 서로 다른 파일 넷에 `depends_on` 을 붙여
    #    병렬로 갈 수 있는 것을 직렬로 묶었고, 첫 조각 뒤 나머지가 안 풀렸다. 설명이
    #    「언제 쓰는가」를 안 적었기 때문이다.
    check("[중요] depends_on 을 보통 비우라고 말한다", "보통 비운다" in specs, specs[:200])
    check("  같은 파일 뎁스일 때만이라고 말한다", "같은 파일" in specs)
    check("[중요] requires 가 능력 라우팅이고 추론엔 UE5 가 필요 없다고 말한다",
          "능력 라우팅" in specs and "필요 없다" in specs)
    check("[중요] 절차서도 조각이 독립이라고 말한다",
          "depends_on` 을 붙이지 마라" in skill or "붙이지 마라" in skill, skill[:100])


def test_consent_rule_reaches_the_requester() -> None:
    """[중요] **게임 소스는 고치기 전에 동의** — 그 조항이 요청자에게 닿아야 한다 (`#298`).

    실측 2026-08-24: `.33` 세션이 「직접 처리」 분기를 타면서 `.uproject` 를 고치고 **빌드까지**
    간 뒤 사용자가 중단했다. 분기 판단은 규칙과 맞았고(플러그인 활성화 = 미세 수정) **빠진 것은
    이 절차**였다 — `ax-request/SKILL.md` 와 내가 만든 골격에 그 조항이 **0곳**이었다.

    [중요] **두 축을 섞지 않는다**: 「미세 수정」은 *어디서* 처리할지의 기준이고 *동의가
    필요한지*의 기준이 아니다.
    """
    print("\n[동의] 게임 소스 쓰기 전 동의 조항이 닿는다 (#298)")
    root = Path(__file__).resolve().parent / "client"

    skill = (root / "skills" / "ax-request" / "SKILL.md").read_text(encoding="utf-8")
    check("[중요] 요청자 절차서에 동의 조항이 있다",
          "동의를 받는다" in skill, skill[:200])
    check("  대상에 `.uproject` 가 들어간다", ".uproject" in skill)
    check("  [중요] **빌드도 그 뒤**라고 말한다",
          "빌드" in skill and "산출물을 바꾼다" in skill)
    check("  [중요] 두 축을 섞지 말라고 못박는다",
          "동의가 필요한지의 기준이 아니다" in skill.replace("*", ""), "축 구분이 없다")
    # 분기 표의 「직접 처리」 칸이 동의를 가리켜야 한다 — 거기서 규칙이 사라진 자리다
    for line in skill.splitlines():
        if "여기서 직접 처리한다" in line:
            check("  분기 표의 「직접 처리」가 동의를 가리킨다", "§0.05" in line, line[:120])
            break

    body = bundle.claude_md_body("NS")
    check("[중요] 마스터가 생성하는 CLAUDE.md 본문에도 있다 (매 세션 읽히는 자리)",
          "동의를 받는다" in body, body[:300])
    check("  읽기는 막지 않는다고 말한다 (과잉 차단 방지)",
          "읽기" in body and "쓰기" in body, "읽기/쓰기 구분이 없다")


def test_direct_branch_records_what_it_did() -> None:
    """[중요] **분산 경로엔 자동 기재가 있고 직접 경로엔 없다** (`#310`).

    실측 `ns#302`: 직접 처리한 작업이 **노트 0건 · 상태 신규**로 남았고 본문은 마스터가
    대신 적어야 했다. `#298` 이 고친 것은 *동의 선행*이고 *기재*가 아니다 — 다른 구멍이다.
    """
    print("\n[기재] 직접 처리 뒤 기록이 남는다 (#310)")
    root = Path(__file__).resolve().parent / "client"
    skill = (root / "skills" / "ax-request" / "SKILL.md").read_text(encoding="utf-8")

    check("[중요] 절차서에 기재 절이 있다", "기재한다" in skill, skill[:200])
    for tool in ("log_history", "redmine_note", "redmine_link_commit"):
        check(f"  셋을 한 묶음으로 — {tool}", tool in skill, f"{tool} 이 없다")
    check("  [중요] 왜 여기만 수동인지 말한다 (큐를 지나지 않는다)",
          "큐를 지나지 않" in skill, "사유가 없다")
    check("  [중요] 상태는 「해결」까지 — 닫는 것은 사람",
          "해결" in skill and "완료" in skill, "상태 규약이 없다")
    check("  [주의] 커밋은 별개의 승인이라고 말한다",
          "커밋은 별개" in skill.replace("**", ""), "커밋 축이 섞여 있다")
    check("  [주의] 미커밋이면 그렇게 적으라고 한다", "미커밋" in skill, "미커밋 서술이 없다")
    check("  trivial 예외를 적었다", "trivial" in skill, "trivial 예외가 없다")
    # [중요] 도구 이름이 **실재**해야 한다 — `#297` 이 죽은 참조 20건을 잡은 그 축이다
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client" / "runtime"))
    import client_mcp as _M                                  # noqa: E402
    names = {t["name"] for t in _M.TOOLS}
    for tool in ("log_history", "redmine_note", "redmine_link_commit"):
        check(f"  [중요] `{tool}` 이 실재하는 도구다 (죽은 참조 금지)", tool in names,
              str(sorted(names)))



# ── 훅 등록 (`#337`) ─────────────────────────────────────────────
#
# [중요] **이 테스트가 잡는 것은 「배달됐다」와 「돈다」의 차이다.** 실측 2026-08-30: 훅 파일은
#    2026-08-20부터 배달됐고 해시도 3자 일치였는데 `settings.json` 에 등록이 없어 한 번도 안
#    돌았다. `check` 는 계속 [완료] 를 보고했다.

def test_hook_registration() -> None:
    import json as _json
    r = bundle.HostFacts(host="h", user="u", path="C:\\ws", driven="ssh",
                         role="requester", os="windows")
    lin = bundle.HostFacts(host="h", user="u", path="/ws", driven="ssh", role="requester")

    # 빈 상태 → 관리 훅이 등록된다
    got = _json.loads(bundle.merge_settings_json("", r))
    ev = got["hooks"]["PostToolUse"]
    check("[중요] 빈 settings 에 관리 훅이 등록된다", len(ev) == 1, str(got))
    cmd = ev[0]["hooks"][0]["command"]
    check("[중요] 윈도우 인터프리터는 `py` — 마스터의 sys.executable 이 아니다",
          cmd.startswith("py "), cmd)
    check("훅 경로는 상대·슬래시 (cwd = 체크아웃 루트)",
          cmd.endswith(".claude/hooks/domain_hint.py"), cmd)
    check("리눅스는 python3",
          _json.loads(bundle.merge_settings_json("", lin))["hooks"]["PostToolUse"][0]
          ["hooks"][0]["command"].startswith("python3 "))

    # [중요] 사용자 훅 보존 — 원전 `_merge_managed_hooks` 의 계약
    prev = _json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "Write", "hooks": [{"type": "command", "command": "my_own.py"}]}]},
        "model": "opus"})
    got = _json.loads(bundle.merge_settings_json(prev, r))
    cmds = [h["command"] for e in got["hooks"]["PostToolUse"] for h in e["hooks"]]
    check("[중요] 사용자 훅은 보존된다", "my_own.py" in cmds, str(cmds))
    check("[중요] 사용자의 다른 키도 보존된다", got.get("model") == "opus", str(got))

    # 멱등 — 두 번 배달해도 항목이 늘지 않는다
    twice = _json.loads(bundle.merge_settings_json(_json.dumps(got), r))
    check("[중요] 재배달이 훅을 중복 등록하지 않는다",
          len(twice["hooks"]["PostToolUse"]) == len(got["hooks"]["PostToolUse"]),
          str(twice))

    # 깨진 JSON → 덮지 않고 멈춘다 (merge_mcp_json 과 같은 판단)
    try:
        bundle.merge_settings_json("{ 이건 JSON 이 아니다", r)
        check("[중요] 깨진 settings.json 은 덮지 않는다", False, "통과해버렸다")
    except bundle.BundleError:
        check("[중요] 깨진 settings.json 은 덮지 않는다", True)

    # 워커는 훅을 안 받는다 (작업장 자산이 요청자 전용)
    check("워커 역할엔 관리 훅이 없다", spec.managed_hooks_for("worker") == ())

    # [중요] 선언된 훅 스크립트가 **실제로 배달되는 목록에 있어야** 한다 —
    #    없으면 없는 파일을 등록하게 된다 (선언과 배선이 두 벌이면 나는 사고)
    delivered = {rel for rel, _src in bundle.workshop_files("requester")}
    for _ev, _m, rel, _t in spec.MANAGED_HOOKS:
        check(f"[중요] 등록할 훅이 배달 목록에 있다 — {rel}", rel in delivered,
              f"배달 목록에 없다: {sorted(delivered)[:5]}…")

    # [중요] SessionStart 훅도 같은 배선을 탄다 (`#337` 본체)
    got = _json.loads(bundle.merge_settings_json("", r))
    ss = got["hooks"].get("SessionStart") or []
    check("[중요] SessionStart 훅이 등록된다", len(ss) == 1, str(got.get("hooks")))
    check("matcher 는 source 를 가른다 — compact 는 빼고 startup/resume/clear",
          ss and ss[0].get("matcher") == "startup|resume|clear",
          str(ss[0].get("matcher")) if ss else "없음")
    # 🔴 [중요] **전제가 2026-09-04 에 바뀌었다** (사용자 지시). 종전은 *"두 훅이 서로 다른
    #    이벤트"* 였는데, `SessionStart` 하나로는 **켜져 있는 세션에 아무것도 안 뜬다** —
    #    실측 01:30: 라운드가 4/4 완주하고 Redmine `#354` 까지 났는데 `.33` 은 끝난 줄 몰랐다.
    #    그래서 `pending_works` 를 `UserPromptSubmit` 에도 걸어 **매 턴** 고지한다.
    #    [주의] 소음이 안 되는 근거는 스크립트에 있다 — 열린 work 이 0이면 침묵한다.
    check("[중요] 세 이벤트에 걸린다 (매 턴 고지 포함)",
          set(got["hooks"]) == {"PostToolUse", "SessionStart", "UserPromptSubmit"},
          str(set(got["hooks"])))
    ups = got["hooks"].get("UserPromptSubmit") or []
    check("  같은 스크립트를 쓴다 (판정 로직을 두 벌 두지 않는다)",
          ups and "pending_works.py" in str(ups[0]), str(ups))
    check("  타임아웃이 세션시작보다 짧다 (사람의 매 턴을 붙잡지 않는다)",
          ups and int(ups[0].get("hooks", [{}])[0].get("timeout", 99)) < 15, str(ups))

    # settings.local.json 은 이름조차 건드리지 않는다
    check("[주의] 관리 대상은 settings.json — local 이 아니다",
          spec.SETTINGS_REL.endswith("/settings.json")
          and "local" not in spec.SETTINGS_REL, spec.SETTINGS_REL)


def main() -> int:
    for fn in (test_role, test_config, test_managed_block, test_merge, test_skill_is_readable,
               test_mcp_json_merge,
               test_role_skills, test_role_payload, test_payload_split, test_deliver_removes_deprecated_skills, test_role_block, test_ue5_detection, test_init_wiring, test_scp_source_windows,
               test_merge_never_replaces_existing,
               test_workshop_assets_reference_only_live_tools,
               test_workshop_delivery,
               test_direct_branch_records_what_it_did,
               test_claude_md_body_has_a_project_axis,
               test_workshop_assets_have_a_project_axis,
               test_workshop_assets_reference_only_live_skills,
               test_consent_rule_reaches_the_requester,
               test_registration_doc_matches_reality,
               test_hook_registration):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_bundle: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
