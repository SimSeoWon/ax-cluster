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
    (T4 종합 리뷰)
    ⑩ 해시가 전부 종결돼야만 종합 리뷰 등재(우선순위 10 · meta track) · 재동기화는 멱등
    ⑪ 종합 리뷰 프롬프트에 해시별 지적·포기/생략 해시가 실린다 · 남음은 fix_index 가 세고 해소는 안 센다
    ⑫ 종합 노트 — 해시 결과 표(완료 R·포기 사유·생략 사유) · 지적별 남음/해소 · summary done·noted
    ⑬ summary 전이 — running · 노트 실패면 닫지 않음 · 포기(abandoned) 노트 · 큐에서 사라지면 waiting
    ⑭ 같은 범위의 옛 범위 항목 — done 은 재사용 안 함(failed) · pending 은 채택
    ⑮ 해시 지적이 없으면 종전 범위 리뷰와 같다(판정 절 없음) · 판정 절 누락은 1회 재시도

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


def test_워터마크_부재는_회차당_한_번():
    """`#917`(R240-8) — 미러에 없는 워터마크는 대기 해시 수와 상관없이 git 확인 1회 · [주의] 1줄."""
    root, shas = make_twin(3)
    register(root, shas)
    wm = "e" * 40                                    # 미러에 없는 워터마크
    calls, logs = [], []
    real = P._has_commit

    def counting(repo, sha):
        calls.append(sha)
        return real(repo, sha)
    P._has_commit = counting
    try:
        out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=wm, logf=logs.append)
    finally:
        P._has_commit = real
    warn = [m for m in logs if "워터마크" in m and "미러에 없다" in m]
    check("🔴 R240-8 워터마크 git 확인 1회(대기 해시 3)", calls.count(wm) == 1, str(calls))
    check("R240-8 [주의] 로그 1줄", len(warn) == 1, str(warn))
    check("R240-8 해시는 waiting 그대로", all(hstate(root, s)["state"] == "waiting" for s in shas)
          and out["skipped"] == 0, str(out))
    # 대기 해시가 없으면 워터마크를 묻지 않는다
    root2, shas2 = make_twin(1)
    register(root2, shas2)
    review_done(root2, shas2[0])
    calls.clear()
    P._has_commit = counting
    try:
        P.sync_issue_tracks(Paths(root2), noter=Noter(), watermark=wm, logf=logs.append)
    finally:
        P._has_commit = real
    check("R240-8 큐에 있는 해시만이면 워터마크 확인 0", wm not in calls, str(calls))
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


# ── T4 종합 리뷰 ─────────────────────────────────────────────────────────────

def _range_body(verdicts: dict, *, remain_row=True) -> str:
    rows = "\n".join(f"| {k} | {v} | Source/M/A.cpp:3 |" for k, v in verdicts.items())
    safety = "| Source/M/A.cpp | 높음 | 3 | 0으로 나눔(남음) | 분모 검사 |\n" if remain_row else ""
    return ("### Source/M\n\n## 1. 변경분 코딩 컨벤션\n| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n"
            "|---|---|---|---|---|\n\n## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
            "|---|---|---|---|---|\n" + safety + "\n## 3. 영향 분석\n영향 없음.\n\n"
            "### 해시별 지적 판정\n| 원 지적 | 판정(남음/해소) | 근거(파일:라인) |\n|---|---|---|\n" + rows + "\n")


def _plain_range_body() -> str:
    return ("### Source/M\n\n## 1. 변경분 코딩 컨벤션\n| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n"
            "|---|---|---|---|---|\n\n## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
            "|---|---|---|---|---|\n\n## 3. 영향 분석\n영향 없음.\n")


def _range(root):
    return [x for x in Q.items(root) if x["kind"] == "range"]


def _summary(root, n=N):
    return T.current(root, n)["summary"]


def _set_range_state(root, state, **kw):
    data = Q._read(root)
    for x in data["items"]:
        if x["kind"] == "range":
            x["state"] = state
            x.update(kw)
    Q._write(root, data)


def _scenario():
    """a(base) → b(지적 2: 높음·낮음) · c(포기) · d(워터마크 생략). 반환 (루트, a,b,c,d)."""
    root, shas = make_twin(4)
    a, b, c, d = shas
    T.register(root, N, project="T", base=a, end=d, hashes=[b, c, d])
    review_done(root, b)
    abandon(root, c)
    return root, a, b, c, d


