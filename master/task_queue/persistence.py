import os
import sys
import json
import time
import shutil
import secrets
import threading
import subprocess
from pathlib import Path
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

# ─────────────────────────────────────────
# 경로·로깅
# ─────────────────────────────────────────

_tq_log_file = None
_tq_log_date = ""
_log_lock = threading.Lock()


STATE_ROOT_ENV = "AX_TASK_QUEUE_ROOT"


def _project_root() -> Path:
    """큐 상태(`<root>/.claude/tasks/`)가 놓일 루트. **명시적 설정만 받는다.**

    [중요] 원본(AgentTest)은 `Path(__file__).parent.parent.parent` 로 **파일 위치에서 역산**했다.
    exe 가 UE5 프로젝트 루트 안에 풀려 있다는 전제였는데, 마스터엔 UE5 프로젝트 루트가 없다.
    역산을 남겨두면 저장소 어딘가(`master/`의 부모 = `ax-cluster/`)에 큐 상태를 쓰게 된다.

    폴백을 두지 않고 **즉시 실패**시키는 이유: 루트를 잘못 잡으면 조용히 엉뚱한 디렉터리에
    상태가 쌓이고, 그건 재기동 후에야 "작업이 사라졌다"로 발견된다.

    `--serve`/CLI 경로는 루트를 인자로 받으므로 이 함수를 타지 않는다 — MCP stdio 모드 전용이다.
    """
    v = os.environ.get(STATE_ROOT_ENV)
    if not v:
        raise RuntimeError(
            f"{STATE_ROOT_ENV} 미설정 — 큐 상태 루트를 알 수 없다. "
            f"예: {STATE_ROOT_ENV}=/home/sim/ax-state (systemd 유닛의 Environment= 로 주입)")
    root = Path(v).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"{STATE_ROOT_ENV}={root} 가 디렉터리가 아니다")
    return root


def _tasks_dir(root: Path) -> Path:
    return root / ".claude" / "tasks"


def _archive_dir(root: Path) -> Path:
    return _tasks_dir(root) / "_archive"


def _log_dir(root: Path) -> Path:
    return root / ".claude" / "logs"


def _tq_log(msg: str, root: Path):
    global _tq_log_file, _tq_log_date
    with _log_lock:
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            if today != _tq_log_date:
                if _tq_log_file:
                    _tq_log_file.close()
                ld = _log_dir(root)
                ld.mkdir(parents=True, exist_ok=True)
                _tq_log_date = today
                _tq_log_file = open(ld / f"task_queue_{today}.log", 'a', encoding='utf-8')
            if _tq_log_file:
                _tq_log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
                _tq_log_file.flush()
        except Exception:
            pass


def _bootstrap_log_rotation(root: Path):
    """데몬 부팅 시 1회 호출 — 오늘 날짜 로그가 이미 있으면 _N 접미사로 rename.
    long-running 모드(--serve, MCP stdio)에서만 호출. 단발 CLI 는 스킵."""
    today = datetime.now().strftime('%Y-%m-%d')
    log_path = _log_dir(root) / f"task_queue_{today}.log"
    if not log_path.exists():
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        candidate = log_path.with_name(f"{log_path.stem}_{n}{log_path.suffix}")
        if not candidate.exists():
            try:
                log_path.rename(candidate)
            except (FileNotFoundError, OSError):
                pass
            return
        n += 1


# ─────────────────────────────────────────
# Frontmatter — 제한된 YAML 부분집합 (우리 스키마 전용)
# ─────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def _gen_task_id() -> str:
    return secrets.token_hex(4)  # 8 hex chars


