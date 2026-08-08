"""색인기(스풀 소비자) 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_indexer.py

🔴 지키는 불변식:
   1. **미러를 `reset --hard` 로 덮지 않는다** — `merge --ff-only`. 갈라졌으면 알아야 한다
   2. **컨텍스트가 안 바뀌었으면 재색인하지 않는다** — 40초를 태워 같은 것을 넣지 않는다
   3. **그 '건너뜀' 을 조용히 넘기지 않는다** — 사유를 남긴다
   4. **워터마크 갱신이 config.yaml 의 주석·순서를 뭉개지 않는다**
   5. **등록되지 않은 project_id 는 거부** (§5.5.4-④)
   6. **fetch 가 실패하면 재색인하지 않는다** — 낡은 소스로 색인하면 조용히 틀린다

git 은 주입한다 — 실제 저장소 없이 규칙을 검증한다.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.events.consumer import (  # noqa: E402
    ProjectResult, _update_watermark, context_digest, process_event,
    read_digest, write_digest,
)
from master.events.spool import Event  # noqa: E402
from master.context_search.paths import ProjectPaths, SOURCE_SUBDIR  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


CONFIG = """# 사용자가 손으로 쓴 주석 — 갱신이 이걸 지우면 안 된다
project_id: Sim/Demo
index:
  last_indexed_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  last_indexed_at: '2026-08-01T00:00:00'
  source: infra_state.zip
  include:
  - Source/**/*.cpp     # 소스 한정 (§5.2-E)
