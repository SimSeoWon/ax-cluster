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


def _facts(p: ml.Paths) -> bundle.HostFacts:
    return bundle.HostFacts(host=bundle.MASTER_HOST, user="sim", path=str(p.root), driven="local",
                            role="requester", os="linux")


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
    new, removed = ml.codex_text(HAND_MADE, e, ml.all_client_tools())
    import tomli
    d = tomli.loads(new)
    ax = d["mcp_servers"]["ax-client"]
    check("command/args 가 공용 형태", ax["command"] == e["command"] and ax["args"] == e["args"])
    check("cwd 제거", "cwd" not in ax)
    check("enabled_tools 제거", "enabled_tools" not in ax)
    check("실제 도구 전체 approve", ml.codex_approvals(new) == tuple(sorted(ml.all_client_tools())),
          str(ml.codex_approvals(new)))
    check("AX MCP 기본 승인·노출", ml.codex_all_approved(new))
    check("다른 서버 보존", d["mcp_servers"]["ax-projects"]["url"].endswith("/mcp")
          and d["mcp_servers"]["ax-projects"]["tools"]["list_projects_tool"]["approval_mode"] == "approve")
    check("최상위·projects 보존", d["model"] == "gpt-5" and d["projects"]["/home/sim"]["trust_level"] == "trusted")
    check("옛 설명 주석 제거", "Existing ax-client stdio server" not in new)
    check("걷은 것 보고", any("손으로 만든" in r for r in removed), str(removed))
    again, removed2 = ml.codex_text(new, e, ml.all_client_tools())
    check("멱등 — 두 번째는 같은 본문", again == new)
    check("두 번째는 관리 블록만 걷음", removed2 == ["관리 블록(이전 master-local 출력)"], str(removed2))
    first, _ = ml.codex_text("", e, ml.all_client_tools())
    check("빈 파일에서도 생성", ml.CODEX_BEGIN in first and tomli.loads(first)["mcp_servers"]["ax-client"])


def test_codex_existing_approvals_and_restrictions() -> None:
    """현재 17개 승인을 보존하며 AX MCP의 명시 제한은 전체 허용 정책으로 바꾼다."""
    import tomli
    current = (*ml.READ_APPROVE, "list_works", "redmine_note", "redmine_link_commit",
               "redmine_create_issue", "register_work", "get_work", "list_fixes", "get_fix",
               "update_fix_status", "find_recipes", "get_anti_patterns", "find_history",
               "log_history", "issue_finish")
    existing = HAND_MADE + "\n".join(
        f'\n[mcp_servers.ax-client.tools.{name}]\napproval_mode = "approve"'
        for name in (*current[3:], "future_tool"))
    e = ml.entry_for(_paths(Path("/t")))
    new, _ = ml.codex_text(existing, e, ml.all_client_tools())
    check("기존 17개 승인 보존", set(current).issubset(set(ml.codex_approvals(new))))
    check("생성기 미등재 기존 승인도 보존", "future_tool" in ml.codex_approvals(new))
    again, _ = ml.codex_text(new, e, ml.all_client_tools())
    check("추가 승인 보존도 멱등", new == again)

    restricted = '''approval_policy = "on-request"
sandbox_mode = "workspace-write"
[mcp_servers.ax-projects]
url = "http://localhost:8103/mcp"
enabled = false
enabled_tools = [
  "only_one",
]
disabled_tools = ["other"]
omit_tools_from = ["codex"]
default_tools_approval_mode = "prompt"
[mcp_servers.ax-projects.http_headers]
Authorization = "test-header-preserved"
[mcp_servers.ax-projects.tools.issue_start_tool]
approval_mode = "prompt"
enabled = false
[mcp_servers.other]
command = "other-server"
enabled = false
'''
    fixed, _ = ml.codex_text(restricted, e, ml.all_client_tools())
    parsed = tomli.loads(fixed)
    projects = parsed["mcp_servers"]["ax-projects"]
    check("명시 거절·도구 노출 제한 해소", ml.codex_all_approved(fixed)
          and all(k not in projects for k in ("enabled_tools", "disabled_tools", "omit_tools_from")))
    check("기존 제한 설정은 검사 불통과", not ml.codex_all_approved(restricted))
    check("연결·다른 서버·샌드박스 보존", projects["url"] == "http://localhost:8103/mcp"
          and projects["http_headers"]["Authorization"] == "test-header-preserved"
          and parsed["mcp_servers"]["other"]["enabled"] is False
          and parsed["approval_policy"] == "on-request" and parsed["sandbox_mode"] == "workspace-write")
    for extra in ('enabled = false', 'enabled_tools = []', 'disabled_tools = ["x"]',
                  'omit_tools_from = ["codex"]'):
        blocked = fixed.replace('[mcp_servers.ax-client]', '[mcp_servers.ax-client]\n' + extra)
        if extra == 'enabled = false':
            blocked = fixed.replace('enabled = true', 'enabled = false', 1)
        check(f"노출 제한 검사 {extra}", not ml.codex_all_approved(blocked))
    prompt = fixed.replace('[mcp_servers.ax-projects.tools.issue_start_tool]\napproval_mode = "approve"',
                           '[mcp_servers.ax-projects.tools.issue_start_tool]\napproval_mode = "prompt"')
    check("개별 승인 override 검사", not ml.codex_all_approved(prompt))


