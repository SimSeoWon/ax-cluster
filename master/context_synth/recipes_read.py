"""레시피·안티패턴 **읽기** — 컨벤션 루프의 반대 방향 (`#267`).

## 왜 별 모듈인가

`recipes_synthesizer.py`(원전 629줄 이식) 독스트링이 이 구멍을 **스스로 적어 뒀다**:
*"[주의] 읽기 도구(find_recipes/get_anti_patterns — code-writer 가 작업 시작 시 부르는 …)"*.
합성은 이식됐고 **읽는 쪽만 없었다** — 그래서 루프가 한 방향이었다.

원전 주석이 호출 시점까지 못박아 뒀다: *"code-writer 에이전트는 **작업 시작 직후에 호출**해
step-by-step 가이드를 컨텍스트로 받는다."*

## [중요] 이식의 갈림길 — 경로 권위는 마스터다

원전은 `.claude/recipes/*.md` 를 **로컬에서** 읽었다. 그 데몬이 UE5 프로젝트 안에 살았기
때문이다. 우리 위상은 다르다 — 레시피는 **마스터 트윈**(`<프로젝트>/recipes/`)에 있고
**요청자 기계엔 그 디렉토리가 없다.** 그래서 `signals`·`history`·`thesaurus` 와 **같은 대행
구조**를 쓴다: 클라 MCP → 큐 API → 마스터가 파일을 읽는다.

[주의] 클라가 레시피 디렉토리를 직접 읽으면 `#267` 완료 조건 2 미달이다.

## [중요] 「없음」과 「고장」을 구분한다

원전이 빈 상태에 **사유 문장**을 돌려준다 — *"합성된 레시피가 아직 없습니다. 신호가 누적되면
주기 합성에서 생성됩니다."* 빈 배열만 돌려주면 부르는 쪽이 고장과 구분할 수 없다. 그 규약을
글자까지 옮긴다(이 저장소가 반복해 배운 것과 같은 결이다).
"""
from __future__ import annotations

import re
from pathlib import Path

from .recipes_synthesizer import ANTI_PATTERNS_FILENAME, recipes_dir

# 원전 `mcp/code_recipes/server.py` 의 규약 — 밑줄로 시작하는 파일은 레시피가 아니다
#    (`_signals.jsonl` · `_anti_patterns.md` · 아카이브).
EMPTY_RECIPES = "합성된 레시피가 아직 없습니다. 신호가 누적되면 주기 합성에서 생성됩니다."
EMPTY_ANTI = ("안티패턴 카탈로그가 아직 없습니다. rejected_approaches 신호가 누적되면 다음 "
              "합성 사이클에서 생성됩니다.")
_TOKEN = re.compile(r"[\w가-힣]+")


