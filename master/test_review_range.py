"""일감 범위 리뷰(`#879` T2) — 큐 `kind=range` · 합친 diff · 게시판 번호 · 주간 플랜 제외.

검증하는 것:

    ① range 등재는 key=<시작>..<끝> 과 meta(issue_id·base·end) 가 맞아야 한다
    ② 소비자가 **시작~끝 합친 diff** 를 한 번 리뷰한다 (중간 커밋 변경까지 들어간다)
    ③ 결과는 `reviews/_range/` — 파일명이 `*_<끝8>.md` 로 끝나지 않는다
       (색인기의 「이미 리뷰됨」 glob 과 `find_final_review` 가 커밋 리뷰로 오인하지 않게)
    ④ `fix_index` 가 R 번호를 주고 범위·일감을 싣는다 · 커밋 리뷰 번호와 겹치지 않는다
    ⑤ 주간 플랜 수집(작성자 디렉토리)에 범위 리뷰가 안 들어간다
    ⑥ 재시도 때 이미 게시된 범위 리뷰가 있으면 모델을 다시 부르지 않는다
    ⑦ 범위를 못 읽으면 **결정적** 실패로 1회에 멈춘다
    ⑧ 범위 프롬프트의 대상 이름 · 커밋 프롬프트는 그대로

실 LLM 을 부르지 않는다(review_call 주입). git 은 실제 임시 저장소다.
`.venv/bin/python master/test_review_range.py`
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import fix_index as FX                  # noqa: E402
from master.context_synth import planner as PL                    # noqa: E402
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
        self.usage_log = Path(root) / "usage_log.jsonl"


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def make_repo():
    """init → c1(A.cpp) → c2(B.cpp). 범위 = init..c2."""
    root = Path(tempfile.mkdtemp(prefix="ax-range-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    (repo / "Source" / "M" / "A.h").write_text("class AFoo {\npublic:\n  void Bar();\n};\n")
    (repo / "Source" / "M" / "A.cpp").write_text("void AFoo::Bar() {}\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "init")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "Source" / "M" / "A.cpp").write_text("void AFoo::Bar() {\n  int x = 1 / 0;\n}\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "c1")
    (repo / "Source" / "M" / "B.cpp").write_text("int Baz() { return 42; }\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "c2")
    end = git(repo, "rev-parse", "HEAD").stdout.strip()
    return root, base, end


BODY = """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/A.cpp | 높음 | 2 | 0으로 나눔 | 분모 검사 |