def test_codex_text_refuses() -> None:
    e = ml.entry_for(_paths(Path("/t")))
    for name, text in (("깨진 TOML", "[a\nb = "),
                       ("인라인 정의", '[mcp_servers]\n"ax-client" = { command = "x" }\n')):
        try:
            ml.codex_text(text, e, ml.READ_APPROVE)
            check(f"{name} 은 거절", False)
        except ml.MasterLocalError:
            check(f"{name} 은 거절", True)


def test_review_r54_edges() -> None:
    # R54-3: 관리 블록 끝 표시가 시작보다 앞이면 덮지 않고 거절한다
    e = ml.entry_for(_paths(Path("/t")))
    bad = f"{ml.CODEX_END}\n[x]\na = 1\n{ml.CODEX_BEGIN}\n"
    try:
        ml.codex_text(bad, e, ml.READ_APPROVE)
        check("R54-3 순서 어긋난 관리 블록은 거절", False)
    except ml.MasterLocalError:
        check("R54-3 순서 어긋난 관리 블록은 거절", True)
    except IndexError as ex:
        check("R54-3 순서 어긋난 관리 블록은 거절", False, f"IndexError {ex}")
    # R54-2: 원천 토큰 읽기 예외의 메시지가 비어도 죽지 않고 예외 이름을 남긴다
    with tempfile.TemporaryDirectory() as td:
        p = _paths(Path(td))
        from master import auth as _auth
        orig = _auth.load_token
        _auth.load_token = lambda _p: (_ for _ in ()).throw(RuntimeError())
        try:
            src, _dst, err = ml._token_state(p)
            check("R54-2 빈 메시지 예외도 사유를 남긴다", src == "" and err == "RuntimeError", err)
        except IndexError as ex:
            check("R54-2 빈 메시지 예외도 사유를 남긴다", False, f"IndexError {ex}")
        finally:
            _auth.load_token = orig


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
              and ml.agy_approvals(p.agy_settings.read_text()) == tuple(sorted(ml.all_client_tools())))
        check("Claude 전체 허용 파일(임시 집)", str(p.claude_settings).startswith(str(tmp))
              and ml.claude_all_approved(p.claude_settings.read_text()))
        check("Codex 전체 허용 파일", ml.codex_all_approved(p.codex_toml.read_text()))
        check("옛 루트는 남긴다", p.legacy_root.exists() and "지우지 않았다" in out)
        # `#920` — ax-projects 는 토큰이 들어가므로 0600, 다른 항목 보존, 값은 출력 안 함
        pt = tmp / "projects-token"
        pt.write_text("projects-secret-920\n")
        p.projects_token = pt
        buf = io.StringIO()
        ml._run = lambda argv, timeout=60: (1, "stub")           # 대역 — 실제 CLI 설정을 건드리지 않는다
        ml.shutil.which = lambda name: None
        ml.codex_get_live = lambda name=ml.SERVER: {
            "enabled": True, "enabled_tools": None,
            "transport": {"type": "stdio", **ml.entry_for(p), "cwd": None}}
        try:
            with contextlib.redirect_stdout(buf):
                ml.apply(p, "AXCluster", facts=f)
        finally:
            ml._run, ml.shutil.which, ml.codex_get_live = keep
        out920, cfg920 = buf.getvalue(), json.loads(p.agy_json.read_text())
        url = ml.projects_mcp_url()
        check("#920 agy ax-projects 항목", ml.agy_projects_matches(p.agy_json.read_text(), url, "projects-secret-920")
              and cfg920["mcpServers"]["ax-projects"]["serverUrl"] == url, str(list(cfg920["mcpServers"])))
        check("#920 ax-client 보존", ml.stdio_matches(ml.agy_get(p.agy_json.read_text()), ml.entry_for(p)))
        check("#920 파일 0600", (p.agy_json.stat().st_mode & 0o777) == 0o600)
        check("#920 출력에 토큰 값 없음", "projects-secret-920" not in out920)
        check("#920 다른 토큰이면 불일치", not ml.agy_projects_matches(p.agy_json.read_text(), url, "x"))
        p.projects_token = None
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
    """전체 도구를 더하되 Antigravity의 기존 전체 허용·모드·다른 설정은 보존한다."""
    human = json.dumps({"model": "x", "mode": "accept-edits", "permissions": {
        "allow": ["command(*)", "mcp(ax-projects/issue_start_tool)", "mcp(ax-client/future_tool)"]},
        "trustedWorkspaces": ["/a"]})
    approve = ml.all_client_tools()
    new, added = ml.agy_permissions_text(human, approve)
    d = json.loads(new)
    check("agy 권한: 사람 항목 보존", set(json.loads(human)["permissions"]["allow"]).issubset(
        set(d["permissions"]["allow"])) and d["mode"] == "accept-edits"
          and d["model"] == "x" and d["trustedWorkspaces"] == ["/a"], new)
    check("agy 권한: 전체 도구를 더한다", added == tuple(ml.agy_grant(t) for t in approve), str(added))
    check("agy 권한: 쓰기도 포함", "mcp(ax-client/redmine_note)" in d["permissions"]["allow"])
    check("agy 권한: 문법 mcp(서버/도구)", ml.agy_grant("redmine_meta") == "mcp(ax-client/redmine_meta)")
    again, added2 = ml.agy_permissions_text(new, approve)
    check("agy 권한: 두 번째는 더할 것 없음", not added2 and again == new)
    check("agy 권한: 되읽기", set(approve).issubset(set(ml.agy_approvals(new))))
    _, added3 = ml.agy_permissions_text("", approve)
    check("agy 권한: 빈 파일은 새로", len(added3) == len(approve))
    for bad in ("{broken", "[]", json.dumps({"permissions": []}),
                json.dumps({"permissions": {"allow": "x"}})):
        try:
            ml.agy_permissions_text(bad, approve)
            check(f"agy 권한: 거절 {bad[:20]}", False)
        except ml.MasterLocalError:
            check(f"agy 권한: 거절 {bad[:20]}", True)
    check("agy 권한: 깨진 파일 되읽기는 빈 값", ml.agy_approvals("{broken") == ())
    # #928: 기본 CLI 명령 접두사 함께 추가 검증
    with_cmds, added_cmds = ml.agy_permissions_text("", approve, extra_commands=ml.AGY_BASE_COMMANDS)
    check("agy 권한: 기본 CLI 명령 포함", all(cmd in json.loads(with_cmds)["permissions"]["allow"] for cmd in ml.AGY_BASE_COMMANDS))
    check("agy 권한: 전체 도구 포함 확인", set(approve).issubset(set(ml.agy_approvals(with_cmds))))


