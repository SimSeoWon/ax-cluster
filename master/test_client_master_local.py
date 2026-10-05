"""마스터 로컬 `ax-client` 설치기 — 생성·병합·대조 (master/client/master_local.py).

**집(~)에 쓰지 않는다.** 전부 임시 디렉토리와 순수 함수다. 지키는 계약:
세 CLI 가 같은 기동 형태를 받는가 · 사람이 쓴 설정을 보존하는가 · 손으로 만든 항목을 걷는가 ·
깨진 파일을 덮지 않는가 · 토큰 값이 출력에 새지 않는가.

`.venv/bin/python master/test_client_master_local.py`
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
os.environ.setdefault("AX_PROJECTS_ROOT", str(_REPO))          # test_client_bundle.py 와 같은 이유

from master.client import __main__ as client_cli, bundle         # noqa: E402
from master.client import master_local as ml                      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _paths(tmp: Path) -> ml.Paths:
    h = tmp / "home"
    return ml.Paths(home=h, root=h / ".local/share/ax-client", token_src=tmp / "src-token",
                    python=Path("/opt/py/bin/python"), script=Path("/opt/repo/client_mcp.py"),
                    claude_json=h / ".claude.json", codex_toml=h / ".codex/config.toml",
                    agy_json=h / ".gemini/config/mcp_config.json", legacy_root=h / ".codex/ax-client")


HAND_MADE = '''model = "gpt-5"

[projects."/home/sim"]
trust_level = "trusted"

[mcp_servers.ax-projects]
url = "http://192.168.0.57:8103/mcp"

[mcp_servers.ax-projects.tools.list_projects_tool]
approval_mode = "approve"

# Existing ax-client stdio server; master connection settings only, no wrapper.
[mcp_servers.ax-client]
command = "/home/sim/ax-cluster/.venv/bin/python"
args = ["/home/sim/ax-cluster/client/runtime/client_mcp.py"]
cwd = "/home/sim/.codex/ax-client"
enabled_tools = ["redmine_list_issues"]

[mcp_servers.ax-client.tools.redmine_get_issue]
approval_mode = "approve"
'''


def test_entry_is_one_shape() -> None:
    p = _paths(Path("/t"))
    e = ml.entry_for(p)
    check("기동은 env -C <루트>", e["command"] == "/usr/bin/env" and e["args"][:2] == ["-C", str(p.root)])
    check("그다음 python·스크립트 절대경로", e["args"][2:] == [str(p.python), str(p.script)])
    claude_entry = {"type": "stdio", **e}
    check("claude 항목 비교", ml.stdio_matches(claude_entry, e))
    check("agy 항목 비교(type 없음)", ml.stdio_matches(dict(e), e))
    check("다른 루트는 불일치", not ml.stdio_matches({**e, "args": ["-C", "/x", *e["args"][2:]]}, e))
    check("빈 항목은 불일치", not ml.stdio_matches({}, e))


def test_redmine_tools() -> None:
    names = ("search_context", "redmine_note", "redmine_list_issues", "redmine_get_issue",
             "redmine_meta", "redmine_link_commit")
    got = ml.redmine_tools(names)
    check("redmine_ 접두만", got == ("redmine_note", "redmine_list_issues", "redmine_get_issue",
                                    "redmine_meta", "redmine_link_commit"), str(got))
    try:
        ml.redmine_tools(("redmine_note",))
        check("READ_APPROVE 누락은 예외", False)
    except ml.MasterLocalError:
        check("READ_APPROVE 누락은 예외", True)
    real = ml.redmine_tools()                                       # 실제 client_mcp.TOOLS
    for n in ("redmine_list_issues", "redmine_get_issue", "redmine_meta", "redmine_create_issue",
              "redmine_note", "redmine_create_version", "redmine_update_version",
              "redmine_delete_version", "redmine_link_commit"):
        check(f"실제 TOOLS 에 {n}", n in real)


def test_codex_text_replaces_hand_made() -> None:
    p = _paths(Path("/t"))
    e = ml.entry_for(p)
    new, removed = ml.codex_text(HAND_MADE, e, ml.READ_APPROVE)
    import tomli
    d = tomli.loads(new)
    ax = d["mcp_servers"]["ax-client"]
    check("command/args 가 공용 형태", ax["command"] == e["command"] and ax["args"] == e["args"])
    check("cwd 제거", "cwd" not in ax)
    check("enabled_tools 제거", "enabled_tools" not in ax)
    check("읽기 셋만 approve", ml.codex_approvals(new) == tuple(sorted(ml.READ_APPROVE)),
          str(ml.codex_approvals(new)))
    check("다른 서버 보존", d["mcp_servers"]["ax-projects"]["url"].endswith("/mcp")
          and d["mcp_servers"]["ax-projects"]["tools"]["list_projects_tool"]["approval_mode"] == "approve")
    check("최상위·projects 보존", d["model"] == "gpt-5" and d["projects"]["/home/sim"]["trust_level"] == "trusted")
    check("옛 설명 주석 제거", "Existing ax-client stdio server" not in new)
    check("걷은 것 보고", any("손으로 만든" in r for r in removed), str(removed))
    again, removed2 = ml.codex_text(new, e, ml.READ_APPROVE)
    check("멱등 — 두 번째는 같은 본문", again == new)
    check("두 번째는 관리 블록만 걷음", removed2 == ["관리 블록(이전 master-local 출력)"], str(removed2))
    first, _ = ml.codex_text("", e, ml.READ_APPROVE)
    check("빈 파일에서도 생성", ml.CODEX_BEGIN in first and tomli.loads(first)["mcp_servers"]["ax-client"])


def test_codex_text_refuses() -> None:
    e = ml.entry_for(_paths(Path("/t")))
    for name, text in (("깨진 TOML", "[a\nb = "),
                       ("인라인 정의", '[mcp_servers]\n"ax-client" = { command = "x" }\n')):
        try:
            ml.codex_text(text, e, ml.READ_APPROVE)
            check(f"{name} 은 거절", False)
        except ml.MasterLocalError:
            check(f"{name} 은 거절", True)


def test_codex_get_matches() -> None:
    e = ml.entry_for(_paths(Path("/t")))
    good = {"name": "ax-client", "enabled": True,
            "transport": {"type": "stdio", "command": e["command"], "args": e["args"], "cwd": None},
            "enabled_tools": None}
    check("정상", ml.codex_get_matches(good, e)[0])
    check("cwd 남음은 실패", not ml.codex_get_matches(
        {**good, "transport": {**good["transport"], "cwd": "/x"}}, e)[0])
    check("enabled_tools 남음은 실패", not ml.codex_get_matches({**good, "enabled_tools": ["a"]}, e)[0])
    check("없음은 실패", not ml.codex_get_matches({}, e)[0])


def test_agy_text() -> None:
    e = ml.entry_for(_paths(Path("/t")))
    new = ml.agy_text("", e)
    check("0바이트에서 생성", ml.stdio_matches(ml.agy_get(new), e))
    other = json.dumps({"mcpServers": {"sqlite": {"command": "s"}}, "x": 1})
    merged = json.loads(ml.agy_text(other, e))
    check("다른 서버·키 보존", merged["mcpServers"]["sqlite"] == {"command": "s"} and merged["x"] == 1)
    check("cwd·env 키를 만들지 않는다(스키마 밖)", set(merged["mcpServers"]["ax-client"]) == {"command", "args"})
    for bad in ("{not json", "[1]"):
        try:
            ml.agy_text(bad, e)
            check(f"깨진 파일 거절 {bad!r}", False)
        except ml.MasterLocalError:
            check(f"깨진 파일 거절 {bad!r}", True)


def test_claude_user_get() -> None:
    e = ml.entry_for(_paths(Path("/t")))
    txt = json.dumps({"mcpServers": {"ax-client": {"type": "stdio", **e}},
                      "projects": {"/x": {"mcpServers": {"ax-client": {"command": "other"}}}}})
    check("최상위(user) 항목을 읽는다", ml.stdio_matches(ml.claude_user_get(txt), e))
    check("projects(로컬) 항목은 user 가 아니다",
          ml.claude_user_get(json.dumps({"projects": {"/x": {"mcpServers": {"ax-client": {}}}}})) == {})
    check("깨진 파일은 빈 값", ml.claude_user_get("{") == {})


def test_config_same_shape_as_delivery() -> None:
    p = _paths(Path("/t"))
    f = bundle.HostFacts(host=bundle.MASTER_HOST, user="sim", path=str(p.root), driven="local",
                         role="requester", os="linux", python=str(p.python))
    cfg = ml.build_config("AXCluster", f)
    ref = bundle.config_for("AXCluster", f)
    check("배달과 같은 키", set(cfg) == set(ref), str(set(cfg) ^ set(ref)))
    v = ml.config_view(cfg)
    check("client_mcp 가 읽는 칸", v == {"project": "AXCluster", "host": "192.168.0.57",
                                        "task_queue": 8101, "projects": 8103}, str(v))
    check("비밀 칸 없음", "token" not in cfg)
    try:
        ml.build_config("", f)
        check("빈 마운트 거절", False)
    except ml.MasterLocalError:
        check("빈 마운트 거절", True)


def test_token_never_printed() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _paths(tmp)
        secret = "S3CRET-" + "x" * 40
        p.token_src.write_text(secret + "\n")
        os.chmod(p.token_src, 0o600)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            lines = ml.plan(p, "AXCluster")
        out = "\n".join(lines) + buf.getvalue()
        check("plan 에 토큰 값 없음", secret not in out)
        check("plan 은 digest 앞 12자", ml.token_digest(secret)[:12] in out)
        check("plan 은 쓰지 않는다", not p.root.exists())
        check("digest 는 공백 무시", ml.token_digest(secret + "\n") == ml.token_digest(secret))


def test_apply_writes_root_and_files() -> None:
    """apply 의 파일 절(루트·config·token·codex·agy)을 임시 집에서. CLI 호출은 막는다."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _paths(tmp)
        secret = "T0KEN-" + "y" * 40
        p.token_src.write_text(secret + "\n")
        os.chmod(p.token_src, 0o600)
        p.codex_toml.parent.mkdir(parents=True)
        p.codex_toml.write_text(HAND_MADE)
        p.agy_json.parent.mkdir(parents=True)
        p.agy_json.write_text("")
        p.legacy_root.mkdir(parents=True)
        f = bundle.HostFacts(host=bundle.MASTER_HOST, user="sim", path=str(p.root), driven="local",
                             role="requester", os="linux")
        calls = []
        keep = (ml._run, ml.shutil.which, ml.codex_get_live)
        ml._run = lambda argv, timeout=60: (calls.append(argv) or (1, "stub"))
        ml.shutil.which = lambda name: None                       # claude 없음 → 실패로 보고
        ml.codex_get_live = lambda name=ml.SERVER: {
            "enabled": True, "enabled_tools": None,
            "transport": {"type": "stdio", **ml.entry_for(p), "cwd": None}}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = ml.apply(p, "AXCluster", facts=f)
        finally:
            ml._run, ml.shutil.which, ml.codex_get_live = keep
        out = buf.getvalue()
        check("claude 부재는 실패 rc=1", rc == 1, out)
        check("루트 0700", (p.root.stat().st_mode & 0o777) == 0o700)
        tok = p.root / ".ax/token"
        check("token 0600", (tok.stat().st_mode & 0o777) == 0o600)
        check("token 같은 값", tok.read_text().strip() == secret)
        check("출력에 토큰 값 없음", secret not in out)
        cfg = json.loads((p.root / ".ax/config.json").read_text())
        check("config project", cfg["project"] == "AXCluster")
        check("codex 백업", any(x.name.startswith("config.toml.bak-master-local-")
                                for x in p.codex_toml.parent.iterdir()))
        check("agy 백업(0바이트도)", any(x.name.startswith("mcp_config.json.bak-master-local-")
                                       for x in p.agy_json.parent.iterdir()))
        check("codex 관리 블록", ml.CODEX_BEGIN in p.codex_toml.read_text()
              and "cwd" not in p.codex_toml.read_text().split(ml.CODEX_BEGIN)[1])
        check("agy 항목", ml.stdio_matches(ml.agy_get(p.agy_json.read_text()), ml.entry_for(p)))
        check("agy 권한 파일(임시 집)", str(p.agy_settings).startswith(str(tmp))
              and ml.agy_approvals(p.agy_settings.read_text()) == tuple(sorted(ml.READ_APPROVE)))
        check("옛 루트는 남긴다", p.legacy_root.exists() and "지우지 않았다" in out)
        check("CLI 미호출(claude 부재)", not calls, str(calls))
        # 두 번째 apply — 파일 절은 「이미 같다」
        buf = io.StringIO()
        ml._run = lambda argv, timeout=60: (1, "stub")
        ml.shutil.which = lambda name: None
        ml.codex_get_live = lambda name=ml.SERVER: {
            "enabled": True, "enabled_tools": None,
            "transport": {"type": "stdio", **ml.entry_for(p), "cwd": None}}
        try:
            with contextlib.redirect_stdout(buf):
                ml.apply(p, "AXCluster", facts=f)
        finally:
            ml._run, ml.shutil.which, ml.codex_get_live = keep
        o2 = buf.getvalue()
        check("재실행 멱등", all(s in o2 for s in ("config.json 이미 같다", "token 이미 같다",
                                                   "config.toml 이미 같다", "mcp_config.json 이미 같다")), o2)