def test_종합_등재는_전부_종결_뒤():
    root, a, b, c, d = _scenario()
    logs = []
    # d 가 아직 waiting(워터마크 없음) → 등재 없음
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark="", logf=logs.append)
    check("⑩ 해시가 남으면 등재 없음", not _range(root) and _summary(root)["state"] == "waiting"
          and out["range_queued"] == 0, str(_range(root)))
    # 워터마크가 d 를 지나 → 전부 종결 → 등재
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    rs = _range(root)
    check("⑩ 전부 종결 → 범위 항목 1건", len(rs) == 1 and rs[0]["key"] == f"{a}..{d}", str(rs))
    m = rs[0].get("meta") or {}
    check("⑩ 우선순위 10 · meta track·회차", rs and rs[0]["priority"] == 10 and m.get("track") is True
          and m.get("issue_round") == 1 and m.get("issue_id") == N and m.get("base") == a
          and m.get("end") == d, str(rs))
    sm = _summary(root)
    check("⑩ summary queued · item_id", sm["state"] == "queued" and sm["item_id"] == rs[0]["id"], str(sm))
    check("⑩ 등재 로그", any("전부 종결 → 종합 리뷰 등재" in x for x in logs), str(logs[-5:]))
    check("⑩ 반환 range_queued=1", out["range_queued"] == 1, str(out))
    # 멱등
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    check("⑩ 재동기화 — 항목 그대로 1건 · queued", len(_range(root)) == 1
          and _summary(root)["state"] == "queued" and out["range_queued"] == 0, str(out))
    shutil.rmtree(root)


def test_종합_리뷰_한_바퀴():
    root, a, b, c, d = _scenario()
    noter, logs = Noter(), []
    P.sync_issue_tracks(Paths(root), noter=noter, watermark=d, logf=logs.append)
    sb = hstate(root, b)["serial"]
    r1, r2 = f"{sb}-1", f"{sb}-2"
    prompts, rnotes = [], Noter()
    rr = R.run_once(Paths(root), range_noter=rnotes,
                    review_call=lambda p, **kw: prompts.append(p) or _range_body({r1: "남음", r2: "해소"}))
    check("⑪ 종합 리뷰 done · 모델 1회", rr is not None and rr.state == "done" and len(prompts) == 1,
          f"{rr and rr.state} {rr and rr.why} {len(prompts)}")
    pr = prompts[0] if prompts else ""
    check("⑪ 프롬프트에 해시별 지적 절", "## 해시별 리뷰 지적 — 최종 코드 기준으로 남음/해소 판정" in pr, pr[-800:])
    check("⑪ 지적 번호·내용이 실린다", f"| {r1} | {b[:12]} | 높음 | Source/M/A.cpp:3 | 0으로 나눔 |" in pr
          and f"| {r2} |" in pr, pr[pr.find("## 해시별"):][:600])
    check("⑪ 포기·생략 해시가 실린다", f"- {c[:12]} 포기 — " in pr and f"- {d[:12]} 생략 — {P.WATERMARK_SKIP_WHY}" in pr,
          pr[pr.find("커밋 리뷰를 거치지"):][:300])
    check("⑪ 판정 규칙과 판정 절 예시", "`남음`" in pr and "### 해시별 지적 판정\n| 원 지적 | 판정(남음/해소) | 근거(파일:라인) |" in pr)
    check("⑪ 지적 절은 DIFF 앞", 0 < pr.find("## 해시별 리뷰 지적") < pr.find("## DIFF"))
    from master.context_synth import fix_index as FX
    doc = FX.get_doc(root, rr.serial)
    ids = [x["description"] for x in doc.get("items_detail") or []]
    check("🔴 ⑪ fix_index 는 남음(다시 적힌 행)만 센다 — 판정 표 행은 안 센다",
          doc.get("ok") and doc.get("items") == 1 and ids == ["0으로 나눔(남음)"], str(ids))
    text = Path(rr.written).read_text(encoding="utf-8")
    check("⑪ 머리말 회차 줄", "- 종합 회차: #884 회차 1" in text and "- 해시 리뷰 지적: 2건" in text, text[:400])
    # 노트(run_range 가 바로 남긴다)
    check("⑫ 노트 1건 · 그 일감", len(rnotes.calls) == 1 and rnotes.calls[0][0] == N, str(rnotes.calls))
    nt = rnotes.calls[0][1] if rnotes.calls else ""
    check("⑫ 해시 결과 머리줄", "종합 리뷰 회차 1 — 해시 3건: 리뷰 완료 1 · 포기 1 · 생략 1" in nt, nt)
    check("⑫ 완료 해시 R·지적 수", f"| `{b[:12]}` | 완료 | {sb} · 지적 2 |" in nt, nt)
    check("⑫ 포기 해시와 사유", f"| `{c[:12]}` | 포기 | " in nt and "형식 위반" in nt, nt)
    check("⑫ 생략 해시와 사유", f"| `{d[:12]}` | 생략 | {P.WATERMARK_SKIP_WHY} |" in nt, nt)
    check("⑫ 지적별 판정 집계", "해시별 지적 판정 — 남음 1 · 해소 1 · 판정 없음 0" in nt, nt)
    check("⑫ 지적별 판정 행", f"| {r1} | 높음 | Source/M/A.cpp:3 | 0으로 나눔 | 남음 | Source/M/A.cpp:3 |" in nt
          and f"| {r2} | 낮음 |" in nt and "| 해소 |" in nt, nt)
    check("⑫ 명령형 없음 · 절대 경로 없음", not any(w in nt for w in ("하세요", "하라", "해라", "할 것"))
          and str(root) not in nt, nt)
    # 다음 동기화 — summary done · noted · 회차 닫힘
    out = P.sync_issue_tracks(Paths(root), noter=noter, watermark=d, logf=logs.append)
    sm = T.rounds(root, N)[-1]["summary"]
    check("⑫ summary done · R · noted", sm["state"] == "done" and sm["serial"] == rr.serial and sm["noted"],
          str(sm))
    check("⑫ 회차가 닫힌다", T.open_rounds(root) == [] and out["range_done"] == 1, str(out))
    n_before = len(noter.calls) + len(rnotes.calls)
    P.sync_issue_tracks(Paths(root), noter=noter, watermark=d, logf=logs.append)
    check("⑫ 닫힌 뒤 노트 중복 없음", len(noter.calls) + len(rnotes.calls) == n_before)
    shutil.rmtree(root)


