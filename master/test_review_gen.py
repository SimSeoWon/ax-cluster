"""자동 코드리뷰 생산자(`#205`) 계약 테스트.

재는 것 넷:
    ① trivial 판정   원전 로직 글자대로 — 주석/로그/include 만이면 스킵, 새 파일·코드 변경은 진행
    ② 작성자 제외    파이프라인 커밋(ax-cluster)은 리뷰 없음 — LLM 을 부르지도 않는다
    ③ 형식 계약      [중요] 생산한 리포트를 **소비자(원전 review_collector)의 정규식**이 읽는가
    ④ 유실 처리      실패는 색인을 막지 않되 카나리에 누적 — 스킵은 카나리가 아니다

실행: .venv/bin/python master/test_review_gen.py   (LLM 0 — chat 주입)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import review_gen as RG      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def g(cwd, *args, author="사람"):
    return subprocess.run(["git", "-c", f"user.name={author}", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class P:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / "repo"
        self.ontology = root / "ontology"


def fixture():
    root = Path(tempfile.mkdtemp(prefix="ax-rg-"))
    p = P(root)
    p.repo.mkdir()
    g(p.repo, "init", "-q", "-b", "main")
    src = p.repo / "Source" / "M"
    src.mkdir(parents=True)
    (src / "A.cpp").write_text("int F() {\n  return 1;\n}\n", encoding="utf-8")
    g(p.repo, "add", "-A")
    g(p.repo, "commit", "-q", "-m", "base")
    return root, p


def commit_change(p, text, *, author="사람", msg="변경", path="Source/M/A.cpp"):
    f = p.repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    g(p.repo, "add", "-A")
    g(p.repo, "commit", "-q", "-m", msg, author=author)
    return g(p.repo, "rev-parse", "HEAD").stdout.strip()


# ── ① trivial 판정 ────────────────────────────────────────────

def test_trivial_detection():
    root, p = fixture()
    c1 = commit_change(p, "// 설명 주석\nint F() {\n  return 1;\n}\n", msg="주석만")
    check("[중요] 주석만 바뀐 커밋은 trivial",
          RG.is_trivial_diff(p.repo, ["Source/M/A.cpp"], c1) is True)
    c2 = commit_change(p, "// 설명 주석\nint F() {\n  return 2;\n}\n", msg="로직")
    check("코드가 바뀌면 trivial 아님",
          RG.is_trivial_diff(p.repo, ["Source/M/A.cpp"], c2) is False)
    c3 = commit_change(p, "int G() { return 3; }\n", msg="새 파일", path="Source/M/B.cpp")
    check("새 파일은 trivial 아님 (전체 분석 필요)",
          RG.is_trivial_diff(p.repo, ["Source/M/B.cpp"], c3) is False)
    c4 = commit_change(p, '// 설명 주석\nint F() {\n  UE_LOG(LogTemp, Log, TEXT("x"));\n  return 2;\n}\n',
                       msg="로그 추가")
    check("로그 추가만이면 trivial",
          RG.is_trivial_diff(p.repo, ["Source/M/A.cpp"], c4) is True)
    check("git 실패는 보수적으로 False (정상 리뷰 진행)",
          RG.is_trivial_diff(p.repo, ["Source/M/A.cpp"], "없는커밋") is False)
    check("파일 없음도 False", RG.is_trivial_diff(p.repo, [], c2) is False)


# ── ② 작성자 제외 + 스킵 ──────────────────────────────────────

def test_author_exclusion_skips_before_llm():
    root, p = fixture()
    c = commit_change(p, "int F() { return 9; }\n", author="ax-cluster", msg="파이프라인")
    called = []
    r = RG.review_commit(p, c, ["Source/M/A.cpp"],
                         chat=lambda pr: called.append(1) or "본문")
    check("[중요] 파이프라인 커밋은 리뷰 생략 (게이트를 이미 지났다)",
          r.skipped.startswith("작성자 제외"), r.skipped)
    check("[중요] LLM 을 부르지도 않는다", called == [], str(called))
    check("리포트를 안 쓴다", not r.written)

    c2 = commit_change(p, "// only\nint F() { return 9; }\n", msg="주석")
    r2 = RG.review_commit(p, c2, ["Source/M/A.cpp"], chat=lambda pr: "본문")
    check("trivial 도 스킵으로 (유실 아님)", "trivial" in r2.skipped, r2.skipped)
    r3 = RG.review_commit(p, "HEAD", ["Content/맵.uasset"], chat=lambda pr: "본문")
    check("소스 밖 변경만이면 스킵", r3.skipped == "소스 변경 없음", r3.skipped)


# ── ③ 형식 계약 — 소비자(원전 파서)가 읽는가 ─────────────────

_ORIGIN_TABLE_RE = re.compile(       # 원전 review_collector._parse_table_rows 의 정규식 그대로
    r'\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*'
    r'\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|')

CANNED = """### Source/M

## 1. 변경분 코딩 컨벤션
| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |
|---|---|---|---|---|
| Source/M/A.cpp | 네이밍 | 함수명이 파스칼케이스가 아님 | 2 | 중간 |

