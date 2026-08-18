"""작업장 폴링 claimer — 큐에서 잡을 **집어서** 실행하고 보고한다 (#204, κ.0 CI 러너 패턴).

원전 κ.0 (`local_llm_distributed_workers_plan_v5.0.md:276`): *"통합 빌드게이트는 인프라에
고정하지 않고 task_queue 잡으로 큐잉 → UE5 있는 윈도우 워커가 claim 하는 CI 러너 패턴"*,
그리고 ②워커의 계약: **실행 + 보고만, 판단 없음** — 재시도·에스컬레이션·머지는 마스터(①)가
보고된 사실로 결정한다.

## [중요] 이 데몬이 하지 않는 것

- **판단하지 않는다** — 빌드가 깨져도 여기서 재시도하지 않는다. 사실(pass/fail+로그)을
  submit 하고 끝. κ.0 ①/② 경계이고, 토큰 스코프(auth.WORKER_SCOPE)가 같은 경계를 강제한다
  (이 토큰으로는 verify·등록·정리를 **못 한다**).
- **신고 안 한 유형을 집지 않는다** — claim 에 `types` 를 신고한다(기본 `["build"]`).
  유형 필터가 없으면 ue5 능력 신고가 requires 빈 태스크까지 끌어와 Flow Y 의 일감을 훔친다.
  [중요] 추론(code) pull 은 **opt-in** (`--types=build,code`) — 켜기 전까지 기존 마스터
  push 파견(infer.py)이 그대로 그 일을 맡는다 (§8.4: 조용한 경로 전환 없음).
- **파일을 마스터로 보내지 않는다** — 로그 꼬리는 submit 본문(HTTP)에 실린다. 워커→마스터
  대용량은 이 경로가 아니다. [중요] 추론 응답도 같다: `response.txt`/`result.json` 은 체크아웃
  안에 남고, **마스터가 collect(scp 읽기)로 가져간다** — push 파견의 회수 경로와 동일.
- **추론 태스크를 submit 하지 않는다** — 추론이 끝난 것은 태스크가 끝난 것이 아니다.
  submit(branch, head_commit)은 통합자가 빌드를 통과시킨 뒤의 일이다(소 1.4.3). 태스크는
  `claimed` 로 남고 리스 만료·재확보는 정상 흐름 — result.json 재사용이 이중 구매를 막는다.

## 실행 (작업장에서, 체크아웃 루트 기준 — [중요] 패키지로 임포트해야 한다. 직접 실행은
## 상대 임포트가 죽는다. PAYLOAD_INIT 의 관례와 같은 형태)

    py -c "import sys; sys.path.insert(0, r'.ax/lib'); from axmaster.work.claimer import main; raise SystemExit(main(['--once']))"
    py -c "import sys; sys.path.insert(0, r'.ax/lib'); from axmaster.work.claimer import main; raise SystemExit(main(['--once', '--types=build,code']))"

읽는 것: `.ax/config.json`(마스터 주소·ue5_cmd·능력·프로젝트 — 손으로 안 적는다) ·
`.ax/token`(worker 역할 토큰 — deliver 가 놓는다). 상주 시 ax_safety 가드 3종이 걸린다
(크래시 로그 `.ax/logs/claimer_crash.log` · 절전 차단 · Quick Edit 차단).

## 상주 (원전 worker.exe 의 자리 — 로그온 세션의 데몬)

스위치 없이 부르면 폴링 상주다. `.ax/claimer.lock` 배타 잠금이 **하나만** 살게 하므로,
감시자(윈도우 작업 스케줄러가 5분마다 재호출)가 겹쳐 불러도 안전하고 크래시 후엔 다음
틱에 되살아난다. [주의] 원전과 같은 전제: **로그온된 사용자 세션에서 돈다** (claude 인증·
git 키가 그 사용자의 것) — 로그아웃 상태에서는 다음 로그온까지 쉰다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

POLL_SEC = 20
HTTP_TIMEOUT = 30
BUILD_TIMEOUT = 1800
GIT_TIMEOUT = 120
INFER_TIMEOUT = 3600                # claude -p 한 번의 상한 (runner.DEFAULT_TIMEOUT 과 동값)
HEARTBEAT_SEC = 240                 # 리스 1200s — 네 번 놓쳐도 산다 (runner 와 동값)
LOG_RETENTION_DAYS = 7              # 일별 로그·task 디버그 보존 기간 (#220 — 원전 retention 회귀)
TYPES = ["build"]                   # [중요] 유형 필터 — 신고 안 한 유형을 훔치지 않는다


class ClaimerError(RuntimeError):
    """기동 불가. [중요] 조용히 도는 척하지 않는다 — 설정이 없으면 여기서 죽는 게 맞다."""


def find_root(start: Path | None = None) -> Path:
    """`.ax/config.json` 이 있는 체크아웃 루트. 스크립트 위치(…/.ax/lib/axmaster/work/)에서
    거슬러 올라가므로 어느 cwd 에서 불려도 같은 답이다."""
    for base in (start or Path(__file__).resolve(), Path.cwd()):
        p = base if isinstance(base, Path) else Path(base)
        for cand in (p, *p.parents):
            if (cand / ".ax" / "config.json").is_file():
                return cand
    raise ClaimerError(".ax/config.json 을 찾지 못했다 — 체크아웃 루트에서 실행하거나 "
                       "마스터에서 `python -m master.client deliver` 로 배달부터")


class Client:
    """큐 HTTP 클라이언트 — worker 역할 토큰으로만 말한다."""

    def __init__(self, root: Path):
        cfg = json.loads((root / ".ax" / "config.json").read_text(encoding="utf-8"))
        tok_p = root / ".ax" / "token"
        if not tok_p.is_file():
            raise ClaimerError(".ax/token 이 없다 — 마스터에서 `python -m master.auth "
                               "init-role worker` 후 재배달할 것 (fail-closed)")
        self.token = tok_p.read_text(encoding="utf-8").strip()
        m = cfg.get("master") or {}
        self.base = f"http://{m.get('host')}:{(m.get('services') or {}).get('task_queue', 8101)}"
        self.worker_id = ((cfg.get("this_host") or {}).get("host")
                          or "unknown-workshop")
        self.project = cfg.get("project") or ""
        self.ue5_cmd = ((cfg.get("backends") or {}).get("ue5_cmd") or "")
        # [중요] 능력은 **마스터가 잰 값**(config.json — deliver 가 probe 실측으로 쓴다)이다.
        #    하드코딩(["ue5"])은 .43 같은 UE5 없는 워커에서 허위 신고가 된다 — 신고한 능력으로
        #    빌드 잡을 집어놓고 못 돌리는 것이 최악이다.
        self.capabilities = list(cfg.get("capabilities") or [])
        self.root = root

    def _call(self, method: str, path: str, payload=None):
        req = urllib.request.Request(
            self.base + path,
            data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
            method=method,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                body = r.read().decode("utf-8", "replace").strip()
                return r.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            return e.code, {"error": e.read().decode("utf-8", "replace")[:300]}

    def claim(self, types=None):
        st, got = self._call("POST", "/api/v1/tasks/claim",
                             {"worker_id": self.worker_id,
                              "capabilities": self.capabilities,
                              "types": list(types or TYPES)})
        return got if st == 200 else None

    def heartbeat(self, task_id: str, note: str = ""):
        # note = 「지금 하는 일」 한 줄 (#220 ③) — /cluster 실시간 층이 보여 준다.
        # 빈 note 는 서버가 이전 값을 유지한다 (models.HeartbeatReq).
        self._call("POST", f"/api/v1/tasks/{task_id}/heartbeat",
                   {"worker_id": self.worker_id, "note": str(note)[:200]})

    def submit(self, task_id: str, *, head_commit: str, build: dict, seconds: float,
               epoch=None):
        payload = {"branch": "", "head_commit": head_commit,
                   "self_check": {"build": build},
                   "metrics": {"seconds": round(seconds, 1),
                               "worker": self.worker_id},
                   "epoch": epoch}
        return self._call("POST", f"/api/v1/tasks/{task_id}/submit", payload)

    def submit_fail(self, task_id: str, reason: str, detail: str = ""):
        return self._call("POST", f"/api/v1/tasks/{task_id}/submit-fail",
                          {"reason": reason[:200], "detail": detail[:2000]})


def _log_dir(root: Path) -> Path:
    return root / ".ax" / "logs"


def _log_path(root: Path) -> Path:
    """일별 메인 로그 (#220 ② — 원전 common.py 의 worker_<date>.log 회귀).
    옛 단일 `claimer.log`(상한 절단)는 이 방식으로 대체됐다 — 절단은 문제가 난 날의
    앞부분(원인)을 지웠다. 총량은 회전 + retention 이 묶는다."""
    return _log_dir(root) / f"claimer_{datetime.now().strftime('%Y-%m-%d')}.log"


def _debug_dir(root: Path, task_id: str) -> Path:
    """task 별 디버그 디렉토리 (#220 ① — 원전 worker_debug/<task_id> 회귀).
    메인 로그가 silent 일 때(심박 스레드·LLM 응답 대기) 무엇이 진행 중인지 여기서 추적.
    task 종료 시 cleanup 안 함 — 사후 디버깅 용도. retention 은 메인 로그와 같은 7일."""
    return _log_dir(root) / "claimer_debug" / task_id


def _dlog(p: Path, msg: str) -> None:
    """디버그 파일 한 줄 append — 실패해도 본 작업을 막지 않는다 (로그 채널 계약)."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _bootstrap_log_rotation(root: Path) -> None:
    """상주 부팅 시 1회 — 오늘 로그가 이미 있으면 _N 접미사로 rename (원전 common.py,
    task_queue/persistence.py 와 같은 이식). 단발(--once)은 호출 안 함 — 파일 폭증."""
    log_path = _log_path(root)
    if not log_path.exists():
        return
    n = 1
    while True:
        candidate = log_path.with_name(f"{log_path.stem}_{n}{log_path.suffix}")
        if not candidate.exists():
            try:
                log_path.rename(candidate)
            except OSError:
                pass                # 동시 부팅 race — 다른 프로세스가 이미 rename 함
            return
        n += 1


def _retention_sweep(root: Path, *, days: int = LOG_RETENTION_DAYS) -> int:
    """오래된 일별 로그·task 디버그 디렉토리 삭제 (원전 retention 7일). 상주 부팅 시 1회.
    반환은 지운 항목 수 — 로그에 적는다 (조용한 삭제는 없다)."""
    import shutil
    cutoff = time.time() - days * 86400
    removed = 0
    d = _log_dir(root)
    try:
        for p in d.glob("claimer_*.log"):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                removed += 1
        dbg = d / "claimer_debug"
        if dbg.is_dir():
            for sub in dbg.iterdir():
                if sub.is_dir() and sub.stat().st_mtime < cutoff:
                    shutil.rmtree(sub, ignore_errors=True)
                    removed += 1
    except OSError:
        pass
    return removed


def _log(root: Path, msg: str) -> None:
    line = f"{datetime.now().strftime('%m-%d %H:%M:%S')} {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # [중요] .2 콘솔은 CP949 — em-dash 하나가 프로세스를 통째로 죽였다 (실측 2026-08-18,
        #    두 번 물린 함정의 세 번째). 콘솔은 손실 표시로 버티고, 원문은 아래 파일(UTF-8)에.
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, "replace").decode(enc, "replace"), flush=True)
    except OSError:
        pass                        # pythonw(상주)에는 콘솔이 없다 — 파일 로그가 본선이다
    try:
        p = _log_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass                        # 로그 채널 — 본 작업을 막지 않는다 (의도된 fail-soft)