def test_종합_상태_전이():
    root, a, b, c, d = _scenario()
    logs = []
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    # running
    Q.claim(root)
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    check("⑬ 큐 running → summary running", _summary(root)["state"] == "running" and out["range_running"] == 1,
          str(_summary(root)))
    # 일시 실패로 pending 복귀 → queued 및 진행 노트 남김 (#882)
    Q.finish(root, _range(root)[0]["id"], ok=False, why="일시 오류 — 네트워크")
    retry_noter = Noter()
    P.sync_issue_tracks(Paths(root), noter=retry_noter, watermark=d, logf=logs.append)
    check("⑬ 재시도 대기 → queued", _summary(root)["state"] == "queued", str(_summary(root)))
    check("⑬ (#882) 재시도 대기 시 진행 노트 기록", len(retry_noter.calls) == 1
          and "자동 범위 리뷰 재시도 대기" in retry_noter.calls[0][1]
          and "일시 오류 — 네트워크" in retry_noter.calls[0][1], str(retry_noter.calls))
    # 같은 attempts 재시도 대기 재동기화 시 중복 노트 없음
    P.sync_issue_tracks(Paths(root), noter=retry_noter, watermark=d, logf=logs.append)
    check("⑬ (#882) 같은 시도 재동기화 시 중복 재시도 노트 없음", len(retry_noter.calls) == 1,
          str(retry_noter.calls))
    # 리뷰 done · 노트 실패 → summary 안 닫힘
    bad = Noter(fail=5)
    R.run_once(Paths(root), range_noter=bad, review_call=lambda p, **kw: _range_body(
        {f"{hstate(root, b)['serial']}-1": "해소", f"{hstate(root, b)['serial']}-2": "해소"}, remain_row=False))
    out = P.sync_issue_tracks(Paths(root), noter=bad, watermark=d, logf=logs.append)
    check("⑬ 노트 실패 → summary 닫지 않음", _summary(root)["state"] in ("queued", "running")
          and out["range_note_failed"] == 1 and not out["ok"], f"{_summary(root)} {out}")
    good = Noter()
    out = P.sync_issue_tracks(Paths(root), noter=good, watermark=d, logf=logs.append)
    sm = T.rounds(root, N)[-1]["summary"]
    check("⑬ 다음 회차가 노트 → done·noted", sm["state"] == "done" and sm["noted"] and len(good.calls) == 1
          and "남음 0 · 해소 2" in good.calls[0][1], f"{sm} {good.calls}")
    shutil.rmtree(root)

    # 포기(abandoned) — 끝난 것으로 친다
    root, a, b, c, d = _scenario()
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    _set_range_state(root, "abandoned", attempts=3, last_why="Antigravity 실패 — 한도 초과 반복")
    noter = Noter()
    out = P.sync_issue_tracks(Paths(root), noter=noter, watermark=d, logf=logs.append)
    sm = T.rounds(root, N)[-1]["summary"]
    check("⑬ 포기 → summary abandoned · noted · 회차 닫힘", sm["state"] == "abandoned" and sm["noted"]
          and T.open_rounds(root) == [] and out["range_abandoned"] == 1, f"{sm} {out}")
    nt = noter.calls[-1][1] if noter.calls else ""
    check("⑬ 포기 노트 — 사유·해시 표·판정 없음", "자동 범위 리뷰 포기" in nt and "한도 초과 반복" in nt
          and "복구 안내:" in nt and f"| `{c[:12]}` | 포기 | " in nt and "판정 없음" in nt, nt)
    check("⑬ 포기 노트 meta.noted", (_range(root)[0].get("meta") or {}).get("noted") is True)
    shutil.rmtree(root)

    # 큐에서 사라짐 → waiting → 재등재
    root, a, b, c, d = _scenario()
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    data = Q._read(root)
    data["items"] = [x for x in data["items"] if x["kind"] != "range"]
    Q._write(root, data)
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    check("⑬ 항목 사라짐 → waiting", _summary(root)["state"] == "waiting", str(_summary(root)))
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    check("⑬ 다음 동기화가 다시 등재", len(_range(root)) == 1 and _summary(root)["state"] == "queued")
    shutil.rmtree(root)