## 2. 변경분 버그·안전성
| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |
|---|---|---|---|---|
| Source/M/A.cpp | 높음 | 3 | null 체크 누락 | IsValid 가드 추가 |

## 3. 영향 분석
호출부 2곳에 영향 없음.
"""


def test_report_is_parseable_by_origin_collector():
    """[중요] 이 표 계약이 깨지면 소비자(#156)가 빈손이 된다 — 되먹임 전체가 조용히 죽는다."""
    root, p = fixture()
    c = commit_change(p, "int F() { return 7; }\n", msg="실변경")
    r = RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: CANNED)
    check("리포트가 저장된다", bool(r.written), r.error or r.skipped)
    body = Path(r.written).read_text(encoding="utf-8")
    m = re.search(r'커밋:\s*`([a-f0-9]+)`', body)
    check("[중요] 원전 파서의 커밋 정규식이 잡는다", m and m.group(1) == c, str(m))
    check("작성자 디렉토리에 들어간다", "/reviews/사람/" in r.written.replace("\\", "/"), r.written)
    check("파일명이 날짜로 시작한다 (since_date 필터 계약)",
          re.match(r"\d{4}-\d{2}-\d{2}_\d{4}_[0-9a-f]{8}\.md$", Path(r.written).name),
          Path(r.written).name)
    blocks = re.split(r'^###\s+', body, flags=re.M)
    check("### 모듈 절이 있다", len(blocks) >= 2)
    rows = [v for v in _ORIGIN_TABLE_RE.finditer(body)]
    data_rows = [m for m in rows if m.group(1).strip() not in ("파일",) and "---" not in m.group(1)]
    check("[중요] 원전 표 정규식이 데이터 행을 잡는다", len(data_rows) >= 2, str(len(data_rows)))


def test_prompt_carries_the_contract():
    pr = RG.build_prompt(diff="+ int x;", files=["Source/M/A.cpp"], commit="abcdef123456",
                         domains="- MissionRuntime: 요약")
    check("변경분만 리뷰하라고 못박는다", "변경분만" in pr and "보고 금지" in pr)
    check("[중요] 표 열 순서를 프롬프트가 고정한다",
          "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |" in pr
          and "| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |" in pr)
    check("도메인 컨텍스트가 실린다", "MissionRuntime" in pr)
    check("diff 가 실린다", "+ int x;" in pr)
    d = RG.commit_diff  # 잘림 계약
    check("diff 상한 초과 시 잘렸다고 말한다 (조용한 절단 금지)", "잘렸다" in
          ("x" * 10 + "\n... (diff 가 잘렸다 — 여기까지만 리뷰 대상이다)"))


# ── ④ 유실 처리 (소비자 배선) ─────────────────────────────────

def test_consumer_wiring_failure_goes_to_canary():
    from master.events import consumer as C
    root, p = fixture()

    class R:
        to_commit = "abc123"
        review_written = ""
        review_note = ""
        canary_write_failed = 0

    r = R()
    p.canary = root / "_silent_failure" / "loss.jsonl"

    def boom(paths, commit, files):
        raise RuntimeError("노드 죽음")

    C._auto_review(p, ["Source/M/A.cpp"], r, review_run=boom)
    check("[중요] 예외가 색인을 막지 않는다 (fail-soft)", True)
    check("유실이 note 에 남는다", "리뷰 생성 예외" in r.review_note, r.review_note)
    check("[중요] 카나리에 누적된다 (워터마크가 전진하므로 영구 유실)",
          p.canary.exists() and "review-lost" in p.canary.read_text(encoding="utf-8"))

    r2 = R()
    C._auto_review(p, ["Source/M/A.cpp"], r2,
                   review_run=lambda *a: RG.ReviewResult(skipped="trivial"))
    check("스킵은 카나리가 아니다 (설계된 생략)", "스킵" in r2.review_note
          and r2.canary_write_failed == 0, r2.review_note)
    before = p.canary.read_text(encoding="utf-8").count("\n")
    C._auto_review(p, ["Source/M/A.cpp"], r2,
                   review_run=lambda *a: RG.ReviewResult(error="응답 빔"))
    after = p.canary.read_text(encoding="utf-8").count("\n")
    check("생성 실패(error)도 카나리", after == before + 1, f"{before}→{after}")


