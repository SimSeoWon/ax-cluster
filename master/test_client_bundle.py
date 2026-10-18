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

from master.client import __main__ as client_cli, bundle, spec      # noqa: E402
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
    cfg = bundle.config_for("ModularStage", _facts(python="/usr/bin/python3"))
    # [중요] 비밀이 들어가면 이 파일이 유출 경로가 된다
    blob = str(cfg).lower()
    check("[중요] config 에 비밀이 없다",
          not any(k in blob for k in ("token", "bearer", "password", "secret")), blob[:80])
    check("체크아웃 경로가 실린다", cfg["checkout"]["path"] == "/home/sim/trunk/ModularStage")
    check("UE5 없으면 능력이 비어 있다", cfg["capabilities"] == [], str(cfg["capabilities"]))
    check("백엔드는 실측값", cfg["backends"]["ollama_models"] == 4 and cfg["backends"]["agy"] is False)
    check("프로젝트 로컬 도구가 쓸 Python 경로를 저장한다",
          cfg["backends"]["python"] == "/usr/bin/python3", str(cfg["backends"]))
    check("부산물 경로를 알려준다", ".ax/work" in cfg["_layout"]["work"])

    win = bundle.config_for("ModularStage", _facts(
        os="windows", ue5=r"C:\UE\UnrealEditor-Cmd.exe", agy=True, ollama_models=7,
        python=r"C:\Py\python.exe"))
    check("UE5 있으면 ue5 능력", "ue5" in win["capabilities"], str(win["capabilities"]))
    check("윈도우면 windows 능력", "windows" in win["capabilities"])
    check("Windows Python 절대경로도 왕복한다",
          win["backends"]["python"] == r"C:\Py\python.exe")


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
    # 🔴 `ax-advance` 는 ⑺ 라운드 종결(작업 브랜치 전진) · `ax-review` 는 main 반영 —
    #    **다른 단계**다. 그 둘을 섞어 오지시를 낸 것이 2026-09-04 의 결함이었다.
    # 🔴 2026-09-16 `ax-fix` 추가 (`#630` — 리뷰·플랜 수정 항목 검토·적용)
    # 2026-10-09 `ax-gemini` 추가 (대화형 리서치·보고서 위임 · 사용자 결정)
    check("[중요] 요청자는 request·ontology·advance·review·fix·gemini (ax-work 아님)",
          set(bundle.skills_for("requester"))
          == {"ax-request", "ax-ontology", "ax-advance", "ax-review", "ax-fix", "ax-gemini"},
          str(bundle.skills_for("requester")))
    check("[중요] 요청자 스킬에 ax-work 가 섞이지 않는다",
          "ax-work" not in bundle.skills_for("requester"))
    # [중요] 스킬 원문이 실재해야 배달이 성립한다 — 이름만 등록하면 배달에서 죽는다
    for n in bundle.skills_for("requester") + bundle.skills_for("worker"):
        check(f"스킬 원문이 있다: {n}", bundle.skill_text(n).startswith("---"))


def test_mcp_json_merge() -> None:
    """소 3.8.4 — .mcp.json 은 사람 항목을 보존하고, 깨진 파일은 덮지 않는다."""
    import json as _json
    f = _facts(os="windows", python=r"C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe")
    e = bundle.mcp_entry_for(f)
    check("[중요] 윈도우는 프로브한 절대경로다 (Codex py 탐지 격리)",
          e["command"] == f.python, str(e))
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
                       "clientside/fix_flow.py",
                       "layer3_verify.py", "source_text.py", "utf8.py",
                       "work/branch_names.py", "work/coordinator.py",
                       "work/review.py", "work/skeleton_gate.py", "work/build_local.py",
                       "work/usage.py", "work/gemini_report.py"},       # `#763` ax-gemini 실행부
          str(pay))
    # [주의] 이 칸은 세 번 움직였다: 옛 계약("워커에는 안 간다") → `#204` 로 claimer 폐포 추가
    #    → 2026-08-23 클라 MCP 추가(`#267`·`#261`) → **2026-08-27 claimer 폐포 제거**(`#320`,
    #    상주 전폐). 워커는 이제 마스터의 SSH push 로 돈다.
    # 🔴 **네 번째 움직임 — 상주 폐포가 돌아왔다** (`#404`, 사용자 결정 2026-09-12).
    #    `#320` 의 가드가 *"되살리려면 **결정이 먼저다**"* 라고 조건을 걸어 뒀고, 그 조건이
    #    성립했다(기계 5~6대 확장 전제 · `#401` 의 세션 0 이 상주로 풀린다). 그 가드는
    #    제 일을 했다 — 오늘 이 배선을 정확히 잡아 세웠다.
    #    [주의] **`claimer.py` 가 아니라 `worker_daemon.py` 다** — 추론(code) 경로는 들어냈다.
    #    그쪽이 폐기된 `carry`/`manifest` 운송 규약 위에 서 있었기 때문이다(2026-09-02 철거).
    check("[중요] 워커에는 클라 MCP + 빌드 사슬 + **상주 폐포**가 간다 (#404)",
          set(bundle.payloads_for("worker")) == {
              "clientside/client_mcp.py", "clientside/ontology_cache.py",
              "work/worker_daemon.py", "work/ax_safety.py",
              "clientside/session1_conductor.py",
              "work/build_local.py",
              "work/skeleton_gate.py", "layer3_verify.py", "source_text.py", "utf8.py",
              "work/usage.py"},                    # `#830` 런처의 agy 실제 모델 대조
          str(bundle.payloads_for("worker")))
    check("🔴 [중요] 옛 `claimer.py` 는 돌아오지 않는다 — 추론 경로째 폐기했다",
          "work/claimer.py" not in set(bundle.payloads_for("worker")),
          str(bundle.payloads_for("worker")))
    check("[중요] `ax_safety` 가 데몬과 **함께** 간다 (빠지면 상주 진입에서 죽는다)",
          {"work/worker_daemon.py", "work/ax_safety.py"} <= set(bundle.payloads_for("worker")))
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
    GUARDED_OK = {"runner", "client.bundle", "client",           # 명시적 가드 화이트리스트
                  "workmodel",   # review 재작업 판정 — 요청자에선 미지원으로 거절(사용자 승인 2026-10-11 · #815)
                  "layer2_verify"}   # usage 의 레인 호출 — 요청자는 파서만 쓴다(`#763`, 가드가 마스터 전용이라 말한다)
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
    # 🔴 동결값도 `#404` 로 움직였다 — 상주 폐포 둘이 **build_local 앞**에 들어간다.
    #    [중요] 순서까지 동결하는 이유는 배달 순서가 계약이기 때문이다(`__init__.py` 가 먼저
    #    가야 나머지가 임포트된다는 것과 같은 결).
    # 🔴 `#401`: 세션 1 지휘자 런처가 더해졌다 — Windows 는 SSH(세션 0)에서 codex 샌드박스
    #    자식이 죽으므로, `/IT` 작업으로 **세션 1** 에서 지휘자를 돌린다.
    FROZEN["worker"] = ("clientside/client_mcp.py", "clientside/ontology_cache.py",
                        "work/worker_daemon.py", "work/ax_safety.py",
                        "clientside/session1_conductor.py",
                        "work/build_local.py", "work/skeleton_gate.py",
                        "layer3_verify.py", "source_text.py", "utf8.py",
                        # 🔴 `#830`: agy 로그 파서가 **끝에** 더해진다 (결정된 변경 — 기준선 이동)
                        "work/usage.py")
    # 🔴 `#630`: 요청자에게 `fix_flow.py` 가 MCP 폐포 **바로 뒤**에 들어간다 (결정된 변경 — 기준선 이동)
    FROZEN["requester"] = ("clientside/client_mcp.py", "clientside/ontology_cache.py",
                           "clientside/fix_flow.py",
                           "layer3_verify.py", "source_text.py", "utf8.py",
                           "work/branch_names.py", "work/coordinator.py", "work/review.py",
                           "work/skeleton_gate.py", "work/build_local.py",
                           # 🔴 `#763`: ax-gemini 실행부가 **끝에** 더해진다 (결정된 변경 — 기준선 이동)
                           "work/usage.py", "work/gemini_report.py")
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
    SPLIT = {"clientside/session1_conductor.py": "client/runtime/session1_conductor.py",
             "clientside/fix_flow.py": "client/runtime/fix_flow.py",
             "clientside/client_mcp.py": "client/runtime/client_mcp.py",
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


def test_shadow_skills_are_reported() -> None:
    """🔴 **codex 가 읽는 옛 스킬 사본을 `check` 가 잡는다** (실측 2026-09-13 `.2`).

    그림자 사본이 있으면 codex 는 목록에 `ax-work` 를 두 번 올린 뒤 **옛 사본을 읽는다.**
    배달본(`~/.codex/skills`) 해시는 일치했으므로 종전 `check` 로는 안 보였다.
    🔴 지워도 **돌아온다** — `#661`(2026-09-21 삭제 → 09-22 12:23 재생성). 그래서 이 검사는
    일회성 청소가 아니라 상시 게이트다.
    """
    check("[중요] 배달하지 않는 codex 스킬 루트가 선언돼 있다",
          ".agents" in spec.SKILL_SHADOW_HOMES, str(spec.SKILL_SHADOW_HOMES))
    check("  그 자리는 배달 대상이 아니다 (한 벌을 더 두지 않는다)",
          not set(spec.SKILL_SHADOW_HOMES) & set(spec.SKILL_HOMES))

    calls: list = []

    def win_ssh(host, user, cmd, *, timeout=None):
        calls.append(cmd)
        return 0, ("PRESENT" if "ax-work" in cmd else "ABSENT")

    win = _facts(os="windows", home=r"C:\Users\janus", host="192.168.0.2", user="janus")
    got = bundle.shadow_skills(win, ("ax-work", "ax-infer"), ssh=win_ssh)
    check("🔴 [중요] 남은 옛 사본을 이름으로 잡는다", got == ["~/.agents/skills/ax-work"], str(got))
    check("  윈도우 경로를 쓴다", any(r"C:\Users\janus\.agents\skills\ax-work\SKILL.md" in c
                                     for c in calls), str(calls))

    lin = bundle.shadow_skills(_facts(), ("ax-work",),
                               ssh=lambda h, u, c, *, timeout=None: (0, "PRESENT"))
    check("리눅스에서도 같은 판정이다", lin == ["~/.agents/skills/ax-work"], str(lin))
    clean = bundle.shadow_skills(_facts(), ("ax-work",),
                                 ssh=lambda h, u, c, *, timeout=None: (0, "ABSENT"))
    check("깨끗하면 빈 목록이다", clean == [], str(clean))

    def boom(h, u, c, *, timeout=None):
        raise OSError("ssh 끊김")

    unknown = bundle.shadow_skills(_facts(), ("ax-work",), ssh=boom)
    check("[중요] **fail-closed** — 재지 못하면 통과로 접지 않는다",
          len(unknown) == 1 and "측정 실패" in unknown[0], str(unknown))
    silent = bundle.shadow_skills(_facts(), ("ax-work",),
                                  ssh=lambda h, u, c, *, timeout=None: (255, ""))
    check("  답이 비어도 측정 실패로 적는다", len(silent) == 1 and "rc=255" in silent[0], str(silent))


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

    # [중요] **파이썬 부산물은 배달 목록에 못 들어온다** (`#374`). `hooks/` 는 import 되는
    #    모듈을 담게 됐고(`pending_works.py` → `editor_mcp.py`), 그러면 `__pycache__` 가
    #    생긴다. 실측 2026-09-06: 그것이 목록에 들어와 `workshop_text` 가 utf-8 로 읽다
    #    죽었다 — **거르지 않으면 배달이 그 자리에서 실패한다.**
    #    [주의] 흉내가 아니라 **진짜 만들어 본다** — 판정을 파일 없이 재면 rglob 계약이 빠진다.
    residue = bundle.workshop_dir() / "hooks" / "__pycache__"
    made = not residue.exists()
    try:
        residue.mkdir(parents=True, exist_ok=True)
        pyc = residue / "editor_mcp.cpython-312.pyc"
        pyc.write_bytes(b"\x00\x9d\xf0\r\r\n")          # 실제 .pyc 처럼 utf-8 이 아니다
        after = [r for r, _s in bundle.workshop_files("requester")]
        check("[중요] `__pycache__` 가 있어도 배달 목록에 안 들어온다",
              not any("__pycache__" in r or r.endswith(".pyc") for r in after),
              str([r for r in after if "pycache" in r or r.endswith(".pyc")]))
        check("그러면서 나머지 자산 수는 그대로다", len(after) == len(rels), f"{len(after)} vs {len(rels)}")
        check("판정은 경로 하나로도 답한다", bundle.is_build_residue(pyc)
              and not bundle.is_build_residue(bundle.workshop_dir() / "hooks" / "editor_mcp.py"))
    finally:
        for p in sorted(residue.rglob("*"), reverse=True):
            p.unlink()
        if made:
            residue.rmdir()

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
    # [주의] 실측 절은 **자기 픽스처 트윈**에서 잰다 — 실제 레지스트리(`NS/` 는 git 밖)를 읽으면
    #    격리 worktree(⑦ 검사 트리)에서 트윈이 없어 실패한다(`#815` ⑤). 단정은 같다.
    import tempfile
    from unittest.mock import patch
    tmp = Path(tempfile.mkdtemp(prefix="bundle-ns-"))
    try:
        (tmp / "projects.yaml").write_text("version: 1\nactive: NS\nprojects:\n- NS\n",
                                           encoding="utf-8")
        src = tmp / "NS" / "repo" / "Source"
        (src / "NS").mkdir(parents=True)
        (tmp / "NS" / "repo" / "NS.uproject").write_text("{}\n", encoding="utf-8")
        for t in ("NS", "NSEditor"):
            (src / f"{t}.Target.cs").write_text("//\n", encoding="utf-8")
        (src / "NS" / "NS.Build.cs").write_text("//\n", encoding="utf-8")
        with patch.dict(os.environ, {"AX_PROJECTS_ROOT": str(tmp)}):
            blk = bundle.managed_block("NS", f)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
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

    🔴 [중요] **2026-09-20 에 하나가 더 나왔다 — `rules/session-management.md`.** 그때는
    `#292` 가 `rules/` 를 「프로젝트 언급」으로만 훑어서 안 걸렸다. 이 문서는 ModularStage 를
    이름으로 부르지 않고 **전제로** 깐다:

        "how Claude should implement session lifecycle … for **this Listen Server project**.
         The architecture assumes a private gathering platform where clients are trusted."

    NS 는 Third Person 템플릿 기반이라 그 전제가 **거짓**이다. 같은 세션에서 나온 더 큰
    건(정본 `.claude/CLAUDE.md` 의 머리 175줄이 통째로 ModularStage 문서였던 것)과 **같은
    부류**이고, 사용자 결정으로 함께 갈랐다.
    [주의] 그래서 판정 기준은 「이름을 부르나」가 아니라 **「다른 프로젝트에서 거짓이 되나」**다.
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
          own == {".claude/rules/mission-editor-mcp.md",
                  ".claude/rules/session-management.md"}, str(own))
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
    check("[중요] 빈 settings 에 관리 훅이 등록된다", len(ev) == 2, str(got))
    completion = [e for e in ev if any("work_completion.py" in h.get("command", "")
                                      for h in e.get("hooks", []))]
    check("등록·개선요청 및 실패 후 감시 재개 훅이 세션을 깨운다",
          len(completion) == 1 and completion[0]["hooks"][0].get("asyncRewake") is True,
          str(completion))
    check("실패 고지 뒤 일반 도구 호출에도 감시가 재개된다",
          len(completion) == 1 and completion[0].get("matcher") == "", str(completion))
    # 🔴 [중요] **쓰는 쪽과 검사하는 쪽이 같은 dict 를 만든다** — `check` 는 정확 일치로 비교하는데
    #    조립이 두 자리에 있었고, `asyncRewake` 가 붙었을 때 쓰는 쪽만 갱신돼 **정상 배달을
    #    「훅 미등록」으로 답했다**(실측 2026-09-10 `.33`). 이 못이 그 어긋남을 잡는다.
    for _f in (r, lin):
        _got = _json.loads(bundle.merge_settings_json("", _f))
        for _ev, _m, _rel, _t in spec.managed_hooks_for(_f.role):
            check(f"검사기 기대값이 배달 결과와 같다 ({_f.os} · {_rel})",
                  bundle.hook_entry(_m, _rel, _t, _f) in _got["hooks"][_ev],
                  f"{bundle.hook_entry(_m, _rel, _t, _f)} not in {_got['hooks'][_ev]}")

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


