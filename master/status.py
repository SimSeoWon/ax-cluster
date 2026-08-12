"""클러스터 상태 — **자립형 HTML 한 장** (중 3.2, 사용자 요청 2026-08-08).

> *"머신들 구성 모습과 SSH로 상태 받아올 수 있으니까 상세 정보 표기하면 좋겠네.
> [뭘 시작했고, 온도, 전력량, cpu, gpu 상태 등]"*

## 🔴 서비스를 또 띄우지 않는다

포트를 하나 더 열면 **베어러 토큰과 ufw 규칙이 따라붙는다**(§9.5.6). 읽기 전용 화면에 그
공격면을 늘릴 이유가 없다 — 도메인 뷰어(소 2.4.2)가 이미 그 판단을 내렸고 **같은 표면을 쓴다**:
파일 한 장, 인라인 CSS·JS, 외부 자원 0. 두 화면은 서로 링크로 잇는다.

## 🔴 폴링 주기를 짧게 잡지 않는다

BC-250 은 이 프로젝트에서 **부하로 커널이 멈춘 전례**가 있다(리포트 10 §8). 그리고 `.33` 은
**사람의 기계**라 게스트 규칙이 적용된다. 그래서:

- `MIN_INTERVAL` **120초** — 그보다 자주 부르면 **거부한다**(`--force` 로만 넘긴다)
- 명령마다 짧은 타임아웃. 🔴 **닿지 않는 것을 "값 없음" 으로 접지 않는다** — *"닿지 않았다"* 로
  표시한다. 조용히 빈칸이 되면 사람이 *"괜찮은가 보다"* 로 읽는다
- 🔴 **전부 읽기 전용이다.** `systemctl is-active` · `cat /sys/...` · `nvidia-smi --query-gpu`
  · `git rev-parse`. 쓰는 명령은 하나도 없다

## ⚠️ 윈도우 SSH 에는 파이프가 없다 (실측)

`cmd.exe` 라 `| head` 가 `'head' is not recognized` 로 죽는다. **파이프 없이 부르고 파이썬에서
자른다.** 이 세션(2026-08-12)에도 같은 함정을 한 번 밟았다 — 문서에 적혀 있는데도.

## 무엇을 읽을 수 있는지는 **이미 실측했다** (2026-08-08, §3 미결 항목)

    BC-250 (.43)   /sys/class/drm/card*/device/hwmon/hwmon*/temp1_input · power1_average
                   → 55.0°C · 32.24W  ⬜ `gpu_busy_percent` 는 **이 보드에선 안 읽힌다**
    .2  RTX 3060   nvidia-smi --query-gpu=… → 42°C · 17.41W · 0% · 9959/12288 MiB
    .33 RTX 3080   같은 명령            → 33°C · 6.32W · 0% · 2509/10240 MiB

그래서 여기서는 **추측한 명령을 넣지 않는다** — 위 목록이 전부다.

## 🔴 첫 화면에 문제가 온다

도메인 뷰어가 *"경계 절 없는 도메인"* 을 맨 위에 올린 것과 같은 이유다. 예쁜 숫자보다
**무엇이 막혔는지**가 먼저다. 상태 색은 **아이콘+라벨과 함께** 쓴다 — 색만으로 의미를 전달하면
색을 못 보는 사람에게는 아무 정보가 아니다.
"""
from __future__ import annotations

import html
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MIN_INTERVAL = 120                # 🔴 초. BC-250 을 두드리지 않는다
SSH_TIMEOUT = 12
HTTP_TIMEOUT = 6
OUT_NAME = "cluster.html"
STAMP_NAME = ".cluster-status-stamp"

UNITS = ("ax-task-queue", "ax-broker", "ax-projects", "ax-indexer.path")

# 🔴 임계값은 **관례**이지 이 하드웨어의 실측 한계가 아니다 — 그렇게 표시한다.
#    (BC-250 은 팬리스이고 idle 55°C 가 실측이다. 스로틀 지점은 우리가 재지 않았다.)
TEMP_BANDS = ((60, "good"), (80, "warning"), (90, "serious"))

