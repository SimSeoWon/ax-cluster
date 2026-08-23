"""색인기(스풀 소비자) 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_indexer.py

[중요] 지키는 불변식:
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
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


CONFIG = """# 사용자가 손으로 쓴 주석 — 갱신이 이걸 지우면 안 된다
project_id: Sim/Demo
index:
  last_indexed_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  last_indexed_at: '2026-08-01T00:00:00'
  analyzed_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  analyzed_at: '2026-08-01T00:00:00'
  source: infra_state.zip
  include:
  - Source/**/*.cpp     # 소스 한정 (§5.2-E)
"""

# [중요] **커서 키가 없는 구 config** — `_update_cursor` 가 `index:` 아래에 새로 넣어야 한다.
#    조용히 아무 것도 안 하면 커서가 영원히 비어 판정이 「미확인」에 머문다 (`#280`).
CONFIG_NO_CURSOR = """project_id: Sim/Demo
index:
  last_indexed_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  last_indexed_at: '2026-08-01T00:00:00'
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
    # [중요] **문서 경로는 그룹 키를 따른다** (`synth.doc_path`) — 그룹 `Source/A` 의 문서는
    #    `context/Source/A.md` 다. 평면으로 두면 `#274` 게이트가 「미합성」으로 판정한다
    #    (실측 2026-08-22: 픽스처가 `context/A.md` 라 워터마크가 안 찍혀 칸이 빨갛게 됐다).
    (p.context / "Source").mkdir(parents=True, exist_ok=True)
    for stem in ("A", "B"):
        (p.context / "Source" / f"{stem}.md").write_text(
            f"---\ntags: [{stem}]\n---\n본문", encoding="utf-8")
    (p.context / "A.md").write_text("---\ntags: [x]\n---\n본문", encoding="utf-8")
    p.config.write_text(CONFIG, encoding="utf-8")
    return p


def rewind(paths, commit: str = "a" * 40) -> None:
    """커서를 되감는다. [중요] 커서가 **파일에 남는** 것이 이 기능의 요점이라(`#280`),
    같은 프로젝트 디렉토리를 쓰는 다음 셀은 되감지 않으면 「최신」으로 접힌다."""
    import re
    t = paths.config.read_text(encoding="utf-8")
    paths.config.write_text(
        re.sub(r"(^\s*analyzed_commit:\s*).*$", rf"\g<1>{commit}", t,
               count=1, flags=re.MULTILINE), encoding="utf-8")


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
        if args[0] == "log":
            # [중요] 커서 → HEAD 사이의 커밋. 하나씩 걷는 계약(`#280`)이라 목록이 필요하다.
            return 0, "b" * 40
        if args[0] == "diff":
            return 0, "Source/A.cpp\nSource/B.cpp"
        if args[0] == "ls-files":
            # [중요] `#274` 워터마크 게이트가 **그룹 수**를 센다 — 소스가 없는 픽스처면
            #    「합성할 그룹이 없다」로 막혀 워터마크가 안 찍힌다(fail-closed).
            #    실제 프로젝트는 소스가 있으므로 픽스처도 그래야 검증이 성립한다.
            return 0, "Source/A.cpp\nSource/A.h\nSource/B.cpp\nSource/B.h"
        return 0, ""
    return run