# ── codex 몫 (`#402`) — 진입 문서와 MCP 등록 ─────────────────────

def test_codex_entry_doc() -> None:
    """🔴 [중요] **codex 는 계층 로드를 하지 않는다** — `AGENTS.md` 는 자족해야 한다.

    실측 2026-09-08(`docs/orchestrator-rules.md` §3.1): Claude 는 저장소에서 시작해도 부모의
    홈 지침까지 싣는데 codex 는 그 저장소 것만 싣는다. 그래서 `CLAUDE.md` 만 배달하면 codex
    세션은 **명령 블록을 못 본다** — 마일스톤 6 에 그 실패가 적혀 있다(`AGENTS.md` 에
    `master.client`·`AX_PROJECTS_ROOT` **0건** → codex 가 환경 전제에 걸려 멈췄다).
    """
    f = _facts(role="worker", codex="0.153.4")
    merged = bundle.merge_claude_md("", "ModularStage", f)

    # ⑴ 없으면 CLAUDE.md 병합 결과를 **그대로** 시드로 쓴다 (두 번째 `/init` 을 안 태운다)
    got = bundle.codex_entry_text("", merged, "ModularStage", f)
    # [주의] **글자까지 같지는 않다** — 정체성 세 줄만 codex 의 것으로 고친다(`test_codex_identity`).
    #    본문은 그대로여야 한다: 길이 차이가 교정분을 넘으면 산문을 건드린 것이다.
    check("[중요] AGENTS.md 가 없으면 CLAUDE.md 병합 결과를 시드로 쓴다",
          abs(len(got) - len(merged)) < 300 and got.count("\n") == merged.count("\n"),
          f"{len(got)} vs {len(merged)}")
    check("  그래서 자족적이다 — AX 블록이 들어 있다", bundle.MD_BEGIN in got)

    # ⑵ 사람이 쓴 AGENTS.md 가 있으면 **블록만** 얹는다
    human = "# 내 코덱스 지침\n\n이 줄은 사람이 썼다.\n"
    got2 = bundle.codex_entry_text(human, merged, "ModularStage", f)
    check("[중요] 사람이 쓴 AGENTS.md 를 덮지 않는다", "이 줄은 사람이 썼다." in got2)
    check("  그 위에 AX 블록을 얹는다", bundle.MD_BEGIN in got2 and bundle.MD_END in got2)
    check("  CLAUDE.md 전문을 다시 밀어넣지 않는다 (사람 문서를 밀어내지 않는다)",
          got2.startswith("# 내 코덱스 지침"))

    # ⑶ 마커가 있으면 그 사이만 교체 — 블록이 두 번 붙지 않는다 (`.2` 전례, 2026-08-09)
    stale = human + "\n" + bundle.MD_BEGIN + "\n낡은 내용\n" + bundle.MD_END + "\n꼬리\n"
    got3 = bundle.codex_entry_text(stale, merged, "ModularStage", f)
    check("[중요] 블록이 두 번 붙지 않는다", got3.count(bundle.MD_BEGIN) == 1, str(got3.count(bundle.MD_BEGIN)))
    check("  낡은 내용은 사라진다", "낡은 내용" not in got3)
    check("  블록 뒤의 사람 글은 남는다", "꼬리" in got3)

    # ⑷ 선언 — 워킹트리 오염을 막는 자리에 들어 있어야 한다
    check("🔴 [중요] AGENTS.md 가 git 제외 목록에 있다 (더티 체크가 파견을 막는다)",
          "/AGENTS.md" in spec.git_excludes_for("worker")
          and "/AGENTS.md" in spec.git_excludes_for("requester"))
    check("  ambient 관리 목록에도 있다 (추적 중이면 이름으로 보고된다)",
          "AGENTS.md" in spec.AMBIENT_MANAGED)
    check("  진입 문서 선언은 한 곳이다", spec.ENTRY_DOCS[1] == ("codex", "AGENTS.md"))