def test_같은_범위의_옛_항목():
    from master.context_synth import review_gen as RG
    # done 인 옛 범위 항목 → 재사용하지 않는다
    root, a, b, c, d = _scenario()
    Q.enqueue(root, kind="range", key=f"{a}..{d}", files=[], requester="issue_flow#884", priority=10,
              meta={"issue_id": N, "base": a, "end": d})
    legacy_notes = Noter()
    lr = R.run_once(Paths(root), range_noter=legacy_notes, review_call=lambda p, **kw: _plain_range_body())
    check("⑭ (준비) 옛 범위 리뷰 done", lr.state == "done" and _range(root)[0]["state"] == "done")
    check("⑭ 옛 노트에는 종합 절이 없다(#879 그대로)", legacy_notes.calls
          and "종합 리뷰 회차" not in legacy_notes.calls[0][1], str(legacy_notes.calls))
    logs = []
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    it0 = _range(root)[0]
    check("🔴 ⑭ 옛 done → summary failed · 재사용 안 함", _summary(root)["state"] == "failed"
          and out["range_stale"] == 1 and not (it0.get("meta") or {}).get("track"), f"{_summary(root)} {it0}")
    check("⑭ 크게 찍는다", any("[중요]" in x and "종합 리뷰 등재 불가" in x for x in logs), str(logs[-4:]))
    out = P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    check("⑭ 재동기화 — failed 유지 · 항목 그대로", _summary(root)["state"] == "failed"
          and len(_range(root)) == 1 and _range(root)[0]["state"] == "done", str(_summary(root)))
    # 문서 재사용도 막는다 — 회차 줄 없는 옛 문서
    check("⑭ find_range_review — 옛 문서는 일반 재사용만", RG.find_range_review(Paths(root), a, d) is not None
          and RG.find_range_review(Paths(root), a, d, issue_id=N, issue_round=1) is None)
    # 큐 항목이 pending 으로 돌아오면(사람이 되돌림) 다음 회차가 채택해 종합 리뷰를 다시 만든다
    _set_range_state(root, "pending")
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    it1 = _range(root)[0]
    check("⑭ pending 옛 항목 채택 — track·회차·우선순위 10 · queued", (it1.get("meta") or {}).get("track") is True
          and it1["meta"].get("issue_round") == 1 and it1["priority"] == 10
          and _summary(root)["state"] == "queued", f"{it1} {_summary(root)}")
    prompts = []
    sb = hstate(root, b)["serial"]
    rr = R.run_once(Paths(root), range_noter=Noter(), review_call=lambda p, **kw: prompts.append(p)
                    or _range_body({f"{sb}-1": "남음", f"{sb}-2": "해소"}))
    check("🔴 ⑭ 채택 뒤에는 옛 문서를 재사용하지 않고 모델을 부른다", rr.state == "done" and len(prompts) == 1
          and "## 해시별 리뷰 지적" in prompts[0], f"{rr.state} {len(prompts)}")
    # 같은 회차 재시도는 새 문서를 재사용한다(모델 0)
    _set_range_state(root, "pending")
    again = []
    rr2 = R.run_once(Paths(root), range_noter=Noter(), review_call=lambda p, **kw: again.append(p) or "x")
    check("⑭ 같은 회차 종합 문서는 재사용(모델 0)", rr2.state == "done" and not again
          and "기존 범위 리뷰" in (_range(root)[0]["history"][-1].get("note") or ""), f"{rr2.state} {len(again)}")
    shutil.rmtree(root)


