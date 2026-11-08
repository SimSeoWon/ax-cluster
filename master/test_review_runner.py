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
    ⑮ 기본 퇴고는 빈 임시 디렉터리에서 돈다 — 원본 트리에 아무것도 안 남는다 (`#844`·`#888`)
    ⑯ agy 쿨다운은 시도를 소비하지 않고, 그 회차는 다음 항목을 꺼내지 않는다 (`#847`)
    ⑱ 퇴고는 자르지 않은 diff, 초고는 24,000자 상한 diff (`#888`)
    ⑲ 한 건 최악·회차 예산·유닛 TimeoutStartSec 이 맞물린다 (`#888`)

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

from master import issue_lock as IL                                # noqa: E402
from master.context_synth import issue_track as IT                # noqa: E402
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


def _patched_reviewers(calls, *, codex=None):
    """기본 경로(`review_call` 없음)를 타며 실제 CLI 대신 어느 리뷰어가 불렸는지만 적는다."""
    orig = R.draft, R.agy_only, R.codex_only
    R.draft = lambda *a, **kw: ("초안", "")
    R.agy_only = lambda _p, **kw: calls.append(("agy", kw)) or _review_body()
    R.codex_only = codex or (lambda _p, **kw: calls.append(("codex", kw)) or _review_body())
    return orig


def _restore_reviewers(orig):
    R.draft, R.agy_only, R.codex_only = orig


def test_antigravity_작성분은_codex가_본다():
    root, head = make_repo()
    IT.register(root, 5, project="P", base="a" * 40, end=head, hashes=[head], authors=["agy"])
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls, lines = [], []
    orig = _patched_reviewers(calls)
    try:
        r = R.run_once(Paths(root), logf=lines.append)
    finally:
        _restore_reviewers(orig)
    check("#920 Antigravity 작성분 → Codex 한 번", [c[0] for c in calls] == ["codex"], str(calls))
    check("#920 빈 작업 디렉터리·한도 전달", calls[0][1].get("workdir") and calls[0][1].get("timeout") == R.COMMIT_REVIEW_TIMEOUT,
          str(calls[0][1]))
    check("#920 로그에 리뷰어", any("리뷰어 Codex" in x and "agy" in x for x in lines), str(lines)[:400])
    check("#920 리뷰 출처 Codex", r.written and "Codex" in Path(r.written).read_text(encoding="utf-8"), r.written)


def test_마감_등록_전에도_잠금으로_가른다():
    """push 뒤 등록 전에 큐가 집는 틈 — 활성 잠금의 계열이 덮는다."""
    root, head = make_repo()
    IL.acquire(root, 5, branch="issue/5", start_rev="a" * 40)
    IL.note_author(root, 5, "agy")
    check("#920 등록 전 — 잠금의 계열", R.commit_authors(root, head, lambda m: None) == ("agy",))
    IL.release(root, 5, op="cancel")
    check("#920 잠금도 없으면 미상", R.commit_authors(root, head, lambda m: None) == ())
    check("#920 미상은 agy", R.reviewer_for(()) == "agy")


def test_다른_계열은_agy_그대로():
    for authors in (["claude"], ["codex"], ["unknown"], []):
        root, head = make_repo()
        IT.register(root, 5, project="P", base="a" * 40, end=head, hashes=[head], authors=authors)
        Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
        calls = []
        orig = _patched_reviewers(calls)
        try:
            R.run_once(Paths(root))
        finally:
            _restore_reviewers(orig)
        check(f"#920 작성 {authors or '없음'} → agy 그대로", [c[0] for c in calls] == ["agy"], str(calls))


def test_codex_실패는_폴백하지_않는다():
    root, head = make_repo()
    IT.register(root, 5, project="P", base="a" * 40, end=head, hashes=[head], authors=["agy"])
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls = []

    def boom(_p, **_kw):
        calls.append(("codex", {}))
        raise RG.ReviewChatError("Codex 실패 — 한도")
    orig = _patched_reviewers(calls, codex=boom)
    try:
        r = R.run_once(Paths(root))
    finally:
        _restore_reviewers(orig)
    check("#920 Codex 실패 — 다른 리뷰어를 부르지 않는다", [c[0] for c in calls] == ["codex"], str(calls))
    check("#920 Codex 실패 — 항목은 성공이 아니다", r.state != "done", r.state)


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