def test_agy_permissions() -> None:
    """agy 헤드리스 허용 — 읽기 셋만 더하고, 사람이 넣은 항목은 보존하고, 깨진 파일은 덮지 않는다."""
    human = json.dumps({"model": "x", "permissions": {"allow": ["command(rg)"]}, "trustedWorkspaces": ["/a"]})
    new, added = ml.agy_permissions_text(human, ml.READ_APPROVE)
    d = json.loads(new)
    check("agy 권한: 사람 항목 보존", "command(rg)" in d["permissions"]["allow"]
          and d["model"] == "x" and d["trustedWorkspaces"] == ["/a"], new)
    check("agy 권한: 읽기 셋을 더한다", added == tuple(ml.agy_grant(t) for t in ml.READ_APPROVE), str(added))
    check("agy 권한: 쓰기는 넣지 않는다", not any("redmine_note" in a or "create" in a
                                                   for a in d["permissions"]["allow"]))
    check("agy 권한: 문법 mcp(서버/도구)", ml.agy_grant("redmine_meta") == "mcp(ax-client/redmine_meta)")
    again, added2 = ml.agy_permissions_text(new, ml.READ_APPROVE)
    check("agy 권한: 두 번째는 더할 것 없음", not added2 and again == new)
    check("agy 권한: 되읽기", ml.agy_approvals(new) == tuple(sorted(ml.READ_APPROVE)))
    _, added3 = ml.agy_permissions_text("", ml.READ_APPROVE)
    check("agy 권한: 빈 파일은 새로", len(added3) == len(ml.READ_APPROVE))
    for bad in ("{broken", "[]", json.dumps({"permissions": []}),
                json.dumps({"permissions": {"allow": "x"}})):
        try:
            ml.agy_permissions_text(bad, ml.READ_APPROVE)
            check(f"agy 권한: 거절 {bad[:20]}", False)
        except ml.MasterLocalError:
            check(f"agy 권한: 거절 {bad[:20]}", True)
    check("agy 권한: 깨진 파일 되읽기는 빈 값", ml.agy_approvals("{broken") == ())


def test_cli_wiring() -> None:
    check("master-local 서브커맨드 등록", "master-local" in client_cli._CMDS)
    check("도움말에 보인다", "master-local" in (client_cli.__doc__ or ""))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = client_cli.main(["master-local", "--apply", "--check"])
    check("--apply·--check 동시는 거절", rc == 2)


def main() -> int:
    for fn in (test_entry_is_one_shape, test_redmine_tools, test_codex_text_replaces_hand_made,
               test_codex_text_refuses, test_codex_get_matches, test_agy_text,
               test_claude_user_get, test_config_same_shape_as_delivery,
               test_token_never_printed, test_apply_writes_root_and_files, test_agy_permissions,
               test_cli_wiring):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_master_local: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