GOOD, WARN, SERIOUS, CRIT, UNKNOWN = "good", "warning", "serious", "critical", "unknown"
_ICON = {GOOD: "●", WARN: "▲", SERIOUS: "▲", CRIT: "✕", UNKNOWN: "?"}
_WORD = {GOOD: "정상", WARN: "주의", SERIOUS: "경고", CRIT: "위험", UNKNOWN: "모름"}


def band(temp) -> str:
    if temp is None:
        return UNKNOWN
    for limit, name in TEMP_BANDS:
        if temp < limit:
            return name
    return CRIT


# ── 수집 (소 3.2.1) — 🔴 전부 읽기 전용 ─────────────────────────────────────────

def _sh(args, timeout=SSH_TIMEOUT):
    """로컬 명령. `(rc, out)`. **예외를 던지지 않는다** — 실패도 사실이다."""
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (subprocess.SubprocessError, OSError) as e:
        return 1, f"{type(e).__name__}: {e}"
    from .source_text import decode          # 🔴 CP949 (윈도우 출력이 섞여 온다)
    return p.returncode, (decode(p.stdout or b"").text
                          + decode(p.stderr or b"").text).strip()


def _ssh(host, user, cmd, timeout=SSH_TIMEOUT):
    return _sh(["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={min(8, timeout)}",
                f"{user}@{host}", cmd], timeout=timeout)


def _api(url, *, token="", timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "null")
    except (urllib.error.URLError, OSError, ValueError):
        return None


@dataclass
class Gpu:
    name: str = ""
    temp: float | None = None
    watts: float | None = None
    util: float | None = None
    mem_used: int | None = None
    mem_total: int | None = None
    note: str = ""                 # ⬜ 안 읽히는 것을 적는다 (BC-250 의 gpu_busy_percent)


@dataclass
class Machine:
    host: str
    user: str = ""
    role: str = ""
    os: str = ""
    reachable: bool = False
    error: str = ""
    gpu: Gpu = field(default_factory=Gpu)
    load: str = ""
    commit: str = ""
    worktrees: list = field(default_factory=list)
    resident: str = ""             # 브로커가 본 상주 모델
    inflight: int = 0
    uptime: str = ""

    @property
    def status(self) -> str:
        if not self.reachable:
            # 🔴 요청자가 꺼져 있는 것은 **정상**이다 — 사람의 기계다
            return WARN if self.role == "requester" else CRIT
        return band(self.gpu.temp)

    @property
    def label(self) -> str:
        if not self.reachable:
            return "닿지 않음" + (" (사람의 기계 — 정상일 수 있다)"
                                if self.role == "requester" else "")
        return _WORD[self.status]


@dataclass
class Snapshot:
    at: str = ""
    seconds: float = 0.0
    units: dict = field(default_factory=dict)          # 유닛 → active/…
    machines: list = field(default_factory=list)
    queue: dict = field(default_factory=dict)
    endpoints: list = field(default_factory=list)
    tasks: list = field(default_factory=list)          # 🔴 "뭘 시작했고" 의 답 (소 3.2.3)
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    # 🔴 큐의 실제 응답 모양을 **재서** 맞췄다 (추측하지 않는다):
    #      {"tasks_by_status": {"cancelled":4,"failed":2,"submitted":2}, "works":7, "tasks":8}
    #    즉 `tasks` 는 **총계**이고 상태별은 `tasks_by_status` 다. 열린 것 = 종료 상태가 아닌 것.
    #    ⚠️ 종료 상태 목록은 큐가 정한다(`verified`·`cancelled`·`failed`) — 여기 박아 두면
    #    큐가 상태를 늘릴 때 조용히 틀린다. 그래서 **총계에서 종료분을 뺀다.**
    CLOSED = ("verified", "cancelled", "failed")

    @property
    def open_tasks(self) -> int:
        q = self.queue or {}
        by = q.get("tasks_by_status")
        if isinstance(by, dict):
            total = q.get("tasks")
            if isinstance(total, int):
                closed = sum(v for k, v in by.items()
                             if k in self.CLOSED and isinstance(v, int))
                return max(0, total - closed)
            return sum(v for k, v in by.items()
                       if k not in self.CLOSED and isinstance(v, int))
        return 0

    def to_dict(self) -> dict:
        d = {"at": self.at, "seconds": round(self.seconds, 1), "units": self.units,
             "queue": self.queue, "endpoints": self.endpoints,
             "problems": self.problems, "notes": self.notes, "machines": []}
        for m in self.machines:
            d["machines"].append({
                "host": m.host, "role": m.role, "os": m.os, "reachable": m.reachable,
                "error": m.error, "load": m.load, "commit": m.commit,
                "worktrees": m.worktrees, "resident": m.resident, "inflight": m.inflight,
                "uptime": m.uptime, "status": m.status,
                "gpu": {"name": m.gpu.name, "temp": m.gpu.temp, "watts": m.gpu.watts,
                        "util": m.gpu.util, "mem_used": m.gpu.mem_used,
                        "mem_total": m.gpu.mem_total, "note": m.gpu.note}})
        return d


