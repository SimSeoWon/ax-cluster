"""마스터 자기 호스트의 요청자 작업장 (`#798`) — 배달물은 **전부 체크아웃 안**.

마스터(.57)가 AXCluster 요청자를 겸할 때 배달이 마스터 홈(`~/.claude/skills`·`~/.codex/skills`·
`~/.claude.json`)을 쓰거나 지우면 마스터 세션의 스킬(`distribute` 등)이 사라진다. 여기서는
**SSH·scp 를 가짜로 바꿔** 실제 `_deliver` 경로를 돌리고, 원격에 나간 명령·쓰기 자리를 전수로 본다.
원격(.43 류) 요청자는 종전 동작(홈 스킬·폐지 삭제·로컬 스코프)을 그대로 유지하는지도 같이 본다.

`.venv/bin/python -B master/test_client_master_requester.py`
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
os.environ.setdefault("AX_PROJECTS_ROOT", str(_REPO))

from master.client import __main__ as client_cli, bundle, spec      # noqa: E402

PASS = FAIL = 0
HOME = "/home/sim"
CHECKOUT = "/home/sim/trunk/AXCluster-requester"
CODE = spec.ProjectInit(index_only=True, code=True)        # `load_init` 이 kind: code 에 내는 값


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _facts(host: str = bundle.MASTER_HOST, *, role: str = "requester", path: str = CHECKOUT):
    return bundle.HostFacts(host=host, user="sim", path=path, driven="ssh", role=role,
                            os="linux", home=HOME, claude="2.1.296 (Claude Code)",
                            codex="codex-cli 0.162.0", python="/usr/bin/python3",
                            checkout_ok=True, commit="7f70309")


class FakeRemote:
    """`_ssh` 와 scp(`subprocess.run`)를 대신한다. 쓰기는 메모리에, 명령은 목록에 남긴다."""

    def __init__(self, tracked: str = ""):
        self.files: dict = {}
        self.cmds: list = []
        self.writes: list = []
        self.tracked = tracked

    def ssh(self, host, user, cmd, timeout=None):
        self.cmds.append(cmd)
        if cmd.startswith("sha256sum ") and "| cut" in cmd:          # `_remote_write` 되읽기
            target = cmd.split(" ", 1)[1].split(" |", 1)[0].strip("'")
            body = self.files.get(target)
            return (0, hashlib.sha256(body.encode("utf-8")).hexdigest()) if body is not None else (1, "")
        if "git ls-files" in cmd:
            return 0, self.tracked
        if "codex mcp get" in cmd:
            e = bundle.mcp_entry_for(_facts())
            import json
            return 0, json.dumps({"transport": {"type": "stdio", "command": e["command"],
                                                "args": e["args"]}})
        if "info/exclude" in cmd:
            return 0, "\n".join(f"OK {ln}" for ln in spec.git_excludes_for("requester"))
        return 0, ""

    def run(self, args, **kw):
        src, dst = args[-2], args[-1]
        if "@" in dst and ":" in dst:                                   # 쓰기: 로컬 → 원격
            target = dst.split(":", 1)[1]
            self.files[target] = Path(src).read_text(encoding="utf-8")
            self.writes.append(target)
        else:                                                           # 읽기: 원격 → 로컬
            path = src.split(":", 1)[1]
            if path in self.files:
                Path(dst).write_text(self.files[path], encoding="utf-8")
            else:
                return subprocess.CompletedProcess(args, 1, "", "No such file or directory")
        return subprocess.CompletedProcess(args, 0, "", "")


def _run_deliver(facts, init, *, tracked: str = ""):
    fake = FakeRemote(tracked)
    saved_ssh, saved_run = bundle._ssh, subprocess.run
    saved_cfg = bundle.config_for
    bundle._ssh = fake.ssh
    subprocess.run = fake.run
    bundle.config_for = lambda project, f: {"project": project}
    try:
        try:
            got = bundle.deliver("AXCluster", facts, project_init=init)
            err = None
        except bundle.BundleError as e:
            got, err = None, e
    finally:
        bundle._ssh, subprocess.run, bundle.config_for = saved_ssh, saved_run, saved_cfg
    return fake, got, err


# ── 판정 ────────────────────────────────────────────────────────

def test_detection() -> None:
    check("마스터 주소는 마스터 호스트", _facts().on_master)
    check("loopback 도 마스터 호스트", bundle.is_master_host("localhost")
          and bundle.is_master_host("127.0.0.1"))
    for h in ("192.168.0.43", "192.168.0.33", "192.168.0.2", ""):
        check(f"{h or '(빈 값)'} 는 마스터가 아니다", not bundle.is_master_host(h))


def test_targets_and_scope() -> None:
    m, r = _facts(), _facts("192.168.0.43")
    mt = bundle.tool_skill_targets(m, "ax-request")
    check("🔴 마스터 호스트 스킬은 체크아웃 `.claude/skills`",
          mt == ((".claude/skills/ax-request/SKILL.md", "checkout"),), str(mt))
    check("  절대경로가 체크아웃 아래", bundle._write_target(m, *mt[0]).startswith(CHECKOUT + "/"))
    rt = bundle.tool_skill_targets(r, "ax-request")
    check("원격은 종전대로 홈 두 자리(.claude · .codex)",
          rt == tuple((x, "home") for x in spec.skill_rels("ax-request")), str(rt))
    check("🔴 마스터 호스트는 폐지 스킬을 지우지 않는다", bundle.removals(m, CODE)["skills"] == ())
    check("  원격 요청자는 종전대로 `distribute` 를 지운다",
          "distribute" in bundle.removals(r, CODE)["skills"], str(bundle.removals(r, CODE)))
    check("🔴 마스터 호스트 MCP 는 project 스코프(.mcp.json)", bundle.mcp_scope(m, CODE) == "project")
    check("  원격 code 는 종전대로 local", bundle.mcp_scope(r, CODE) == "local")
    check("  원격 unreal 은 종전대로 project", bundle.mcp_scope(r, spec.EMPTY_INIT) == "project")
    check("spec 의 표는 그대로 (호스트 무관 선언)", spec.mcp_scope_for(CODE) == "local"
          and "distribute" in spec.removals_for("requester", CODE)["skills"])


def test_guard() -> None:
    m = _facts()
    sent: list = []
    saved = bundle._ssh
    bundle._ssh = lambda *a, **k: (sent.append(a), (0, ""))[1]
    try:
        for rel, base in ((".claude/skills/x/SKILL.md", "home"),
                          (f"{HOME}/.codex/skills/x/SKILL.md", "abs"),
                          (f"{HOME}/.agents/skills/x/SKILL.md", "abs")):
            try:
                bundle._remote_write(m, rel, "x", base=base)
                check(f"🔴 마스터 홈 쓰기 거절 — {rel}", False, "통과해버렸다")
            except bundle.BundleError:
                check(f"마스터 홈 쓰기 거절 — {rel}", True)
        try:
            bundle._remote_rm_dir(m, ".claude/skills/distribute")
            check("🔴 마스터 홈 스킬 삭제 거절", False, "통과해버렸다")
        except bundle.BundleError:
            check("마스터 홈 스킬 삭제 거절", True)
        r = bundle.claude_mcp_local_add(m, "ax-client")
        check("🔴 마스터 호스트 로컬 스코프 등록은 건너뛴다", "건너뜀" in r and "#798" in r, r)
    finally:
        bundle._ssh = saved
    check("  거절은 SSH 를 하나도 보내기 전이다", not sent, str(sent))
    # 원격 기계의 홈 쓰기는 가드가 막지 않는다
    try:
        bundle._guard_master_home(_facts("192.168.0.43"), f"{HOME}/.claude/skills/x/SKILL.md", "home")
        check("원격 홈 쓰기는 가드 통과", True)
    except bundle.BundleError as e:
        check("원격 홈 쓰기는 가드 통과", False, str(e))
    # 체크아웃 안의 `.claude/skills` 는 마스터에서도 허용
    try:
        bundle._guard_master_home(m, f"{CHECKOUT}/.claude/skills/x/SKILL.md", "checkout")
        check("마스터 체크아웃 안은 통과", True)
    except bundle.BundleError as e:
        check("마스터 체크아웃 안은 통과", False, str(e))


def test_deliver_master_requester() -> None:
    fake, got, err = _run_deliver(_facts(), CODE)
    check("배달이 끝까지 돈다", err is None and got is not None, str(err))
    if got is None:
        return
    outside = [t for t in fake.writes if not t.startswith(CHECKOUT + "/")]
    check("🔴 쓰기는 전부 체크아웃 안", not outside and fake.writes, str(outside))
    for root in (".claude/skills", ".codex/skills", ".agents/skills", ".claude.json", ".codex/config"):
        hit = [t for t in fake.writes if t.startswith(f"{HOME}/{root}")]
        check(f"🔴 홈 {root} 에 쓰지 않는다", not hit, str(hit))
    bad = [c for c in fake.cmds if any(k in c for k in ("rm -rf", "claude mcp", "codex mcp add", "crontab"))]
    check("🔴 홈 삭제·MCP 전역 등록·crontab 명령이 없다", not bad, str(bad))
    check("  폐지 삭제 결과가 비어 있다", got.get("removed") == [] and got.get("removed_codex") == [],
          f"{got.get('removed')} {got.get('removed_codex')}")
    names = spec.skills_for("requester", CODE)
    for n in names:
        check(f"  {n} → 체크아웃 .claude/skills", f"{CHECKOUT}/.claude/skills/{n}/SKILL.md" in fake.writes)
        check(f"  {n} → 체크아웃 .agents/skills", f"{CHECKOUT}/.agents/skills/{n}/SKILL.md" in fake.writes)
    for rel in (".mcp.json", ".codex/config.toml", ".claude/settings.json", bundle.CONFIG_REL):
        check(f"  {rel} 는 체크아웃에 쓴다", f"{CHECKOUT}/{rel}" in fake.writes, str(fake.writes[-8:]))
    check("  루트 CLAUDE.md·AGENTS.md 는 code 규약대로 안 쓴다 (#695)",
          f"{CHECKOUT}/CLAUDE.md" not in fake.writes and f"{CHECKOUT}/AGENTS.md" not in fake.writes)
    check("  상주는 부르지 않는다", "#798" in str(got.get("residency")), str(got.get("residency")))
    import json
    mcp = json.loads(fake.files[f"{CHECKOUT}/.mcp.json"])["mcpServers"]["ax-client"]
    check("  .mcp.json 항목은 mcp_entry_for 와 같다", mcp == bundle.mcp_entry_for(_facts()), str(mcp))


def test_deliver_refuses_tracked_mcp_json() -> None:
    fake, got, err = _run_deliver(_facts(), CODE, tracked=".mcp.json\n")
    check("🔴 `.mcp.json` 추적 중이면 거절한다", err is not None and "#798" in str(err), str(err))
    check("  거절은 어떤 쓰기보다 먼저다", not fake.writes, str(fake.writes))


def test_dry_run_master_requester() -> None:
    d = bundle.deliver("AXCluster", _facts(), dry_run=True, project_init=CODE)
    check("dry_run: 폐지 없음", d["removed"] == [], str(d["removed"]))
    check("dry_run: project 스코프", d["mcp_scope"] == "project")
    check("dry_run: 스킬 자리는 전부 체크아웃 안",
          d["skill_targets"] and all(t.startswith(CHECKOUT + "/") for t in d["skill_targets"]),
          str(d["skill_targets"]))


def test_remote_requester_unchanged() -> None:
    """원격 요청자는 종전 동작 그대로 — 홈 스킬 · 폐지 삭제 · 로컬 스코프 등록."""
    r = _facts("192.168.0.43", path="/home/sim/trunk/X")
    fake, got, err = _run_deliver(r, CODE)
    check("원격 배달이 끝까지 돈다", err is None, str(err))
    if got is None:
        return
    check("원격: 홈 `.claude/skills` 에 쓴다",
          f"{HOME}/.claude/skills/ax-request/SKILL.md" in fake.writes, str(fake.writes[:6]))
    check("원격: 홈 `.codex/skills` 에 쓴다",
          f"{HOME}/.codex/skills/ax-request/SKILL.md" in fake.writes)
    check("원격: 폐지 스킬을 지운다", any("rm -rf" in c and "distribute" in c for c in fake.cmds))
    check("원격: 로컬 스코프로 등록한다", any("claude mcp add --scope local" in c for c in fake.cmds))
    check("원격: .mcp.json 은 안 쓴다 (code 규약)", "/home/sim/trunk/X/.mcp.json" not in fake.writes)


def test_plan_master_requester() -> None:
    """`plan` 출력에 홈 쓰기·폐지 삭제·로컬 스코프 명령이 나오지 않는다."""
    saved = (client_cli._facts, bundle.compare_tag, bundle.tracked_managed, spec.load_init)
    client_cli._facts = lambda project, only="": [_facts()]
    bundle.compare_tag = lambda f, p: {"ok": False, "stored": "", "reason": "없음"}
    bundle.tracked_managed = lambda f: ("CLAUDE.md", "AGENTS.md")
    spec.load_init = lambda project="", registry=None: CODE
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = client_cli.cmd_plan("AXCluster")
    finally:
        client_cli._facts, bundle.compare_tag, bundle.tracked_managed, spec.load_init = saved
    out = buf.getvalue()
    check("plan rc=0", rc == 0, out[-300:])
    check("🔴 plan 에 홈 스킬 자리가 없다",
          f"{HOME}/.claude/skills" not in out and f"{HOME}/.codex/skills" not in out, out)
    check("🔴 plan 에 폐지 삭제가 없다", "✕ 폐지 스킬" not in out, out)
    check("🔴 plan 에 로컬 스코프·전역 codex 등록이 없다",
          "claude mcp add" not in out and "codex mcp add" not in out, out)
    check("  plan 이 체크아웃 스킬 자리를 찍는다", f"{CHECKOUT}/.claude/skills/ax-request/SKILL.md" in out)
    check("  plan 이 `.codex/config.toml` 을 찍는다", f"{CHECKOUT}/.codex/config.toml" in out)


def test_probe_finds_user_bin_codex() -> None:
    """`#798` — 리눅스 probe 는 `~/.local/bin` 을 PATH 앞에 둔다 (마스터 SSH PATH 에 없다)."""
    sent: list = []
    saved = bundle._ssh
    bundle._ssh = lambda host, user, cmd, timeout=None: (sent.append(cmd), (0, "Linux"))[1]
    try:
        bundle.probe(bundle.MASTER_HOST, "sim", CHECKOUT, "ssh", "requester")
    finally:
        bundle._ssh = saved
    cx = [c for c in sent if "codex --version" in c]
    check("codex 버전 프로브가 `~/.local/bin` 을 본다", cx and bundle.LINUX_USER_BIN in cx[0], str(cx))
    sent.clear()
    bundle._ssh = lambda host, user, cmd, timeout=None: (sent.append(cmd), (0, "{}"))[1]
    try:
        bundle.codex_mcp_get(_facts(), "ax-client", project=True)
    finally:
        bundle._ssh = saved
    check("codex mcp get 도 같은 PATH", bundle.LINUX_USER_BIN in sent[0], sent[0])


def test_codex_master_global_entry() -> None:
    """실측 2026-10-11: 마스터 클론에서 codex 는 전역 `master-local` 항목을 본다 — 그것이 정본이다."""
    from master.client import master_local as ml
    e = ml.entry_for(ml.Paths.default())
    glob = {"transport": {"type": "stdio", "command": e["command"], "args": list(e["args"])},
            "enabled": True}
    other = {"transport": {"type": "stdio", "command": "/usr/bin/python3", "args": ["x.py"]}}
    check("🔴 마스터 호스트: 전역 master-local 항목은 맞는 답", bundle.codex_master_global_ok(glob, _facts()))
    check("  마스터 호스트: 엉뚱한 항목은 아니다", not bundle.codex_master_global_ok(other, _facts()))
    check("  빈 항목은 아니다", not bundle.codex_master_global_ok({}, _facts()))
    check("🔴 원격 요청자는 전역 항목을 인정하지 않는다(판정 불변)",
          not bundle.codex_master_global_ok(glob, _facts("192.168.0.33")))
    check("  원격 워커도 마찬가지", not bundle.codex_master_global_ok(glob, _facts("192.168.0.43", role="worker")))


def main() -> int:
    for fn in (test_detection, test_targets_and_scope, test_guard, test_deliver_master_requester,
               test_deliver_refuses_tracked_mcp_json, test_dry_run_master_requester,
               test_remote_requester_unchanged, test_plan_master_requester,
               test_probe_finds_user_bin_codex, test_codex_master_global_entry):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_master_requester: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
