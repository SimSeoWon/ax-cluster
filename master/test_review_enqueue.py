"""색인이 리뷰를 큐에 위임한다 (`#635`) — 결함 ⓒⓓ 가 닫혔는지 본다.

검증하는 것:

    ① 등재는 LLM 을 부르지 않는다 — 색인이 기다리지 않는다 (결함 ⓑ)
    ② 🔴 **결함 ⓓ-⑴** — 합성이 이미 끝난 커밋(`todo` 가 빈 회차)도 리뷰가 등재된다
    ③ 🔴 **결함 ⓓ-⑵** — 커밋 **전체** 변경 파일이 실린다 (부분 목록이 아니다)
    ④ 🔴 **결함 ⓒ** — 기존 리뷰가 **형식 위반**이면 다시 등재한다
    ⑤ 기존 리뷰가 정상이면 등재하지 않는다 (커밋당 리뷰 한 번)
    ⑥ 등재 실패는 조용하지 않다 — 카나리 `review-lost`
    ⑦ 요약 줄이 「리뷰 등재로 위임」을 말한다 (저널에서 사라지지 않는다)

`.venv/bin/python master/test_review_enqueue.py`
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.events import consumer as C                           # noqa: E402
from master.context_synth import review_gen as RG                 # noqa: E402

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
        self.canary = Path(root) / "canary" / "permanent_loss.jsonl"


class Res:
    def __init__(self):
        self.to_commit = "abc12345deadbeef"
        self.review_note = ""
        self.review_written = ""
        self.review_serial = ""
        self.review_queued = ""
        self.canary_write_failed = 0


def make_root():
    root = Path(tempfile.mkdtemp(prefix="ax-enq-"))
    (root / "repo").mkdir()
    return root


def write_review(root, commit8, body):
    d = root / RG.REVIEWS_DIRNAME / "Simkung"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"2026-09-19_1200_{commit8}.md"
    f.write_text(body, encoding="utf-8")
    return f


GOOD = ("### Source/NS\n\n## 1. 변경분 코딩 컨벤션\n"
        "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n\n"
        "## 2. 변경분 버그·안전성\n"
        "| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n|---|---|---|---|---|\n")
BAD = "리뷰를 산문으로 썼습니다. 표가 없습니다.\n"


def test_기본_등재():
    root = make_root()
    from master.context_synth import review_queue as Q
    r = Res()
    C._enqueue_review(Paths(root), ["Source/A.cpp", "Source/A.h"], r, commit="abc12345deadbeef")
    items = Q.items(root)
    check("① 등재된다", len(items) == 1 and items[0]["state"] == "pending", str(items))
    check("③ 커밋 전체 파일이 실린다",
          items[0]["files"] == ["Source/A.cpp", "Source/A.h"], str(items[0]["files"]))
    check("⑦ 요약용 필드가 세팅된다", r.review_queued == "abc12345deadbeef", r.review_queued)
    check("note 가 등재를 말한다", "리뷰 큐 등재" in r.review_note, r.review_note)
    shutil.rmtree(root)


def test_LLM을_부르지_않는다():
    """① 등재 경로에 상용 체인이 없다 — 있으면 색인이 240초를 기다린다(결함 ⓑ)."""
    root = make_root()
    called = []
    orig = RG.commercial_chat
    RG.commercial_chat = lambda *a, **kw: called.append(1)
    try:
        C._enqueue_review(Paths(root), ["Source/A.cpp"], Res(), commit="abc12345deadbeef")
    finally:
        RG.commercial_chat = orig
    check("🔴 ① 등재가 상용 체인을 부르지 않는다", not called, str(called))
    shutil.rmtree(root)


def test_기존_리뷰가_정상이면_등재하지_않는다():
    root = make_root()
    from master.context_synth import review_queue as Q
    write_review(root, "abc12345", GOOD)
    r = Res()
    C._enqueue_review(Paths(root), ["Source/A.cpp"], r, commit="abc12345deadbeef")
    check("⑤ 정상 리뷰가 있으면 등재 생략", not Q.items(root), str(Q.items(root)))
    check("⑤ 사유가 남는다", "생략" in r.review_note, r.review_note)
    shutil.rmtree(root)


def test_형식위반_리뷰는_다시_등재한다():
    """🔴 ④ 결함 ⓒ — 종전엔 「파일이 있으면 스킵」이라 형식 위반인 채로 굳었다."""
    root = make_root()
    from master.context_synth import review_queue as Q
    write_review(root, "abc12345", BAD)
    r = Res()
    C._enqueue_review(Paths(root), ["Source/A.cpp"], r, commit="abc12345deadbeef")
    items = Q.items(root)
    check("🔴 ④ 형식 위반이면 다시 등재한다 (결함 ⓒ)",
          len(items) == 1 and items[0]["state"] == "pending", str(items))
    check("④ 사유가 사람에게 말한다", "형식 위반" in r.review_note, r.review_note)
    shutil.rmtree(root)


def test_등재_실패는_카나리다():
    """⑥ 워터마크가 이 뒤에서 전진하므로 등재 실패는 유실이다."""
    root = make_root()

    def boom(*a, **kw):
        raise RuntimeError("큐를 못 썼다")

    r = Res()
    C._enqueue_review(Paths(root), ["Source/A.cpp"], r, commit="abc12345deadbeef",
                      enqueue=boom)
    check("⑥ 사유가 note 에 남는다", "등재 실패" in r.review_note, r.review_note)
    canary = root / "canary" / "permanent_loss.jsonl"
    body = canary.read_text(encoding="utf-8") if canary.is_file() else ""
    check("⑥ 카나리에 review-lost 가 쌓인다", "review-lost" in body, body[:120])
    shutil.rmtree(root)


def test_커밋이_없으면_생략():
    root = make_root()
    from master.context_synth import review_queue as Q
    r = Res()
    r.to_commit = ""
    C._enqueue_review(Paths(root), ["Source/A.cpp"], r, commit="")
    check("커밋 없으면 등재하지 않는다", not Q.items(root))
    check("사유가 남는다", "커밋이 없다" in r.review_note, r.review_note)
    shutil.rmtree(root)


def test_호출부가_todo_밖이고_changed_를_넘긴다():
    """🔴 ② 결함 ⓓ — 소스에 그 구조가 유지되는지 본다.

    [주의] 실물 이벤트를 돌리는 대신 호출부의 **형태**를 고정한다 — 종전 결함이
    「들여쓰기 한 칸」과 「인자 이름 하나」였기 때문이다.
    """
    src = Path(C.__file__).read_text(encoding="utf-8")
    line = next((l for l in src.splitlines() if "_enqueue_review(paths," in l), "")
    check("🔴 ② 호출부가 `if todo:` 밖이다 (들여쓰기 12칸)",
          line.startswith(" " * 12) and not line.startswith(" " * 16), repr(line[:40]))
    check("🔴 ③ 호출부가 changed 를 넘긴다 (todo 가 아니다)",
          "_enqueue_review(paths, changed," in line, repr(line.strip()[:60]))
    check("② process_event 에 주입 자리가 있다", "enqueue_review=None" in src)


def test_요약줄():
    r = C.ProjectResult(project_id="Sim/NS")
    r.review_queued = "abc12345deadbeef"
    line = r.summary
    check("⑦ 요약이 위임을 말한다", "리뷰 등재로 위임" in line and "abc12345" in line, line)


if __name__ == "__main__":
    for fn in (test_기본_등재, test_LLM을_부르지_않는다,
               test_기존_리뷰가_정상이면_등재하지_않는다,
               test_형식위반_리뷰는_다시_등재한다, test_등재_실패는_카나리다,
               test_커밋이_없으면_생략, test_호출부가_todo_밖이고_changed_를_넘긴다,
               test_요약줄):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
