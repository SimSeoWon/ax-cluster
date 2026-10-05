"""대화 세션 수집기 (`#713` ②, 2026-10-03 · 원본 복사 2026-10-04 · agy `#748` 2026-10-05)
— Claude Code·Codex 세션 jsonl · Antigravity(agy) 대화 `transcript.jsonl`.

🔴 [중요] **왜 지금 있나.** 지휘 세션(마스터)·요청자 세션(`.33`)의 비용은 어디에도 집계되지 않는다.
   그런데 두 도구는 **이미 세션마다 사용량을 로컬에 남긴다** — 새 기록기를 심을 필요가 없다
   (사용자 결정 2026-10-03: *".33 도 로컬에 저장해뒀다가 나중에 가져오는건 어때?"*).
   🔴 다만 Claude Code 는 기본 `cleanupPeriodDays`=30 으로 **30일 지난 기록을 지운다** — `.33` 의
   가장 오래된 기록이 정확히 30일 전이었다(실측 2026-10-03). 그래서 **주기적으로** 가져와 적립한다.

🔴 [중요] **원본을 그대로 복사한다** (사용자 결정 2026-10-04: *"다 내 컴퓨터니 그대로 복사해와"*).
   종전 규칙 「숫자만 남긴다」는 **폐기됐다** — 목적이 토큰 집계에서 **나중의 대화 분석**까지로
   넓어졌다. 마스킹하지 않고 바이트 그대로 둔다:

       ~/ax-state/usage/raw/<프로젝트|_unassigned>/<host|local>/<claude|codex|agy>/<원래 상대 경로>
       ~/ax-state/usage/raw/index.jsonl   파일마다 project·work_id·task_id·host·tool·origin·
                                          size·mtime·sha256·collected_at (원자적 통째 교체)

   `<원래 상대 경로>` 는 `~/.claude` · `~/.codex` · `~/.gemini/antigravity-cli` 기준이다
   (`projects/…` · `sessions/…` · `brain/<대화 id>/.system_generated/logs/transcript.jsonl`).
   [중요] **프로젝트는 세션의 cwd 로만 정한다** — 그 기계의 등록 작업장 체크아웃 경로
   (`<프로젝트>/config.yaml` `workshops.<host>.path`) 아래면 그 프로젝트, 아니면 `_unassigned`.
   **활성 프로젝트로 떨어뜨리지 않는다.** [주의] 마스터(`local`)는 등록 작업장이 아니라서
   `MASTER_CHECKOUTS` 로 따로 잇는다(사용자 결정 2026-10-04: cwd `~/ax-cluster` → AXCluster).
   그 밖의 마스터 세션(`~` 등)은 `_unassigned` 다. task_id 는 cwd 가 `<체크아웃>/.ax/work/<task_id>` 아래일 때만,
   work_id 는 그 task_id 를 큐 파일에서 찾았을 때만 채운다.
[중요] **원격에는 아무것도 쓰지 않는다** — 목록(크기·mtime)을 읽고 `tar` 스트림으로 읽기만 한다.
   지우지도 옮기지도 않는다(`.33` 은 사람의 메인 PC — 손님 규칙: 읽기 전용). 원격 삭제는
   **구현하지 않는다.** 원격에서 사라진 파일(30일 정리)의 사본과 색인 줄은 보존 기간까지 남는다.
🔴 [중요] **마스터 사본에도 보존 기간이 있다** (사용자 결정 2026-10-04). 루트 `projects.yaml` 의
   `usage.raw_retention_days`(없으면 30). 색인 `mtime`(세션 파일의 마지막 수정)이 그보다 오래된
   **마스터의 원본 사본과 그 색인 줄만** 지운다(`prune_raw`). **숫자 스냅샷은 남긴다** — 화면의 지난
   기록은 그대로다. **워커는 건드리지 않는다.** 그리고 기준보다 오래된 원격 파일은 **다시 받지 않고
   스냅샷도 다시 만들지 않는다** — 목록을 색인과 비교하기 전에 mtime 으로 거른다. 정리는 수집마다
   (`collect_all` — CLI·화면 열기 트리거 둘 다) 잠금 아래에서 먼저 돈다. 설정이 잘못됐으면 그 실행의
   정리와 거름을 건너뛰고 수집은 계속한다(삭제는 되돌릴 수 없다 — 기본값으로 지우지 않는다).
[중요] **증분이다.** 원격 목록의 크기+mtime 이 색인과 같으면 건너뛰고, 다르면(자라는 세션) 그 파일을
   **통째로** 다시 받아 tmp→replace 로 바꾼다. 받을 파일만 이름 목록으로 `tar -T -` 에 stdin 으로 준다
   (윈도우 bsdtar·리눅스 GNU tar 모두 실측 2026-10-04 — 명령줄 길이 한계를 피한다).
[중요] **토큰 숫자는 원본 사본에서 만든다.** 숫자 스냅샷(`DEFAULT_STORE`, `usage_dashboard` 가 읽는다)은
   그대로 두되, 복사한 원본을 `parse_claude`/`parse_codex` 로 다시 읽어 프로젝트와 함께 적는다.
   세션 하나 = 스냅샷 하나로 통째 덮어쓰므로 멱등이다.
[주의] **표시는 토큰만**(사용자 결정) — 이 기록에 금액 칸은 없다. CLI 구독은 금액을 모른다.

중복 규칙 (실측):
- Claude: 한 응답이 콘텐츠 블록마다 **같은 `message.id`·같은 usage** 로 여러 줄 찍힌다 → id 로 한 번만
- Codex: `token_count` 이벤트가 같은 누적값으로 **반복**될 수 있다 → `total_token_usage` 가 바뀔 때만
  그 턴의 `last_token_usage` 를 센다
- agy: 대화 폴더에 `transcript.jsonl` 과 `transcript_full.jsonl`·`chunks/` 가 같이 있다 → **`transcript.jsonl`
  하나만** 받는다. 사용량은 `PLANNER_RESPONSE` 줄의 `input_tokens`(캐시 제외)·`cache_read_tokens`·
  `output_tokens` 다(실측 2026-10-05: 캐시 16,284 일 때 입력 5,083). 모델 키는 없고, 사용자가 모델을
  고르면 본문에 ``The user changed setting `Model Selection` from X to Y.`` 가 찍힌다 → 그 Y 를 이후 턴에 쓴다.
  cwd 키도 없다 → 첫 `run_command` 호출의 `Cwd` 인자를 쓴다. 명령을 안 돌린 대화(헤드리스 `agy -p` 대부분 —
  실측 255 중 219)는 cwd 가 비어 `_unassigned` 다. 그 실행은 작업 실행 기록(`usage_log`)에도 남는다.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STORE = Path.home() / "ax-state" / "usage" / "sessions"
DEFAULT_RAW = Path.home() / "ax-state" / "usage" / "raw"
UNASSIGNED = "_unassigned"
INDEX_NAME = "index.jsonl"
LOCK_NAME = ".lock"
STAMP_NAME = ".last_refresh"
REFRESH_MIN_INTERVAL = 300          # 화면 열기 트리거의 최소 간격(초)

# 원격 기계 → (ssh 대상, 윈도우인가). 마스터 자신은 "local".
HOSTS = {
    "192.168.0.33": ("user@192.168.0.33", True),
    "192.168.0.2": ("janus@192.168.0.2", True),
    "192.168.0.43": ("sim@192.168.0.43", False),
}
# 마스터(`local`) 체크아웃 → 프로젝트. 레지스트리의 workshops 에는 마스터가 없다(작업장이 아니다).
# [중요] 사용자 결정 2026-10-04: *"마스터 세션은 ~/ax-cluster 면 AXCluster 로 귀속해"*.
#    레지스트리에 그 프로젝트가 없으면 잇지 않는다 — 없는 프로젝트를 만들어 넣지 않는다.
MASTER_CHECKOUTS = ((str(Path.home() / "ax-cluster"), "AXCluster"),)
SOURCES = (("claude", ".claude", "projects"), ("codex", ".codex", "sessions"),
           ("agy", ".gemini/antigravity-cli", "brain"))
# 도구별로 받을 파일 이름 — agy 는 대화 폴더의 `transcript.jsonl` 만(같은 폴더의 `_full`·조각은 중복이다)
_NAME = {"claude": "*.jsonl", "codex": "*.jsonl", "agy": "transcript.jsonl"}
_DAY = 86400
_FROM_REGISTRY = object()           # collect_all: 보존 기간을 레지스트리에서 읽는다(기본)
_BASE = {tool: base for tool, base, _ in SOURCES}
_SSH = ("ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes")


def _log(msg: str) -> None:
    print(f"[session-usage] {msg}", file=sys.stderr, flush=True)


@dataclass
class Session:
    tool: str
    session_id: str
    records: list = field(default_factory=list)


def parse_claude(lines) -> Session | None:
    """Claude Code 세션 jsonl → 응답(message.id)마다 한 레코드."""
    seen: set = set()
    sid, recs = "", []
    for raw in lines:
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if d.get("type") != "assistant":
            continue
        m = d.get("message") or {}
        u = m.get("usage") or {}
        mid = m.get("id") or d.get("requestId") or ""
        if not u or not mid or mid in seen:
            continue
        seen.add(mid)
        sid = sid or d.get("sessionId") or ""
        recs.append({
            "ts": d.get("timestamp", ""), "model": m.get("model", ""),
            "input": int(u.get("input_tokens") or 0),
            "output": int(u.get("output_tokens") or 0),
            "cache_read": int(u.get("cache_read_input_tokens") or 0),
            "cache_create": int(u.get("cache_creation_input_tokens") or 0),
            "reasoning": int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0),
        })
    return Session("claude", sid, recs) if recs else None


def parse_codex(lines) -> Session | None:
    """Codex 세션 jsonl → 누적값이 바뀐 `token_count` 마다 한 레코드(그 턴의 사용량)."""
    sid, model, prev, recs = "", "", None, []
    for raw in lines:
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            continue
        p = d.get("payload") or {}
        t = d.get("type")
        if t == "session_meta":
            sid = sid or p.get("id") or p.get("session_id") or ""
        elif t == "turn_context":
            model = p.get("model") or model
        elif t == "event_msg" and p.get("type") == "token_count":
            info = p.get("info") or {}
            total, last = info.get("total_token_usage"), info.get("last_token_usage")
            if not total or not last or total == prev:
                continue
            prev = total
            recs.append({
                "ts": d.get("timestamp", ""), "model": model,
                "input": int(last.get("input_tokens") or 0),
                "output": int(last.get("output_tokens") or 0),
                "cache_read": int(last.get("cached_input_tokens") or 0),
                "cache_create": int(last.get("cache_write_input_tokens") or 0),
                "reasoning": int(last.get("reasoning_output_tokens") or 0),
            })
    return Session("codex", sid, recs) if recs else None


_AGY_MODEL = re.compile(r"setting `Model Selection` from .*? to (.+?)\.(?:\s|$)")


def parse_antigravity(lines) -> Session | None:
    """agy `transcript.jsonl` → `PLANNER_RESPONSE` 마다 한 레코드. 세션 id 는 폴더 이름(원본 경로)이 맡는다."""
    model, recs = "", []
    for raw in lines:
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(d, dict):
            continue
        content = d.get("content")
        if isinstance(content, str) and "Model Selection" in content:
            m = _AGY_MODEL.search(content)
            if m:
                model = m.group(1).strip()
        if d.get("type") != "PLANNER_RESPONSE" or "input_tokens" not in d:
            continue
        try:
            inp, out, cache = (int(d.get(k) or 0) for k in
                               ("input_tokens", "output_tokens", "cache_read_tokens"))
        except (ValueError, TypeError):
            # R56-2: 숫자가 아닌 값은 그 줄만 버린다 — 0 으로 적지 않고 세션 전체도 죽이지 않는다
            continue
        recs.append({
            "ts": d.get("created_at", ""), "model": model,
            "input": inp, "output": out, "cache_read": cache,
            "cache_create": 0, "reasoning": 0,
        })
    return Session("agy", "", recs) if recs else None


PARSERS = {"claude": parse_claude, "codex": parse_codex, "agy": parse_antigravity}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _store(store: Path, host: str, s: Session, origin: str, meta: dict | None = None) -> Path:
    # [주의] 이름은 **원본 경로**에서 만든다 — Claude 서브에이전트 기록은 부모와 같은 `sessionId` 를
    #    써서, 세션 id 로 이름을 지으면 서로 덮는다(실측 `.33`: 306 세션 → 297 파일).
    name = origin.replace("\\", "/").removesuffix(".jsonl").replace("/", "__")
    out = store / host / s.tool / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    meta = meta or {}
    tmp.write_text(json.dumps({"host": host, "tool": s.tool, "session_id": s.session_id,
                               "origin": origin, "collected_at": _now(),
                               "project": meta.get("project"), "work_id": meta.get("work_id"),
                               "task_id": meta.get("task_id"),
                               "records": s.records}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)                       # 원자적 교체 — 반쯤 쓴 파일을 남기지 않는다
    return out


# ---------------------------------------------------------------- 귀속 (cwd → 프로젝트)

def _norm(path: str, windows: bool) -> str:
    p = (path or "").replace("\\", "/").rstrip("/")
    return p.casefold() if windows else p


def workshop_paths(projects_root: Path | None = None) -> dict[str, list[tuple[str, str]]]:
    """등록 레지스트리에서 host → [(체크아웃 경로, 프로젝트)] (긴 경로 먼저).

    [주의] 레지스트리를 못 읽으면 **예외를 그대로 올린다** — 빈 표로 진행하면 모든 파일이
    `_unassigned` 로 굳는다(재귀속은 `--reparse` 를 따로 돌려야 한다). fail-closed.
    """
    from ..projects.config import ConfigError, Registry
    reg = Registry.load(projects_root)
    out: dict[str, list[tuple[str, str]]] = {}
    for name in reg.names:
        try:
            shops = reg.config_of(name).workshops
        except ConfigError as e:
            _log(f"[주의] 프로젝트 설정 읽기 실패 {name}: {e}")
            continue
        for host, shop in shops.items():
            if shop.path:
                out.setdefault(host, []).append((shop.path, name))
    for checkout, name in MASTER_CHECKOUTS:
        if name in reg.names:
            out.setdefault("local", []).append((checkout, name))
        else:
            _log(f"[주의] 마스터 귀속 대상 {name} 이 레지스트리에 없다 — {checkout} 세션은 _unassigned")
    for rows in out.values():
        rows.sort(key=lambda row: len(row[0]), reverse=True)
    return out


def session_cwd(path: Path, tool: str, max_lines: int = 5000) -> str:
    """원본 사본에서 세션의 cwd — Codex 는 `session_meta.payload.cwd`, Claude 는 첫 `cwd` 필드,
    agy 는 첫 `run_command` 의 `Cwd` 인자(값이 따옴표째 실린다)."""
    try:
        with path.open("rb") as fh:
            for i, raw in enumerate(fh):
                if i >= max_lines:
                    break
                try:
                    d = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(d, dict):
                    continue
                if tool == "codex":
                    if d.get("type") == "session_meta":
                        cwd = (d.get("payload") or {}).get("cwd")
                        return cwd if isinstance(cwd, str) else ""
                elif tool == "agy":
                    for tc in d.get("tool_calls") or ():
                        args = tc.get("args") if isinstance(tc, dict) else None
                        if isinstance(args, dict) and tc.get("name") == "run_command":  # R56-1
                            cwd = args.get("Cwd")
                            cwd = cwd.strip().strip("\"'") if isinstance(cwd, str) else ""
                            if cwd:
                                return cwd
                elif isinstance(d.get("cwd"), str) and d["cwd"]:
                    return d["cwd"]
    except OSError as e:
        _log(f"[주의] cwd 읽기 실패: {type(e).__name__}")
    return ""


def attribute(cwd: str, host: str, shops: dict) -> tuple[str | None, str | None]:
    """(프로젝트, task_id). 그 host 의 등록 체크아웃 아래가 아니면 (None, None)."""
    windows = HOSTS.get(host, ("", False))[1]
    c = _norm(cwd, windows)
    if not c:
        return None, None
    for checkout, project in shops.get(host, ()):
        p = _norm(checkout, windows)
        if not p or not (c == p or c.startswith(p + "/")):
            continue
        rest = cwd.replace("\\", "/").rstrip("/")[len(p):].lstrip("/").split("/")
        task = rest[2] if len(rest) >= 3 and _norm(rest[0], windows) == ".ax" \
            and _norm(rest[1], windows) == "work" and rest[2] else None
        return project, task
    return None, None


def _queue_root(queue_root: Path | None) -> Path:
    return Path(queue_root) if queue_root is not None else \
        Path(os.environ.get("AX_TASK_QUEUE_ROOT") or Path.home() / "ax-state")


def work_of(task_id: str, queue_root: Path | None = None) -> str | None:
    """큐 파일(`<tasks>/<work_id>/<task_id>_*.md`, 보관 포함)에서 work_id. 없으면 None."""
    from ..task_queue.persistence import _read_md, _tasks_dir
    tasks = _tasks_dir(_queue_root(queue_root))
    if not task_id or not tasks.is_dir():
        return None
    try:
        for path in list(tasks.rglob(f"{task_id}_*.md")) + list(tasks.rglob(f"{task_id}.md")):
            meta, _ = _read_md(path)
            if str(meta.get("task_id") or "") == task_id and meta.get("work_id"):
                return str(meta["work_id"])
    except (OSError, ValueError) as e:
        _log(f"[주의] work_id 조회 실패 {task_id}: {type(e).__name__}")
    return None


# ---------------------------------------------------------------- 색인

def _key(host: str, tool: str, origin: str) -> str:
    return f"{host}\t{tool}\t{origin}"


def load_index(raw_root: Path) -> dict[str, dict]:
    path = Path(raw_root) / INDEX_NAME
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            out[_key(e["host"], e["tool"], e["origin"])] = e
        except (ValueError, KeyError, TypeError):
            _log("[주의] 색인에 읽지 못한 줄이 있다 — 그 파일은 다시 받는다")
    return out


def save_index(raw_root: Path, index: dict[str, dict]) -> None:
    path = Path(raw_root) / INDEX_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(index[k], ensure_ascii=False) + "\n" for k in sorted(index)),
                   encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- 목록·전송

# (tool, origin, size, mtime) — origin 은 `~/.claude`·`~/.codex` 기준 상대 경로(`/` 구분)
Entry = tuple


def list_local(home: Path | None = None) -> list[Entry]:
    home = home or Path.home()
    out = []
    for tool, base, sub in SOURCES:
        root = home / base / sub
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(_NAME[tool])):
            if p.is_file():
                st = p.stat()
                out.append((tool, f"{sub}/{p.relative_to(root).as_posix()}", st.st_size,
                            int(st.st_mtime)))
    return out


_PS_LIST = r"""$ErrorActionPreference='SilentlyContinue'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$ic=[Globalization.CultureInfo]::InvariantCulture
$ep=[datetime]'1970-01-01'
foreach($s in @('claude|.claude|projects|*.jsonl','codex|.codex|sessions|*.jsonl','agy|.gemini\antigravity-cli|brain|transcript.jsonl')){
 $t,$b,$d,$n=$s.Split('|')
 $r=Join-Path $env:USERPROFILE "$b\$d"
 if(Test-Path -LiteralPath $r){
  Get-ChildItem -LiteralPath $r -Recurse -File -Force -Filter $n | ForEach-Object {
   $rel=$_.FullName.Substring($r.Length+1).Replace('\','/')
   "$t`t$($_.Length)`t$((($_.LastWriteTimeUtc - $ep).TotalSeconds).ToString($ic))`t$d/$rel"
  }
 }
}"""
_SH_LIST = ("for s in 'claude:.claude:projects:*.jsonl' 'codex:.codex:sessions:*.jsonl' "
            "'agy:.gemini/antigravity-cli:brain:transcript.jsonl'; do "
            "t=${s%%:*}; r=${s#*:}; b=${r%%:*}; r=${r#*:}; d=${r%%:*}; n=${r#*:}; "
            '[ -d "$HOME/$b/$d" ] && find "$HOME/$b/$d" -type f -name "$n" '
            '-printf "$t\\t%s\\t%T@\\t$d/%P\\n"; done; true')


def parse_listing(text: str) -> list[Entry]:
    out = []
    for line in text.splitlines():
        parts = line.rstrip("\r").split("\t")
        if len(parts) != 4 or parts[0] not in _BASE:
            continue
        try:
            out.append((parts[0], parts[3], int(parts[1]), int(float(parts[2]))))
        except ValueError:
            continue
    return out


def list_remote(host: str) -> list[Entry]:
    """원격 목록(크기·mtime). 읽기만 한다. 실패하면 RuntimeError."""
    target, windows = HOSTS[host]
    if windows:
        enc = base64.b64encode(_PS_LIST.encode("utf-16-le")).decode()
        cmd = f"powershell -NoProfile -NonInteractive -EncodedCommand {enc}"
    else:
        cmd = _SH_LIST
    p = subprocess.run([*_SSH, target, cmd], capture_output=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"목록 rc={p.returncode}: "
                           f"{p.stderr.decode('utf-8', 'replace').strip()[:160]}")
    return parse_listing(p.stdout.decode("utf-8", "replace"))


# 🔴 [주의] **원격 tar 에 주는 이름 목록(stdin)은 묶음당 8KB 이하로 자른다** (실측 2026-10-04 `.33`).
#    윈도우 OpenSSH + bsdtar 에서 이름 250개(22.7KB)를 한 번에 주자 tar 가 **출력 0 바이트로 멈췄다**
#    — 같은 250개를 50개씩 나누면 다 됐고, 190개(17.3KB)까지는 한 번에 됐다. 경계는 재지 않았다
#    (재는 동안 멈춘 tar.exe 가 사람 PC 에 남는다). 그래서 확인된 범위의 절반 아래로 둔다.
STDIN_BUDGET = 8000


def fetch_remote(host: str, tool: str, origins: list[str], *, timeout: float = 600):
    """원격 `<home>/<base>` 기준 이름 목록을 tar 로 받는다. yield (origin, 파일객체, mtime).

    [중요] 이름 목록은 **stdin** 으로 준다(`-T -`) — cmd 명령줄 8191자 한계를 피한다.
    원격에는 아무것도 쓰지 않는다. 그 사이 사라진 파일은 tar 가 rc≠0 으로 알리고 건너뛴다.
    """
    target, windows = HOSTS[host]
    base = _BASE[tool]
    remote = (f'tar -cf - -C "%USERPROFILE%\\{base.replace("/", chr(92))}" -T -' if windows
              else f'tar -cf - -C "$HOME/{base}" -T -')
    proc = subprocess.Popen([*_SSH, target, remote], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdin.write("".join(o + "\n" for o in origins).encode("utf-8"))
    proc.stdin.close()
    # stderr 가 차서 막히지 않게 따로 비운다
    err_chunks: list[bytes] = []

    def _drain() -> None:
        err_chunks.append(proc.stderr.read())

    drain = threading.Thread(target=_drain, daemon=True)
    drain.start()
    fired: list[bool] = []

    def _watchdog() -> None:
        # [중요] 멈춘 전송이 잠금을 영원히 쥐지 않게 — 마스터 쪽 ssh 만 끊는다(원격은 건드리지 않는다)
        fired.append(True)
        _log(f"[주의] {host} {tool} tar {int(timeout)}초 초과 — 마스터 쪽 ssh 를 끊는다")
        proc.kill()

    timer = threading.Timer(timeout, _watchdog)
    timer.daemon = True
    timer.start()
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
            for m in tf:
                if m.isfile():
                    fh = tf.extractfile(m)
                    if fh is not None:
                        yield m.name, fh, int(m.mtime)
    finally:
        timer.cancel()
        proc.stdout.close()
        rc = proc.wait()
        drain.join(timeout=5)
        if rc != 0:
            _log(f"{host} {tool} tar rc={rc} (사라진 파일이면 정상): "
                 f"{b''.join(err_chunks).decode('utf-8', 'replace').strip()[:160]}")


def fetch_local(tool: str, origins: list[str], home: Path | None = None):
    home = home or Path.home()
    for o in origins:
        p = home / _BASE[tool] / o
        try:
            fh = p.open("rb")
            mtime = int(p.stat().st_mtime)
        except OSError as e:
            _log(f"[주의] local 읽기 실패: {type(e).__name__}")
            continue
        yield o, fh, mtime


def _write_atomic(fh, dest: Path, mtime: int) -> tuple[int, str]:
    """스트림을 tmp 로 받고 sha256 을 세며 replace. 반환 (바이트, sha256)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h, n = hashlib.sha256(), 0
    with tmp.open("wb") as out:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            out.write(chunk)
            n += len(chunk)
    os.utime(tmp, (mtime, mtime))
    tmp.replace(dest)
    return n, h.hexdigest()


def _raw_rel(project: str | None, host: str, tool: str, origin: str) -> str:
    return f"{project or UNASSIGNED}/{host}/{tool}/{origin}"


def _safe_origin(origin: str) -> bool:
    parts = origin.replace("\\", "/").split("/")
    return bool(origin) and not origin.startswith("/") and ".." not in parts and ":" not in origin


def _snapshot(raw: Path, store: Path, host: str, tool: str, origin: str, meta: dict) -> int:
    with raw.open("rb") as fh:
        s = PARSERS[tool](fh.read().decode("utf-8", "replace").splitlines())
    if s is None:
        return 0
    _store(store, host, s, origin, meta)
    return len(s.records)


def _place(raw_root: Path, store: Path, host: str, tool: str, origin: str, tmp_path: Path,
           shops: dict, queue_root, index: dict, size: int, mtime: int, sha: str) -> dict:
    """받은 사본의 귀속을 정해 제자리에 두고 색인·스냅샷을 갱신한다."""
    cwd = session_cwd(tmp_path, tool)
    project, task = attribute(cwd, host, shops)
    work = work_of(task, queue_root) if task else None
    rel = _raw_rel(project, host, tool, origin)
    dest = raw_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(dest)
    old = index.get(_key(host, tool, origin))
    if old and old.get("raw") and old["raw"] != rel:
        # 귀속이 바뀌었다 — 마스터 쪽 옛 사본만 치운다(원격은 건드리지 않는다)
        (raw_root / old["raw"]).unlink(missing_ok=True)
    entry = {"project": project, "work_id": work, "task_id": task, "host": host, "tool": tool,
             "origin": origin, "raw": rel, "cwd": cwd, "size": size, "mtime": mtime,
             "sha256": sha, "collected_at": _now()}
    index[_key(host, tool, origin)] = entry
    _snapshot(dest, store, host, tool, origin, entry)
    return entry


def batches(origins: list[str], budget: int = STDIN_BUDGET):
    """이름 목록을 stdin 바이트 예산으로 자른다 — 위 `STDIN_BUDGET` 주석."""
    batch: list[str] = []
    size = 0
    for o in origins:
        n = len(o.encode("utf-8")) + 1
        if batch and size + n > budget:
            yield batch
            batch, size = [], 0
        batch.append(o)
        size += n
    if batch:
        yield batch


def _stream(host: str, tool: str, want: dict, fetcher):
    """받을 파일을 묶음마다 받아 하나의 스트림으로 잇는다."""
    for batch in batches(list(want)):
        if fetcher is not None:
            part = fetcher(host, tool, batch)
        elif host == "local":
            part = fetch_local(tool, batch)
        else:
            expected = sum(want[o][0] for o in batch)
            part = fetch_remote(host, tool, batch, timeout=60 + expected / 1_000_000)
        try:
            yield from part
        finally:
            close = getattr(part, "close", None)
            if close is not None:
                close()


def collect(host: str, *, raw_root: Path = DEFAULT_RAW, store: Path = DEFAULT_STORE,
            projects_root: Path | None = None, queue_root: Path | None = None,
            shops: dict | None = None, lister=None, fetcher=None,
            cutoff: float | None = None) -> dict:
    """한 기계의 두 도구 세션 원본을 증분 복사한다. 반환: 도구별 통계.

    `lister(host)->[Entry]` · `fetcher(host, tool, origins)->iter((origin, fh, mtime))` 는
    검사 주입용이다. 기본은 local 파일 / SSH 목록·tar.
    `cutoff`(epoch 초)가 있으면 mtime 이 그보다 오래된 목록 항목은 **색인과 비교하기 전에** 거른다 —
    보존 기간이 지나 지운 사본을 다시 받지 않고, 남은 스냅샷도 다시 만들지 않는다(`old` 로 센다).
    """
    raw_root, store = Path(raw_root), Path(store)
    if shops is None:
        shops = workshop_paths(projects_root)
    stats = {tool: {"listed": 0, "skipped": 0, "old": 0, "copied": 0, "bytes": 0, "errors": 0,
                    "error": "", "seconds": 0.0} for tool, _, _ in SOURCES}
    t0 = time.monotonic()
    try:
        if lister is not None:
            entries = lister(host)
        elif host == "local":
            entries = list_local()
        else:
            entries = list_remote(host)
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        msg = f"{type(e).__name__}: {e}"[:200]
        for tool in stats:
            stats[tool].update(error=msg, errors=1, seconds=round(time.monotonic() - t0, 1))
            _log(f"{host} {tool} — 목록 실패 · [주의] {msg}")
        return stats
    list_secs = time.monotonic() - t0
    index = load_index(raw_root)
    for tool, _, _ in SOURCES:
        t1 = time.monotonic()
        st = stats[tool]
        want: dict[str, tuple[int, int]] = {}
        for etool, origin, size, mtime in entries:
            if etool != tool:
                continue
            if not _safe_origin(origin):
                st["errors"] += 1
                _log(f"[주의] {host} {tool} 이상한 경로를 건너뛴다")
                continue
            st["listed"] += 1
            if cutoff is not None and mtime < cutoff:
                st["old"] += 1                   # 보존 기간 밖 — 받지 않는다(원격은 그대로 둔다)
                continue
            old = index.get(_key(host, tool, origin))
            if (old and old.get("size") == size and old.get("mtime") == mtime
                    and (raw_root / old.get("raw", "")).is_file()):
                st["skipped"] += 1
                continue
            want[origin] = (size, mtime)
        if want:
            stream = _stream(host, tool, want, fetcher)
            got: set[str] = set()
            staging = raw_root / ".staging" / host / tool
            try:
                for origin, fh, mtime in stream:
                    origin = origin.replace("\\", "/")
                    if origin not in want or not _safe_origin(origin):
                        continue
                    listed_size, listed_mtime = want[origin]
                    tmp_path = staging / origin
                    try:
                        with fh:
                            n, sha = _write_atomic(fh, tmp_path, mtime)
                        # [주의] 크기는 **실제 받은 바이트**, mtime 은 **목록 값** — 받는 사이 자랐으면
                        #    다음 목록과 어긋나 한 번 더 받는다(손해는 재전송뿐, 누락은 없다).
                        _place(raw_root, store, host, tool, origin, tmp_path, shops, queue_root,
                               index, n, listed_mtime, sha)
                        got.add(origin)
                        st["copied"] += 1
                        st["bytes"] += n
                    except (OSError, ValueError) as e:
                        st["errors"] += 1
                        _log(f"[주의] {host} {tool} 사본 실패: {type(e).__name__}: {e}"[:240])
            except (tarfile.TarError, OSError) as e:
                st["error"] = f"{type(e).__name__}: {e}"[:200]
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()                      # 원격 tar 프로세스를 그 자리에서 거둔다
            missing = len(want) - len(got)
            if missing:
                st["errors"] += missing
            shutil.rmtree(raw_root / ".staging" / host, ignore_errors=True)
            save_index(raw_root, index)          # 도구마다 저장 — 중간에 죽어도 받은 만큼은 남는다
        st["seconds"] = round(time.monotonic() - t1 + list_secs / len(SOURCES), 1)
        _log(f"{host} {tool} — 목록 {st['listed']} · 건너뜀 {st['skipped']}"
             f" · 기간 지남 {st['old']} · 복사 {st['copied']}"
             f" · {st['bytes']}바이트 · 오류 {st['errors']} · {st['seconds']}초"
             + (f" · [주의] {st['error']}" if st["error"] else ""))
    return stats


def _cutoff_of(days: int, now: float | None = None) -> float:
    return (time.time() if now is None else now) - days * _DAY


def prune_raw(raw_root: Path = DEFAULT_RAW, days: int = 30, *, now: float | None = None,
              dry_run: bool = False) -> dict:
    """보존 기간이 지난 **마스터의 원본 사본과 색인 줄**을 지운다. 반환: 통계.

    [중요] 기준은 색인 `mtime`(세션 파일의 마지막 수정, 원격 목록 값)이다 — 받은 시각이 아니다.
    숫자 스냅샷(`DEFAULT_STORE`)은 건드리지 않는다. 원격은 건드리지 않는다(원격 삭제는 없다).
    mtime 이 없거나 숫자가 아닌 줄은 **지우지 않는다** — 모르면 남긴다.
    `dry_run` 이면 세기만 하고 파일·색인을 바꾸지 않는다.
    """
    raw_root = Path(raw_root)
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError(f"보존 기간은 양의 정수여야 한다: {days!r}")
    cutoff = _cutoff_of(days, now)
    index = load_index(raw_root)
    stats = {"days": days, "cutoff": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cutoff)),
             "indexed": len(index), "pruned": 0, "bytes": 0, "missing": 0, "errors": 0,
             "dry_run": dry_run}
    root = raw_root.resolve()
    for key, e in list(index.items()):
        mtime = e.get("mtime")
        if isinstance(mtime, bool) or not isinstance(mtime, (int, float)) or mtime >= cutoff:
            continue
        rel = e.get("raw") or ""
        path = (raw_root / rel) if rel else None
        # [주의] 색인 값으로 경로를 만들므로 raw 루트 밖은 지우지 않는다
        if path is not None and root not in path.resolve().parents:
            stats["errors"] += 1
            _log("[주의] 보존 정리 — raw 루트 밖을 가리키는 색인 줄을 건너뛴다")
            continue
        try:
            size = path.stat().st_size if path is not None and path.is_file() else None
        except OSError:
            size = None
        if size is None:
            stats["missing"] += 1
        if not dry_run:
            if size is not None:
                try:
                    path.unlink()
                except OSError as e2:
                    stats["errors"] += 1
                    _log(f"[주의] 보존 정리 — 사본 삭제 실패: {type(e2).__name__}")
                    continue
                _prune_empty_dirs(path.parent, root)
            del index[key]
        stats["pruned"] += 1
        stats["bytes"] += size or 0
    if stats["pruned"] and not dry_run:
        save_index(raw_root, index)
    _log(f"보존 정리{' (시험 — 지우지 않음)' if dry_run else ''} — 기준 {days}일 · 기준일 {stats['cutoff']}"
         f" · 색인 {stats['indexed']} · 정리 {stats['pruned']} · {stats['bytes']}바이트"
         f" · 사본 없던 줄 {stats['missing']} · 오류 {stats['errors']}")
    return stats