def test_퇴고는_빈_디렉터리에서_돈다():
    """⑮ `#844`·`#888` — 커밋 리뷰 agy 는 라이브 트리도 고정 트리도 아닌 **빈 임시 디렉터리**에서 돈다.

    `#844`: agy 가 원본 트리에서 명령을 돌려 `.mypy_cache/` 를 남겼다(실측 2026-10-30).
    `#888`: 고정 트리를 주면 도구 호출 20–37회로 탐색하다 시간 초과 — 빈 디렉터리면 4–6회.
    workdir 는 None 이 아니고, 저장소 밖이며, 끝나면 사라진다. 한도는 `COMMIT_REVIEW_TIMEOUT`.
    """
    root, head = make_repo()
    repo = Path(root) / "repo"
    before = git(repo, "status", "--porcelain").stdout
    wt_before = git(repo, "worktree", "list").stdout
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    seen = {}

    def fake_agy(prompt, *, workdir=None, timeout=None, **kw):
        wd = Path(workdir)
        seen.update(wd=wd, listing=sorted(x.name for x in wd.iterdir()), timeout=timeout,
                    wt=git(repo, "worktree", "list").stdout)
        (wd / ".mypy_cache").mkdir()                       # 에이전트의 셸 산출물 흉내
        (wd / ".mypy_cache" / "x.json").write_text("{}")
        return _review_body()
    orig, R.agy_only = R.agy_only, fake_agy
    logs = []
    try:
        r = R.run_once(Paths(root), draft_call=lambda p: "없음", logf=logs.append)
    finally:
        R.agy_only = orig
    wd = seen.get("wd")
    check("⑮ done", r.state == "done", f"{r.state} {r.why}")
    check("⑮ workdir 를 받았다(None 아님)", wd is not None)
    check("⑮ #888 빈 디렉터리다", seen.get("listing") == [], str(seen.get("listing")))
    check("⑮ 저장소 밖이다", wd is not None and not str(wd).startswith(str(root)), str(wd))
    check("⑮ #888 고정 트리를 만들지 않는다", seen.get("wt") == wt_before, str(seen.get("wt")))
    check("⑮ #888 한도는 커밋 리뷰 한도(480)", seen.get("timeout") == R.COMMIT_REVIEW_TIMEOUT == 480,
          str(seen.get("timeout")))
    check("⑮ 끝나면 디렉터리가 사라진다", wd is not None and not wd.exists(), str(wd))
    check("⑮ 🔴 원본 트리는 그대로다", git(repo, "status", "--porcelain").stdout == before
          and not (repo / ".mypy_cache").exists())
    check("⑮ 작업 디렉터리를 로그로 드러낸다",
          any("빈 디렉터리" in x and "480초" in x for x in logs), str(logs))
    shutil.rmtree(root)


def test_빈_디렉터리_실패는_실패다():
    """⑮ 빈 디렉터리를 못 만들면 workdir=None(라이브 트리)으로 가지 않고 실패로 끝낸다."""
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    calls = []
    orig_agy, R.agy_only = R.agy_only, lambda p, **kw: calls.append(kw) or _review_body()
    import tempfile as TF
    orig_td = TF.TemporaryDirectory

    def boom(*a, **kw):
        raise OSError("흉내 — 디스크 없음")
    TF.TemporaryDirectory = boom
    try:
        r = R.run_once(Paths(root), draft_call=lambda p: "없음")
    finally:
        R.agy_only, TF.TemporaryDirectory = orig_agy, orig_td
    check("⑮ 디렉터리 실패면 failed", r.state == "failed" and "빈 작업 디렉터리" in r.why,
          f"{r.state} {r.why}")
    check("⑮ agy 를 부르지 않았다", calls == [], str(calls))
    shutil.rmtree(root)


def make_big_repo():
    """`#888` — 24,000자를 넘는 diff 커밋."""
    root, _ = make_repo()
    repo = Path(root) / "repo"
    big = "void AFoo::Bar() {\n" + "".join(f"  int v{i} = {i};\n" for i in range(3000)) + "}\n"
    (repo / "Source" / "M" / "A.cpp").write_text(big, encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "big")
    return root, git(repo, "rev-parse", "HEAD").stdout.strip()


