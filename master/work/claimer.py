"""작업장 폴링 claimer — 큐에서 잡을 **집어서** 실행하고 보고한다 (#204, κ.0 CI 러너 패턴).

원전 κ.0 (`local_llm_distributed_workers_plan_v5.0.md:276`): *"통합 빌드게이트는 인프라에
고정하지 않고 task_queue 잡으로 큐잉 → UE5 있는 윈도우 워커가 claim 하는 CI 러너 패턴"*,
그리고 ②워커의 계약: **실행 + 보고만, 판단 없음** — 재시도·에스컬레이션·머지는 마스터(①)가
보고된 사실로 결정한다.

## [중요] 이 데몬이 하지 않는 것

- **판단하지 않는다** — 빌드가 깨져도 여기서 재시도하지 않는다. 사실(pass/fail+로그)을
  submit 하고 끝. κ.0 ①/② 경계이고, 토큰 스코프(auth.WORKER_SCOPE)가 같은 경계를 강제한다
  (이 토큰으로는 verify·등록·정리를 **못 한다**).
- **infer 를 집지 않는다** — claim 에 `types=["build"]` 를 신고한다. 유형 필터가 없으면
  ue5 능력 신고가 requires 빈 infer 태스크까지 끌어와 Flow Y 의 일감을 훔친다.
- **파일을 마스터로 보내지 않는다** — 로그 꼬리는 submit 본문(HTTP)에 실린다. 워커→마스터
  대용량은 이 경로가 아니다.

## 실행 (작업장에서, 체크아웃 루트 기준 — [중요] 패키지로 임포트해야 한다. 직접 실행은
## 상대 임포트가 죽는다. PAYLOAD_INIT 의 관례와 같은 형태)

    py -c "import sys; sys.path.insert(0, r'.ax/lib'); from axmaster.work.claimer import main; raise SystemExit(main(['--once']))"
    py -c "import sys; sys.path.insert(0, r'.ax/lib'); from axmaster.work.claimer import main; raise SystemExit(main())"

읽는 것: `.ax/config.json`(마스터 주소·ue5_cmd·프로젝트 — 손으로 안 적는다) ·
`.ax/token`(worker 역할 토큰 — deliver 가 놓는다). 상주 시 ax_safety 가드 3종이 걸린다
(크래시 로그 `.ax/logs/claimer_crash.log` · 절전 차단 · Quick Edit 차단).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

POLL_SEC = 20
HTTP_TIMEOUT = 30
BUILD_TIMEOUT = 1800
CAPABILITIES = ["ue5"]
TYPES = ["build"]                   # [중요] 유형 필터 — infer 를 훔치지 않는다


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

    def claim(self):
        st, got = self._call("POST", "/api/v1/tasks/claim",
                             {"worker_id": self.worker_id,
                              "capabilities": CAPABILITIES, "types": TYPES})
        return got if st == 200 else None

    def heartbeat(self, task_id: str):
        self._call("POST", f"/api/v1/tasks/{task_id}/heartbeat",
                   {"worker_id": self.worker_id})

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


def _log(root: Path, msg: str) -> None:
    line = f"{datetime.now().strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        p = root / ".ax" / "logs" / "claimer.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass                        # 로그 채널 — 본 작업을 막지 않는다 (의도된 fail-soft)


def _head_commit(tree: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def run_one(c: Client, task: dict, *, build_fn=None, log=None) -> dict:
    """잡 하나 실행 → 보고. 반환은 사람이 읽을 요약 (판단은 없다 — 사실만)."""
    log = log or (lambda m: _log(c.root, m))
    tid = task.get("task_id") or task.get("id") or ""
    kind = str(task.get("type") or "")
    if kind != "build":
        # [중요] 유형 필터를 뚫고 왔다면 그건 큐 버그다 — 조용히 삼키지 않고 되돌린다
        c.submit_fail(tid, "unsupported-type", f"claimer 는 build 만 다룬다: {kind!r}")
        return {"task": tid, "outcome": f"[중요] 지원 안 하는 유형 {kind!r} — submit-fail"}
    data = task.get("task_data") or {}
    tree = Path(data.get("tree") or c.root)
    log(f"[claim] {tid[:8]} build tree={tree}")
    c.heartbeat(tid)
    t0 = time.time()
    try:
        fn = build_fn
        if fn is None:
            from .build_local import local_build_fn
            fn = local_build_fn(project=c.project, ue5_cmd=c.ue5_cmd,
                                timeout=int(data.get("timeout") or BUILD_TIMEOUT))
        res = fn(tree)
    except Exception as e:                                    # noqa: BLE001
        # 빌드를 시작조차 못 했다 — 확인 불가는 통과가 아니다 (layer3 계약)
        c.submit_fail(tid, "build-setup", f"{type(e).__name__}: {e}")
        return {"task": tid, "outcome": f"[중요] 빌드 착수 실패 — {type(e).__name__}: {e}"}
    dt = time.time() - t0
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
    for a in argv:
        if a.startswith("--interval="):
            interval = max(5, int(a.split("=", 1)[1]))
    root = find_root()
    c = Client(root)
    log = lambda m: _log(root, m)                            # noqa: E731

    from . import ax_safety
    if once:
        ax_safety.setup_crash_handler(root / ".ax" / "logs", log)   # 가드 셋 중 크래시만
    else:
        ax_safety.apply_all(root / ".ax" / "logs", log)

    log(f"[boot] claimer worker_id={c.worker_id} project={c.project} "
        f"types={TYPES} caps={CAPABILITIES} {'once' if once else f'poll {interval}s'}")
    while True:
        task = c.claim()
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
    sys.exit(main())
