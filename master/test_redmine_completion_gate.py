"""레드마인 「완료」 관문 (`#883` T4 → `#889`) — `update_issue` 가 닫기 전에 일감 잠금을 본다.

`#889` (사용자 결정 2026-11-06·11-07): 마감은 `issue_finish` 하나다 — finish 가 main 적용 때 닫고,
리뷰는 노트로만 붙는다. 관문은 **리뷰를 보지 않고** 「작업 중(잠금 활성·보류)인 일감을 손으로 닫기」만 막는다.

검증하는 것:

    ① 관문 해당 없음(apply=False) → PUT 진행 · 결과 문장 종전과 같다
    ② 관문이 막음 → PUT 0회(노트도 안 쓴다) · `[주의] … 완료 거절 — <why>`
    ③ 관문 통과 → PUT · **잠금 해제 꼬리 없음**(닫기는 잠금을 풀지 않는다)
    ④ 관문 예외·형식 오류 → 막음(fail-closed) · PUT 0회
    ⑤ 닫기가 아닌 상태(해결)·노트만 → 관문을 부르지 않는다
    ⑥ 이름이 달라도 `is_closed` 상태면 닫기로 본다 · 상태 조회 실패면 닫기가 아니다
    ⑦ sender 주입 + 관문 미지정 → 관문 없음(테스트가 실 트윈을 읽지 않는다)
    ⑧ 실배선: `make_completion_gate` + 임시 잠금 루트
         잠금 밖 → PUT · 활성 → 막음(finish 안내 · 잠금 그대로) · 보류 → 막음
         **finish 뒤(잠금 해제) → 리뷰가 안 끝났어도 PUT** · 깨진 잠금 파일 → 막음(경로) · 루트 실패 → 막음
    ⑪ (`#884` T6) 등록된 트윈 훑기 — 파일 있는 트윈만 · 빈 트윈에 파일을 안 만든다 ·
         잠금 트윈 → 막음(트윈 이름) · 어디에도 없음 → 관문 밖 · 어느 트윈이든 읽기 실패 → 막음 · 목록 실패 → 막음

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
from master.context_synth import issue_track as IT                # noqa: E402
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


def test_passed_no_release():
    s, g = Sender(), Gate({"apply": True, "ok": True, "why": "통과"}, release={"ok": True, "was": "active"})
    out = RM.update_issue(7, notes="닫음", status_name="완료", sender=s, completion_gate=g)
    check("③ PUT 1회", len(s.puts) == 1, str(s.calls))
    check("③ 닫기는 잠금을 풀지 않는다(관문이 해제 수단을 줘도)", not g.released, str(g.released))
    check("③ 결과 문장에 잠금 꼬리 없음", out.startswith("레드마인 #7 갱신") and "잠금" not in out, out)


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
    return Path(tempfile.mkdtemp(prefix="rm-gate-"))


def _real_gate(root, logs):
    return RM.make_completion_gate(root_fn=lambda: root, logf=logs.append)


def test_real_gate_wiring():
    logs: list = []
    root = _roots()
    gate = _real_gate(root, logs)

    s = Sender()
    out = RM.update_issue(901, status_name="완료", sender=s, completion_gate=gate)
    check("⑧ 잠금 밖 → PUT", len(s.puts) == 1 and "잠금" not in out, out)
    check("⑧ 잠금 밖 로그", any("잠금 밖" in m for m in logs), str(logs))

    IL.acquire(root, 883, branch="issue/883", start_rev="a" * 40)
    s = Sender()
    out = RM.update_issue(883, notes="닫음", status_name="완료", sender=s, completion_gate=gate)
    check("⑧ 활성 → 막음", out.startswith("[주의] 레드마인 #883 완료 거절")
          and "작업 중" in out and "활성" in out and not s.puts, out)
    check("⑧ 막는 사유가 finish·보류·취소를 안내한다",
          "issue_finish" in out and "issue_pause" in out and "issue_cancel" in out, out)
    check("⑧ 막혀도 잠금은 그대로", IL.is_tracked(root, 883))

    IL.pause(root, 883)
    s = Sender()
    out = RM.update_issue(883, status_name="완료", sender=s, completion_gate=gate)
    check("⑧ 보류 → 막음", out.startswith("[주의] 레드마인 #883 완료 거절") and "보류" in out
          and not s.puts, out)

    # finish 가 잠금을 풀었다 — 마감 추적 라운드의 해시가 아직 대기여도 닫힌다(리뷰는 안 본다)
    IL.acquire(root, 883, branch="issue/883", start_rev="a" * 40)
    IT.register(root, 883, project="AXCluster", base="1" * 40, end="2" * 40, hashes=["2" * 40])
    IL.release(root, 883, op="finish")
    s = Sender()
    out = RM.update_issue(883, notes="닫음", status_name="완료", done_ratio=100, sender=s,
                          completion_gate=gate)
    check("⑧ finish 뒤 · 리뷰 대기 중 → PUT(리뷰를 보지 않는다)", len(s.puts) == 1
          and out.startswith("레드마인 #883 갱신") and "잠금" not in out, out)
    hist = IL._load(root)["history"]
    check("⑧ 닫기가 잠금 이력을 더하지 않는다", hist[-1]["op"] == "finish", str(hist[-1]))


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

    root = _roots()
    IT.state_path(root).write_text("{깨짐", encoding="utf-8")
    s = Sender()
    out = RM.update_issue(886, status_name="완료", sender=s, completion_gate=_real_gate(root, []))
    check("⑧ 마감 추적 파일은 더 이상 보지 않는다(깨져도 닫힌다)", len(s.puts) == 1, out)


# ── ⑪ (`#884` T6) 여러 트윈 훑기 — Redmine 번호는 전역, 잠금은 트윈마다 ─────────────────

def _registry(names):
    from master.projects.config import Registry
    base = Path(tempfile.mkdtemp(prefix="rm-gate-reg-"))
    for n in names:
        (base / n).mkdir()
    (base / "projects.yaml").write_text(
        "version: 1\nactive: %s\nprojects:\n%s" % (names[0], "".join(f"- {n}\n" for n in names)),
        encoding="utf-8")
    return Registry.load(base), base


def test_scan_roots():
    reg, base = _registry(["AXCluster", "Game", "Empty"])
    IL.acquire(base / "AXCluster", 1, branch="issue/1", start_rev="a" * 40)
    IT.register(base / "Game", 5, project="Game", base="1" * 40, end="2" * 40, hashes=["2" * 40])
    got = RM.tracking_roots(registry=reg)
    check("⑪ tracking_roots — 잠금·추적 파일이 있는 트윈만", [n for n, _ in got] == ["AXCluster", "Game"], str(got))
    check("⑪ tracking_roots — 빈 트윈에 잠금 파일을 만들지 않는다",
          not any((base / "Empty").iterdir()), str(list((base / "Empty").iterdir())))

    logs: list = []
    gate = RM.make_completion_gate(roots_fn=lambda: RM.tracking_roots(registry=reg), logf=logs.append)
    d = gate(5)
    check("⑪ 마감 추적만 있는 트윈(Game) → 관문 밖", d.get("apply") is False and d.get("ok"), str(d))
    check("⑪ Game 쪽 훑기가 잠금 파일을 만들지 않았다", not (base / "Game" / "issue_lock.json").exists())
    d = gate(1)
    check("⑪ 잠금 트윈(AXCluster) → 막음 · 트윈 이름", d.get("apply") and not d.get("ok")
          and "AXCluster" in d.get("why", "") and "활성" in d["why"], str(d))
    check("⑪ 관문은 잠금을 풀지 않는다", IL.is_tracked(base / "AXCluster", 1) and "release" not in d, str(d))
    d = gate(77)
    check("⑪ 어디에도 없음 → 관문 밖", d.get("apply") is False and d.get("ok"), str(d))
    check("⑪ 관문 밖 로그에 트윈 수", any("트윈 2개" in m for m in logs), str(logs[-3:]))

    (base / "Game" / "issue_lock.json").write_text("{깨짐", encoding="utf-8")
    d = gate(77)
    check("⑪ 다른 트윈의 잠금 파일이 깨졌으면 막음(fail-closed)", d.get("apply") and not d.get("ok")
          and "Game" in d.get("why", "") and "issue_lock.json" in d["why"], str(d))

    def boom():
        raise RuntimeError("레지스트리 없음")
    d = RM.make_completion_gate(roots_fn=boom, logf=lambda m: None)(5)
    check("⑪ 트윈 목록 실패 → 막음", d.get("apply") and not d.get("ok")
          and "등록된 프로젝트 트윈 목록" in d.get("why", ""), str(d))

    s = Sender()
    out = RM.update_issue(5, status_name="완료", sender=s,
                          completion_gate=RM.make_completion_gate(roots_fn=boom, logf=lambda m: None))
    check("⑪ update_issue — 훑기 실패면 PUT 0", out.startswith("[주의]") and not s.puts, out)


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
    for fn in (test_not_applicable_puts, test_refused_no_put, test_passed_no_release,
               test_gate_errors_fail_closed,
               test_non_closing_untouched, test_closed_detection,
               test_injected_sender_without_gate, test_real_gate_wiring,
               test_real_gate_broken_lock_and_root,
               test_scan_roots, test_server_warn_field):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_redmine_completion_gate: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