_NVIDIA = ("nvidia-smi --query-gpu=name,temperature.gpu,power.draw,utilization.gpu,"
           "memory.used,memory.total --format=csv,noheader,nounits")
# 🔴 리눅스(BC-250)는 hwmon 을 직접 읽는다 — `gpu_busy_percent` 는 **이 보드에서 안 읽힌다**(실측)
_HWMON = ("cat /sys/class/drm/card*/device/hwmon/hwmon*/temp1_input "
          "/sys/class/drm/card*/device/hwmon/hwmon*/power1_average 2>/dev/null; "
          "echo ---; cat /proc/loadavg; echo ---; uptime -p")


def _num(s):
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def read_machine(host, user, path, role, os_hint="") -> Machine:
    """머신 하나를 **읽기만** 한다. ⚠️ 윈도우엔 파이프를 쓰지 않는다."""
    m = Machine(host=host, user=user, role=role, os=os_hint)
    rc, out = _ssh(host, user, "echo ax-ok")
    if rc != 0 or "ax-ok" not in out:
        m.error = (out or "응답 없음")[:120]
        return m
    m.reachable = True

    windows = os_hint == "windows" or "\\" in str(path)
    if windows:
        # ⚠️ 파이프 금지 — `| head` 가 `'head' is not recognized` 로 죽는다(실측)
        rc, out = _ssh(host, user, _NVIDIA)
        if rc == 0 and "," in out:
            first = [ln for ln in out.splitlines() if "," in ln][:1]
            f = [x.strip() for x in first[0].split(",")] if first else []
            if len(f) >= 6:
                m.gpu = Gpu(name=f[0], temp=_num(f[1]), watts=_num(f[2]),
                            util=_num(f[3]), mem_used=int(_num(f[4]) or 0),
                            mem_total=int(_num(f[5]) or 0))
        else:
            m.gpu.note = "nvidia-smi 를 못 읽었다"
    else:
        rc, out = _ssh(host, user, _HWMON)
        blocks = (out or "").split("---")
        vals = [_num(x) for x in blocks[0].split()] if blocks else []
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            # temp1_input 은 밀리도, power1_average 는 마이크로와트다
            m.gpu = Gpu(name="AMD BC-250 (gfx1013)", temp=vals[0] / 1000.0,
                        watts=vals[1] / 1e6,
                        note="⬜ `gpu_busy_percent` 는 이 보드에서 안 읽힌다 (실측)")
        if len(blocks) > 1:
            m.load = " ".join(blocks[1].split()[:3])
        if len(blocks) > 2:
            m.uptime = blocks[2].strip()[:40]

    rc, out = _ssh(host, user, f'git -C "{path}" rev-parse --short HEAD')
    if rc == 0 and out:
        m.commit = out.split()[0]
    rc, out = _ssh(host, user, f'git -C "{path}" worktree list')
    if rc == 0:
        m.worktrees = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip()]
    return m


