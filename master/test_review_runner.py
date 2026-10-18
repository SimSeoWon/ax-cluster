"""리뷰 큐 소비자 (`#636`·`#638`) — 로컬 초안 → Antigravity 정형 리뷰.

검증하는 것:

    ① 로컬 초안 뒤에 Antigravity를 정확히 한 번 부른다 (Claude 자동 폴백 없음)
    ② 성공하면 초안은 제거되고 최종 정형 리뷰만 `reviews/<작성자>/`
    ③ 최종 리뷰를 기존 수집기가 읽어 주간 플랜 입력이 된다
    ④ 로컬이 「없음」이어도 Antigravity는 원본 diff를 직접 본다
    ⑤ 초고 호출 실패는 큐에 남아 재시도된다
    ⑥ diff 를 못 읽으면 **결정적**으로 갈려 1회에 멈춘다
    ⑦ trivial·소스 없음은 유실이 아니라 설계된 스킵 — done 으로 종결
    ⑧ `kind=scope` 는 이 소비자가 처리하지 않는다 (`#639` 의 몫)
    ⑨ 선언부는 커밋에 `.h` 가 없어도 짝 헤더에서 긁는다
    ⑩ grounding 머리말이 「미검증·버려라」를 먼저 말한다 (Antigravity 검증용)
    ⑫ 기존 초안을 재사용하고 성공 시 제거한다. 실패 시에는 보존한다
    ⑪ 🔴 **`main()` 이 실제로 돈다** — 유닛이 부르는 진입점이다
    ⑬ 머지는 결합 diff(`--cc`)로 가른다 — 비면 스킵(done), 있으면 그것만 리뷰 (`#744` ①)
    ⑭ 지워진 [PSEUDO] 가 있으면 초고·퇴고 둘 다 「골조 지시 이행」을 싣는다 (`#815` ④)

[중요] ⑪ 은 값을 치르고 얻었다. 첫 배포 회차가 @reg.projects@ AttributeError 로 죽었는데
(`Registry` 의 필드는 `.names` 다), **유닛 21건이 전부 통과한 상태였다** — `run_once` 만 탔고
`main()` 은 한 줄도 안 탔기 때문이다. 유닛이 부르는 경로는 유닛 테스트도 타야 한다.

`.venv/bin/python master/test_review_runner.py`
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import review_gen as RG                 # noqa: E402
from master.context_synth import review_queue as Q                # noqa: E402
from master.context_synth import review_runner as R               # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Paths:
    def __init__(self, root):
        self.root = str(root)
        self.repo = str(Path(root) / "repo")
        self.ontology = str(Path(root) / "ontology")
        self.canary = Path(root) / "canary" / "permanent_loss.jsonl"
        self.usage_log = Path(root) / "usage_log.jsonl"          # `#713` ① 기록 지점


def git(root, *a):
    return subprocess.run(["git", "-C", str(root)] + list(a),
                          capture_output=True, text=True)


def make_repo() -> Path:
    """실제 git 저장소 — diff·작성자를 진짜로 읽는다 (모의하지 않는다)."""
    root = Path(tempfile.mkdtemp(prefix="ax-run-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    git(repo.parent, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    (repo / "Source" / "M" / "A.h").write_text(
        "class AFoo {\npublic:\n  void Bar();\n};\n", encoding="utf-8")
    (repo / "Source" / "M" / "A.cpp").write_text("void AFoo::Bar() {}\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "init")
    (repo / "Source" / "M" / "A.cpp").write_text(
        "void AFoo::Bar() {\n  int x = 1;\n  x = x / 0;\n}\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "change")
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    return root, head


def _review_body():
    return """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/A.cpp | 높음 | 3 | 0으로 나눔 | 분모 검사 |