def test_codex_mcp_registration() -> None:
    """[중요] **파일을 쓰지 않고 `codex mcp add` 를 부른다** — 쓰는 쪽과 읽는 쪽을 codex 로 맞춘다.

    `#385` 에서 정확히 그 병을 앓았다: 스킬 파일은 **정상 배달돼 있었는데** codex 가 그 경로를
    안 봐서 `ax-work` 가 빈 참조가 됐다. 파일이 맞는 것과 도구가 그것을 보는 것은 다른 사실이다.
    """
    calls: list = []
    entry_json = ('{"name":"ax-client","enabled":true,"transport":'
                  '{"type":"stdio","command":"python3",'
                  '"args":[".ax/lib/axmaster/clientside/client_mcp.py"]}}')

    def fake_ssh(host, user, cmd, *, timeout=None):
        calls.append(cmd)
        if "codex mcp get" in cmd:
            return 0, entry_json
        return 0, ""

    saved = bundle._ssh
    bundle._ssh = fake_ssh
    try:
        f = _facts(role="worker", codex="0.153.4")
        got = bundle.codex_mcp_add(f, "ax-client")
        check("[중요] 등록하고 **되읽어 대조**한다 (「썼다」는 보고를 믿지 않는다)",
              "[완료]" in got, got)
        check("  add 와 get 을 둘 다 부른다",
              any("codex mcp add" in c for c in calls)
              and any("codex mcp get ax-client --json" in c for c in calls), str(calls))
        check("[중요] 명령은 `.mcp.json` 항목과 같은 출처다 (두 도구에 다른 명령이 가지 않는다)",
              bundle.mcp_entry_for(f)["command"] in bundle.codex_mcp_cmd(f, "ax-client"))

        # Windows Codex 샌드박스는 사용자별 `py`가 설치본을 못 찾을 수 있어 프로브한 절대경로다.
        win = _facts(role="requester", os="windows", home=r"C:\Users\USER",
                     path=r"C:\Users\USER\Documents\ModularStage", codex="0.153.4",
                     python=r"C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe")
        check("[중요] codex MCP도 같은 Python 절대경로로 등록한다",
              win.python in bundle.codex_mcp_cmd(win, "ax-client"),
              bundle.codex_mcp_cmd(win, "ax-client"))

        # 🔴 rc 로 판정하지 않는다 — 없는 이름에도 `codex mcp get` 은 rc=0 이다 (실측 2026-09-12)
        calls.clear()

        def ssh_missing(host, user, cmd, *, timeout=None):
            calls.append(cmd)
            if "codex mcp get" in cmd:
                return 0, "Error: No MCP server named 'ax-client' found."
            return 0, ""

        bundle._ssh = ssh_missing
        check("🔴 [중요] rc=0 + 비-JSON 을 「못 찾음」으로 읽는다",
              bundle.codex_mcp_get(f, "ax-client") == {})
        bad = bundle.codex_mcp_add(f, "ax-client")
        check("  그래서 등록 실패를 [완료] 로 답하지 않는다", "[완료]" not in bad, bad)

        # 내용이 다르면 **무엇이 다른지** 말한다
        def ssh_other(host, user, cmd, *, timeout=None):
            if "codex mcp get" in cmd:
                return 0, ('{"name":"ax-client","transport":{"type":"stdio",'
                           '"command":"python2","args":["/wrong.py"]}}')
            return 0, ""

        bundle._ssh = ssh_other
        diff = bundle.codex_mcp_add(f, "ax-client")
        check("[중요] 다르면 codex 가 보는 값을 말한다 (합계만 찍지 않는다)",
              "python2" in diff, diff)
    finally:
        bundle._ssh = saved

    # codex 가 없으면 **건너뛰되 사유를 말한다** — 침묵이 이틀을 태웠다 (리포트 44)
    nocodex = _facts(role="worker", codex="")
    skipped = bundle.codex_mcp_add(nocodex, "ax-client")
    check("[중요] codex 가 없으면 건너뛴다 (fail-open — 배달을 막지 않는다)",
          "건너뜀" in skipped, skipped)
    check("  그리고 **왜** 건너뛰었는지 찍는다", "codex" in skipped and "[주의]" in skipped, skipped)

    # 🔴 토큰 헤더가 필요한 것은 이 경로로 보내지 않는다 (사용자 결정 2026-09-12)
    check("🔴 [중요] codex 에 등록하는 것은 stdio 뿐이다 — ax-projects 는 빠진다",
          "ax-projects" not in spec.codex_mcp_for("requester")
          and "ax-client" in spec.codex_mcp_for("requester"),
          str(spec.codex_mcp_for("requester")))


def test_project_local_codex_surfaces() -> None:
    """`#699` — 스킬과 MCP 모두 체크아웃 로컬 정본을 갖는다."""
    f = _facts(role="worker", codex="0.153.4")
    check("프로젝트 스킬은 `.agents/skills`",
          spec.project_skill_rel("ax-work") == ".agents/skills/ax-work/SKILL.md")
    excludes = spec.git_excludes_for("worker")
    check("프로젝트 Codex 관리 영역을 Git 에서 뺀",
          "/.agents/" in excludes and "/.codex/" in excludes, str(excludes))
    merged = bundle.codex_project_mcp_text("# human\n", f, "ax-client")
    check("프로젝트 MCP 블록이 사람 설정을 보존",
          "# human" in merged and "[mcp_servers.ax-client]" in merged, merged)
    merged2 = bundle.codex_project_mcp_text(merged, f, "ax-client")
    check("MCP 관리 블록은 멱등",
          merged2.count(bundle.CODEX_MCP_BEGIN) == 1, merged2)
    calls = []
    saved = bundle._ssh
    bundle._ssh = lambda host, user, cmd, timeout=None: (
        calls.append(cmd),
        (0, '{"transport":{"type":"stdio","command":"python3","args":[]}}'))[1]
    try:
        bundle.codex_mcp_get(f, "ax-client", project=True)
    finally:
        bundle._ssh = saved
    check("실제 MCP 검사는 체크아웃에서 실행",
          f.path in calls[0] and "codex mcp get" in calls[0], calls[0])


def test_codex_identity() -> None:
    """🔴 [중요] **시드한 `AGENTS.md` 가 자기를 `CLAUDE.md` 라고 소개했다** (`#402`, `.2` 실물).

    1행 `# CLAUDE.md` · 3행 *"guidance to **Claude Code** (claude.ai/code)"*. codex 가 읽으면
    「남의 문서」로 읽을 여지가 그대로 있고, 마일스톤 6 에 적힌 실패(진입 문서가 자족하지
    못해 codex 가 멈췄다)와 같은 종류다.
    """
    f = _facts(role="worker", codex="0.153.4")
    merged = bundle.merge_claude_md("", "ModularStage", f)
    got, missed = bundle.apply_codex_identity(merged)

    check("[중요] 제목이 AGENTS.md 다", got.lstrip().startswith("# AGENTS.md"),
          got.lstrip()[:30])
    check("  더는 Claude Code 전용이라 말하지 않는다",
          "provides guidance to Claude Code" not in got)
    check("  codex 가 계층 로드를 안 한다는 사실을 스스로 적는다",
          "does not load parent directories" in got)
    check("[주의] gitignore 문장이 /AGENTS.md 를 포함한다",
          "`/AGENTS.md`" in got, str([l for l in got.splitlines() if "gitignored" in l][:1]))
    check("[중요] 정본 머리글이 그대로면 못 찾은 것이 없다", missed == (), str(missed))

    # 본문 산문은 건드리지 않는다 — 「정본은 payload/claude_md/<P>.md」는 **맞는 설명**이다
    body = bundle.claude_md_body("ModularStage")
    tail = body.splitlines()[4].strip()          # 머리 3줄 아래 = 교정 대상이 아닌 산문
    check("[중요] 본문 산문은 그대로다 (정체성 세 줄만 고친다)", tail and tail in got, tail[:60])

    # 멱등 — 나중에 정본이 도구 중립으로 바뀌어도 시끄러워지지 않는다
    again, missed2 = bundle.apply_codex_identity(got)
    check("[주의] 멱등이다", again == got and missed2 == (), str(missed2))

    # 못 찾으면 **조용히 넘기지 않는다**
    _, missed3 = bundle.apply_codex_identity("아무 관계 없는 글")
    check("[중요] 정본 머리글이 바뀌면 못 찾았다고 말한다", len(missed3) == 3, str(missed3))

    # 시드일 때만 교정한다 — 사람이 쓴 AGENTS.md 는 제목까지 사람 것이다
    human = "# 내 코덱스 지침\n\n사람이 썼다.\n"
    kept = bundle.codex_entry_text(human, merged, "ModularStage", f)
    check("[중요] 사람이 쓴 AGENTS.md 의 제목은 안 건드린다",
          kept.startswith("# 내 코덱스 지침"), kept[:30])
    seeded = bundle.codex_entry_text("", merged, "ModularStage", f)
    check("  시드일 때는 교정한다", seeded.lstrip().startswith("# AGENTS.md"))


def test_dispatched_work_needs_no_consent() -> None:
    """🔴 **파견된 조각에는 「고치기 전 동의」가 이미 나 있다** (실측 2026-09-12).

    `.2` 의 codex 가 구현 계획까지 정확히 세워 놓고 *"AGENTS.md 규약상 … 승인해 주세요"* 로
    멈춰 **같은 조각이 4번 실패**했다. 비대화형이라 승인해 줄 사람이 없어 `RESULT: BLOCKED`
    로 끝난다. **모델이 규칙을 어긴 것이 아니라 정직하게 따른 것**이고, 규칙에 예외가 없던
    것이 결함이었다.

    [중요] 이 조항은 **관리 블록 안**에 있어야 한다 — 본문은 사람 글이라 재배달이 덮지
    않는다(`merge_claude_md`). 이미 배달된 기계에 닿으려면 블록이어야 한다.
    """
    f = _facts(role="worker")
    b = bundle.managed_block("ModularStage", f)
    check("🔴 [중요] 파견 조각은 묻지 말고 진행한다고 적혀 있다",
          "묻지 말고 진행한다" in b, b[-400:])
    check("  등재가 곧 승인이라는 근거를 적는다", "등재한 것 자체가 승인" in b)
    check("  실측 근거를 남긴다 (왜 이 예외가 생겼나)", "4번 실패" in b)
    check("[주의] 예외는 **지정된 파일**까지다 — `.uproject`·`Config` 는 그대로 동의가 필요",
          "목록 밖 파일" in b and "#298" in b)
    check("🔴 [중요] **관리 블록 안**이다 (본문이면 기존 기계에 안 닿는다)",
          b.startswith(bundle.MD_BEGIN) and b.rstrip().endswith(bundle.MD_END))

    # 🔴 [중요] **요청자에게는 주지 않는다** — 그 트리는 사람이 편집 중이고, 거기서
    #    에이전트가 묻지 않고 고치는 것이 더티 체크가 막던 사고다. 기존 가드
    #    (*"요청자 블록은 ax-work 를 가리키지 않는다"*)가 내 첫 배선을 잡아 세웠다.
    r = bundle.managed_block("ModularStage", _facts(role="requester"))
    check("🔴 [중요] 요청자에게는 이 예외를 주지 않는다 (사람이 편집 중인 트리다)",
          "묻지 말고 진행한다" not in r)


def test_residency_reconcile_removes_forbidden_registration() -> None:
    """원하는 상태가 없음이면 deliver가 과거 등록도 걷고 부재를 되읽는다."""
    f = _facts(role="worker", os="linux", ue5="", path="/home/sim/trunk/NS")
    state = {"registered": True}
    calls = []

    class FakeRegistry:
        @staticmethod
        def load():
            return type("R", (), {"active": "NS"})()

    def fake_ssh(host, user, cmd, *, timeout=None):
        calls.append(cmd)
        if "| crontab -" in cmd:
            state["registered"] = False
            return 0, ""
        if cmd == "crontab -l 2>/dev/null":
            return 0, (f"*/5 * * * * cd {f.path} && /usr/bin/python3 x\n"
                       if state["registered"] else "")
        return 0, ""

    old_ssh, old_registry = bundle._ssh, bundle.Registry
    bundle._ssh, bundle.Registry = fake_ssh, FakeRegistry
    try:
        got = bundle._register_residency("NS", f)
    finally:
        bundle._ssh, bundle.Registry = old_ssh, old_registry
    check("[중요] 등록 불필요 상태를 skipped로 말한다", "skipped" in got, str(got))
    check("[중요] 남아 있던 등록을 제거한다", not state["registered"], str(calls))
    check("[중요] 제거 뒤 다시 조회한다",
          calls.count("crontab -l 2>/dev/null") == 2, str(calls))