def test_format_validation_and_retry():
    """[중요] 첫 라이브 런이 잡은 결함 — 모델이 산문만 내면 소비자는 0건으로 읽는다."""
    root, p = fixture()
    c = commit_change(p, "int F() { return 8; }\n", msg="변경")
    calls = []

    def prose_then_good(prompt):
        calls.append(prompt)
        return "이 커밋은 include 경로를 정리했습니다. 전반적으로 양호합니다." \
            if len(calls) == 1 else CANNED

    r = RG.review_commit(p, c, ["Source/M/A.cpp"], chat=prose_then_good)
    check("[중요] 형식 위반이면 1회 재시도한다", r.retried and len(calls) == 2, str(len(calls)))
    check("재시도 프롬프트가 예시 골격을 앞세운다", "골격" in calls[1] and "### " in calls[1])
    check("재시도가 성공하면 format_ok", r.format_ok is True)

    calls2 = []
    r2 = RG.review_commit(p, c, ["Source/M/A.cpp"],
                          chat=lambda pr: calls2.append(pr) or "산문뿐입니다.")
    check("두 번 다 산문이면 저장은 하되 format_ok=False (버리지 않는다 — 사람은 읽는다)",
          r2.written and r2.format_ok is False, f"written={bool(r2.written)}")
    check("재시도는 1회뿐 (무한 루프 금지)", len(calls2) == 2, str(len(calls2)))
    def chain_down(pr):
        raise RG.ReviewChatError("상용 체인(agy → claude) 둘 다 응답 없음")

    r3 = RG.review_commit(p, c, ["Source/M/A.cpp"], chat=chain_down)
    check("[중요] 상용 체인 전멸은 error (카나리 대상) — 예외를 밖으로 안 던진다",
          r3.error.startswith("리뷰 생성 실패") and not r3.written, r3.error)

    check("검증기가 소비자와 같은 눈으로 센다",
          RG.parseable_rows(CANNED) == 2 and RG.parseable_rows("산문") == 0)
    empty_tables = ("### M\n\n## 1. 변경분 코딩 컨벤션\n"
                    "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n\n"
                    "## 2. 변경분 버그·안전성\n"
                    "| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n|---|---|---|---|---|\n")
    check("[중요] 위반 0건(헤더만 있는 표)도 형식 준수다 — 깨끗한 커밋은 정상이다",
          RG.format_ok(empty_tables) and RG.parseable_rows(empty_tables) == 0)
    check("[중요] (없음) 자리표시 행은 만들지 않는다 — 소비자에서 쓰레기 이슈가 된다 (실측)",
          "(없음)" not in RG._FORMAT_EXAMPLE and "비워 둔다" in RG._FORMAT_EXAMPLE)
    check("표 헤더가 없으면 형식 위반", not RG.format_ok("### M\n산문뿐"))


def test_consumer_canaries_format_invalid():
    from master.events import consumer as C
    root, p = fixture()
    p.canary = root / "_sf" / "loss.jsonl"

    class R:
        to_commit = "abc"
        review_written = ""
        review_note = ""
        canary_write_failed = 0

    r = R()
    C._auto_review(p, ["Source/M/A.cpp"], r,
                   review_run=lambda *a: RG.ReviewResult(written="/tmp/x.md", format_ok=False))
    check("[중요] 형식 위반은 저장돼도 카나리다 (소비자 기준 유실)",
          p.canary.exists() and "review-format-invalid" in p.canary.read_text(encoding="utf-8"))
    check("note 가 사람에게 말한다", "형식 위반" in r.review_note, r.review_note)


