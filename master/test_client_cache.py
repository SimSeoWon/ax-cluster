"""클라이언트 폴백 캐시 (소 3.4.3 · `#162`) — 원전 두 모듈 이식분.

검증하는 것:

    ① [중요] **3분기가 합쳐지지 않는다** — `absent` 는 폴백하지 않고 캐시하지도 않는다
       (합치면 사람이 지운 개념이 캐시에서 되살아난다)
    ② 에러·파싱 불가 응답은 **적재되지 않는다** (캐시 = 마지막 「정상」 데이터)
    ③ stale 응답에 `_stale`·`_cached_at` 이 **주입된다** (표기 없으면 아무도 모른다)
    ④ TTL 이 없다 — 오래돼도 내준다 (온톨로지는 중앙 SSOT)
    ⑤ 초기화 실패는 **한 번만** 시도하고, 실패를 값으로 돌린다
    ⑥ 모르는 `outcome` 은 **예외** — 조용히 `unreachable` 로 접지 않는다
    ⑦ [중요] 벡터 폴백: **해시가 같으면 임베딩을 다시 만들지 않는다**
    ⑧ 벡터 폴백 결과에 `source` 표시가 박힌다 · 임베더는 **우리 다국어 모델**이다

`.venv/bin/python master/test_client_cache.py`
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.clientside.ontology_cache import OntologyCache, is_error_payload   # noqa: E402
from master.clientside import vector_fallback as VF                            # noqa: E402

PASS = FAIL = 0
GOOD = json.dumps({"domain": "MissionRuntime", "objects": ["UManager_Mission"]},
                  ensure_ascii=False)


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── ①⑥ 3분기 ────────────────────────────────────────────────────────────────

def test_three_outcomes_stay_separate():
    with tempfile.TemporaryDirectory() as tmp:
        c = OntologyCache(tmp)

        body, how = c.serve("/onto/domain/MissionRuntime", lambda e: (GOOD, "ok"))
        check("① ok → 서버 응답 그대로", how == "server" and body == GOOD, f"{how} {body[:40]}")
        check("① ok 는 캐시를 워밍한다", c.entries() == 1, str(c.entries()))

        # [중요] absent — 서버가 「없다」고 답했다. 폴백하면 지워진 개념이 되살아난다
        absent_body = json.dumps({"error": "not found"})
        body, how = c.serve("/onto/domain/MissionRuntime", lambda e: (absent_body, "absent"))
        check("① [중요] absent 는 폴백하지 않는다", how == "absent" and body == absent_body,
              f"{how} {body[:40]}")
        check("① [중요] absent 는 캐시도 안 바꾼다",
              json.loads(c.get_stale("/onto/domain/MissionRuntime"))["domain"] == "MissionRuntime")

        body, how = c.serve("/onto/domain/MissionRuntime", lambda e: ("", "unreachable"))
        check("① unreachable → stale 폴백", how == "stale", how)
        check("③ `_stale` 표기가 주입된다", json.loads(body).get("_stale") is True, body[:60])
        check("③ `_cached_at` 도 실린다", bool(json.loads(body).get("_cached_at")), body[:60])

        body, how = c.serve("/onto/none", lambda e: ("", "unreachable"))
        check("① 캐시 미스는 None 이다", how == "miss" and body is None, f"{how} {body}")
        c.close()


def test_unknown_outcome_raises():
    with tempfile.TemporaryDirectory() as tmp:
        c = OntologyCache(tmp)
        try:
            c.serve("/x", lambda e: ("{}", "weird"))
            check("⑥ 모르는 outcome 은 예외다", False, "예외가 안 났다")
        except ValueError as e:
            check("⑥ 모르는 outcome 은 예외다", "outcome" in str(e), str(e))
        c.close()


# ── ② 에러는 적재되지 않는다 ─────────────────────────────────────────────────

def test_error_payloads_are_never_cached():
    check("② error 키가 있으면 error 다", is_error_payload('{"error":"x"}'))
    check("② 파싱 불가도 error 다", is_error_payload("깨진 json {{{"))
    check("② 정상은 아니다", not is_error_payload(GOOD))
    with tempfile.TemporaryDirectory() as tmp:
        c = OntologyCache(tmp)
        r = c.put("/e", '{"error":"boom"}')
        check("② 에러는 적재 거부", not r["stored"] and "에러" in r["reason"], str(r))
        r = c.put("/e2", "깨진 json {{{")
        check("② 파싱 불가도 거부", not r["stored"], str(r))
        r = c.put("/e3", "")
        check("② 빈 본문도 거부", not r["stored"], str(r))
        check("② 캐시가 비어 있다", c.entries() == 0, str(c.entries()))
        c.close()


def test_no_ttl():
    """④ 오래된 값도 내준다 — 시간으로 버리면 마스터가 오래 꺼진 동안 아무것도 못 낸다."""
    with tempfile.TemporaryDirectory() as tmp:
        c = OntologyCache(tmp)
        c.put("/k", GOOD)
        # fetched_at 을 아주 과거로 바꿔도 여전히 내준다
        conn = c._conn_or_none()
        conn.execute("UPDATE cache SET fetched_at='2020-01-01T00:00:00'")
        conn.commit()
        out = c.get_stale("/k")
        check("④ TTL 없음 — 오래돼도 내준다", out is not None and "2020-01-01" in out,
              str(out)[:60])
        c.close()


def test_broken_cache_fails_open_once():
    with tempfile.TemporaryDirectory() as tmp:
        # 캐시 디렉토리 자리에 **파일**을 놓아 mkdir 을 실패시킨다
        bad = Path(tmp) / "x"
        bad.mkdir()
        (bad / "ontology_client_cache").write_text("not a dir", encoding="utf-8")
        c = OntologyCache(bad)
        check("⑤ 폴백이 비활성이다", not c.available, c.error)
        check("⑤ 사유를 값으로 들고 있다", "초기화 실패" in c.error, c.error)
        r = c.put("/k", GOOD)
        check("⑤ put 이 예외를 올리지 않는다", not r["stored"], str(r))
        check("⑤ get 은 None", c.get_stale("/k") is None)
        # [중요] 재시도하지 않는다 (한 번만 시도)
        c._tried = True
        check("⑤ 한 번만 시도한다", c._conn_or_none() is None)


# ── ⑦⑧ 벡터 폴백 ────────────────────────────────────────────────────────────

def _results(h="h1", body="미션 실행기는 태스크를 순차로 돌린다. 본문이 충분히 길다."):
    return [{"file": "Source/Mission/Executor.md", "content_preview": body,
             "content_hash": h, "category": "Game/Mission",
             "tags": ["미션", "실행기"], "related_classes": {"UMissionTaskExecutor": "x.h"}}]


def test_hash_skip_avoids_reembedding():
    with tempfile.TemporaryDirectory() as tmp:
        vf = VF.VectorFallback(tmp)
        if not vf.available:
            check("⑦ (건너뜀) chromadb 를 못 열었다", True, vf.error)
            return
        r1 = vf.upsert(_results())
        check("⑦ 처음엔 적재한다", r1["upserted"] == 1, str(r1))
        r2 = vf.upsert(_results())
        check("⑦ [중요] 해시가 같으면 건너뛴다", r2["upserted"] == 0 and r2["skipped"] == 1, str(r2))
        r3 = vf.upsert(_results(h="h2"))
        check("⑦ 해시가 바뀌면 다시 적재한다", r3["upserted"] == 1, str(r3))
        bad = vf.upsert([{"file": "", "content_preview": ""}])
        check("⑦ 못 쓸 항목은 버리고 센다", bad["dropped"] == 1, str(bad))


def test_search_marks_the_fallback_and_uses_our_model():
    with tempfile.TemporaryDirectory() as tmp:
        vf = VF.VectorFallback(tmp)
        if not vf.available:
            check("⑧ (건너뜀) chromadb 를 못 열었다", True, vf.error)
            return
        vf.upsert(_results())
        hits = vf.search("미션 실행기", limit=3)
        check("⑧ 한글 질의로 결과가 나온다", len(hits) == 1, str(len(hits)))
        check("⑧ [중요] 폴백임을 표시한다", hits[0]["source"] == "client_cache_vector",
              hits[0]["source"])
        check("⑧ 유사도가 0 이상", hits[0]["similarity"] >= 0.0, str(hits[0]["similarity"]))
        check("⑧ 태그를 되살린다", hits[0]["tags"] == ["미션", "실행기"], str(hits[0]["tags"]))
        check("⑧ related_classes 를 되살린다",
              "UMissionTaskExecutor" in hits[0]["related_classes"],
              str(hits[0]["related_classes"]))
        st = vf.stats()
        check("⑧ [중요] 임베더가 우리 다국어 모델이다",
              "multilingual" in (st["embed_model"] or ""), str(st["embed_model"]))
        check("⑧ 빈 질의는 빈 결과", vf.search("  ") == [])


def main() -> int:
    for fn in (test_three_outcomes_stay_separate, test_unknown_outcome_raises,
               test_error_payloads_are_never_cached, test_no_ttl,
               test_broken_cache_fails_open_once, test_hash_skip_avoids_reembedding,
               test_search_marks_the_fallback_and_uses_our_model):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_cache: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