def test_check_mount_lookup_is_fail_closed() -> None:
    """check가 레지스트리 오류를 빈 마운트로 바꾸지 않고 실제 active를 쓴다."""
    class MountedNS:
        @staticmethod
        def load():
            return type("R", (), {"active": "NS"})()

    class BrokenRegistry:
        @staticmethod
        def load():
            raise RuntimeError("registry unavailable")

    old_registry = bundle.Registry
    try:
        bundle.Registry = MountedNS
        mounted = client_cli._mounted_project_for_check()
        check("check는 bundle.Registry의 실제 마운트를 읽는다", mounted == "NS", mounted)
        decision = __import__("client.init.residency", fromlist=["desired_state"]).desired_state(
            "ModularStage", mounted, _facts(role="worker", ue5="ue5"))
        check("NS 마운트에서는 ModularStage 미등록이 정상", not decision.required,
              decision.reason)

        bundle.Registry = BrokenRegistry
        try:
            client_cli._mounted_project_for_check()
            check("[중요] 레지스트리 조회 실패를 숨기지 않는다", False)
        except RuntimeError as exc:
            check("[중요] 레지스트리 조회 실패를 숨기지 않는다",
                  str(exc) == "registry unavailable", str(exc))
    finally:
        bundle.Registry = old_registry


def test_update_covers_every_registered_project() -> None:
    """update는 프로젝트 선택 없이 레지스트리 전체를 deliver→check 한다."""
    calls = []

    class AllProjects:
        names = ["NS", "ModularStage"]

        @staticmethod
        def check():
            return []

    class FakeRegistry:
        @staticmethod
        def load():
            return AllProjects()

    def fake_deliver(project, *, init=False, only=""):
        calls.append(("deliver", project, init, only))
        return 0

    def fake_check(project, *, only="", stats=None):
        calls.append(("check", project, only))
        return 0

    old_registry = bundle.Registry
    old_deliver, old_check = client_cli.cmd_deliver, client_cli.cmd_check
    old_head, old_dirty = client_cli._master_head, client_cli._master_dirty
    bundle.Registry = FakeRegistry
    client_cli.cmd_deliver, client_cli.cmd_check = fake_deliver, fake_check
    client_cli._master_head = lambda: "a" * 40
    client_cli._master_dirty = lambda: False
    try:
        rc = client_cli.main(["update", "--init", "--all"])
    finally:
        bundle.Registry = old_registry
        client_cli.cmd_deliver, client_cli.cmd_check = old_deliver, old_check
        client_cli._master_head, client_cli._master_dirty = old_head, old_dirty
    check("전체 업데이트가 성공한다", rc == 0, str(rc))
    check("전체를 배달한 뒤 전체를 검사해 마지막 덮어쓰기를 잡는다", calls == [
        ("deliver", "NS", True, ""), ("deliver", "ModularStage", True, ""),
        ("check", "NS", ""), ("check", "ModularStage", ""),
    ], str(calls))


def test_ensure_ignored_is_one_call_and_strict() -> None:
    """`#655` — exclude 줄을 연결 한 번에 넣고, 확인되지 않은 줄이 하나라도 있으면 실패다."""
    calls = []
    keep = bundle._ssh
    try:
        lines = spec.git_excludes_for("worker")
        for f in (_facts(), _facts(os="windows", path=r"E:\\trunk\\X")):
            calls.clear()
            bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, "\n".join(
                "OK " + ln for ln in lines)))
            check(f"{f.os}: 한 번의 연결로 전부", bundle._ensure_ignored(f) is True
                  and len(calls) == 1, str(len(calls)))
            check(f"{f.os}: 모든 줄이 명령에 있다", all(ln in calls[0] for ln in lines), calls[0][:200])
        bundle._ssh = lambda h, u, cmd, **k: (0, "\n".join("OK " + ln for ln in lines[:-1]))
        raised = ""
        try:
            bundle._ensure_ignored(_facts())
        except bundle.BundleError as e:
            raised = str(e)
        check("[중요] 확인 안 된 줄이 있으면 그 줄 이름으로 실패", lines[-1] in raised, raised)
    finally:
        bundle._ssh = keep


def test_fetch_prune_delivery_and_check() -> None:
    """`#787` ③ — 워커 클론에 `fetch.prune=true` 를 걸고(두 OS 모양 · 멱등 · 되읽기),
    실패는 삼키지 않으며, `check` 는 값을 재서 판정한다. requester(사람 클론)는 건드리지 않는다."""
    calls = []
    keep = bundle._ssh
    try:
        lin = _facts()
        win = _facts(os="windows", path=r"C:\trunk\AXCluster", home=r"C:\Users\USER")
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, "true"))
        got = bundle.ensure_fetch_prune(lin)
        check("리눅스: 한 번의 연결로 설정+되읽기",
              len(calls) == 1 and calls[0] == ("git -C /home/sim/trunk/ModularStage config --local "
                                                "fetch.prune true && git -C /home/sim/trunk/ModularStage "
                                                "config --local --get fetch.prune"), calls[0])
        check("리눅스: 완료 보고", got.startswith("[완료]"), got)
        calls.clear()
        got = bundle.ensure_fetch_prune(win)
        check("윈도우(cmd): 경로를 큰따옴표로 · --local 로컬 config",
              len(calls) == 1 and calls[0] == ('git -C "C:\\trunk\\AXCluster" config --local '
                                               'fetch.prune true && git -C "C:\\trunk\\AXCluster" '
                                               'config --local --get fetch.prune'), calls[0])
        check("윈도우: 완료 보고", got.startswith("[완료]"), got)
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, "true\r"))
        check("윈도우: 끝의 CR 을 견딘다", bundle.ensure_fetch_prune(win).startswith("[완료]"))
        # 멱등 — 같은 명령을 두 번 내도 결과가 같다(git config 는 값 덮어쓰기)
        calls.clear()
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, "true"))
        a, b = bundle.ensure_fetch_prune(lin), bundle.ensure_fetch_prune(lin)
        check("멱등: 두 번 걸어도 같은 명령 · 같은 결과", a == b and calls[0] == calls[1]
              and "--add" not in calls[0], str(calls))

        for rc, out, why in ((128, "fatal: not in a git directory", "rc≠0"),
                             (0, "", "빈 되읽기"), (0, "false", "값이 false")):
            bundle._ssh = lambda h, u, cmd, rc=rc, out=out, **k: (rc, out)
            raised = ""
            try:
                bundle.ensure_fetch_prune(lin)
            except bundle.BundleError as e:
                raised = str(e)
            check(f"[중요] 실패를 삼키지 않는다 — {why}", "fetch.prune" in raised, raised or "예외 없음")

        calls.clear()
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, "true"))
        req = _facts(role="requester", os="windows", path=r"C:\Users\USER\Documents\ModularStage")
        got = bundle.ensure_fetch_prune(req)
        check("🔴 requester(사람 클론)는 건드리지 않는다", not calls and got.startswith("건너뜀"), got)
        check("  check 도 requester 는 재지 않는다", bundle.check_fetch_prune(req) == (True, "")
              and not calls, str(calls))

        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, "true"))
        ok, note = bundle.check_fetch_prune(win)
        check("check: 값이 true 면 통과", ok and "fetch.prune=true" in note
              and calls[-1] == 'git -C "C:\\trunk\\AXCluster" config --local --get fetch.prune',
              f"{ok} {note} {calls[-1]}")
        bundle._ssh = lambda h, u, cmd, **k: (1, "")
        ok, note = bundle.check_fetch_prune(lin)
        check("check: 설정 없음(rc=1)이면 실패로 이름을 대 보고", not ok and "[실패]" in note
              and "없음" in note, note)
        bundle._ssh = lambda h, u, cmd, **k: (255, "ssh: connect timed out")
        ok, note = bundle.check_fetch_prune(lin)
        check("check: 연결 실패도 실패다(통과로 접지 않는다)", not ok and "rc=255" in note, note)
    finally:
        bundle._ssh = keep


def test_fetch_prune_wired_into_deliver_and_check() -> None:
    """`#787` ③ — 배달 결과에 `fetch_prune` 이 실리고, `cmd_check` 가 판정에 넣는다."""
    import inspect
    src = inspect.getsource(bundle._deliver)
    check("배달이 ensure_fetch_prune 을 부른다", '"fetch_prune": ensure_fetch_prune(facts)' in src)
    csrc = inspect.getsource(client_cli.cmd_check)
    check("check 가 check_fetch_prune 을 부른다", "bundle.check_fetch_prune(f)" in csrc)
    check("check 의 OK/FAIL·bad·#737 분류 셋 모두에 ok_prune 이 들어간다",
          csrc.count("ok_prune") >= 4, str(csrc.count("ok_prune")))
    check("#830 check 가 check_agy_model 을 부른다", "bundle.check_agy_model(f)" in csrc)
    check("#830 check 의 OK/FAIL·bad·#737 분류 셋 모두에 ok_agy 가 들어간다",
          csrc.count("ok_agy") >= 4, str(csrc.count("ok_agy")))


def test_agy_model_delivered_and_checked() -> None:
    """`#830` — config 에 정본 agy 모델 id 가 실리고, `check_agy_model` 이 없음·다름을 잡는다."""
    import json as _json
    from master import agy_models
    canon = agy_models.DEFAULT_MODEL
    for facts in (_facts(), _facts(os="windows", path=r"C:\trunk\AXCluster", home=r"C:\Users\USER")):
        cfg = bundle.config_for("ModularStage", facts)
        check(f"config 에 정본 agy_model 이 실린다 ({facts.os})",
              cfg["backends"].get("agy_model") == canon, str(cfg["backends"]))
    check("정본은 agy_models.DEFAULT_MODEL 하나다", bundle.agy_model() == canon)
    # [중요] agy_models 는 fcntl(리눅스 전용) — 배달물에 섞이면 윈도우 워커에서 import 가 죽는다
    srcs = [str(src) for role in (ROLE_WORKER, ROLE_REQUESTER)
            for _rel, src in bundle.payload_pairs(role)]
    check("[중요] agy_models.py 는 배달 목록에 없다",
          not any("agy_models" in s_ for s_ in srcs), str([s_ for s_ in srcs if "agy" in s_]))

    keep = bundle._remote_read
    try:
        lin = _facts()
        good = _json.dumps(bundle.config_for("ModularStage", lin))
        bundle._remote_read = lambda f, path: good
        ok, note = bundle.check_agy_model(lin)
        check("check: 정본과 같으면 통과", ok and canon in note, note)
        bundle._remote_read = lambda f, path: _json.dumps({"backends": {"agy": True}})
        ok, note = bundle.check_agy_model(lin)
        check("[중요] check: agy_model 이 없으면 실패", not ok and "없다" in note, note)
        bundle._remote_read = lambda f, path: _json.dumps({"backends": {"agy_model": "gemini-4-argon"}})
        ok, note = bundle.check_agy_model(lin)
        check("[중요] check: 값이 다르면 실패 + 두 값을 댄다",
              not ok and "gemini-4-argon" in note and canon in note, note)
        bundle._remote_read = lambda f, path: _json.dumps({"project": "ModularStage"})
        ok, note = bundle.check_agy_model(lin)
        check("check: backends 자체가 없으면 실패", not ok and "backends" in note, note)
        bundle._remote_read = lambda f, path: ""
        ok, note = bundle.check_agy_model(lin)
        check("check: 못 읽음도 실패다(통과로 접지 않는다)", not ok and "재지 못했다" in note, note)
        bundle._remote_read = lambda f, path: "{not json"
        ok, note = bundle.check_agy_model(lin)
        check("check: 깨진 JSON 도 실패다", not ok and "파싱" in note, note)
        paths = []
        bundle._remote_read = lambda f, path: (paths.append(path) or good)
        bundle.check_agy_model(_facts(os="windows", path=r"C:\trunk\AXCluster", home=r"C:\Users\USER"))
        check("윈도우: 역슬래시 경로로 config 를 읽는다",
              paths and paths[-1] == r"C:\trunk\AXCluster\.ax\config.json", str(paths))
    finally:
        bundle._remote_read = keep