## 3. 영향 분석
런타임 오류 위험.
"""


def test_로컬뒤_antigravity가_퇴고한다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls = []
    r = R.run_once(Paths(root), draft_call=lambda p: "나눗셈이 0 이다. 라인 3.",
                   review_call=lambda p: calls.append(p) or _review_body())
    check("① Antigravity 퇴고를 한 번 부른다", len(calls) == 1, str(len(calls)))
    check("① 퇴고 프롬프트에 초안과 원본 diff가 함께 있다",
          "나눗셈이 0" in calls[0] and "x = x / 0" in calls[0])
    check("② 성공한 초안은 제거", not r.draft_written
          and not list((Path(root) / "reviews" / "_drafts").rglob("*.md")))
    check("② 최종 리뷰는 작성자 디렉토리", "reviews/테스터/" in r.written
          and Path(r.written).is_file(), r.written)
    body = Path(r.written).read_text(encoding="utf-8")
    check("③ 최종 리뷰가 정형 계약", RG.format_ok(body) and RG.parseable_rows(body) == 1)
    check("③ 최종 리뷰에 모델 이력", "초안 모델: gemma4:e4b" in body
          and "검증 모델: Antigravity" in body)
    check("큐가 done 이다", Q.counts(root)["done"] == 1, str(Q.counts(root)))
    shutil.rmtree(root)


def test_로컬_없음이어도_antigravity가_본다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls = []
    r = R.run_once(Paths(root), draft_call=lambda p: "없음",
                   review_call=lambda p: calls.append(p) or _review_body())
    check("④ 로컬이 없음이어도 Antigravity 호출", len(calls) == 1)
    check("④ 최종 리뷰가 저장되고 done", bool(r.written) and r.state == "done"
          and Q.counts(root)["done"] == 1)
    shutil.rmtree(root)


def test_초안_실패여도_antigravity가_마무리한다():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])

    def boom(p):
        raise RuntimeError("브로커에 닿지 않는다")

    calls = []
    r = R.run_once(Paths(root), draft_call=boom,
                   review_call=lambda p: calls.append(p) or _review_body())
    check("⑤ 로컬 초안 실패여도 Antigravity가 호출된다", len(calls) == 1)
    check("⑤ 최종 리뷰 성공으로 종결된다", r.state == "done" and bool(r.written), r.state)
    shutil.rmtree(root)


def test_기존_초안_재사용과_실패_보존():
    root, head = make_repo()
    paths = Paths(root)
    old = Path(R.write_draft(paths, head, ["Source/M/A.cpp"], "기존 초안의 0 나눗셈"))
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    local_calls = []
    prompts = []
    r = R.run_once(paths, draft_call=lambda p: local_calls.append(p) or "새 초안",
                   review_call=lambda p: prompts.append(p) or _review_body())
    check("⑫ 기존 초안이면 로컬 재호출 없음", not local_calls)
    check("⑫ 기존 초안이 Antigravity 입력", "기존 초안의 0 나눗셈" in prompts[0])
    check("⑫ 성공한 기존 초안 제거", not old.exists() and r.state == "done")
    shutil.rmtree(root)

    root, head = make_repo()
    paths = Paths(root)
    old = Path(R.write_draft(paths, head, ["Source/M/A.cpp"], "실패 때 남을 초안"))
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    r = R.run_once(paths, draft_call=lambda p: "호출되면 안 됨", review_call=lambda p: "산문")
    check("⑫ 형식 실패면 초안 보존", r.state == "failed" and old.is_file())
    check("⑫ 실패 산출물은 일반 리뷰에 없음",
          not list((Path(root) / "reviews" / "테스터").glob("*.md")))
    shutil.rmtree(root)


def test_diff를_못_읽으면_결정적이다():
    root, _ = make_repo()
    Q.enqueue(root, key="0" * 40, files=["Source/M/A.cpp"])
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("⑥ 실패", r.state == "failed", r.state)
    it = Q.items(root)[0]
    check("🔴 ⑥ 결정적으로 갈린다", it["last_kind"] == Q.DETERMINISTIC, it["last_kind"])
    check("🔴 ⑥ 1회에 멈춘다 (몇 번을 돌려도 같다)",
          it["state"] == "abandoned", it["state"])
    shutil.rmtree(root)


def test_설계된_스킵():
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["README.md"])
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("⑦ 소스 변경 없음은 done", r.state == "done" and r.why == "소스 변경 없음", r.why)
    shutil.rmtree(root)

    root, head = make_repo()
    Q.enqueue(root, kind="scope", key="Source/M")
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("⑧ kind=scope 는 처리하지 않는다 (#639 의 몫)",
          r.state == "failed" and "kind" in (r.why or ""), r.why)
    shutil.rmtree(root)


def test_선언부():
    root, head = make_repo()
    d = R.declarations(Path(root) / "repo", ["Source/M/A.cpp"], head)
    check("🔴 ⑨ 커밋에 .h 가 없어도 짝 헤더를 긁는다", "class AFoo" in d, d[:80])
    check("⑨ 경로가 붙는다", "Source/M/A.h" in d, d[:80])
    shutil.rmtree(root)


def test_main_이_실제로_돈다():
    """🔴 ⑪ 유닛이 부르는 진입점. 레지스트리·경로 해석까지 진짜로 탄다.

    [중요] 여기서 모의하는 것은 **로컬 모델 호출 하나뿐**이다 — 나머지(레지스트리 로드,
    프로젝트 이름 해석, 트윈 경로, 큐 읽기)는 실물로 돈다. 첫 배포가 죽은 자리가 바로
    그 「나머지」였다.
    """
    import os
    root, head = make_repo()
    projects = Path(tempfile.mkdtemp(prefix="ax-reg-"))
    (projects / "projects.yaml").write_text(
        "version: 1\nactive: T\nprojects:\n  - T\n", encoding="utf-8")
    twin = projects / "T"
    twin.mkdir()
    (twin / "config.yaml").write_text(
        f"version: 1\nname: T\nrepo:\n  local_clone: repo\n", encoding="utf-8")
    shutil.copytree(Path(root) / "repo", twin / "repo")

    old_env = os.environ.get("AX_PROJECTS_ROOT")
    os.environ["AX_PROJECTS_ROOT"] = str(projects)
    calls = []
    orig_draft, orig_agy = R.draft, R.agy_only
    R.draft = lambda *a, **kw: (calls.append(1), ("나눗셈이 0 이다.", ""))[1]
    R.agy_only = lambda _p, **_kw: _review_body()
    try:
        Q.enqueue(twin, key=head, files=["Source/M/A.cpp"])
        rc = R.main(["--limit", "1"])
        check("🔴 ⑪ main() 이 rc=0 으로 끝난다", rc == 0, f"rc={rc}")
        check("⑪ 큐를 실제로 비웠다", Q.counts(twin)["done"] == 1, str(Q.counts(twin)))
        check("⑪ 초고 호출이 일어났다", len(calls) == 1, str(calls))
        rc2 = R.main(["--limit", "1"])
        check("⑪ 큐가 비면 조용히 끝난다", rc2 == 0 and len(calls) == 1, f"rc={rc2}")
    finally:
        R.draft = orig_draft
        R.agy_only = orig_agy
        if old_env is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old_env
    shutil.rmtree(root); shutil.rmtree(projects)


def test_퇴고도_사용량에_남는다():
    """⑬ `#728` — 퇴고(agy)가 초고와 **같은 task_id** 로 트윈 `usage_log.jsonl` 에 남는다.

    [중요] 퇴고는 **기본 경로(`agy_only` → `call_agy_why`)를 그대로 탄다** — PATH 앞에 둔
    가짜 `agy` 가 실측 봉투(2026-10-04)를 낸다. 초고는 브로커 대신 기록 지점을 직접 부른다.
    """
    import json
    import os
    from master.work import usage as U
    root, head = make_repo()
    paths = Paths(root)
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    bindir = Path(root) / "bin"
    bindir.mkdir()
    env = bindir / "envelope.json"
    env.write_text(json.dumps({"status": "SUCCESS", "response": _review_body(),
                               "usage": {"input_tokens": 900, "output_tokens": 120,
                                         "cache_read_tokens": 50, "total_tokens": 1020}},
                              ensure_ascii=False), encoding="utf-8")
    exe = bindir / "agy"
    exe.write_text(f'''#!/bin/sh
if [ "$1" = models ]; then
  printf '%s\\t%s\\n' 'gemini-3.8-flash-medium' 'Gemini 3.8 Flash (Medium)'
  exit 0
fi
while [ "$#" -gt 0 ]; do
  if [ "$1" = --log-file ]; then
    shift
    printf '%s\\n' 'Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"' > "$1"
  fi
  shift
done
cat '{env}'
''', encoding="utf-8")
    exe.chmod(0o755)

    def draft_call(p):
        U.emit_broker("gemma4:e4b", {"in": 300, "out": 40})
        return "나눗셈이 0 이다."

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bindir}{os.pathsep}{old_path}"
    old_agy_state = os.environ.get("AX_AGY_STATE_PATH")
    os.environ["AX_AGY_STATE_PATH"] = str(Path(root) / "agy-state.json")
    try:
        r = R.run_once(paths, draft_call=draft_call)
    finally:
        os.environ["PATH"] = old_path
        if old_agy_state is None:
            os.environ.pop("AX_AGY_STATE_PATH", None)
        else:
            os.environ["AX_AGY_STATE_PATH"] = old_agy_state
    check("⑬ 기본 퇴고 경로로 done", r.state == "done" and bool(r.written), f"{r.state} {r.why}")
    rows = [json.loads(x) for x in paths.usage_log.read_text(encoding="utf-8").splitlines()] \
        if paths.usage_log.is_file() else []
    lanes = [(x.get("lane"), x.get("source"), x.get("task_id")) for x in rows]
    check("⑬ 초고·퇴고 두 줄", lanes == [("local:gemma4:e4b", "review", head[:12]),
                                       ("agy", "review", head[:12])], str(lanes))
    fin = rows[-1] if rows else {}
    check("⑬ 퇴고 토큰이 실린다", fin.get("measured") is True and
          (fin.get("input_tokens"), fin.get("output_tokens")) == (900, 120), str(fin))
    shutil.rmtree(root)


def test_grounding_머리말():
    g = R.grounding_text("초고다", "class AFoo;")
    check("⑩ 미검증이라고 먼저 말한다", "미검증" in g and "버려라" in g, g[:90])
    check("⑩ 선언부는 실측으로 구분한다", "실측" in g, g[:90])
    check("⑩ 둘 다 비면 빈 문자열", R.grounding_text("", "") == "")


def make_merge_repo():
    """`#744` ① — 실제 git 저장소에 깨끗한 머지 · 충돌 해소 머지 · 주석만 해소한 머지 · 루트."""
    root = Path(tempfile.mkdtemp(prefix="ax-run-744-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    git(repo.parent, "init", "-q", "-b", "main", str(repo))
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    a, b = repo / "Source" / "M" / "A.cpp", repo / "Source" / "M" / "B.cpp"
    body = "".join(f"int v{i} = {i};\n" for i in range(1, 11))
    a.write_text(body, encoding="utf-8")
    b.write_text(body + "// note\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "root")
    rootc = git(repo, "rev-parse", "HEAD").stdout.strip()

    def commit_on(branch, path, old, new, msg):
        git(repo, "checkout", "-q", branch)
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        git(repo, "commit", "-qam", msg)

    git(repo, "branch", "side")
    commit_on("side", b, "int v2 = 2;", "int v2 = 2 / 0;", "side: B")
    commit_on("main", a, "int v9 = 9;", "int v9 = 99;", "main: A")
    git(repo, "merge", "-q", "--no-ff", "--no-edit", "side")
    clean = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "branch", "side2")
    commit_on("side2", a, "int v5 = 5;", "int v5 = 50;", "side2: A")
    commit_on("main", a, "int v5 = 5;", "int v5 = 500;", "main: A conflict")
    git(repo, "merge", "-q", "--no-edit", "side2")            # 충돌 — 손으로 해소한다
    text = a.read_text(encoding="utf-8")
    head, rest = text.split("<<<<<<<", 1)
    tail = rest.split(">>>>>>> side2\n", 1)[1]
    a.write_text(head + "int v5 = 5 / 0;  // 해소\n" + tail, encoding="utf-8")
    git(repo, "commit", "-qam", "merge side2 (resolved)")
    conflict = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "branch", "side3")
    commit_on("side3", b, "// note", "// side note", "side3: B 주석")
    commit_on("main", b, "// note", "// main note", "main: B 주석 충돌")
    git(repo, "merge", "-q", "--no-edit", "side3")
    text = b.read_text(encoding="utf-8")
    head, rest = text.split("<<<<<<<", 1)
    tail = rest.split(">>>>>>> side3\n", 1)[1]
    b.write_text(head + "// both note\n" + tail, encoding="utf-8")   # 주석끼리의 충돌을 주석으로 해소
    git(repo, "commit", "-qam", "merge side3 (comment only)")
    comment = git(repo, "rev-parse", "HEAD").stdout.strip()
    return root, {"root": rootc, "clean": clean, "conflict": conflict, "comment": comment}


def test_머지는_결합_diff로_가른다():
    root, c = make_merge_repo()
    repo = Path(root) / "repo"
    files = ["Source/M/A.cpp", "Source/M/B.cpp"]
    check("#744 부모 수 — 루트 0 · 머지 2", RG.parent_count(repo, c["root"]) == 0
          and RG.parent_count(repo, c["clean"]) == 2)
    check("#744 부모를 못 읽으면 -1 (머지로 새지 않는다)", RG.parent_count(repo, "0" * 40) == -1)
    check("#744 루트 커밋은 일반 diff 로 리뷰 재료가 나온다",
          "int v1 = 1;" in RG.commit_diff(repo, files, c["root"]))
    check("#744 깨끗한 머지의 결합 diff 는 비어 있다", RG.commit_diff(repo, files, c["clean"]) == ""
          and RG.is_clean_merge(repo, files, c["clean"]))
    check("#744 충돌 해소 머지·루트는 깨끗한 머지가 아니다",
          not RG.is_clean_merge(repo, files, c["conflict"])
          and not RG.is_clean_merge(repo, files, c["root"]))
    orig = RG._show_diff
    RG._show_diff = lambda *a, **k: (128, "")
    try:
        check("[주의] #744 git 이 결합 diff 를 못 읽으면 깨끗한 머지로 접지 않는다",
              not RG.is_clean_merge(repo, files, c["clean"]))
    finally:
        RG._show_diff = orig
    d = RG.commit_diff(repo, files, c["conflict"])
    check("#744 충돌 해소 머지는 해소분만 + 결합 diff 머리말",
          d.startswith(RG.MERGE_DIFF_HEADER) and "5 / 0" in d and "v2 = 2 / 0" not in d, d[:300])
    check("#744 주석만으로 해소한 머지는 trivial (줄 머리가 부모 수만큼의 열)",
          RG.is_trivial_diff(repo, ["Source/M/B.cpp"], c["comment"]))
    check("#744 코드로 해소한 머지는 trivial 이 아니다",
          not RG.is_trivial_diff(repo, ["Source/M/A.cpp"], c["conflict"]))

    # ── 큐 소비자: 깨끗한 머지 → done(스킵) · 모델 호출 0 ──
    Q.enqueue(root, key=c["clean"], files=files)
    logs, calls = [], []
    r = R.run_once(Paths(root), draft_call=lambda p: calls.append(p) or "안 불린다",
                   review_call=lambda p: calls.append(p) or _review_body(), logf=logs.append)
    it = [x for x in Q.items(root) if x["key"] == c["clean"]][0]
    check("🔴 #744 깨끗한 머지는 done — 「diff 를 읽지 못했다」로 포기하지 않는다",
          r.state == "done" and it["state"] == "done", f"{r.state} {it['state']}")
    check("#744 스킵 사유가 큐에 남는다", RG.MERGE_SKIP_NOTE in str(it.get("note", "")) or
          RG.MERGE_SKIP_NOTE in str(it), str(it)[:300])
    check("#744 모델을 부르지 않는다", calls == [], str(len(calls)))
    check("#744 어느 갈래였는지 로그에 남긴다",
          any("머지" in m and "스킵" in m for m in logs), str(logs))

    # ── 충돌 해소 머지 → 해소분만 리뷰 ──
    Q.enqueue(root, key=c["conflict"], files=files)
    logs, drafts, finals = [], [], []
    r = R.run_once(Paths(root), draft_call=lambda p: drafts.append(p) or "해소 줄이 0 으로 나눈다",
                   review_call=lambda p: finals.append(p) or _review_body(), logf=logs.append)
    check("🔴 #744 충돌 해소 머지는 리뷰한다", r.state == "done" and len(finals) == 1,
          f"{r.state} {r.why} {len(finals)}")
    check("#744 리뷰 재료는 해소분뿐이다 (옆 브랜치 변경은 조각 커밋의 몫)",
          finals and "5 / 0" in finals[0] and "v2 = 2 / 0" not in finals[0]
          and RG.MERGE_DIFF_HEADER in finals[0])
    check("#744 초고도 같은 결합 diff 를 받는다", drafts and RG.MERGE_DIFF_HEADER in drafts[0])
    check("#744 리뷰 갈래가 로그에 남는다", any("머지 안 변경만 리뷰" in m for m in logs), str(logs))

    # ── 주석만 해소 → trivial 스킵 ──
    Q.enqueue(root, key=c["comment"], files=["Source/M/B.cpp"])
    r = R.run_once(Paths(root), draft_call=lambda p: "안 불린다")
    check("#744 주석만 해소한 머지는 trivial 스킵", r.state == "done" and r.why == "trivial", r.why)

    # ── review_gen 직접 경로도 같은 판정 ──
    rv = RG.review_commit(Paths(root), c["clean"], files, chat=lambda p: "안 불린다")
    check("#744 review_commit 도 깨끗한 머지를 스킵으로 돌려준다",
          rv.skipped and not rv.error and "머지" in rv.skipped, f"{rv.skipped} {rv.error}")
    shutil.rmtree(root)


def test_시간예산과_주인없는_running_회수():
    """🔴 #749 — 남은 시간이 한 건 최악보다 적으면 꺼내지 않고, main 은 죽은 회차의 running 을 회수한다."""
    import os
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    logs, calls = [], []
    now = [1000.0]
    out = R.drain(Paths(root), limit=5, logf=logs.append, deadline=now[0] + R.ITEM_WORST - 1,
                  clock=lambda: now[0], draft_call=lambda p: calls.append(p) or "초안")
    check("#749 예산이 모자라면 꺼내지 않는다", out == [] and Q.counts(root)["pending"] == 1
          and not calls, str(Q.counts(root)))
    check("#749 예산 판단을 로그에 남긴다", any("시간 예산" in m for m in logs), str(logs))
    shutil.rmtree(root)

    # main(): 지난 회차가 죽어 running 이 남았다 → 회수 → 같은 회차에서 리뷰
    root, head = make_repo()
    projects = Path(tempfile.mkdtemp(prefix="ax-reg-"))
    (projects / "projects.yaml").write_text(
        "version: 1\nactive: T\nprojects:\n  - T\n", encoding="utf-8")
    twin = projects / "T"
    twin.mkdir()
    (twin / "config.yaml").write_text(
        "version: 1\nname: T\nrepo:\n  local_clone: repo\n", encoding="utf-8")
    shutil.copytree(Path(root) / "repo", twin / "repo")
    Q.enqueue(twin, key=head, files=["Source/M/A.cpp"])
    Q.claim(twin)                                              # 지난 회차가 꺼낸 뒤 죽었다
    old_env = os.environ.get("AX_PROJECTS_ROOT")
    os.environ["AX_PROJECTS_ROOT"] = str(projects)
    orig_draft, orig_agy = R.draft, R.agy_only
    R.draft = lambda *a, **kw: ("나눗셈이 0 이다.", "")
    R.agy_only = lambda _p, **_kw: _review_body()
    try:
        rc = R.main(["--limit", "1"])
        it = Q.items(twin)[0]
        check("🔴 #749 main 이 주인 없는 running 을 회수해 끝낸다",
              rc == 0 and it["state"] == "done" and it["attempts"] == 2, str(it["state"]))
        check("#749 회수 이력이 남는다",
              any(h.get("why") == Q.ORPHAN_WHY for h in it["history"]), str(it["history"]))
        Q.enqueue(twin, key="f" * 40, files=["Source/M/A.cpp"])
        with Q.consumer_lock(twin) as held:                    # 살아 있는 소비자가 있다
            rc = R.main(["--limit", "1"])
        check("#749 다른 소비자가 돌면 건너뛴다(건드리지 않는다)",
              held and rc == 0 and Q.counts(twin)["pending"] == 1, str(Q.counts(twin)))
    finally:
        R.draft, R.agy_only = orig_draft, orig_agy
        if old_env is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old_env
    shutil.rmtree(root); shutil.rmtree(projects)