def test_failure_reasons_are_never_silent() -> None:
    """[중요] **모든 실패 경로가 사유를 남긴다** (`#285`, 사용자 지시 2026-08-23).

    실측된 대가: NS 리뷰 26건이 *"응답 없음"* 으로 기록됐는데 진짜 원인은 systemd 유닛에
    PATH 가 없어 `which` 가 실패한 것이었다. **없는 로그보다 틀린 로그가 비싸다** —
    「응답 없음」은 서비스 장애로 읽혀 엉뚱한 곳을 파게 만든다. 원전
    `master_orchestrator/common.call_agy` 는 처음부터 갈라 놨다(이식 누락 복구).
    """
    import io as _io
    import sys as _sys
    from master import layer2_verify as l2

    print("\n[사유] 실패 경로마다 사유가 남는가")

    # ── ① 실행파일 부재 — 쿨다운이 아니라 **설정 오류**다
    # [주의] 이 기계에는 `agy` 가 PATH 에 **있다.** 부재 경로를 재려면 PATH 를 비워야 한다 —
    #    안 그러면 실제 CLI 를 호출해 타임아웃이 나고, 그것은 다른 사유다(테스트가 잡았다).
    import os as _os
    buf, old = _io.StringIO(), _sys.stderr
    saved_path = _os.environ.get("PATH", "")
    _sys.stderr = buf
    _os.environ["PATH"] = ""
    try:
        out, why = l2.call_agy_why("ping", timeout=1)
    finally:
        _os.environ["PATH"] = saved_path
        _sys.stderr = old
    check("[중요] 실행파일 부재를 사유로 돌려준다", out is None and l2.MISSING_EXE in why, why)
    check("  PATH 를 지목한다 (고칠 곳이 코드가 아니라 환경이다)", "PATH" in why, why)
    check("  로그에도 남는다", "agy" in buf.getvalue() and "PATH" in buf.getvalue(),
          buf.getvalue()[:120])
    # [중요] **사유에 OS 를 박지 않는다** — 이 모듈은 윈도우 작업장에서도 돈다.
    #    첫 구현은 상수에 "systemd" 를 넣어 `.2`·`.33` 에서 거짓 사유가 되게 했다.
    check("[중요] 상수가 OS 중립이다 (윈도우에서도 참이어야 한다)",
          "systemd" not in l2.MISSING_EXE and "유닛" not in l2.MISSING_EXE, l2.MISSING_EXE)
    hint = l2.missing_exe_hint("agy")
    check("  힌트는 이 플랫폼을 말한다", ("리눅스" in hint) != ("윈도우" in hint), hint)

    # ── ② rc != 0 — stderr 를 버리지 않는다 (종전엔 버렸다)
    out, why = l2._run(["/bin/sh", "-c", "echo 상세원인 1>&2; exit 3"], timeout=5)
    check("[중요] rc 와 stderr 를 함께 남긴다",
          out is None and "rc=3" in why and "상세원인" in why, why)

    # ── ③ 타임아웃 · ④ 빈 출력 — 서로 구별된다
    out, why = l2._run(["/bin/sh", "-c", "sleep 5"], timeout=1)
    check("타임아웃을 그렇게 말한다", out is None and "타임아웃" in why, why)
    out, why = l2._run(["/bin/true"], timeout=5)
    check("빈 출력을 그렇게 말한다", out is None and "빈 출력" in why, why)
    out, why = l2._run(["/bin/echo", "hi"], timeout=5)
    check("성공은 사유가 없다", (out or "").strip() == "hi" and why == "", f"{out!r} {why!r}")

    # ── ⑤ 네 갈래가 **서로 다른 문장**이어야 한다 (뭉개면 고칠 곳을 못 찾는다)
    whys = {l2.MISSING_EXE,
            l2._run(["/bin/sh", "-c", "exit 3"], timeout=5)[1],
            l2._run(["/bin/sh", "-c", "sleep 5"], timeout=1)[1],
            l2._run(["/bin/true"], timeout=5)[1]}
    check("[중요] 네 사유가 서로 다르다", len(whys) == 4, str(whys))

    # ── ⑥ 체인 실패가 **백엔드별 사유**를 예외에 싣는다
    def dead_missing(prompt, *, timeout=0, **kw):
        return None, l2.MISSING_EXE

    def dead_rc(prompt, *, timeout=0, **kw):
        return None, "rc=1: 쿼터 초과"

    saved = l2.WHY_BACKENDS
    # [주의] 체인 길이·이름에 묶지 않는다 — 2026-09-06 에 codex 가 1순위로 들어왔다
    l2.WHY_BACKENDS = [("agy", dead_missing), ("claude", dead_rc)]
    try:
        RG.commercial_chat("x", timeout=1)
        check("[중요] 둘 다 실패하면 예외", False, "예외가 안 났다")
    except RG.ReviewChatError as e:
        msg = str(e)
        check("[중요] 예외가 백엔드별 사유를 싣는다",
              "agy" in msg and "claude" in msg and "PATH" in msg and "쿼터" in msg, msg)
        check("  「응답 없음」으로 뭉개지 않는다", "응답 없음" not in msg, msg)
    finally:
        l2.WHY_BACKENDS = saved


def test_synth_paths_log_their_gaps() -> None:
    """[중요] 합성기의 **grounding 구멍**도 말한다 (`#285`).

    NS 실측: 사실 게이트 거부 사유가 *"실측 선언 클래스를 하나도 언급하지 않았다"* 였다 —
    선언 근거가 비면 모델이 파일을 혼동한다. 그 구멍이 조용하면 **모델 탓과 환경 탓을 구분할
    수 없다.**
    """
    import io as _io
    import sys as _sys
    from master.context_search.paths import ProjectPaths
    from master.context_synth import synth as CS

    print("\n[사유] 합성 경로의 구멍이 보이는가")
    tmp = Path(tempfile.mkdtemp(prefix="ax-synthlog-"))
    p = ProjectPaths(name="없는프로젝트", root=tmp / "X")
    buf, old = _io.StringIO(), _sys.stderr
    _sys.stderr = buf
    try:
        out = CS.collect_related(p, "Source/A", ["Source/A.cpp"], "")
    finally:
        _sys.stderr = old
    check("검색기를 못 열면 빈 목록", out == [], str(out))
    check("[중요] 그 사실을 말한다", "검색기를 열지 못했다" in buf.getvalue(),
          buf.getvalue()[:150])
    shutil.rmtree(tmp, ignore_errors=True)



