"""일감 마감 추적 ↔ 리뷰 큐 동기화 · 해시별 진행 노트 (`#884` T3).

검증하는 것:

    ① 큐 done → 해시 done · 노트에 R 번호와 지적 수(심각도별) · noted=True
    ② 큐 abandoned → 해시 abandoned · 노트에 「포기」와 사유
    ③ 한 번의 동기화에서 여러 해시가 끝나면 노트는 하나
    ④ noter 실패 → noted 그대로 · 다음 동기화가 다시 남긴다 · 성공 뒤 중복 없음
    ⑤ 워터마크가 지나간(조상) 큐 밖 해시 → skipped · 미러에 없는 해시는 waiting 유지
    ⑥ 추적 밖 큐 항목은 건드리지 않는다 · waiting + pending 은 우선순위 10 으로 연결
    ⑦ 깨진 추적 파일은 로그로 남고 예외가 올라오지 않는다
    ⑧ 🔴 noter 미주입 + 등록 안 된 루트 → 실 Redmine 호출 없음
    ⑨ main 이 drain 앞뒤로 동기화를 부른다

`.venv/bin/python master/test_issue_progress.py`
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import issue_progress as P              # noqa: E402
from master.context_synth import issue_track as T                 # noqa: E402
from master.context_synth import review_queue as Q                # noqa: E402
from master.context_synth import review_runner as R               # noqa: E402

PASS = FAIL = 0
N = 884
GHOST = "e" * 40          # 미러에 없는 해시


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _never(*_a, **_kw):
    raise AssertionError("실 Redmine noter 가 불렸다")


P._default_noter = _never          # 🔴 어떤 경로로도 실 Redmine 에 닿지 않게


class Paths:
    def __init__(self, root, name=""):
        self.root = str(root)
        self.repo = str(Path(root) / "repo")
        self.ontology = str(Path(root) / "ontology")
        self.canary = Path(root) / "canary" / "permanent_loss.jsonl"
        self.usage_log = Path(root) / "usage_log.jsonl"
        self.config = Path(root) / "config.yaml"
        self.name = name


class Noter:
    def __init__(self, fail=0):
        self.calls, self.fail = [], fail

    def __call__(self, issue_id, *, notes):
        self.calls.append((issue_id, notes))
        if self.fail:
            self.fail -= 1
            return "[주의] 레드마인 응답 500"
        return f"#{issue_id} 노트 기록"


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def make_twin(n_commits=4):
    """트윈 루트 + 미러(`repo`) — 커밋마다 A.cpp 를 바꾼다. 반환 (루트, [sha…] 오래된 것부터)."""
    root = Path(tempfile.mkdtemp(prefix="ax-ip-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    git(root, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    (repo / "Source" / "M" / "A.h").write_text("class AFoo {\npublic:\n  void Bar();\n};\n",
                                               encoding="utf-8")
    shas = []
    for i in range(n_commits):
        (repo / "Source" / "M" / "A.cpp").write_text(
            f"void AFoo::Bar() {{\n  int x = {i};\n  x = x / 0;\n}}\n", encoding="utf-8")
        git(repo, "add", "-A"); git(repo, "commit", "-qm", f"c{i}")
        shas.append(git(repo, "rev-parse", "HEAD").stdout.strip())
    return root, shas


def register(root, hashes, base="0" * 40, end="f" * 40):
    res = T.register(root, N, project="T", base=base, end=end, hashes=list(hashes))
    assert res["ok"], res
    return res


def hstate(root, sha):
    return next(h for h in T.current(root, N)["hashes"] if h["sha"] == sha)


def _review_body():
    return """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/A.cpp | 높음 | 3 | 0으로 나눔 | 분모 검사 |
| Source/M/A.cpp | 낮음 | 2 | 매직 넘버 | 상수로 |