def make_piece_repo():
    """골조(`[PSEUDO]`) → 조각 커밋이 그 줄을 지우고 본문을 쓴다 — 실제 조각 커밋의 모양."""
    root = Path(tempfile.mkdtemp(prefix="ax-run-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    git(repo.parent, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    (repo / "Source" / "M" / "A.h").write_text("class AFoo {\npublic:\n  bool Bar();\n};\n",
                                              encoding="utf-8")
    (repo / "Source" / "M" / "A.cpp").write_text(
        "bool AFoo::Bar() {\n  // [PSEUDO] 실패하면 false 를 돌려준다\n  return false;\n}\n",
        encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "골조")
    (repo / "Source" / "M" / "A.cpp").write_text(
        "bool AFoo::Bar() {\n  int x = 1;\n  return true;\n}\n", encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "[task:t1] worker=w target=A.cpp")
    return root, git(repo, "rev-parse", "HEAD").stdout.strip()


def _intent_body(rows=""):
    return (_review_body().rstrip() + "\n\n## 4. 골조 지시 이행\n" + RG._INTENT_HEADER
            + "\n|---|---|---|---|---|\n" + rows)


def test_골조_지시_이행_절():
    import hashlib
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,1 @@\n-import json, os\n+import os\n"
    gold = {"unreal": "78960881fa44da5b60af7c7b737ddc0a29accc01fe8338ec8d6eb1012cc0ac34",
            "code": "d23ce97100d29b8662bc06f629a7644e4e194119d42a3fb514b1a7dcf6da0dcf"}
    for kind, h in gold.items():
        seen = []
        R.draft(diff, "decl", call=lambda p: seen.append(p) or "없음", kind=kind)
        check(f"⑭ [중요] intent 없는 초고 프롬프트는 종전과 바이트 단위로 같다 ({kind})",
              hashlib.sha256(seen[0].encode()).hexdigest() == h)
        seen2 = []
        R.draft(diff, "decl", call=lambda p: seen2.append(p) or "없음", kind=kind, intent=True)
        check(f"⑭ intent 초고는 지시 대조를 덧붙인다 ({kind})",
              seen2[0] == seen[0] + R.DRAFT_INTENT and "표를 만들지 마라" in seen2[0])

    root, head = make_piece_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    drafts, finals, logs = [], [], []
    row = "| Source/M/A.cpp | 실패하면 false 를 돌려준다 | 늘 true 를 돌려준다 | 3 | 불이행 |\n"
    r = R.run_once(Paths(root), draft_call=lambda p: drafts.append(p) or "없음",
                   review_call=lambda p: finals.append(p) or _intent_body(row),
                   logf=logs.append)
    check("⑭ 초고 프롬프트가 지시 대조를 싣는다", drafts and R.DRAFT_INTENT in drafts[0])
    check("⑭ 퇴고 프롬프트가 4절을 싣는다",
          finals and "## 4. 골조 지시 이행" in finals[0] and RG._INTENT_HEADER in finals[0])
    check("⑭ 요청 로그 한 줄", sum("골조 지시 이행 절 요청" in m for m in logs) == 1, str(logs))
    check("⑭ 4절 있는 퇴고는 done", r.state == "done" and bool(r.written), r.why)
    from master.context_synth import fix_index as F
    items = F.get_doc(root, r.serial)["items_detail"] if r.serial else []
    check("⑭ 4절 행이 R 항목이 된다 (안전성 1 + 지시 이행 1)",
          [i["category"] for i in items] == ["safety", "intent"], str(items))
    shutil.rmtree(root)

    root, head = make_piece_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    r = R.run_once(Paths(root), draft_call=lambda p: "없음",
                   review_call=lambda p: _review_body())
    check("⑭ [중요] 4절을 요청했는데 빠지면 fail-closed — 큐 실패 + _rejected 보존",
          r.state == "failed" and "형식 위반" in r.why
          and list((Path(root) / "reviews" / "_rejected").glob("*.md")), r.why)
    shutil.rmtree(root)

    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    drafts, finals = [], []
    r = R.run_once(Paths(root), draft_call=lambda p: drafts.append(p) or "없음",
                   review_call=lambda p: finals.append(p) or _review_body())
    check("⑭ [중요] [PSEUDO] 없는 커밋은 둘 다 4절 없이 종전대로 done",
          R.DRAFT_INTENT not in drafts[0] and "## 4. 골조 지시 이행" not in finals[0]
          and r.state == "done")
    shutil.rmtree(root)


if __name__ == "__main__":
    for fn in (test_로컬뒤_antigravity가_퇴고한다,
               test_로컬_없음이어도_antigravity가_본다,
               test_초안_실패여도_antigravity가_마무리한다,
               test_기존_초안_재사용과_실패_보존,
               test_diff를_못_읽으면_결정적이다,
               test_설계된_스킵, test_선언부, test_main_이_실제로_돈다,
               test_퇴고도_사용량에_남는다, test_grounding_머리말,
               test_머지는_결합_diff로_가른다, test_시간예산과_주인없는_running_회수,
               test_골조_지시_이행_절):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