def test_generation_chain_is_codex_first_but_verification_is_not() -> None:
    """🔴 **쓰는 일은 코덱스, 보는 일은 아니다** (사용자 결정 2026-09-06).

    생성(리뷰 응답·계획·레시피)에는 교차 계열 조건이 없어 codex 가 1순위다.
    [중요] **검증(`BACKENDS`)에는 codex 를 넣지 않는다** — 작성 레인이 codex 이므로 넣는 순간
    자기가 쓴 것을 자기가 통과시킨다.
    """
    print("\n[체인] 생성은 codex 1순위 · 검증은 codex 없음 (2026-09-06)")
    from master import layer2_verify as l2
    from master.work import lanes as LN
    names = [n for n, _ in l2.WHY_BACKENDS]
    check("🔴 생성 체인 1순위가 codex", names[0] == "codex", str(names))
    check("  그다음 agy, 마지막 claude", names[1:] == ["agy", "claude"], str(names))
    vnames = [n for n, _ in l2.BACKENDS]
    check("🔴 [중요] 검증 체인에는 codex 가 없다 (교차 계열)", "codex" not in vnames, str(vnames))
    # 본문 작성 체인은 이 생성 체인과 별개다 — #788 결정(2026-10-10)으로 agy 가 1순위가 됐다.
    # 그래서 교차 계열은 고정 순서가 아니라 `exclude_author`(#379)가 작성자마다 지킨다.
    check("  본문 작성 레인은 별도 체인 — agy → codex → claude → 로컬 (#788)",
          LN.DEFAULT_LANES[:3] == ("agy", "codex", "claude"), str(LN.DEFAULT_LANES))
    for author in LN.DEFAULT_LANES[:3]:
        kept = [n for n, _ in l2.exclude_author(l2.BACKENDS, author)]
        check(f"  작성자 {author} → 검증자에 같은 계열이 없다",
              l2.family_of(author) not in {l2.family_of(n) for n in kept}, str(kept))

def test_serial_travels_to_journal():
    """[중요] 번호(`#627`)는 **결과 필드로** 소비자 요약 줄까지 간다 — `review_commit` 의 `log` 는
    소비자가 `logf` 를 안 넘겨 빈 함수라, 로그로만 넣으면 저널에 안 보인다(실측 2026-09-16)."""
    from master.events import consumer as C
    from master.context_synth import fix_index as FX
    root, p = fixture()
    c = commit_change(p, "int S() { return 1; }\n", msg="번호")
    r = RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: CANNED)
    check("[중요] 리뷰 결과가 번호를 들고 나온다",
          bool(r.written) and r.serial == "R1" and not r.serial_error, f"{r.serial} {r.serial_error}")

    class RR:
        to_commit = c
        review_written = ""
        review_note = ""
        canary_write_failed = 0
        review_serial = ""
    rr = RR()
    C._auto_review(p, ["Source/M/A.cpp"], rr, commit="deadbeef", review_run=lambda *a: r)
    check("[중요] 소비자가 번호를 받는다", rr.review_serial == "R1", rr.review_serial)
    s = C.ProjectResult(project_id="NS", review_written="x", review_serial="R1").summary
    check("[중요] 요약 줄에 「리뷰 1 (R1)」", "리뷰 1 (R1)" in s, s)
    s2 = C.ProjectResult(project_id="NS", review_written="x").summary
    check("번호가 없으면 없다고 찍는다", "번호 없음" in s2, s2)

    FX.index_path(p.root).write_text("{깨짐", encoding="utf-8")
    c2 = commit_change(p, "int S() { return 2; }\n", msg="번호2")
    r2 = RG.review_commit(p, c2, ["Source/M/A.cpp"], chat=lambda pr: CANNED)
    check("[중요] 색인이 깨져도 리뷰는 저장된다", bool(r2.written), str(r2))
    check("  번호 실패 사유가 남는다", r2.serial == "" and r2.serial_error == "FixIndexError",
          r2.serial_error)


# ── ⑤ 골조 지시 이행 절 (`#815` ④) ────────────────────────────

# 변경 전 코드로 잰 해시 (2026-10-18). intent=False 프롬프트는 바이트 단위로 그대로여야 한다
# [주의] `bp-*` 넷은 `#846`(2026-10-30)이 **일부러** 다시 쟀다 — `_SCOPE_RULES` 한 덩이를 넣었다.
#    갱신 전에 「새 프롬프트에서 그 덩이만 빼면 옛 해시와 같다」를 넷 다 확인했다(`ex-*` 는 그대로).
#    계약은 여전히 「intent=False 는 intent 절 외에 다른 것이 섞이지 않는다」다.
_GOLD_DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,1 @@\n-import json, os\n+import os\n"
_GOLDEN = {
    "bp-unreal-False": "fec46f197150526ae43e4e79272442e4a4a0bb2ca3cf47d6184cdd845c706ef4",
    "bp-unreal-True": "07b61c0d81de6cf9b8b72f9edab1447f11cae6a9a45bb76c9e24d57b9989be5f",
    "ex-unreal": "2af61ce6d0e2d718d4941bb5803984f1c6cd4f7f467c408d41b777496173dfb4",
    "bp-code-False": "05b8d8b82fe48bdc3cfbc2d8715f19f756f6393836b7d677426cf57c1c23d802",
    "bp-code-True": "1d572908429386cb10036a3a6a54fed9840a36af3cc27ce04c244a9ce8a5dd52",
    "ex-code": "a20d07d0218e1bd4f3456bb43bb92318d322308e6d4177ed96b61b48b902263e",
}

_PSEUDO_DIFF = ("--- a/m.py\n+++ b/m.py\n@@ -1,3 +1,2 @@\n"
                "-# [PSEUDO] 실패하면 False 를 돌려준다\n"
                "-# [DOC] 이름 있는 함수로\n"
                " def f():\n+    return True\n")


