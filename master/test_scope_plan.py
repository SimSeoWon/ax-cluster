"""범위 플랜 (`#639`) — 큐 `kind=scope` · 리뷰 없는 커밋 채우기 · `plans/_scope/` 저장.

검증하는 것:

    ① 대상 해석 — 빈 값·절대 경로·`..`·경계 밖·파일 없음은 거절 · 경로·도메인은 소스 파일로
    ② slug — 결정적 · 파일시스템 안전 · `a/b` 와 `a_b` 가 겹치지 않는다
    ③ 커밋 가르기 — 덮임(done · 리뷰 파일) / 대기 / 공백(포기) / 미등재
    ④ 1회차 — 미등재 커밋을 `kind=commit` 으로 등재(우선순위 10 · 요청자 scope:<slug>)하고 대기(WAIT)
       · 같은 회차에 범위 항목을 다시 꺼내지 않는다 · 커밋 리뷰는 그 회차에 돈다
    ⑤ 다음 회차 — 리뷰가 끝났으면 `plans/_scope/<slug>/<회차>/` 에 플랜 + `_summary.md`
       · 범위 밖 파일의 지적은 빠진다 · 원본 리뷰는 그 자리에 남는다
    ⑥ `fix_index`·주간 플랜 인덱스·`planner.list_author_dirs` 가 `_scope` 를 보지 않는다
    ⑦ 지적 0건 — 플랜 없이 done · 요약은 쓴다 · 상용 호출 0
    ⑧ 공백 커밋 — 다시 등재하지 않고 요약·로그에 남기고 진행한다
    ⑨ 플랜 생성 실패 — 재시도 가능한 실패로 남고(플랜 파일 0) 다음 회차에 끝난다
    ⑩ 소비자에 닿은 잘못된 대상 — 결정적으로 1회에 종결
    ⑪ 입구 — CLI 등재·중복·거절 · MCP 도구(마운트된 프로젝트만) · 레지스트리 해석은 실물
    ⑫ 로그 — 사건마다 `[범위플랜]` 한 줄

실 LLM 을 부르지 않는다(초고·퇴고·플랜 호출 주입). git 은 실제 임시 저장소다.
`.venv/bin/python master/test_scope_plan.py`
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.context_synth import fix_index as FX                  # noqa: E402
from master.context_synth import plan_generator as PG             # noqa: E402
from master.context_synth import planner as PL                    # noqa: E402
from master.context_synth import review_queue as Q                # noqa: E402
from master.context_synth import review_runner as R               # noqa: E402
from master.context_synth import scope_plan as SP                 # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Paths:
    """트윈 경로 대역. `scope`·`name` 을 일부러 안 둔다 — 기본 경계(`Source/`)로 접히는 것까지 탄다."""

    def __init__(self, root):
        self.root = str(root)
        self.repo = str(Path(root) / "repo")
        self.ontology = Path(root) / "ontology"
        self.context = Path(root) / "context"
        self.class_graph_db = Path(root) / "class_graph.db"
        self.usage_log = Path(root) / "usage_log.jsonl"


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def make_repo():
    """c0(A.h·A.cpp·N/C.cpp·README·Docs) → c1(A.cpp) → c2(B.cpp + N/C.cpp).

    범위 `Source/M` 의 마지막 커밋: A.h=c0 · A.cpp=c1 · B.cpp=c2. c2 는 범위 밖 파일도 건드린다.
    """
    root = Path(tempfile.mkdtemp(prefix="ax-scope-"))
    repo = root / "repo"
    (repo / "Source" / "M").mkdir(parents=True)
    (repo / "Source" / "N").mkdir(parents=True)
    (repo / "Docs").mkdir()
    (root / "context").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git(repo, "config", "user.email", "t@e.st")
    git(repo, "config", "user.name", "테스터")
    (repo / "Source" / "M" / "A.h").write_text("class AFoo {\npublic:\n  void Bar();\n};\n")
    (repo / "Source" / "M" / "A.cpp").write_text("void AFoo::Bar() {}\n")
    (repo / "Source" / "N" / "C.cpp").write_text("int C() { return 0; }\n")
    (repo / "README.md").write_text("읽어 보기\n")
    (repo / "Docs" / "guide.md").write_text("안내\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "c0")
    c0 = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "Source" / "M" / "A.cpp").write_text("void AFoo::Bar() {\n  int x = 1 / 0;\n}\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "c1")
    c1 = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "Source" / "M" / "B.cpp").write_text("int Baz() { int* p = nullptr; return *p; }\n")
    (repo / "Source" / "N" / "C.cpp").write_text("int C() { int* q = nullptr; return *q; }\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "c2")
    c2 = git(repo, "rev-parse", "HEAD").stdout.strip()
    return root, (c0, c1, c2)


HEAD_ROWS = """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
"""
TAIL = "\n## 3. 영향 분석\n런타임 오류 위험.\n"
# 범위 안(A.cpp) 하나 · 범위 밖(N/C.cpp) 하나
BODY = (HEAD_ROWS + "| Source/M/A.cpp | 높음 | 2 | 0으로 나눔 | 분모 검사 |\n"
        "| Source/N/C.cpp | 높음 | 1 | 널 역참조 | 널 검사 |\n" + TAIL)
BODY_CLEAN = HEAD_ROWS + TAIL

VALID_PLAN = """## 문제 분석
분모 검증이 없어 0으로 나눌 수 있다.

