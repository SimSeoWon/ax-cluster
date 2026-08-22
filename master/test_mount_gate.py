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
    # [중요] 조건이 **두 번 좁아졌다**: to_commit 만 → MD 0건 가드(#244) → 미합성 0 (#274).
    #    지금 기준은 `synth_complete()` 다. 옛 두 형태가 남아 있으면 되돌아간 것이다.
    # [주의] 호출 형태를 문자열로 박지 않는다 — 주입 인자가 붙어 `synth_complete(paths, git=run)`
    #    이 되자 칸이 빨갛게 됐다(실측). **함수 이름**으로 잰다.
    check("[중요] 워터마크가 synth_complete 아래 있다", "synth_complete(" in src)
    check("주입 자리를 통과시킨다 (테스트가 실제 git 을 안 탄다)", "git=run" in src)
    check("[주의] digest 로 판정하지 않는다",
          "if r.to_commit and context_digest(paths):" not in src)
    check("[주의] MD 0건 가드만으로 찍지 않는다",
          "if r.to_commit and has_context_md(paths):" not in src)
    check("안 찍은 것을 사유로 남긴다", "워터마크 미기입" in src)
    check("[주의] to_commit 만 보는 옛 조건이 사라졌다",
          "if r.to_commit:\n        _update_watermark" not in src)


# ── #274 부분 완료를 완료로 읽지 않는다 ────────────────────────────

def test_partial_synth_is_not_done() -> None:
    """[중요] **실측이 이 칸을 만들었다** (2026-08-22).

    NS 가 42그룹 중 13건인 상태에서 `synth [완료]` 로 찍혔고, 그 상태로 마운트하면 색인기가
    워터마크를 찍어 온보딩이 *"전부 초기화됐다"* 고 거짓 보고했다. `#244` 의 0건 가드는
    **부분 완료를 막지 못한다.**

    [주의] **개수 비교로는 안 된다** — ModularStage 는 문서 1,055 > 그룹 909 다(`_archive/`·
    `_domains/`·삭제된 파일의 문서가 쌓인다). **그룹마다 문서가 있는지**를 세야 한다.
    """
    from master.events.consumer import synth_complete
    from master.context_search.paths import ProjectPaths
    from master.projects.onboard import _probe_synth

    tmp = Path(tempfile.mkdtemp(prefix="ax-partial-test-"))
    (tmp / "repo" / "Source" / "M").mkdir(parents=True)
    for stem in ("A", "B", "C"):
        for ext in (".h", ".cpp"):
            (tmp / "repo" / "Source" / "M" / f"{stem}{ext}").write_text("int x;\n",
                                                                       encoding="utf-8")
    (tmp / "context").mkdir()
    paths = ProjectPaths(name="T", root=tmp)

    # git 없이 그룹을 세게 — list_source_files 는 git ls-files 를 쓰므로 주입 대신 실제 git 을 만든다
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp / "repo")], check=True)
    subprocess.run(["git", "-C", str(tmp / "repo"), "add", "-A"], check=True,
                   capture_output=True)

    done, why = _probe_synth(paths)
    check("0/3 은 미완", not done and "0/3" in why, why)
    check("[중요] 분모가 보인다", "3" in why and "미합성" in why, why)
    check("워터마크 게이트도 막는다", not synth_complete(paths)[0], str(synth_complete(paths)))

    # 부분 — 두 그룹만 문서를 만든다
    (tmp / "context" / "Source" / "M").mkdir(parents=True)
    for stem in ("A", "B"):
        (tmp / "context" / "Source" / "M" / f"{stem}.md").write_text("x", encoding="utf-8")
    done2, why2 = _probe_synth(paths)
    check("[중요] 2/3 은 **미완이다** (부분 완료를 완료로 읽지 않는다)",
          not done2 and "2/3" in why2, why2)
    check("워터마크 게이트도 여전히 막는다", not synth_complete(paths)[0])

    # 전부
    (tmp / "context" / "Source" / "M" / "C.md").write_text("x", encoding="utf-8")
    done3, why3 = _probe_synth(paths)
    check("3/3 이면 완료", done3 and "3/3" in why3, why3)
    check("그때 워터마크 게이트가 통과한다", synth_complete(paths)[0])

    # [주의] MD 가 있기만 하면 통과하던 옛 기준이 남아 있지 않은지
    src = (Path(__file__).resolve().parent / "projects" / "onboard.py").read_text(
        encoding="utf-8")
    check("[주의] 옛 기준(MD 가 있으면 완료)이 사라졌다",
          'return True, f"MD {n}건"' not in src)