def test_claude_permissions() -> None:
    human = json.dumps({"hooks": {"Stop": []}, "permissions": {"allow": ["Bash(rg *)"]}})
    new = ml.claude_permissions_text(human)
    d = json.loads(new)
    check("Claude 전체 허용 모드", ml.claude_all_approved(new))
    check("Claude 다른 설정 보존", d["hooks"] == {"Stop": []}
          and d["permissions"]["allow"] == ["Bash(rg *)"])
    check("Claude 멱등", ml.claude_permissions_text(new) == new)
    check("Claude 기본 모드는 전체 허용 아님", not ml.claude_all_approved("{}"))
    for bad in ("{broken", "[]", '{"permissions": []}'):
        try:
            ml.claude_permissions_text(bad)
            check("Claude 깨진 설정 거절", False)
        except ml.MasterLocalError:
            check("Claude 깨진 설정 거절", True)


def test_cli_wiring() -> None:
    check("master-local 서브커맨드 등록", "master-local" in client_cli._CMDS)
    check("도움말에 보인다", "master-local" in (client_cli.__doc__ or ""))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = client_cli.main(["master-local", "--apply", "--check"])
    check("--apply·--check 동시는 거절", rc == 2)


def test_claude_skills_sync_and_check() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skills_dir = root / "skills"
        skills_dir.mkdir()
        (skills_dir / "ax-test-skill").mkdir()
        (skills_dir / "ax-test-skill" / "SKILL.md").write_text("---\nname: ax-test-skill\n---\n")
        claude_skills = root / "claude_skills"
        claude_skills.mkdir()

        p = ml.Paths(
            home=root,
            root=root / ".local" / "share" / ml.SERVER,
            token_src=root / "dummy_token",
            python=Path(sys.executable),
            script=root / "dummy_script.py",
            claude_json=root / ".claude.json",
            codex_toml=root / "config.toml",
            agy_json=root / "mcp_config.json",
            legacy_root=root / "legacy",
            skills_dir=skills_dir,
            claude_skills=claude_skills,
        )

        # 1. 초기 상태: claude_skills에 링크 없음 -> 누락 확인
        master_skills = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
        claude_existing = set(d.name for d in claude_skills.iterdir())
        missing = [s for s in master_skills if s not in claude_existing]
        check("Claude 스킬 누락 감지", missing == ["ax-test-skill"])

        # 2. apply() 시 심볼릭 링크 자동 생성
        p.token_src.write_text("dummy-token-for-test")
        (p.root / ".ax").mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        # `#930` — 대역이 없으면 apply 가 진짜 `claude mcp` 로 실제 ~/.claude.json 을 고쳤다
        calls, f = [], _facts(p)
        keep = (ml._run, ml.shutil.which, ml.codex_get_live)
        ml._run = lambda argv, timeout=60: (calls.append(argv) or (1, "stub"))
        ml.shutil.which = lambda name: None
        ml.codex_get_live = lambda name=ml.SERVER: {}
        try:
            with contextlib.redirect_stdout(buf):
                # 필요한 최소 파일 준비
                p.claude_json.write_text("{}")
                p.codex_toml.write_text("")
                p.agy_json.write_text("{}")
                ml.apply(p, "test-proj", facts=f)
        finally:
            ml._run, ml.shutil.which, ml.codex_get_live = keep
        check("#930 스킬 시험이 CLI 를 부르지 않는다", not calls, str(calls))

        link = claude_skills / "ax-test-skill"
        check("apply 후 Claude 스킬 심볼릭 링크 생성됨", link.is_symlink())
        check("심볼릭 링크 대상 일치", link.resolve() == (skills_dir / "ax-test-skill").resolve())

        # 3. 링크 존재 시 누락 없음 확인
        claude_existing_after = set(d.name for d in claude_skills.iterdir())
        missing_after = [s for s in master_skills if s not in claude_existing_after]
        check("심볼릭 링크 생성 후 누락 0건", missing_after == [])