def test_퇴고는_온전한_diff_초고는_잘린_diff():
    """⑱ `#888` — agy 퇴고 프롬프트는 자르지 않은 diff, 로컬 초고는 종전 24,000자 상한.

    하트비트 요약의 잘림 표시도 커밋 리뷰에서 `diff 온전` 이 된다.
    """
    from master import layer2_verify as L2
    root, head = make_big_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    drafts, seen = [], []

    def fake_call(prompt, **kw):
        seen.append((prompt, kw))
        return _review_body(), ""
    orig, L2.call_agy_why = L2.call_agy_why, fake_call
    try:
        r = R.run_once(Paths(root), draft_call=lambda p: drafts.append(p) or "없음",
                       logf=lambda m: None)
    finally:
        L2.call_agy_why = orig
    check("⑱ done", r.state == "done", f"{r.state} {r.why}")
    check("⑱ 초고는 잘린 diff", drafts and "(diff 가 잘렸다" in drafts[0]
          and "int v2999 = 2999;" not in drafts[0])
    prompt, kw = seen[0] if seen else ("", {})
    check("⑱ 퇴고는 온전한 diff", "(diff 가 잘렸다" not in prompt and "int v2999 = 2999;" in prompt)
    check("⑱ 하트비트 요약은 diff 온전", kw.get("heartbeat_note") == "diff 온전",
          str(kw.get("heartbeat_note")))
    check("⑱ call_agy_why 한도 480 · workdir 있음", kw.get("timeout") == 480 and bool(kw.get("workdir")),
          str({k: v for k, v in kw.items() if k in ("timeout", "workdir")}))
    shutil.rmtree(root)


def test_시간_예산은_유닛과_같다():
    """⑲ `#888` — 한 건 최악 = 초고 180 + 퇴고 480 + 60 = 720 < 회차 예산 900 = 유닛 TimeoutStartSec."""
    import re
    check("⑲ ITEM_WORST == 720", R.ITEM_WORST == 720, str(R.ITEM_WORST))
    check("⑲ RUN_BUDGET == 900", R.RUN_BUDGET == 900, str(R.RUN_BUDGET))
    check("⑲ 한 건 최악이 예산 안", R.ITEM_WORST < R.RUN_BUDGET)
    check("⑲ 범위 리뷰 한도도 한 건 최악 안", R.RANGE_REVIEW_TIMEOUT + 60 <= R.ITEM_WORST,
          str(R.RANGE_REVIEW_TIMEOUT))
    check("⑲ 전역 REVIEW_TIMEOUT 은 그대로(다른 호출자 기본값)", RG.REVIEW_TIMEOUT == 240)
    unit = (Path(__file__).resolve().parent / "systemd" / "ax-review-queue.service").read_text(encoding="utf-8")
    m = re.search(r"^TimeoutStartSec=(\d+)", unit, re.M)
    check("⑲ 유닛 TimeoutStartSec == RUN_BUDGET", bool(m) and int(m.group(1)) == R.RUN_BUDGET,
          m.group(0) if m else "없음")


def test_쿨다운은_시도를_쓰지_않고_회차를_멈춘다():
    """⑯ `#847` 실측 — 쿨다운 중 2/3·3/3 이 같은 초에 소진돼 포기됐다(2026-10-30 18:29:23)."""
    root, head = make_repo()
    repo = Path(root) / "repo"
    first = git(repo, "rev-parse", "HEAD~1").stdout.strip()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    Q.enqueue(root, key=first, files=["Source/M/A.cpp"])
    calls, logs = [], []

    def cooled(p):
        calls.append(1)
        raise RG.ReviewChatError("Antigravity 실패 — gemini-3.8-flash-medium: model cooldown 237s")
    out = R.drain(Paths(root), limit=5, logf=logs.append,
                  draft_call=lambda p: "없음", review_call=cooled)
    its = {it["key"]: it for it in Q.items(root)}
    check("⑯ 한 건만 처리하고 멈춘다", len(out) == 1 and len(calls) == 1, f"{len(out)} {len(calls)}")
    check("⑯ 시도를 소비하지 않는다", its[head]["attempts"] == 0 and its[head]["state"] == "pending",
          str(its[head]))
    check("⑯ 다음 항목은 손대지 않았다", its[first]["attempts"] == 0 and its[first]["state"] == "pending")
    check("⑯ 회차 중단을 로그에 남긴다", any("회차 중단" in x for x in logs), str(logs[-3:]))
    # 쿨다운이 아닌 실패는 종전대로 다음 항목으로 넘어간다
    calls.clear()
    out = R.drain(Paths(root), limit=5, draft_call=lambda p: "없음",
                  review_call=lambda p: (_ for _ in ()).throw(RG.ReviewChatError("연결 끊김")))
    check("⑯ 일반 실패는 회차를 멈추지 않는다", len(out) >= 2, str(len(out)))
    shutil.rmtree(root)