## 수정 방안
Before: `1 / 0`
After: 분모를 검사한 뒤 나눈다.

## 영향 범위
호출자의 기존 정상 입력 동작은 유지한다.

## 우선순위 근거
런타임 중단을 막는다.
"""


def kw(body=BODY, chats=None, lines=None, plan=VALID_PLAN):
    """소비자 주입 한 벌 — 초고·퇴고·플랜 호출 전부 대역."""
    def chat(prompt):
        if chats is not None:
            chats.append(prompt)
        return plan
    out = dict(draft_call=lambda p: "없음", review_call=lambda p, **k: body, scope_chat=chat)
    if lines is not None:
        out["logf"] = lines.append
    return out


def scope_item(root):
    return [x for x in Q.items(root) if x["kind"] == "scope"][0]


def force_state(root, item_id, state, why=""):
    data = Q._read(root)
    for it in data["items"]:
        if it["id"] == item_id:
            it["state"], it["last_why"] = state, why
    Q._write(root, data)


def test_resolve():
    root, _ = make_repo()
    p = Paths(root)
    for name, target in (("빈 값", ""), ("공백", "   "), ("절대 경로", "/etc"), ("드라이브 경로", "C:\\x"),
                         ("상위 참조", "../x"), ("가운데 상위 참조", "Source/../Docs"),
                         ("저장소 전체", "."), ("경계 밖", "Docs"), ("경계 밖 파일", "README.md"),
                         ("없는 경로", "Source/Nope"), ("없는 도메인", "domain:Nope"),
                         ("도메인 이름 아님", "domain:a/b")):
        try:
            SP.resolve_scope(p, target)
            check(f"① {name} → 거절", False, target)
        except SP.ScopeError as e:
            check(f"① {name} → 거절 · 사유가 있다", bool(str(e)), target)
    s = SP.resolve_scope(p, "Source/M")
    check("① 디렉토리 → 범위 안 소스 파일(정렬)", s.files == ["Source/M/A.cpp", "Source/M/A.h", "Source/M/B.cpp"]
          and s.kind == "path" and s.key == "Source/M", str(s))
    check("① 끝 슬래시·역슬래시는 같은 대상", SP.resolve_scope(p, "Source\\M/").key == "Source/M"
          and SP.resolve_scope(p, "./Source/M/").slug == s.slug)
    check("① 파일 하나도 대상이다", SP.resolve_scope(p, "Source/M/A.cpp").files == ["Source/M/A.cpp"])
    check("① 경계 전체", len(SP.resolve_scope(p, "Source").files) == 4)
    # 도메인 — 멤버의 소스 파일(`collect.members_of`)
    d = p.ontology / "domains" / "Combat"
    (d / "objects").mkdir(parents=True)
    (d / "domain.yaml").write_text("domain: Combat\nobjects:\n  - objects/AFoo.yaml\n  - objects/Gone.yaml\n",
                                   encoding="utf-8")
    (d / "objects" / "AFoo.yaml").write_text("name: AFoo\nfile: Source/M/A.h\n", encoding="utf-8")
    (d / "objects" / "Gone.yaml").write_text("name: AGone\nfile: Source/M/Gone.h\n", encoding="utf-8")
    sd = SP.resolve_scope(p, "domain:Combat")
    check("① 도메인 → 멤버 파일 중 추적되는 것만", sd.files == ["Source/M/A.h"] and sd.kind == "domain"
          and sd.key == "domain:Combat", str(sd))
    # ② slug
    check("② slug 결정적", SP.slug_for("Source/M") == SP.slug_for("Source/M"))
    check("② slug 는 경로 구분자·콜론이 없다", all(ch not in SP.slug_for(k) for k in ("a/b c", "domain:전투")
                                              for ch in "/\\: ") and not SP.slug_for("../x").startswith((".", "_")))
    check("② a/b 와 a_b 가 겹치지 않는다", SP.slug_for("a/b") != SP.slug_for("a_b"))
    shutil.rmtree(root)


def test_classify():
    root, (c0, c1, c2) = make_repo()
    p = Paths(root)
    commits, orphan = SP.last_commits(p.repo, ["Source/M/A.cpp", "Source/M/A.h", "Source/M/B.cpp"])
    check("③ 파일 → 마지막 커밋(중복 제거)", commits == {c1: ["Source/M/A.cpp"], c0: ["Source/M/A.h"],
                                                c2: ["Source/M/B.cpp"]} and not orphan, str(commits))
    check("③ 커밋의 소스 파일 — 색인기 등재와 같은 모양", SP.commit_files(p, c2) == ["Source/M/B.cpp", "Source/N/C.cpp"]
          and SP.commit_files(p, c0) == ["Source/M/A.cpp", "Source/M/A.h", "Source/N/C.cpp"],
          f"{SP.commit_files(p, c2)} {SP.commit_files(p, c0)}")
    fake = "d" * 40
    got = SP.classify_commits(p, [c0, c1, c2, fake])
    check("③ 큐·파일 어디에도 없으면 미등재", got["missing"] == [c0, c1, c2, fake] and not got["covered"], str(got))
    # c0 = 아카이브된 리뷰 파일(큐 항목 없음) · c1 = pending · c2 = abandoned
    arch = Path(root) / "reviews" / "테스터" / "_archive" / "2026-W40"
    arch.mkdir(parents=True)
    (arch / f"2026-10-01_1200_{c0[:8]}.md").write_text(
        f"# 자동 코드 리뷰 — {c0[:12]}\n\n- 커밋: `{c0}`\n- 작성자: 테스터\n\n" + BODY, encoding="utf-8")
    Q.enqueue(root, key=c1, files=["Source/M/A.cpp"])
    Q.enqueue(root, key=c2, files=["Source/M/B.cpp"])
    force_state(root, f"commit:{c2}", "abandoned", "diff 를 읽지 못했다")
    got = SP.classify_commits(p, [c0, c1, c2, fake])
    check("③ 아카이브 리뷰 파일 → 덮임", got["covered"] == [c0], str(got["covered"]))
    check("③ pending → 대기", got["waiting"] == [c1], str(got["waiting"]))
    check("③ abandoned → 공백(사유 포함)", [g["commit"] for g in got["gaps"]] == [c2]
          and "diff 를 읽지 못했다" in got["gaps"][0]["why"], str(got["gaps"]))
    check("③ 나머지 → 미등재", got["missing"] == [fake])
    force_state(root, f"commit:{c1}", "running")
    check("③ running → 대기", SP.classify_commits(p, [c1])["waiting"] == [c1])
    force_state(root, f"commit:{c1}", "done")
    check("③ done → 덮임(리뷰 파일이 없어도 — 스킵 종결 포함)", SP.classify_commits(p, [c1])["covered"] == [c1])
    # 형식 위반 리뷰 파일은 덮임으로 세지 않는다
    bad = Path(root) / "reviews" / "테스터" / f"2026-10-02_1200_{fake[:8]}.md"
    bad.write_text(f"# 자동 코드 리뷰 — x\n\n- 커밋: `{fake}`\n\n표가 없다\n", encoding="utf-8")
    check("③ 형식 위반 리뷰 파일은 덮임이 아니다", SP.classify_commits(p, [fake])["missing"] == [fake])
    # 지적 수집 — 덮인 커밋 · 범위 안 파일만 · 줄여 쓴 경로는 하나로 맞을 때만
    files = ["Source/M/A.cpp", "Source/M/A.h", "Source/M/B.cpp"]
    issues = SP.collect_issues(p, files, [c0])
    check("③ 지적 — 범위 안 파일만 (아카이브에서도 읽는다)", [i.file for i in issues] == ["Source/M/A.cpp"],
          str([(i.file, i.commit_hash[:8]) for i in issues]))
    check("③ 지적 — 다른 커밋의 리뷰는 안 읽는다", SP.collect_issues(p, files, [c2]) == [])
    check("③ 줄여 쓴 경로는 범위 파일 하나로 맞춘다", SP._in_scope("`A.cpp`", files) == "Source/M/A.cpp"
          and SP._in_scope("C.cpp", files) == "" and SP._in_scope("M/B.cpp", files) == "Source/M/B.cpp")
    check("③ 둘 이상 맞으면 고르지 않는다", SP._in_scope("X.cpp", ["Source/A/X.cpp", "Source/B/X.cpp"]) == "")
    shutil.rmtree(root)


def test_rounds():
    root, (c0, c1, c2) = make_repo()
    p = Paths(root)
    out = SP.request(p, "Source/M", requester="test")
    check("④ 요청 — pending · 파일 3건", out["ok"] and not out["already"] and out["state"] == "pending"
          and out["files"] == 3 and out["id"] == "scope:Source/M", str(out))
    slug = out["slug"]
    chats, lines = [], []
    rs = R.drain(p, limit=5, **kw(chats=chats, lines=lines))
    it = scope_item(root)
    check("④ 1회차 — 범위 항목은 한 번만 꺼냈다 · 대기(WAIT)", sum(1 for r in rs if r.item_id == it["id"]) == 1
          and it["attempts"] == 1 and it["state"] == "pending" and it["last_kind"] == Q.WAIT,
          f"{[r.item_id for r in rs]} {it['attempts']} {it['state']} {it['last_kind']}")
    check("④ 대기 사유에 건수가 있다", SP.WAIT_WHY in it["last_why"] and "이번 회차 등재 3건" in it["last_why"]
          and "커밋 3건" in it["last_why"], it["last_why"])
    cs = {x["key"]: x for x in Q.items(root) if x["kind"] == "commit"}
    check("④ 미등재 커밋 3건을 kind=commit 으로 등재", set(cs) == {c0, c1, c2}, str(sorted(cs)))
    check("④ 우선순위 10 · 요청자 scope:<slug>", all(x["priority"] == 10 and x["requester"] == f"scope:{slug}"
                                              for x in cs.values()), str([(x["priority"], x["requester"]) for x in cs.values()]))
    check("④ 범위 항목은 그 커밋 리뷰보다 한 칸 아래", it["priority"] == 9, str(it["priority"]))
    check("④ 등재 파일 = 그 커밋의 소스 파일", cs[c2]["files"] == ["Source/M/B.cpp", "Source/N/C.cpp"]
          and cs[c1]["files"] == ["Source/M/A.cpp"], f"{cs[c2]['files']} {cs[c1]['files']}")
    check("④ 커밋 리뷰는 같은 회차에 돈다", all(x["state"] == "done" for x in cs.values()),
          str([x["state"] for x in cs.values()]))
    check("④ 1회차에는 플랜 호출 0 · 플랜 디렉토리 없음", not chats and not (Path(root) / "plans").exists())
    reviews = sorted(f.name for f in (Path(root) / "reviews" / "테스터").glob("*.md"))
    check("④ 리뷰 파일 3건(기존 리뷰 형식 그대로)", len(reviews) == 3, str(reviews))

    # 다음 회차 — 리뷰가 다 끝났다
    now = datetime(2026, 11, 12, 9, 30)
    res = R.RunnerResult()
    item = Q.claim(root)
    check("⑤ 다음 회차에 범위 항목을 다시 꺼낸다", item is not None and item["kind"] == "scope", str(item))
    r = SP.run_scope(p, item, res, chat=kw(chats=chats)["scope_chat"], logf=lines.append, now=now)
    it = scope_item(root)
    run_dir = Path(root) / "plans" / "_scope" / slug / "2026-11-12_0930"
    check("⑤ done", r.state == "done" and it["state"] == "done", f"{r.state} {r.why}")
    plans = sorted(f.name for f in run_dir.glob("*.md"))
    check("⑤ plans/_scope/<slug>/<회차>/ 에 플랜 + 요약", plans == ["_summary.md", "high_A.md"], str(plans))
    check("⑤ 플랜 호출 1회 — 범위 안 파일만", len(chats) == 1 and "[대상 파일] Source/M/A.cpp" in chats[0]
          and "Source/N/C.cpp" not in chats[0], str(len(chats)))
    plan = (run_dir / "high_A.md").read_text(encoding="utf-8")
    check("⑤ 플랜은 주간 플랜과 같은 형식(프론트매터 · 본문)", plan.startswith("---") and "## 수정 방안" in plan
          and "Source/M/A.cpp" in plan, plan[:200])
    summ = (run_dir / "_summary.md").read_text(encoding="utf-8")
    check("⑤ 요약 — 대상·파일·커밋·지적·플랜", "scope: Source/M" in summ and "범위 안 소스 파일: 3건" in summ
          and "마지막 커밋: 3건 — 리뷰로 덮임 3 · 공백 0" in summ and "생성한 플랜: 1건 · 실패 0건" in summ
          and "high_A.md" in summ and "status: 완료" in summ, summ)
    check("⑤ 요약 — 수집 지적은 범위 안 것만 센다(3커밋 × A.cpp)", "수집 지적: 3건 (정리 뒤 1건" in summ, summ)
    check("⑤ 큐 기록 — 저장 위치·건수", it["meta"].get("plans_dir") == f"plans/_scope/{slug}/2026-11-12_0930"
          and it["meta"].get("plans") == 1 and it["meta"].get("gaps") == 0
          and "플랜 1건" in it["history"][-1]["note"], str(it["meta"]))
    check("⑤ 원본 리뷰는 그 자리에 남는다(아카이브 안 함)",
          sorted(f.name for f in (Path(root) / "reviews" / "테스터").glob("*.md")) == reviews
          and not (Path(root) / "reviews" / "테스터" / "_archive").exists())
    # ⑥ 주간 플랜 집계·fix_index 가 보지 않는다
    check("⑥ fix_index 플랜 목록에 없다", FX._plan_files(Path(root)) == [], str(FX._plan_files(Path(root))))
    FX.sweep(root)
    kinds = [d.get("kind") for d in FX.load(root)["docs"].values()]
    check("⑥ fix_index 번호 — 리뷰 3건만 · 플랜 번호 없음", kinds.count("review") == 3 and "plan" not in kinds, str(kinds))
    check("⑥ planner.list_author_dirs 가 _scope 를 작성자로 안 본다",
          PL.list_author_dirs(Path(root) / "plans") == [])
    PG._update_global_plan_index(Path(root) / "plans")
    check("⑥ 전체 플랜 인덱스에 _scope 없음",
          "_scope" not in (Path(root) / "plans" / "_index.md").read_text(encoding="utf-8"))
    # ⑫ 로그
    text = "\n".join(lines)
    for mark in ("[범위플랜] 해석 Source/M (path) — 파일 3 · 커밋 3", f"[범위플랜] 등재 {c1[:8]} 파일 1건",
                 "[범위플랜] 대기 Source/M — 남은 커밋 리뷰 3건", "[범위플랜] 지적 Source/M — 수집 3건 · 정리 뒤 1건",
                 "[범위플랜] 플랜 생성 Source/M — 1건 저장", f"[범위플랜] 저장 plans/_scope/{slug}/2026-11-12_0930/",
                 "[범위플랜] 종료 Source/M — pending", "[범위플랜] 종료 Source/M — done"):
        check(f"⑫ 로그 — {mark[:34]}", mark in text, text[-600:] if mark not in text else "")
    # 끝난 대상은 다시 등재되지 않는다
    again = SP.request(p, "Source/M/", requester="test")
    check("⑪ 완료된 대상 재요청 → already", again["already"] and again["state"] == "done", str(again))
    shutil.rmtree(root)


def test_zero_issues():
    root, _ = make_repo()
    p = Paths(root)
    SP.request(p, "Source/M")
    chats = []
    R.drain(p, limit=5, **kw(body=BODY_CLEAN, chats=chats))
    rs = R.drain(p, limit=5, **kw(body=BODY_CLEAN, chats=chats))
    it = scope_item(root)
    check("⑦ 지적 0건 → done", it["state"] == "done" and len(rs) == 1 and rs[0].state == "done", str(it["state"]))
    check("⑦ 노트 「지적 0건 — 플랜 없음」", "지적 0건 — 플랜 없음" in it["history"][-1]["note"], str(it["history"][-1]))
    check("⑦ 상용 호출 0", not chats, str(len(chats)))
    run_dirs = list((Path(root) / "plans" / "_scope" / it["meta"]["slug"]).iterdir())
    names = [f.name for f in run_dirs[0].iterdir()] if run_dirs else []
    check("⑦ 요약은 쓴다 · 플랜 파일 없음", len(run_dirs) == 1 and names == ["_summary.md"], str(names))
    summ = (run_dirs[0] / "_summary.md").read_text(encoding="utf-8") if run_dirs else ""
    check("⑦ 요약 상태", "status: 지적 0건 — 플랜 없음" in summ and "수집 지적: 0건" in summ, summ)
    shutil.rmtree(root)


def test_below_gate():
    """지적은 있는데 플랜 생성기 기준(고위험 1+ · 중위험 3+)에 못 미친다 — 조용한 0건이 아니라 사유를 낸다.

    실물(2026-11-12 `master/broker`: low 2 · mid 1 → 플랜 0건, 요약은 「완료」)에서 나온 경우다.
    """
    root, _ = make_repo()
    p = Paths(root)
    SP.request(p, "Source/M")
    chats, lines = [], []
    body = HEAD_ROWS + "| Source/M/A.cpp | 낮음 | 2 | 사소한 지적 | 정리 |\n" + TAIL
    R.drain(p, limit=5, **kw(body=body, chats=chats, lines=lines))
    R.drain(p, limit=5, **kw(body=body, chats=chats, lines=lines))
    it = scope_item(root)
    note = it["history"][-1]["note"]
    check("⑦-2 기준 미달 → done · 상용 호출 0", it["state"] == "done" and not chats, f"{it['state']} {len(chats)}")
    check("⑦-2 노트에 「플랜 기준 미달」과 심각도", SP.BELOW_GATE in note and "low" in note, note)
    run_dirs = list((Path(root) / "plans" / "_scope" / it["meta"]["slug"]).iterdir())
    summ = (run_dirs[0] / "_summary.md").read_text(encoding="utf-8") if run_dirs else ""
    check("⑦-2 요약 상태·심각도·기준", f"status: {SP.BELOW_GATE}" in summ and "지적 심각도: low" in summ
          and SP.GATE_RULE in summ, summ)
    check("⑦-2 로그 [주의]", any("[주의]" in ln and SP.BELOW_GATE in ln for ln in lines), "\n".join(lines[-6:]))
    shutil.rmtree(root)


def test_gap():
    root, (c0, c1, c2) = make_repo()
    p = Paths(root)
    # c2 의 리뷰는 이미 포기됐다 — 범위 요청이 되살리지 않는다
    Q.enqueue(root, key=c2, files=["Source/M/B.cpp"])
    force_state(root, f"commit:{c2}", "abandoned", "Antigravity 정형 리뷰 형식 위반")
    SP.request(p, "Source/M")
    lines, chats = [], []
    R.drain(p, limit=5, **kw(chats=chats, lines=lines))
    c2_item = [x for x in Q.items(root) if x["id"] == f"commit:{c2}"][0]
    check("⑧ 포기된 커밋은 다시 등재하지 않는다", c2_item["state"] == "abandoned" and c2_item["attempts"] == 0,
          f"{c2_item['state']} {c2_item['attempts']}")
    it = scope_item(root)
    check("⑧ 1회차 대기 사유 — 등재 2 · 공백 1", "이번 회차 등재 2건" in it["last_why"] and "공백 1" in it["last_why"],
          it["last_why"])
    R.drain(p, limit=5, **kw(chats=chats, lines=lines))
    it = scope_item(root)
    check("⑧ 공백이 있어도 플랜까지 간다", it["state"] == "done" and it["meta"].get("gaps") == 1
          and "공백 1" in it["history"][-1]["note"], f"{it['state']} {it.get('meta')}")
    summ = (Path(root) / it["meta"]["plans_dir"] / "_summary.md").read_text(encoding="utf-8")
    check("⑧ 요약 — 공백 커밋·사유·파일", "## 공백" in summ and c2[:12] in summ and "형식 위반" in summ
          and "Source/M/B.cpp" in summ and "리뷰로 덮임 2 · 공백 1" in summ, summ)
    check("⑧ 로그 — 공백", any("[범위플랜] [주의] 공백 " + c2[:8] in ln for ln in lines), "\n".join(lines)[-400:])
    shutil.rmtree(root)


def test_plan_failure_retries():
    root, _ = make_repo()
    p = Paths(root)
    SP.request(p, "Source/M")
    R.drain(p, limit=5, **kw())
    lines = []
    rs = R.drain(p, limit=5, **kw(plan="", lines=lines))               # 빈 응답 = 생성 실패
    it = scope_item(root)
    check("⑨ 생성 실패 → 재시도 가능한 실패(pending · transient)", rs and rs[0].state == "failed"
          and it["state"] == "pending" and it["last_kind"] == Q.TRANSIENT and "범위 플랜 생성 미완료" in it["last_why"],
          f"{it['state']} {it['last_kind']} {it['last_why']}")
    base = Path(root) / "plans" / "_scope" / it["meta"]["slug"]
    check("⑨ 실패 회차에는 플랜 파일이 없다(요약만)", [f.name for f in base.glob("*/*.md")] == ["_summary.md"],
          str([f.name for f in base.glob("*/*.md")]))
    summ = next(base.glob("*/_summary.md")).read_text(encoding="utf-8")
    check("⑨ 요약 — 생성 미완료·실패 사유", "status: 생성 미완료" in summ and "## 생성 실패" in summ
          and "high_A.md" in summ, summ)
    check("⑨ 로그 — 생성 결과·종료", any("[범위플랜] 플랜 생성 Source/M — 0건 저장" in ln and "실패 1" in ln for ln in lines)
          and any("[범위플랜] 종료 Source/M — pending" in ln for ln in lines), "\n".join(lines)[-400:])
    # 한도 사유는 시도를 소비하지 않는다(큐의 기존 갈래를 그대로 탄다)
    before = it["attempts"]

    def quota(_p):
        raise RuntimeError("You've hit your session limit")
    R.drain(p, limit=5, draft_call=lambda q: "없음", review_call=lambda q, **k: BODY, scope_chat=quota)
    it = scope_item(root)
    check("⑨ 한도 실패는 시도 미소비", it["last_kind"] == Q.QUOTA and it["attempts"] == before and it["state"] == "pending",
          f"{it['last_kind']} {it['attempts']} {before}")
    R.drain(p, limit=5, **kw())
    it = scope_item(root)
    check("⑨ 다음 회차에 끝난다", it["state"] == "done" and it["meta"].get("plans") == 1, f"{it['state']} {it.get('meta')}")
    shutil.rmtree(root)


def test_bad_target_at_consumer():
    root, _ = make_repo()
    Q.enqueue(root, kind="scope", key="Docs")                          # 입구를 안 거친 잘못된 대상
    lines = []
    r = R.run_once(Paths(root), logf=lines.append, **kw())
    it = scope_item(root)
    check("⑩ 잘못된 대상 → 결정적 · 1회에 종결", r.state == "failed" and it["last_kind"] == Q.DETERMINISTIC
          and it["state"] == "abandoned" and SP.BAD_TARGET_WHY in it["last_why"], f"{it['last_kind']} {it['state']}")
    check("⑩ 커밋 리뷰를 등재하지 않는다", Q.counts(root)["pending"] == 0)
    check("⑩ 로그 — 종료", any("[범위플랜] 종료 Docs — abandoned" in ln for ln in lines), "\n".join(lines))
    check("⑩ 마커가 큐의 갈래와 맞는다", Q.classify(SP.BAD_TARGET_WHY) == Q.DETERMINISTIC
          and Q.classify(SP.WAIT_WHY) == Q.WAIT)
    shutil.rmtree(root)


def test_entrances():
    """⑪ CLI·MCP — 레지스트리·경로 해석은 실물로 탄다."""
    root, _ = make_repo()
    projects = Path(tempfile.mkdtemp(prefix="ax-reg-"))
    (projects / "projects.yaml").write_text(
        "version: 1\nactive: T\nprojects:\n  - T\n  - U\n", encoding="utf-8")
    for name in ("T", "U"):
        twin = projects / name
        twin.mkdir()
        (twin / "config.yaml").write_text(f"version: 1\nname: {name}\nrepo:\n  local_clone: repo\n", encoding="utf-8")
        shutil.copytree(Path(root) / "repo", twin / "repo")
    old = os.environ.get("AX_PROJECTS_ROOT")
    os.environ["AX_PROJECTS_ROOT"] = str(projects)

    def cli(*argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = SP.main(list(argv))
        return rc, buf.getvalue()
    try:
        rc, out = cli("request", "--project", "T", "Source/M")
        check("⑪ CLI 등재 — rc 0 · id·상태 출력", rc == 0 and "등재 scope:Source/M (T) 상태=pending" in out
              and "[범위플랜] 요청 등재 kind=scope Source/M (T) 요청자=cli" in out, f"{rc} {out}")
        it = scope_item(projects / "T")
        check("⑪ 큐 항목 — kind=scope · 요청자 cli · 우선순위 9", it["key"] == "Source/M" and it["requester"] == "cli"
              and it["priority"] == 9 and it["state"] == "pending", str(it))
        rc, out = cli("request", "Source/M/")                        # 프로젝트 생략 = 마운트된 것
        check("⑪ CLI 중복 → 「이미 …」", rc == 0 and "이미 pending — scope:Source/M (T)" in out, f"{rc} {out}")
        check("⑪ 중복은 항목을 늘리지 않는다", len(Q.items(projects / "T")) == 1)
        rc, out = cli("request", "--project", "T", "../etc")
        check("⑪ CLI 잘못된 대상 → rc 2 · 등재 없음", rc == 2 and "거절" in out and len(Q.items(projects / "T")) == 1,
              f"{rc} {out}")
        rc, out = cli("request", "--project", "없는프로젝트", "Source/M")
        check("⑪ CLI 없는 프로젝트 → rc 1", rc == 1 and "프로젝트를 풀지 못했다" in out, f"{rc} {out}")
        # MCP 도구
        from master.projects import mcp_server as pj
        got = json.loads(pj.request_scope_plan_tool("Source/N"))
        check("⑪ MCP 등재 — 마운트된 프로젝트", got.get("ok") and got.get("project") == "T"
              and got.get("id") == "scope:Source/N" and not got.get("already"), str(got))
        mcp_item = [x for x in Q.items(projects / "T") if x["key"] == "Source/N"][0]
        check("⑪ MCP 요청자 표시", mcp_item["requester"] == "mcp", mcp_item["requester"])
        got = json.loads(pj.request_scope_plan_tool("Source/M", project="U"))
        check("⑪ MCP — 마운트되지 않은 프로젝트는 거절", got.get("ok") is False and "마운트" in got.get("error", "")
              and not Q.items(projects / "U"), str(got))
        got = json.loads(pj.request_scope_plan_tool("/abs"))
        check("⑪ MCP — 잘못된 대상은 ok:false", got.get("ok") is False and "절대 경로" in got.get("error", ""), str(got))
    finally:
        if old is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = old
        shutil.rmtree(projects)
        shutil.rmtree(root)


def main() -> int:
    for fn in (test_resolve, test_classify, test_rounds, test_zero_issues, test_below_gate, test_gap,
               test_plan_failure_retries, test_bad_target_at_consumer, test_entrances):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_scope_plan: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