## 3. 영향 분석
런타임 오류 위험.
"""


def review_done(root, sha):
    """실제 소비자 경로로 커밋 리뷰를 끝낸다 — R 번호·지적 수가 fix_index 에서 나온다."""
    Q.enqueue(root, key=sha, files=["Source/M/A.cpp"])
    r = R.run_once(Paths(root), draft_call=lambda p: "없음", review_call=lambda p: _review_body())
    assert r is not None and r.state == "done", (r and r.why)
    return r


def abandon(root, sha, why="Antigravity 실패 — 결정적 형식 위반"):
    Q.enqueue(root, key=sha, files=["Source/M/A.cpp"])
    for _ in range(10):
        it = next(x for x in Q.items(root) if x["key"] == sha)
        if it["state"] == "abandoned":
            return it
        Q.claim(root)
        Q.finish(root, f"commit:{sha}", ok=False, why=why)
    raise AssertionError("abandoned 로 가지 않았다")


def test_done_과_포기_한_노트():
    root, shas = make_twin(4)
    a, b, c, d = shas
    register(root, shas)
    review_done(root, a)
    abandon(root, b)
    noter, logs = Noter(), []
    out = P.sync_issue_tracks(Paths(root), noter=noter, watermark="", logf=logs.append)
    ha, hb = hstate(root, a), hstate(root, b)
    check("① done 으로 옮긴다", ha["state"] == "done", str(ha))
    check("① R 번호와 지적 수", ha["serial"].startswith("R") and ha["findings"] == 2, str(ha))
    check("② abandoned 로 옮긴다 · 사유", hb["state"] == "abandoned" and "형식 위반" in hb["why"], str(hb))
    check("🔴 ③ 노트는 하나", len(noter.calls) == 1, str(noter.calls))
    text = noter.calls[0][1] if noter.calls else ""
    check("③ 일감 번호로 남긴다", noter.calls and noter.calls[0][0] == N, str(noter.calls))
    check("① 머리줄 — 끝난 수·남은 수", "해시 리뷰 진행 (회차 1) — 2/4 끝남 · 남은 2" in text, text)
    check("① 노트에 R 번호·지적·심각도",
          f"`{a[:12]}` {ha['serial']} · 지적 2 (높음 1·중간 0·낮음 1)" in text, text)
    check("② 노트에 포기와 사유", f"`{b[:12]}` 포기 — " in text and "형식 위반" in text, text)
    check("③ 남은 해시는 노트에 줄이 없다", c[:12] not in text and d[:12] not in text, text)
    check("명령형이 없다", not any(w in text for w in ("하세요", "하라", "해라", "할 것")), text)
    check("① noted=True", ha["noted"] and hb["noted"], f"{ha['noted']} {hb['noted']}")
    check("반환 건수", out["done"] == 1 and out["abandoned"] == 1 and out["noted_notes"] == 1
          and out["noted_hashes"] == 2 and out["ok"], str(out))
    check("결정마다 로그", any("[issue-progress] #884" in m and "done → done" in m for m in logs)
          and any("abandoned → abandoned" in m for m in logs), str(logs))
    # 다시 돌려도 노트가 또 나가지 않는다
    P.sync_issue_tracks(Paths(root), noter=noter, watermark="", logf=logs.append)
    check("③ 재동기화는 노트 없음", len(noter.calls) == 1, str(len(noter.calls)))
    shutil.rmtree(root)


def test_노트_실패는_다음_회차가_다시():
    root, shas = make_twin(2)
    a, _b = shas
    register(root, shas)
    review_done(root, a)
    noter, logs = Noter(fail=1), []
    out = P.sync_issue_tracks(Paths(root), noter=noter, watermark="", logf=logs.append)
    check("④ 실패면 noted 그대로", hstate(root, a)["state"] == "done" and not hstate(root, a)["noted"],
          str(hstate(root, a)))
    check("④ 실패 건수·로그", out["note_failed"] == 1 and not out["ok"]
          and any("노트 실패" in m for m in logs), str(out))
    P.sync_issue_tracks(Paths(root), noter=noter, watermark="", logf=logs.append)
    check("④ 다음 동기화가 다시 남긴다", len(noter.calls) == 2 and hstate(root, a)["noted"],
          str(len(noter.calls)))
    P.sync_issue_tracks(Paths(root), noter=noter, watermark="", logf=logs.append)
    check("④ 성공 뒤 중복 없음", len(noter.calls) == 2, str(len(noter.calls)))

    # 예외도 실패로 접는다
    root2, shas2 = make_twin(1)
    register(root2, shas2)
    review_done(root2, shas2[0])

    def boom(*_a, **_kw):
        raise ConnectionError("끊김")
    out = P.sync_issue_tracks(Paths(root2), noter=boom, watermark="", logf=logs.append)
    check("④ noter 예외도 실패 · noted 그대로",
          out["note_failed"] == 1 and not hstate(root2, shas2[0])["noted"], str(out))
    shutil.rmtree(root); shutil.rmtree(root2)


def test_워터마크():
    root, shas = make_twin(4)
    a, b, c, d = shas
    register(root, [a, b, d, GHOST])
    noter, logs = Noter(), []
    out = P.sync_issue_tracks(Paths(root), noter=noter, watermark=c, logf=logs.append)
    check("⑤ 워터마크의 조상 → skipped", hstate(root, a)["state"] == "skipped"
          and hstate(root, b)["state"] == "skipped", f"{hstate(root, a)} {hstate(root, b)}")
    check("⑤ why", hstate(root, a)["why"] == P.WATERMARK_SKIP_WHY, hstate(root, a)["why"])
    check("⑤ 워터마크 뒤 커밋은 waiting", hstate(root, d)["state"] == "waiting", str(hstate(root, d)))
    check("🔴 ⑤ 미러에 없는 해시는 waiting", hstate(root, GHOST)["state"] == "waiting",
          str(hstate(root, GHOST)))
    check("⑤ 미러 지연을 로그에 남긴다", any("미러에 아직 없다" in m for m in logs), str(logs))
    text = noter.calls[0][1] if noter.calls else ""
    check("⑤ 생략도 노트에 · 하나로", len(noter.calls) == 1 and f"`{a[:12]}` 생략 — " in text
          and "2/4 끝남 · 남은 2" in text, text)
    check("⑤ 반환 skipped=2", out["skipped"] == 2, str(out))

    # 워터마크를 비우면(트윈 config 없음) 판정하지 않는다
    root2, shas2 = make_twin(2)
    register(root2, shas2[:1])
    P.sync_issue_tracks(Paths(root2), noter=Noter(), logf=logs.append)
    check("⑤ 워터마크 없음 → waiting 유지", hstate(root2, shas2[0])["state"] == "waiting")
    # 트윈 config 의 last_indexed_commit 을 기본값으로 읽는다
    (root2 / "config.yaml").write_text(
        f"version: 1\nname: T\nindex:\n  last_indexed_commit: {shas2[1]}\n", encoding="utf-8")
    P.sync_issue_tracks(Paths(root2), noter=Noter(), logf=logs.append)
    check("⑤ config 워터마크를 기본으로 읽는다", hstate(root2, shas2[0])["state"] == "skipped",
          str(hstate(root2, shas2[0])))
    shutil.rmtree(root); shutil.rmtree(root2)


def test_추적_밖과_연결():
    root, shas = make_twin(3)
    a, b, c = shas
    register(root, [a])
    Q.enqueue(root, key=a, files=["Source/M/A.cpp"])            # 색인기가 등록 전에 넣었다 · 우선순위 0
    Q.enqueue(root, key=c, files=["Source/M/A.cpp"])            # 추적 밖
    before_c = next(x for x in Q.items(root) if x["key"] == c)
    logs = []
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=c, logf=logs.append)
    ia = next(x for x in Q.items(root) if x["key"] == a)
    ic = next(x for x in Q.items(root) if x["key"] == c)
    check("⑥ waiting + pending → queued · 우선순위 10",
          hstate(root, a)["state"] == "queued" and ia["priority"] == 10
          and (ia.get("meta") or {}).get("issue_id") == N, f"{hstate(root, a)} {ia}")
    check("⑥ queued 는 워터마크로 skipped 되지 않는다", out["skipped"] == 0, str(out))
    check("⑥ 추적 밖 항목은 그대로", ic == before_c, f"{ic} / {before_c}")
    shutil.rmtree(root)


def test_깨진_추적_파일():
    root, shas = make_twin(1)
    T.state_path(root).write_text("{깨짐", encoding="utf-8")
    logs = []
    try:
        out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark="", logf=logs.append)
        raised = False
    except Exception as e:                                      # noqa: BLE001
        out, raised = {"err": repr(e)}, True
    check("⑦ 예외가 올라오지 않는다", not raised, str(out))
    check("⑦ 크게 찍는다", any("[중요]" in m and "믿을 수 없다" in m for m in logs), str(logs))
    check("⑦ 파일을 덮지 않는다", T.state_path(root).read_text(encoding="utf-8") == "{깨짐")
    # 추적 파일이 없으면 잠금 파일도 안 만든다
    root2, _ = make_twin(1)
    P.sync_issue_tracks(Paths(root2), noter=Noter(), watermark="", logf=logs.append)
    check("⑦ 추적 파일 없으면 잠금 파일도 없다", not (root2 / T.LOCK_NAME).exists())
    shutil.rmtree(root); shutil.rmtree(root2)


def test_실_redmine_가드():
    root, shas = make_twin(1)
    register(root, shas)
    review_done(root, shas[0])
    calls, logs = [], []
    orig = P._default_noter
    P._default_noter = lambda *a, **kw: calls.append(a) or "기록"
    try:
        out = P.sync_issue_tracks(Paths(root, name="T"), watermark="", logf=logs.append)
    finally:
        P._default_noter = orig
    check("🔴 ⑧ 등록 안 된 루트 + noter 미주입 → 호출 없음", not calls, str(calls))
    check("⑧ noted 그대로 · 생략 로그", not hstate(root, shas[0])["noted"]
          and out["note_skipped"] == 1 and any("노트 생략" in m for m in logs), str(out))
    check("⑧ 상태 동기화는 한다", hstate(root, shas[0])["state"] == "done")
    shutil.rmtree(root)


def _make_registry(twin_src: Path):
    projects = Path(tempfile.mkdtemp(prefix="ax-reg-"))
    (projects / "projects.yaml").write_text(
        "version: 1\nactive: T\nprojects:\n  - T\n", encoding="utf-8")
    twin = projects / "T"
    twin.mkdir()
    (twin / "config.yaml").write_text(
        "version: 1\nname: T\nrepo:\n  local_clone: repo\n", encoding="utf-8")
    shutil.copytree(twin_src / "repo", twin / "repo")
    return projects, twin


def test_main_이_drain_앞뒤로_부른다():
    root, shas = make_twin(2)
    projects, twin = _make_registry(root)
    old_env = os.environ.get("AX_PROJECTS_ROOT")
    os.environ["AX_PROJECTS_ROOT"] = str(projects)
    order = []
    orig_sync, orig_drain = P.sync_issue_tracks, R.drain
    P.sync_issue_tracks = lambda paths, **kw: order.append(("sync", Path(paths.root).name)) or {}
    R.drain = lambda *a, **kw: order.append(("drain",)) or []
    try:
        Q.enqueue(twin, key=shas[0], files=["Source/M/A.cpp"])
        rc = R.main(["--limit", "1"])
        check("⑨ main rc=0", rc == 0, f"rc={rc}")
        check("🔴 ⑨ sync → drain → sync", order == [("sync", "T"), ("drain",), ("sync", "T")], str(order))
    finally:
        P.sync_issue_tracks, R.drain = orig_sync, orig_drain

    # 실물 한 바퀴 — 등록된 트윈에서 리뷰가 끝나면 같은 회차에 노트가 난다(noter 만 대역)
    register(twin, shas)
    calls = []
    orig_noter, orig_draft, orig_agy = P._default_noter, R.draft, R.agy_only
    P._default_noter = lambda n, *, notes: calls.append((n, notes)) or "기록"
    R.draft = lambda *a, **kw: ("없음", "")
    R.agy_only = lambda _p, **_kw: _review_body()
    try:
        rc = R.main(["--limit", "1"])
        h = next(x for x in T.current(twin, N)["hashes"] if x["sha"] == shas[0])
        check("⑨ 같은 회차에 done · 노트", rc == 0 and h["state"] == "done" and h["noted"]
              and len(calls) == 1 and f"`{shas[0][:12]}` R" in calls[0][1], f"{h} {calls}")
    finally:
        P._default_noter, R.draft, R.agy_only = orig_noter, orig_draft, orig_agy
        if old_env is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old_env
    shutil.rmtree(root); shutil.rmtree(projects)


if __name__ == "__main__":
    for fn in (test_done_과_포기_한_노트, test_노트_실패는_다음_회차가_다시, test_워터마크,
               test_추적_밖과_연결, test_깨진_추적_파일, test_실_redmine_가드,
               test_main_이_drain_앞뒤로_부른다):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
