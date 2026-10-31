"""#861: 기계별 홈 안내서 대조·동기화 — 네트워크 없이 주입으로 검사한다."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import home_guides as H
from master.client import __main__ as cli

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


ROOT = H.REPO_ROOT
WANT = {t.path + "@" + t.host: H.want_content(t) for t in H.TARGETS if t.kind == "copy"}


class Fake:
    """원격 상태 표 — path → ("file", 내용) · ("link", 대상) · ("absent",) · ("rc", n)."""

    def __init__(self, state: dict):
        self.state = state
        self.cmds = []
        self.writes = []
        self.events = []

    def runner(self, host, user, cmd):
        self.cmds.append((host, cmd))
        self.events.append("backup" if "Copy-Item" in cmd else "query")
        if "Copy-Item" in cmd:
            return 0, ""
        for t in H.TARGETS:
            if t.host == host and f"'{t.path}'" in cmd or (t.host == host and H._q(t.path) in cmd):
                st = self.state.get((host, t.path), ("absent",))
                if st[0] == "rc":
                    return st[1], "ssh: connect timed out"
                if st[0] == "absent":
                    return 0, "AX_ABSENT"
                if st[0] == "link":
                    return 0, f"AX_LINK={st[1]}"
                if t.os == "windows":
                    return 0, h(st[1]).upper()
                return 0, f"AX_FILE\n{h(st[1])}"
        return 0, "AX_ABSENT"

    def writer(self, facts, path, content):
        self.writes.append((facts.host, path, content, facts.windows))
        self.events.append("write")
        self.state[(facts.host, path)] = ("file", content)
        return path

    def local(self, path):
        st = self.state.get(("192.168.0.57", path), ("absent",))
        if st[0] == "link":
            return ("link", st[1])
        if st[0] == "file":
            return ("file", h(st[1]))
        return ("absent", "")


def all_ok_state() -> dict:
    s = {}
    for t in H.TARGETS:
        if t.kind == "copy":
            s[(t.host, t.path)] = ("file", H.want_content(t))
        elif t.kind == "symlink":
            s[(t.host, t.path)] = ("link", t.link_target)
    return s


def run(fake, **kw):
    lines = []
    rc = H.run(runner=fake.runner, writer=fake.writer, local=fake.local, now=lambda: 0,
               out=lines.append, **kw)
    return rc, lines


def T(host, name):
    return next(t for t in H.TARGETS if t.host == host and t.path.endswith(name))


# ── derive_agents ──
src = ("# CLAUDE.md — Windows worker `.2`\n\n> scp x janus@192.168.0.2:C:/Users/janus/CLAUDE.md\r\n"
       "> keep CLAUDE.md word\n## Body\nC:/Users/janus/CLAUDE.md stays\n# CLAUDE.md later\n")
d = H.derive_agents(src)
check("derive: 제목", d.startswith("# AGENTS.md — Windows worker `.2`\n"))
check("derive: 머리의 경로도 바이트 그대로(제목만 바꾼다)", "janus@192.168.0.2:C:/Users/janus/CLAUDE.md\r\n" in d)
check("derive: 머리의 다른 CLAUDE.md 단어 보존", "> keep CLAUDE.md word\n" in d)
check("derive: 본문 그대로", d.split("## Body", 1)[1] == src.split("## Body", 1)[1])
check("derive: 길이 동일", len(d) == len(src))
try:
    H.derive_agents("# Something else\n")
    check("derive: 모양 바뀌면 예외", False)
except H.GuideError:
    check("derive: 모양 바뀌면 예외", True)
real = H.want_content(T("192.168.0.2", "AGENTS.md"))
canon = (ROOT / "machines/win-worker-2.md").read_text(encoding="utf-8")
check("derive: 실제 정본 — 제목", real.splitlines()[0] == "# AGENTS.md — Windows worker `.2`")
# 정본 머리말은 수동 scp 대신 home-guides 를 안내한다(#861) — 제목 줄 말고는 같아야 한다
_r, _c = real.splitlines(), canon.splitlines()
check("derive: 실제 정본 — 제목 외 전 줄 동일",
      len(_r) == len(_c) and _r[1:] == _c[1:],
      [i for i, (a, b) in enumerate(zip(_r, _c)) if a != b][:5])
check("derive: 실제 정본 — 수동 scp 안내 없음", "scp ~/ax-cluster/machines/win-worker-2.md" not in canon)
check("derive: 실제 정본 — 본문 동일",
      real.split("\n## ", 1)[1] == canon.split("\n## ", 1)[1])

# ── 전부 OK ──
f = Fake(all_ok_state())
rc, lines = run(f)
check("plan 전부 OK → rc 0", rc == 0, "\n".join(lines))
check("plan 전부 OK → 쓰기 없음", not f.writes)
check("plan: 대상 수만큼 줄", sum(1 for ln in lines if ln.startswith("[") and not ln.startswith("[home-guides]")) == len(H.TARGETS))
check("plan: .33 AGENTS ABSENT", any("ABSENT" in ln and "USER\\AGENTS.md" in ln for ln in lines))

# ── DIFF copy ──
st = all_ok_state()
t2c = T("192.168.0.2", "CLAUDE.md")
st[(t2c.host, t2c.path)] = ("file", "stale\n")
f = Fake(st)
rc, lines = run(f)
check("DIFF → plan rc 1", rc == 1)
check("DIFF → plan 쓰기 없음", not f.writes)
check("DIFF 줄에 해시", any("[DIFF" in ln and h("stale\n")[:12] in ln for ln in lines))
f = Fake(dict(st))
rc, lines = run(f, apply=True)
bk = [c for _, c in f.cmds if "Copy-Item" in c]
check("apply: 백업 명령 1회", len(bk) == 1, str(bk))
check("apply: 백업 경로", bk and f"{t2c.path}.bak-" in bk[0] and "-Destination" in bk[0])
check("apply: 백업이 쓰기보다 먼저",
      "backup" in f.events and "write" in f.events
      and f.events.index("backup") < f.events.index("write"), str(f.events))
check("apply: 올바른 내용", f.writes and f.writes[0][1:3] == (t2c.path, WANT[t2c.path + "@" + t2c.host]))
check("apply: 윈도우 facts", f.writes and f.writes[0][3] is True)
check("apply: 재대조 후 rc 0", rc == 0, "\n".join(lines))
check("apply: 재대조 줄", "[home-guides] 다시 대조" in lines)

# ── 조회 실패 ──
st = all_ok_state()
st[(t2c.host, t2c.path)] = ("rc", 255)
f = Fake(st)
rc, lines = run(f, apply=True)
check("rc255 → FAIL", any("[FAIL" in ln and t2c.path in ln for ln in lines), "\n".join(lines))
check("rc255 → ABSENT 아님", not any("ABSENT" in ln and t2c.path in ln for ln in lines))
check("rc255 → apply 에도 쓰기 없음", not f.writes)
check("rc255 → rc 1", rc == 1)
# 해석 불가 출력
r = H.evaluate(t2c, runner=lambda *a: (0, "garbage"), local=None)
check("해석 불가 → FAIL", r.status == "FAIL")
r = H.evaluate(T("192.168.0.43", "CLAUDE.md"), runner=lambda *a: (0, "AX_FILE\nzz"), local=None)
check("리눅스 해석 불가 → FAIL", r.status == "FAIL")

# ── .33 AGENTS 는 절대 안 쓴다 ──
t33a = T("192.168.0.33", "AGENTS.md")
st = all_ok_state()
f = Fake(st)
rc, _ = run(f, apply=True, host="192.168.0.33")
check(".33 AGENTS 없음 → rc 0", rc == 0)
check(".33 AGENTS 쓰기 없음", not any(w[1] == t33a.path for w in f.writes))
st[(t33a.host, t33a.path)] = ("file", "x")
f = Fake(st)
rc, lines = run(f, apply=True, host="192.168.0.33")
check(".33 AGENTS 있으면 FAIL·쓰기 없음", rc == 1 and not f.writes, "\n".join(lines))

# ── 심볼릭 링크 ──
t43 = T("192.168.0.43", "CLAUDE.md")
st = all_ok_state()
st[(t43.host, t43.path)] = ("file", "regular")
f = Fake(st)
rc, lines = run(f, apply=True)
check("symlink 자리에 일반 파일 → FAIL", any("[FAIL" in ln and t43.path in ln and "192.168.0.43" in ln
                                           for ln in lines))
check("symlink 일반 파일 → 쓰기 없음", not f.writes and rc == 1)
st[(t43.host, t43.path)] = ("link", "/home/sim/elsewhere.md")
f = Fake(st)
rc, lines = run(f, apply=True)
check("symlink 다른 대상 → FAIL·쓰기 없음", rc == 1 and not f.writes)
t57 = T("192.168.0.57", "AGENTS.md")
st = all_ok_state()
st[(t57.host, t57.path)] = ("link", "/home/sim/ax-cluster/machines/sim-desktop.md")
f = Fake(st)
rc, _ = run(f, apply=True, host="192.168.0.57")
check(".57 로컬 링크 다름 → FAIL·쓰기 없음", rc == 1 and not f.writes)
st[(t57.host, t57.path)] = ("link", "ax-cluster/machines/sim-desktop-agents.md")
f = Fake(st)
rc, _ = run(f, host="192.168.0.57")
check(".57 상대 링크 해석 → OK", rc == 0)

# ── --host ──
f = Fake(all_ok_state())
rc, lines = run(f, host="192.168.0.99")
check("--host 미등록 → rc 2", rc == 2 and not f.cmds)
f = Fake(all_ok_state())
rc, lines = run(f, host="192.168.0.2")
check("--host 한 대만 조회", rc == 0 and {c[0] for c in f.cmds} == {"192.168.0.2"})

# ── 없는 copy 대상 + apply → 백업 없이 쓴다 ──
st = all_ok_state()
t2a = T("192.168.0.2", "AGENTS.md")
del st[(t2a.host, t2a.path)]
f = Fake(st)
rc, lines = run(f, apply=True)
check("없는 copy → 백업 없음", not any("Copy-Item" in c for _, c in f.cmds))
check("없는 copy → 유도 내용으로 쓴다",
      len(f.writes) == 1 and f.writes[0][1:3] == (t2a.path, WANT[t2a.path + "@" + t2a.host]))
check("없는 copy → 재대조 rc 0", rc == 0, "\n".join(lines))

# ── 쓰기 실패는 보고 ──
st = all_ok_state()
st[(t2c.host, t2c.path)] = ("file", "stale\n")
f = Fake(st)


def boom(*a):
    raise RuntimeError("해시 불일치")


lines = []
rc = H.run(apply=True, runner=f.runner, writer=boom, local=f.local, out=lines.append)
check("쓰기 예외 → [실패] 줄·rc 1", rc == 1 and any("쓰기 실패" in ln for ln in lines))

# ── CLI 배선 ──
check("CLI: _CMDS 에 home-guides", "home-guides" in cli._CMDS)
check("CLI: 사용법 줄", "home-guides" in (cli.__doc__ or ""))
called = {}
orig = cli.cmd_home_guides
cli.cmd_home_guides = lambda **kw: called.update(kw) or 0
try:
    rc = cli.main(["home-guides", "--host=192.168.0.2", "--apply"])
finally:
    cli.cmd_home_guides = orig
check("CLI: 인자 전달", rc == 0 and called == {"apply": True, "host": "192.168.0.2"}, str(called))

total = PASS + FAIL
if FAIL:
    print(f"[실패] test_home_guides: {PASS}/{total} 통과")
    sys.exit(1)
print(f"OK test_home_guides: {PASS}/{total} 통과")