def test_claude_mcp_local_add_skips_identical() -> None:
    """`#655` — 이미 같은 항목이면 remove·add 를 부르지 않는다. 다르면 종전대로 다시 넣는다."""
    f = _facts()
    keep = (bundle._ssh, bundle.claude_mcp_local_get)
    calls = []
    try:
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0, ""))
        bundle.claude_mcp_local_get = lambda ff, n: bundle.mcp_entry_for(ff)
        out = bundle.claude_mcp_local_add(f, "ax-client")
        check("[중요] 같으면 등록 명령을 안 부른다", calls == [] and "재등록 생략" in out, out)
        seq = [{"command": "old", "args": []}, bundle.mcp_entry_for(f)]
        bundle.claude_mcp_local_get = lambda ff, n: seq.pop(0)
        out = bundle.claude_mcp_local_add(f, "ax-client")
        check("다르면 다시 등록하고 되읽어 대조한다",
              len(calls) == 1 and "mcp add" in calls[0] and "[완료]" in out, out)
    finally:
        bundle._ssh, bundle.claude_mcp_local_get = keep


def test_check_stats_counters_are_not_shadowed() -> None:
    """`cmd_check` 의 `stats` 카운터가 출력용 목록으로 덮이지 않는다 (실측 2026-10-07).

    `dirty_only` 를 호스트 목록으로 다시 대입해 `stats["dirty_only"]` 가 목록이 됐고, dirty 트리에서
    `update` 가 실패 요약(`_label_check_failure`)을 만들다 TypeError 로 죽었다. 기존 #737 하네스는
    `cmd_check` 를 가짜로 끼워 이 경로를 못 탔다 — 그래서 소스에서 대입 자리를 센다.
    """
    import inspect
    import re
    src = inspect.getsource(client_cli.cmd_check)
    for name in ("behind_only", "dirty_only", "behind_dirty"):
        assigns = re.findall(rf"^\s*{name} = ", src, flags=re.M)     # 키워드 인자(`x=`)는 제외
        check(f"{name} 에 대입하는 곳은 초기화 한 곳뿐", len(assigns) == 1, str(assigns))
    check("통계 단위 해석이 정수를 받는다",
          client_cli._label_check_failure("P", {"bad": 1, "dirty_only": 1}, moved=False,
                                          dirty_start=True, became_dirty=False,
                                          started_at=0).startswith("P: check"))


def test_remote_hashes_and_skip_unchanged() -> None:
    """🔴 `#655` — 원격 해시를 한 번에 받고, 같은 파일은 디렉토리·scp·되읽기를 건너뛴다."""
    import hashlib
    calls = []
    keep = bundle._ssh
    cache = bundle._DeliveryCache()
    token = bundle._DELIVERY_CACHE.set(cache)
    try:
        lin = _facts()
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0,
            "aa" * 32 + "  /home/sim/a.md\n" + "bb" * 32 + "  /home/sim/b md.py\n"))
        got = bundle.remote_hashes(lin, ["/home/sim/a.md", "/home/sim/b md.py", "/home/sim/none"])
        check("리눅스: 한 번의 ssh 로 받는다", len(calls) == 1 and calls[0].startswith("sha256sum -- "),
              str(calls))
        check("리눅스: 경로→해시 (공백 든 경로 포함, 없는 파일은 빠진다)",
              got == {"/home/sim/a.md": "aa" * 32, "/home/sim/b md.py": "bb" * 32}, str(got))

        calls.clear()
        win = _facts(os="windows", path=r"E:\trunk\X", home=r"C:\Users\janus")
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (0,
            "CC" * 32 + "|E:\\trunk\\X\\.ax\\config.json\r\n"))
        got = bundle.remote_hashes(win, [r"E:\trunk\X\.ax\config.json", r"E:\it's.md"])
        check("윈도우: PowerShell 한 번 · 작은따옴표는 두 겹으로",
              len(calls) == 1 and "Get-FileHash" in calls[0] and "it''s" in calls[0], calls[0][:200])
        check("윈도우: 해시는 소문자로", got == {r"E:\trunk\X\.ax\config.json": "cc" * 32}, str(got))

        bundle._ssh = lambda h, u, cmd, **k: (255, "ssh 죽음")
        check("[주의] 연결 실패는 빈 결과 (종전 경로로 쓰고 되읽는다)",
              bundle.remote_hashes(lin, ["/x"]) == {})

        # 같으면 쓰지 않는다 — ssh·scp 를 한 번도 부르지 않는다
        calls.clear()
        bundle._ssh = lambda h, u, cmd, **k: (calls.append(cmd) or (1, "불려선 안 된다"))
        content = "본문\n"
        target = bundle._write_target(lin, ".ax/config.json", "checkout")
        cache.hashes[(lin.host, lin.user, target)] = hashlib.sha256(
            content.encode("utf-8")).hexdigest()
        out = bundle._remote_write(lin, ".ax/config.json", content, base="checkout")
        check("[중요] 해시가 같으면 연결 없이 끝난다", out == target and calls == [], str(calls))
        check("  건너뛴 수를 센다", cache.unchanged == 1, str(cache.unchanged))
    finally:
        bundle._ssh = keep
        bundle._DELIVERY_CACHE.reset(token)


def test_deliver_clears_hash_cache_even_on_error() -> None:
    """`#655` — 받아 둔 해시는 배달 한 번만 산다. 예외여도 비운다(낡은 해시로 건너뛰지 않게)."""
    f = _facts()
    keep = (bundle.remote_hashes, bundle._deliver, bundle.delivery_targets)
    try:
        bundle.delivery_targets = lambda p, ff, pi: ["/t"]
        bundle.remote_hashes = lambda ff, ts: {"/t": "ab" * 32}
        seen = {}

        def boom(*a, **k):
            seen.update(bundle._DELIVERY_CACHE.get().hashes)
            raise bundle.BundleError("중간 실패")
        bundle._deliver = boom
        try:
            bundle.deliver("X", f, project_init=object())
        except bundle.BundleError:
            pass
        check("배달 중에는 받아 둔 해시가 있다", (f.host, f.user, "/t") in seen, str(seen))
        check("[중요] 예외여도 끝나면 비운다", bundle._DELIVERY_CACHE.get() is None)
    finally:
        bundle.remote_hashes, bundle._deliver, bundle.delivery_targets = keep