def test_지적_없으면_종전_범위_리뷰():
    root, shas = make_twin(3)
    a, b, c = shas
    T.register(root, N, project="T", base=a, end=c, hashes=[b, c])
    noter, logs = Noter(), []
    P.sync_issue_tracks(Paths(root), noter=noter, watermark=c, logf=logs.append)   # b·c 생략
    check("⑮ (준비) 전부 생략 → 등재", len(_range(root)) == 1 and _summary(root)["state"] == "queued")
    prompts, rnotes = [], Noter()
    rr = R.run_once(Paths(root), range_noter=rnotes,
                    review_call=lambda p, **kw: prompts.append(p) or _plain_range_body())
    pr = prompts[0] if prompts else ""
    check("⑮ 지적 없음 → 판정 절 없이 통과 · 1회", rr.state == "done" and len(prompts) == 1, f"{rr.state} {rr.why}")
    check("⑮ 프롬프트에 해시 지적 절·판정 규칙 없음", "해시별 리뷰 지적" not in pr and "해시별 지적 판정" not in pr)
    nt = rnotes.calls[0][1] if rnotes.calls else ""
    check("⑮ 노트 — 해시 결과 표 · 지적 0건", "리뷰 완료 0 · 포기 0 · 생략 2" in nt
          and "해시별 커밋 리뷰 지적: 0건" in nt, nt)
    shutil.rmtree(root)

    # 판정 절을 빠뜨리면 1회 재시도
    root, a, b, c, d = _scenario()
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    sb = hstate(root, b)["serial"]
    replies = [_plain_range_body(), _range_body({f"{sb}-1": "남음", f"{sb}-2": "해소"})]
    prompts = []
    rr = R.run_once(Paths(root), range_noter=Noter(),
                    review_call=lambda p, **kw: prompts.append(p) or replies[len(prompts) - 1])
    check("⑮ 판정 절 누락 → 재시도 · 예시에 판정 절", rr.state == "done" and len(prompts) == 2
          and prompts[1].startswith("직전 응답이 형식을 어겼다")
          and prompts[1].count("### 해시별 지적 판정") >= 2, f"{rr.state} {len(prompts)}")
    shutil.rmtree(root)
    root, a, b, c, d = _scenario()
    P.sync_issue_tracks(Paths(root), noter=Noter(), watermark=d, logf=logs.append)
    rr = R.run_once(Paths(root), range_noter=Noter(), review_call=lambda p, **kw: _plain_range_body())
    it0 = _range(root)[0]
    check("⑮ 두 번 다 누락 → 형식 위반 실패 · 문서는 _rejected", rr.state == "failed"
          and it0["state"] == "pending" and (Path(root) / "reviews" / "_rejected").is_dir(), f"{rr.state} {it0['state']}")
    shutil.rmtree(root)


def test_공개_apply_를_쓴다():
    """`#884` T5 — 동기화는 `issue_link.apply`(공개 이름)를 부른다."""
    import inspect
    src = inspect.getsource(P)
    check("⑩ il.apply 사용", "il.apply(" in src and "il._apply(" not in src)


if __name__ == "__main__":
    for fn in (test_공개_apply_를_쓴다, test_done_과_포기_한_노트, test_노트_실패는_다음_회차가_다시, test_워터마크, test_워터마크_부재는_회차당_한_번,
               test_추적_밖과_연결, test_깨진_추적_파일, test_실_redmine_가드,
               test_main_이_drain_앞뒤로_부른다,
               test_종합_등재는_전부_종결_뒤, test_종합_리뷰_한_바퀴, test_종합_상태_전이,
               test_같은_범위의_옛_항목, test_지적_없으면_종전_범위_리뷰):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
