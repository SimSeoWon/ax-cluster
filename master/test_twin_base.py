"""작업 기준 커밋 — `twin_commit` · durable 브랜치 존재 확인 (레드마인 #21).

**git 을 실행하지 않는다** — `runner` 를 주입해 `ls-remote` 출력을 흉내낸다. 여기서 지키는
계약은 명령이 아니라 판정이다: **모른다·없다·못 봤다 셋을 뭉치지 않는가.**

`python3 master/test_twin_base.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths        # noqa: E402
from master.work import twin_base                            # noqa: E402

PASS = FAIL = 0
COMMIT = "bc4b38f43c23d0e898573b0a5fd89c12fee7f813"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _project(tmp: Path, *, commit: str = COMMIT, bare: str = "/var/lib/gitea/x.git") -> ProjectPaths:
    paths = ProjectPaths(name="T", root=tmp)
    lines = ["version: 1", "name: T", "track:"]
    if bare:
        lines.append(f"  bare_path: {bare}")
    lines += ["  branch: main", "  local_clone: repo", "index:"]
    if commit:
        lines.append(f"  last_indexed_commit: {commit}")
    tmp.mkdir(parents=True, exist_ok=True)
    paths.config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths


def _runner(out: str, rc: int = 0):
    def run(cmd: str):
        run.calls.append(cmd)
        return rc, out
    run.calls = []
    return run


def test_twin_commit() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        check("트윈 커밋을 읽는다", twin_base.twin_commit(paths) == COMMIT)

        empty = _project(Path(t) / "b", commit="")
        try:
            twin_base.twin_commit(empty)
            check("🔴 커밋이 없으면 예외", False, "빈 문자열을 돌려줬다")
        except twin_base.TwinBaseError as e:
            # 🔴 빈 문자열로 얼버무리면 "모른다" 가 "괜찮다" 로 둔갑한다
            check("🔴 커밋이 없으면 예외 (빈 문자열 금지)", "색인" in str(e), str(e)[:60])


def test_resolve() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        br = "task/w1"

        r = _runner(f"{COMMIT}\trefs/heads/main\n{COMMIT}\trefs/heads/{br}\n")
        b = twin_base.resolve(paths, "w1", runner=r)
        check("브랜치가 있으면 exists", b.exists and b.checked, b.summary)
        check("커밋을 싣는다", b.commit == COMMIT)
        check("이름 규약은 durable", b.branch == br, b.branch)
        check("있으면 시킬 게 없다", b.instruction == "")
        check("읽기 전용 명령만 부른다",
              all("ls-remote" in c and "push" not in c for c in r.calls), str(r.calls))

        b2 = twin_base.resolve(paths, "w1", runner=_runner(f"{COMMIT}\trefs/heads/main\n"))
        check("없으면 exists=False 지만 확인은 했다", (not b2.exists) and b2.checked, b2.summary)
        # 🔴 "무엇을 해야 하는지" 까지 말해야 요청자가 움직인다
        check("🔴 만들 명령을 알려준다",
              b2.branch in b2.instruction and COMMIT in b2.instruction and "push" in b2.instruction,
              b2.instruction)

        # 🔴 못 본 것과 없는 것은 다르다
        b3 = twin_base.resolve(paths, "w1", runner=_runner("permission denied", rc=128))
        check("🔴 확인 실패는 '없음' 이 아니다", (not b3.checked) and b3.error, b3.summary)
        check("실패 사유를 들고 나온다", "읽지 못했다" in b3.error, b3.error[:60])

        nobare = _project(Path(t) / "c", bare="")
        b4 = twin_base.resolve(nobare, "w1", runner=_runner(""))
        check("bare_path 가 없으면 확인 실패로 표시", not b4.checked, b4.summary)


def test_manifest_section() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))

        have = twin_base.resolve(paths, "w1",
                                 runner=_runner(f"{COMMIT}\trefs/heads/task/w1\n"))
        txt = "\n".join(twin_base.manifest_section(have))
        check("기준 커밋이 본문에 있다", COMMIT in txt)
        check("🔴 ff-only 를 못박는다", "fast-forward" in txt and "reset --hard" in txt)
        check("있으면 '만들어야 한다' 를 안 쓴다", "아직 없다" not in txt)

        miss = twin_base.resolve(paths, "w1", runner=_runner(""))
        txt2 = "\n".join(twin_base.manifest_section(miss))
        check("🔴 없으면 본문에 그렇게 쓴다", "원격에 아직 없다" in txt2)
        check("만들 명령이 본문에 실린다", "git push -u origin task/w1" in txt2)

        bad = twin_base.resolve(paths, "w1", runner=_runner("boom", rc=1))
        txt3 = "\n".join(twin_base.manifest_section(bad))
        check("🔴 확인 못 했으면 그렇게 쓴다 (없다고 하지 않는다)",
              "확인하지 못했다" in txt3 and "원격에 아직 없다" not in txt3, txt3[:120])


def main() -> int:
    for fn in (test_twin_commit, test_resolve, test_manifest_section):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_twin_base: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
