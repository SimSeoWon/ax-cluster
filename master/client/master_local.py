"""마스터(.57) 로컬 LLM CLI 세 개에 `ax-client` stdio MCP 하나를 단다.

    python -m master.client master-local            계획만 (쓰지 않는다)
    python -m master.client master-local --apply    루트 생성 + 세 CLI 등록 → 되읽어 대조
    python -m master.client master-local --check    항목마다 OK/FAIL 한 줄, FAIL 이 있으면 rc=1

## 왜 있나

마스터의 Claude Code · Codex CLI · Antigravity(`agy`) 가 레드마인을 **같은 MCP 하나**로 다뤄야
한다. 그 MCP 는 워커·요청자에 배달되는 `client/runtime/client_mcp.py` 그대로다 — 마스터 큐
(8101) `/api/v1/redmine/*` 를 requester 토큰으로 부른다. 종전에는 Codex 쪽에만 **손으로 만든**
루트(`~/.codex/ax-client`)가 있었고 `.ax/token` 이 없어 모든 호출이 죽었다. 손으로 만든 설정은
조용히 갈라진다 — 그래서 이 명령이 만들고 이 명령이 잰다.

## [중요] 루트는 도구 중립 자리 하나다 — `~/.local/share/ax-client`

`client_mcp.py` 는 `.ax/config.json`·`.ax/token` 을 **cwd 기준**으로 찾는다. 세 CLI 가 같은 루트를
보게 하려면 그 루트가 어느 한 도구의 집(`~/.codex`·`~/.claude`·`~/.gemini`) 안에 있으면 안 된다
— 한 도구를 지우거나 재설치할 때 남의 MCP 가 같이 죽는다. XDG 데이터 자리가 그 중립 위치다.

## [중요] 기동 형태도 하나다 — `/usr/bin/env -C <루트> <python> <client_mcp.py>`

Claude Code 의 stdio 항목과 agy 의 `mcp_config.json` 에는 **cwd 필드가 없다**(agy 문서
`agy-customizations/docs/mcp_servers.md` 는 command·args·env 뿐). `client_mcp.py` 는 환경변수로
루트를 받지 않으므로(cwd 고정이 그 파일의 결정이고, 이 명령은 그 파일을 고치지 않는다) cwd 를
**기동 명령이** 정한다. coreutils `env -C`(`--chdir`)가 그 일을 한다. Codex 는 cwd 필드가
있지만 같은 형태를 쓴다 — 세 도구에 다른 명령이 등록되면 한쪽만 도는 상태가 조용히 생긴다
(`bundle.mcp_entry_for` 가 한 자리인 이유와 같다). 그래서 **조립 자리는 `entry_for` 하나다.**

## [중요] 노출 도구는 세 CLI 가 같다 — Codex 의 `enabled_tools` 를 걷는다

Claude 의 MCP 항목과 agy 의 `mcp_config.json` 에는 도구 허용 목록이 없다. Codex 에만 목록을 두면
같은 MCP 가 CLI 마다 다른 도구를 보인다. 그래서 목록을 두지 않고, 실제 `ax-client` 도구
전부를 자동 승인한다(사용자 2026-11-09). 기존에 추가한 승인도 보존한다. 도구 실행 권한과
일감·사람 게이트의 승인 규칙은 별개다.

## [중요] 토큰은 출력에 싣지 않는다

값을 찍지 않고 **sha256 앞 12자**로만 대조한다. 원천은 `auth.role_token_file("requester")`
(권한·길이 검사는 `auth.load_token` 재사용).
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import bundle

SERVER = bundle.MCP_SERVER_NAME                 # "ax-client" — 선언은 spec.MCP_BY_ROLE
ROLE = "requester"
ENV_BIN = "/usr/bin/env"
REPO = Path(__file__).resolve().parents[2]
# 기존 읽기 목록 API는 유지한다. 설치·대조의 승인 정본은 all_client_tools()다.
READ_APPROVE = ("redmine_list_issues", "redmine_get_issue", "redmine_meta")
CODEX_BEGIN = "# BEGIN AX MANAGED MCP (master-local)"
CODEX_END = "# END AX MANAGED MCP (master-local)"
LOG = "[master-local]"
AGY_PROJECTS = "ax-projects"
AGY_BASE_COMMANDS = (
    "command(git)",
    "command(git -C)",
    "command(python3)",
    "command(.venv/bin/python)",
    "command(/home/sim/ax-cluster/.venv/bin/python)",
    "command(AX_PROJECTS_ROOT=)",
    "command(cd /home/sim/ax-cluster)",
    "command(systemctl)",
    "command(journalctl)",
    "command(agy)",
    "command(rg)",
    "command(ls)",
    "command(cat)",
    "command(sed)",
    "command(head)",
    "command(tail)",
    "command(grep)",
    "command(diff)",
    "command(find)",
    "command(which)",
)


class MasterLocalError(RuntimeError):
    """설치·검사를 진행할 수 없다. [중요] 조용히 건너뛰지 않는다."""


@dataclass
class Paths:
    """이 명령이 만지는 자리 전부. 테스트는 임시 디렉토리로 통째로 바꾼다."""
    home: Path
    root: Path
    token_src: Path
    python: Path
    script: Path
    claude_json: Path
    codex_toml: Path
    agy_json: Path
    legacy_root: Path
    projects_token: Path | None = None  # `#920` agy ax-projects 헤더 토큰 — 비우면 그 단계를 건너뛴다(시험)
    agy_settings: Path | None = None    # agy 헤드리스 권한(`permissions.allow`) — 비우면 집 기준
    claude_settings: Path | None = None

    def __post_init__(self) -> None:
        if self.agy_settings is None:
            self.agy_settings = self.home / ".gemini" / "antigravity-cli" / "settings.json"
        if self.claude_settings is None:
            self.claude_settings = self.home / ".claude" / "settings.json"

    @classmethod
    def default(cls, home: Path | None = None) -> "Paths":
        from .. import auth as _auth
        h = home or Path.home()
        return cls(home=h,
                   root=h / ".local" / "share" / SERVER,
                   token_src=_auth.role_token_file(ROLE),
                   python=REPO / ".venv" / "bin" / "python",
                   script=REPO / "client" / "runtime" / "client_mcp.py",
                   claude_json=h / ".claude.json",
                   codex_toml=h / ".codex" / "config.toml",
                   agy_json=h / ".gemini" / "config" / "mcp_config.json",
                   legacy_root=h / ".codex" / SERVER,
                   projects_token=_auth.DEFAULT_TOKEN_FILE)


# ─────────────────────────────────────────────────────────────
# 순수 함수 — 무엇을 쓸지
# ─────────────────────────────────────────────────────────────

def entry_for(p: Paths) -> dict:
    """세 CLI 가 공유하는 stdio 기동 형태. 🔴 [중요] **조립 자리는 여기 하나다.**"""
    return {"command": ENV_BIN,
            "args": ["-C", str(p.root), str(p.python), str(p.script)]}


def redmine_tools(names: tuple | None = None) -> tuple:
    """클라 MCP 가 실제로 노출하는 redmine 도구. 선언은 `client_mcp.TOOLS` 하나다."""
    names = tuple(names if names is not None else bundle.client_tool_names())
    rm = tuple(n for n in names if n.startswith("redmine_"))
    missing = [n for n in READ_APPROVE if n not in rm]
    if missing:
        raise MasterLocalError(f"READ_APPROVE 의 {missing} 가 client_mcp.TOOLS 에 없다 — 목록이 낡았다")
    return rm


def all_client_tools() -> tuple:
    """권한 목록도 실제 클라이언트 TOOLS에서 얻는다 — 읽기·쓰기 모두 허용한다."""
    return tuple(bundle.client_tool_names())


def local_facts(p: Paths) -> "bundle.HostFacts":
    """마스터 자신의 실측 — `config_for` 의 backends 칸을 채운다(배달 프로브와 같은 뜻)."""
    def _ver(cmd: str) -> str:
        exe = shutil.which(cmd)
        if not exe:
            return ""
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
            return (r.stdout or "").strip().splitlines()[0] if r.returncode == 0 and r.stdout else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    return bundle.HostFacts(host=bundle.MASTER_HOST, user=getpass.getuser(), path=str(p.root),
                            driven="local", role=ROLE, os="linux", home=str(p.home),
                            claude=_ver("claude"), codex=_ver("codex"), python=str(p.python),
                            agy=bool(shutil.which("agy")), checkout_ok=False)


def build_config(project: str, facts: "bundle.HostFacts") -> dict:
    """`.ax/config.json` — 워커·요청자 배달과 **같은 `bundle.config_for`** 로 만든다."""
    if not (project or "").strip():
        raise MasterLocalError("마운트된 프로젝트가 비어 있다 — 폴백은 없다 (projects.yaml 의 active)")
    return bundle.config_for(project, facts)


def config_view(cfg: dict) -> dict:
    """대조할 칸 — `client_mcp.py` 가 **실제로 읽는 것**만. 도장(`delivered_by`)은 매 커밋 바뀐다."""
    m = (cfg or {}).get("master") or {}
    s = m.get("services") or {}
    return {"project": (cfg or {}).get("project"), "host": m.get("host"),
            "task_queue": s.get("task_queue"), "projects": s.get("projects")}


def token_digest(text: str) -> str:
    """토큰의 sha256 (공백 제거 후). [중요] 출력은 앞 12자만 — 값은 어디에도 찍지 않는다."""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def claude_user_get(claude_json_text: str, name: str = SERVER) -> dict:
    """`~/.claude.json` 최상위 `mcpServers` 의 항목(user 스코프). 없으면 빈 dict.

    [중요] `claude mcp get` 을 쓰지 않는다 — 접속을 시도해 느리고 실패가 섞인다
    (`bundle.claude_mcp_local_get` 과 같은 판단). 판정은 「등록됐나」다.
    """
    try:
        d = json.loads(claude_json_text or "{}")
    except ValueError:
        return {}
    got = ((d.get("mcpServers") or {}) if isinstance(d, dict) else {}).get(name)
    return got if isinstance(got, dict) else {}


def stdio_matches(got: dict, entry: dict) -> bool:
    """Claude·agy 항목 비교. `type` 은 없거나 stdio 여야 한다."""
    return (bool(got) and got.get("type", "stdio") == "stdio"
            and got.get("command") == entry["command"]
            and list(got.get("args") or []) == list(entry["args"]))


def codex_get_matches(got: dict, entry: dict) -> tuple:
    """`codex mcp get --json` 이 보는 항목 비교 → `(ok, 사유)`."""
    tr = (got or {}).get("transport") or {}
    if not got:
        return False, "codex 가 항목을 못 찾는다"
    if tr.get("type") != "stdio" or tr.get("command") != entry["command"] \
            or list(tr.get("args") or []) != list(entry["args"]):
        return False, f"기동 명령이 다르다 — {tr.get('command')} {' '.join(tr.get('args') or [])}"
    if tr.get("cwd"):
        return False, f"cwd 가 남아 있다({tr.get('cwd')}) — 기동 형태가 세 CLI 와 다르다"
    if got.get("enabled_tools") is not None:
        return False, "enabled_tools 허용 목록이 남아 있다 — 세 CLI 의 노출 도구가 갈린다"
    if got.get("enabled") is False:
        return False, "비활성(enabled=false)"
    return True, ""


def _toml():
    try:
        import tomli                                                  # noqa: PLC0415
    except ImportError as e:                                           # py3.10 — tomllib 없음
        raise MasterLocalError("tomli 가 없다 — .venv/bin/python 으로 돌릴 것") from e
    return tomli


def _header_key(line: str) -> list | None:
    """TOML 표 머리 `[a.b]`/`[[a.b]]` 의 키 경로. 머리가 아니면 None."""
    s = line.strip()
    if not s.startswith("["):
        return None
    s = s.lstrip("[").split("]", 1)[0].strip()      # 뒤의 `]`·주석은 버린다
    return [k.strip().strip('"').strip("'") for k in s.split(".")]


def _strip_codex_entry(text: str, name: str) -> tuple:
    """기존 `name` 항목을 걷어낸다 → `(남은 텍스트, 걷은 것 설명 목록)`.

    걷는 것: 관리 블록 전체 · 손으로 만든 `[mcp_servers.<name>]` 와 그 하위 표 · 그 머리 **바로
    위에 붙은** 주석 중 이름을 말하는 줄. [주의] 다른 표는 건드리지 않는다 — 그 보증은 호출자
    (`codex_text`)가 **파싱 결과를 앞뒤로 대조**해서 선다.
    """
    removed = []
    if CODEX_BEGIN in text and CODEX_END in text:
        before, rest = text.split(CODEX_BEGIN, 1)
        if CODEX_END not in rest:
            # R54-3: 끝 표시가 시작보다 앞에 있다 — 어디까지가 관리 블록인지 모르니 덮지 않는다
            raise MasterLocalError("config.toml 의 관리 블록 표시 순서가 어긋났다 — 덮지 않는다(사람이 확인할 것)")
        after = rest.split(CODEX_END, 1)[1]
        text = before.rstrip("\n") + "\n" + after.lstrip("\n")
        removed.append("관리 블록(이전 master-local 출력)")
    lines = text.splitlines()
    out: list = []
    inside = False
    n_tables = 0
    for line in lines:
        key = _header_key(line)
        if key is not None:
            inside = key[:2] == ["mcp_servers", name]
            if inside:
                n_tables += 1
                # 머리 바로 위의 이름 언급 주석은 그 항목의 설명이다 — 같이 걷는다
                while out and out[-1].lstrip().startswith("#") and name in out[-1]:
                    out.pop()
                continue
        if inside:
            continue
        out.append(line)
    if n_tables:
        removed.append(f"손으로 만든 [mcp_servers.{name}] 표 {n_tables}개(하위 tools 포함)")
    new = "\n".join(out).rstrip("\n")
    return (new + "\n" if new else ""), removed


def codex_block(entry: dict, approve: tuple, name: str = SERVER) -> str:
    lines = [CODEX_BEGIN,
             "# python -m master.client master-local 이 생성한다 — 손으로 고치지 말 것(다시 돌리면 덮인다).",
             "# 기동 형태·노출 도구는 Claude Code·agy 와 같다(enabled_tools 없음).",
             f"[mcp_servers.{name}]",
             f"command = {json.dumps(entry['command'], ensure_ascii=False)}",
             f"args = {json.dumps(list(entry['args']), ensure_ascii=False)}",
             "enabled = true",
             'default_tools_approval_mode = "approve"',
             "startup_timeout_sec = 30.0",
             "tool_timeout_sec = 120.0"]
    for t in approve:
        lines += ["", f"[mcp_servers.{name}.tools.{t}]", 'approval_mode = "approve"']
    lines.append(CODEX_END)
    return "\n".join(lines) + "\n"


def _codex_projects_approve(text: str) -> str:
    """등록된 ax-projects의 도구 노출·승인만 통일한다. 연결 설정은 보존한다."""
    lines = []
    key = None
    source = text.splitlines()
    index = 0
    while index < len(source):
        line = source[index]
        index += 1
        header = _header_key(line)
        if header is not None:
            key = header
            lines.append(line)
            if key == ["mcp_servers", AGY_PROJECTS]:
                lines.append('default_tools_approval_mode = "approve"')
                lines.append("enabled = true")
            continue
        field = line.strip().split("=", 1)[0].strip()
        if key == ["mcp_servers", AGY_PROJECTS]:
            if field in ("enabled_tools", "disabled_tools", "omit_tools_from"):
                # TOML 배열은 여러 줄일 수 있다. 실제 파서가 끝났다고 할 때까지 걷는다.
                assignment = line
                while True:
                    try:
                        _toml().loads(assignment)
                        break
                    except ValueError:
                        if index >= len(source):
                            raise MasterLocalError("ax-projects 도구 제한 목록을 읽지 못했다")
                        assignment += "\n" + source[index]
                        index += 1
                continue
            if field in ("default_tools_approval_mode", "enabled"):
                continue
        if key and key[:3] == ["mcp_servers", AGY_PROJECTS, "tools"]:
            if field == "approval_mode":
                line = 'approval_mode = "approve"'
            elif field == "enabled":
                line = "enabled = true"
        lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def codex_text(existing: str, entry: dict, approve: tuple, name: str = SERVER) -> tuple:
    """`~/.codex/config.toml` 의 새 본문 → `(본문, 걷은 것 목록)`.

    🔴 [중요] **파싱 결과로 보증한다** — 걷기 전후를 tomli 로 읽어 관리 ax-client 항목과
    ax-projects의 승인·노출 정책을 뺀 나머지가 **완전히 같아야** 쓴다.
    (마스터는 py3.10 이라 tomllib 이 없다 — 그래서 venv 의 tomli 다).
    """
    tomli = _toml()
    try:
        before = tomli.loads(existing or "")
    except Exception as e:                                             # noqa: BLE001
        raise MasterLocalError(f"기존 config.toml 이 깨진 TOML 이다 — 덮지 않는다 ({e})") from e
    # 생성기 목록보다 먼저 추가한 승인도 지우지 않는다(#927).
    approve = tuple(sorted(set(approve) | set(codex_approvals(existing, name))))
    stripped, removed = _strip_codex_entry(existing or "", name)
    stripped = _codex_projects_approve(stripped)
    new = (stripped + ("\n" if stripped else "")) + codex_block(entry, approve, name)
    try:
        after = tomli.loads(new)
    except Exception as e:                                             # noqa: BLE001
        raise MasterLocalError(f"생성한 config.toml 이 TOML 로 안 읽힌다 — 쓰지 않는다 ({e})") from e

    def _others(d: dict) -> dict:
        d = json.loads(json.dumps(d, default=str))
        (d.get("mcp_servers") or {}).pop(name, None)
        projects = (d.get("mcp_servers") or {}).get(AGY_PROJECTS)
        if isinstance(projects, dict):
            for field in ("default_tools_approval_mode", "enabled", "enabled_tools", "disabled_tools",
                          "omit_tools_from"):
                projects.pop(field, None)
            for tool in (projects.get("tools") or {}).values():
                if isinstance(tool, dict):
                    tool.pop("approval_mode", None)
                    tool.pop("enabled", None)
        if "mcp_servers" in d and not d["mcp_servers"]:
            d.pop("mcp_servers")
        return d
    if _others(before) != _others(after):
        raise MasterLocalError("관리 대상 MCP 승인 밖의 설정이 바뀌는 편집이다 — 쓰지 않는다(사람이 확인할 것)")
    got = (after.get("mcp_servers") or {}).get(name) or {}
    if got.get("command") != entry["command"] or got.get("args") != list(entry["args"]):
        raise MasterLocalError("생성한 config.toml 의 ax-client 항목이 기대와 다르다 — 쓰지 않는다")
    return new, removed


def codex_approvals(toml_text: str, name: str = SERVER) -> tuple:
    """config.toml 에서 `approval_mode = "approve"` 인 도구 이름들 (정렬)."""
    d = _toml().loads(toml_text or "")
    tools = (((d.get("mcp_servers") or {}).get(name) or {}).get("tools") or {})
    return tuple(sorted(t for t, v in tools.items()
                        if isinstance(v, dict) and v.get("approval_mode") == "approve"))


def codex_all_approved(text: str) -> bool:
    """두 AX MCP의 기본 허용과 개별 거절/질문 재정의 부재를 대조한다."""
    servers = _toml().loads(text or "").get("mcp_servers") or {}
    for name in (SERVER, AGY_PROJECTS):
        item = servers.get(name)
        if name == AGY_PROJECTS and item is None:
            continue
        if not isinstance(item, dict) or item.get("default_tools_approval_mode") != "approve":
            return False
        if item.get("enabled") is False or "enabled_tools" in item or item.get("disabled_tools") \
                or item.get("omit_tools_from"):
            return False
        if any(isinstance(t, dict) and (t.get("approval_mode", "approve") != "approve"
                                       or t.get("enabled") is False)
               for t in (item.get("tools") or {}).values()):
            return False
    return set(all_client_tools()).issubset(set(codex_approvals(text)))


def claude_permissions_text(existing: str) -> str:
    """Claude의 정식 전체 도구 허용 모드를 병합하며 다른 설정은 보존한다."""
    try:
        data = json.loads(existing or "{}")
    except ValueError as exc:
        raise MasterLocalError("기존 Claude settings.json이 깨진 JSON이다 — 덮지 않는다") from exc
    if not isinstance(data, dict) or not isinstance(data.get("permissions", {}), dict):
        raise MasterLocalError("Claude settings.json 및 permissions는 객체여야 한다 — 덮지 않는다")
    data.setdefault("permissions", {})["defaultMode"] = "bypassPermissions"
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def claude_all_approved(text: str) -> bool:
    try:
        data = json.loads(text or "{}")
        return isinstance(data, dict) and isinstance(data.get("permissions"), dict) \
            and data["permissions"].get("defaultMode") == "bypassPermissions"
    except ValueError:
        return False


def agy_text(existing: str, entry: dict, name: str = SERVER) -> str:
    """agy `mcp_config.json` 의 새 본문. 다른 서버 항목은 보존한다(`bundle.merge_mcp_json` 규약).

    [중요] 깨진 JSON 이면 **덮지 않고 멈춘다**. 0바이트(현재 상태)는 빈 설정으로 읽는다.
    """
    data = _agy_data(existing)
    data.setdefault("mcpServers", {})[name] = {"command": entry["command"],
                                               "args": list(entry["args"])}
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _agy_data(existing: str) -> dict:
    txt = (existing or "").strip()
    if not txt:
        return {}
    try:
        data = json.loads(txt)
    except ValueError as e:
        raise MasterLocalError(f"기존 mcp_config.json 이 깨진 JSON 이다 — 덮지 않는다 ({e})") from e
    if not isinstance(data, dict):
        raise MasterLocalError("기존 mcp_config.json 최상위가 객체가 아니다 — 덮지 않는다")
    return data


def projects_mcp_url() -> str:
    return f"http://{bundle.MASTER_HOST}:{bundle.SERVICES['projects']}/mcp"


def agy_projects_text(existing: str, url: str, token: str) -> str:
    """🔴 `#920` — agy 에 `ax-projects`(HTTP)를 더한다. 일감 시작이 이 경로의 clientInfo 를 요구한다.

    형식은 `agy mcp add -H … <이름> <url>` 의 산출(실측 2026-11-08). 토큰이 들어가므로 파일은 0600 이다.
    """
    data = _agy_data(existing)
    data.setdefault("mcpServers", {})[AGY_PROJECTS] = {"serverUrl": url,
                                                       "headers": {"Authorization": f"Bearer {token}"}}
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def agy_projects_matches(existing: str, url: str, token: str) -> bool:
    """토큰 값을 드러내지 않고 항목이 맞는지만 답한다."""
    try:
        item = json.loads(existing or "{}").get("mcpServers", {}).get(AGY_PROJECTS) or {}
    except (ValueError, AttributeError):
        return False
    return item.get("serverUrl") == url and item.get("headers") == {"Authorization": f"Bearer {token}"}


def agy_grant(tool: str, name: str = SERVER) -> str:
    """agy 권한 문법 `mcp(<서버>/<도구>)` — 내장 `automation` 스킬 문서의 형식."""
    return f"mcp({name}/{tool})"


def agy_permissions_text(existing: str, approve: tuple, name: str = SERVER,
                         extra_commands: tuple = ()) -> tuple:
    """agy `settings.json` 의 새 본문과 더한 항목 → `(본문, added)`.

    [중요] 헤드리스(`agy -p`)는 권한을 물을 수 없어 MCP 호출을 **자동 거부**한다(실측
    2026-10-05). 호출자가 전달한 전체 도구와 기본 클러스터 명령 접두사(`extra_commands`)를
    허용에 넣는다. 다른 키·다른 허용 항목은 보존하고, 깨진 JSON 이면 덮지 않고 멈춘다.
    """
    txt = (existing or "").strip()
    if txt:
        try:
            data = json.loads(txt)
        except ValueError as e:
            raise MasterLocalError(f"기존 agy settings.json 이 깨진 JSON 이다 — 덮지 않는다 ({e})") from e
        if not isinstance(data, dict):
            raise MasterLocalError("기존 agy settings.json 최상위가 객체가 아니다 — 덮지 않는다")
    else:
        data = {}
    perms = data.setdefault("permissions", {})
    if not isinstance(perms, dict):
        raise MasterLocalError("agy settings.json 의 permissions 가 객체가 아니다 — 덮지 않는다")
    allow = perms.setdefault("allow", [])
    if not isinstance(allow, list):
        raise MasterLocalError("agy settings.json 의 permissions.allow 가 목록이 아니다 — 덮지 않는다")
    to_add = [agy_grant(t, name) for t in approve] + [c for c in extra_commands if isinstance(c, str)]
    added = [g for g in to_add if g not in allow]
    allow.extend(added)
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n", tuple(added)


def agy_approvals(text: str, name: str = SERVER) -> tuple:
    """agy 허용 목록에서 이 서버의 도구만 → 정렬된 튜플. 읽지 못하면 빈 튜플."""
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return ()
    allow = ((d.get("permissions") or {}).get("allow") or []) if isinstance(d, dict) else []
    pre, post = f"mcp({name}/", ")"
    return tuple(sorted(a[len(pre):-1] for a in allow
                        if isinstance(a, str) and a.startswith(pre) and a.endswith(post)))


def agy_get(text: str, name: str = SERVER) -> dict:
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return {}
    got = ((d.get("mcpServers") or {}) if isinstance(d, dict) else {}).get(name)
    return got if isinstance(got, dict) else {}


# ─────────────────────────────────────────────────────────────
# 입출력 — 실제로 쓰고 읽는 자리
# ─────────────────────────────────────────────────────────────

def mounted_project() -> str:
    """마운트(=`projects.yaml` 의 active). `__main__._mounted_project_for_check` 와 같은 읽기."""
    return (bundle.Registry.load().active or "").strip()


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _backup(p: Path, stamp: str) -> str:
    """덮기 전 사본. 원본 권한을 그대로 가진다(copy2). 원본이 없으면 빈 문자열."""
    if not p.exists():
        return ""
    dst = p.with_name(f"{p.name}.bak-master-local-{stamp}")
    shutil.copy2(p, dst)
    return str(dst)


def _write_private(p: Path, text: str, mode: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(p, mode)


def _run(argv: list, timeout: int = 60) -> tuple:
    """subprocess 한 번 → `(rc, stdout+stderr)`. **예외를 던지지 않는다** — 실패도 사실이다."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, f"{type(e).__name__}: {e}"