def test_deliver_cache_isolation() -> None:
    """동일 호스트의 동시 호출·중첩·실패가 서로의 해시와 집계를 바꾸지 않는다."""
    import hashlib
    import threading
    from unittest.mock import patch
    f = _facts()
    target = bundle._write_target(f, "same", "checkout")
    barrier = threading.Barrier(2)
    finished = threading.Event()
    results, errors, restored = {}, [], []

    def hashes(ff, ts):
        content = threading.current_thread().name
        return {target: hashlib.sha256(content.encode()).hexdigest()}

    def fake(project, ff, **kw):
        content = threading.current_thread().name
        barrier.wait(timeout=5)
        if content == "fails":
            finished.set()
            raise bundle.BundleError("fixture")
        finished.wait(timeout=5)
        for _ in range(7):
            bundle._remote_write(ff, "same", content, base="checkout")
        return {}

    def run():
        try:
            results[threading.current_thread().name] = bundle.deliver("X", f, project_init=object())
        except bundle.BundleError:
            errors.append(threading.current_thread().name)
        finally:
            restored.append(bundle._DELIVERY_CACHE.get() is None)

    with patch.object(bundle, "remote_hashes", side_effect=hashes), \
            patch.object(bundle, "delivery_targets", return_value=[target]), \
            patch.object(bundle, "_deliver", side_effect=fake), \
            patch.object(bundle, "_ssh", side_effect=AssertionError("unexpected ssh")):
        threads = [threading.Thread(target=run, name=name) for name in ("survives", "fails")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    check("동일 호스트 한쪽 실패 후 다른 호출의 해시·집계 유지",
          results == {"survives": {"unchanged": 7}} and errors == ["fails"], str((results, errors)))
    check("각 호출 종료 후 캐시 없음", len(restored) == 2 and all(restored))

    outer = bundle._DeliveryCache({(f.host, f.user, target): "outer"}, 7)
    token = bundle._DELIVERY_CACHE.set(outer)
    try:
        def nested(*args, **kw):
            check("중첩 호출 캐시는 바깥과 독립", bundle._DELIVERY_CACHE.get() is not outer
                  and not bundle._DELIVERY_CACHE.get().hashes)
            return {}
        with patch.object(bundle, "_deliver", side_effect=nested), \
                patch.object(bundle, "remote_hashes", return_value={}), \
                patch.object(bundle, "delivery_targets", return_value=[]):
            bundle.deliver("X", f, project_init=object())
            bundle.deliver("X", f, dry_run=True, project_init=object())
            with patch.dict(os.environ, {"AX_DELIVER_ALL": "1"}):
                bundle.deliver("X", f, project_init=object())
        check("정상·dryrun·전체배달 후 바깥 캐시 복원", bundle._DELIVERY_CACHE.get() is outer
              and outer.unchanged == 7 and outer.hashes[(f.host, f.user, target)] == "outer")
        with patch.object(bundle, "_deliver", side_effect=bundle.BundleError("nested fixture")), \
                patch.object(bundle, "remote_hashes", return_value={}), \
                patch.object(bundle, "delivery_targets", return_value=[]):
            try:
                bundle.deliver("X", f, project_init=object())
            except bundle.BundleError:
                pass
        check("중첩 실패 후에도 바깥 캐시 복원", bundle._DELIVERY_CACHE.get() is outer
              and outer.unchanged == 7)
    finally:
        bundle._DELIVERY_CACHE.reset(token)
    check("후속 호출은 캐시 없이 시작", bundle._DELIVERY_CACHE.get() is None)


def _run_update_mount(active, *, argv=None, all_projects=False):
    """`#655`·`#745` — 마운트 기준 update 하네스 (SSH·배달 없음)."""
    import contextlib
    import io
    calls = []

    class Projects:
        names = ["NS", "ModularStage", "AXCluster"]

        @staticmethod
        def check():
            return []
    Projects.active = active

    class FakeRegistry:
        @staticmethod
        def load():
            return Projects()

    saved = (bundle.Registry, client_cli.cmd_deliver, client_cli.cmd_check,
             client_cli._master_head, client_cli._master_dirty)
    bundle.Registry = FakeRegistry
    client_cli.cmd_deliver = lambda project, *, init=False, only="": calls.append(("deliver", project)) or 0
    client_cli.cmd_check = lambda project, *, only="", stats=None: calls.append(("check", project)) or 0
    client_cli._master_head = lambda: "a" * 40
    client_cli._master_dirty = lambda: False
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = (client_cli.main(argv) if argv is not None
                  else client_cli.cmd_update(all_projects=all_projects))
    finally:
        (bundle.Registry, client_cli.cmd_deliver, client_cli.cmd_check,
         client_cli._master_head, client_cli._master_dirty) = saved
    return rc, calls, out.getvalue()


def test_update_defaults_to_mounted_project() -> None:
    """🔴 `#655`·`#745` (사용자 결정 2026-10-06) — 기본은 마운트 하나, `--all` 은 등록 전체."""
    rc, calls, out = _run_update_mount("AXCluster")
    check("[중요] 기본은 마운트된 프로젝트만 배달·검사한다",
          rc == 0 and calls == [("deliver", "AXCluster"), ("check", "AXCluster")], str(calls))
    check("  대상과 --all 안내를 찍는다", "마운트된 AXCluster 만" in out and "--all" in out, out[:300])

    rc, calls, _ = _run_update_mount("AXCluster", argv=["update"])
    check("CLI 기본도 마운트만", rc == 0 and [c[1] for c in calls] == ["AXCluster", "AXCluster"],
          str(calls))
    rc, calls, out = _run_update_mount("AXCluster", argv=["update", "--all"])
    check("[중요] --all 은 등록 전체 (종전 동작)",
          rc == 0 and [c[1] for c in calls if c[0] == "deliver"] == ["NS", "ModularStage", "AXCluster"],
          str(calls))
    check("  --all 완료 문구는 개수를 말한다", "등록 프로젝트 3개" in out, out[-200:])

    rc, calls, out = _run_update_mount("")
    check("[중요] 마운트가 비면 폴백 없이 멈춘다 (rc 2, 아무것도 안 함)",
          rc == 2 and calls == [] and "폴백은 없다" in out, out)
    rc, calls, out = _run_update_mount("Ghost")
    check("마운트가 등록에 없으면 멈춘다", rc == 1 and calls == [] and "Ghost" in out, out)


def test_update_reports_partial_failure() -> None:
    """한 프로젝트 실패가 전체 성공으로 접히지 않고, 나머지 업데이트는 계속된다."""
    calls = []

    class AllProjects:
        names = ["NS", "ModularStage"]

        @staticmethod
        def check():
            return []

    class FakeRegistry:
        @staticmethod
        def load():
            return AllProjects()

    def fake_deliver(project, *, init=False, only=""):
        calls.append(("deliver", project))
        return 1 if project == "NS" else 0

    def fake_check(project, *, only="", stats=None):
        calls.append(("check", project))
        return 0

    old_registry = bundle.Registry
    old_deliver, old_check = client_cli.cmd_deliver, client_cli.cmd_check
    old_head, old_dirty = client_cli._master_head, client_cli._master_dirty
    bundle.Registry = FakeRegistry
    client_cli.cmd_deliver, client_cli.cmd_check = fake_deliver, fake_check
    client_cli._master_head = lambda: "a" * 40
    client_cli._master_dirty = lambda: False
    try:
        rc = client_cli.cmd_update(all_projects=True)
    finally:
        bundle.Registry = old_registry
        client_cli.cmd_deliver, client_cli.cmd_check = old_deliver, old_check
        client_cli._master_head, client_cli._master_dirty = old_head, old_dirty
    check("부분 실패면 전체 명령도 실패한다", rc == 1, str(rc))
    check("실패한 프로젝트는 검사하지 않고 다음 등록 프로젝트를 계속한다", calls == [
        ("deliver", "NS"), ("deliver", "ModularStage"), ("check", "ModularStage"),
    ], str(calls))


def _run_update_with_heads(heads, check_results, dirties=(False,)):
    """`#737` 하네스 — HEAD·dirty 리더와 deliver/check 를 주입하고 출력을 잡는다 (SSH·배달 없음).

    ``heads``: `_master_head` 가 차례로 돌려줄 값(시작 → 검사 직전 → 끝).
    ``dirties``: `_master_dirty` 가 차례로 돌려줄 값(같은 세 시점, 마지막 값 반복).
    ``check_results``: 프로젝트 → (rc, stats).
    """
    import contextlib
    import io

    class AllProjects:
        names = list(check_results)

        @staticmethod
        def check():
            return []

    class FakeRegistry:
        @staticmethod
        def load():
            return AllProjects()

    seq = list(heads)

    def fake_check(project, *, only="", stats=None):
        rc, st = check_results[project]
        if stats is not None:
            stats.update(st)
        return rc

    dseq = list(dirties)
    saved = (bundle.Registry, client_cli.cmd_deliver, client_cli.cmd_check, client_cli._master_head,
             client_cli._master_dirty)
    bundle.Registry = FakeRegistry
    client_cli.cmd_deliver = lambda project, *, init=False, only="": 0
    client_cli.cmd_check = fake_check
    client_cli._master_head = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
    client_cli._master_dirty = lambda: dseq.pop(0) if len(dseq) > 1 else (dseq[0] if dseq else None)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = client_cli.cmd_update(all_projects=True)
    finally:
        (bundle.Registry, client_cli.cmd_deliver, client_cli.cmd_check,
         client_cli._master_head, client_cli._master_dirty) = saved
    return rc, out.getvalue()


def test_update_reports_head_movement() -> None:
    """🔴 `#737` (사용자 결정 2026-10-05) — 실행 중 HEAD 이동을 따로 말하고 초록불로 바꾸지 않는다."""
    A, B = "5fc6786" + "0" * 33, "4ac3099" + "0" * 33
    ok, behind = (0, {"bad": 0, "behind_only": 0}), (1, {"bad": 2, "behind_only": 2})

    rc, out = _run_update_with_heads([A, A, A], {"NS": ok, "ModularStage": ok})
    check("이동 없음 + 검사 통과 → 종전대로 성공", rc == 0 and "[완료]" in out, out[-200:])
    check("  시작 HEAD 를 고정해 찍는다", "[update] 시작 마스터 HEAD 5fc6786" in out, out[:200])
    check("  이동 문구가 없다", "움직였다" not in out, out)

    rc, out = _run_update_with_heads([A, A, A], {"NS": ok, "ModularStage": behind})
    check("이동 없음 + 뒤처짐 → 종전 그대로 「check」 실패", rc == 1
          and "전체 업데이트 실패: ModularStage: check\n" in out and "이동 탓" not in out, out[-300:])

    rc, out = _run_update_with_heads([A, B, B], {"NS": ok, "ModularStage": behind})
    check("[중요] 배달 중 이동 → rc 는 여전히 1 (초록불 금지)", rc == 1, str(rc))
    check("  이동 사실을 따로 한 줄로 말한다",
          "[중요] 실행 중 마스터 HEAD 가 움직였다: 5fc6786 → 4ac3099" in out
          and "다시 실행하라" in out and "커밋하지 말 것" in out, out[-500:])
    check("  배달 중 이동도 검사 전에 말한다", "배달 중 마스터 HEAD 가 움직였다" in out, out)
    check("  뒤처짐만인 실패는 이동 탓으로 표시한다",
          "ModularStage: check (실행 중 HEAD 이동 탓 — 출처 뒤처짐 2대)" in out, out[-300:])

    genuine = (1, {"bad": 2, "behind_only": 1})
    rc, out = _run_update_with_heads([A, B, B], {"NS": genuine, "ModularStage": behind})
    check("[주의] 다른 사유가 섞인 실패는 진짜 실패 그대로 둔다",
          "NS: check," in out and "NS: check (" not in out
          and "ModularStage: check (실행 중 HEAD 이동 탓" in out, out[-300:])

    unknown = (1, {})
    rc, out = _run_update_with_heads([A, B, B], {"NS": unknown})
    check("  내역을 모르는 실패도 이동 탓으로 접지 않는다",
          "NS: check\n" in out and rc == 1, out[-300:])

    rc, out = _run_update_with_heads([A, A, B], {"NS": ok})
    check("[중요] 검사 뒤 이동이어도 rc 1 — 배달물이 새 HEAD 와 다를 수 있다",
          rc == 1 and "5fc6786 → 4ac3099" in out
          and "검사는 통과했으나 HEAD 가 움직였다" in out, out[-300:])

    rc, out = _run_update_with_heads([""], {"NS": ok})
    check("HEAD 를 못 읽으면 감지 불가를 말하고 판정은 종전대로",
          rc == 0 and "감지할 수 없다" in out, out[:200])


def test_update_reports_dirty_tree() -> None:
    """🔴 `#737` (사용자 승인 2026-10-05) — 작업 트리 dirty 도 HEAD 이동과 같은 방식으로 말한다.

    실측 2026-10-05: HEAD 그대로 · 실행 중 `commit_flow.py` 무커밋 수정 → 이후 도장 전부 dirty,
    검사 11/15 FAIL + 서비스 신선도 실패 — 실행 중에는 아무 말도 없었다.
    """
    import time
    A, B = "90ab208" + "0" * 33, "f5d7f77" + "0" * 33
    ok = (0, {"bad": 0, "behind_only": 0, "dirty_only": 0, "behind_dirty": 0, "fresh_bad": 0})
    dirty2 = (1, {"bad": 2, "behind_only": 0, "dirty_only": 2, "behind_dirty": 0, "fresh_bad": 0})

    rc, out = _run_update_with_heads([A], {"NS": ok}, dirties=[False])
    check("깨끗한 트리 + 통과 → 성공, dirty 문구 없음",
          rc == 0 and "dirty 해졌다" not in out and "마스터 트리가 dirty 다" not in out, out)

    rc, out = _run_update_with_heads([A], {"NS": ok, "MS": dirty2}, dirties=[True])
    head = out.split("══", 1)[0]
    check("[중요] 시작부터 dirty → 배달 **전에** 크게 경고한다",
          "[중요] 마스터 트리가 dirty 다 — 배달 도장이 「추적 불가」로 찍힌다, 커밋 후 실행하라" in head,
          head)
    check("  그래도 계속한다(도장은 배달을 막지 않는다) — 두 프로젝트 모두 처리",
          "NS: 배달 결과 검사" in out and "MS: 배달 결과 검사" in out, out)
    check("  dirty 도장만인 실패는 「시작부터 트리 dirty 탓」으로 표기",
          "MS: check (시작부터 트리 dirty 탓 — dirty 도장 2대)" in out and rc == 1, out[-400:])
    check("  끝에 한 번 더 말한다", "[주의] 시작부터 마스터 트리가 dirty 였다" in out, out[-400:])
    check("  「실행 중 dirty 해졌다」와는 섞지 않는다", "dirty 해졌다" not in out, out)

    rc, out = _run_update_with_heads([A], {"NS": ok}, dirties=[False, True, True])
    check("[중요] 실행 중 dirty 해짐 → 검사가 통과해도 rc 1",
          rc == 1 and "검사는 통과했으나 트리가 dirty 해졌다" in out, out[-300:])
    check("  배달 중 dirty 를 검사 전에 말한다",
          "[중요] 배달 중 마스터 트리가 dirty 해졌다" in out.split("NS: 배달 결과 검사")[0], out)
    check("  별도 줄 「실행 중 마스터 트리가 dirty 해졌다 … 다시 실행하라」 + 읽기 순서",
          "[중요] 실행 중 마스터 트리가 dirty 해졌다 (깨끗 → dirty → dirty)" in out
          and "다시 실행하라" in out, out[-500:])

    now = int(time.time())
    measured = (1, {"bad": 3, "behind_only": 0, "dirty_only": 2, "behind_dirty": 0,
                    "fresh_bad": 1, "fresh_changed_at": now + 3600})
    rc, out = _run_update_with_heads([A], {"MS": measured}, dirties=[False, True, True])
    check("[중요] 실측 모양 — dirty 도장 + 실행 중 파일 변경의 신선도 실패를 함께 그 탓으로",
          "MS: check (실행 중 트리 dirty 탓 — dirty 도장 2대 · 서비스 신선도(실행 중 파일 변경 — 재기동 필요))"
          in out and rc == 1, out[-400:])

    old_fresh = (1, {"bad": 3, "behind_only": 0, "dirty_only": 2, "behind_dirty": 0,
                     "fresh_bad": 1, "fresh_changed_at": now - 3600})
    rc, out = _run_update_with_heads([A], {"MS": old_fresh}, dirties=[False, True, True])
    check("[주의] 실행 **전** 변경으로 생긴 신선도 실패는 진짜 실패 — 종전 표기",
          "MS: check\n" in out, out[-300:])
    unknown_fresh = (1, {"bad": 3, "behind_only": 0, "dirty_only": 2, "behind_dirty": 0,
                         "fresh_bad": 1, "fresh_changed_at": None})
    rc, out = _run_update_with_heads([A], {"MS": unknown_fresh}, dirties=[False, True, True])
    check("  신선도를 판정 못 했으면(사유 섞임) 접지 않는다", "MS: check\n" in out, out[-300:])

    genuine = (1, {"bad": 3, "behind_only": 0, "dirty_only": 2, "behind_dirty": 0, "fresh_bad": 0})
    rc, out = _run_update_with_heads([A], {"MS": genuine}, dirties=[False, True, True])
    check("  다른 사유가 섞인 실패는 종전 표기", "MS: check\n" in out and rc == 1, out[-300:])

    rc, out = _run_update_with_heads([A], {"MS": dirty2}, dirties=[False])
    check("  dirty 변화가 없는데 dirty 도장이면 이 실행 탓으로 접지 않는다",
          "MS: check\n" in out, out[-300:])

    both = (1, {"bad": 2, "behind_only": 1, "dirty_only": 0, "behind_dirty": 1, "fresh_bad": 0})
    rc, out = _run_update_with_heads([A, B, B], {"MS": both}, dirties=[False, True, True])
    check("  커밋+dirty 가 함께면 두 원인을 같이 적는다",
          "MS: check (실행 중 HEAD 이동 · 실행 중 트리 dirty 탓 — 출처 뒤처짐 1대 · 뒤처짐+dirty 도장 1대)"
          in out, out[-400:])

    rc, out = _run_update_with_heads([A], {"NS": ok}, dirties=[None])
    check("dirty 를 못 읽으면 감지 불가를 말하고 판정은 종전대로",
          rc == 0 and "dirty 여부를 읽지 못했다" in out, out[:300])

    rc, out = _run_update_with_heads([A], {"NS": ok}, dirties=[])
    check("빈 dirty 입력은 미상으로 경고하며 정상 검사 판정 유지",
          rc == 0 and "dirty 여부를 읽지 못했다" in out, out[:300])
    rc, out = _run_update_with_heads([A], {"MS": dirty2}, dirties=[])
    check("빈 dirty 입력도 검사 실패는 rc 1로 유지",
          rc == 1 and "dirty 여부를 읽지 못했다" in out and "MS: check\n" in out, out)

    check("_version_failure_kind — 사유 모양",
          [client_cli._version_failure_kind(v) for v in (
              {"ok": True, "behind": 0}, {"ok": False, "behind": 2, "stamp_dirty": False},
              {"ok": False, "behind": 0, "stamp_dirty": True},
              {"ok": False, "behind": 1, "stamp_dirty": True},
              {"ok": False, "behind": 2, "stamp_dirty": None},
              {"ok": False, "behind": None, "stamp_dirty": True},
              {"ok": False, "behind": None, "stamp_dirty": None})]
          == ["", "behind", "dirty", "behind_dirty", "", "", ""])

    kind = client_cli._version_failure_kind({"ok": False, "behind": 2, "stamp_dirty": None})
    unclassified = (1, {"bad": 1, "behind_only": int(kind == "behind"),
                        "dirty_only": int(kind == "dirty"),
                        "behind_dirty": int(kind == "behind_dirty"), "fresh_bad": 0})
    rc, out = _run_update_with_heads([A, B, B], {"MS": unclassified})
    check("[주의] dirty 미상의 뒤처짐은 HEAD 이동 중에도 종전 check 실패로 둔다",
          rc == 1 and "MS: check\n" in out and "MS: check (" not in out, out[-400:])


def test_update_head_round_trip_is_reported() -> None:
    """`#737` R42-1 — A→B→A 이면 끝 HEAD 가 시작과 같아도 관측된 이동을 그대로 말한다."""
    A, B = "5fc6786" + "0" * 33, "4ac3099" + "0" * 33
    ok = (0, {"bad": 0, "behind_only": 0})
    rc, out = _run_update_with_heads([A, B, A], {"NS": ok})
    check("[중요] A→B→A 를 그대로 보고한다",
          "실행 중 마스터 HEAD 가 움직였다: 5fc6786 → 4ac3099 → 5fc6786" in out, out[-500:])
    check("  끝이 시작과 같다는 주의를 덧붙인다", "끝 HEAD 는 시작과 같지만 중간에 달랐다" in out, out)
    check("  rc 1", rc == 1, str(rc))
    check("_head_trail — 연속 중복만 접고 빈 읽기는 뺀다",
          client_cli._head_trail([A, "", A, B]) == "5fc6786 → 4ac3099"
          and client_cli._head_trail([A, A, A]) == "5fc6786", client_cli._head_trail([A, "", A, B]))


def _live_update_in_temp_repo(mutate):
    """`#737` 실물 모양 하네스 — **진짜 `cmd_update` 흐름**을 임시 git 저장소에 돌린다.

    실저장소·워커·SSH 를 건드리지 않는다. 바꾸는 것은 뿌리(`version.REPO_ROOT`) 하나와
    배달/검사의 원격 부분뿐이다:
      · HEAD·dirty 리더 — 실제 `_master_head`/`_master_dirty` 가 임시 저장소를 읽는다
      · 배달 — 실제 `bundle._delivery_stamp()` 로 도장을 찍어 둔다(원격 쓰기 없음)
      · 검사 — 실제 `bundle.compare_version` + `_version_failure_kind` 로 판정, 신선도는
              `service_freshness` 와 같은 규칙(`newest > started`)을 임시 저장소 파일 mtime 에 댄다
    ``mutate(repo, project, phase)`` 가 배달·검사 도중 임시 저장소에 실제 커밋·수정을 한다.
    """
    import contextlib
    import io
    import shutil
    import subprocess
    import tempfile
    import time
    from types import SimpleNamespace
    from master import version as V

    tmp = Path(tempfile.mkdtemp(prefix="ax737-"))
    git = ["git", "-C", str(tmp), "-c", "user.name=t", "-c", "user.email=t@t", "-c",
           "commit.gpgsign=false"]

    def g(*a):
        return subprocess.run([*git, *a], capture_output=True, text=True, check=True).stdout.strip()

    code = tmp / "master" / "webui" / "commit_flow.py"
    code.parent.mkdir(parents=True)
    code.write_text("X = 1\n", encoding="utf-8")
    g("init", "-q")
    g("add", "-A")
    g("commit", "-q", "-m", "init")
    past = int(time.time()) - 100
    os.utime(code, (past, past))
    service_started = past + 50          # 서비스는 그 파일 뒤, update 전에 떴다

    names = ["P1", "P2", "P3"]
    stamps: dict = {}

    class AllProjects:
        @staticmethod
        def check():
            return []
    AllProjects.names = names

    class FakeRegistry:
        @staticmethod
        def load():
            return AllProjects()

    def fake_deliver(project, *, init=False, only=""):
        mutate(tmp, g, project, "deliver")
        stamps[project] = bundle._delivery_stamp()
        print(f"  배달 도장 {stamps[project].get('commit_short')} dirty={stamps[project].get('dirty')}")
        return 0

    def fake_check(project, *, only="", stats=None):
        mutate(tmp, g, project, "check")
        ver = bundle.compare_version(SimpleNamespace(project=project),
                                     runner=lambda c, h: subprocess.run(
                                         [*git, "merge-base", "--is-ancestor", c, h]).returncode == 0)
        kind = client_cli._version_failure_kind(ver)
        print(f"  {'OK' if ver['ok'] else 'FAIL'} {project}-host: 출처 {ver['reason']}")
        newest = int(code.stat().st_mtime)
        fresh = 1 if newest > service_started else 0
        if stats is not None:
            stats.update(bad=(0 if ver["ok"] else 1) + fresh, behind_only=int(kind == "behind"),
                         dirty_only=int(kind == "dirty"), behind_dirty=int(kind == "behind_dirty"),
                         fresh_bad=fresh, fresh_changed_at=newest if fresh else None)
        return 0 if ver["ok"] and not fresh else 1

    saved = (V.REPO_ROOT, bundle.Registry, bundle.delivered_stamp, bundle._run_local,
             client_cli.cmd_deliver, client_cli.cmd_check)
    V.REPO_ROOT = tmp
    bundle.Registry = FakeRegistry
    bundle.delivered_stamp = lambda f: stamps[f.project]
    bundle._run_local = lambda *a: subprocess.run([*git, *a], capture_output=True,
                                                  text=True).stdout.strip()
    client_cli.cmd_deliver, client_cli.cmd_check = fake_deliver, fake_check
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = client_cli.cmd_update(all_projects=True)
    finally:
        (V.REPO_ROOT, bundle.Registry, bundle.delivered_stamp, bundle._run_local,
         client_cli.cmd_deliver, client_cli.cmd_check) = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return rc, out.getvalue()


def test_update_live_shaped_in_temp_repo() -> None:
    """🔴 `#737` — 가짜 리더가 아니라 **실제 git 상태 변화**로 이동·dirty 경로를 돌린다."""
    def nothing(repo, g, project, phase):
        pass

    rc, out = _live_update_in_temp_repo(nothing)
    check("[실물] 정상 — rc 0 · [완료] · 이동/dirty 문구 없음",
          rc == 0 and "[완료]" in out and "움직였다" not in out and "dirty 해졌다" not in out, out)
    check("  시작 줄이 임시 저장소 HEAD·깨끗을 말한다",
          "[update] 시작 마스터 HEAD" in out and "시작 마스터 트리 깨끗" in out, out[:300])

    def commit_mid(repo, g, project, phase):
        if (project, phase) == ("P2", "deliver"):
            (repo / "doc.md").write_text("handoff\n", encoding="utf-8")
            g("add", "-A")
            g("commit", "-q", "-m", "doc")

    rc, out = _live_update_in_temp_repo(commit_mid)
    check("[실물] 배달 중 실제 커밋 → rc 1 · 이동 보고",
          rc == 1 and "배달 중 마스터 HEAD 가 움직였다" in out
          and "실행 중 마스터 HEAD 가 움직였다" in out, out[-600:])
    check("  P1 만 실제로 1 커밋 뒤 — 이동 탓으로 표기",
          "P1: check (실행 중 HEAD 이동 탓 — 출처 뒤처짐 1대)" in out
          and "HEAD 보다 1 커밋 뒤" in out and "P2: check" not in out, out[-600:])

    def edit_mid(repo, g, project, phase):
        if (project, phase) == ("P2", "deliver"):
            f = repo / "master" / "webui" / "commit_flow.py"
            f.write_text("X = 2\n", encoding="utf-8")

    rc, out = _live_update_in_temp_repo(edit_mid)
    check("[실물] 배달 중 실제 무커밋 수정 → rc 1 · 별도 줄",
          rc == 1 and "[중요] 배달 중 마스터 트리가 dirty 해졌다" in out
          and "[중요] 실행 중 마스터 트리가 dirty 해졌다 (깨끗 → dirty → dirty)" in out, out[-700:])
    check("  P2·P3 는 실제 dirty 도장 — 신선도 실패까지 실행 중 dirty 탓으로",
          "P2: check (실행 중 트리 dirty 탓 — dirty 도장 1대 · 서비스 신선도(실행 중 파일 변경 — 재기동 필요))"
          in out and "P3: check (실행 중 트리 dirty 탓" in out
          and "배달 시점 트리가 dirty 였다" in out, out[-900:])
    check("  P1 은 도장이 깨끗해 출처는 통과 — 신선도만 실패해도 실행 중 변경 탓",
          "OK P1-host: 출처 마스터 HEAD 와 같다" in out
          and "P1: check (실행 중 파일 변경 탓 — 서비스 신선도(실행 중 파일 변경 — 재기동 필요))" in out,
          out[-900:])
    check("  HEAD 는 그대로라 이동 문구가 없다", "HEAD 가 움직였다" not in out, out)

    rc, out = _live_update_with_dirty_start()
    check("[실물] 시작부터 dirty → 첫 배달 전에 경고하고 계속 진행",
          "[중요] 마스터 트리가 dirty 다 — 배달 도장이 「추적 불가」로 찍힌다, 커밋 후 실행하라"
          in out.split("══", 1)[0] and "P3: 배달 결과 검사" in out, out[:600])
    check("  dirty 도장 실패는 「시작부터 트리 dirty 탓」 · 「실행 중 dirty 해졌다」 문구 없음",
          "P1: check (시작부터 트리 dirty 탓 — dirty 도장 1대)" in out
          and "dirty 해졌다" not in out and rc == 1, out[-600:])

    def round_trip(repo, g, project, phase):
        if (project, phase) == ("P3", "deliver"):
            (repo / "doc.md").write_text("b\n", encoding="utf-8")
            g("add", "-A")
            g("commit", "-q", "-m", "B")
        if (project, phase) == ("P3", "check"):
            g("reset", "-q", "--hard", "HEAD~1")

    rc, out = _live_update_in_temp_repo(round_trip)
    trail = [ln for ln in out.splitlines() if "실행 중 마스터 HEAD 가 움직였다" in ln]
    hs = trail[0].split(": ", 1)[1].split(" — ")[0].split(" → ") if trail else []
    check("[실물] R42-1 — 실제 commit 후 reset(A→B→A)을 A → B → A 로 보고",
          len(hs) == 3 and hs[0] == hs[2] != hs[1] and rc == 1
          and "끝 HEAD 는 시작과 같지만 중간에 달랐다" in out, out[-600:])


def _live_update_with_dirty_start():
    """시작부터 dirty — 첫 dirty 읽기 직전에 임시 저장소에 실제 미추적 파일을 만든다.

    판정은 실제 `_master_dirty`(= `version.identity()["dirty"]`)가 한다. 서비스 코드가 아닌
    파일이라 신선도 실패는 생기지 않는다(시작 전 변경은 이 실행 탓이 아니다).
    """
    from master import version as V
    real_dirty = client_cli._master_dirty
    state = {"done": False}

    def dirty_then_read():
        if not state["done"]:
            (Path(V.REPO_ROOT) / "notes.txt").write_text("wip\n", encoding="utf-8")
            state["done"] = True
        return real_dirty()

    client_cli._master_dirty = dirty_then_read
    try:
        return _live_update_in_temp_repo(lambda repo, g, project, phase: None)
    finally:
        client_cli._master_dirty = real_dirty


def test_index_only_delivery() -> None:
    """🔴 색인 전용 배달 (`#693`) — **커밋된 사람 파일을 쓰지 않는다.**

    kimodo 레포는 `CLAUDE.md`·`AGENTS.md`·`.mcp.json` 을 커밋해 두고 쓴다. 배달이 그 셋을 쓰면
    사람의 작업 트리가 더러워진다(사용자 확정 2026-09-28: MCP 는 로컬 스코프, 블록은
    `.claude/CLAUDE.md` 에만).
    """
    idx = spec.ProjectInit(index_only=True)
    ws = [r for r, _ in bundle.workshop_files("requester", "", idx)]
    check("작업장 자산은 검색 힌트 훅 둘뿐", set(ws) <= set(spec.INDEX_ONLY_WORKSHOP) and ws, str(ws))
    check("  기본(unreal)은 그대로 전부", len(bundle.workshop_files("requester")) > len(ws))
    md = bundle.merge_workshop_md("", "requester", "", idx)
    check("[중요] `.claude/CLAUDE.md` 는 색인 전용 정본", "색인 전용" in md and bundle.WS_BEGIN in md, md[:80])
    check("  분산 작업 안내가 섞이지 않는다", "register_work" not in md or "거절" in md)
    f = _facts(role="requester", os="windows", path=r"C:\Users\USER\Documents\K", home=r"C:\Users\USER",
               python=r"C:\Py\python.exe")
    import json
    hooks = json.loads(bundle.merge_settings_json("", f, idx)).get("hooks") or {}
    rels = [h["hooks"][0]["command"] for evs in hooks.values() for h in evs]
    check("[중요] 등록되는 훅은 배달되는 스크립트뿐 (없는 훅이 프롬프트를 막는다)",
          rels and all("domain_hint" in c for c in rels), str(rels))
    cmd = bundle.claude_mcp_local_cmd(f, "ax-client")
    check("로컬 스코프 명령 — 체크아웃에서 remove 뒤 add (멱등)",
          "--scope local" in cmd and cmd.index("remove") < cmd.index(" add ") and "K" in cmd, cmd)
    check("  같은 mcp_entry_for 에서 나온다", r"C:\Py\python.exe" in cmd and "client_mcp.py" in cmd, cmd)
    sent: list = []
    saved_ssh = bundle._ssh
    bundle._ssh = lambda host, user, c, timeout=None: (sent.append(c), (0, ""))[1]
    try:
        bundle.claude_mcp_local_get(f, "ax-client")
    finally:
        bundle._ssh = saved_ssh
    check("🔴 PowerShell 속성 이름을 따옴표로 감싼다 (`ax-client` 의 `-` 가 빼기로 파싱돼 죽었다)",
          "mcpServers.'ax-client'" in sent[0] and "mcpServers.ax-client " not in sent[0], sent[0][-120:])
    check("🔴 ~/.claude.json 을 UTF-8 로 읽는다 (CP949 로 읽어 한글 기록이 JSON 을 깨뜨렸다 · `.2` 실측)",
          "Get-Content -Raw -Encoding UTF8" in sent[0], sent[0][:120])
    check("  ~/.claude.json 키는 슬래시 경로 (실측)",
          bundle.claude_local_key(f) == "C:/Users/USER/Documents/K", bundle.claude_local_key(f))

    wrote: list = []
    saved = {k: getattr(bundle, k) for k in ("_remote_write", "_remote_read", "config_for",
             "_register_residency", "_ensure_ignored", "claude_mcp_local_add",
             "codex_project_mcp_add")}
    bundle._remote_write = lambda facts, rel, content, base="home": (wrote.append(rel), f"[완료] {rel}")[1]
    bundle._remote_read = lambda facts, path: ""
    bundle.config_for = lambda project, facts: {}
    bundle._register_residency = lambda project, facts: {"registered": False}
    bundle._ensure_ignored = lambda facts: True
    bundle.claude_mcp_local_add = lambda facts, n: f"{n} [완료] local"
    bundle.codex_project_mcp_add = lambda facts, n: f"{n} [완료] codex"
    try:
        got = bundle.deliver("K", f, project_init=idx)
    finally:
        for k, v in saved.items():
            setattr(bundle, k, v)
    check("🔴 루트 CLAUDE.md 를 쓰지 않는다", "CLAUDE.md" not in wrote, str(wrote))
    check("🔴 AGENTS.md 를 쓰지 않는다", spec.CODEX_ENTRY_REL not in wrote, str(wrote))
    check("🔴 .mcp.json 을 쓰지 않는다", ".mcp.json" not in wrote, str(wrote))
    check("  대신 로컬 스코프로 등록한다", "local" in str(got.get("claude_mcp_local")), str(got.get("claude_mcp_local")))
    check("  `.claude/CLAUDE.md` 블록은 쓴다", bundle.WORKSHOP_MD_REL in wrote, str(wrote))
    # 2026-10-09 `ax-gemini` 추가 (사용자 결정) — 분산 작업과 무관한 리서치 스킬이라 빈 참조가 아니다
    check("  스킬은 ax-ontology·ax-gemini 뿐", [r for r in wrote if "skills/" in r]
          and all(("ax-ontology" in r or "ax-gemini" in r) for r in wrote if "skills/" in r),
          str([r for r in wrote if "skills/" in r]))
    check("  config·토큰 자리는 그대로 (태그가 있어야 검색이 자기 프로젝트를 본다)",
          bundle.CONFIG_REL in wrote, str(wrote))


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
               test_hook_registration,
               test_codex_entry_doc,
               test_codex_mcp_registration,
               test_project_local_codex_surfaces,
               test_codex_identity,
               test_residency_reconcile_removes_forbidden_registration,
               test_check_mount_lookup_is_fail_closed,
               test_update_covers_every_registered_project,
               test_update_reports_partial_failure,
               test_update_defaults_to_mounted_project,
               test_remote_hashes_and_skip_unchanged,
               test_check_stats_counters_are_not_shadowed,
               test_ensure_ignored_is_one_call_and_strict,
               test_fetch_prune_delivery_and_check,
               test_fetch_prune_wired_into_deliver_and_check,
               test_agy_model_delivered_and_checked,
               test_claude_mcp_local_add_skips_identical,
               test_deliver_clears_hash_cache_even_on_error,
               test_deliver_cache_isolation,
               test_update_reports_head_movement,
               test_update_reports_dirty_tree,
               test_update_head_round_trip_is_reported,
               test_update_live_shaped_in_temp_repo,
               test_shadow_skills_are_reported,
               test_index_only_delivery):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_bundle: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