# ── #243 요청 표면의 마운트 강제 ────────────────────────────────────

def test_request_surface_gate() -> None:
    """[중요] **사용자 요구가 이것이다** — *"인프라 서버는 단일 하나의 프로젝트만 관리한다.
    그 이외의 작업은 모두 거절하도록 요청에 태그 넣으라"*.

    [주의] 배선 전 실측(2026-08-22): `resolve(req.project or "")` 가 태그를 **검사 없이** 따라
    `project=NS`(비마운트) 요청이 `thesaurus.register` 까지 진입해 `open()` 에서 **500** 으로
    죽었다. 막은 것은 우리 코드가 아니라 **systemd 샌드박스**였다 — 의도된 방어가 아니다.
    """
    import os
    from master.context_search.paths import resolve_mounted_only
    from master.projects.config import ConfigError

    class R:
        def __init__(self, active, names):
            self.active, self.names, self.root = active, names, Path("/tmp")
        def dir_of(self, n):
            return Path("/tmp") / n

    reg = R("A", ["A", "B"])
    check("활성과 같으면 통과", resolve_mounted_only("A", registry=reg).name == "A")
    check("빈 태그는 활성으로", resolve_mounted_only("", registry=reg).name == "A")
    for bad in ("B", "없는것"):
        try:
            resolve_mounted_only(bad, registry=reg)
            check(f"[중요] {bad} 는 거부", False, "통과해버렸다")
        except ConfigError as e:
            check(f"{bad} 는 거부", "마운트되지 않은" in str(e) or "등록되지" in str(e), str(e))

    # [중요] **활성이 비어도 막는다** — 종전 조건 `if name and reg.active and …` 는 통과시켰다
    try:
        resolve_mounted_only("A", registry=R("", ["A"]))
        check("[중요] 활성이 비면 태그가 있어도 거부 (fail-closed)", False, "통과해버렸다")
    except ConfigError as e:
        check("활성이 비면 거부", "마운트된 프로젝트가 없다" in str(e), str(e))

    # 엔드포인트가 그 함수를 쓰고 **200 + ok:false** 로 답하는지 (형태가 계약이다)
    src = (Path(__file__).resolve().parent / "task_queue" / "server.py").read_text(
        encoding="utf-8")
    check("[중요] thesaurus 표면이 게이트를 쓴다", src.count("_mounted_paths(req.project)") == 2,
          str(src.count("_mounted_paths(req.project)")))
    # [주의] **`_paths_for` 의 `resolve(proj or "")` 는 남아 있어야 한다** — `#210` 의 의도된
    #    예외다(work 스탬프). 칸을 「전부 금지」로 쓰면 그 예외까지 잡아 거짓 실패가 난다.
    #    금지 대상은 **요청자가 고르는 태그**를 검사 없이 따르는 형태다.
    body = src.split("def thesaurus_alias_ep")[1].split("def anti_patterns_notify_ep")[0]
    check("[주의] thesaurus 표면에 검사 없는 resolve 가 없다",
          'resolve(req.project or "")' not in body)
    check("거부가 200 + ok:false 다", '"ok": False, "status": "not_mounted"' in src)
    check("사유를 담는다", '"reason": str(e)' in src)
    # [중요] work 해석은 **의도된 예외**다 (#210) — 강제하면 미종결 work 산출물이 엉뚱한 곳으로
    check("[중요] work 스탬프 경로는 예외로 남긴다",
          "여기는 `#243` 의 마운트 강제를 적용하지 않는다" in src)


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
               test_partial_synth_is_not_done, test_request_surface_gate,
               test_set_active_note_true):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_mount_gate: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
