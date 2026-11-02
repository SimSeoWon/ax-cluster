"""유휴 배치 구동 주체 — 원전 `watch.py` 유휴 사이클의 리눅스 대응
(소 3.4.4 · `#192`, 2026-08-14).

    python -m master.batch.run plan        [중요] 무엇이 돌지/왜 안 도는지만 보고 (기본)
    python -m master.batch.run run         실제로 돈다 (ax-batch.timer 가 부르는 것)
    python -m master.batch.run status      게이트·마커 현황

## 순서 — [중요] **작업 중이면 아무것도 안 돈다**

    ① events.gate.check()   진행 중 분산 작업이 있으면 **전부 미룬다** (원전: git lock 경쟁)
    ② 배치별 시간 게이트     때가 됐나 (gates.should_run)
    ③ 실행 → 마커 기록       [중요] 성공했을 때만 마커를 쓴다 (실패하면 다음 회차에 다시 온다)

[주의] **①을 배치별 게이트보다 앞에 둔다.** 원전 유휴 사이클도 *"작업 중이 아닐 때"* 를 밖에
두고 안에서 시각을 봤다. 순서를 뒤집으면 작업 중에도 시각 조건만 맞으면 도는 창이 생긴다.

## 종료코드 — [중요] 색인기와 **같은 규약**

    0   돌 것을 돌았다 (또는 돌 것이 없었다)
    4   일시 중지 게이트에 걸림 — **고장이 아니다.** `SuccessExitStatus=4` 로 받는다
    1   진짜 실패 (배치가 오류를 냈다)

색인기 유닛이 이미 이 규약을 쓴다(*"늘 빨간 유닛은 유닛이 아니다"*). 같은 뜻에 다른 숫자를
쓰면 운영자가 매번 되짚어야 한다.

## [주의] 배치는 하나뿐이다 (지금)

`rag_analysis`(소 3.4.2 `#161`) 하나다. [중요] **자리만 만들지 않기 위해 그 배치와 같은 커밋에
넣었다** — 리포트 13 §19.3 의 *"가드를 두고 타이머를 안 두면 갱신 주체가 아무도 없다"* 의
역방향(구동 주체를 두고 돌 것을 안 두면 그것도 빈 유닛이다). `planner`(`#155`)·
`recipes_synthesizer`(`#157`)·`history_harvest`(`#158`)가 오면 `BATCHES` 에 한 줄씩 늘어난다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import gates

PAUSED_EXIT = 4          # [중요] 색인기와 같은 규약


@dataclass
class BatchDef:
    """배치 하나 — 게이트 · 입력 크기 · 실행. [중요] **입력 크기를 세는 법이 정의의 일부**다.

    입력을 못 세면 게이트의 `min_entries` 가 의미를 잃는다(원전도 각 게이트가 자기 입력을
    직접 셌다 — 신호 수·로그 엔트리 수).
    """

    schedule: gates.Schedule
    label: str
    count_input: object                  # (paths) -> int
    execute: object                      # (paths) -> dict {ok, reason, ...}
    # 게이트가 `Schedule` 다섯 조건과 모양이 다른 배치만 준다 (`gates.should_run` 과 같은 시그니처)
    gate: object = None


@dataclass
class Outcome:
    key: str
    label: str
    ran: bool = False
    verdict: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def line(self) -> str:
        if self.error:
            return f"  [중요] {self.key}: {self.error}"
        if not self.ran:
            return f"  · {self.key}: {self.verdict}"
        r = self.result or {}
        extra = ""
        if r.get("entries") is not None:
            extra = f" · 엔트리 {r['entries']}건"
        if r.get("files"):
            extra += f" · 파일 {len(r['files'])}개"
        if r.get("assigned"):
            extra += f" · 번호 {len(r['assigned'])}건"
        return f"  ▶ {self.key}: 실행{extra}"


# ── 배치 정의 ────────────────────────────────────────────────────────────────

def _rag_count(paths) -> int:
    from ..context_search import search_log
    return len(search_log.read_entries(paths))


def _rag_run(paths) -> dict:
    from ..context_search import search_log_analyzer as A
    return A.run_for_project(paths)


def _plan_count(paths) -> int:
    """입력 = 작성자 디렉토리에 남은 리뷰 수 (`_archive/` 로 옮겨진 것은 이미 플랜에 반영됐다)."""
    from ..context_synth.planner import REVIEWS_DIRNAME, list_author_dirs
    return sum(1 for a in list_author_dirs(Path(paths.root) / REVIEWS_DIRNAME)
               for f in a.glob("*.md") if not f.name.startswith("_"))


def _plan_run(paths) -> dict:
    """주간 플랜 생성 → 새 플랜에 번호 (`#628` · `#627`).

    [중요] **레드마인 등록은 끈다** (사용자 결정 2026-09-16) — `plan_register` 가 프로젝트를 안
    넘겨 NS 플랜이 ModularStage 레드마인으로 떨어진다(`#632`). 그것을 고치기 전에는 켜지 않는다.
    """
    from ..context_synth import fix_index, planner
    say = lambda m: print(f"    {m}", flush=True)                    # noqa: E731
    generated = planner.run_weekly_plans(paths, redmine=False, logf=say)
    swept = fix_index.sweep(paths.root, logf=say)
    return {"ok": True, "generated": bool(generated), "assigned": swept["assigned"]}


def _candidate_count(paths) -> int:
    from ..context_synth.dismissal_candidates import count_open
    return count_open(paths)


def _candidate_run(paths) -> dict:
    from ..context_synth.dismissal_candidates import collect
    result = collect(paths)
    if result.get("unjudged"):
        print(f"    [기각 후보] 미판정: {', '.join(result['unjudged'])}", flush=True)
    return result


def _revalidation_count(paths) -> int:
    """입력 = 표시된 문서 + 표시된 조각 기록 **전부** (후보 유무 무관).

    [중요] 후보가 붙은 기록도 센다 — 채택·삭제는 정산(`settle_tasks`, LLM 0)을 돌려야만 보인다.
    후보 대기만 남아도 매일 한 번 git 조회가 돈다(호출 비용 0).
    """
    from ..work.revalidation import marked_documents, task_entries, unreadable_summary
    unreadable = []
    n = len(marked_documents(paths, unreadable=unreadable))
    line = unreadable_summary(unreadable)
    if line:
        # [중요] 매 회차(plan·run 둘 다) 사람이 보도록 한 줄 — 파일별 줄은 찍지 않는다.
        print(f"    {line}", flush=True)
    return n + len(task_entries(paths.root))


def _revalidation_half(fn) -> dict:
    """반쪽 하나. 예외도 결과로 바꾼다 — [중요] 한쪽 실패가 다른 쪽을 가리지 않게."""
    try:
        result = fn() or {}
    except Exception as e:                                  # noqa: BLE001
        result = {"ok": False, "reason": f"{type(e).__name__}: {e}", "entries": 0}
    if not isinstance(result, dict):
        result = {"ok": False, "reason": f"결과 형식 오류: {type(result).__name__}", "entries": 0}
    return result


def _revalidation_run(paths, *, documents=None, settle=None, tasks=None) -> dict:
    """문서 재합성 → 조각 정산 → 조각 후보 생성 (#840 T2). 셋 다 돌고 결과는 따로 남는다.

    호출 예산은 반쪽마다 따로다 — 문서 최대 2호출 · 조각 최대 2호출(정산은 LLM 0).
    전체 ok = 셋 다 ok. 주입 자리는 테스트용(`documents`·`settle`·`tasks` 는 `(paths)->dict`).
    """
    from ..work import revalidation as RV
    say = lambda m: print(f"    {m}", flush=True)                    # noqa: E731
    documents = documents or (lambda p: RV.run_documents(p, limit=2))
    settle = settle or (lambda p: RV.settle_tasks(p, logf=say))
    tasks = tasks or (lambda p: RV.run_tasks(p, limit=2, logf=say))

    doc = _revalidation_half(lambda: documents(paths))
    say(f"[재검증] 문서 — ok={doc.get('ok')} · 대상 {doc.get('entries', 0)}건"
        + (f" · 머리말 못 읽음 {len(doc['unreadable'])}건" if doc.get("unreadable") else "")
        + (f" · {doc.get('reason')}" if doc.get("reason") else ""))
    st = _revalidation_half(lambda: settle(paths))
    say(f"[재검증] 조각 정산 — ok={st.get('ok')} · {st.get('summary') or st.get('entries', 0)}"
        + (f" · {st.get('reason')}" if st.get("reason") else ""))
    tk = _revalidation_half(lambda: tasks(paths))
    say(f"[재검증] 조각 후보 — ok={tk.get('ok')} · 대상 {tk.get('entries', 0)}건 · "
        f"호출 {tk.get('calls', 0)} · 채택 대기 {tk.get('waiting', 0)}"
        + (f" · {tk.get('reason')}" if tk.get("reason") else ""))

    halves = (("문서", doc), ("정산", st), ("조각", tk))
    return {"ok": all(r.get("ok") is True for _, r in halves),
            "entries": sum(int(r.get("entries") or 0) for _, r in halves),
            "documents": doc, "tasks": {"settle": st, "run": tk},
            "reason": " / ".join(f"{n}: {r.get('reason') or '실패'}"
                                 for n, r in halves if r.get("ok") is not True)}


BATCHES = [
    BatchDef(schedule=gates.RAG_ANALYSIS,
             label="RAG 채널 분석 (stdlib·LLM 0)",
             count_input=_rag_count,
             execute=_rag_run),
    BatchDef(schedule=gates.WEEKLY_PLAN,
             label="주간 개선 플랜 (상용 LLM · 레드마인 등록 끔)",
             count_input=_plan_count,
             execute=_plan_run,
             gate=gates.should_run_weekly_plan),
    BatchDef(schedule=gates.DISMISSAL_CANDIDATES,
             label="기각 후보 수집 (상태 변경 없음)",
             count_input=_candidate_count, execute=_candidate_run,
             gate=gates.should_run_dismissal_candidates),
    BatchDef(schedule=gates.CLOUD_REVALIDATION,
             label="로컬 산출물 클라우드 재검증 — 문서 재합성 · 조각 정산·후보 "
                   "(표시된 대상만, 각 회당 최대 2호출 · 정산 LLM 0)",
             count_input=_revalidation_count, execute=_revalidation_run),
]


def _verdict(b: BatchDef, cfg: dict, paths, n: int, now) -> "gates.Verdict":
    return (b.gate or gates.should_run)(b.schedule, cfg, paths.root, input_count=n, now=now)


# ── 구동 ─────────────────────────────────────────────────────────────────────

def plan(paths, cfg: dict, *, now: datetime | None = None) -> list:
    """무엇이 돌지 **판정만** 한다. 부작용 0 — 마커도 안 쓴다."""
    out = []
    for b in BATCHES:
        o = Outcome(key=b.schedule.key, label=b.label)
        try:
            n = int(b.count_input(paths))
        except Exception as e:                              # noqa: BLE001
            o.error = f"입력을 세지 못했다: {type(e).__name__}: {e}"
            out.append(o)
            continue
        v = _verdict(b, cfg, paths, n, now)
        o.verdict = v.reason
        o.ran = False
        o.result = {"would_run": v.run, "input": n}
        out.append(o)
    return out


def run(paths, cfg: dict, *, now: datetime | None = None, force: bool = False) -> list:
    """게이트를 통과한 배치를 돌리고 마커를 쓴다.

    [중요] **`force` 가 넘는 것과 못 넘는 것을 정확히 적는다** (첫 판은 문서와 코드가 어긋났다):

        넘는다     시각 · 요일 · 최소 간격 · 입력 최소치
                   (입력이 얇아도 안전하다 — 분석기가 스스로 「판단 보류」를 낸다)
        못 넘는다  [중요] **`batch.<key>=false`** — 운영자가 **명시적으로 끈 것**이다
                   [중요] **일시 중지 게이트**(작업 중) — 넘게 만들면 원전이 피하려던
                      git lock 경쟁이 그대로 돌아온다. 그것은 `main()` 밖에 있다
    """
    out = []
    for b in BATCHES:
        o = Outcome(key=b.schedule.key, label=b.label)
        try:
            n = int(b.count_input(paths))
        except Exception as e:                              # noqa: BLE001
            o.error = f"입력을 세지 못했다: {type(e).__name__}: {e}"
            out.append(o)
            continue

        v = _verdict(b, cfg, paths, n, now)
        o.verdict = v.reason
        # [중요] `force` 도 **활성 플래그는 못 넘는다** — 운영자가 끈 것을 도구가 되살리지 않는다.
        may_force = force and gates.enabled(cfg, b.schedule.key)
        if not (v.run or may_force):
            if force and not may_force:
                o.verdict = f"force 무시됨 — {v.reason} (활성 플래그는 force 로 넘지 않는다)"
            out.append(o)
            continue
        if may_force and not v.run:
            o.verdict = f"force — 게이트 무시 ({v.reason})"

        try:
            o.result = b.execute(paths) or {}
        except Exception as e:                              # noqa: BLE001
            # [중요] 배치 하나가 죽어도 나머지는 돈다. 다만 **조용히 넘기지 않는다.**
            o.error = f"{type(e).__name__}: {e}"
            out.append(o)
            continue

        if not o.result.get("ok", False):
            o.error = f"배치가 실패를 보고했다: {o.result.get('reason', '?')}"
            out.append(o)
            continue

        o.ran = True
        if o.result.get("complete") is False:
            # 예산으로 끊겨도 주간 마커는 쓴다 — 안 쓰면 시간 타이머가 같은 주말 내내 매시
            # 다시 돈다(#823). 남은 항목은 캐시를 이어 **다음 주말**에 계속한다.
            o.verdict = f"{o.verdict} · 예산으로 끊김 — 남은 항목은 다음 주말에 이어간다"
        m = gates.write_marker(paths.root, b.schedule.key, now=now)
        if not m.get("ok"):
            # 마커를 못 쓰면 **다음 회차에 또 돈다** — 그건 알아야 할 사실이다.
            o.error = m.get("reason", "마커 기록 실패")
        out.append(o)
    return out


def load_config(paths) -> dict:
    """프로젝트 config. 못 읽으면 **빈 dict** — 그러면 전부 원전 기본값으로 돈다."""
    try:
        import yaml
        return yaml.safe_load(Path(paths.config).read_text(encoding="utf-8")) or {}
    except Exception:                                        # noqa: BLE001
        return {}


def main(argv: list | None = None) -> int:
    from ..context_search.paths import resolve
    from ..events import gate as pause_gate

    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "plan"
    if cmd in ("-h", "--help", "help"):
        print("사용법: python -m master.batch.run plan|run|status [--force]")
        print("  plan    [중요] 무엇이 돌지/왜 안 도는지만 보고 (기본, 부작용 0)")
        print("  run     실제로 돈다 (ax-batch.timer 가 부르는 것)")
        print("  status  게이트·마커 현황")
        print("  --force 시각·요일·간격·입력최소치를 무시 — [중요] 활성 플래그와")
        print("          일시 중지 게이트는 넘지 않는다")
        return 0

    force = "--force" in args
    paths = resolve("")
    cfg = load_config(paths)

    # ① [중요] 작업 중이면 아무것도 안 돈다
    v = pause_gate.check()
    if v.paused:
        print(f"⏸  배치 일시 중지 — {v.reason}")
        print("   (진행 중 분산 작업이 있다. 고장이 아니다 — 종료코드 4)")
        return PAUSED_EXIT

    if cmd == "status":
        print(f"프로젝트: {paths.name} · 일시중지: {v.paused} ({v.reason})")
        for b in BATCHES:
            s = b.schedule.from_config(cfg)
            last = gates.read_marker(paths.root, s.key)
            print(f"  {s.key}: {s.schedule} {s.day} {s.hour}시 · 최소 {s.min_entries}건 · "
                  f"마지막 {last.isoformat(timespec='minutes') if last else '없음'}")
        return 0

    outcomes = plan(paths, cfg) if cmd == "plan" else run(paths, cfg, force=force)
    if cmd == "plan":
        print(f"배치 계획 ({paths.name}) — [중요] 아무것도 실행하지 않았다")
        for o in outcomes:
            mark = "▶ 돌 것" if o.result.get("would_run") else "· 안 돈다"
            print(f"  {mark} {o.key} (입력 {o.result.get('input', '?')}건) — {o.verdict or o.error}")
        return 1 if any(o.error for o in outcomes) else 0

    ran = sum(1 for o in outcomes if o.ran)
    print(f"배치 {ran}/{len(outcomes)}건 실행 ({paths.name})")
    for o in outcomes:
        print(o.line())
    return 1 if any(o.error for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