def _frontmatter(text: str) -> tuple:
    """`---` 프론트매터 → `(dict, 본문)`. [주의] YAML 파서를 쓰지 않는다 — 원전도 그렇고,
    레시피 프론트매터는 스칼라·리스트 한 겹이다. 파서를 들이면 실패 모드가 늘어난다."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    head, body = text[3:end], text[end + 4:]
    meta: dict = {}
    for line in head.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k] = v.strip("'\"")
    return meta, body


def _files(paths) -> list:
    d = recipes_dir(paths)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md") if not p.name.startswith("_"))


def find(paths, query: str, n_results: int = 3) -> dict:
    """의도·키워드로 레시피를 찾는다 — **키워드·태그 매칭**(원전과 같다, 벡터 아님).

    [주의] 벡터 검색으로 「개선」하지 않는다. 원전이 *"레시피 양이 늘어나면 별도 인덱싱 도입
    가능"* 이라고 적어 뒀고, 지금 레시피는 한 자릿수다 — 없는 문제를 미리 풀면 실패 모드만 는다.
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "query 는 필수다 — 무엇을 하려는지가 매칭의 근거다"}
    files = _files(paths)
    if not files:
        return {"ok": True, "matches": [], "total_recipes": 0, "message": EMPTY_RECIPES}
    tokens = set(t.lower() for t in _TOKEN.findall(q.lower()))
    scored = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, body = _frontmatter(text)
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        name = meta.get("recipe_name") or p.stem
        intent = meta.get("intent") or ""
        hay = " ".join([str(name), " ".join(str(t) for t in tags), str(intent),
                        body[:1200]]).lower()
        hay_tokens = set(_TOKEN.findall(hay))
        # 원전과 같은 결: **정확 일치에 가중치**, 부분 일치는 낮게
        score = 0
        for t in tokens:
            if t in hay_tokens:
                score += 3
            elif t in hay:
                score += 1
        # 태그·이름에 걸리면 더 무겁게 — 그것이 저자가 붙인 색인이다
        label = (str(name) + " " + " ".join(str(x) for x in tags)).lower()
        score += 2 * sum(1 for t in tokens if t in label)
        if score <= 0:
            continue
        scored.append({"score": score, "recipe_name": str(name), "intent": str(intent),
                       "tags": [str(x) for x in tags], "file": p.name,
                       "preview": body.strip()[:400]})
    scored.sort(key=lambda x: (-x["score"], x["recipe_name"]))
    top = scored[:max(1, int(n_results or 3))]
    out = {"ok": True, "query": q, "matches": top, "total_recipes": len(files)}
    if not top:
        # [중요] **막다른 답을 주지 않는다 — 목록을 준다.**
        #
        # 실측 2026-08-23 (라이브 런): 신호는 한글인데 **합성된 레시피는 전부 영문**이다
        # (원전 규약 — 그 저장소 history 에 *"레시피_피드백캡처_영문화"* 가 있다). 그래서
        # 한글 질의 *"미션 태스크 추가"* 가 `MissionTaskDefinition` 레시피를 **못 찾는다**.
        # 원전 독스트링의 예시 질의도 같은 이유로 안 걸렸을 것이다 — 이식하며 처음 드러났다.
        #
        # [주의] 한글↔영문 사전을 여기 심지 않는다. 이 저장소엔 이미 그 일을 하는 것이 있고
        # (온톨로지 시소러스 · `resolve_terms`), 두 벌을 만들면 갈라진다. 대신 **있는 것을
        # 보여 준다** — 부르는 쪽은 에이전트이고, 목록을 보면 스스로 고를 수 있다.
        out["catalog"] = [
            {"recipe_name": str((_frontmatter(p.read_text(encoding="utf-8", errors="replace"))[0]
                                 .get("recipe_name")) or p.stem),
             "intent": str(_frontmatter(p.read_text(encoding="utf-8", errors="replace"))[0]
                           .get("intent") or ""),
             "file": p.name}
            for p in files[:30]
        ]
        out["message"] = (
            f"이 질의로는 걸리는 것이 없다 — 레시피 {len(files)}건의 목록을 대신 낸다. "
            f"[중요] 레시피는 **영문으로 합성된다**(원전 규약)이라 한글 질의가 못 걸릴 수 있다. "
            f"목록의 `recipe_name`·`intent` 를 보고 다시 묻거나, 식별자(예: MSMissionTask)로 "
            f"물어볼 것")
    return out


def anti_patterns(paths) -> dict:
    """안티패턴 카탈로그. **`exists` 로 「없음」을 명시한다**(원전 규약)."""
    p = recipes_dir(paths) / ANTI_PATTERNS_FILENAME
    if not p.is_file():
        return {"ok": True, "exists": False, "message": EMPTY_ANTI}
    try:
        meta, body = _frontmatter(p.read_text(encoding="utf-8", errors="replace"))
    except OSError as e:
        # [중요] 읽기 실패를 「없음」으로 접지 않는다 — 고장과 부재는 다른 사고다
        return {"ok": False, "exists": True, "error": f"카탈로그 읽기 실패: {e}"}
    return {"ok": True, "exists": True,
            "last_updated": meta.get("last_updated", ""),
            "total_entries_processed": meta.get("total_entries_processed", "0"),
            "unique_patterns": meta.get("unique_patterns", "0"),
            "content": body.strip()}
