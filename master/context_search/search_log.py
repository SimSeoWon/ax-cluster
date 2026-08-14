"""검색 로그 — 원전 `mcp/context_search/cs_common.py` 의 `_log_search` 계열 이식
(소 3.4.5 · `#193`, 2026-08-14).

    detect_lang            질의 언어 휴리스틱 (ko/en/mixed/other) — 원전 그대로
    build_result_details   채널별 rank·score 추출 — 🔴 `Hit` **필드**를 직접 읽는다
    log_search             한 줄 append (+ 회전) — 🔴 검색을 절대 막지 않는다
    read_entries           소비자용 로더 (분석기 `#161` 가 쓴다)

## 🔴 왜 이제 이식하나 — 보류였고, 그 보류를 푸는 근거가 셋 생겼다

`search.py` 머리말이 이식 당시 적어 뒀다: *"검색 로그(`_log_search`, caller/session_id/
work_id) → §5.2-D 로 별도 판단 (감사 계층)"*. **누락이 아니라 의도적 보류**였다. 푸는 근거:

    ① 우리 코드가 이미 요청하고 있다 — `bm25.py`: *"이 규칙은 질의 3개로 정했다. 표본이
       얇다 — `search_log.jsonl` 이 쌓이면…"*
    ② `#161`(원전 `search_log_analyzer` 696줄)의 **입력**이다. 없으면 입력 없는 배치가 된다
    ③ 사용자 지시 2026-08-14: *"작동하는 상태를 만들어야 **실증 로그를 심어서** 문제가 될
       것이 있는지 보고 개선할 게 있는지 찾지"*

## 🔴 원전과 다르게 둔 것 둘 — 근거가 있다

**① 조용히 실패하지 않는다.** 원전은 `_log_search` 와 `_rotate_search_log` 둘 다
`except Exception: pass` 다. **fail-open 자체는 옮긴다** — 로그가 검색을 막으면 그건 더 나쁘다.
하지만 **소리 없이는 안 된다**: 중 4.2 에서 σ 감사(원전 `.claude/reviews/_silent_failure/`)를
이식했고 그 기준이 *"조용한 실패는 결함"* 이다. 그래서 실패를 **반환값으로 돌려주고**
(σ 기준: *"예외를 값으로 돌려주면 조용하지 않다"*) 호출자가 무시할지 고른다.

**② 위치가 프로젝트 밖이다.** 원전은 `<프로젝트>/.claude/search_log.jsonl` 이지만 §5.5 가
*"데이터를 프로젝트 밖으로"* 로 확정했다 → `<프로젝트 데이터>/search_log.jsonl`.
🔴 그리고 이것은 **관측 기록이라 파생물이 아니다** — canary(`permanent_loss.jsonl`)와 같은 결로
지우면 복구되지 않는다. 청소 대상에 넣지 말 것.

## ⚠️ `Hit.to_dict()` 로는 스키마를 채울 수 없다

`to_dict()` 는 `bm25_score`·`vector_rank`·`bm25_rank` 를 **버린다**(응답 축소용). 원전
`result_details` 는 그 셋이 본체다 — 채널 기여도 비교가 목적이므로 **필드를 직접 읽는다.**
`to_dict()` 로 적으면 분석기의 채널 분해가 조용히 전부 비게 된다.

## 🔴 어디서 기록하나 — 표면 전수 (2026-08-14 census)

기준 하나: **사람·에이전트가 던진 질의만 기록한다.** 기계가 스스로 만든 질의를 섞으면 분포가
오염되고, 채널 튜닝의 근거가 오염된 분포 위에 서게 된다. 원전도 `combined_search`(MCP·HTTP
표면) 에서만 기록하고 `watcher/context.py` 는 기록하지 않는다.

| 자리 | 성격 | 기록 |
|---|---|---|
| `projects/mcp_server.search_context_tool` | 사람·에이전트 질의 (MCP) | ✅ |
| `webui/routes.api_search` | 사람 질의 (웹 UI) | ✅ |
| `projects/mcp_server.resolve_terms_tool` | 시소러스 해소 — *"이 표현이 어느 클래스냐"* | ❌ 질의가 아니다 |
| `webui/board.py` | 도메인 보드가 topic 으로 관련 문서 찾기 | ❌ 기계 생성 |
| `work/register.py` · `work/manifest.py` | 파이프라인 내부 수집 | ❌ 기계 생성 |
| `context_synth/synth.py` | 컨텍스트 합성 | ❌ 기계 생성 (원전도 안 한다) |

⚠️ **처음엔 MCP 한 곳만 심었다.** 서비스 재기동을 검증하려다 `api_search` 를 발견했다 —
원전은 **양쪽**에서 기록하므로 한쪽만 심으면 로그가 표면에 따라 편향된다. 🔴 **이식을
「한 자리에 넣었다」로 끝내지 말고 원전이 부르는 자리를 전수로 세라** — census 가 있는 이유다.

## 기록만 해 둔 개선 후보 (사용자 지시: 개선은 기록만)

- `query_used`(시소러스 확장·`focus()` 적용 **후**의 질의) 를 한 필드 더 싣기. 우리 `focus()` 는
  대괄호 밖을 **버리므로** 원전보다 질의가 크게 바뀐다 — 시소러스 갭 분석에 유용할 수 있다.
  🔴 원전에 없는 필드라 지금은 넣지 않는다.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

SEARCH_LOG_MAX_ENTRIES = 2000          # 원전 상수 그대로

_HANGUL_RE = re.compile(r"[가-힣]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# 원전 Phase η.12.16 — 같은 파일에 동시 append 하면 줄이 겹칠 수 있다. `ax-projects` 도
# uvicorn **단일 프로세스**이므로 프로세스 내 락으로 충분하다(워커를 늘리면 무효 — 늘리지 않는다).
_lock = threading.Lock()


def detect_lang(query: str) -> str:
    """질의 언어를 휴리스틱으로 분류한다 — `ko`/`en`/`mixed`/`other`. **원전 그대로.**

    5배 우세 규칙까지 원전과 같다. 바꾸면 언어별 갭 리포트가 과거 데이터와 비교 불가해진다.
    """
    if not query:
        return "other"
    ko = len(_HANGUL_RE.findall(query))
    en = len(_LATIN_RE.findall(query))
    if ko == 0 and en == 0:
        return "other"
    if ko > 0 and en == 0:
        return "ko"
    if en > 0 and ko == 0:
        return "en"
    if ko >= en * 5:
        return "ko"
    if en >= ko * 5:
        return "en"
    return "mixed"


def build_result_details(hits) -> list[dict]:
    """채널별 rank·score 추출. 🔴 `Hit` **필드**를 읽는다 (`to_dict()` 는 셋을 버린다).

    원전과 같은 키 이름을 쓴다 — `vec_rank`·`bm25_rank` 는 분석기가 그 이름으로 읽는다.
    ⚠️ **0 도 의미 있는 값**(1위)이라 `None` 비교로 가른다. truthy 검사로 바꾸면 1위가 사라진다.
    """
    details = []
    for h in hits or []:
        d = {
            "file": getattr(h, "file_id", None),
            "source": getattr(h, "source", None),
            "rrf_score": round(getattr(h, "rrf_score", 0.0) or 0.0, 6),
        }
        if getattr(h, "vector_rank", None) is not None:
            d["vec_rank"] = h.vector_rank
        if getattr(h, "bm25_rank", None) is not None:
            d["bm25_rank"] = h.bm25_rank
        if getattr(h, "similarity", 0):
            d["similarity"] = round(h.similarity, 4)
        if getattr(h, "bm25_score", None) is not None:
            d["bm25_score"] = round(h.bm25_score, 4)
        details.append(d)
    return details


def log_path_for(paths) -> Path:
    """`<프로젝트 데이터>/search_log.jsonl`. §5.5 — 프로젝트 안에 두지 않는다.

    정본은 `ProjectPaths.search_log` 다(데이터 위치는 그 클래스가 소유한다). 여기서 `root`
    로 조립하는 경로는 **그 속성이 없는 호출자**(테스트 대역)를 위한 폴백이다 — 두 곳이
    갈리지 않게 **속성이 있으면 그것을 쓴다.**
    """
    p = getattr(paths, "search_log", None)
    return Path(p) if p is not None else Path(paths.root) / "search_log.jsonl"


def log_search(paths, *, query: str | None = None, hits=None,
               caller: str | None = None, session_id: str | None = None,
               work_id: str | None = None) -> dict:
    """검색 한 건을 기록한다. **반환값으로만** 성패를 말한다 — 예외를 올리지 않는다.

    🔴 **로그가 검색을 막아선 안 된다**(원전의 fail-open 을 옮긴다). 다만 원전처럼 조용히
    삼키지는 않는다 — `{"ok": False, "reason": …}` 을 돌려주므로 호출자가 무시할지 고른다
    (σ 기준: *"예외를 값으로 돌려주면 조용하지 않다"*).

    스키마는 원전 그대로다:

        ts · results · zero_hit(2건 미만일 때만) · query · lang · result_details
        caller · session_id · work_id

    ⚠️ `results`(파일 목록)는 원전이 스스로 *"자동 승급은 영구 비활성이라 회귀 호환 목적만"*
    이라 적어 뒀지만 **스키마는 그대로 둔다** — 분석기가 그 필드를 읽는다.
    """
    hits = list(hits or [])
    if query is None and not hits:
        return {"ok": False, "reason": "질의도 결과도 없다 — 기록할 것이 없다", "written": False}

    payload: dict = {
        "ts": datetime.now().isoformat(),
        "results": [getattr(h, "file_id", None) for h in hits],
    }
    # 🔴 원전 Phase η.12.5 — 2건 미만일 때만 명시한다. *"0건 검색어를 모아 시소러스 후보를
    #    제안"* 하는 배치의 입력 신호이고, 과거엔 2건 미만을 통째로 스킵해 그 데이터가
    #    전혀 쌓이지 않는 갭이었다.
    if len(hits) < 2:
        payload["zero_hit"] = len(hits) == 0
    if query is not None:
        payload["query"] = query
        payload["lang"] = detect_lang(query)
    if hits:
        payload["result_details"] = build_result_details(hits)
    for k, v in (("caller", caller), ("session_id", session_id), ("work_id", work_id)):
        if v is not None:
            payload[k] = v

    p = log_path_for(paths)
    try:
        line = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return {"ok": False, "reason": f"직렬화 실패: {e}", "written": False}

    try:
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            rot = rotate(p)
    except OSError as e:
        # 🔴 fail-open — 검색은 이미 끝났고 사용자는 결과를 받아야 한다.
        return {"ok": False, "reason": f"기록 실패: {e}", "written": False}
    return {"ok": True, "written": True, "path": str(p), "rotated": rot.get("removed", 0)}


def rotate(p: Path) -> dict:
    """최대 건수를 넘으면 오래된 것을 버린다 (원전 `_rotate_search_log`).

    ⚠️ 원전과 같이 **뒤쪽을 남긴다**(최신 우선). 회전 실패도 조용히 넘기지 않고 값으로 돌린다.
    """
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return {"ok": False, "reason": f"읽기 실패: {e}", "removed": 0}
    if len(lines) <= SEARCH_LOG_MAX_ENTRIES:
        return {"ok": True, "removed": 0}
    kept = lines[-SEARCH_LOG_MAX_ENTRIES:]
    try:
        p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "reason": f"쓰기 실패: {e}", "removed": 0}
    return {"ok": True, "removed": len(lines) - len(kept)}


def read_entries(paths, *, limit: int = 0) -> list[dict]:
    """기록을 읽어 온다 (분석기 `#161` 의 입력). 🔴 **깨진 줄은 건너뛰고 세지 않는다.**

    한 줄이 깨졌다고 전체 분석을 포기하면 관측이 사라진다 — 그건 로그의 목적에 반한다.
    `limit` 을 주면 **최신** 그만큼만.
    """
    p = log_path_for(paths)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out[-limit:] if limit else out