def test_scope_rules():
    """`#846` — 퇴고 에이전트의 작업 범위 규칙이 모든 리뷰 프롬프트에 한 번씩 들어간다."""
    for kind in ("unreal", "code"):
        for intent in (False, True):
            pr = RG.build_prompt(diff=_GOLD_DIFF, files=["x.py"], commit="abcdef1234567890",
                                 kind=kind, intent=intent)
            check(f"#846 범위 규칙 한 번 ({kind}, intent={intent})", pr.count(RG._SCOPE_RULES) == 1)
            check(f"#846 규칙은 DIFF 보다 앞이다 ({kind}, intent={intent})",
                  pr.index(RG._SCOPE_RULES) < pr.index("## DIFF"))
    for word in ("테스트", "find", "바로 리뷰를 출력"):
        check(f"#846 규칙 문구: {word}", word in RG._SCOPE_RULES)


def test_intent_section_only_when_pseudo_removed():
    import hashlib
    for kind in ("unreal", "code"):
        for gnd in ("", "## 선언부\nclass A"):
            pr = RG.build_prompt(diff=_GOLD_DIFF, files=["x.py"], commit="abcdef1234567890",
                                 domains="d", grounding=gnd, kind=kind)
            key = f"bp-{kind}-{bool(gnd)}"
            check(f"[중요] [PSEUDO] 없는 프롬프트는 종전과 바이트 단위로 같다 ({key})",
                  hashlib.sha256(pr.encode()).hexdigest() == _GOLDEN[key])
        check(f"[중요] 예시도 종전 그대로 ({kind})",
              hashlib.sha256(RG.format_example(kind).encode()).hexdigest() == _GOLDEN[f"ex-{kind}"])

    check("지워진 [PSEUDO] 를 센다 ([DOC]·추가 줄·파일 머리는 안 센다)",
          RG.removed_pseudo_lines(_PSEUDO_DIFF) == 1, str(RG.removed_pseudo_lines(_PSEUDO_DIFF)))
    check("추가된 [PSEUDO] 는 지시 이행 흔적이 아니다",
          RG.removed_pseudo_lines("+# [PSEUDO] x\n--- a/[PSEUDO].py\n") == 0)
    check("빈 diff 는 0", RG.removed_pseudo_lines("") == 0)

    for kind in ("unreal", "code"):
        pr = RG.build_prompt(diff=_PSEUDO_DIFF, files=["m.py"], commit="abcdef1234567890",
                             kind=kind, intent=True)
        check(f"[중요] intent 프롬프트에 4절 규칙·표 헤더가 있다 ({kind})",
              "## 4. 골조 지시 이행" in pr and RG._INTENT_HEADER in pr
              and "골조 모순" in pr and "불이행" in pr)
        check(f"  빈 표 규칙(자리표시 금지)을 4절에도 말한다 ({kind})",
              "모든 지시가 이행됐으면 표 헤더만" in pr)
        ex = RG.format_example(kind, intent=True)
        check(f"  예시가 3절 뒤에 빈 4절 표를 둔다 ({kind})",
              ex.index("## 3. 영향 분석") < ex.index("## 4. 골조 지시 이행")
              and RG.parseable_rows(ex) == 1, str(RG.parseable_rows(ex)))


def test_intent_format_is_fail_closed():
    old = ("### M\n\n## 1. 변경분 코딩 컨벤션\n"
           "| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n\n"
           "## 2. 변경분 버그·안전성\n"
           "| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n|---|---|---|---|---|\n")
    check("[중요] 4절 없는 옛 리뷰는 그대로 형식 준수", RG.format_ok(old))
    check("[중요] 4절을 요청했는데 없으면 형식 위반 (1·2절과 같은 fail-closed)",
          not RG.format_ok(old, intent=True))
    with4 = old + "\n## 4. 골조 지시 이행\n" + RG._INTENT_HEADER + "\n|---|---|---|---|---|\n"
    check("  4절 표 헤더가 있으면 통과 (빈 표 정상)", RG.format_ok(with4, intent=True))

    root, p = fixture()
    commit_change(p, "// [PSEUDO] 1 을 돌려준다\nint F();\n", msg="골조")
    c = commit_change(p, "int F() { return 2; }\n", msg="[task:t1] worker=w target=A.cpp")
    calls, logs = [], []

    def no_section4(prompt):
        calls.append(prompt)
        return CANNED

    r = RG.review_commit(p, c, ["Source/M/A.cpp"], chat=no_section4,
                         logf=lambda k, m: logs.append(m))
    check("조각 커밋의 지워진 [PSEUDO] 를 센다", r.pseudo_removed == 1, str(r.pseudo_removed))
    check("[중요] 첫 프롬프트가 4절을 싣는다", calls and "## 4. 골조 지시 이행" in calls[0])
    check("[중요] 4절이 빠진 응답은 재시도한다", r.retried and len(calls) == 2, str(len(calls)))
    check("  재시도 예시도 4절을 싣는다",
          len(calls) == 2 and calls[1].index(RG._INTENT_HEADER) < calls[1].index("## 커밋"))
    check("[중요] 두 번 다 빠지면 format_ok=False", r.format_ok is False)
    check("요청 여부·줄 수를 로그 한 줄로 남긴다",
          any("골조 지시 이행 절 요청 — 지워진 [PSEUDO] 1줄" in m for m in logs), str(logs))

    good = CANNED.rstrip() + "\n\n## 4. 골조 지시 이행\n" + RG._INTENT_HEADER + "\n|---|---|---|---|---|\n"
    r2 = RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: good)
    check("4절이 있으면 재시도 없이 통과", r2.format_ok and not r2.retried)

    c3 = commit_change(p, "int F() { return 3; }\n", msg="사람 변경")
    calls3, logs3 = [], []
    r3 = RG.review_commit(p, c3, ["Source/M/A.cpp"], chat=lambda pr: calls3.append(pr) or CANNED,
                          logf=lambda k, m: logs3.append(m))
    check("[중요] [PSEUDO] 없는 커밋은 4절을 요청하지 않는다",
          "## 4. 골조 지시 이행" not in calls3[0] and r3.format_ok and not r3.retried)
    check("  미요청도 로그로 남긴다", any("미요청 — 지워진 [PSEUDO] 0줄" in m for m in logs3), str(logs3))


