"""기계별 홈 안내서(`CLAUDE.md`·`AGENTS.md`) 대조·동기화 (`#861`).

왜 있나
    `.2` 의 홈 안내서는 **복사본**이다(심볼릭 링크를 걸 ax-cluster 클론이 없다). 복사본은
    낡는다 — `#861` 에서 `.2` 의 `AGENTS.md` 는 아직 「상주 AxWorker」를 말하는데 같은 기계의
    `CLAUDE.md` 는 「데몬 없음」을 말했다. 손으로 `scp` 하던 갱신을 명령 하나로 만들고,
    무엇이 정본과 다른지를 먼저 보여 준다.

대상 표 (`TARGETS`, 선언형 — 네 대)
    .2   janus  windows  C:\\Users\\janus\\CLAUDE.md   copy       machines/win-worker-2.md
    .2   janus  windows  C:\\Users\\janus\\AGENTS.md   copy       같은 정본에서 **유도**(`derive_agents`)
    .33  user   windows  C:\\Users\\USER\\CLAUDE.md    copy       machines/win-main-33.md
    .33  user   windows  C:\\Users\\USER\\AGENTS.md    absent_ok  (없음이 정상 — 만들지 않는다)
    .43  sim    linux    /home/sim/CLAUDE.md          symlink    → ~/ax-cluster/machines/bc250-1.md
    .43  sim    linux    /home/sim/AGENTS.md          absent_ok
    .57  sim    local    /home/sim/CLAUDE.md          symlink    → machines/sim-desktop.md
    .57  sim    local    /home/sim/AGENTS.md          symlink    → machines/sim-desktop-agents.md

동작
    기본은 **계획(대조)만** 한다 — 읽기 전용. 대상마다 한 줄 `OK`/`DIFF`/`ABSENT`/`FAIL`
    (sha256 앞 12자, 기대 대 실측). `--apply` 는 **`copy` 대상의 `DIFF` 만** 쓴다: 원격 파일이
    있으면 먼저 `<경로>.bak-<YYYYmmdd-HHMMSS>` 백업을 만들고, 전송은 `bundle._remote_write`
    (scp + sha256 되읽기)를 그대로 쓴다. 쓴 뒤 다시 대조해 결과를 찍는다.

[중요] 심볼릭 링크는 **검증만** 한다 — 링크인지, 가리키는 곳이 기대 경로인지. 일반 파일이거나
    다른 곳을 가리키면 `FAIL` 로 보고하고 **쓰거나 바꾸지 않는다**(`~/CLAUDE.md` 는 링크여야 한다).
[중요] `.33` 은 사람의 기계이고 마스터는 손님이다 — `AGENTS.md` 가 없다는 사실을 보고만 하고
    **절대 만들지 않는다.** 쓰기는 `kind == "copy"` 에서만 일어난다.
[중요] 조회 실패(SSH rc≠0 · 255 · 해석 불가 출력)는 `FAIL` 이지 `ABSENT` 가 아니다 — 「못 봤다」를
    「없다」로 읽지 않는다(`#861` T1 과 같은 원칙). `FAIL` 대상은 `--apply` 에서도 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import bundle

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Target:
    host: str
    user: str
    os: str              # "windows" | "linux" | "local"
    path: str            # 원격(또는 로컬) 절대경로
    kind: str            # "copy" | "symlink" | "absent_ok"
    canonical: str = ""  # 저장소 기준 상대경로
    derive: str | None = None   # None | "agents"
    link_root: str = ""  # symlink 기대 대상의 클론 루트 (그 기계 기준)

    @property
    def link_target(self) -> str:
        return f"{self.link_root}/{self.canonical}"

    @property
    def label(self) -> str:
        return f"{self.host} {self.path}"


TARGETS = (
    Target("192.168.0.2", "janus", "windows", r"C:\Users\janus\CLAUDE.md", "copy",
           "machines/win-worker-2.md"),
    Target("192.168.0.2", "janus", "windows", r"C:\Users\janus\AGENTS.md", "copy",
           "machines/win-worker-2.md", derive="agents"),
    Target("192.168.0.33", "user", "windows", r"C:\Users\USER\CLAUDE.md", "copy",
           "machines/win-main-33.md"),
    Target("192.168.0.33", "user", "windows", r"C:\Users\USER\AGENTS.md", "absent_ok"),
    Target("192.168.0.43", "sim", "linux", "/home/sim/CLAUDE.md", "symlink",
           "machines/bc250-1.md", link_root="/home/sim/ax-cluster"),
    Target("192.168.0.43", "sim", "linux", "/home/sim/AGENTS.md", "absent_ok"),
    Target("192.168.0.57", "sim", "local", "/home/sim/CLAUDE.md", "symlink",
           "machines/sim-desktop.md", link_root="/home/sim/ax-cluster"),
    Target("192.168.0.57", "sim", "local", "/home/sim/AGENTS.md", "symlink",
           "machines/sim-desktop-agents.md", link_root="/home/sim/ax-cluster"),
)

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class GuideError(RuntimeError):
    """정본 모양이 바뀌어 유도할 수 없다 — fail-closed."""


def derive_agents(text: str) -> str:
    """`.2` 의 `AGENTS.md` 를 `CLAUDE.md` 정본에서 결정적으로 만든다.

    첫 줄의 `# CLAUDE.md` → `# AGENTS.md`, 머리 블록(첫 `## ` 앞) 안의
    `C:/Users/janus/CLAUDE.md` → `C:/Users/janus/AGENTS.md`. 그 밖은 바이트 그대로.
    """
    if not text.startswith("# CLAUDE.md"):
        raise GuideError("정본 첫 줄이 `# CLAUDE.md` 로 시작하지 않는다 — 유도 규칙을 다시 본다")
    text = "# AGENTS.md" + text[len("# CLAUDE.md"):]
    m = re.search(r"^## ", text, flags=re.M)
    cut = m.start() if m else len(text)
    head = text[:cut].replace("C:/Users/janus/CLAUDE.md", "C:/Users/janus/AGENTS.md")
    return head + text[cut:]


def want_content(t: Target, root: Path = REPO_ROOT) -> str:
    # newline="" — 줄바꿈을 바꾸지 않는다(해시가 정본 바이트와 같아야 한다)
    with open(root / t.canonical, encoding="utf-8", newline="") as f:
        text = f.read()
    return derive_agents(text) if t.derive == "agents" else text


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── 조회 ──────────────────────────────────────────────────────────────────
# 결과는 튜플 하나: ("file", sha) · ("link", 대상) · ("absent", "") · ("other", 설명)
#                  · ("error", 사유) — error 는 **못 봤다**이지 없다가 아니다.

def _q(p: str) -> str:
    return "'" + p.replace("'", "'\\''") + "'"


def windows_query_cmd(path: str) -> str:
    return (f"powershell -NoProfile -Command \"if(Test-Path -LiteralPath '{path}')"
            f"{{(Get-FileHash -LiteralPath '{path}' -Algorithm SHA256).Hash}}"
            f"else{{'AX_ABSENT'}}\"")


def linux_query_cmd(path: str) -> str:
    p = _q(path)
    return (f"if [ -L {p} ]; then echo AX_LINK=$(readlink {p}); "
            f"elif [ -f {p} ]; then echo AX_FILE; sha256sum {p} | cut -d' ' -f1; "
            f"elif [ -e {p} ]; then echo AX_OTHER; else echo AX_ABSENT; fi")


def query_remote(t: Target, runner) -> tuple:
    cmd = windows_query_cmd(t.path) if t.os == "windows" else linux_query_cmd(t.path)
    rc, out = runner(t.host, t.user, cmd)
    out = (out or "").strip()
    if rc != 0:
        return ("error", f"조회 실패 rc={rc} {out[:80]}")
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if t.os == "windows":
        if lines == ["AX_ABSENT"]:
            return ("absent", "")
        if len(lines) == 1 and _HEX64.match(lines[0]):
            return ("file", lines[0].lower())
        return ("error", f"해석 불가 출력 {out[:80]!r}")
    if lines == ["AX_ABSENT"]:
        return ("absent", "")
    if lines == ["AX_OTHER"]:
        return ("other", "파일도 링크도 아니다")
    if len(lines) == 1 and lines[0].startswith("AX_LINK="):
        return ("link", lines[0][len("AX_LINK="):])
    if len(lines) == 2 and lines[0] == "AX_FILE" and _HEX64.match(lines[1]):
        return ("file", lines[1].lower())
    return ("error", f"해석 불가 출력 {out[:80]!r}")


def query_local(path: str) -> tuple:
    try:
        if os.path.islink(path):
            return ("link", os.readlink(path))
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return ("file", hashlib.sha256(f.read()).hexdigest())
        if os.path.lexists(path):
            return ("other", "파일도 링크도 아니다")
        return ("absent", "")
    except OSError as e:
        return ("error", f"{type(e).__name__}: {e}")


def _resolve_link(path: str, got: str) -> str:
    if got.startswith("/"):
        return os.path.normpath(got)
    return os.path.normpath(os.path.join(os.path.dirname(path), got))


@dataclass
class Result:
    target: Target
    status: str          # OK | DIFF | ABSENT | FAIL
    detail: str
    got: tuple = ("", "")
    want: str = ""

    @property
    def line(self) -> str:
        return f"[{self.status:6}] {self.target.label} ({self.target.kind}) — {self.detail}"


def evaluate(t: Target, *, runner, local, root: Path = REPO_ROOT) -> Result:
    got = local(t.path) if t.os == "local" else query_remote(t, runner)
    kind, val = got
    if kind == "error":
        return Result(t, "FAIL", val, got)
    if t.kind == "absent_ok":
        if kind == "absent":
            return Result(t, "ABSENT", "없음 (정상 — 만들지 않는다)", got)
        return Result(t, "FAIL", f"없어야 하는데 있다({kind}) — 쓰지 않는다, 사람이 판단", got)
    if t.kind == "symlink":
        want = t.link_target
        if kind != "link":
            return Result(t, "FAIL", f"링크가 아니다({kind}) — 기대 → {want} · 쓰지 않는다", got)
        if _resolve_link(t.path, val) != os.path.normpath(want):
            return Result(t, "FAIL", f"링크 대상이 다르다 → {val} (기대 {want}) · 쓰지 않는다",
                          got)
        return Result(t, "OK", f"→ {val}", got)
    # copy
    try:
        want = sha(want_content(t, root))
    except (OSError, GuideError) as e:
        return Result(t, "FAIL", f"정본을 못 만든다 — {e}", got)
    if kind == "absent":
        return Result(t, "DIFF", f"기대 {want[:12]} 실측 없음", got, want)
    if kind != "file":
        return Result(t, "FAIL", f"파일이 아니다({kind}: {val}) — 쓰지 않는다", got, want)
    if val == want:
        return Result(t, "OK", f"{want[:12]}", got, want)
    return Result(t, "DIFF", f"기대 {want[:12]} 실측 {val[:12]}", got, want)


def backup_cmd(path: str, stamp: str) -> str:
    return (f"powershell -NoProfile -Command \"Copy-Item -LiteralPath '{path}' "
            f"-Destination '{path}.bak-{stamp}'\"")


def _facts(t: Target) -> "bundle.HostFacts":
    return bundle.HostFacts(host=t.host, user=t.user, path="", driven="ssh",
                            os="windows" if t.os == "windows" else "linux")


def _default_writer(facts, abs_path: str, content: str) -> str:
    return bundle._remote_write(facts, abs_path, content, base="abs")


def apply_one(r: Result, *, runner, writer, stamp: str, root: Path = REPO_ROOT) -> str:
    """`copy` 대상의 DIFF 하나를 쓴다. 반환은 출력할 한 줄. 예외를 던지지 않는다."""
    t = r.target
    if t.kind != "copy" or r.status != "DIFF":      # 방어 — 호출부가 이미 거른다
        return f"[건너뜀] {t.label} — 쓰기 대상 아님"
    if t.os != "windows":
        return f"[건너뜀] {t.label} — copy 쓰기는 윈도우 대상만 정의돼 있다"
    if r.got[0] == "file":
        bk = backup_cmd(t.path, stamp)
        rc, out = runner(t.host, t.user, bk)
        if rc != 0:
            return f"[실패] {t.label} — 백업 실패 rc={rc} {(out or '')[:80]} · 쓰지 않았다"
        note = f"백업 {t.path}.bak-{stamp}"
    else:
        note = "원격에 없음 — 백업 없이 생성"
    try:
        writer(_facts(t), t.path, want_content(t, root))
    except Exception as e:                                           # noqa: BLE001
        return f"[실패] {t.label} — 쓰기 실패 {e}"
    return f"[썼다] {t.label} — {note}"


def run(*, apply: bool = False, host: str = "", runner=None, writer=None, local=None,
        now=None, root: Path = REPO_ROOT, targets=TARGETS, out=print) -> int:
    runner = runner or bundle._ssh
    writer = writer or _default_writer
    local = local or query_local
    hosts = sorted({t.host for t in targets})
    if host:
        if host not in hosts:
            out(f"[home-guides] [실패] --host={host} 는 대상 표에 없다 — {', '.join(hosts)}")
            return 2
        targets = tuple(t for t in targets if t.host == host)

    results = [evaluate(t, runner=runner, local=local, root=root) for t in targets]
    for r in results:
        out(r.line)
    bad = [r for r in results if r.status in ("DIFF", "FAIL")]
    if not apply:
        if bad:
            out(f"[home-guides] 다름·실패 {len(bad)}건 — copy 의 DIFF 만 --apply 로 쓴다")
        else:
            out("[home-guides] 전부 정본과 같다")
        return 1 if bad else 0

    todo = [r for r in results if r.status == "DIFF" and r.target.kind == "copy"]
    if not todo:
        out("[home-guides] 쓸 것 없음")
        return 1 if bad else 0
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now() if now else None))
    for r in todo:
        out(apply_one(r, runner=runner, writer=writer, stamp=stamp, root=root))
    out("[home-guides] 다시 대조")
    again = [evaluate(t, runner=runner, local=local, root=root) for t in targets]
    for r in again:
        out(r.line)
    return 1 if any(r.status in ("DIFF", "FAIL") for r in again) else 0