def codex_get_live(name: str = SERVER) -> dict:
    """codex 가 **실제로 보는** 항목. rc 가 아니라 JSON 파싱 성공이 판정이다(`bundle.codex_mcp_get`)."""
    rc, out = _run(["codex", "mcp", "get", name, "--json"])
    if rc != 0:
        return {}
    try:
        got = json.loads(out)
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def _token_state(p: Paths) -> tuple:
    """`(원천 digest, 루트 digest, 원천 오류)`. 값은 돌려주지 않는다."""
    from .. import auth as _auth
    try:
        src = token_digest(_auth.load_token(p.token_src))
        err = ""
    except Exception as e:                                             # noqa: BLE001
        src, err = "", (str(e).splitlines() or [type(e).__name__])[0]   # R54-2: 빈 메시지
    dst_p = p.root / ".ax" / "token"
    dst = token_digest(_read(dst_p)) if dst_p.is_file() else ""
    return src, dst, err


def plan(p: Paths, project: str) -> list:
    """무엇을 할지 줄 목록. **쓰지 않는다.**"""
    e = entry_for(p)
    out = [f"{LOG} 마운트 프로젝트: {project or '(없음)'}",
           f"{LOG} 루트: {p.root} (0700) — .ax/config.json · .ax/token(0600)",
           f"{LOG} 기동: {e['command']} {' '.join(e['args'])}"]
    cur = config_view(json.loads(_read(p.root / ".ax" / "config.json") or "{}"))
    out.append(f"{LOG} config.json: {'이미 같다' if cur.get('project') == project and cur.get('host') else '쓴다'}"
               f" (현재 project={cur.get('project')})")
    src, dst, err = _token_state(p)
    out.append(f"{LOG} token: " + (f"[실패] 원천을 못 읽는다 — {err}" if err else
                                   "이미 같다" if src == dst else
                                   f"복사한다 (원천 sha256 {src[:12]} · 현재 {dst[:12] or '없음'})"))
    out.append(f"{LOG} claude(user): " + ("이미 같다" if stdio_matches(claude_user_get(_read(p.claude_json)), e)
                                         else "claude mcp add-json -s user 로 등록"))
    try:
        prev = _read(p.claude_settings)
        new = claude_permissions_text(prev)
        out.append(f"{LOG} claude 권한: " + ("이미 같다" if new == prev else
                   f"{p.claude_settings} permissions.defaultMode=bypassPermissions (백업 후)"))
    except MasterLocalError as ex:
        out.append(f"{LOG} claude 권한: [실패] {ex}")
    try:                                   # 계획에서도 실제 편집을 메모리에서 한 번 돌려 본다
        prev = _read(p.codex_toml)
        approve = all_client_tools()
        new, removed = codex_text(prev, e, approve)
        out.append(f"{LOG} codex: " + ("이미 같다" if new == prev else
                   f"{p.codex_toml} 관리 블록으로 교체 (백업 후) · 걷을 것: {'; '.join(removed) or '없음'}"
                   f" · approve={','.join(codex_approvals(new))}"))
    except MasterLocalError as ex:
        out.append(f"{LOG} codex: [실패] {ex}")
    out.append(f"{LOG} agy: {p.agy_json} 에 병합 (백업 후)")
    try:
        _, added = agy_permissions_text(_read(p.agy_settings), all_client_tools(), extra_commands=AGY_BASE_COMMANDS)
        out.append(f"{LOG} agy 권한: " + ("이미 같다" if not added else
                   f"{p.agy_settings} permissions.allow 에 더한다 (백업 후) — {', '.join(added)}"))
    except MasterLocalError as ex:
        out.append(f"{LOG} agy 권한: [실패] {ex}")
    if p.legacy_root.exists():
        out.append(f"{LOG} [주의] 손으로 만든 옛 루트 {p.legacy_root} — 지우지 않는다(사람이 정한다)")
    return out