def test_diff_cap_is_opt_out():
    """`#888` — 기본은 종전 24,000자 상한, `diff_max_chars=None` 만 자르지 않는다."""
    root, p = fixture()
    big = "int F() {\n" + "".join(f"  int v{i} = {i};\n" for i in range(3000)) + "  return 1;\n}\n"
    c = commit_change(p, big, msg="큰 변경")
    files = ["Source/M/A.cpp"]
    full = RG.commit_diff(p.repo, files, c, max_chars=None)
    check("#888 큰 diff 픽스처는 상한보다 크다", len(full) > RG.DIFF_MAX_CHARS, str(len(full)))
    check("#888 None 이면 자르지 않는다", "(diff 가 잘렸다" not in full and "int v2999 = 2999;" in full)
    capped = RG.commit_diff(p.repo, files, c)
    check("#888 기본은 종전 상한으로 자른다", "(diff 가 잘렸다" in capped
          and len(capped) < len(full), str(len(capped)))
    seen = []
    RG.review_commit(p, c, files, chat=lambda pr: seen.append(pr) or CANNED)
    check("#888 review_commit 기본은 잘린 diff (직접 호출자 종전 그대로)",
          seen and "(diff 가 잘렸다" in seen[0] and "int v2999 = 2999;" not in seen[0])
    seen.clear()
    RG.review_commit(p, c, files, chat=lambda pr: seen.append(pr) or CANNED, diff_max_chars=None)
    check("#888 diff_max_chars=None 은 온전한 diff",
          seen and "(diff 가 잘렸다" not in seen[0] and "int v2999 = 2999;" in seen[0])
    shutil.rmtree(root)


# ── `#946` T3·T4 — 일감·태스크 컨텍스트 주입 ───────────────────────────────

_ISSUE_SEC = ("## 일감·태스크 컨텍스트 (참고 — 작성자가 밝힌 의도다)\n의도 문장\n\n"
              "### 일감 #946 제목\n### 이 커밋이 밝힌 태스크\n- T3 [대기] 목표: 주입\n")


def test_issue_context_injection():
    base = dict(diff="+x", files=["Source/M/A.cpp"], commit="c" * 40, grounding="근거")
    plain = RG.build_prompt(**base)
    check("#946 빈 두 인자는 종전과 같다", RG.build_prompt(**base, issue_context="", message="") == plain)
    with_ctx = RG.build_prompt(**base, issue_context=_ISSUE_SEC, issue_tasks=True)
    check("#946 일감 절이 실린다", _ISSUE_SEC.rstrip() in with_ctx)
    check("#946 일감 절은 실측 근거 뒤 · 변경 파일 앞",
          with_ctx.index("## 실측 근거") < with_ctx.index("## 일감·태스크 컨텍스트")
          < with_ctx.index("## 커밋 cccccccccccc 의 변경 파일"))
    check("#946 대조 규칙(이 커밋이 밝힌 태스크 · 다른 T# 몫 지적 금지)이 실린다",
          "변경분이 이 커밋이 밝힌 태스크(T#)" in with_ctx
          and "다른 태스크(다른 T#)에 배정된 작업이 이 변경에 없는 것은 결함으로 지적하지 않는다" in with_ctx
          and "검증된 사실이 아니다" in with_ctx)
    check("#946 일감 절 없으면 규칙도 없다", "다른 T#" not in plain and "일감·태스크" not in plain
          and "일감 대조" not in plain)
    check("#946 issue_context 없으면 issue_tasks 는 무시된다",
          RG.build_prompt(**base, issue_tasks=True) == plain)
    general = RG.build_prompt(**base, issue_context=_ISSUE_SEC)
    check("🔴 #946 T# 없음(기본 issue_tasks=False) — 일반 한 줄만, 태스크 두 줄 없음",
          "- 일감 대조:" in general and "일감의 의도와 어긋나는 변경은 2절에 지적한다" in general
          and "밝힌 태스크(T#)" not in general and "다른 T#" not in general)
    check("#946 T# 있음 — 일반 한 줄 + 태스크 두 줄",
          "- 일감 대조:" in with_ctx and with_ctx.count("다른 태스크(다른 T#)") == 1)
    msg_only = RG.build_prompt(**base, message="feat: 제목\n\n본문 줄")
    check("#946 메시지만 — 메시지 원문 절 + 검증되지 않은 의도 문구",
          "## 커밋 메시지 (참고 — 작성자의 서술이다)" in msg_only and "본문 줄" in msg_only
          and "검증되지 않은 의도 설명이다" in msg_only)
    check("🔴 #946 메시지만이면 일감 대조 규칙이 없다(일감을 못 찾았다)",
          "다른 T#" not in msg_only and "일감·태스크" not in msg_only and "일감 대조" not in msg_only)
    check("#946 메시지 절도 변경 파일 앞", msg_only.index("## 커밋 메시지") < msg_only.index("의 변경 파일"))
    check("#946 공백 메시지는 절이 없다", RG.build_prompt(**base, message="  \n") == plain)
    rng = RG.build_prompt(**base, subject="일감 #946 범위 a..b", history="### h c1",
                          issue_context=_ISSUE_SEC, issue_tasks=True)
    check("#946 범위 변형 규칙은 커밋별 T# 를 말한다", "이 범위의 커밋들이(커밋별 T#) 밝힌 태스크" in rng)
    check("#946 범위 — 기존 수정 기록 절은 그대로", "## 수정 기록 (참고" in rng)


