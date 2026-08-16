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


def main() -> int:
    for fn in (test_trivial_detection, test_author_exclusion_skips_before_llm,
               test_format_validation_and_retry, test_consumer_canaries_format_invalid,
               test_report_is_parseable_by_origin_collector, test_prompt_carries_the_contract,
               test_consumer_wiring_failure_goes_to_canary):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_review_gen: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
