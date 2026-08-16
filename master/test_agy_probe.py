"""agy 프로브(`#171`) 계약 테스트 — 🔴 **「돌았다」를 「됐다」로 세지 않는가.**

이 프로브의 존재 이유는 저장소 하드룰이다: *"위임한 백엔드의 「done」을 믿지 마라. 실측
2026-08-07: `agy` 가 `status:"SUCCESS"` 를 돌려주면서 **파일을 쓰지 않았다**."*
그래서 여기서 재는 것은 게이트가 **무엇을 보고 통과를 주는가**다.

실행: python3 master/test_agy_probe.py   (🔴 실 agy 를 부르지 않는다 — 전부 주입)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import agy_probe as A       # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


class Proc:
    def __init__(self, out=""):
        self.stdout, self.stderr, self.returncode = out, "", 0


def which_ok(_):
    return "/usr/local/bin/agy"


# ── 호출 형태 ─────────────────────────────────────────────────

def test_command_shape():
    cmd = A.build_command("agy", "안녕", model="m", add_dir="/tmp/x")
    check("🔴 `-p` 다음이 프롬프트다 (위치 함정)", cmd[-1] == "안녕" and cmd[1] == "-p", str(cmd))
    check("모델 오버라이드가 실린다", "--model" in cmd and "m" in cmd, str(cmd))
    check("🔴 `--add-dir` 로 파일을 쥐여준다 (출처를 지어내지 않게)",
          "--add-dir" in cmd and "/tmp/x" in cmd, str(cmd))
    plain = A.build_command("agy", "x")
    check("옵션 없으면 안 싣는다", plain == ["agy", "-p", "x"], str(plain))


def test_marker_is_unguessable():
    a, b = A.marker(), A.marker()
    check("🔴 마커는 매번 다르다 (모델이 지어낼 수 없어야 한다)", a != b, f"{a} {b}")
    check("접두어로 알아볼 수 있다", a.startswith("AGYPROBE") and len(a) > 12, a)


def test_ansi_is_stripped():
    check("ANSI 이스케이프를 벗긴다",
          A.strip_ansi("\x1b[32mAGYPROBE1234\x1b[0m") == "AGYPROBE1234")
    check("없는 것도 그대로", A.strip_ansi("plain") == "plain")


# ── 게이트 판정 ───────────────────────────────────────────────

def test_missing_agy_stops_early():
    r = A.probe(which=lambda _: None, runner=lambda c, t: Proc("x"))
    check("agy 가 없으면 거기서 멈춘다", len(r.gates) == 1 and not r.ok, str(r.gates))
    check("사유를 말한다", "PATH" in r.gates[0].detail, r.gates[0].detail)


def test_empty_output_is_a_failure():
    """🔴 호출은 끝났는데 아무것도 안 온 것 — 원전이 비-TTY 에서 겪은 그 모양."""
    r = A.probe(which=which_ok, runner=lambda c, t: Proc(""))
    check("출력이 비면 불합격", not r.ok)
    check("🔴 '비었다' 고 말한다", any("비었다" in g.detail for g in r.gates), str(r.gates))
    check("산출물 게이트까지 가지 않는다", len(r.gates) == 2, str(len(r.gates)))


def test_hang_is_named_not_swallowed():
    def boom(cmd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)
    r = A.probe(which=which_ok, runner=boom, timeout=9)
    check("타임아웃은 불합격", not r.ok)
    check("🔴 hang 가능성을 말한다 (원전은 PTY 로 우회했다)",
          any("hang" in g.detail for g in r.gates), str(r.gates))


def test_wrong_output_is_not_a_roundtrip():
    """🔴 '응답이 왔다' 는 통과가 아니다 — **내가 보낸 것이 돌아와야** 한다."""
    r = A.probe(which=which_ok, runner=lambda c, t: Proc("알겠습니다. 도와드릴까요?"))
    rt = [g for g in r.gates if "라운드트립" in g.name][0]
    check("🔴 다른 말을 하면 라운드트립 실패", not rt.passed, rt.detail)
    check("받은 것을 보여 준다", "받은 앞부분" in rt.detail, rt.detail)


def test_status_success_without_file_fails():
    """🔴 **이 저장소의 하드룰이 겨눈 바로 그 실패** — SUCCESS 라면서 파일을 안 쓴다."""
    with tempfile.TemporaryDirectory() as d:
        def runner(cmd, timeout):
            # 마커는 되돌려 주지만(=②는 통과) 파일은 **안 쓴다**
            tok = [c for c in cmd if c.startswith("다음 토큰") or "정확히 이 한 줄" in c]
            m = ""
            for c in cmd:
                for w in c.split():
                    if w.startswith("AGYPROBE"):
                        m = w
            return Proc(f'{{"status":"SUCCESS"}}\n{m}')
        r = A.probe(which=which_ok, runner=runner, workdir=d)
        rt = [g for g in r.gates if "라운드트립" in g.name][0]
        art = [g for g in r.gates if "산출물" in g.name][0]
        check("라운드트립은 통과한다", rt.passed, rt.detail)
        check("🔴 그런데 산출물 게이트가 막는다", not art.passed, art.detail)
        check("🔴 그 실패가 실측된 것임을 말한다", "SUCCESS" in art.detail, art.detail)
        check("전체는 불합격", not r.ok, str(r.failed))


def test_full_pass_requires_the_file():
    with tempfile.TemporaryDirectory() as d:
        state = {}

        def runner(cmd, timeout):
            m = ""
            for c in cmd:
                for w in c.split():
                    if w.startswith("AGYPROBE"):
                        m = w
            state["tok"] = m
            if "파일을 만들고" in cmd[-1]:
                Path(d, "probe_out.txt").write_text(m, encoding="utf-8")
            return Proc(m)

        r = A.probe(which=which_ok, runner=runner, workdir=d)
        check("파일까지 쓰면 통과한다", r.ok, str(r.failed))
        check("게이트 셋을 다 돈다", len(r.gates) == 3, str(len(r.gates)))
        check("요약이 수치를 준다", "3/3" in r.summary(), r.summary())


def test_file_without_marker_fails():
    with tempfile.TemporaryDirectory() as d:
        def runner(cmd, timeout):
            m = ""
            for c in cmd:
                for w in c.split():
                    if w.startswith("AGYPROBE"):
                        m = w
            if "파일을 만들고" in cmd[-1]:
                Path(d, "probe_out.txt").write_text("엉뚱한 내용", encoding="utf-8")
            return Proc(m)
        r = A.probe(which=which_ok, runner=runner, workdir=d)
        art = [g for g in r.gates if "산출물" in g.name][0]
        check("🔴 파일은 있는데 내용이 다르면 불합격", not art.passed, art.detail)
        check("무엇이 들었는지 보여 준다", "마커가 없다" in art.detail, art.detail)


def main() -> int:
    for fn in (test_command_shape, test_marker_is_unguessable, test_ansi_is_stripped,
               test_missing_agy_stops_early, test_empty_output_is_a_failure,
               test_hang_is_named_not_swallowed, test_wrong_output_is_not_a_roundtrip,
               test_status_success_without_file_fails, test_full_pass_requires_the_file,
               test_file_without_marker_fails):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_agy_probe: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