def test_종합_리뷰_회차_기록이_없으면_실패다():
    """`#884` T4 — meta track 인데 마감 회차 기록이 없으면 해시 지적 없이 리뷰하지 않는다(모델 0)."""
    root = Path(tempfile.mkdtemp(prefix="ax-rr-track-"))
    b, e = "a" * 40, "b" * 40
    Q.enqueue(root, kind="range", key=f"{b}..{e}", files=[], priority=10,
              meta={"issue_id": 884, "base": b, "end": e, "issue_round": 1, "track": True})
    calls, logs = [], []
    r = R.run_once(Paths(root), logf=logs.append, range_noter=lambda *a, **k: "x",
                   review_call=lambda p, **kw: calls.append(p) or "x")
    it = Q.items(root)[0]
    check("T4 회차 기록 없음 → failed · 모델 0", r.state == "failed" and not calls
          and "마감 회차 기록" in r.why and it["state"] == "pending", f"{r.state} {r.why} {it['state']}")
    txt = R.track_note_text(Paths(root), it)
    check("T4 노트 회차 절 — 기록 없음을 적는다", txt.startswith("[주의] 마감 회차 기록이 없다"), txt)
    # 옛(track 없는) 범위 항목의 노트에는 회차 절이 없다
    legacy = {"meta": {"issue_id": 1, "base": b, "end": e}, "history": [{"result": "done", "note": "스킵: 소스 변경 없음"}]}
    lt = R.range_note_text(Paths(root), legacy)
    check("T4 옛 범위 노트는 종전 그대로", lt == f"자동 범위 리뷰 완료: `{b[:12]}..{e[:12]}` — 스킵: 소스 변경 없음", lt)
    shutil.rmtree(root)