def acquire_singleton(root: Path):
    """상주 중복 방지 — `.ax/claimer.lock` 배타 잠금. 성공 = 열린 핸들(살아 있는 동안 유지),
    실패 = None (이미 상주 중). [중요] 잠금은 프로세스 죽음과 함께 OS 가 풀어 준다 —
    PID 파일과 달리 크래시 뒤 stale 잠금이 없어서, 감시자(schtasks)가 5분마다 불러도
    「이미 돈다」/「죽었으니 새로 뜬다」 가 판정 없이 갈린다.
    """
    p = root / ".ax" / "claimer.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p, "a+b")              # noqa: SIM115 — 수명이 프로세스 수명이다
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None


def _head_commit(tree: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ── 추론(code) — 실행 + 사실 기록. 판단·회수·제출은 전부 마스터의 것 ──────────────────

# [중요] infer.py 의 INFER_INSTRUCTION 과 **글자까지 같아야 한다** (test_claimer 가 대조한다).
#    여기 사본을 두는 이유: 이 파일은 payload 로 작업장에 나가고, infer.py 는 마스터 전용
#    의존(bundle 등)을 물고 있어 못 나간다. 프롬프트를 고치면 **둘 다** 고칠 것.
INFER_INSTRUCTION = (
    "Follow the ax-infer skill (INFERENCE ONLY, not ax-work). "
    "Read ./{work}/{task}/manifest.md and do exactly what it says. "
    "Judge from the source files in this checkout, not from memory. "
    "Do NOT edit source files, do NOT commit, do NOT push, do NOT create branches. "
    "Write the complete new content of every target file to ./{work}/{task}/{resp} as UTF-8, "
    "one block per file, each starting with a line: === FILE: <path from the manifest> === . "
    "That file must contain ONLY those blocks: do NOT write RESPONSE: or RESULT: into it. "
    "Then PRINT to stdout, as the last two non-empty lines you print and nothing after them: "
    "RESPONSE: <number of files> / RESULT: DONE "
    "(print RESULT: BLOCKED instead if you could not finish, and say why above it)."
)

WORK_REL = ".ax/work"               # bundle.WORK_REL 과 동값 (payload 라 임포트 불가)
RESPONSE_NAME = "response.txt"      # infer.RESPONSE_NAME 과 동값
RESULT_NAME = "result.json"         # 실행 사실 기록 — 마스터 collect 가 읽는다
# carry.py 의 운송 규약과 동값 — 매니페스트는 durable task/<id> 의 이 경로에 실려 온다
CARRY_MANIFEST_REL = ".ax/tasks/{tid}/context.md"
CARRY_REF = "refs/ax/carry/{tid}"


class _Heart:
    """긴 실행 동안 리스를 살려 둔다. [중요] 실패해도 본 작업을 죽이지 않는다 —
    하트비트 한 번 놓친 것과 워커가 죽은 것은 다르다 (runner._Beater 와 같은 계약).

    #220: `note` 는 「지금 하는 일」 한 줄 — 본 작업 스레드가 `set_note()` 로 갱신하면
    다음 심박이 실어 나른다 (beat 가 인자를 받으면 전달, 아니면 종전대로). `hb_path` 가
    있으면 매 심박 결과를 task 디버그 파일에 append (원전 heartbeat.py 회귀) —
    메인 로그가 silent 일 때 심박 스레드 생존을 여기서 확인한다."""

    def __init__(self, beat, interval: int = HEARTBEAT_SEC, hb_path: Path | None = None):
        self._beat, self._interval = beat, interval
        self._stop = threading.Event()
        self._t = None
        self._hb_path = hb_path
        self._note = ""
        self.errors = 0
        # note 전달 여부는 여기서 한 번 판정 — 호출 시 TypeError 폴백은 beat **내부**의
        # TypeError 까지 삼켜 심박을 조용히 절반만 돌게 한다 (그 함정을 피한다)
        import inspect
        try:
            self._wants_note = len(inspect.signature(beat).parameters) >= 1
        except (TypeError, ValueError):
            self._wants_note = False

    def set_note(self, note: str) -> None:
        """위상 전환은 다음 interval 을 기다리지 않고 **즉시 한 번** 심박을 쏜다 —
        240s 간격만으로는 /cluster 의 「지금」이 위상 하나를 통째로 놓친다.
        note 변경은 task 당 손에 꼽는 횟수라 큐에 부담이 없다."""
        self._note = str(note)
        if self._hb_path is not None:
            _dlog(self._hb_path, f"[note] {self._note}")
        self._tick()

    def _tick(self):
        try:
            if self._wants_note:
                self._beat(self._note)
            else:
                self._beat()                                 # note 를 안 받는 beat (기존 계약)
            if self._hb_path is not None:
                _dlog(self._hb_path, f"[beat] ok errors={self.errors} note={self._note}")
        except Exception as e:                               # noqa: BLE001
            self.errors += 1
            if self._hb_path is not None:
                _dlog(self._hb_path, f"[beat] FAIL {type(e).__name__}: {e} errors={self.errors}")

    def __enter__(self):
        def _loop():
            while not self._stop.wait(self._interval):
                self._tick()
        self._t = threading.Thread(target=_loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)
        return False


def _git(tree: Path, *args: str, timeout: int = GIT_TIMEOUT) -> tuple:
    """`(rc, stdout_bytes, stderr_text)`. [중요] stdout 은 **bytes** — 매니페스트 본문이
    지나가는 자리라 콘솔 인코딩(CP949)에 닿기 전에 그대로 파일로 흘려야 한다."""
    try:
        r = subprocess.run(["git", "-C", str(tree), *args],
                           capture_output=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        return -1, b"", f"{type(e).__name__}: {e}"


def materialize_manifest(tree: Path, tid: str) -> tuple:
    """durable `task/<tid>` 에서 매니페스트를 자기 클론으로 꺼낸다. `(경로, blob sha)`.

    carry.materialize_command 와 같은 절차를 **로컬에서** 돈다 — pull 에서는 마스터가
    밀어 줄 수 없으니 워커가 스스로 꺼낸다 (#185 가 이 확장을 위해 깔아 둔 전제).
    실패는 예외 — 매니페스트 없이 추론시키면 Claude 가 할 일을 지어낸다.
    """
    ref = CARRY_REF.format(tid=tid)
    rel = CARRY_MANIFEST_REL.format(tid=tid)
    rc, _, err = _git(tree, "fetch", "origin", f"+refs/heads/task/{tid}:{ref}")
    if rc != 0:
        raise ClaimerError(f"매니페스트 fetch 실패 (task/{tid}) — {err.strip()[-200:]}")
    rc, body, err = _git(tree, "--no-pager", "show", f"{ref}:{rel}")
    if rc != 0 or not body.strip():
        raise ClaimerError(f"매니페스트가 durable 에 없다 ({rel}) — 등록이 carry.publish 를 "
                           f"안 탔거나 낡은 태스크다: {err.strip()[-160:]}")
    dst = tree / WORK_REL / tid / "manifest.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(body)
    rc, sha, err = _git(tree, "hash-object", str(dst))
    if rc != 0:
        raise ClaimerError(f"blob sha 실패 — {err.strip()[-160:]}")
    return dst, sha.decode("ascii", "replace").strip()


def _claude_argv(instr: str) -> list:
    argv = ["claude", "-p", "--output-format", "json",
            "--dangerously-skip-permissions", instr]
    # [주의] 윈도우의 claude 는 .cmd 심이라 cmd /c 를 거쳐야 돈다. instr 는 ASCII 만이라
    #    (runner 의 「지시는 ASCII」 규칙) CP949 콘솔 함정이 성립하지 않는다.
    return (["cmd", "/c"] + argv) if sys.platform == "win32" else argv


def run_infer(c: Client, task: dict, *, exec_fn=None, retry_sleep=None, log=None) -> dict:
    """추론 태스크 하나: 매니페스트 실체화 → claude 실행 → **사실을 result.json 에**.

    [중요] 판단하지 않고, submit 하지 않는다 — 마커 해석·층1·스풀은 마스터 collect 의 일이고
    (κ.0 ①/② 경계), submit 은 통합자가 빌드를 통과시킨 뒤의 일이다. 여기서 남기는 것은
    「무엇이 실행됐고 무엇이 출력됐나」 뿐이다.
    """
    log = log or (lambda m: _log(c.root, m))
    tid = task.get("task_id") or task.get("id") or ""
    epoch = task.get("epoch")
    tree = c.root
    workdir = tree / WORK_REL / tid
    result_p = workdir / RESULT_NAME
    ddir = _debug_dir(c.root, tid)                       # #220 ① — 진행 중 추적의 자리
    log(f"[claim] {tid[:8]} code (infer) epoch={epoch} · debug={ddir}")

    with _Heart(lambda n="": c.heartbeat(tid, note=n),
                hb_path=ddir / "heartbeat.log") as hb:
        hb.set_note("매니페스트 실체화 중")
        # [중요] 실체화는 참을성 있게 — 등록 순서상 durable publish 는 태스크 등록 **뒤**라
        #    (task_id 가 나와야 브랜치명이 생긴다, 원전도 같은 모순을 work_id 폴백으로 풀었다)
        #    20s 폴링 데몬은 publish 완료 전에 claim 할 수 있다. gitea 일시 오류도 같은 결
        #    (실측 2026-08-18: "Gitea: Failed to execute git command"). 재시도는 판단이
        #    아니라 운송의 인내다 — 상한(5회×15s)을 넘으면 사실로 되돌린다(fail-closed).
        blob = None
        last_err = None
        for i in range(5):
            try:
                _, blob = materialize_manifest(tree, tid)
                break
            except ClaimerError as e:
                last_err = e
                log(f"[retry] {tid[:8]} 실체화 {i + 1}/5 실패 — 15s 후 재시도")
                hb.set_note(f"실체화 재시도 {i + 1}/5 — 15s 대기")
                (retry_sleep or time.sleep)(15)
        if blob is None:
            # 추론을 시작조차 못 했다 — 사실로 되돌린다 (build-setup 과 같은 계약)
            c.submit_fail(tid, "infer-setup", str(last_err))
            return {"task": tid, "outcome": f"[중요] 추론 착수 실패 — {last_err}"}

        # [중요] 재사용 (소 1.3.3 의 워커판): 같은 매니페스트(blob)의 완료 기록이 이미 있으면
        #    다시 사지 않는다. epoch 만 이번 claim 의 것으로 갱신 — 낡은 epoch 제출은 큐가
        #    fencing 으로 거부하므로(그러라고 있다) 갱신 없이는 재사용분을 제출할 수 없다.
        if result_p.is_file() and (workdir / RESPONSE_NAME).is_file():
            try:
                old = json.loads(result_p.read_text(encoding="utf-8"))
            except ValueError:
                old = {}
            # [주의] "RESULT: DONE" 존재는 판정이 아니라 값싼 사실 필터다 (판정은 마스터의
            #    collect 가 층1까지 한다). BLOCKED 기록을 재사용하면 마스터가 재큐잉해도
            #    같은 실패만 되돌아온다 — BLOCKED 는 다시 돈다.
            if (old.get("manifest_blob") == blob and old.get("rc") == 0
                    and "RESULT: DONE" in str(old.get("stdout") or "")):
                old["epoch"] = epoch
                old["reused_at"] = datetime.now().isoformat(timespec="seconds")
                _atomic_json(result_p, old)
                log(f"[reuse] {tid[:8]} 같은 매니페스트의 응답이 이미 있다 — 추론 안 함")
                return {"task": tid, "infer": "reused", "manifest_blob": blob[:12]}

        instr = INFER_INSTRUCTION.format(work=WORK_REL, task=tid, resp=RESPONSE_NAME)
        data = task.get("task_data") or {}
        timeout = int(data.get("timeout") or INFER_TIMEOUT)
        hb.set_note("claude 추론 중 (stdout 은 debug/llm_stdout.log 에 실시간)")
        t0 = time.time()
        if exec_fn is not None:
            rc, stdout = exec_fn(tree, _claude_argv(instr), timeout)
        else:
            rc, stdout = _run_claude(tree, _claude_argv(instr), timeout,
                                     stream_dir=ddir)
        dt = time.time() - t0
        hb.set_note(f"추론 종료 rc={rc} ({dt:.0f}s) — result.json 기록")

    rec = {
        "task_id": tid, "epoch": epoch, "kind": "code",
        "manifest_blob": blob, "rc": rc,
        # [주의] 상한은 방어선일 뿐 — claude 의 json 출력(마커+계측)은 통상 수 KB 다.
        #    응답 본문은 여기 없다: response.txt 가 나르고 collect 가 scp 로 읽는다.
        "stdout": (stdout or "")[-65536:],
        "seconds": round(dt, 1), "worker": c.worker_id,
        "heartbeat_errors": hb.errors,
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    _atomic_json(result_p, rec)
    log(f"[infer] {tid[:8]} rc={rc} {dt:.0f}s → {RESULT_NAME} 기록 "
        f"(submit 없음 — 마스터가 collect 한다)")
    return {"task": tid, "infer": "recorded", "rc": rc, "seconds": round(dt, 1)}


def _pump(pipe, sink: list, path: Path | None) -> threading.Thread:
    """파이프를 실시간으로 파일에 흘리며 버퍼에 모은다 (#220 ① — 원전 claude_spawn 의
    llm_stdout.log 회귀). LLM 응답 대기 중에도 debug 파일에서 진행을 볼 수 있다."""
    def _run():
        for line in pipe:
            sink.append(line)
            if path is not None:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as f:
                        f.write(line)
                except OSError:
                    pass                # 로그 채널 — 본 작업을 막지 않는다
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def _run_claude(tree: Path, argv: list, timeout: int,
                stream_dir: Path | None = None) -> tuple:
    """`(rc, stdout)`. 예외를 던지지 않는다 — 타임아웃·기동 실패도 사실이다.

    [주의] stderr 는 stdout 에 **섞지 않는다** — collect 의 마커 계약(`RESULT:` 가 stdout
    말미)이 stderr 혼입으로 깨질 수 있다. stderr 는 debug 의 llm_stderr.log 로만 간다."""
    try:
        proc = subprocess.Popen(argv, cwd=str(tree), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8",
                                errors="replace")
    except OSError as e:
        return -1, f"[claimer] claude 기동 실패: {type(e).__name__}: {e}"
    out: list = []
    err: list = []
    t_out = _pump(proc.stdout, out, (stream_dir / "llm_stdout.log") if stream_dir else None)
    t_err = _pump(proc.stderr, err, (stream_dir / "llm_stderr.log") if stream_dir else None)
    try:
        rc = proc.wait(timeout=timeout)
        t_out.join(timeout=10)
        t_err.join(timeout=10)
        return rc, "".join(out)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        t_out.join(timeout=10)
        t_err.join(timeout=10)
        return -1, "".join(out) + f"\n[claimer] {timeout}s 타임아웃 — 프로세스를 죽였다"


def _atomic_json(p: Path, obj: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)                  # collect 가 반쯤 쓰인 기록을 읽으면 안 된다


def run_one(c: Client, task: dict, *, build_fn=None, exec_fn=None, retry_sleep=None,
            log=None) -> dict:
    """잡 하나 실행 → 보고. 반환은 사람이 읽을 요약 (판단은 없다 — 사실만)."""
    log = log or (lambda m: _log(c.root, m))
    tid = task.get("task_id") or task.get("id") or ""
    kind = str(task.get("type") or "")
    if kind == "code":
        return run_infer(c, task, exec_fn=exec_fn, retry_sleep=retry_sleep, log=log)
    if kind != "build":
        # [중요] 유형 필터를 뚫고 왔다면 그건 큐 버그다 — 조용히 삼키지 않고 되돌린다
        c.submit_fail(tid, "unsupported-type", f"claimer 는 build·code 만 다룬다: {kind!r}")
        return {"task": tid, "outcome": f"[중요] 지원 안 하는 유형 {kind!r} — submit-fail"}
    data = task.get("task_data") or {}
    tree = Path(data.get("tree") or c.root)
    ddir = _debug_dir(c.root, tid)                       # #220 ① — 진행 중 추적의 자리
    log(f"[claim] {tid[:8]} build tree={tree} · debug={ddir}")
    t0 = time.time()
    try:
        # [중요] 빌드는 수 분(실측 109~194s)이라 심박 없이는 리스가 낡는다 — 이제 note 도
        #    함께 나른다 (#220 ③). 옛 단발 c.heartbeat(tid) 는 이 스레드가 대체한다.
        with _Heart(lambda n="": c.heartbeat(tid, note=n),
                    hb_path=ddir / "heartbeat.log") as hb:
            hb.set_note("UE5 빌드 중")
            fn = build_fn
            if fn is None:
                from .build_local import local_build_fn
                fn = local_build_fn(project=c.project, ue5_cmd=c.ue5_cmd,
                                    timeout=int(data.get("timeout") or BUILD_TIMEOUT))
            res = fn(tree)
            hb.set_note(f"빌드 종료 — {str(res.get('summary') or '')[:80]} · submit 중")
    except Exception as e:                                    # noqa: BLE001
        # 빌드를 시작조차 못 했다 — 확인 불가는 통과가 아니다 (layer3 계약)
        c.submit_fail(tid, "build-setup", f"{type(e).__name__}: {e}")
        return {"task": tid, "outcome": f"[중요] 빌드 착수 실패 — {type(e).__name__}: {e}"}
    dt = time.time() - t0
    # 빌드 근거를 task 디버그에 보존 (#220 ①) — submit 본문의 log_tail 은 잘린 꼬리고,
    # 사후 디버깅은 워커 쪽 이 파일에서 시작한다 (전체 UBT 로그는 엔진 자신의 위치에 남는다)
    _dlog(ddir / "build.log", f"summary={res.get('summary')} seconds={dt:.0f}\n"
          + str(res.get("raw_tail") or res.get("log_tail") or "")[-16384:])
    # [중요] 실패도 submit 이다 — pass/fail 은 사실이고 판단(재시도 등)은 마스터의 것.
    #    submit-fail 은 "실행 자체가 안 됐다" 에만 쓴다.
    slim = {k: v for k, v in res.items()
            if k in ("ok", "passed", "failure", "summary", "seconds", "log_tail")}
    st, got = c.submit(tid, head_commit=_head_commit(tree), build=slim, seconds=dt,
                       epoch=task.get("epoch"))
    ok = bool(res.get("ok"))
    log(f"[submit] {tid[:8]} build={'PASS' if ok else 'FAIL'} {dt:.0f}s → HTTP {st}")
    return {"task": tid, "build_ok": ok, "seconds": round(dt, 1),
            "submit_http": st, **({"submit_error": got.get("error")} if st != 200 else {})}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    once = "--once" in argv
    interval = POLL_SEC
    types = list(TYPES)
    for a in argv:
        if a.startswith("--interval="):
            interval = max(5, int(a.split("=", 1)[1]))
        elif a.startswith("--types="):
            # [중요] opt-in 확장 자리 — code(추론 pull)는 이 스위치로만 켠다. 모르는 유형은
            #    여기서 거른다: 신고했다가 run_one 이 되돌리면 왕복만 남는다.
            want = [t.strip() for t in a.split("=", 1)[1].split(",") if t.strip()]
            bad = [t for t in want if t not in ("build", "code")]
            if bad:
                raise ClaimerError(f"모르는 유형 {bad} — claimer 가 다루는 것은 build·code")
            types = want or types
    root = find_root()
    c = Client(root)
    log = lambda m: _log(root, m)                            # noqa: E731

    from . import ax_safety
    if once:
        ax_safety.setup_crash_handler(root / ".ax" / "logs", log)   # 가드 셋 중 크래시만
    else:
        # [중요] 상주는 하나만 — 감시자(schtasks 5분)가 겹쳐 불러도 두 번째는 조용히 물러난다
        #    (겹치면 같은 큐를 두 입이 빤다). exit 0 — 감시자에게는 「이미 산다」가 정상이다.
        #    [주의] 핸들 참조를 놓으면 GC 가 잠금을 풀어 버린다 — 루프가 사는 동안 쥔다.
        _lock = acquire_singleton(root)                      # noqa: F841 — 참조 유지가 목적
        if _lock is None:
            log("[boot] 이미 상주 중 (claimer.lock 잠김) — 이 인스턴스는 물러난다")
            return 0
        ax_safety.apply_all(root / ".ax" / "logs", log)
        # #220 ② — 부팅별 회전 + retention. 상주에서만: --once 는 회전하면 파일이 폭증한다
        #    (원전 common.py 의 단서 그대로). 잠금 획득 **뒤**라 동시 부팅 race 도 없다.
        _bootstrap_log_rotation(root)
        swept = _retention_sweep(root)
        if swept:
            log(f"[boot] 로그 retention — {LOG_RETENTION_DAYS}일 지난 {swept}개 항목 삭제")

    log(f"[boot] claimer worker_id={c.worker_id} project={c.project} "
        f"types={types} caps={c.capabilities} {'once' if once else f'poll {interval}s'}")
    while True:
        task = c.claim(types)
        if task:
            out = run_one(c, task, log=log)
            log(f"[done] {json.dumps(out, ensure_ascii=False)}")
            if once:
                return 0 if out.get("build_ok") or "outcome" not in out else 1
            continue                # 집었으면 바로 다음을 물어본다 — 큐 소진 우선
        if once:
            log("[idle] 집을 잡이 없다")
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    if __package__ in (None, ""):
        # [중요] 직접 실행 자리 — 윈도우 작업 스케줄러(/tr)가 이 파일을 pythonw 로 바로
        #    가리킨다 (런처 파일 없이). 상대 임포트가 죽으므로 패키지로 재진입한다.
        #    배치 배열: <checkout>/.ax/lib/axmaster/work/claimer.py → parents[2] = lib
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from axmaster.work.claimer import main as _pkg_main
        sys.exit(_pkg_main())
    sys.exit(main())
