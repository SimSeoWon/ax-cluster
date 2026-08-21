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
    # [중요] 워커에는 **둘** 간다 — `ax-infer`(현 토폴로지: 추론만) + `ax-work`(구 토폴로지).
    #    구 것을 지우지 않는 이유는 settled 결정이다: N-writer 기계장치는 측정으로 뒤집힐
    #    여지가 있는 동안 되돌릴 수 있게 둔다(§8.4). 파견 지시가 이름으로 고른다.
    check("워커는 ax-work + ax-infer",
          set(bundle.skills_for("worker")) == {"ax-work", "ax-infer"},
          str(bundle.skills_for("worker")))
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
    # [주의] 옛 계약("워커에는 안 간다")은 #204 로 의도 변경 — claimer 폐포가 간다.
    check("[중요] 워커에는 claimer 폐포가 간다 (#204)",
          set(bundle.payloads_for("worker")) == {
              "work/claimer.py", "work/ax_safety.py", "work/build_local.py",
              "work/skeleton_gate.py", "layer3_verify.py", "source_text.py", "utf8.py"},
          str(bundle.payloads_for("worker")))
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

    왜 이 테스트가 있나: 배달 위치는 함부로 못 바꾼다. `.33` 의 `.mcp.json` args 가 그 값이고
    (`mcp_entry_for`), `.2` schtasks·`.43` cron 이 `axmaster.work.claimer` 로 상주를 부른다
    (`work/claimer.py:27-28`). **저장소 재배치(#263·#264)가 이 목록을 흔들면 두 기계가 죽는다** —
    그때 이 테스트가 먼저 죽어야 한다.
    """
    FROZEN = {
        "requester": ("clientside/client_mcp.py", "clientside/ontology_cache.py",
                      "layer3_verify.py", "source_text.py", "utf8.py",
                      "work/branch_names.py", "work/coordinator.py", "work/review.py",
                      "work/skeleton_gate.py", "work/build_local.py"),
        "worker": ("work/claimer.py", "work/ax_safety.py", "work/build_local.py",
                   "work/skeleton_gate.py", "layer3_verify.py", "source_text.py",
                   "utf8.py"),
    }
    for role, want in FROZEN.items():
        got = bundle.payloads_for(role)
        check(f"[중요] {role} 의 **배달 위치**가 동결값과 순서까지 같다",
              got == want, f"실제={got}")
    # [중요] 상주가 부르는 경로는 이름이 박혀 있다 — 이 한 줄이 `.2`·`.43` 의 생사다
    check("[중요] claimer 의 배달 위치가 `work/claimer.py` 다 (상주가 그 경로로 부른다)",
          "work/claimer.py" in bundle.payloads_for("worker"))
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
    #    나머지는 `master/<배달경로>` 미러링이다 — 사용자 결정 ⓒ(claimer 사슬은 `master/` 에
    #    남는다, `layer3_verify` 를 상대경로로 올려다보기 때문). 의도하지 않은 갈림도 여기서 죽는다.
    SPLIT = {"clientside/client_mcp.py": "client/runtime/client_mcp.py",
             "clientside/ontology_cache.py": "client/runtime/ontology_cache.py"}
    for role in FROZEN:
        for dest, src in bundle.payload_pairs(role):
            want = SPLIT.get(dest, f"master/{dest}")
            check(f"[중요] 저장소 위치가 동결값이다: {dest} ← {src}", src == want, f"기대={want}")
    check("[중요] claimer 사슬은 master/ 에 남는다 (ⓒ) — layer3_verify 상대 임포트가 산다",
          all(src.startswith("master/work/")
              for dest, src in bundle.payload_pairs("worker") if "claimer" in dest
              or "ax_safety" in dest or "build_local" in dest or "skeleton_gate" in dest),
          str(bundle.payload_pairs("worker")))
    try:
        bundle.payload_pairs("사장님")
        check("[중요] 모르는 역할은 예외 (payload_pairs)", False, "조용히 돌려줬다")
    except bundle.BundleError:
        check("[중요] 모르는 역할은 예외 (payload_pairs)", True)


def test_role_block() -> None:
    w = bundle.managed_block("P", _facts(role="worker"))
    r = bundle.managed_block("P", _facts(role="requester"))
    check("워커 블록은 ax-work 를 가리킨다", "`ax-work`" in w)
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

    dry = bundle.deliver("P", _facts(role="requester"), dry_run=True)
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


def main() -> int:
    for fn in (test_role, test_config, test_managed_block, test_merge, test_skill_is_readable,
               test_mcp_json_merge,
               test_role_skills, test_role_payload, test_payload_split, test_role_block, test_ue5_detection, test_init_wiring, test_scp_source_windows,
               test_merge_never_replaces_existing,
               test_workshop_assets_reference_only_live_tools,
               test_workshop_delivery):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_bundle: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
