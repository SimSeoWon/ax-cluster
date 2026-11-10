"""일감 흐름의 인프라 쪽(`#884` T6) — `.33` 요청자가 8101 로 부르는 `infra_*` 계약 테스트.

[중요] 대부분은 git 이 없다 — 요청자가 보낸 값(브랜치·리비전·해시)만으로 플랜·잠금·마감 추적·노트가 마스터 로컬
흐름과 같은 규칙으로 도는가. `t_verify`(`#933`)만 **임시 git 저장소**를 실제로 만들어 마감 범위 검증을 본다. 잠금·추적은 **임시 트윈 루트**(lock_root)에, Redmine 은 대역(getter/noter)이다.
실 Redmine·실 트윈을 두드리지 않는다.

    .venv/bin/python master/test_issue_infra.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import issue_infra as INF                  # noqa: E402
from master import issue_lock as IL                    # noqa: E402
from master.context_synth import issue_track as IT     # noqa: E402
from master.test_issue_flow import Issue, PLAN, SPEC   # noqa: E402

PASS = FAIL = 0
P = "Game"
R1, R2, R3, R4 = "1" * 40, "2" * 40, "3" * 40, "4" * 40


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def run(fn):
    with tempfile.TemporaryDirectory() as d:
        fn(Path(d))


def t_project_and_input(tmp):
    iss = Issue(SPEC + PLAN)
    r = INF.infra_start("", 7, check_only=True, getter=iss.get, noter=iss.note, lock_root=tmp)
    check("프로젝트 없음 → 거절(project)", not r["ok"] and r["step"] == "project", str(r)[:200])
    r = INF.infra_start(P, "x", getter=iss.get, noter=iss.note, lock_root=tmp)
    check("일감 번호 아님 → 거절(input)", not r["ok"] and r["step"] == "input", str(r)[:200])
    r = INF.infra_pause(P, 7, noter=iss.note)
    check("pause — 대역에 lock_root 없음 → 거절(운영 잠금 안 건드림)", not r["ok"] and r["step"] == "lock", str(r)[:200])
    check("거절은 노트 0", iss.notes == [])


def t_start(tmp):
    lk = tmp / "twin"
    ev = tmp / "ev.jsonl"
    iss = Issue(SPEC)                                   # 플랜 없음
    r = INF.infra_start(P, 7, check_only=True, getter=iss.get, noter=iss.note, lock_root=lk)
    check("플랜 없음 → 거절(plan) · 노트 0", not r["ok"] and r["step"] == "plan" and not iss.notes, str(r)[:200])

    iss = Issue(SPEC + PLAN)
    r = INF.infra_start(P, 7, check_only=True, getter=iss.get, noter=iss.note, lock_root=lk, events_path=ev)
    check("check_only → ok · 판정 next · 잠금 free · 쓰기 0", r["ok"] and r["check_only"] and r["verdict"] == "next"
          and r["lock_state"] == "free" and not iss.notes and IL.current(lk) is None, str(r)[:300])
    r = INF.infra_start(P, 7, branch="issue/8", start_rev=R1, getter=iss.get, noter=iss.note, lock_root=lk)
    check("브랜치 이름 어긋남 → 거절(branch)", not r["ok"] and r["step"] == "branch" and not iss.notes, str(r)[:200])
    r = INF.infra_start(P, 7, branch="issue/7", start_rev="abc", getter=iss.get, noter=iss.note, lock_root=lk)
    check("start_rev 40자리 아님 → 거절(rev) · 잠금 없음", not r["ok"] and r["step"] == "rev"
          and IL.current(lk) is None and not iss.notes, str(r)[:200])
    r = INF.infra_start(P, 7, branch="issue/7", start_rev=R1.upper().replace("1", "A"), getter=iss.get,
                        noter=iss.note, lock_root=lk, events_path=ev)
    check("시작 → ok · 잠금 acquired · 노트에 리비전 · 신규→진행",
          r["ok"] and r["lock"] == "acquired" and (IL.current(lk) or {}).get("issue_id") == 7
          and "a" * 40 in iss.notes[-1][0] and iss.notes[-1][1] == "진행", str(r)[:300])
    check("잠금 기록의 브랜치·리비전", (IL.current(lk) or {}).get("branch") == "issue/7"
          and (IL.current(lk) or {}).get("start_rev") == "a" * 40, str(IL.current(lk)))
    steps = [json.loads(x)["step"] for x in ev.read_text().splitlines()]
    check("단계 로그(jsonl)", steps[-4:] == ["plan", "lock", "redmine", "lock"] and "check" in steps, str(steps))
    n0 = len(iss.notes)
    r = INF.infra_start(P, 7, branch="issue/7", start_rev=R2, getter=iss.get, noter=iss.note, lock_root=lk)
    check("재호출(같은 N 활성) → already · 노트 추가 없음 · 리비전 다름 경고",
          r["ok"] and r["already"] and len(iss.notes) == n0 and r["start_rev"] == "a" * 40
          and "warning" in r, str(r)[:300])

    other = Issue(SPEC + PLAN)
    r = INF.infra_start(P, 8, check_only=True, getter=other.get, noter=other.note, lock_root=lk)
    check("다른 일감 활성 → check_only 도 거절(lock · holder)", not r["ok"] and r["step"] == "lock"
          and r.get("holder") == 7 and "#7 작업이 진행 중이다" in r["why"], str(r)[:300])
    check("거절 응답에 project", r.get("project") == P)

    fail = Issue(SPEC + PLAN, answer="[주의] 레드마인 실패")
    IL.release(lk, 7, op="cancel")
    r = INF.infra_start(P, 9, branch="issue/9", start_rev=R3, getter=fail.get, noter=fail.note, lock_root=lk)
    check("노트 실패 → 거절(redmine) · 잠금 안 잡음", not r["ok"] and r["step"] == "redmine"
          and IL.current(lk) is None, str(r)[:300])


def t_pause_resume(tmp):
    lk = tmp / "twin"
    iss = Issue(SPEC + PLAN)
    INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=iss.get, noter=iss.note, lock_root=lk)
    r = INF.infra_pause(P, 7, end="zz", noter=iss.note, lock_root=lk)
    check("보류 end 형식 오류 → 거절(rev) · 잠금 그대로", not r["ok"] and r["step"] == "rev"
          and (IL.current(lk) or {}).get("issue_id") == 7, str(r)[:200])
    r = INF.infra_pause(P, 7, end=R2, noter=iss.note, lock_root=lk)
    check("보류 → ok · 잠금 비고 보류 · 노트", r["ok"] and IL.current(lk) is None and 7 in IL.paused(lk)
          and "보류" in iss.notes[-1][0] and R2 in iss.notes[-1][0], str(r)[:300])
    r = INF.infra_pause(P, 7, noter=iss.note, lock_root=lk)
    check("보류 중 다시 보류 → 거절(lock)", not r["ok"] and r["step"] == "lock", str(r)[:200])

    r = INF.infra_finish(P, 7, base=R1, end=R2, hashes=[R2], noter=iss.note, lock_root=lk)
    check("보류 중 finish → 거절(lock)", not r["ok"] and r["step"] == "lock" and "보류" in r["why"], str(r)[:200])

    r = INF.infra_start(P, 7, check_only=True, getter=iss.get, noter=iss.note, lock_root=lk)
    check("check_only — lock_state paused · 보류 기록", r["ok"] and r["lock_state"] == "paused"
          and r["paused"]["start_rev"] == R1, str(r)[:300])
    fail = Issue(SPEC + PLAN, answer="[주의] 실패")
    r = INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=fail.get, noter=fail.note, lock_root=lk)
    check("재개 노트 실패 → 다시 보류(relocked)", not r["ok"] and r["step"] == "redmine" and r["relocked"]
          and IL.current(lk) is None and 7 in IL.paused(lk), str(r)[:300])
    r = INF.infra_start(P, 7, branch="issue/7", start_rev=R3, getter=iss.get, noter=iss.note, lock_root=lk)
    check("재개 → resumed · 잠금 기록 리비전 유지 · 재개 노트", r["ok"] and r["resumed"] and r["start_rev"] == R1
          and (IL.current(lk) or {}).get("issue_id") == 7 and "재개" in iss.notes[-1][0], str(r)[:300])


def t_finish(tmp):
    lk = tmp / "twin"
    iss = Issue(SPEC + PLAN)
    INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=iss.get, noter=iss.note, lock_root=lk)
    bad = [
        ("base 형식", dict(base="x", end=R3, hashes=[R2, R3])),
        ("해시 없음", dict(base=R1, end=R3, hashes=[])),
        ("해시 형식", dict(base=R1, end=R3, hashes=["zz", R3])),
        ("마지막 ≠ end", dict(base=R1, end=R3, hashes=[R3, R2])),
        ("base 가 목록 안", dict(base=R1, end=R3, hashes=[R1, R3])),
        ("subjects 수 다름", dict(base=R1, end=R3, hashes=[R2, R3], subjects=["a"])),
    ]
    n0 = len(iss.notes)
    for label, kw in bad:
        r = INF.infra_finish(P, 7, noter=iss.note, lock_root=lk, **kw)
        check(f"finish {label} → 거절(span)", not r["ok"] and r["step"] == "span", str(r)[:200])
    check("span 거절은 노트·추적·잠금 변화 0", len(iss.notes) == n0 and not IT.state_path(lk).exists()
          and (IL.current(lk) or {}).get("issue_id") == 7)

    def reg_fail(root, n, **kw):
        return {"ok": False, "reason": "bad_sha", "why": "대역 거절"}
    r = INF.infra_finish(P, 7, base=R1, end=R3, hashes=[R2, R3], noter=iss.note, register=reg_fail, lock_root=lk)
    check("등록 실패 → ok False · 잠금 유지 · 노트에 실패·유지", not r["ok"] and not r["registered"]
          and (IL.current(lk) or {}).get("issue_id") == 7 and "등록 실패" in iss.notes[-1][0]
          and "유지" in iss.notes[-1][0], str(r)[:300])
    check("#889 등록 실패 → 닫지 않는다(노트만 · 열어 둔다)", iss.notes[-1][1] == "" and r.get("closed") is False
          and "일감 상태: 열어 둔다" in iss.notes[-1][0], str((iss.notes[-1][1], r.get("closed"))))

    r = INF.infra_finish(P, 7, base=R1.upper(), end=R3, hashes=[R2, R3], subjects=["첫 커밋", "둘째\n본문"],
                         noter=iss.note, lock_root=lk)
    note = iss.notes[-1][0]
    check("finish → ok · 등록 · 잠금 해제", r["ok"] and r["registered"] and r["round"] == 1 and r["lock_released"]
          and IL.current(lk) is None and not IL.is_tracked(lk, 7), str(r)[:400])
    rnd = IT.current(lk, 7) or {}
    check("마감 추적 — 프로젝트·범위·해시 순서", rnd.get("project") == P and rnd.get("base") == R1
          and rnd.get("end") == R3 and [h["sha"] for h in rnd.get("hashes", [])] == [R2, R3], str(rnd)[:300])
    check("노트 — 로컬 finish 와 같은 틀(리뷰 요청·범위·커밋 제목·추적·잠금)",
          note.startswith(f"리뷰 요청: `{R1}..{R3}` (커밋 2건)") and "첫 커밋" in note and "둘째" in note
          and "본문" not in note and "마감 추적: 라운드 1 에 해시 2개 등록" in note
          and "일감 잠금: 해제(finish)" in note and INF.REMOTE_DELETED in note, note)
    check("done 순서", r["done"] == ["register", "link", "release", "close", "redmine"], str(r["done"]))
    check("#889 등록 성공 → 「완료」·100 · closed", iss.notes[-1][1] == "완료" and iss.ratios[-1] == 100
          and r.get("closed") is True and "일감 상태: 「완료」·100" in note, str((iss.notes[-1][1], r.get("closed"))))

    class Refuse(Issue):
        def note(self, iid, *, notes, status_name="", done_ratio=None):
            super().note(iid, notes=notes, status_name=status_name, done_ratio=done_ratio)
            return "[주의] 레드마인 #7 완료 거절 — 대역" if status_name else "레드마인 #7 갱신 (notes)"
    rf = Refuse(SPEC + PLAN)
    lk2 = tmp / "twin2"
    INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=rf.get, noter=rf.note, lock_root=lk2)
    r = INF.infra_finish(P, 7, base=R1, end=R3, hashes=[R2, R3], noter=rf.note, lock_root=lk2)
    check("#889 닫기 거절 → 노트만 다시 · problems · closed False", not r["ok"] and r.get("closed") is False
          and len(rf.notes) >= 2 and rf.notes[-1][1] == "" and "닫기 실패" in rf.notes[-1][0]
          and "Redmine 닫기" in r["why"] and "redmine" in r["done"], str(r)[:400])
    r = INF.infra_finish(P, 7, base=R1, end=R3, hashes=[R2, R3], noter=iss.note, lock_root=lk)
    check("같은 범위 재호출 → already · 잠금 기록 없음 경고로 진행", r["registered"]
          and "이미 등록" in " ".join(r["log"]) and any("잠금 기록 없음" in x for x in r["log"]), str(r)[:300])

    other = Issue(SPEC + PLAN)
    INF.infra_start(P, 8, branch="issue/8", start_rev=R1, getter=other.get, noter=other.note, lock_root=lk)
    r = INF.infra_finish(P, 7, base=R1, end=R3, hashes=[R2, R3], noter=iss.note, lock_root=lk)
    check("다른 일감 활성 중 finish → 거절(lock · holder)", not r["ok"] and r["step"] == "lock"
          and r.get("holder") == 8, str(r)[:200])


def _mkrepo(root: Path):
    """임시 저장소 — main 에 c1·c2·c3, main 밖 가지에 side. `(git 실행기, c1, c2, c3, side)`."""
    root.mkdir(parents=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "PATH": __import__("os").environ.get("PATH", "")}

    def g(*a):
        return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, env=env,
                              check=True).stdout.strip()
    g("init", "-q", "-b", "main")
    out = []
    for name in ("첫 커밋", "둘째 커밋", "셋째 커밋"):
        (root / "f.txt").write_text(name, encoding="utf-8")
        g("add", "f.txt")
        g("commit", "-q", "-m", name)
        out.append(g("rev-parse", "HEAD"))
    g("checkout", "-q", "-b", "side", out[0])
    (root / "s.txt").write_text("side", encoding="utf-8")
    g("add", "s.txt")
    g("commit", "-q", "-m", "가지 커밋")
    side = g("rev-parse", "HEAD")
    g("checkout", "-q", "main")
    gd = root / ".git"
    return (lambda *a: INF._run_git(gd, *a)), out[0], out[1], out[2], side


def t_verify(tmp):
    """`#933` — 마감 범위를 git 에서 확인·도출한다. 실제 임시 저장소."""
    git, c1, c2, c3, side = _mkrepo(tmp / "repo")
    got = INF.verify_span(git, base=c1, end=c3)
    check("verify_span — 해시·제목을 git 에서 구한다(오래된 것부터)", got["hashes"] == [c2, c3]
          and got["subjects"] == ["둘째 커밋", "셋째 커밋"], str(got))
    check("verify_span — 보고 해시가 같으면 통과", INF.verify_span(git, base=c1, end=c3, hashes=[c2, c3])["hashes"] == [c2, c3])

    def kind(**kw):
        try:
            INF.verify_span(kw.pop("g", git), **kw)
        except INF.SpanError as x:
            return x.kind, x.why
        return "", ""
    fake = c3[:7] + "f5ad081c7847c50a2718104d41fa9a5e8"        # `#929` — 앞 7자만 실제인 해시
    k, why = kind(base=c1, end=fake)
    check("🔴 #929 재현 — 앞 7자만 같은 없는 해시 → mismatch", k == "mismatch" and "없는 커밋" in why, why)
    check("없는 base → mismatch", kind(base=R1, end=c3)[0] == "mismatch")
    check("보고 해시 목록이 다르다 → mismatch", kind(base=c1, end=c3, hashes=[c3])[0] == "mismatch")
    check("보고 해시 순서가 다르다 → mismatch", kind(base=c1, end=c3, hashes=[c3, c2])[0] == "mismatch")
    check("base 가 end 의 조상이 아니다 → mismatch", kind(base=c3, end=c1)[0] == "mismatch")
    k, why = kind(base=c1, end=side)
    check("end 가 main 밖 → mismatch(push 전)", k == "mismatch" and "도달 가능하지 않다" in why, why)
    check("base == end → mismatch(마칠 것 없음)", kind(base=c3, end=c3)[0] == "mismatch")
    nogit = lambda *a: INF._run_git(tmp / "없는저장소", *a)                     # noqa: E731
    check("저장소를 못 읽는다 → lookup", kind(g=nogit, base=c1, end=c3)[0] == "lookup")

    lk = tmp / "twin"
    iss = Issue(SPEC + PLAN)
    INF.infra_start(P, 7, branch="issue/7", start_rev=c1, getter=iss.get, noter=iss.note, lock_root=lk)
    n0 = len(iss.notes)
    for label, kw, vk in (
            ("없는 end", dict(base=c1, end=fake, hashes=[fake]), "mismatch"),
            ("해시 목록 불일치", dict(base=c1, end=c3, hashes=[c3]), "mismatch"),
            ("main 밖 end", dict(base=c1, end=side), "mismatch"),
            ("조회 실패", dict(base=c1, end=c3, git=nogit), "lookup")):
        r = INF.infra_finish(P, 7, noter=iss.note, lock_root=lk, **{"git": git, **kw})
        check(f"finish {label} → 거절(verify · {vk})", not r["ok"] and r["step"] == "verify"
              and r.get("verify") == vk, str(r)[:300])
    check("🔴 verify 거절은 노트·추적·잠금 변화 0", len(iss.notes) == n0 and not IT.state_path(lk).exists()
          and (IL.current(lk) or {}).get("issue_id") == 7)
    r = INF.infra_finish(P, 7, base=c1, end=c3, git=nogit, noter=iss.note, lock_root=lk)
    check("조회 실패 사유에 「등록하지 않는다」", "등록하지 않는다" in r.get("why", ""), r.get("why", ""))

    r = INF.infra_finish(P, 7, end=c3, check_only=True, git=git, noter=iss.note, lock_root=lk)
    check("check_only · base 생략 → 잠금의 시작 리비전 · git 도출 · 쓰기 0", r["ok"] and r["check_only"]
          and r["base"] == c1 and [c[:40] for c in r["commits"]] == [c2, c3] and r["verified"]
          and len(iss.notes) == n0 and not IT.state_path(lk).exists()
          and (IL.current(lk) or {}).get("issue_id") == 7, str(r)[:400])
    r = INF.infra_finish(P, 7, end=c3, git=git, noter=iss.note, lock_root=lk)
    note = iss.notes[-1][0]
    rnd = IT.current(lk, 7) or {}
    check("end 만으로 마감 → 등록 · 해시는 git 것", r["ok"] and r["registered"] and r["base"] == c1
          and [h["sha"] for h in rnd.get("hashes", [])] == [c2, c3] and IL.current(lk) is None, str(r)[:400])
    check("노트의 커밋 제목은 git 것", "둘째 커밋" in note and "셋째 커밋" in note
          and note.startswith(f"리뷰 요청: `{c1}..{c3}` (커밋 2건)"), note)
    check("로그 — 검증 대상·결과가 남는다", any("verify" in x and "git 에서 확인한다" in x for x in r["log"])
          and any("verify" in x and "git 에서 구함" in x for x in r["log"]), str(r["log"]))

    lk2 = tmp / "twin2"
    r = INF.infra_finish(P, 9, end=c3, git=git, noter=iss.note, lock_root=lk2)
    check("base 생략인데 잠금이 없다 → 거절(span)", not r["ok"] and r["step"] == "span"
          and "시작 리비전이 없다" in r["why"], str(r)[:300])
    r = INF.infra_finish(P, 9, base=c1, end=c3, check_only=True, git=git, noter=iss.note, lock_root=lk2)
    check("check_only · 잠금 없음 · base 명시 → 도출만", r["ok"] and r["check_only"] and not r["lock_held"]
          and [c[:40] for c in r["commits"]] == [c2, c3] and not IT.state_path(lk2).exists(), str(r)[:300])
    r = INF.infra_finish(P, 7, base=R1, end=R3, hashes=[R2, R3], noter=iss.note, lock_root=tmp / "twin3")
    check("대역 주입 + git 없음 → 검증 건너뜀을 로그에 남긴다",
          any("git 검증 미사용" in x for x in r["log"]), str(r["log"]))


def t_span_source():
    """운영 경로의 저장소 해석 — 못 풀면 lookup 으로 거절(fail-closed)."""
    try:
        INF.span_source("등록되지-않은-프로젝트-933")
        ok = False
    except INF.SpanError as x:
        ok = x.kind == "lookup"
    check("span_source — 미등록 프로젝트 → SpanError(lookup)", ok)


def t_cancel(tmp):
    lk = tmp / "twin"
    iss = Issue(SPEC + PLAN)
    r = INF.infra_cancel(P, 7, branch_exists=False, noter=iss.note, lock_root=lk)
    check("잠금도 브랜치도 없음 → 거절", not r["ok"] and r["step"] == "lock", str(r)[:200])
    INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=iss.get, noter=iss.note, lock_root=lk)
    before = IL.state_path(lk).read_text()
    n0 = len(iss.notes)
    commits = [f"{R2} 하나", f"{R3} 둘"]
    r = INF.infra_cancel(P, 7, commits=commits, local_only=[R3], delete_branch=True, noter=iss.note, lock_root=lk)
    check("미리보기 → 쓰기 0 · 경고(원격 없음)", r["ok"] and not r["confirmed"] and r["lock_state"] == "active"
          and IL.state_path(lk).read_text() == before and len(iss.notes) == n0 and "되살릴 수 없다" in r["warning"],
          str(r)[:300])
    fail = Issue(SPEC + PLAN, answer="[주의] 실패")
    r = INF.infra_cancel(P, 7, confirm=True, commits=commits, local_only=[R3], delete_branch=True,
                         noter=fail.note, lock_root=lk)
    check("노트 실패 → branch_delete_allowed False · 잠금은 해제됨", not r["ok"] and r["step"] == "redmine"
          and r["branch_delete_allowed"] is False and IL.current(lk) is None, str(r)[:300])
    INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=iss.get, noter=iss.note, lock_root=lk)
    r = INF.infra_cancel(P, 7, confirm=True, commits=commits, local_only=[R3], delete_branch=True,
                         noter=iss.note, lock_root=lk)
    note = iss.notes[-1][0]
    check("승인 → 잠금 해제 · 노트(커밋·로컬에만·삭제) · 삭제 허용", r["ok"] and r["branch_delete_allowed"]
          and not IL.is_tracked(lk, 7) and "삭제(branch -D)" in note and "(로컬에만)" in note and "하나" in note,
          note)
    INF.infra_start(P, 7, branch="issue/7", start_rev=R1, getter=iss.get, noter=iss.note, lock_root=lk)
    r = INF.infra_cancel(P, 7, confirm=True, commits=commits, noter=iss.note, lock_root=lk)
    check("delete_branch 없음 → 유지 · 삭제 불허", r["ok"] and r["branch_delete_allowed"] is False
          and "유지" in iss.notes[-1][0], str(r)[:200])


def t_shared_with_local():
    """[중요] 로컬 흐름과 **같은 함수·같은 문장**이다 — 두 벌이 아니다."""
    from master import issue_flow as IF
    check("FINISH_NOTE 하나", IF.FINISH_NOTE is INF.FINISH_NOTE)
    check("START/PAUSE/RESUME/CANCEL 노트 하나", IF.START_NOTE is INF.START_NOTE and IF.PAUSE_NOTE is INF.PAUSE_NOTE
          and IF.RESUME_NOTE is INF.RESUME_NOTE and IF.CANCEL_NOTE is INF.CANCEL_NOTE)
    check("로그·거절·Redmine 호출 하나", IF._Log is INF.Log and IF._refuse is INF.refuse
          and IF._call_redmine is INF.call_redmine)
    import inspect
    src = inspect.getsource(IF)
    for fn in ("plan_gate", "lock_gate", "start_note", "resume_record", "finish_lock_check", "finish_record",
               "pause_lock", "pause_note", "cancel_state", "cancel_record"):
        check(f"issue_flow 가 INF.{fn} 를 부른다", f"INF.{fn}(" in src)
    for dup in ("IL.release(", "IL.acquire(lroot, n, branch=branch, start_rev=start_rev",
                "it.register(", "TRACK_OK.format("):
        check(f"issue_flow 에 기록 로직 사본이 없다: {dup}", dup not in src)


def t_imperative_free():
    """자동 경로 노트에 세션을 향한 명령형을 싣지 않는다(CLAUDE.md) — 「…하라·하세요·해라」."""
    texts = [INF.START_NOTE, INF.RESUME_NOTE, INF.PAUSE_NOTE, INF.CANCEL_NOTE, INF.FINISH_NOTE, INF.TRACK_OK,
             INF.TRACK_FAIL, INF.REMOTE_DELETED]
    for t in texts:
        check(f"명령형 없음: {t[:20]}", not any(x in t for x in ("하라", "하세요", "해라", "하십시오", "해 주세요")))


def main() -> int:
    for fn in (t_project_and_input, t_start, t_pause_resume, t_finish, t_verify, t_cancel):
        run(fn)
    t_span_source()
    t_shared_with_local()
    t_imperative_free()
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_infra: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