def _apply_with_cli_present(p: ml.Paths) -> tuple:
    """`claude` 가 PATH 에 있는 것처럼 apply 를 돌린다 → `(rc, 출력, CLI 호출 목록)`."""
    p.token_src.write_text("T0KEN-930\n")
    p.codex_toml.parent.mkdir(parents=True)
    p.codex_toml.write_text("")
    p.agy_json.parent.mkdir(parents=True)
    p.agy_json.write_text("{}")
    calls, buf = [], io.StringIO()
    keep = (ml._run, ml.shutil.which, ml.codex_get_live)
    ml._run = lambda argv, timeout=60: (calls.append(argv) or (1, "stub"))
    ml.shutil.which = lambda name: "/opt/bin/" + name
    ml.codex_get_live = lambda name=ml.SERVER: {}
    try:
        with contextlib.redirect_stdout(buf):
            rc = ml.apply(p, "AXCluster", facts=_facts(p))
    finally:
        ml._run, ml.shutil.which, ml.codex_get_live = keep
    return rc, buf.getvalue(), calls


def test_apply_refuses_cli_outside_real_config() -> None:
    """`#930` — CLI 는 `Paths` 를 모른다. 실제 설정이 아닌 경로면 CLI 를 부르지 않는다."""
    keep_env = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_CONFIG_DIR")}
    try:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        with tempfile.TemporaryDirectory() as td:
            rc, out, calls = _apply_with_cli_present(_paths(Path(td)))
            check("#930 임시 경로면 CLI 호출 0건", not calls, str(calls))
            check("#930 임시 경로면 실패 rc=1", rc == 1, out)
            check("#930 거절 사유 출력", "CLI 호출을 거절한다" in out, out)
        # 운영 경로(CLI 가 실제로 쓰는 파일)는 그대로 CLI 를 부른다 — 방어가 설치를 막지 않는다
        with tempfile.TemporaryDirectory() as td:
            p = _paths(Path(td))
            p.home.mkdir()
            os.environ["HOME"] = str(p.home)
            _rc, out, calls = _apply_with_cli_present(p)
            check("#930 운영 경로면 add-json 호출", any("add-json" in c for c in calls), out)
    finally:
        for k, v in keep_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _live_config() -> dict:
    """실제 집의 세 CLI `ax-client` 설정. 읽기만 하고, 값은 비교에만 쓴다(`#930`)."""
    h = Path.home()
    codex = ml._read(h / ".codex" / "config.toml")
    block = codex.partition(ml.CODEX_BEGIN)[2].partition(ml.CODEX_END)[0]
    return {"claude": ml.claude_user_get(ml._read(h / ".claude.json")),
            "codex": block,
            "agy": ml.agy_get(ml._read(h / ".gemini" / "config" / "mcp_config.json"))}