"""


class FakeReg:
    def __init__(self, root: Path, name="Demo", pid="Sim/Demo"):
        self._root, self.names, self.active = root, [name], name
        self._pid = pid

    def dir_of(self, name):
        return self._root / name

    def find_by_project_id(self, pid):
        return "Demo" if (pid or "").casefold() == self._pid.casefold() else ""


def make_project(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="Demo", root=root / "Demo")
    (p.repo / SOURCE_SUBDIR).mkdir(parents=True, exist_ok=True)
    p.context.mkdir(parents=True, exist_ok=True)
    (p.context / "A.md").write_text("---\ntags: [x]\n---\n본문", encoding="utf-8")
    p.config.write_text(CONFIG, encoding="utf-8")
    return p


def git_ok(log: list):
    """성공하는 가짜 git. **fetch 전후로 HEAD 가 달라진다** — 실제 푸시가 그렇다.

    이걸 고정값으로 두면 `from == to` 라 diff 경로가 아예 안 돌아, 테스트가 통과해도
    아무것도 검증하지 못한다.
    """
    state = {"fetched": False}

    def run(repo, *args):
        log.append(list(args))
        if args[0] == "fetch":
            state["fetched"] = True
            return 0, ""
        if args[0] == "rev-parse":
            return 0, ("b" * 40) if state["fetched"] else ("a" * 40)
        if args[0] == "diff":
            return 0, "Source/A.cpp\nSource/B.cpp"
        return 0, ""
    return run


def ev(pid="Sim/Demo", subject="feat: x"):
    return Event(project_id=pid, ref="refs/heads/main", old="a" * 40, new="b" * 40,
                 subject=subject)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-idx-test-"))
    paths = make_project(tmp)
    reg = FakeReg(tmp)

    print("\n[1] 🔴 미러를 덮어쓰지 않는다 — ff-only")
    log = []
    r = process_event(ev(), registry=reg, git=git_ok(log), reindex=lambda p: 7)
    cmds = [" ".join(c) for c in log]
    check("fetch 한다", any(c.startswith("fetch") for c in cmds), str(cmds))
    check("🔴 merge --ff-only 를 쓴다",
          any("merge --ff-only" in c for c in cmds), str(cmds))
    check("🔴 reset --hard 를 쓰지 않는다",
          not any("reset" in c for c in cmds), str(cmds))
    check("소스 변경만 센다 (§5.2-E)",
          any("diff --name-only" in c and c.endswith("Source") for c in cmds), str(cmds))
    check("변경 파일 수", r.source_changed == 2, str(r.source_changed))
    check("오류 없음", r.ok, r.error)

    print("\n[2] 첫 실행은 재색인한다 (다이제스트가 없다)")
    check("재색인함", r.reindexed and r.docs == 7, f"{r.reindexed} {r.docs}")
    check("다이제스트가 저장된다", bool(read_digest(paths)))

    print("\n[3] 🔴 컨텍스트가 그대로면 재색인하지 않는다")
    calls = []
    r2 = process_event(ev(), registry=reg, git=git_ok([]),
                       reindex=lambda p: calls.append(1) or 7)
    check("🔴 재색인을 부르지 않는다", calls == [], str(calls))
    check("건너뛴 사유를 남긴다", "변화 없음" in r2.skipped, r2.skipped)
    check("  소스는 바뀐 상황이므로 이유를 덧붙인다",
          "합성이 문서를 바꾸지 않았다" in r2.skipped, r2.skipped)
    check("그래도 실패는 아니다", r2.ok)

    print("\n[4] 컨텍스트가 바뀌면 다시 색인한다")
    (paths.context / "B.md").write_text("---\ntags: [y]\n---\n새 문서", encoding="utf-8")
    calls.clear()
    r3 = process_event(ev(), registry=reg, git=git_ok([]),
                       reindex=lambda p: calls.append(1) or 9)
    check("재색인함", r3.reindexed and len(calls) == 1, f"{r3.reindexed} {calls}")
    check("문서 수", r3.docs == 9)
    check("다이제스트 갱신", read_digest(paths) == context_digest(paths))

    print("\n[5] 🔴 워터마크 갱신이 주석·순서를 뭉개지 않는다")
    text = paths.config.read_text(encoding="utf-8")
    check("커밋이 전진했다", "b" * 40 in text, text[:120])
    check("사용자 주석 보존", "사용자가 손으로 쓴 주석" in text)
    check("인라인 주석 보존", "# 소스 한정 (§5.2-E)" in text)
    check("항목 순서 보존", text.index("last_indexed_commit") < text.index("source"))
    check("임시 파일 안 남음", not list(paths.root.glob("*.tmp")))

    print("\n[6] 🔴 등록되지 않은 project_id 는 거부 (§5.5.4-④)")
    r4 = process_event(ev(pid="Someone/Else"), registry=reg, git=git_ok([]),
                       reindex=lambda p: 1)
    check("거부", not r4.ok and "등록되지 않은" in r4.error, r4.error)
    check("대소문자는 접어서 매칭",
          process_event(ev(pid="sim/DEMO"), registry=reg, git=git_ok([]),
                        reindex=lambda p: 1).ok)

    print("\n[7] 🔴 fetch 가 실패하면 재색인하지 않는다")
    calls.clear()

    def git_fetch_fail(repo, *args):
        if args[0] == "fetch":
            return 128, "could not read from remote"
        return 0, "b" * 40

    r5 = process_event(ev(), registry=reg, git=git_fetch_fail,
                       reindex=lambda p: calls.append(1) or 1)
    check("오류로 잡는다", not r5.ok and "fetch 실패" in r5.error, r5.error)
    check("🔴 재색인을 부르지 않는다", calls == [], str(calls))

    print("\n[8] 🔴 미러가 갈라지면 조용히 덮지 않는다")

    def git_diverged(repo, *args):
        if args[0] == "merge":
            return 1, "fatal: Not possible to fast-forward, aborting."
        return 0, "b" * 40

    r6 = process_event(ev(), registry=reg, git=git_diverged, reindex=lambda p: 1)
    check("오류로 잡는다", not r6.ok and "갈라졌다" in r6.error, r6.error)

    def git_uptodate(repo, *args):
        if args[0] == "merge":
            return 1, "Already up to date."
        return 0, "b" * 40

    check("'Already up to date' 는 실패가 아니다",
          process_event(ev(), registry=reg, git=git_uptodate, reindex=lambda p: 1).ok)

    print("\n[9] 재색인이 터져도 소비자가 죽지 않는다")

    (paths.context / "C.md").write_text("---\ntags: [z]\n---\n또", encoding="utf-8")

    def boom(p):
        raise RuntimeError("chromadb 죽음")

    r7 = process_event(ev(), registry=reg, git=git_ok([]), reindex=boom)
    check("오류로 보고", not r7.ok and "재색인 실패" in r7.error, r7.error)
    check("  원인이 남는다", "chromadb 죽음" in r7.error)
    check("🔴 다이제스트를 갱신하지 않는다 (다음에 다시 시도한다)",
          read_digest(paths) != context_digest(paths))

    print("\n[10] 소스 클론이 없으면 거부")
    shutil.rmtree(paths.repo)
    r8 = process_event(ev(), registry=reg, git=git_ok([]), reindex=lambda p: 1)
    check("거부", not r8.ok and "소스 클론이 없다" in r8.error, r8.error)

    print("\n[10-1] 🔴 트윈이 자란다 — 합성기가 색인기에 물려 있다 (중 1.2)")
    p3 = make_project(tmp / "grow")
    seen = {}

    def fake_synth(paths_, *, changed=None, commit="", **kw):
        seen["changed"], seen["commit"] = list(changed or []), commit
        # 실제로 문서를 바꿔야 재색인이 돈다
        (paths_.context / "New.md").write_text("---\ntags: [n]\n---\n새 문서",
                                               encoding="utf-8")

        class S:
            written, lost, aborted = 1, 0, ""
            summary = "그룹 1 → 통과 1"
            results: list = []
        return S()

    calls = []
    r9 = process_event(ev(), registry=FakeReg(tmp / "grow"), git=git_ok([]),
                       reindex=lambda p: calls.append(1) or 5, synth_run=fake_synth)
    check("합성을 부른다", "changed" in seen, str(seen))
    check("  변경 파일 목록을 넘긴다",
          seen.get("changed") == ["Source/A.cpp", "Source/B.cpp"], str(seen.get("changed")))
    check("🔴 커밋 해시를 넘긴다 (source_commit 스탬프의 원천)",
          seen.get("commit") == "b" * 40, seen.get("commit"))
    check("합성 결과가 보고된다", r9.synth_written == 1, r9.summary)
    check("🔴 합성이 문서를 바꿨으니 재색인이 돈다", r9.reindexed and calls == [1], r9.summary)
    check("그래프도 갱신 시도한다", bool(r9.graph_notes), str(r9.graph_notes))
    check("요약에 다 들어간다", "합성" in r9.summary and "색인" in r9.summary, r9.summary)

    print("\n[10-2] 🔴 유실을 삼키지 않는다 (워터마크가 전진하므로 영구 유실이다)")

    class LostS:
        written, lost, aborted = 0, 2, ""
        summary = "그룹 2 → 통과 0 · 🔴 사실 거부 2"

        class G:
            def __init__(self, k, why):
                self.key, self.reason, self.lost = k, why, True
        results = [G("Source/A", "사실 게이트 거부 — 유령 식별자"),
                   G("Source/B", "LLM 실패: 타임아웃")]

    r10 = process_event(ev(), registry=FakeReg(tmp / "grow"), git=git_ok([]),
                        reindex=lambda p: 1, synth_run=lambda *a, **k: LostS())
    check("유실 수를 센다", r10.synth_lost == 2, str(r10.synth_lost))
    check("🔴 어느 그룹인지 남긴다", len(r10.lost_groups) == 2, str(r10.lost_groups))
    check("  사유도 남긴다", "유령 식별자" in r10.lost_groups[0], r10.lost_groups[0])
    check("요약이 유실을 드러낸다", "유실 2" in r10.summary, r10.summary)

    print("\n[10-3] 합성을 끌 수 있다 (노드가 죽었을 때)")
    off = []
    r11 = process_event(ev(), registry=FakeReg(tmp / "grow"), git=git_ok([]),
                        reindex=lambda p: 1, synthesize=False,
                        synth_run=lambda *a, **k: off.append(1))
    check("🔴 합성을 부르지 않는다", off == [], str(off))
    check("  그래도 그래프는 갱신한다", bool(r11.graph_notes), str(r11.graph_notes))

    print("\n[10-4] 🔴 합성이 터져도 색인기가 죽지 않는다")

    def boom_synth(*a, **k):
        raise RuntimeError("브로커 죽음")

    r12 = process_event(ev(), registry=FakeReg(tmp / "grow"), git=git_ok([]),
                        reindex=lambda p: 1, synth_run=boom_synth)
    check("오류로 잡고 계속한다", r12.ok and "합성 실패" in r12.synth_note, r12.synth_note)

    print("\n[11] 다이제스트 — 변화를 잡아낸다")
    p2 = make_project(tmp / "second")
    d1 = context_digest(p2)
    check("같은 상태면 같은 값", d1 == context_digest(p2))
    (p2.context / "New.md").write_text("---\ntags: [n]\n---\nx", encoding="utf-8")
    check("파일이 늘면 달라진다", context_digest(p2) != d1)
    check("context/ 가 없으면 빈 문자열",
          context_digest(ProjectPaths(name="X", root=tmp / "없음")) == "")
    write_digest(p2, "abc123")
    check("쓰고 읽는다", read_digest(p2) == "abc123")
    check("없으면 빈 문자열", read_digest(ProjectPaths(name="Y", root=tmp / "없음2")) == "")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