def apply(p: Paths, project: str, *, facts=None) -> int:
    """만들고 등록하고 **되읽어 대조**한다. 실패가 하나라도 있으면 rc=1."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    e = entry_for(p)
    bad = 0

    # ── 루트 + config.json ──────────────────────────────────────
    ax = p.root / ".ax"
    ax.mkdir(parents=True, exist_ok=True)
    os.chmod(p.root, 0o700)
    os.chmod(ax, 0o700)
    print(f"{LOG} 루트 {p.root} · {ax} 권한 0700")
    cfg_p = ax / "config.json"
    want = build_config(project, facts or local_facts(p))
    try:
        cur = json.loads(_read(cfg_p) or "{}")
    except ValueError:
        cur = {}
    if config_view(cur) == config_view(want):
        print(f"{LOG} config.json 이미 같다 (project={project}) — 쓰지 않는다")
    else:
        _write_private(cfg_p, json.dumps(want, ensure_ascii=False, indent=2) + "\n", 0o600)
        print(f"{LOG} config.json 썼다 → {cfg_p} (project={project} · "
              f"task_queue={want['master']['services']['task_queue']})")

    # ── token ─────────────────────────────────────────────────
    from .. import auth as _auth
    try:
        tok = _auth.load_token(p.token_src)
    except Exception as ex:                                            # noqa: BLE001
        tok = ""
        bad += 1
        print(f"{LOG} [실패] requester 토큰 원천을 못 읽는다 — {str(ex).splitlines()[0]}")
    if tok:
        tok_p = ax / "token"
        if tok_p.is_file() and token_digest(_read(tok_p)) == token_digest(tok):
            os.chmod(tok_p, 0o600)
            print(f"{LOG} token 이미 같다 (sha256 {token_digest(tok)[:12]}) — 권한만 0600 확인")
        else:
            _write_private(tok_p, tok + "\n", 0o600)
            ok = token_digest(_read(tok_p)) == token_digest(tok)
            bad += 0 if ok else 1
            print(f"{LOG} token {'복사했다' if ok else '[실패] 복사 뒤 해시 불일치'} → {tok_p} "
                  f"(0600 · sha256 {token_digest(tok)[:12]})")
    del tok

    # ── Claude Code (user 스코프) ─────────────────────────────
    if stdio_matches(claude_user_get(_read(p.claude_json)), e):
        print(f"{LOG} claude: user 스코프 {SERVER} 이미 같다 — 건드리지 않는다")
    elif not shutil.which("claude"):
        bad += 1
        print(f"{LOG} [실패] claude: 실행 파일이 PATH 에 없다")
    else:
        bk = _backup(p.claude_json, stamp)
        print(f"{LOG} claude: ~/.claude.json 백업 → {bk or '(원본 없음)'}")
        rc, out = _run(["claude", "mcp", "remove", "-s", "user", SERVER])
        print(f"{LOG} claude: 기존 user 항목 제거 rc={rc} ({'없었다' if rc else '있었다'})")
        rc, out = _run(["claude", "mcp", "add-json", "-s", "user", SERVER,
                        json.dumps({"type": "stdio", **e}, ensure_ascii=False)])
        ok = rc == 0 and stdio_matches(claude_user_get(_read(p.claude_json)), e)
        bad += 0 if ok else 1
        print(f"{LOG} claude: add-json rc={rc} · ~/.claude.json 되읽기 "
              f"{'대조 통과' if ok else '[실패] 항목이 없거나 다르다 — ' + out.strip()[:160]}")

    # ── Claude 전체 도구 권한 (MCP 등록 파일과 별개인 settings.json) ──
    try:
        prev = _read(p.claude_settings)
        new = claude_permissions_text(prev)
        if new == prev:
            print(f"{LOG} claude 권한: 이미 같다 — 쓰지 않는다")
        else:
            bk = _backup(p.claude_settings, stamp)
            mode = (p.claude_settings.stat().st_mode & 0o777) if p.claude_settings.exists() else 0o600
            _write_private(p.claude_settings, new, mode)
            print(f"{LOG} claude 권한: 백업 {bk or '(원본 없음)'} · bypassPermissions 기록")
        ok = claude_all_approved(_read(p.claude_settings))
        bad += 0 if ok else 1
        print(f"{LOG} claude 권한: 파일 되읽기 {'대조 통과' if ok else '[실패] 모드 불일치'}")
    except MasterLocalError as ex:
        bad += 1
        print(f"{LOG} [실패] claude 권한: {ex}")

    # ── Codex (~/.codex/config.toml 관리 블록) ─────────────────
    try:
        approve = all_client_tools()
        prev = _read(p.codex_toml)
        new, removed = codex_text(prev, e, approve)
        if new == prev:
            print(f"{LOG} codex: config.toml 이미 같다 — 쓰지 않는다")
        else:
            bk = _backup(p.codex_toml, stamp)
            mode = (p.codex_toml.stat().st_mode & 0o777) if p.codex_toml.exists() else 0o600
            _write_private(p.codex_toml, new, mode)
            print(f"{LOG} codex: config.toml 백업 → {bk or '(원본 없음)'}")
            print(f"{LOG} codex: 걷은 것 — {'; '.join(removed) or '없음'} · 관리 블록 기록 "
                  f"(approve {len(approve)}개)")
        ok, why = codex_get_matches(codex_get_live(), e)
        bad += 0 if ok else 1
        print(f"{LOG} codex: codex mcp get 되읽기 {'대조 통과' if ok else '[실패] ' + why}")
        ok = codex_all_approved(_read(p.codex_toml))
        bad += 0 if ok else 1
        print(f"{LOG} codex 권한: 파일 되읽기 {'대조 통과' if ok else '[실패] 허용 정책 불일치'}")
    except MasterLocalError as ex:
        bad += 1
        print(f"{LOG} [실패] codex: {ex}")

    # ── agy (~/.gemini/config/mcp_config.json) ────────────────
    try:
        prev = _read(p.agy_json)
        new = agy_text(prev, e)
        if prev == new:
            print(f"{LOG} agy: mcp_config.json 이미 같다 — 쓰지 않는다")
        else:
            bk = _backup(p.agy_json, stamp)
            mode = (p.agy_json.stat().st_mode & 0o777) if p.agy_json.exists() else 0o644
            _write_private(p.agy_json, new, mode)
            print(f"{LOG} agy: mcp_config.json 백업 → {bk or '(원본 없음)'} · {SERVER} 병합 기록")
        ok = stdio_matches(agy_get(_read(p.agy_json)), e)
        bad += 0 if ok else 1
        print(f"{LOG} agy: 파일 되읽기 {'대조 통과' if ok else '[실패] 항목이 없거나 다르다'}")
    except MasterLocalError as ex:
        bad += 1
        print(f"{LOG} [실패] agy: {ex}")

    # ── agy ax-projects (`#920`) — 토큰이 들어가므로 파일을 0600 으로 ─────
    if p.projects_token is not None:
        try:
            url = projects_mcp_url()
            token = p.projects_token.read_text(encoding="utf-8").strip()
            prev = _read(p.agy_json)
            new = agy_projects_text(prev, url, token)
            if prev != new:
                bk = _backup(p.agy_json, stamp)
                _write_private(p.agy_json, new, 0o600)
                print(f"{LOG} agy: {AGY_PROJECTS} 병합 기록 · 백업 {bk or '(원본 없음)'} · 권한 0600")
            else:
                os.chmod(p.agy_json, 0o600)
                print(f"{LOG} agy: {AGY_PROJECTS} 이미 같다 — 권한만 0600 으로 확인")
            ok = agy_projects_matches(_read(p.agy_json), url, token)
            bad += 0 if ok else 1
            print(f"{LOG} agy: {AGY_PROJECTS} 되읽기 {'대조 통과' if ok else '[실패] 항목이 없거나 다르다'}")
        except (OSError, MasterLocalError) as ex:
            bad += 1
            print(f"{LOG} [실패] agy {AGY_PROJECTS}: {type(ex).__name__}")

    # ── agy 헤드리스 권한 (~/.gemini/antigravity-cli/settings.json) ──
    try:
        approve = all_client_tools()
        prev = _read(p.agy_settings)
        new, added = agy_permissions_text(prev, approve, extra_commands=AGY_BASE_COMMANDS)
        if not added:
            print(f"{LOG} agy 권한: 전체 도구 {len(approve)}개 및 기본 명령 이미 허용 — 쓰지 않는다")
        else:
            bk = _backup(p.agy_settings, stamp)
            mode = (p.agy_settings.stat().st_mode & 0o777) if p.agy_settings.exists() else 0o644
            _write_private(p.agy_settings, new, mode)
            print(f"{LOG} agy 권한: settings.json 백업 → {bk or '(원본 없음)'} · 더함 — {', '.join(added)}")
        ok = set(approve).issubset(set(agy_approvals(_read(p.agy_settings))))
        bad += 0 if ok else 1
        print(f"{LOG} agy 권한: 파일 되읽기 {'대조 통과' if ok else '[실패] 허용 목록이 다르다'}")
    except MasterLocalError as ex:
        bad += 1
        print(f"{LOG} [실패] agy 권한: {ex}")

    if p.legacy_root.exists():
        print(f"{LOG} [주의] 손으로 만든 옛 루트 {p.legacy_root} 가 남아 있다 — 지우지 않았다(사람이 정한다)")
    print(f"{LOG} {'완료' if not bad else f'[실패] {bad}건'} — 다음: --check")
    return 1 if bad else 0


def stdio_smoke(e: dict, tool: str = "redmine_meta", timeout: int = 60) -> tuple:
    """등록된 기동 명령 그대로 MCP 를 띄워 **읽기 도구 한 번** 부른다 → `(ok, 요약)`.

    [중요] 요약에 응답 본문을 싣지 않는다 — 키 이름과 크기만. 쓰기 도구는 부르지 않는다.
    """
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "master-local-check", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": tool, "arguments": {}}}]
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    try:
        r = subprocess.run([e["command"], *e["args"]], input=stdin, capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as ex:
        return False, f"기동 실패 — {type(ex).__name__}"
    resp = {}
    for line in (r.stdout or "").splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict) and "id" in m:
            resp[m["id"]] = m
    tools = [t.get("name") for t in ((resp.get(2) or {}).get("result") or {}).get("tools") or []]
    res = (resp.get(3) or {}).get("result") or {}
    text = "".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
    if not res or res.get("isError"):
        return False, f"{tool} 오류 — {text.splitlines()[0][:160] if text else (r.stderr or '응답 없음')[:160]}"
    try:
        body = json.loads(text)
    except ValueError:
        body = {}
    if isinstance(body, dict) and body.get("error"):
        return False, f"{tool} 응답 error — {str(body['error'])[:160]}"
    keys = sorted(body)[:6] if isinstance(body, dict) else []
    return True, f"tools {len(tools)}개 · {tool} 응답 키 {keys}"


def check(p: Paths, project: str, *, smoke: bool = True) -> int:
    """항목마다 OK/FAIL 한 줄. FAIL 이 하나라도 있으면 rc=1."""
    e = entry_for(p)
    rows: list = []

    def row(name: str, ok: bool, note: str = "") -> None:
        rows.append(ok)
        print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" — {note}" if note else ""))

    st = p.root.stat().st_mode & 0o777 if p.root.is_dir() else None
    row("root", st == 0o700, f"{p.root} " + (oct(st) if st is not None else "없음"))
    try:
        cur = config_view(json.loads(_read(p.root / ".ax" / "config.json") or "{}"))
    except ValueError:
        cur = {}
    want_ok = (cur.get("project") == project and cur.get("host") == bundle.MASTER_HOST
               and cur.get("task_queue") == bundle.SERVICES["task_queue"]
               and cur.get("projects") == bundle.SERVICES["projects"])
    row("config.json", want_ok, f"project={cur.get('project')} (마운트 {project or '없음'})"
        + ("" if want_ok else " — 다시 --apply"))
    src, dst, err = _token_state(p)
    tp = p.root / ".ax" / "token"
    tmode = tp.stat().st_mode & 0o777 if tp.is_file() else None
    row("token", bool(src) and src == dst and tmode == 0o600,
        f"원천 오류: {err}" if err else
        f"sha256 원천 {src[:12]} · 루트 {dst[:12] or '없음'} · 권한 {oct(tmode) if tmode else '없음'}")
    row("claude(user)", stdio_matches(claude_user_get(_read(p.claude_json)), e),
        f"{p.claude_json} mcpServers.{SERVER}")
    row("claude approvals", claude_all_approved(_read(p.claude_settings)),
        "permissions.defaultMode=bypassPermissions")
    ok, why = codex_get_matches(codex_get_live(), e)
    row("codex", ok, why or "codex mcp get --json 대조")
    try:
        appr = codex_approvals(_read(p.codex_toml))
        row("codex approvals", codex_all_approved(_read(p.codex_toml)), f"approve={list(appr)}")
    except Exception as ex:                                            # noqa: BLE001
        row("codex approvals", False, f"config.toml 파싱 실패 — {ex}")
    row("agy", stdio_matches(agy_get(_read(p.agy_json)), e), f"{p.agy_json} mcpServers.{SERVER}")
    if p.projects_token is not None:                       # `#920`
        try:
            url = projects_mcp_url()
            same = agy_projects_matches(_read(p.agy_json), url,
                                        p.projects_token.read_text(encoding="utf-8").strip())
            mode = p.agy_json.stat().st_mode & 0o777
            row(f"agy {AGY_PROJECTS}", same and mode == 0o600, f"{url} · 권한 {oct(mode)}")
        except OSError as ex:
            row(f"agy {AGY_PROJECTS}", False, type(ex).__name__)
    appr = agy_approvals(_read(p.agy_settings))
    row("agy approvals", set(all_client_tools()).issubset(set(appr)), f"allow={list(appr)}")
    rc, out = _run(["agy", "mcp", "list"], timeout=30)
    row("agy mcp list", rc == 0 and SERVER in out, f"rc={rc}")
    if smoke:
        ok, note = stdio_smoke(e)
        row("stdio 실측(redmine_meta)", ok, note)
    if p.legacy_root.exists():
        print(f"INFO 옛 손 루트 {p.legacy_root} 가 남아 있다 — 지우지 않는다(사람이 정한다)")
    bad = rows.count(False)
    print(f"{LOG} {'OK' if not bad else 'FAIL'} {len(rows) - bad}/{len(rows)}")
    return 1 if bad else 0
