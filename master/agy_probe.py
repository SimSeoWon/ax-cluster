"""agy 라이브 검증 프로브 — 원전 `scripts/agy_probe.py` 이식 (소 3.6.5 · `#171`).

원전이 이 스크립트를 만든 이유가 우리에게 그대로 있다: **배선이 컴파일되는 것과 그 백엔드가
실제로 도는 것은 다르다.** 원전 원문 — *"단위 테스트는 배선 로직을 agy 없이 검증하고, 이
프로브는 **실제 agy 호출의 운영 게이트**를 검증한다."*

## 🔴 기제는 옮기고 **신호원은 우리 것**으로 바꾼다

원전의 핵심 게이트는 **가상 PTY(ConPTY via pywinpty)** 라운드트립이다. 근거는 원전 환경의
실측이다 — *"agy 는 비-TTY(파이프/파일 캡처)면 출력 0 + hang."* ⚠️ **그 전제는 윈도우 것이고
우리는 리눅스다.** 그래서 PTY 를 전제로 박지 않고 **재서** 고른다(`pty_fallback`).

🔴 **우리 실패 모드는 따로 기록돼 있다** — 저장소 하드룰: *"위임한 백엔드의 「done」을 믿지
마라. 실측 2026-08-07: `agy` 가 `status:"SUCCESS"` 를 돌려주면서 **파일을 쓰지 않았다**."*
그리고 운영 메모 둘: **웹 검색을 시키면 출처를 지어낸다**(→ `--add-dir` 로 파일을 쥐여준다)와
**`-p` 위치 함정**.

그래서 게이트를 우리 실패 모드에 맞춰 셋으로 둔다:

    ① 해결      agy 가 PATH 에 있는가
    ② 라운드트립 마커를 넣으면 **그 마커가 돌아오는가** (출력 0·hang 을 가른다)
                🔴 셀프테스트의 NONCE 증명과 **같은 논리**다 — 응답이 왔다가 아니라
                   *"내가 보낸 것이 돌아왔다"* 를 본다
    ③ 산출물    파일을 쓰라고 시키면 **파일이 생기는가**
                🔴 이것이 우리 하드룰이 겨눈 그 실패다. status 를 보지 않는다

## ⚠️ 이 프로브는 비용을 쓴다

실 agy 호출이 2회 든다. 그래서 **자동으로 돌지 않는다** — 사람이 부른다(원전도 배포 전 수동
게이트였다). 판정 로직은 주입 가능해 실 호출 없이 잰다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT = 180
# ANSI 이스케이프 — PTY 로 받으면 섞여 온다. 마커 대조 전에 벗긴다(원전과 같은 이유).
_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


def resolve_agy(which=None) -> str:
    """PATH 에서 agy 를 찾는다. 없으면 빈 문자열."""
    return (which or shutil.which)("agy") or ""


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ProbeResult:
    ok: bool = False
    agy: str = ""
    gates: list = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.gates.append(Gate(name, bool(passed), detail))

    @property
    def failed(self) -> list:
        return [g.name for g in self.gates if not g.passed]

    def summary(self) -> str:
        n = sum(1 for g in self.gates if g.passed)
        return (f"agy 프로브 {n}/{len(self.gates)} 통과"
                + (f" · 🔴 실패: {', '.join(self.failed)}" if self.failed else ""))


def marker() -> str:
    """돌아오는지 볼 토큰. 🔴 **프롬프트 밖에서 만든다** — 모델이 지어낼 수 없는 값이어야 한다."""
    return "AGYPROBE" + os.urandom(4).hex().upper()


def build_command(agy: str, prompt: str, *, model: str = "", add_dir: str = "") -> list:
    """실 호출 형태. 🔴 **`-p` 다음이 프롬프트다** — 순서가 어긋나면 조용히 다르게 동작한다.

    ⚠️ 이 저장소의 운영 메모 둘이 여기 박혀 있다: `-p` 위치 함정, 그리고 **웹 검색을 시키면
    출처를 지어내므로 `--add-dir` 로 파일을 쥐여준다.**
    """
    cmd = [agy, "-p"]
    if model:
        cmd += ["--model", model]
    if add_dir:
        cmd += ["--add-dir", add_dir]
    cmd.append(prompt)
    return cmd


def _run(cmd, timeout: int):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def probe(*, model: str = "", timeout: int = DEFAULT_TIMEOUT, runner=None, which=None,
          workdir=None) -> ProbeResult:
    """게이트 셋을 돌린다. `runner(cmd, timeout)` 주입으로 실 호출 없이 잴 수 있다."""
    run = runner or _run
    r = ProbeResult()

    # ① 해결
    r.agy = resolve_agy(which)
    r.add("agy 가 PATH 에 있다", bool(r.agy), r.agy or "PATH 에서 찾지 못했다")
    if not r.agy:
        return r

    # ② 라운드트립 — 🔴 "응답이 왔다" 가 아니라 "내가 보낸 것이 돌아왔다"
    tok = marker()
    try:
        proc = run(build_command(r.agy, f"다음 토큰을 그대로 한 줄로 출력하라: {tok}", model=model),
                   timeout)
        out = strip_ansi((getattr(proc, "stdout", "") or "")
                         + (getattr(proc, "stderr", "") or ""))
    except subprocess.TimeoutExpired:
        # ⚠️ 원전 환경에서 비-TTY hang 이 정확히 이 모양이었다. 우리 환경이 그런지는 **재서** 안다.
        r.add("마커 라운드트립", False,
              f"{timeout}초 안에 끝나지 않았다 — 비-TTY hang 일 수 있다(원전은 PTY 로 우회했다)")
        return r
    except OSError as e:
        r.add("마커 라운드트립", False, f"실행 실패: {e}")
        return r
    if not out.strip():
        r.add("마커 라운드트립", False, "🔴 출력이 비었다 — 호출은 끝났는데 아무것도 안 왔다")
        return r
    r.add("마커 라운드트립", tok in out,
          "마커가 돌아왔다" if tok in out else f"🔴 마커가 없다 — 받은 앞부분: {out.strip()[:120]!r}")

    # ③ 산출물 — 🔴 우리 하드룰이 겨눈 실패: SUCCESS 라면서 파일을 안 쓴다
    tmp = Path(workdir or tempfile.mkdtemp(prefix="ax-agy-probe-"))
    target = tmp / "probe_out.txt"
    try:
        run(build_command(r.agy,
                          f"{target} 파일을 만들고 그 안에 정확히 이 한 줄만 써라: {tok}",
                          model=model, add_dir=str(tmp)),
            timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        r.add("산출물 생성", False, f"실행 실패: {type(e).__name__}")
        return r
    wrote = target.is_file()
    body = target.read_text(encoding="utf-8", errors="replace") if wrote else ""
    # 🔴 **status 를 보지 않는다.** 파일이 있고 그 안에 마커가 있어야 통과다.
    r.add("산출물 생성 (🔴 status 가 아니라 파일을 본다)", wrote and tok in body,
          "파일과 내용 확인" if wrote and tok in body
          else ("🔴 파일이 없다 — 이것이 실측된 그 실패다(SUCCESS 라면서 안 씀)" if not wrote
                else f"파일은 있는데 마커가 없다: {body[:80]!r}"))
    r.ok = not r.failed
    return r


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="agy 라이브 검증 프로브 (실 호출 2회 — 비용이 든다)")
    ap.add_argument("--model", default="", help="모델 오버라이드")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    a = ap.parse_args(argv)
    r = probe(model=a.model, timeout=a.timeout)
    print(f"agy = {r.agy or '(없음)'}")
    for g in r.gates:
        print(f"  {'✅' if g.passed else '🔴'} {g.name}" + (f" — {g.detail}" if g.detail else ""))
    print(r.summary())
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