def test_agy_하트비트_배선():
    """⑰ `#888` — `agy_only(log=)` 는 하트비트·요약을 켜고 diff 잘림 여부를 요약에 싣는다.

    `log` 가 없으면 `call_agy_why` 에 새 인자를 하나도 넘기지 않는다(종전 그대로).
    기본 퇴고 경로(`review_call=None`)는 커밋·범위 두 자리 모두 큐의 로그 함수를 넘긴다.
    """
    import inspect
    from master import layer2_verify as L2
    seen = []

    def fake(prompt, **kw):
        seen.append(kw)
        if "heartbeat" in kw:
            kw["heartbeat"]("[agy 하트비트] 경과 20초 · 턴 1")
        return _review_body(), ""
    orig, L2.call_agy_why = L2.call_agy_why, fake
    logs = []
    try:
        R.agy_only("본문", timeout=9)
        R.agy_only("본문", timeout=9, workdir="/w", log=logs.append)
        cut = "diff\n... (diff 가 잘렸다 — 여기까지만 리뷰 대상이다)"
        R.agy_only(cut, log=logs.append)
    finally:
        L2.call_agy_why = orig
    check("⑰ log 없음 → 새 인자 없음", seen[0] == {"timeout": 9}, str(seen[0]))
    check("⑰ log 있음 → heartbeat·note", callable(seen[1].get("heartbeat"))
          and seen[1].get("heartbeat_note") == "diff 온전" and seen[1].get("workdir") == "/w",
          str(seen[1]))
    check("⑰ 잘린 diff 를 표시한다", seen[2].get("heartbeat_note") == "diff 잘림", str(seen[2]))
    check("⑰ 하트비트는 큐 로그로 간다(접두 포함)",
          logs and logs[0] == "[리뷰큐] [agy 하트비트] 경과 20초 · 턴 1", str(logs))
    check("⑰ 잘림 판정은 review_gen 꼬리와 같은 글", R.DIFF_TRUNCATED_MARK in inspect.getsource(RG.commit_diff))
    # `#888` T7 — diff 본문 줄에 같은 글이 들어 있어도 잘림이 아니다(68f1568 오표시)
    body = ('+    check("x", "(diff 가 잘렸다" in capped)\n'
            '         d = d[:max_chars] + "\\n... (diff 가 잘렸다 — 여기까지만 리뷰 대상이다)"\n'
            '-    "(diff 가 잘렸다"\n')
    check("⑰ 본문 줄의 꼬리 글은 잘림이 아니다", R.diff_truncation_note(body) == "diff 온전",
          R.diff_truncation_note(body))
    check("⑰ 줄 머리 꼬리 + 뒤 프롬프트 → 잘림",
          R.diff_truncation_note(body + "... (diff 가 잘렸다 — 여기까지만 리뷰 대상이다)\n\n## 규칙\n")
          == "diff 잘림")

    # 기본 커밋 리뷰 경로가 실제로 log 를 넘긴다
    root, head = make_repo()
    Q.enqueue(root, key=head, files=["Source/M/A.cpp"])
    got = {}

    def fake_agy(prompt, **kw):
        got.update(kw)
        return _review_body()
    orig_agy, R.agy_only = R.agy_only, fake_agy
    qlogs = []
    try:
        r = R.run_once(Paths(root), draft_call=lambda p: "없음", logf=qlogs.append)
    finally:
        R.agy_only = orig_agy
    check("⑰ 커밋 리뷰 done", r.state == "done", f"{r.state} {r.why}")
    lg = got.get("log")
    check("⑰ 커밋 리뷰 경로가 log 를 넘긴다", callable(lg), str(got))
    if callable(lg):
        lg("표지")
        check("⑰ 그 log 는 큐 로그다", "표지" in qlogs, str(qlogs[-3:]))
    shutil.rmtree(root)
    # 범위 리뷰 자리 — 기본 경로는 유닛이 타지 않으므로 배선 문장을 직접 본다
    src = inspect.getsource(R.run_range)
    check("⑰ 범위 리뷰 경로가 _ask 에 log 를 넘긴다", "_ask(reviewer, workdir=tree, log=log" in src)
    seen = {}
    keep_agy, keep_codex = R.agy_only, R.codex_only
    R.agy_only = lambda _p, **kw: seen.update(agy=kw.get("log")) or "x"
    R.codex_only = lambda _p, **kw: seen.update(codex=kw.get("log")) or "x"
    try:
        marker = lambda m: None                                   # noqa: E731
        R._ask("agy", workdir="/w", log=marker, timeout=1)("p")
        R._ask("codex", workdir="/w", log=marker, timeout=1)("p")
    finally:
        R.agy_only, R.codex_only = keep_agy, keep_codex
    check("⑰ _ask 가 두 리뷰어 모두에 그 log 를 넘긴다",
          seen.get("agy") is marker and seen.get("codex") is marker, str(seen))


if __name__ == "__main__":
    for fn in (test_로컬뒤_antigravity가_퇴고한다,
               test_로컬_없음이어도_antigravity가_본다,
               test_초안_실패여도_antigravity가_마무리한다,
               test_기존_초안_재사용과_실패_보존,
               test_diff를_못_읽으면_결정적이다,
               test_설계된_스킵, test_선언부, test_main_이_실제로_돈다,
               test_퇴고도_사용량에_남는다, test_grounding_머리말,
               test_머지는_결합_diff로_가른다, test_시간예산과_주인없는_running_회수,
               test_골조_지시_이행_절, test_퇴고는_빈_디렉터리에서_돈다,
               test_빈_디렉터리_실패는_실패다,
               test_퇴고는_온전한_diff_초고는_잘린_diff, test_시간_예산은_유닛과_같다,
               test_쿨다운은_시도를_쓰지_않고_회차를_멈춘다,
               test_종합_리뷰_회차_기록이_없으면_실패다,
               test_agy_하트비트_배선, test_antigravity_작성분은_codex가_본다,
               test_마감_등록_전에도_잠금으로_가른다, test_다른_계열은_agy_그대로,
               test_codex_실패는_폴백하지_않는다):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
