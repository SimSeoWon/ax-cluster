"""`#740` 파일 간 응답 중복 — 조각 1(session_usage)·조각 2(usage_dashboard)의 계약 검사.

    .venv/bin/python master/test_session_usage_dedupe.py

[DOC] 사용자 결정 2026-10-09 (가): 같은 (host, mid) · 같은 값 → 한 번만 · 값이 다르면 둘 다 세고 경고.
      실 LLM·SSH·네트워크 0 — 임시 디렉토리에 스냅샷 JSON 을 손으로 만들어 쓴다. 출력 형식은 저장소 관례
      (`check()` 와 마지막 줄 `OK|FAIL test_session_usage_dedupe: N/M 통과`)를 따른다.
      스냅샷 모양: {"host","tool","session_id","origin","collected_at","project","work_id","task_id","records":[…]}
      레코드 모양: {"ts","model","input","output","cache_read","cache_create","reasoning","mid"}
[DOC] 검사할 계약(전부):
      1 parse_claude 가 레코드에 mid 를 남긴다 · 파일 안의 같은 id 는 여전히 한 번만
      2 same_usage — 값이 같으면 참 · 하나라도 다르면 거짓 · ts 차이는 무시
      3 cross_file_duplicates — 두 파일에 같은 값(같음 1) · 세 번째 파일에 다른 값(충돌 1) · mid 없는 레코드
        (no_mid) · 깨진 파일(unreadable) · 반환 키가 전부 있다 · conflicts 에 절대 경로가 없다
      4 usage_dashboard.build_report(source="session") — 같음은 한 번만 합산(totals.tokens 가 줄어든다) ·
        duplicate_records 1 · 충돌은 둘 다 합산 · duplicate_conflicts 1 · 고정 경고 문구 · source="dispatch" 여도
        두 키가 0 으로 있다
      build_report 는 projects_root(빈 등록부)·queue_root·session_store·now 를 주입해 결정적으로 돈다 —
      기존 master/test_usage_dashboard.py 의 주입 방식을 그대로 본뜬다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label} — {detail}")


def main() -> int:
    # [DOC] 위 계약 1~4 를 함수 하나씩으로 나눠 부르고, 각 함수는 자기 임시 디렉토리를 만들고 지운다.
    # [PSEUDO] 계약 1~4 검사 함수를 만들고 여기서 차례로 부른다.
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