def ev(pid="Sim/Demo", subject="feat: x"):
    return Event(project_id=pid, ref="refs/heads/main", old="a" * 40, new="b" * 40,
                 subject=subject)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-idx-test-"))
    paths = make_project(tmp)
    reg = FakeReg(tmp)

    print("\n[1] [중요] 미러를 덮어쓰지 않는다 — ff-only")
    log = []
    r = process_event(ev(), registry=reg, git=git_ok(log), reindex=lambda p: 7)
    cmds = [" ".join(c) for c in log]
    check("fetch 한다", any(c.startswith("fetch") for c in cmds), str(cmds))
    check("[중요] merge --ff-only 를 쓴다",
          any("merge --ff-only" in c for c in cmds), str(cmds))
    check("[중요] reset --hard 를 쓰지 않는다",
          not any("reset" in c for c in cmds), str(cmds))
    check("소스 변경만 센다 (§5.2-E)",
          any("diff --name-only" in c and c.endswith("Source") for c in cmds), str(cmds))
    check("변경 파일 수", r.source_changed == 2, str(r.source_changed))
    check("오류 없음", r.ok, r.error)

    print("\n[2] 첫 실행은 재색인한다 (다이제스트가 없다)")
    check("재색인함", r.reindexed and r.docs == 7, f"{r.reindexed} {r.docs}")
    check("다이제스트가 저장된다", bool(read_digest(paths)))

    print("\n[3] [중요] 컨텍스트가 그대로면 재색인하지 않는다")
    calls = []
    r2 = process_event(ev(), registry=reg, git=git_ok([]),
                       reindex=lambda p: calls.append(1) or 7)
    check("[중요] 재색인을 부르지 않는다", calls == [], str(calls))
    check("건너뛴 사유를 남긴다", "변화 없음" in r2.skipped, r2.skipped)
    check("[중요] 커서가 최신이면 같은 커밋을 다시 걷지 않는다 (`#280`)",
          r2.source_changed == 0 and r2.commits_total == 0,
          f"{r2.source_changed} {r2.commits_total}")
    check("[중요] 걷기 단계의 사유를 재색인 절이 덮지 않는다",
          "최신" in r2.skipped and "변화 없음" in r2.skipped, r2.skipped)
    check("그래도 실패는 아니다", r2.ok)

    print("\n[3-1] 합성이 돌았는데 문서가 안 바뀌면 그 사실을 덧붙인다")
    rewind(paths)

    class NoChange:
        written, lost, aborted = 0, 0, ""
        summary = "그룹 2 → 통과 0"
        results: list = []

    r2b = process_event(ev(), registry=reg, git=git_ok([]), reindex=lambda p: 7,
                        synth_run=lambda *a, **k: NoChange())
    check("소스 변경은 셌다", r2b.source_changed == 2, str(r2b.source_changed))
    check("이유를 덧붙인다", "합성이 문서를 바꾸지 않았다" in r2b.skipped, r2b.skipped)

    print("\n[4] 컨텍스트가 바뀌면 다시 색인한다")
    (paths.context / "B.md").write_text("---\ntags: [y]\n---\n새 문서", encoding="utf-8")
    calls.clear()
    r3 = process_event(ev(), registry=reg, git=git_ok([]),
                       reindex=lambda p: calls.append(1) or 9)
    check("재색인함", r3.reindexed and len(calls) == 1, f"{r3.reindexed} {calls}")
    check("문서 수", r3.docs == 9)
    check("다이제스트 갱신", read_digest(paths) == context_digest(paths))

    print("\n[5] [중요] 워터마크 갱신이 주석·순서를 뭉개지 않는다")
    text = paths.config.read_text(encoding="utf-8")
    check("커밋이 전진했다", "b" * 40 in text, text[:120])
    check("사용자 주석 보존", "사용자가 손으로 쓴 주석" in text)
    check("인라인 주석 보존", "# 소스 한정 (§5.2-E)" in text)
    check("항목 순서 보존", text.index("last_indexed_commit") < text.index("source"))
    check("임시 파일 안 남음", not list(paths.root.glob("*.tmp")))

    print("\n[6] [중요] 등록되지 않은 project_id 는 거부 (§5.5.4-④)")
    r4 = process_event(ev(pid="Someone/Else"), registry=reg, git=git_ok([]),
                       reindex=lambda p: 1)
    check("거부", not r4.ok and "등록되지 않은" in r4.error, r4.error)
    check("대소문자는 접어서 매칭",
          process_event(ev(pid="sim/DEMO"), registry=reg, git=git_ok([]),
                        reindex=lambda p: 1).ok)

    print("\n[7] [중요] fetch 가 실패하면 재색인하지 않는다")
    calls.clear()

    def git_fetch_fail(repo, *args):
        if args[0] == "fetch":
            return 128, "could not read from remote"
        return 0, "b" * 40

    r5 = process_event(ev(), registry=reg, git=git_fetch_fail,
                       reindex=lambda p: calls.append(1) or 1)
    check("오류로 잡는다", not r5.ok and "fetch 실패" in r5.error, r5.error)
    check("[중요] 재색인을 부르지 않는다", calls == [], str(calls))

    print("\n[8] [중요] 미러가 갈라지면 조용히 덮지 않는다")

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
    check("[중요] 다이제스트를 갱신하지 않는다 (다음에 다시 시도한다)",
          read_digest(paths) != context_digest(paths))

    print("\n[10] 소스 클론이 없으면 거부")
    shutil.rmtree(paths.repo)
    r8 = process_event(ev(), registry=reg, git=git_ok([]), reindex=lambda p: 1)
    check("거부", not r8.ok and "소스 클론이 없다" in r8.error, r8.error)

    print("\n[10-1] [중요] 트윈이 자란다 — 합성기가 색인기에 물려 있다 (중 1.2)")
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
    check("[중요] 커밋 해시를 넘긴다 (source_commit 스탬프의 원천)",
          seen.get("commit") == "b" * 40, seen.get("commit"))
    check("합성 결과가 보고된다", r9.synth_written == 1, r9.summary)
    check("[중요] 합성이 문서를 바꿨으니 재색인이 돈다", r9.reindexed and calls == [1], r9.summary)
    check("그래프도 갱신 시도한다", bool(r9.graph_notes), str(r9.graph_notes))
    check("요약에 다 들어간다", "합성" in r9.summary and "색인" in r9.summary, r9.summary)

    print("\n[10-2] [중요] 유실을 삼키지 않는다 (워터마크가 전진하므로 영구 유실이다)")

    class LostS:
        written, lost, aborted = 0, 2, ""
        summary = "그룹 2 → 통과 0 · [중요] 사실 거부 2"

        class G:
            def __init__(self, k, why):
                self.key, self.reason, self.lost = k, why, True
        results = [G("Source/A", "사실 게이트 거부 — 유령 식별자"),
                   G("Source/B", "LLM 실패: 타임아웃")]

    rewind(p3)
    r10 = process_event(ev(), registry=FakeReg(tmp / "grow"), git=git_ok([]),
                        reindex=lambda p: 1, synth_run=lambda *a, **k: LostS())
    check("유실 수를 센다", r10.synth_lost == 2, str(r10.synth_lost))
    check("[중요] 어느 그룹인지 남긴다", len(r10.lost_groups) == 2, str(r10.lost_groups))
    check("  사유도 남긴다", "유령 식별자" in r10.lost_groups[0], r10.lost_groups[0])
    check("요약이 유실을 드러낸다", "유실 2" in r10.summary, r10.summary)

    print("\n[10-3] 합성을 끌 수 있다 (노드가 죽었을 때)")
    off = []
    rewind(p3)
    r11 = process_event(ev(), registry=FakeReg(tmp / "grow"), git=git_ok([]),
                        reindex=lambda p: 1, synthesize=False,
                        synth_run=lambda *a, **k: off.append(1))
    check("[중요] 합성을 부르지 않는다", off == [], str(off))
    check("  그래도 그래프는 갱신한다", bool(r11.graph_notes), str(r11.graph_notes))

    print("\n[10-4] [중요] 합성이 터져도 색인기가 죽지 않는다")

    def boom_synth(*a, **k):
        raise RuntimeError("브로커 죽음")

    rewind(p3)
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

    # ══════════════════════════════════════════════════════════════════
    # [12] 분석 커서 (`#278` — 사용자 지시 2026-08-23)
    #      불변식: 기준은 **config 의 커서**다 · 커밋을 **하나씩** 걷는다 ·
    #              소스 밖은 스킵하되 **커서는 전진**한다 · 못 끝낸 커밋은 **넘지 않는다**
    # ══════════════════════════════════════════════════════════════════
    import re as _re

    def cursor_of(paths) -> str:
        m = _re.search(r"^\s*analyzed_commit:\s*(\S*)\s*$",
                       paths.config.read_text(encoding="utf-8"), flags=_re.MULTILINE)
        return m.group(1) if m else ""

    def git_walk(commits, *, diffs=None, head=None, log=None):
        """푸시가 없어 **HEAD 가 안 움직이는** 가짜 git — NS 의 실제 상태다.

        `diffs` 는 커밋별 diff 결과(없으면 소스 2건). `log` 를 주면 그것을 쓴다.
        """
        h = head or ("b" * 40)

        def run(repo, *args):
            if args[0] == "fetch":
                return 0, ""
            if args[0] == "rev-parse":
                return 0, h                      # [중요] fetch 전후가 **같다**
            if args[0] == "log":
                return 0, (log if log is not None else "\n".join(reversed(commits)))
            if args[0] == "diff":
                target = args[3]                 # diff --name-only prev c -- Source
                if diffs is not None:
                    return 0, diffs.get(target, "Source/A.cpp\nSource/B.cpp")
                return 0, "Source/A.cpp\nSource/B.cpp"
            if args[0] == "ls-files":
                return 0, "Source/A.cpp\nSource/A.h\nSource/B.cpp\nSource/B.h"
            return 0, ""
        return run

    def synth_writes(paths_, *, changed=None, commit="", **kw):
        """실제로 그 그룹의 문서를 만든다 — 커서 전진의 전제다."""
        for k in {str(Path(f).parent / Path(f).stem) for f in (changed or [])}:
            d = paths_.context / f"{k}.md"
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(f"---\nsource_commit: {commit}\n---\n본문", encoding="utf-8")

        class S:
            written, lost, aborted = 1, 0, ""
            summary = "그룹 1 → 통과 1"
            results: list = []
        return S()

    print("\n[12-1] [중요] 기준은 클론 HEAD 가 아니라 커서다 (`#279` — NS 의 상태)")
    pc = make_project(tmp / "cur")
    C1, C2, C3 = "1" * 40, "2" * 40, "3" * 40
    rewind(pc)                                          # 커서 = a*40, HEAD = b*40 고정
    r = process_event(ev(), registry=FakeReg(tmp / "cur"), git=git_walk([C1]),
                      reindex=lambda p: 1, synth_run=synth_writes)
    check("HEAD 가 안 움직여도 걷는다", r.commits_total == 1, r.summary)
    check("  그 커밋을 끝냈다", r.commits_done == 1, r.summary)
    check("[중요] 커서가 파일에 남는다", cursor_of(pc) == C1, cursor_of(pc))

    print("\n[12-2] [중요] 커밋을 하나씩 걷는다 — 커서가 마지막 완료 커밋을 가리킨다")
    rewind(pc)
    r = process_event(ev(), registry=FakeReg(tmp / "cur"),
                      git=git_walk([C1, C2, C3]), reindex=lambda p: 1,
                      synth_run=synth_writes)
    check("셋을 다 걷는다", (r.commits_total, r.commits_done) == (3, 3), r.summary)
    check("커서 = 마지막 커밋", cursor_of(pc) == C3, cursor_of(pc))

    print("\n[12-3] [중요] 중간에서 멈추면 커서는 그 앞에 있다 (재개 지점)")
    rewind(pc)
    hit = {"n": 0}

    def synth_second_fails(paths_, *, changed=None, commit="", **kw):
        hit["n"] += 1
        if hit["n"] == 2:                               # 두 번째 커밋에서 문서를 안 만든다
            for f in changed or []:
                d = paths_.context / f"{Path(f).parent / Path(f).stem}.md"
                if d.exists():
                    d.unlink()

            class L:
                written, lost, aborted = 0, 1, ""
                summary = "그룹 1 → 통과 0 · 사실 거부 1"
                results: list = []
            return L()
        return synth_writes(paths_, changed=changed, commit=commit)

    r = process_event(ev(), registry=FakeReg(tmp / "cur"),
                      git=git_walk([C1, C2, C3]), reindex=lambda p: 1,
                      synth_run=synth_second_fails)
    check("[중요] 실패한 커밋을 넘지 않는다", r.commits_done == 1, r.summary)
    check("  커서는 직전 완료 커밋", cursor_of(pc) == C1, cursor_of(pc))
    check("  멈춘 사유를 남긴다", "문서 없음" in r.halted, r.halted)
    check("  세 번째 커밋을 건드리지 않았다", hit["n"] == 2, str(hit["n"]))

    print("\n[12-4] [중요] 소스 밖 변경만 있는 커밋 — 합성 없이 커서만 전진 (`#281`)")
    rewind(pc)
    called = []
    r = process_event(
        ev(), registry=FakeReg(tmp / "cur"),
        git=git_walk([C1, C2], diffs={C1: "", C2: "Source/A.cpp"}),
        reindex=lambda p: 1,
        synth_run=lambda *a, **k: called.append(k.get("commit")) or synth_writes(*a, **k))
    check("소스 밖 커밋에는 합성을 안 부른다", called == [C2], str(called))
    check("[중요] 그래도 커서는 전진한다 (안 그러면 무한 재시도)",
          cursor_of(pc) == C2, cursor_of(pc))
    check("건너뛴 것을 센다", r.commits_nonsource == 1, r.summary)
    check("  사유를 남긴다", any("소스 밖" in x for x in r.nonsource_notes),
          str(r.nonsource_notes))

    print("\n[12-5] 커서가 비어 있으면 시끄럽게 보고하고 전 이력을 걷지 않는다 (M2 금기)")
    pn = make_project(tmp / "nocur")
    # [중요] **둘 다 비어야** 이 경로다 — 워터마크가 있으면 [12-9] 의 이행 폴백이 맞다.
    pn.config.write_text("project_id: Sim/Demo\nindex:\n  last_indexed_commit: ''\n",
                         encoding="utf-8")
    walked = []
    r = process_event(ev(), registry=FakeReg(tmp / "nocur"),
                      git=git_walk([C1, C2, C3]), reindex=lambda p: 1,
                      synth_run=lambda *a, **k: walked.append(1))
    check("[중요] 합성을 부르지 않는다", walked == [], str(walked))
    check("커서 없음을 사유로 남긴다", "커서가 비어 있다" in r.skipped, r.skipped)
    check("[중요] 「최신」이라고 말하지 않는다", "최신" not in r.skipped, r.skipped)

    print("\n[12-6] 커서 키가 없는 구 config 에도 기록된다 (`index:` 아래 삽입)")
    pn2 = make_project(tmp / "oldcfg")
    pn2.config.write_text(CONFIG_NO_CURSOR.replace(
        "  last_indexed_at: '2026-08-01T00:00:00'",
        "  last_indexed_at: '2026-08-01T00:00:00'\n  analyzed_commit: " + "a" * 40),
        encoding="utf-8")
    r = process_event(ev(), registry=FakeReg(tmp / "oldcfg"), git=git_walk([C1]),
                      reindex=lambda p: 1, synth_run=synth_writes)
    check("걷고 기록한다", cursor_of(pn2) == C1, cursor_of(pn2))
    from master.events.consumer import _update_cursor as _uc
    pn3 = make_project(tmp / "insert")
    pn3.config.write_text("project_id: Sim/Demo\nindex:\n  last_indexed_commit: x\n",
                          encoding="utf-8")
    check("[중요] 키가 없으면 새로 넣는다", _uc(pn3, C2) and cursor_of(pn3) == C2,
          pn3.config.read_text(encoding="utf-8"))
    pn4 = make_project(tmp / "noindex")
    pn4.config.write_text("project_id: Sim/Demo\n", encoding="utf-8")
    check("  `index:` 절이 없으면 조용히 넘기지 않고 실패를 알린다",
          _uc(pn4, C2) is False)

    print("\n[12-7] 커서가 이 이력의 조상이 아니면 사람에게 넘긴다 (되감김/강제 푸시)")
    rewind(pc)
    r = process_event(ev(), registry=FakeReg(tmp / "cur"),
                      git=git_walk([], log=""), reindex=lambda p: 1,
                      synth_run=synth_writes)
    check("걸을 커밋 0 을 「최신」으로 접지 않는다",
          "조상이 아니다" in r.skipped, r.skipped)

    print("\n[12-8] 합성이 꺼져 있으면 커서를 전진시키지 않는다")
    rewind(pc)
    r = process_event(ev(), registry=FakeReg(tmp / "cur"), git=git_walk([C1]),
                      reindex=lambda p: 1, synthesize=False)
    check("[중요] 커서 그대로", cursor_of(pc) == "a" * 40, cursor_of(pc))
    check("  사유를 남긴다", "합성이 꺼져" in r.halted, r.halted)
    check("  그래프는 갱신한다", bool(r.graph_notes), str(r.graph_notes))

    print("\n[12-9] 이행 — 커서 키가 없으면 **번 워터마크**를 출발점으로 삼고, 그것을 말한다")
    pm = make_project(tmp / "migrate")
    pm.config.write_text(CONFIG_NO_CURSOR.replace(
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "9" * 40), encoding="utf-8")
    r = process_event(ev(), registry=FakeReg(tmp / "migrate"), git=git_walk([C1]),
                      reindex=lambda p: 1, synth_run=synth_writes)
    check("걷는다 (「최초 합성 필요」로 접지 않는다)", r.commits_done == 1, r.summary)
    check("출발점이 워터마크", r.cursor_from == "9" * 40, r.cursor_from)
    check("[중요] 폴백을 조용히 하지 않는다", "워터마크" in r.cursor_note, r.cursor_note)
    check("  그리고 커서를 적는다", cursor_of(pm) == C1, cursor_of(pm))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
