"""레드마인 「완료」 관문 (`#883` T4) — `update_issue` 가 닫기 전에 잠금·범위 리뷰를 본다.

검증하는 것:

    ① 관문 해당 없음(apply=False) → PUT 진행 · 결과 문장 종전과 같다
    ② 관문이 막음 → PUT 0회(노트도 안 쓴다) · `[주의] … 완료 거절 — <why>`
    ③ 관문 통과 → PUT 뒤 release 호출 · `· 잠금 해제` · 해제 실패는 거절이 아니라 `[주의]` 표시
    ④ 관문 예외·형식 오류 → 막음(fail-closed) · PUT 0회
    ⑤ 닫기가 아닌 상태(해결)·노트만 → 관문을 부르지 않는다
    ⑥ 이름이 달라도 `is_closed` 상태면 닫기로 본다 · 상태 조회 실패면 닫기가 아니다
    ⑦ sender 주입 + 관문 미지정 → 관문 없음(테스트가 실 트윈을 읽지 않는다)
    ⑧ 실배선: `make_completion_gate` + 임시 잠금 루트 + 임시 리뷰 큐
         추적 밖 → 통과 · 추적+리뷰 없음 → 막힘 · 추적+HIGH open → 막힘
         추적+리뷰 스킵 완료 → PUT 뒤 **실제 잠금 해제** · 깨진 잠금 파일 → 막힘(경로를 말한다)
         루트 해석 실패 → 막힘

[중요] 실 Redmine·실 트윈을 두드리지 않는다 — `sender` 와 임시 루트만 쓴다.

    .venv/bin/python master/test_redmine_completion_gate.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import issue_lock as IL                               # noqa: E402
from master import redmine as RM                                  # noqa: E402
from master.context_synth import review_queue as RQ               # noqa: E402
from master.test_redmine import Sender                            # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Gate:
    def __init__(self, decision=None, boom=None, release=None):
        self.calls: list = []
        self.decision = decision
        self.boom = boom
        self.release_result = release
        self.released: list = []

    def __call__(self, issue_id):
        self.calls.append(issue_id)
        if self.boom is not None:
            raise self.boom
        d = dict(self.decision)
        if self.release_result is not None:
            def rel():
                self.released.append(issue_id)
                if isinstance(self.release_result, Exception):
                    raise self.release_result
                return self.release_result
            d["release"] = rel
        return d


class ClosedSender(Sender):
    """상태 목록에 `is_closed` 를 싣는다 — 「거절」도 닫힌 상태인 Redmine."""

    def __call__(self, method, url, payload=None):
        if url.endswith("/issue_statuses.json"):
            self.calls.append((method, url, payload))
            return {"issue_statuses": [{"id": 3, "name": "해결", "is_closed": False},
                                       {"id": 4, "name": "완료", "is_closed": True},
                                       {"id": 6, "name": "거절", "is_closed": True}]}
        return super().__call__(method, url, payload)


def test_not_applicable_puts():
    s, g = Sender(), Gate({"apply": False, "ok": True, "why": "추적 밖"})
    out = RM.update_issue(7, notes="닫음", status_name="완료", done_ratio=100, sender=s,
                          completion_gate=g)
    check("① 관문을 한 번 부른다", g.calls == [7], str(g.calls))
    check("① PUT 진행", len(s.puts) == 1 and s.puts[0][1]["issue"].get("status_id") == 5, str(s.puts))
    check("① 성공 문장 · 잠금 언급 없음", out.startswith("레드마인 #7 갱신") and "잠금" not in out, out)


def test_refused_no_put():
    s = Sender()
    g = Gate({"apply": True, "ok": False, "why": "#7 범위 리뷰 R12 에 결정되지 않은 HIGH 지적 1건: R12-3"},
             release={"ok": True})
    out = RM.update_issue(7, notes="닫음", status_name="완료", done_ratio=100, sender=s,
                          completion_gate=g)
    check("② PUT 0회", not s.puts, str(s.calls))
    check("② [주의] 완료 거절 + 사유", out.startswith("[주의] 레드마인 #7 완료 거절 — ")
          and "R12-3" in out, out)
    check("② 아무것도 쓰지 않았다고 말한다", "PUT 안 함" in out and "노트" in out, out)
    check("② 해제를 부르지 않는다", not g.released, str(g.released))


def test_passed_releases():
    s, g = Sender(), Gate({"apply": True, "ok": True, "why": "통과"}, release={"ok": True, "was": "active"})
    out = RM.update_issue(7, notes="닫음", status_name="완료", sender=s, completion_gate=g)
    check("③ PUT 1회", len(s.puts) == 1, str(s.calls))
    check("③ PUT 뒤 해제", g.released == [7], str(g.released))
    check("③ 결과에 잠금 해제", out.startswith("레드마인 #7 갱신") and out.endswith(" · 잠금 해제"), out)

    s, g = Sender(), Gate({"apply": True, "ok": True, "why": "통과"},
                          release={"ok": False, "why": "#7 는 활성·보류 어디에도 없다"})
    out = RM.update_issue(7, status_name="완료", sender=s, completion_gate=g)
    check("③ 해제 실패는 거절이 아니다(갱신 문장 유지)", out.startswith("레드마인 #7 갱신"), out)
    check("③ 해제 실패를 [주의] 로 표시", "[주의] 잠금 해제 실패" in out and "이미 반영" in out, out)

    s, g = Sender(), Gate({"apply": True, "ok": True, "why": "통과"}, release=OSError("디스크"))
    out = RM.update_issue(7, status_name="완료", sender=s, completion_gate=g)
    check("③ 해제 예외도 표시만", len(s.puts) == 1 and "[주의] 잠금 해제 실패 — OSError" in out, out)

    s, g = Sender(), Gate({"apply": True, "ok": True, "why": "통과"})
    out = RM.update_issue(7, status_name="완료", sender=s, completion_gate=g)
    check("③ 해제 수단이 없으면 생략을 말한다", "잠금 해제 생략" in out, out)


def test_put_failure_does_not_release():
    s = Sender(boom=None)
    g = Gate({"apply": True, "ok": True, "why": "통과"}, release={"ok": True})

    class PutBoom(Sender):
        def __call__(self, method, url, payload=None):
            if method == "PUT":
                self.calls.append((method, url, payload))
                raise OSError("연결 끊김")
            return super().__call__(method, url, payload)

    s = PutBoom()
    out = RM.update_issue(7, status_name="완료", sender=s, completion_gate=g)
    check("③ PUT 실패면 해제하지 않는다", out.startswith("[주의]") and not g.released, out)

    class Unapplied(Sender):
        def __call__(self, method, url, payload=None):
            if method == "GET" and "/issues/7.json?" in url:
                self.calls.append((method, url, payload))
                return {"issue": {"id": 7, "status": {"id": 2}}}
            return super().__call__(method, url, payload)

    g = Gate({"apply": True, "ok": True, "why": "통과"}, release={"ok": True})
    out = RM.update_issue(7, status_name="완료", sender=Unapplied(), completion_gate=g)
    check("③ 상태 미반영이면 해제하지 않는다", out.startswith("[주의]") and not g.released, out)


def test_gate_errors_fail_closed():
    for boom in (IL.IssueLockError("깨졌다"), RuntimeError("뭔가")):
        s = Sender()
        out = RM.update_issue(7, notes="x", status_name="완료", sender=s,
                              completion_gate=Gate(boom=boom))
        check(f"④ 관문 예외 {type(boom).__name__} → 막음", out.startswith("[주의] 레드마인 #7 완료 거절")
              and type(boom).__name__ in out, out)
        check(f"④ 관문 예외 {type(boom).__name__} → PUT 0회", not s.puts, str(s.calls))
    s = Sender()
    out = RM.update_issue(7, status_name="완료", sender=s, completion_gate=lambda n: "ok")
    check("④ 반환 형식 오류 → 막음", out.startswith("[주의] 레드마인 #7 완료 거절") and not s.puts, out)


def test_non_closing_untouched():
    g = Gate(boom=AssertionError("부르면 안 된다"))
    s = Sender()
    out = RM.update_issue(7, notes="완료", status_name="해결", done_ratio=100, sender=s, completion_gate=g)
    check("⑤ 「해결」 은 관문 밖", not g.calls and len(s.puts) == 1 and not out.startswith("[주의]"), out)
    s = Sender()
    out = RM.update_issue(7, notes="코멘트", sender=s, completion_gate=g)
    check("⑤ 노트만은 관문 밖", not g.calls and len(s.puts) == 1, out)
    check("⑤ 노트만 문장 종전과 같다", out == "레드마인 #7 갱신 (notes)", out)
    s = Sender()
    out = RM.update_issue(7, done_ratio=100, sender=s, completion_gate=g)
    check("⑤ 완료율만도 관문 밖", not g.calls and len(s.puts) == 1, out)


def test_closed_detection():
    g = Gate({"apply": True, "ok": False, "why": "막음"})
    s = ClosedSender()
    out = RM.update_issue(7, status_name="거절", sender=s, completion_gate=g)
    check("⑥ is_closed 상태는 이름이 달라도 닫기", g.calls == [7] and not s.puts, out)
    g = Gate(boom=AssertionError("부르면 안 된다"))
    s = ClosedSender()
    RM.update_issue(7, status_name="해결", sender=s, completion_gate=g)
    check("⑥ is_closed=False 는 관문 밖", not g.calls and len(s.puts) == 1, str(s.calls))
    # 상태 조회 실패 → status_id 를 싣지 않으므로 닫히지 않는다 → 관문도 필요 없다
    s = Sender(statuses=("신규", "진행"))
    out = RM.update_issue(7, notes="x", status_name="완료", sender=s, completion_gate=g)
    check("⑥ 「완료」 를 못 찾으면 닫기가 아니다(노트만 · 건너뜀을 말한다)",
          not g.calls and len(s.puts) == 1 and "건너뜀" in out, out)


def test_injected_sender_without_gate():
    s = Sender()
    orig = RM.make_completion_gate
    RM.make_completion_gate = lambda **kw: (_ for _ in ()).throw(AssertionError("실 관문 생성"))
    try:
        out = RM.update_issue(7, status_name="완료", sender=s)
    finally:
        RM.make_completion_gate = orig
    check("⑦ sender 주입 + 관문 미지정 → 관문 없음", len(s.puts) == 1 and "잠금" not in out, out)


# ── ⑧ 실배선 ──────────────────────────────────────────────────────────────

def _roots():
    root = Path(tempfile.mkdtemp(prefix="rm-gate-"))
    return root


def _real_gate(root, logs):
    return RM.make_completion_gate(root_fn=lambda: root, logf=logs.append)


def test_real_gate_wiring():
    logs: list = []
    root = _roots()
    gate = _real_gate(root, logs)

    s = Sender()
    out = RM.update_issue(901, status_name="완료", sender=s, completion_gate=gate)
    check("⑧ 추적 밖 → PUT", len(s.puts) == 1 and "잠금" not in out, out)
    check("⑧ 추적 밖 로그", any("추적 밖" in m for m in logs), str(logs))

    IL.acquire(root, 883, branch="issue/883", start_rev="a" * 40)
    s = Sender()
    out = RM.update_issue(883, notes="닫음", status_name="완료", sender=s, completion_gate=gate)
    check("⑧ 추적 + 리뷰 없음 → 막음", out.startswith("[주의] 레드마인 #883 완료 거절")
          and "범위 리뷰가 큐에 없다" in out and not s.puts, out)
    check("⑧ 막혀도 잠금은 그대로", IL.is_tracked(root, 883))

    b, e = "1" * 40, "2" * 40
    it = RQ.enqueue(root, kind="range", key=f"{b}..{e}",
                    meta={"issue_id": 883, "base": b, "end": e}, requester="issue_flow#883")
    s = Sender()
    out = RM.update_issue(883, status_name="완료", sender=s, completion_gate=gate)
    check("⑧ 리뷰 pending → 막음", "아직 끝나지 않았다" in out and not s.puts, out)

    # HIGH open 리뷰 파일
    d = root / "reviews" / "_range"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"2026-11-04_1000_issue883_{b[:8]}-{e[:8]}.md").write_text(
        f"# 일감 범위 리뷰 — #883\n\n- 범위: `{b}..{e}`\n- 일감: #883\n- 작성자: Antigravity\n"
        "- 파일: 1개\n- 생성: 2026-11-04 10:00\n\n### m\n\n## 1. 변경분 코딩 컨벤션\n"
        "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n\n"
        "## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
        "|---|---|---|---|---|\n| m/x.py | high | 9 | 위험 | 고친다 |\n", encoding="utf-8")
    RQ.claim(root)
    RQ.finish(root, it["id"], ok=True, note="ok")
    s = Sender()
    out = RM.update_issue(883, status_name="완료", sender=s, completion_gate=gate)
    check("⑧ HIGH open → 막음", "HIGH 지적 1건" in out and not s.puts, out)
    check("⑧ 여전히 추적", IL.is_tracked(root, 883))


def test_real_gate_skip_releases():
    logs: list = []
    root = _roots()
    gate = _real_gate(root, logs)
    IL.acquire(root, 884, branch="issue/884", start_rev="a" * 40)
    IL.pause(root, 884)
    b, e = "3" * 40, "4" * 40
    it = RQ.enqueue(root, kind="range", key=f"{b}..{e}",
                    meta={"issue_id": 884, "base": b, "end": e}, requester="issue_flow#884")
    RQ.claim(root)
    RQ.finish(root, it["id"], ok=True, note="스킵 — 변경 파일 없음")
    s = Sender()
    out = RM.update_issue(884, notes="닫음", status_name="완료", done_ratio=100, sender=s,
                          completion_gate=gate)
    check("⑧ 스킵 완료(보류 중) → PUT", len(s.puts) == 1, out)
    check("⑧ 결과에 잠금 해제", out.endswith(" · 잠금 해제"), out)
    check("⑧ 실제로 잠금이 풀렸다", not IL.is_tracked(root, 884))
    hist = IL._load(root)["history"]
    check("⑧ 이력에 complete · by=redmine.update_issue",
          hist[-1]["op"] == "complete" and hist[-1]["by"] == "redmine.update_issue", str(hist[-1]))
    check("⑧ 해제 로그", any("[issue_lock] #884 complete" in m for m in logs), str(logs))


def test_real_gate_broken_lock_and_root():
    root = _roots()
    IL.state_path(root).write_text("{깨짐", encoding="utf-8")
    s = Sender()
    out = RM.update_issue(885, status_name="완료", sender=s,
                          completion_gate=_real_gate(root, []))
    check("⑧ 깨진 잠금 파일 → 막음", out.startswith("[주의] 레드마인 #885 완료 거절") and not s.puts, out)
    check("⑧ 복구 경로(잠금 파일)를 말한다", str(IL.state_path(root)) in out and "복구" in out, out)
    check("⑧ 깨진 파일을 덮어쓰지 않았다", IL.state_path(root).read_text(encoding="utf-8") == "{깨짐")

    def no_root():
        raise KeyError("AXCluster")
    s = Sender()
    out = RM.update_issue(885, status_name="완료", sender=s,
                          completion_gate=RM.make_completion_gate(root_fn=no_root, logf=lambda m: None))
    check("⑧ 루트 해석 실패 → 막음", out.startswith("[주의] 레드마인 #885 완료 거절")
          and "KeyError" in out and not s.puts, out)


def test_server_warn_field():
    """`#883` T5 — 8101 `/redmine/note` 는 반영 뒤 경고(잠금 해제 실패 등)를 `warn` 으로 따로 말한다.

    앱이 `_run_http_server` 안에서 만들어지므로 `test_work_mode_patch` 와 같이 소스로 확인한다.
    """
    import inspect
    from master.task_queue.server import _run_http_server
    src = inspect.getsource(_run_http_server)
    check("⑨ 8101 redmine/note — ok 는 [주의] 시작 여부", 'ok = not result.startswith("[주의]")' in src)
    check("⑨ 8101 redmine/note — warn 은 반영 뒤 문장 안 [주의]",
          '"warn": ok and "[주의]" in result' in src)


def main() -> int:
    for fn in (test_not_applicable_puts, test_refused_no_put, test_passed_releases,
               test_put_failure_does_not_release, test_gate_errors_fail_closed,
               test_non_closing_untouched, test_closed_detection,
               test_injected_sender_without_gate, test_real_gate_wiring,
               test_real_gate_skip_releases, test_real_gate_broken_lock_and_root,
               test_server_warn_field):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_redmine_completion_gate: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