## 3. 영향 분석
런타임 오류 위험.
"""


def enqueue_range(root, base, end, issue=879, files=None):
    return Q.enqueue(root, kind="range", key=f"{base}..{end}", files=files or [],
                     meta={"issue_id": issue, "base": base, "end": end}, requester="test")


def test_enqueue_contract():
    root, base, end = make_repo()
    for name, kw in (("meta 없음", {}),
                     ("issue 없음", {"meta": {"base": base, "end": end}}),
                     ("key 와 meta 불일치", {"meta": {"issue_id": 1, "base": end, "end": base}})):
        try:
            Q.enqueue(root, kind="range", key=f"{base}..{end}", **kw)
            check(f"① {name} → 거절", False)
        except Q.ReviewQueueError:
            check(f"① {name} → 거절", True)
    it = enqueue_range(root, base, end)
    check("① 정상 등재 · meta 보존", it["state"] == "pending" and it["meta"]["issue_id"] == 879, str(it))
    again = enqueue_range(root, base, end)
    check("① 같은 범위 재등재는 그대로", again["id"] == it["id"] and Q.counts(root)["pending"] == 1)
    shutil.rmtree(root)


def test_run_range():
    root, base, end = make_repo()
    enqueue_range(root, base, end)
    calls = []
    r = R.run_once(Paths(root), review_call=lambda p, **kw: calls.append(p) or BODY)
    check("② 한 번 부른다", len(calls) == 1, str(len(calls)))
    p = calls[0] if calls else ""
    check("② 합친 diff — 두 커밋의 변경이 다 있다", "1 / 0" in p and "return 42" in p)
    check("⑧ 대상 이름이 범위다", f"일감 #879 범위 {base[:12]}..{end[:12]} (커밋 2건)" in p
          and "아래 범위(여러 커밋을 합친 diff)의" in p, p[:200])
    check("⑧ 선언부 근거가 실린다", "선언부" in p and "AFoo" in p)
    check("② done", r is not None and r.state == "done" and Q.counts(root)["done"] == 1,
          f"{r and r.state} {r and r.why}")
    w = Path(r.written)
    check("③ reviews/_range/ 에 저장", w.parent == Path(root) / "reviews" / "_range" and w.is_file(), str(w))
    check("③ 파일명이 _<끝8>.md 로 끝나지 않는다", not w.name.endswith(f"_{end[:8]}.md")
          and w.name.endswith(f"_issue879_{base[:8]}-{end[:8]}.md"), w.name)
    check("③ 커밋 리뷰 glob 에 안 걸린다",
          not list((Path(root) / "reviews").glob(f"*/*_{end[:8]}.md")))
    check("③ find_final_review 가 범위 리뷰를 커밋 리뷰로 안 본다",
          R.find_final_review(Paths(root), end) is None)
    text = w.read_text(encoding="utf-8")
    check("③ 머리말 — 범위·일감, 커밋 줄 없음",
          f"- 범위: `{base}..{end}`" in text and "- 일감: #879" in text and "- 커밋:" not in text)
    # ④ 번호
    check("④ R 번호", r.serial.startswith("R"), r.serial)
    doc = FX.get_doc(root, r.serial)
    check("④ get_doc 에 범위·일감", doc.get("ok") and doc.get("range_full") == f"{base}..{end}"
          and doc.get("issue_id") == 879 and doc.get("items") == 1, str({k: doc.get(k) for k in
                                                                         ("ok", "range_full", "issue_id", "items")}))
    check("④ serial_for_range", FX.serial_for_range(root, base, end) == r.serial)
    check("④ serial_for_commit(끝) 은 범위 리뷰가 아니다", FX.serial_for_commit(root, end) == "")
    # 커밋 리뷰가 따로 생겨도 번호가 갈린다
    Q.enqueue(root, key=end, files=["Source/M/B.cpp"])
    rc = R.run_once(Paths(root), draft_call=lambda p: "없음", review_call=lambda p, **kw: BODY)
    check("④ 끝 커밋의 커밋 리뷰도 생긴다(둘 다 유지)", rc.state == "done" and "reviews/테스터/" in rc.written,
          f"{rc.state} {rc.written}")
    check("④ 번호가 겹치지 않는다", rc.serial and rc.serial != r.serial, f"{rc.serial} {r.serial}")
    # ⑤ 주간 플랜
    authors = [d.name for d in PL.list_author_dirs(Path(root) / "reviews")]
    check("⑤ 주간 플랜 작성자 목록에 _range 없음", "_range" not in authors and "테스터" in authors, str(authors))
    # ⑥ 재시도
    Q.enqueue(root, kind="range", key=f"{base}..{end}", files=[],
              meta={"issue_id": 879, "base": base, "end": end})       # done 이면 생략
    data = Q._read(root)
    for it in data["items"]:
        if it["kind"] == "range":
            it["state"] = "pending"
    Q._write(root, data)
    again = []
    r2 = R.run_once(Paths(root), review_call=lambda p, **kw: again.append(p) or BODY)
    check("⑥ 기존 범위 리뷰가 있으면 모델 0회", not again and r2.state == "done", f"{len(again)} {r2.state}")
    shutil.rmtree(root)


def test_bad_range_is_deterministic():
    root, base, end = make_repo()
    bogus = "0" * 40
    Q.enqueue(root, kind="range", key=f"{bogus}..{end}", files=[],
              meta={"issue_id": 879, "base": bogus, "end": end})
    r = R.run_once(Paths(root), review_call=lambda p, **kw: BODY)
    it = [x for x in Q.items(root) if x["kind"] == "range"][0]
    check("⑦ 범위 못 읽음 → failed", r.state == "failed", r.why)
    check("⑦ 결정적 갈래 → 1회에 abandoned", it["last_kind"] == Q.DETERMINISTIC
          and it["state"] == "abandoned", f"{it['last_kind']} {it['state']}")
    shutil.rmtree(root)


def test_end_not_yet_in_mirror_is_transient():
    root, base, end = make_repo()
    missing = "f" * 40
    Q.enqueue(root, kind="range", key=f"{base}..{missing}", files=[],
              meta={"issue_id": 879, "base": base, "end": missing})
    r = R.run_once(Paths(root), review_call=lambda p, **kw: BODY)
    it = [x for x in Q.items(root) if x["kind"] == "range"][0]
    check("⑦ 끝 커밋이 미러에 없음 → 일시적 · pending 으로 재시도", r.state == "failed"
          and it["last_kind"] == Q.TRANSIENT and it["state"] == "pending", f"{it['last_kind']} {it['state']}")
    shutil.rmtree(root)


def test_commit_prompt_unchanged():
    a = RG.build_prompt(diff="d", files=["x"], commit="abc")
    check("⑧ 커밋 프롬프트 — 범위 문구 없음", "여러 커밋을 합친" not in a and "일감 #" not in a and "## 커밋 abc 의 변경 파일" in a
          and "아래 커밋의 **변경분만**" in a)


def main() -> int:
    for fn in (test_enqueue_contract, test_run_range, test_bad_range_is_deterministic,
               test_end_not_yet_in_mirror_is_transient,
               test_commit_prompt_unchanged):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_review_range: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