def _prune_empty_dirs(start: Path, root: Path) -> None:
    """지운 사본의 빈 상위 디렉토리를 raw 루트 직전까지 치운다."""
    d = start
    while d.resolve() != root and root in d.resolve().parents:
        try:
            d.rmdir()
        except OSError:
            break                                # 비어 있지 않다 — 거기서 멈춘다
        d = d.parent


def retention_days(projects_root: Path | None = None) -> int | None:
    """레지스트리의 보존 기간(일). 설정이 잘못됐으면 None — **그 실행은 지우지도 거르지도 않는다**."""
    from ..projects.config import ConfigError, Registry
    try:
        return Registry.load(projects_root).raw_retention_days()
    except ConfigError as e:
        _log(f"[주의] 보존 기간을 정하지 못했다 — 이번 실행은 사본을 지우지 않는다: {e}"[:300])
        return None


def reparse(*, raw_root: Path = DEFAULT_RAW, store: Path = DEFAULT_STORE,
            projects_root: Path | None = None, queue_root: Path | None = None,
            shops: dict | None = None) -> dict:
    """전송 없이 색인의 모든 사본을 다시 귀속하고 스냅샷을 다시 만든다(파서·레지스트리 변경 뒤)."""
    raw_root, store = Path(raw_root), Path(store)
    if shops is None:
        shops = workshop_paths(projects_root)
    index = load_index(raw_root)
    n = moved = missing = 0
    for key, e in list(index.items()):
        src = raw_root / e.get("raw", "")
        if not src.is_file():
            missing += 1
            continue
        tmp = raw_root / ".staging" / "reparse" / e["origin"]
        tmp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, tmp)
        new = _place(raw_root, store, e["host"], e["tool"], e["origin"], tmp, shops, queue_root,
                     index, e["size"], e["mtime"], e["sha256"])
        moved += int(new["raw"] != e.get("raw"))
        n += 1
    shutil.rmtree(raw_root / ".staging" / "reparse", ignore_errors=True)
    save_index(raw_root, index)
    _log(f"재귀속 — 사본 {n} · 이동 {moved} · 사본 없음 {missing}")
    return {"files": n, "moved": moved, "missing": missing}


