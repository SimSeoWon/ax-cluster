"""수정 항목 색인 (`#627`) — 리뷰·플랜 번호와 항목 결정.

검증하는 것:

    ① 번호는 시간순으로 붙고 다시 훑어도 바뀌지 않는다 (멱등)
    ② [중요] 리뷰가 `_archive/` 로 **옮겨져도 같은 번호**다 — 번호는 커밋에 묶인다
    ③ 헤더 없는 리뷰도 파일명 8자로 같은 커밋에 묶인다
    ④ 사라진 문서는 번호를 지우지 않고 `missing` — 돌아오면 풀린다
    ⑤ [중요] 요약(8103 에 그대로 나간다)에 **본문·지적 설명·소스 경로가 없다**
    ⑥ 항목 결정 — 형식·범위·상태 거절은 `ok:false` + 사유
    ⑦ 플랜 결정은 MD frontmatter `status` 를 원전 값(acted/dismissed/pending)으로 맞춘다
    ⑧ [중요] 깨진 색인은 **덮지 않는다** (덮으면 번호가 다시 매겨진다)
    ⑨ 동시에 훑어도 번호가 겹치지 않는다 (파일 잠금)

`.venv/bin/python master/test_fix_index.py`
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import fix_index as F                   # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


SECRET_DESC = "비밀설명_널역참조"
SECRET_PATH = "Source/NS/Hidden/Secret.cpp"


def review_text(commit: str, author: str, *, header: bool = True, rows: int = 2) -> str:
    head = (f"# 자동 코드 리뷰 — {commit[:12]}\n\n- 커밋: `{commit}`\n- 작성자: {author}\n"
            f"- 파일: 3개\n- 생성: 2026-09-13 17:07\n\n") if header else ""
    safety = "\n".join(f"| {SECRET_PATH} | high | {10 + i} | {SECRET_DESC}{i} | IsValid 추가 |"
                       for i in range(rows))
    return (head + "### Source/NS/AI\n\n## 1. 변경분 코딩 컨벤션\n"
            "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n"
            f"| {SECRET_PATH} | 명명 | b 접두 누락 | 5 | low |\n\n"
            "## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
            "|---|---|---|---|---|\n" + safety + "\n")


def plan_text(status: str = "pending") -> str:
    return ("---\ntype: improvement_plan\nweek: 2026-W37\ncategory: safety\nseverity: high\n"
            f"target_file: {SECRET_PATH}\nsource_reviews:\n  - a.md\nstatus: {status}\n---\n\n"
            f"## 원본 리뷰 지적\n\n- {SECRET_DESC}\n")


def make_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="fixidx-"))
    a = root / "reviews" / "Simkung"
    b = root / "reviews" / "SimSeoWon"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "2026-09-13_1707_aaaaaaaa.md").write_text(review_text("a" * 40, "Simkung"), encoding="utf-8")
    (b / "2026-09-13_1708_bbbbbbbb.md").write_text(review_text("b" * 40, "SimSeoWon", rows=1),
                                                   encoding="utf-8")
    (a / "2026-09-13_1709_cccccccc.md").write_text(review_text("c" * 40, "Simkung", header=False),
                                                   encoding="utf-8")
    (a / "_note.md").write_text("리뷰 아님", encoding="utf-8")
    w = root / "plans" / "Simkung" / "2026-W37"
    w.mkdir(parents=True)
    (w / "high_Secret.md").write_text(plan_text(), encoding="utf-8")
    (w / "_summary.md").write_text("요약", encoding="utf-8")
    return root


def test_serials_and_idempotent():
    root = make_root()
    logs = []
    got = F.sweep(root, logf=logs.append)
    check("① 리뷰 3 + 플랜 1 에 번호", got["assigned"] == ["R1", "R2", "R3", "P1"], str(got))
    check("① `_` 접두 파일·요약은 번호가 없다", got["total"] == 4, str(got))
    check("① 번호 부여가 로그에 남는다", any("[fix] 번호 부여 4건" in m for m in logs), str(logs))
    docs = F.load(root)["docs"]
    check("① 시간순(파일명)으로 붙는다 — 작성자 무관",
          [docs[s]["commit"][:1] for s in ("R1", "R2", "R3")] == ["a", "b", "c"], str(docs))
    again = F.sweep(root)
    check("① 다시 훑어도 새 번호가 없다", again["assigned"] == [] and again["moved"] == 0, str(again))
    shutil.rmtree(root)


def test_archive_move_keeps_serial():
    root = make_root()
    F.sweep(root)
    src = root / "reviews" / "Simkung" / "2026-09-13_1707_aaaaaaaa.md"
    dst = root / "reviews" / "Simkung" / "_archive" / "2026-W37"
    dst.mkdir(parents=True)
    shutil.move(str(src), dst / src.name)
    got = F.sweep(root)
    doc = F.load(root)["docs"]["R1"]
    check("② [중요] 옮겨져도 새 번호가 없다", got["assigned"] == [], str(got))
    check("② 경로만 갱신된다", "_archive/2026-W37" in doc["file"] and got["moved"] == 1, str(doc))
    check("② 옮겨진 리뷰의 항목도 읽힌다", F.get_doc(root, "R1")["items"] == 3,
          str(F.get_doc(root, "R1").get("items")))
    shutil.rmtree(root)


def test_header_less_review_binds_by_prefix():
    root = make_root()
    F.sweep(root)
    d = F.load(root)["docs"]["R3"]
    check("③ 헤더 없는 리뷰는 파일명 8자를 커밋으로 쓴다", d["commit"] == "cccccccc", str(d))
    # 같은 커밋의 헤더 있는 리뷰가 뒤에 와도 같은 번호로 묶인다
    (root / "reviews" / "Simkung" / "2026-09-14_0101_cccccccc.md").write_text(
        review_text("c" * 40, "Simkung"), encoding="utf-8")
    got = F.sweep(root)
    check("③ 같은 커밋이면 새 번호가 없다", got["assigned"] == [], str(got))
    shutil.rmtree(root)


def test_missing_then_revived():
    root = make_root()
    F.sweep(root)
    f = root / "reviews" / "SimSeoWon" / "2026-09-13_1708_bbbbbbbb.md"
    keep = f.read_text(encoding="utf-8")
    f.unlink()
    got = F.sweep(root)
    check("④ 사라진 문서는 missing", F.load(root)["docs"]["R2"].get("missing") is True
          and got["missing"] == 1, str(got))
    f.write_text(keep, encoding="utf-8")
    F.sweep(root)
    check("④ 돌아오면 missing 이 풀린다", "missing" not in F.load(root)["docs"]["R2"])
    shutil.rmtree(root)


def test_summary_has_no_body():
    root = make_root()
    out = F.list_docs(root)
    dump = json.dumps(out, ensure_ascii=False)
    check("⑤ [중요] 요약에 지적 설명이 없다", SECRET_DESC not in dump)
    check("⑤ [중요] 요약에 소스 경로가 없다", SECRET_PATH not in dump)
    check("⑤ 요약에 file 키가 없다", all("file" not in d for d in out["docs"]), dump[:300])
    r1 = next(d for d in out["docs"] if d["serial"] == "R1")
    check("⑤ 항목 수·심각도 건수는 있다",
          r1["items"] == 3 and r1["severity"] == {"high": 2, "mid": 0, "low": 1}, str(r1))
    check("⑤ 결정 없으면 전부 open", r1["states"] == {"open": 3}, str(r1))
    order = [d["serial"] for d in out["docs"]]
    check("⑤ 최신 번호가 먼저", order == ["P1", "R3", "R2", "R1"], str(order))
    full = F.get_doc(root, "r1")
    check("⑤ get_doc 은 본문·항목을 준다 (토큰 경로 전용)",
          full["ok"] and SECRET_DESC in full["body"] and len(full["items_detail"]) == 3, str(full)[:300])
    check("⑤ 항목 번호는 R1-1 부터", full["items_detail"][0]["id"] == "R1-1", str(full["items_detail"][0]))
    shutil.rmtree(root)


def test_status_validation():
    root = make_root()
    F.sweep(root)
    ok = F.set_status(root, "R1-2", "accepted", note="합당", by="t", branch="fix/R1")
    check("⑥ 정상 기록", ok["ok"] and ok["id"] == "R1-2", str(ok))
    st = F.get_doc(root, "R1")
    check("⑥ 상태가 항목에 붙는다", st["items_detail"][1]["status"]["state"] == "accepted"
          and st["states"] == {"accepted": 1, "open": 2}, str(st["states"]))
    for args, want in ((("R1", "accepted"), "행 번호"), (("R1-9", "accepted"), "1~3"),
                       (("R99-1", "accepted"), "없는 번호"), (("Z1", "accepted"), "형식"),
                       (("R1-1", "done"), "모르는 상태")):
        got = F.set_status(root, *args)
        check(f"⑥ 거절: {args}", got["ok"] is False and want in got["reason"], str(got))
    F.set_status(root, "R1-2", "open")
    check("⑥ open 은 기록을 지운다", "R1-2" not in F.load(root)["status"])
    shutil.rmtree(root)


def test_plan_status_frontmatter():
    root = make_root()
    F.sweep(root)
    p = root / "plans" / "Simkung" / "2026-W37" / "high_Secret.md"
    got = F.set_status(root, "P1", "applied", commit="d" * 40)
    check("⑦ applied → acted", got.get("plan_status") == "acted" and "status: acted" in p.read_text())
    F.set_status(root, "P1", "accepted")
    check("⑦ accepted 는 frontmatter 를 안 건드린다", "status: acted" in p.read_text())
    F.set_status(root, "P1", "dismissed")
    check("⑦ dismissed → dismissed", "status: dismissed" in p.read_text())
    F.set_status(root, "P1", "open")
    check("⑦ open → pending", "status: pending" in p.read_text())
    check("⑦ 본문은 보존", SECRET_DESC in p.read_text())
    check("⑦ 플랜 행 번호는 무시하고 문서로 기록", F.set_status(root, "P1-1", "stale")["id"] == "P1")
    shutil.rmtree(root)


def test_broken_index_is_not_overwritten():
    root = make_root()
    F.sweep(root)
    ip = F.index_path(root)
    ip.write_text("{깨짐", encoding="utf-8")
    try:
        F.sweep(root)
        check("⑧ [중요] 깨진 색인이면 멈춘다", False)
    except F.FixIndexError as e:
        check("⑧ [중요] 깨진 색인이면 멈춘다", True)
        check("⑧ 메시지에 절대 경로가 없다", str(root) not in str(e), str(e))
    check("⑧ [중요] 파일을 덮지 않았다", ip.read_text(encoding="utf-8") == "{깨짐")
    shutil.rmtree(root)


def test_concurrent_sweeps():
    root = make_root()
    errors = []

    def run():
        try:
            F.sweep(root)
        except Exception as e:                               # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    data = F.load(root)
    check("⑨ 동시 훑기에 오류가 없다", not errors, str(errors))
    check("⑨ 번호가 겹치지 않고 4개뿐", sorted(data["docs"]) == ["P1", "R1", "R2", "R3"]
          and data["next"] == {"R": 4, "P": 2}, str(data["next"]))
    shutil.rmtree(root)


if __name__ == "__main__":
    for fn in (test_serials_and_idempotent, test_archive_move_keeps_serial,
               test_header_less_review_binds_by_prefix, test_missing_then_revived,
               test_summary_has_no_body, test_status_validation, test_plan_status_frontmatter,
               test_broken_index_is_not_overwritten, test_concurrent_sweeps):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
