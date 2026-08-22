"""0단계 셋 — 마운트 게이트(`#242`) · 워터마크(`#244`) · 문구(`#241`).

[중요] **실측이 이 파일을 만들었다** (2026-08-22). NS 를 등록만 해 두고 합성을 보류했는데,
색인기가 5분 타이머로 **마운트되지 않은 NS 를 색인하고 워터마크를 찍어** 온보딩 판정이
*"전부 초기화됐다"* 고 **거짓 보고**했다. 판정기를 만든 당일에 그 판정기가 무력화된 것이다.

    18:00:17  이벤트 0건 → 프로젝트 2개
              [완료] Sim/NS: dcf315c0→dcf315c0 · 재색인 2건      ← 마운트 밖인데 돌았다
    그 뒤     plan('NS') → remaining: [] · "전부 초기화됐다"     ← 42그룹 중 2건인데 완료

`python3 master/test_mount_gate.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class _Reg:
    """레지스트리 대역 — 마운트만 흉내낸다."""

    def __init__(self, active, names, cfgs=None):
        self.active, self.names = active, names
        self._cfgs = cfgs or {}
        self.root = Path("/tmp")

    def find_by_project_id(self, pid):
        for n in self.names:
            if self._cfgs.get(n, n) == pid or n == pid:
                return n
        return "o/mounted" == pid and self.names[0] or None

    def config_of(self, name):
        import types
        return types.SimpleNamespace(project_id=self._cfgs.get(name, name))

    def dir_of(self, name):
        return Path("/tmp") / name


# ── #242 마운트 게이트 ──────────────────────────────────────────────

def test_gate_blocks_unmounted() -> None:
    """[중요] **git 을 부르기 전에** 막힌다 — 완료 조건 ①."""
    from master.events.consumer import Event, process_event

    calls = []

    def spy_git(repo, *args):
        calls.append(args)
        return 0, "deadbeef"

    reg = _Reg(active="Mounted", names=["Mounted", "Other"],
               cfgs={"Mounted": "o/mounted", "Other": "o/other"})
    r = process_event(Event(project_id="o/other"), registry=reg, git=spy_git)
    check("[중요] 비마운트는 건너뛴다", "마운트되지 않았다" in (r.skipped or ""), str(r.skipped))
    check("[중요] git 을 부르지 않았다", not calls, str(calls))
    check("[주의] 에러가 아니다 (유닛을 빨갛게 만들지 않는다)", not r.error, r.error)
    check("활성 이름을 사유에 적는다", "Mounted" in (r.skipped or ""), str(r.skipped))


def test_gate_fails_closed_on_empty_active() -> None:
    """[중요] **`active` 가 비어도 막힌다** — 완료 조건 ③.

    2026-08-21 에 만든 게이트가 정확히 이 구멍(빈 active 면 통과)을 가졌다.
    「모르면 통과」는 게이트가 아니다.
    """
    from master.events.consumer import Event, process_event

    calls = []
    reg = _Reg(active="", names=["Mounted"], cfgs={"Mounted": "o/mounted"})
    r = process_event(Event(project_id="o/mounted"), registry=reg,
                      git=lambda *a: (calls.append(a), (0, "x"))[1])
    check("[중요] active 가 비면 통과시키지 않는다", "마운트되지 않았다" in (r.skipped or ""),
          str(r.skipped))
    check("그때도 git 을 안 부른다", not calls, str(calls))
    check("사유가 '(없음)' 을 밝힌다", "(없음)" in (r.skipped or ""), str(r.skipped))


def test_poll_loop_only_mounted() -> None:
    """빈 스풀 폴링이 마운트된 하나만 만든다 — 완료 조건 ②(`프로젝트 1개`)."""
    src = (Path(__file__).resolve().parent / "events" / "consumer.py").read_text(encoding="utf-8")
    body = src.split("if not batch.events:")[1].split("sp.done(batch)")[0]
    check("[중요] 폴링이 reg.names 전부를 돌지 않는다",
          "for _name in reg.names:" not in body, "전수 순회가 남아 있다")
    check("마운트된 것만 만든다", "_mounted" in body and "reg.active" in body, body[:120])


# ── #244 워터마크 ───────────────────────────────────────────────────

def test_watermark_needs_context() -> None:
    """[중요] **컨텍스트 MD 0건이면 워터마크가 비어 있다** — `#244` 완료 조건.

    실측 근거 둘: ServerTest 가 MD 0건인데 `last_indexed_commit` 이 HEAD 였고,
    NS 는 표본 2건으로 찍혀 「완료」가 됐다.
    """
    from master.events import consumer as C

    tmp = Path(tempfile.mkdtemp(prefix="ax-wm-test-"))
    (tmp / "repo").mkdir()
    (tmp / "context").mkdir()
    cfg = tmp / "config.yaml"
    cfg.write_text("version: 1\nname: T\nindex:\n  last_indexed_commit: ''\n"
                   "  last_indexed_at: ''\n", encoding="utf-8")

    from master.context_search.paths import ProjectPaths
    paths = ProjectPaths(name="T", root=tmp)

    # [중요] **여기서 함정 하나를 잡았다** — `context_digest()` 는 빈 디렉토리에도 해시를
    #    돌려준다(빈 문자열의 sha256). 그것으로 판정하면 게이트가 새므로 개수로 잰다.
    check("전제: context/ 는 있고 MD 는 0건", C.has_context_md(paths) is False,
          f"digest={C.context_digest(paths)!r}")
    check("[주의] digest 는 그때도 참이다 (그래서 판정 근거가 될 수 없다)",
          bool(C.context_digest(paths)), C.context_digest(paths))
    (tmp / "context" / "sub").mkdir()
    (tmp / "context" / "sub" / "a.md").write_text("x", encoding="utf-8")
    check("하위 디렉토리의 MD 를 센다", C.has_context_md(paths) is True)
    (tmp / "context" / "sub" / "a.md").unlink()
    C._update_watermark(paths, "abc1234")
    check("(대조군) 직접 부르면 찍힌다", "abc1234" in cfg.read_text(encoding="utf-8"))

    # 게이트가 그 호출을 막는지 — 소스로 잰다(process_event 전체를 태우지 않는다)
    src = (Path(__file__).resolve().parent / "events" / "consumer.py").read_text(encoding="utf-8")
    check("[중요] 워터마크가 MD 개수 조건 아래 있다",
          "if r.to_commit and has_context_md(paths):" in src)
    check("[주의] digest 로 판정하지 않는다",
          "if r.to_commit and context_digest(paths):" not in src)
    check("안 찍은 것을 사유로 남긴다", "워터마크 미기입" in src)
    check("[주의] to_commit 만 보는 옛 조건이 사라졌다",
          "if r.to_commit:\n        _update_watermark" not in src)


# ── #241 문구 ───────────────────────────────────────────────────────

def test_set_active_note_true() -> None:
    """거짓 문구가 남아 있지 않다 — `#241` 최소 완료 조건."""
    src = (Path(__file__).resolve().parent / "projects" / "logic.py").read_text(encoding="utf-8")
    check("멈춘다는 주장이 근거를 든다", "멈춰 있었다(#242)" in src)
    # [중요] 따라잡기 기준은 워터마크가 아니라 미러 HEAD 다 — #244 로 워터마크가 조건부가 됐으니
    #    옛 문구("last_indexed_commit 부터 따라잡는다")는 이제 확실히 거짓이다
    check("[중요] 옛 거짓 문구가 사라졌다",
          "last_indexed_commit 부터 따라잡는다" not in src)
    check("정확한 기제를 적었다", "미러 HEAD 부터 따라잡는다" in src)


if __name__ == "__main__":
    for fn in (test_gate_blocks_unmounted, test_gate_fails_closed_on_empty_active,
               test_poll_loop_only_mounted, test_watermark_needs_context,
               test_set_active_note_true):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_mount_gate: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