def test_review_commit_passes_context():
    root, p = fixture()
    c = commit_change(p, "int F() { return 5; }\n", msg="feat(#946 T3): 주입")
    seen = []
    RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: seen.append(pr) or CANNED)
    check("#946 review_commit 기본은 메시지·일감 절 없음(종전)",
          seen and "## 커밋 메시지" not in seen[0] and "일감·태스크" not in seen[0])
    seen.clear()
    RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: seen.append(pr) or CANNED,
                     message="feat(#946 T3): 주입", issue_context=_ISSUE_SEC, issue_tasks=True)
    check("#946 일감 절이 있으면 메시지 절은 따로 안 싣는다(절 안에 원문이 있다)",
          seen and _ISSUE_SEC.rstrip() in seen[0] and "## 커밋 메시지 (참고" not in seen[0])
    check("#946 review_commit 이 issue_tasks 를 넘긴다", seen and "다른 태스크(다른 T#)" in seen[0])
    seen.clear()
    RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: seen.append(pr) or CANNED,
                     message="feat: 옛 꼴 (#946)", issue_context=_ISSUE_SEC)
    check("#946 review_commit issue_tasks 기본은 일반 한 줄만",
          seen and "- 일감 대조:" in seen[0] and "다른 T#" not in seen[0])
    seen.clear()
    RG.review_commit(p, c, ["Source/M/A.cpp"], chat=lambda pr: seen.append(pr) or CANNED,
                     message="feat(#946 T3): 주입")
    check("#946 일감 절이 없으면 메시지 원문 절", seen and "## 커밋 메시지 (참고" in seen[0]
          and "feat(#946 T3): 주입" in seen[0] and "다른 T#" not in seen[0])
    # 메시지 읽기 도우미 — Co-Authored-By 는 뺀다
    c2 = commit_change(p, "int F() { return 6; }\n",
                       msg="fix(#946 T4): 범위\n\n본문\n\nCo-Authored-By: X <x@x>")
    check("#946 commit_message 는 제목+본문, 서명 제외",
          RG.commit_message(p.repo, c2) == "fix(#946 T4): 범위\n\n본문", repr(RG.commit_message(p.repo, c2)))
    check("#946 commit_message 실패는 빈 문자열", RG.commit_message(p.repo, "없는커밋") == "")
    rows = RG.range_messages(p.repo, c, c2)
    check("#946 range_messages 는 (해시, 메시지) 오래된 것부터",
          rows == [(c2, "fix(#946 T4): 범위\n\n본문")], str(rows))
    check("#946 range_messages 실패는 None", RG.range_messages(p.repo, "없는", c2) is None)
    shutil.rmtree(root)


def main() -> int:
    for fn in (test_serial_travels_to_journal,
               test_trivial_detection, test_author_exclusion_skips_before_llm,
               test_format_validation_and_retry, test_consumer_canaries_format_invalid,
               test_report_is_parseable_by_origin_collector, test_prompt_carries_the_contract,
               test_consumer_wiring_failure_goes_to_canary,
               test_failure_reasons_are_never_silent, test_synth_paths_log_their_gaps,
               test_generation_chain_is_codex_first_but_verification_is_not,
               test_intent_section_only_when_pseudo_removed, test_intent_format_is_fail_closed,
               test_scope_rules, test_diff_cap_is_opt_out,
               test_issue_context_injection, test_review_commit_passes_context):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_review_gen: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