# ---------------------------------------------------------------- 잠금·화면 열기 트리거

class Busy(RuntimeError):
    """다른 수집이 진행 중이다."""


def _acquire(raw_root: Path):
    import fcntl
    raw_root.mkdir(parents=True, exist_ok=True)
    fd = os.open(raw_root / LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise Busy("다른 수집이 진행 중")
    return fd


def collect_all(hosts, *, raw_root: Path = DEFAULT_RAW, store: Path = DEFAULT_STORE,
                projects_root: Path | None = None, queue_root: Path | None = None,
                retention=_FROM_REGISTRY, now: float | None = None, **inject) -> dict:
    """여러 기계를 차례로 — 프로세스 간 잠금(`<raw>/.lock`) 아래에서 한 번에 하나.

    [중요] 수집 전에 보존 정리(`prune_raw`)를 먼저 돌리고, 같은 기준으로 오래된 목록 항목을 거른다.
    `retention` 은 기본이 레지스트리 값이고, 검사는 일수(int)나 None(정리·거름 끔)을 준다.
    """
    raw_root = Path(raw_root)
    fd = _acquire(raw_root)
    try:
        shops = inject.pop("shops", None)
        if shops is None:
            shops = workshop_paths(projects_root)
        days = retention_days(projects_root) if retention is _FROM_REGISTRY else retention
        cutoff = None
        if days is not None:
            prune_raw(raw_root, days, now=now)
            cutoff = _cutoff_of(days, now)
        res = {h: collect(h, raw_root=raw_root, store=store, queue_root=queue_root,
                          shops=shops, cutoff=cutoff, **inject) for h in hosts}
        if cutoff is not None:
            old = sum(v.get("old", 0) for r in res.values() for v in r.values())
            _log(f"보존 기간 지난 목록 항목 {old}개는 받지 않았다(기준 {days}일)")
        return res
    finally:
        os.close(fd)


_BG_LOCK = threading.Lock()


def _bg_run(hosts, raw_root: Path, store: Path) -> None:
    try:
        t0 = time.monotonic()
        collect_all(hosts, raw_root=raw_root, store=store)
        _log(f"화면 열기 수집 완료 · {round(time.monotonic() - t0, 1)}초")
    except Busy:
        _log("화면 열기 수집 건너뜀 — 다른 수집이 진행 중(잠금)")
    except Exception as e:                                  # noqa: BLE001 — 배경 스레드는 죽지 않는다
        _log(f"[주의] 화면 열기 수집 실패: {type(e).__name__}: {e}"[:240])
    finally:
        _BG_LOCK.release()


def refresh_in_background(*, hosts=None, raw_root: Path = DEFAULT_RAW,
                          store: Path = DEFAULT_STORE,
                          min_interval: float = REFRESH_MIN_INTERVAL, _thread=True) -> str:
    """`/usage` 화면 열기가 부르는 **비차단** 수집 트리거. 반환: started|interval|busy|error.

    🔴 [중요] **`/cluster` 의 「새로고침은 SSH 를 부르지 않는다」 규칙의 명시적 예외다**
       (사용자 제안 2026-10-04 — 화면을 열면 세션 기록을 가져온다). 그래서 둘로 조인다:
       ① 프로세스 안 잠금 + `<raw>/.lock` 로 **한 번에 하나** ② `<raw>/.last_refresh` 로
       **최소 간격**(기본 5분 · 실패한 실행도 간격을 먹는다). 응답은 SSH 를 기다리지 않는다 —
       데몬 스레드로 넘기고 바로 돌아온다. 이 함수는 예외를 올리지 않는다.
    """
    try:
        raw_root = Path(raw_root)
        stamp = raw_root / STAMP_NAME
        try:
            age = time.time() - stamp.stat().st_mtime
        except OSError:
            age = None
        if age is not None and age < min_interval:
            _log(f"화면 열기 수집 건너뜀 — 간격 {int(age)}초 < {int(min_interval)}초")
            return "interval"
        if not _BG_LOCK.acquire(blocking=False):
            _log("화면 열기 수집 건너뜀 — 이미 도는 중(프로세스 안 잠금)")
            return "busy"
        try:
            raw_root.mkdir(parents=True, exist_ok=True)
            stamp.touch()
            args = (list(hosts) if hosts else ["local", *HOSTS], raw_root, Path(store))
            if _thread:
                threading.Thread(target=_bg_run, args=args, daemon=True,
                                 name="session-usage-refresh").start()
            else:
                _bg_run(*args)
        except BaseException:
            if _BG_LOCK.locked():
                _BG_LOCK.release()
            raise
        _log("화면 열기 수집 시작 (배경)")
        return "started"
    except Exception as e:                                  # noqa: BLE001 — 화면 응답을 막지 않는다
        _log(f"[주의] 화면 열기 트리거 실패: {type(e).__name__}: {e}"[:240])
        return "error"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="대화 세션 원본 수집 (#713 ②) — 원본 증분 복사 + 토큰 스냅샷")
    ap.add_argument("hosts", nargs="*", default=["local"],
                    help="local · all · " + " · ".join(HOSTS))
    ap.add_argument("--raw-root", default=str(DEFAULT_RAW))
    ap.add_argument("--store", default=str(DEFAULT_STORE))
    ap.add_argument("--reparse", action="store_true",
                    help="전송 없이 색인의 사본을 다시 귀속하고 스냅샷을 다시 만든다")
    ap.add_argument("--prune", action="store_true",
                    help="전송 없이 보존 기간(projects.yaml usage.raw_retention_days)이 지난 "
                         "마스터 사본·색인 줄만 지운다. 스냅샷·워커는 그대로")
    ap.add_argument("--dry-run", action="store_true",
                    help="--prune 과 함께 — 지울 것만 세고 지우지 않는다")
    a = ap.parse_args(argv)
    if a.dry_run and not a.prune:
        ap.error("--dry-run 은 --prune 과 함께만 쓴다")
    if a.prune and a.reparse:
        ap.error("--prune 과 --reparse 는 따로 실행한다")
    hosts = ["local", *HOSTS] if a.hosts == ["all"] else a.hosts
    bad = [h for h in hosts if h != "local" and h not in HOSTS]
    if bad:
        ap.error(f"모르는 기계: {bad}")
    raw_root, store = Path(a.raw_root), Path(a.store)
    try:
        if a.prune:
            days = retention_days()
            if days is None:
                return 2                         # 설정이 잘못됐다 — 기본값으로 지우지 않는다
            fd = _acquire(raw_root)
            try:
                st = prune_raw(raw_root, days, dry_run=a.dry_run)
            finally:
                os.close(fd)
            return 1 if st["errors"] else 0
        if a.reparse:
            fd = _acquire(raw_root)
            try:
                reparse(raw_root=raw_root, store=store)
            finally:
                os.close(fd)
            return 0
        res = collect_all(hosts, raw_root=raw_root, store=store)
    except Busy:
        _log("[주의] 다른 수집이 진행 중이다 — 끝난 뒤 다시 실행")
        return 1
    except RuntimeError as e:
        # 레지스트리(AX_PROJECTS_ROOT)를 못 읽으면 귀속을 못 한다 — 전부 `_unassigned` 로 굳히지 않고 멈춘다
        _log(f"[주의] 수집 중단 — {type(e).__name__}: {e}"[:300])
        return 2
    failed = any(v["error"] for r in res.values() for v in r.values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