def _changed(before: dict, after: dict) -> list:
    """달라진 CLI 이름만 — 설정 값(경로·토큰)은 출력에 싣지 않는다."""
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def test_live_config_guard_detects_change() -> None:
    """`#930` T3 — 감시가 실제로 변경을 잡는가. 값은 사유에 실리지 않는다."""
    a = {"claude": {"args": ["/home/x"]}, "codex": "b", "agy": {}}
    check("#930 같으면 변경 없음", _changed(a, dict(a)) == [])
    check("#930 바뀌면 이름을 짚는다", _changed(a, {**a, "claude": {"args": ["/tmp/y"]}}) == ["claude"])


def main() -> int:
    before = _live_config()
    try:
        for fn in (test_entry_is_one_shape, test_redmine_tools, test_codex_text_replaces_hand_made,
                   test_codex_existing_approvals_and_restrictions, test_claude_permissions,
                   test_codex_text_refuses, test_review_r54_edges, test_codex_get_matches, test_agy_text,
                   test_claude_user_get, test_config_same_shape_as_delivery,
                   test_token_never_printed, test_apply_writes_root_and_files, test_agy_permissions,
                   test_cli_wiring, test_claude_skills_sync_and_check,
                   test_apply_refuses_cli_outside_real_config, test_live_config_guard_detects_change):
            fn()
    finally:
        # `#930` — 임시 경로만 보는 검사는 통과해도 실제 설정이 망가진 것을 못 본다
        changed = _changed(before, _live_config())
        check("#930 실제 CLI 설정 불변", not changed, f"달라진 설정: {changed}")
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_master_local: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