def collect(*, project: str = "", token: str = "", force: bool = False,
            state_dir=None) -> Snapshot:
    """스냅샷 한 번. 🔴 **`MIN_INTERVAL` 보다 자주 부르면 거부한다.**"""
    t0 = time.time()
    snap = Snapshot(at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"))
    stamp = Path(state_dir or Path.home() / ".config" / "ax-cluster") / STAMP_NAME
    if not force and stamp.is_file():
        try:
            last = float(stamp.read_text(encoding="utf-8").strip() or 0)
        except (ValueError, OSError):
            last = 0.0
        gap = time.time() - last
        if gap < MIN_INTERVAL:
            # 🔴 BC-250 은 부하로 커널이 멈춘 전례가 있다 — 자주 두드리지 않는다
            raise RuntimeError(
                f"{gap:.0f}초 전에 이미 수집했다 — 최소 간격 {MIN_INTERVAL}초. "
                f"BC-250 을 자주 두드리지 않는다(부하로 커널이 멈춘 전례). "
                f"정말 필요하면 --force")

    # ① 마스터 서비스 — 로컬, 읽기 전용
    for u in UNITS:
        rc, out = _sh(["systemctl", "is-active", u], timeout=6)
        snap.units[u] = (out or "unknown").splitlines()[0].strip()
        if snap.units[u] != "active":
            snap.problems.append(f"서비스 `{u}` 가 {snap.units[u]} 다")

    if not token:
        try:
            token = (Path.home() / ".config" / "ax-cluster" / "token").read_text(
                encoding="utf-8").strip()
        except OSError:
            snap.notes.append("⚠️ 토큰을 못 읽어 큐·브로커 상태를 비웠다")

    # ② 큐 · 브로커 — 🔴 "뭘 시작했고" 의 본체 (소 3.2.3)
    if token:
        q = _api("http://127.0.0.1:8101/api/v1/status", token=token)
        if isinstance(q, dict):
            snap.queue = q
        else:
            snap.problems.append("큐(8101) 가 상태를 주지 않는다")
        # 🔴 **"뭘 시작했고" 는 이것이다** (소 3.2.3) — 종료되지 않은 태스크와 누가 잡았나.
        #    ⚠️ 종료 상태를 코드에 박지 않는다: `Snapshot.CLOSED` 한 곳에서만 정한다.
        tl = _api("http://127.0.0.1:8101/api/v1/tasks", token=token)
        if isinstance(tl, list):
            for x in tl:
                if not isinstance(x, dict) or x.get("status") in Snapshot.CLOSED:
                    continue
                snap.tasks.append({
                    "task_id": str(x.get("task_id") or "")[:8],
                    "status": str(x.get("status") or ""),
                    "worker": str(x.get("assignee") or x.get("worker_id") or ""),
                    "file": str(x.get("target_file") or ""),
                    "since": str(x.get("claimed_at") or x.get("created") or "")[:19],
                    "beat": str(x.get("last_heartbeat") or "")[:19],
                    "attempts": x.get("attempt_count") or 0,
                    "requires": x.get("requires") or []})
            # 🔴 오래 잡혀 있는 것은 문제다 — 리스가 1200초인데 하트비트가 멈췄으면 좀비다
            stale = [x for x in snap.tasks
                     if x["status"] == "claimed" and not x["beat"]]
            for x in stale:
                snap.problems.append(
                    f"태스크 `{x['task_id']}` 가 하트비트 없이 claimed 다 "
                    f"({x['worker'] or '워커 미상'}) — 리스 만료를 기다리는 중일 수 있다")

        h = _api("http://127.0.0.1:8102/health", token=token)
        if isinstance(h, dict):
            snap.endpoints = h.get("endpoints") or []
            for e in snap.endpoints:
                if not e.get("healthy"):
                    snap.problems.append(
                        f"추론 엔드포인트 `{e.get('name')}` 가 unhealthy — "
                        f"{e.get('last_error') or '사유 없음'}")
        else:
            snap.problems.append("브로커(8102) 가 상태를 주지 않는다")

    # ③ 머신 — 레지스트리가 아는 것만. 🔴 목록을 코드에 박지 않는다
    try:
        from .client import bundle
        shops = bundle.workshops(project) if project else []
        if not shops:
            from .projects.config import Registry
            reg = Registry.load()
            name = project or (reg.active or "")
            shops = bundle.workshops(name) if name else []
    except Exception as e:                                   # noqa: BLE001
        shops = []
        snap.notes.append(f"⚠️ 레지스트리에서 머신 목록을 못 읽었다: {e}")

    by_host = {str(e.get("host", "")).split(":")[0]: e for e in snap.endpoints}
    for host, user, path, _driven, role in shops:
        m = read_machine(host, user, path, role)
        e = by_host.get(host)
        if e:
            m.resident = e.get("resident") or ""
            m.inflight = int(e.get("inflight") or 0)
        snap.machines.append(m)
        if m.status in (CRIT, SERIOUS):
            snap.problems.append(f"`{host}` — {m.label}"
                                 + (f" ({m.error})" if m.error else ""))

    snap.seconds = time.time() - t0
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    return snap


# ── 표시 (소 3.2.2) — 🔴 도메인 뷰어와 같은 표면 ────────────────────────────────
#
# 🔴 상태는 **아이콘 + 라벨 + 색** 셋이다. 색만으로 의미를 전달하지 않는다.
# 🔴 히어로 숫자는 **하나뿐**이다 (열린 태스크) — 대시보드가 이끄는 숫자.
# ⚠️ 추세 스파크라인을 넣지 않았다. 수집 주기가 길어(최소 120초) 이력이 희박하고,
#    희박한 이력으로 그린 선은 **없는 추세를 있는 것처럼** 보이게 한다.

_CSS = """
:root{
 --bg:#fcfcfb;--fg:#0b0b0b;--dim:#52514e;--line:#e2e2e0;--card:#fff;
 --good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--unknown:#8a8a86;
 --track:#ececea;
}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#1a1a19;--fg:#fff;--dim:#c3c2b7;--line:#2f2f2c;--card:#212120;
 --good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--unknown:#9a9a94;
 --track:#2b2b28;
}}
:root[data-theme="dark"]{
 --bg:#1a1a19;--fg:#fff;--dim:#c3c2b7;--line:#2f2f2c;--card:#212120;
 --good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--unknown:#9a9a94;
 --track:#2b2b28;
}
*{box-sizing:border-box}
body{margin:0;padding:1.5rem;background:var(--bg);color:var(--fg);
 font:15px/1.6 -apple-system,'Noto Sans KR',Segoe UI,sans-serif}
h1{font-size:1.35rem;margin:0 0 .15rem}
h2{font-size:.95rem;margin:1.6rem 0 .5rem;color:var(--dim);font-weight:600;
 text-transform:none;letter-spacing:.01em}
.sub{color:var(--dim);font-size:.85rem}
a{color:inherit}
.hero{margin:1.1rem 0 .2rem;display:flex;align-items:baseline;gap:.6rem}
.hero b{font-size:3rem;line-height:1;font-weight:650}
.hero span{color:var(--dim);font-size:.9rem}
.band{border:1px solid var(--line);border-left:4px solid var(--critical);
 background:var(--card);border-radius:8px;padding:.7rem .9rem;margin:.9rem 0}
.band.ok{border-left-color:var(--good)}
.band ul{margin:.4rem 0 0;padding-left:1.1rem}
.grid{display:grid;gap:.7rem;grid-template-columns:repeat(auto-fit,minmax(255px,1fr))}
.tile{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.8rem .9rem}
.tile .who{font-family:ui-monospace,Menlo,monospace;font-weight:650}
.tile .val{font-size:1.9rem;font-weight:650;line-height:1.15;margin:.35rem 0 .1rem}
.tile .val small{font-size:.85rem;font-weight:500;color:var(--dim)}
.tile dl{margin:.5rem 0 0;display:grid;grid-template-columns:auto 1fr;gap:.15rem .55rem;
 font-size:.82rem}
.tile dt{color:var(--dim)}
.tile dd{margin:0;font-variant-numeric:tabular-nums}
.st{display:inline-flex;align-items:center;gap:.3rem;font-size:.8rem;font-weight:600;
 white-space:nowrap}
.st i{font-style:normal}
.good{color:var(--good)}.warning{color:var(--warning)}.serious{color:var(--serious)}
.critical{color:var(--critical)}.unknown{color:var(--unknown)}
.meter{height:6px;border-radius:3px;background:var(--track);margin:.5rem 0 .1rem;
 overflow:hidden}
.meter i{display:block;height:100%;border-radius:3px}
.scale{display:flex;justify-content:space-between;color:var(--dim);font-size:.7rem;
 margin:0 0 .15rem}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{border:1px solid var(--line);border-radius:999px;padding:.2rem .6rem;font-size:.8rem;
 background:var(--card);display:inline-flex;gap:.35rem;align-items:center}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{text-align:left;padding:.35rem .5rem;border-bottom:1px solid var(--line)}
td.n{font-variant-numeric:tabular-nums}
code{font-family:ui-monospace,Menlo,monospace;font-size:.85em}
.foot{color:var(--dim);font-size:.78rem;margin-top:1.6rem;border-top:1px solid var(--line);
 padding-top:.7rem}
"""


def short_model(name: str, *, limit: int = 30) -> str:
    """모델 이름을 사람이 읽을 만큼만. 🔴 **토큰 중간에서 자르지 않는다.**

    실측(2026-08-12 화면 확인): `Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M` 를 28자로 자르니
    `…GGUF:IQ` 가 되어 **양자화 접미사가 반쪽**이 됐다 — `IQ2_M` 인지 `IQ4` 인지 알 수 없으면
    그 값은 정보가 아니다. 그래서 뒤에서부터 남기고(`:` 뒤가 태그다) 앞을 줄인다.
    """
    n = str(name or "").split("/")[-1]          # 레지스트리 경로는 버린다
    if len(n) <= limit:
        return n
    base, _, tag = n.rpartition(":")
    if tag and len(tag) + 2 < limit:
        keep = limit - len(tag) - 2             # `…` + `:`
        return f"{base[:keep]}…:{tag}"
    return n[:limit - 1] + "…"


def _st(kind: str, text: str = "") -> str:
    return (f'<span class="st {kind}"><i>{_ICON[kind]}</i>'
            f'{html.escape(text or _WORD[kind])}</span>')


TEMP_MAX = 100          # 미터의 오른쪽 끝. 🔴 눈금 의미를 화면에 적는다(안 적으면 장식이다)


def _meter(temp) -> str:
    """온도 미터. 🔴 트랙은 **채움과 같은 색의 밝은 단계**다 — dataviz 규약(같은 램프).

    회색 트랙을 쓰면 상태가 채워진 부분에서만 읽히는데, 같은 램프면 **바 전체에서** 읽힌다.
    `color-mix` 미지원 브라우저를 위해 중립 트랙을 먼저 선언해 둔다(선언 순서가 폴백이다).
    """
    if temp is None:
        return ""
    pct = max(4, min(100, round(temp / TEMP_MAX * 100)))
    c = f"var(--{band(temp)})"
    warn, ser = TEMP_BANDS[0][0], TEMP_BANDS[1][0]
    return (f'<div class="meter" role="img" aria-label="온도 {temp:.0f}도, 눈금 0에서 '
            f'{TEMP_MAX}도" style="background:var(--track);'
            f'background:color-mix(in oklab,{c} 20%,var(--track))">'
            f'<i style="width:{pct}%;background:{c}"></i></div>'
            f'<div class="scale"><span>0</span>'
            f'<span>주의 {warn} · 경고 {ser}</span><span>{TEMP_MAX}°C</span></div>')


def render(snap: Snapshot, *, viewer_link: str = "") -> str:
    """자립형 HTML. 🔴 외부 자원 0 · 상태는 아이콘+라벨+색."""
    e = html.escape
    p = [f'<h1>AX 클러스터 상태</h1>',
         f'<div class="sub">{e(snap.at)} 수집 · {snap.seconds:.0f}초 소요 · '
         f'🔴 최소 간격 {MIN_INTERVAL}초(BC-250 을 자주 두드리지 않는다)</div>']

    # 🔴 히어로는 하나 — 지금 큐에 무엇이 있나
    p += [f'<div class="hero"><b>{snap.open_tasks}</b>'
          f'<span>큐에 열린 태스크</span></div>']

    # 🔴 첫 화면에 문제가 온다 (도메인 뷰어와 같은 판단)
    if snap.problems:
        p.append('<div class="band"><b>🔴 문제 %d건</b><ul>%s</ul></div>'
                 % (len(snap.problems),
                    "".join(f"<li>{e(x)}</li>" for x in snap.problems)))
    else:
        p.append('<div class="band ok">%s <b>문제 없음</b> — 서비스 %d개 active, '
                 '머신 %d대 응답</div>'
                 % (_st(GOOD, "정상"), sum(1 for v in snap.units.values() if v == "active"),
                    sum(1 for m in snap.machines if m.reachable)))

    p.append("<h2>머신</h2><div class=\"grid\">")
    for m in snap.machines:
        g = m.gpu
        val = (f'{g.temp:.0f}<small>°C</small>' if g.temp is not None
               else '<small>온도 못 읽음</small>')
        rows = []
        if g.watts is not None:
            rows.append(("전력", f"{g.watts:.2f} W"))
        if g.util is not None:
            rows.append(("GPU 사용", f"{g.util:.0f} %"))
        if g.mem_total:
            rows.append(("GPU 메모리", f"{g.mem_used:,} / {g.mem_total:,} MiB"))
        if m.load:
            rows.append(("load", m.load))
        if m.uptime:
            rows.append(("가동", m.uptime))
        if m.resident:
            rows.append(("상주 모델", short_model(m.resident)))
        if m.commit:
            rows.append(("체크아웃", m.commit))
        if m.worktrees:
            rows.append(("워크트리", f"{len(m.worktrees)}개"))
        p.append(
            '<div class="tile"><div style="display:flex;justify-content:space-between;'
            'align-items:center;gap:.5rem"><span class="who">%s</span>%s</div>'
            '<div class="sub">%s · %s</div><div class="val">%s</div>%s'
            '<dl>%s</dl>%s</div>'
            % (e(m.host), _st(m.status, m.label),
               e(m.role or "?"), e(g.name or m.os or "?"), val, _meter(g.temp),
               "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in rows),
               f'<div class="sub">{e(g.note)}</div>' if g.note else ""))
    p.append("</div>")

    # 🔴 "뭘 시작했고" — 사용자가 요청한 그 항목이다. 없으면 없다고 적는다.
    p.append("<h2>진행 중인 작업</h2>")
    if snap.tasks:
        p.append('<table><tr><th>태스크</th><th>상태</th><th>맡은 워커</th>'
                 '<th>대상 파일</th><th>이후</th><th class="n">시도</th></tr>')
        for x in snap.tasks:
            kind = {"claimed": GOOD, "pending": UNKNOWN,
                    "needs_revision": WARN, "submitted": WARN}.get(x["status"], UNKNOWN)
            p.append("<tr><td><code>%s</code></td><td>%s</td><td><code>%s</code></td>"
                     "<td><code>%s</code></td><td class=\"n\">%s</td>"
                     "<td class=\"n\">%s</td></tr>"
                     % (e(x["task_id"]), _st(kind, x["status"]),
                        e(x["worker"] or "—"),
                        e(x["file"].split("/")[-1] or "—"),
                        e(x["since"].replace("T", " ")), x["attempts"]))
        p.append("</table>")
    else:
        p.append('<div class="sub">열린 태스크가 없다 — 큐가 비어 있다</div>')

    p.append("<h2>마스터 서비스</h2><div class=\"chips\">")
    for u, v in snap.units.items():
        kind = GOOD if v == "active" else (UNKNOWN if v == "unknown" else CRIT)
        p.append(f'<span class="chip">{_st(kind, v)}<code>{e(u)}</code></span>')
    p.append("</div>")

    if snap.endpoints:
        p.append("<h2>추론 엔드포인트</h2><table><tr><th>이름</th><th>호스트</th>"
                 "<th>상태</th><th>상주 모델</th><th class=\"n\">inflight</th>"
                 "<th class=\"n\">보유</th></tr>")
        for ep in snap.endpoints:
            ok = bool(ep.get("healthy"))
            p.append("<tr><td><code>%s</code></td><td><code>%s</code></td><td>%s</td>"
                     "<td><code>%s</code></td><td class=\"n\">%s</td>"
                     "<td class=\"n\">%s</td></tr>"
                     % (e(str(ep.get("name", ""))), e(str(ep.get("host", ""))),
                        _st(GOOD if ok else CRIT, "healthy" if ok else "unhealthy"),
                        e(short_model(str(ep.get("resident") or "(없음)"), limit=34)),
                        ep.get("inflight", 0), len(ep.get("models") or [])))
        p.append("</table>")

    if snap.queue:
        p.append("<h2>큐</h2><table>")
        for k, v in sorted(snap.queue.items()):
            if isinstance(v, (str, int, float)):
                p.append(f'<tr><td>{e(str(k))}</td><td class="n">{e(str(v))}</td></tr>')
        p.append("</table>")

    if snap.notes:
        p.append("<h2>수집 결손</h2><ul>%s</ul>"
                 % "".join(f"<li>{e(n)}</li>" for n in snap.notes))

    foot = ("🔴 이 화면은 <b>읽기 전용 수집</b>이다 — <code>systemctl is-active</code> · "
            "<code>cat /sys/…</code> · <code>nvidia-smi --query-gpu</code> · "
            "<code>git rev-parse</code>. 쓰는 명령은 없다.<br>"
            "⚠️ 온도 구간(60/80/90°C)은 <b>관례</b>이고 이 하드웨어의 실측 스로틀 지점이 "
            "아니다. BC-250 은 팬리스이고 idle 55°C 가 실측값이다.<br>"
            "⚠️ 추세 그래프를 넣지 않았다 — 수집 주기가 길어 이력이 희박하고, 희박한 이력으로 "
            "그린 선은 <b>없는 추세를 있는 것처럼</b> 보이게 한다.")
    if viewer_link:
        foot += f'<br>같은 표면의 다른 화면: <a href="{e(viewer_link)}">도메인 뷰어</a>'
    p.append(f'<div class="foot">{foot}</div>')

    return ("<!doctype html><html lang=ko><head><meta charset=utf-8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
            "<title>AX 클러스터 상태</title><style>" + _CSS + "</style></head><body>"
            + "\n".join(p) + "</body></html>")


def write(snap: Snapshot, out: Path, *, viewer_link: str = "") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(render(snap, viewer_link=viewer_link), encoding="utf-8")
    tmp.replace(out)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────────
#
#   python -m master.status show [프로젝트]        터미널에 요약 (수집만)
#   python -m master.status html [프로젝트]        HTML 한 장을 쓴다
#   🔴 `--force` 없이는 최소 간격 안에 두 번 수집하지 않는다.

def main(argv) -> int:
    cmd = (argv[0] if argv else "show").strip()
    force = "--force" in argv
    rest = [a for a in argv[1:] if not a.startswith("--")]
    project = rest[0] if rest else ""
    if cmd not in ("show", "html"):
        print("  show [프로젝트] [--force] | html [프로젝트] [--force]")
        return 2
    try:
        snap = collect(project=project, force=force)
    except RuntimeError as e:
        print(f"🔴 {e}")
        return 1

    if cmd == "show":
        print(f"{snap.at} · {snap.seconds:.0f}초 · 열린 태스크 {snap.open_tasks}")
        for u, v in snap.units.items():
            print(f"  {'✅' if v == 'active' else '🔴'} {u}: {v}")
        for m in snap.machines:
            g = m.gpu
            bits = [f"{m.host} [{m.role}]", m.label]
            if g.temp is not None:
                bits.append(f"{g.temp:.0f}°C")
            if g.watts is not None:
                bits.append(f"{g.watts:.2f}W")
            if m.resident:
                bits.append(m.resident.split("/")[-1][:24])
            if m.commit:
                bits.append(m.commit)
            print("  " + " · ".join(bits) + (f" — {m.error}" if m.error else ""))
        for x in snap.problems:
            print(f"  🔴 {x}")
        for n in snap.notes:
            print(f"  {n}")
        return 0

    from .context_search.paths import resolve
    paths = resolve(project)
    out = write(snap, paths.root / OUT_NAME, viewer_link="domains.html")
    print(f"{out}  ({out.stat().st_size:,} bytes)")
    print(f"문제 {len(snap.problems)}건 · 머신 {len(snap.machines)}대 · "
          f"열린 태스크 {snap.open_tasks}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