def _slugify(s: str) -> str:
    """ASCII-only slug — branch/디렉토리명 안전성 확보.

    [중요] **비-ASCII 가 버려지면 해시를 붙인다 (2026-08-08 수정).**

    원본은 비-ASCII 를 그냥 버리고 결과가 비면 `"work"` 로 폴백했다. 팀이 영문 제목을
    쓰던 환경에서는 드러나지 않았지만, **한국어 제목은 전부 `"work"` 로 떨어진다** —
    실측: `'워크플로우 복구'` · `'골조 전달'` · `'매니저 초기화'` → 전부 `'work'`.

    slug 는 **중복 검출 키**다(`find_active_duplicates`). 그래서 이 저장소에서는
    **두 번째 한글 일감이 항상 첫 번째의 중복으로 거부된다.** 워크플로우가 시작부터 막힌다.

    고친 방식: 버려진 내용이 있으면 정규화한 원문의 해시를 덧붙인다.

    - **같은 제목 → 같은 slug** — 중복 검출은 그대로 동작한다 (이게 요점이다)
    - **다른 제목 → 다른 slug** — 한글끼리도 갈린다
    - **순수 ASCII 제목은 그대로** — 기존 work id 와 호환된다
    """
    out = []
    for c in s.lower():
        if c.isascii() and c.isalnum():
            out.append(c)
        elif c in " -_":
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")

    # 버려진 알파벳/숫자가 있었는가 (기호·공백은 원래 구분자라 셈하지 않는다).
    dropped = any(c.isalnum() and not c.isascii() for c in s)
    if not dropped:
        return slug or "work"
    norm = " ".join(s.split()).casefold()
    h = hashlib.md5(norm.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{h}" if slug else f"work_{h}"


def _gen_work_id(slug: str = "") -> str:
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    return f"{ts}_{_slugify(slug)}" if slug else ts


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """`---\\n<yaml>\\n---\\n<body>` 에서 (meta, body) 분리."""
    if not (text.startswith('---\n') or text.startswith('---\r\n')):
        return {}, text
    # 시작 마커 길이
    start = 4 if text.startswith('---\n') else 5
    body_start = -1
    fm_text = ""
    for marker in ('\n---\n', '\r\n---\r\n', '\n---\r\n', '\r\n---\n'):
        idx = text.find(marker, start)
        if idx >= 0:
            fm_text = text[start:idx]
            body_start = idx + len(marker)
            break
    if body_start < 0:
        return {}, text
    return _parse_yaml_simple(fm_text), text[body_start:]


def _parse_yaml_simple(text: str) -> dict:
    """제한적 YAML 파서 — 우리 스키마 전용.

    지원: top-level scalars, 리스트(- ...), 1-depth nested dict, inline list/dict.
    """
    out: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            i += 1
            continue
        if line.startswith(' ') or line.startswith('\t'):
            i += 1
            continue
        if ':' not in line:
            i += 1
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if val == '':
            # 다음 라인이 들여쓰기 리스트 또는 dict
            items: list = []
            nested: dict = {}
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or nxt.lstrip().startswith('#'):
                    j += 1
                    continue
                stripped = nxt.lstrip()
                if not (nxt.startswith(' ') or nxt.startswith('\t')) and not stripped.startswith('-'):
                    break
                if stripped.startswith('- '):
                    items.append(_parse_scalar(stripped[2:].strip()))
                    j += 1
                elif stripped.startswith('-'):
                    items.append(_parse_scalar(stripped[1:].strip()))
                    j += 1
                elif ':' in stripped:
                    nk, _, nv = stripped.partition(':')
                    nested[nk.strip()] = _parse_scalar(nv.strip())
                    j += 1
                else:
                    break
            if items:
                out[key] = items
            elif nested:
                out[key] = nested
            else:
                out[key] = None
            i = j
        elif val.startswith('[') and val.endswith(']'):
            inner = val[1:-1].strip()
            out[key] = [_parse_scalar(x.strip()) for x in inner.split(',')] if inner else []
            i += 1
        elif val.startswith('{') and val.endswith('}'):
            try:
                out[key] = json.loads(val)
            except Exception:
                out[key] = {}
            i += 1
        else:
            out[key] = _parse_scalar(val)
            i += 1
    return out


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if s == '' or s.lower() in ('null', '~'):
        return None
    if s.lower() == 'true':
        return True
    if s.lower() == 'false':
        return False
    if s.lstrip('-').isdigit():
        try:
            return int(s)
        except Exception:
            pass
    if (len(s) >= 2 and s[0] == s[-1] and s[0] in '"\''):
        return s[1:-1]
    return s


def _emit_yaml_simple(meta: dict) -> str:
    lines = []
    for k, v in meta.items():
        lines.append(_emit_kv(k, v, indent=0))
    return "\n".join(lines)


def _emit_kv(k: str, v: Any, indent: int) -> str:
    pad = '  ' * indent
    if v is None:
        return f"{pad}{k}: null"
    if isinstance(v, bool):
        return f"{pad}{k}: {'true' if v else 'false'}"
    if isinstance(v, (int, float)):
        return f"{pad}{k}: {v}"
    if isinstance(v, list):
        if not v:
            return f"{pad}{k}: []"
        out = [f"{pad}{k}:"]
        for item in v:
            out.append(f"{pad}  - {_emit_scalar(item)}")
        return "\n".join(out)
    if isinstance(v, dict):
        if not v:
            return f"{pad}{k}: {{}}"
        out = [f"{pad}{k}:"]
        for nk, nv in v.items():
            out.append(f"{pad}  {nk}: {_emit_scalar(nv)}")
        return "\n".join(out)
    return f"{pad}{k}: {_emit_scalar(v)}"


def _emit_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == '' or any(c in s for c in '#\n') or s.lower() in ('true', 'false', 'null', 'yes', 'no'):
        return f'"{s}"'
    if s.startswith('[') or s.startswith('{') or s.startswith('-') or s.startswith('"') or s.startswith("'"):
        return f'"{s}"'
    return s


def _build_md(meta: dict, body: str) -> str:
    fm = _emit_yaml_simple(meta)
    return f"---\n{fm}\n---\n{body}"


# ─────────────────────────────────────────
# 파일 I/O — atomic write
# ─────────────────────────────────────────

def _atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(path)


def parse_task_data(body: str) -> dict:
    """MD 본문의 ``## task_data`` json 블록을 되읽는다. 없으면 빈 dict.

    [중요] **되읽지 못하는 것과 「없다」를 섞지 않는다** — 깨진 json 은 빈 dict 로 조용히 넘기지 않고
    호출자가 로그를 남길 수 있게 그대로 빈 dict + `False` 를 구분… 하지 않는다. 여기서는 빈 dict
    가 맞다: 이 값은 **워커에게 전달되는 자료**이고, 판정에 쓰이는 신호가 아니다. 깨졌으면 워커가
    받을 것이 없는 것이고 그것은 등재 시점의 결함이다(등재는 우리가 json 으로 직렬화한다).
    """
    if not body:
        return {}
    marker = "## task_data"
    at = body.find(marker)
    if at < 0:
        return {}
    start = body.find("```", at)
    if start < 0:
        return {}
    nl = body.find("\n", start)
    if nl < 0:
        return {}
    end = body.find("```", nl)
    if end < 0:
        return {}
    try:
        val = json.loads(body[nl + 1:end])
    except (ValueError, TypeError):
        return {}
    return val if isinstance(val, dict) else {}


def parse_fail_reason(body: str) -> dict:
    """MD 본문의 마지막 ``## fail`` 절에서 `fail_reason`·`fail_detail`·`failed_at` 을 되읽는다 (#222).

    2026-08-19 부터 `submit_fail` 이 레코드에도 남기지만, 그 전 실패는 본문에만 있다 — 화면이
    「왜 실패했나」를 답하려면 옛 기록도 읽혀야 한다. 없으면 빈 dict (실패가 아닌 태스크가 대부분).
    같은 태스크가 여러 번 실패했으면 **마지막 것**이 현재 상태다.
    """
    if not body or "## fail" not in body:
        return {}
    sec = body.rsplit("## fail", 1)[1]
    out = {}
    for line in sec.splitlines():
        line = line.strip()
        if line.startswith("## "):
            break                       # 다음 절 — fail 절은 끝났다
        for key, field in (("reason:", "fail_reason"), ("detail:", "fail_detail"),
                           ("at:", "failed_at")):
            if line.startswith(key) and field not in out:
                val = line[len(key):].strip()
                if val:
                    out[field] = val[:600]
    return out


def _read_md(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    return _parse_frontmatter(text)


# ─────────────────────────────────────────
# Git — task MD 커밋 (audit log). 실패해도 동작 막지 않음
# ─────────────────────────────────────────

def _git_repo(root: Path) -> Path:
    if (root / ".git").exists():
        return root
    if (root / "Source" / ".git").exists():
        return root / "Source"
    return root


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """git 호출. stdin=DEVNULL 로 부모 stdio 상속 차단 (stdio MCP deadlock 방지)."""
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(repo),
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           stdin=subprocess.DEVNULL, timeout=30,
                           creationflags=creationflags)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def _git_commit_tasks(root: Path, msg: str, paths: list[Path]):
    """task MD 들의 audit commit. 모두 gitignored 면 silent skip — 사용자 프로젝트의
    .gitignore 가 .claude/ 를 막은 환경에서 매번 [git] add 실패 스팸이 나는 걸 방지."""
    repo = _git_repo(root)
    if not (repo / ".git").exists():
        # git 미초기화 환경 — silent (보통 dev 머신에서 발생, 노이즈 가치 없음)
        return
    rels = []
    for p in paths:
        try:
            rels.append(str(p.resolve().relative_to(repo.resolve())))
        except ValueError:
            rels.append(str(p))
    if not rels:
        return
    # check-ignore preflight: 모든 path 가 ignored 면 commit 시도 자체 스킵
    # (사용자가 .claude/ 를 .gitignore 한 경우 정상 동작)
    rc_ci, out_ci = _git(repo, "check-ignore", "-q", "--", *rels)
    # check-ignore 의 rc: 0 = 모두 ignored, 1 = 일부/전부 tracked (commit 가능), 128 = 오류
    if rc_ci == 0:
        return  # 모두 ignored, 정상 — 사용자 의도대로 audit 스킵
    rc, out = _git(repo, "add", *rels)
    if rc != 0:
        _tq_log(f"[git] add 실패: {out[:200]}", root)
        return
    rc, out = _git(repo, "commit", "-m", msg)
    if rc != 0 and "nothing to commit" not in out:
        _tq_log(f"[git] commit 실패: {out[:200]}", root)


def _delete_feature_branches(repo: Path, branches: list[str]) -> dict:
    """로컬 + origin 의 feature 브랜치 삭제. 현재 체크아웃된 브랜치는 main 으로 전환 후 삭제."""
    if not (repo / ".git").exists():
        return {"deleted_local": [], "deleted_remote": [], "failed": []}

    deleted_local: list[str] = []
    deleted_remote: list[str] = []
    failed: list[dict] = []

    # 현재 체크아웃 브랜치 확인 — 삭제 대상이면 main 으로 전환
    rc, cur = _git(repo, "branch", "--show-current")
    current = cur.strip() if rc == 0 else ""
    if current in branches:
        rc, out = _git(repo, "checkout", "main")
        if rc != 0:
            _tq_log(f"[reset-branches] main 체크아웃 실패: {out[:200]}", repo)
            return {"deleted_local": [], "deleted_remote": [], "failed": [{"reason": "checkout_main_failed", "error": out[:200]}]}
        _tq_log(f"[reset-branches] main 으로 전환 (이전: {current})", repo)

    for b in branches:
        # 로컬
        rc, out = _git(repo, "branch", "-D", b)
        if rc == 0:
            deleted_local.append(b)
            _tq_log(f"[reset-branches] 로컬 삭제: {b}", repo)
        elif "not found" not in out and "not a valid" not in out:
            failed.append({"scope": "local", "branch": b, "error": out[:200]})
        # 원격
        rc, out = _git(repo, "push", "origin", "--delete", b)
        if rc == 0:
            deleted_remote.append(b)
            _tq_log(f"[reset-branches] 원격 삭제: {b}", repo)
        elif "remote ref does not exist" not in out and "deleted" not in out:
            failed.append({"scope": "remote", "branch": b, "error": out[:200]})

    return {"deleted_local": deleted_local, "deleted_remote": deleted_remote, "failed": failed}


def _list_worker_branches(repo: Path) -> list[str]:
    """현재 origin/worker/* 모두 나열."""
    rc, out = _git(repo, "branch", "-r", "--list", "origin/worker/*")
    branches = []
    for line in (out or "").splitlines():
        b = line.strip()
        if b.startswith("origin/"):
            name = b[len("origin/"):]
            if name not in branches:
                branches.append(name)
    return branches


# ─────────────────────────────────────────
# 인덱스 (서버 시작 시 .claude/tasks/ 스캔)
# ─────────────────────────────────────────

class TaskIndex:
    def __init__(self, root: Path):
        self.root = root
        self.tasks: dict[str, dict] = {}       # task_id → meta
        self.task_paths: dict[str, Path] = {}
        # [중요] task_data 는 프론트매터가 아니라 **MD 본문의 json 블록**에 산다 — 중첩 dict·리스트를
        #    담으므로 우리 제한적 YAML 파서(1-depth)로는 왕복이 안 된다. 그래서 meta 와 **따로**
        #    들고, `rebuild()` 가 본문에서 다시 읽는다.
        #    원전 근거(`cluster_selftest.py:223`): *"task_data 는 free-form dict → 확실히
        #    저장·**claim 응답에 전달**(top-level 은 모델이 drop)"* — 워커가 `force_backend`
        #    같은 값을 읽는 경로가 이것이다. 실측 2026-08-16: 이 map 이 없어 claim 응답에
        #    task_data 가 아예 없었고, `force_backend` 이식이 **죽은 이식**이 될 뻔했다.
        self.task_data: dict[str, dict] = {}   # task_id → 등재 시 받은 free-form dict
        self.works: dict[str, dict] = {}       # work_id → meta
        self.work_paths: dict[str, Path] = {}
        # 워커 directive 큐: heartbeat / poll 응답으로 1회 소비됨
        # 값은 directive 문자열 리스트 (FIFO). admin 이 push, 워커가 take 시 비움
        self.worker_directives: dict[str, list[str]] = {}
        self.worker_last_seen: dict[str, str] = {}   # worker_id → ISO ts
        # Plan v5 C.3 — claim 시 verify_capable=True 로 신고한 워커의 최근 접촉 ts.
        # backlog 카나리("verify-capable 0대인데 push submitted>0")의 liveness 판정 입력.
        self.verify_capable_seen: dict[str, str] = {}   # worker_id → ISO ts
        # PLAN §5.2-C — claim 시 워커가 마지막으로 신고한 능력 목록 (관측 전용).
        # 라우팅 판정은 claim 요청에 실려온 값으로 하지 이 캐시로 하지 않는다 — 워커가
        # UE5 를 지운 뒤에도 옛 신고가 남아 잘못 배정되는 일을 막기 위해서다.
        self.worker_capabilities: dict[str, list[str]] = {}   # worker_id → [cap]
        self.lock = threading.RLock()

    def rebuild(self):
        with self.lock:
            self.tasks.clear()
            self.task_paths.clear()
            self.task_data.clear()
            self.works.clear()
            self.work_paths.clear()
            td = _tasks_dir(self.root)
            if not td.exists():
                return
            for work_dir in td.iterdir():
                if not work_dir.is_dir() or work_dir.name.startswith("_"):
                    continue
                req = work_dir / "_request.md"
                if req.exists():
                    meta, _ = _read_md(req)
                    wid = meta.get("work_id") or work_dir.name
                    meta["work_id"] = wid
                    self.works[wid] = meta
                    self.work_paths[wid] = req
                for f in work_dir.glob("*.md"):
                    if f.name == "_request.md":
                        continue
                    meta, body = _read_md(f)
                    tid = meta.get("task_id")
                    if tid:
                        self.tasks[tid] = meta
                        self.task_paths[tid] = f
                        # [중요] 재기동해도 워커가 받을 자료가 남아야 한다 — 본문에서 되읽는다.
                        self.task_data[tid] = parse_task_data(body)
                        # 실패 근거도 같은 이유로 되읽는다 (#222) — 2026-08-19 이전 실패는
                        # 본문에만 있어서 API·화면이 「왜」를 몰랐다. 레코드 값이 우선.
                        for k, v in parse_fail_reason(body).items():
                            meta.setdefault(k, v)
