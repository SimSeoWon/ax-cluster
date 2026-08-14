"""클라이언트 온톨로지 폴백 캐시 — 원전 `mcp/context_search/ontology_client_cache.py` 이식
(소 3.4.3 · `#162`, 2026-08-15).

**last-known-good, 영구 보관.** 마스터가 응답한 온톨로지 소비 결과를 **엔드포인트를 키로**
로컬 SQLite 에 적재하고, 마스터에 닿지 못할 때 마지막 정상 응답을 `_stale: true` 로 표기해
내준다.

## 🔴 왜 우리에게 **더** 필요한가 (사용자 정정 2026-08-15)

나는 이것을 *"팀 전용일 가능성"* 으로 낮게 봤고 **틀렸다.** 사용자 지적:

> *"클라이언트 캐시는 오히려 가져와야 해. 기존과 달리 모든 윈도우 PC 는 온톨로지 정보가 없이
> 리눅스 서버에 저장된 내용을 활용하게 바뀌었으니까."*

실측이 그것을 확인했다 (2026-08-15):

    .2 · .43 의 `.claude/vector_db`     🔴 **디렉토리 자체가 없다** (온톨로지·벡터 0건)
    작업장 MCP 등록                      `mcpServers: {}` — 마스터 8101/8102/8103 등록 0건
    현재 온톨로지 전달                    마스터가 **매니페스트 파일**에 담아 scp

원전은 팀원 PC 가 **로컬 데이터를 가질 수도** 있는 구조였다(로컬/서버/클라이언트 3모드).
🔴 **우리는 온톨로지가 마스터에만 있다** — 소비자가 마스터에 닿지 못하면 대안이 없다.
그래서 이 캐시는 우리 구조에서 **덜 필요한 것이 아니라 더 필요하다.**

## 🔴 진짜 소비자는 요청자(`.33`)다 — 작업장이 아니다

    worker    (.2·.43)  스킬 `ax-infer` 가 못박는다: *"큐(8101)는 **401 이 정상**이다 —
                        토큰은 마스터에만 있고 **우회로를 찾지 않는다**"* → 매니페스트 파일만 읽는다
    requester (.33)     스킬 `ax-ontology` 가 `search_context_tool` 등 **MCP 조회**를 쓴다
                        = 🔴 **클라이언트 모드 소비자.** 마스터가 멈추면 **사람이 멈춘다**

⚠️ **코드 배달 경로는 아직 없다** — 우리 번들(`client/bundle.py`)은 config·CLAUDE.md·스킬
**텍스트만** 나른다(원전은 `.exe` 를 배포했고 그건 안 옮겼다). 그래서 이 모듈은 **여기(클라이언트
코드의 집)에 놓이고**, 배달은 별개 칸이다. 🔴 없는 경로를 지금 발명하지 않는다.

## 🔴 3분기 `outcome` 이 이 캐시의 핵심이다 (원전 그대로)

    "ok"           캐시 워밍(put) 후 응답 그대로 — 정상
    "absent"       🔴 **서버가 도달돼 「없다/오류」라고 답했다** → 응답을 그대로 넘긴다.
                   **폴백하지 않고 캐시하지도 않는다** — 진짜 부재 신호를 보존한다
    "unreachable"  전송 실패 → last-known-good 을 `_stale` 표기해 내준다. 없으면 `None`

⚠️ **`absent` 에 폴백하면 지워진 개념이 되살아난다.** 사람이 온톨로지에서 지운 항목이 캐시에서
다시 나오면, 그건 *"자동 승급 폐기"* 로 막아 둔 부류의 사고와 같은 결이다. 원전이 이 셋을 가른
이유가 그것이고, **합치면 안 된다.**

## 정책 (원전, 사용자 확정 2026-06-06)

- **TTL 없음** — 온톨로지는 중앙 SSOT 라 `_stale` 표기로 충분하다. 시간으로 버리면 마스터가
  오래 꺼져 있을 때 **아무것도 못 내주는** 상태가 된다
- **성공·비에러 응답만 적재** — top-level `error` 키가 있으면 skip. 파싱 불가도 error 로 본다
  → 🔴 캐시에 있는 것은 언제나 **마지막 「정상」 데이터**다
- 검색용 벡터 폴백(`vector_fallback.py`)과 **디렉토리·책임을 분리**한다 — 정형 KV vs 임베딩

## 원전과 다르게 둔 것 둘

**① 모듈 전역이 아니라 인스턴스다.** 원전은 전역 `_conn` + `reset_for_test()` 로 테스트를
우회한다. 우리는 `OntologyCache(cache_dir)` 로 받는다 — 🔴 원전 자신이 같은 이유로
`attempt_branch(ts=…)` 를 인자로 뒀다(*"테스트에서 고정할 수 있어야 한다"*).

**② 실패를 값으로 돌린다.** 원전은 `except … : _cs_log(...)` 로 삼킨다. **fail-open 은 옮긴다**
(캐시가 호출자를 막으면 더 나쁘다) — 다만 조용히는 안 된다(중 4.2 σ 기준).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_NAME = "cache.db"
CACHE_DIRNAME = "ontology_client_cache"


def is_error_payload(body: str) -> bool:
    """last-known-good 이 **아닌** 응답인가. 🔴 **파싱 불가도 error 로 본다.**

    이유: 캐시의 계약이 *"있는 것은 마지막 정상 데이터"* 다. 못 읽는 것을 적재하면 그 계약이
    깨지고, 폴백이 쓰레기를 정답처럼 내민다.
    """
    try:
        obj = json.loads(body)
    except (TypeError, ValueError):
        return True
    return isinstance(obj, dict) and "error" in obj


class OntologyCache:
    """엔드포인트 → 마지막 정상 응답. 🔴 **한 번만 초기화를 시도한다.**

    초기화가 실패하면 다시 시도하지 않고 **폴백을 비활성**으로 둔다(원전 그대로). 매 호출마다
    재시도하면 디스크가 못 쓰는 상태에서 호출자가 매번 그 비용을 낸다.
    """

    def __init__(self, cache_dir):
        self.dir = Path(cache_dir) / CACHE_DIRNAME
        self._conn = None
        self._tried = False
        self._lock = threading.Lock()
        self.error = ""

    # ── 연결 ────────────────────────────────────────────────────────────────
    def _conn_or_none(self):
        if self._conn is not None or self._tried:
            return self._conn
        self._tried = True
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.dir / DB_NAME), check_same_thread=False)
            conn.execute("CREATE TABLE IF NOT EXISTS cache ("
                         "endpoint TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                         "fetched_at TEXT NOT NULL)")
            conn.commit()
            self._conn = conn
        except (OSError, sqlite3.Error) as e:
            # 🔴 fail-open — 캐시가 없어도 호출자는 계속 가야 한다. 다만 사유를 남긴다.
            self.error = f"캐시 초기화 실패 — 폴백 비활성: {e}"
            self._conn = None
        return self._conn

    @property
    def available(self) -> bool:
        return self._conn_or_none() is not None

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    # ── 적재·조회 ────────────────────────────────────────────────────────────
    def put(self, endpoint: str, body: str) -> dict:
        """성공·비에러 응답만 적재(upsert). 🔴 **에러는 캐시에 들어가지 않는다.**"""
        if not body:
            return {"stored": False, "reason": "본문이 비었다"}
        if is_error_payload(body):
            return {"stored": False, "reason": "에러 응답이거나 파싱 불가 — 적재하지 않는다"}
        conn = self._conn_or_none()
        if conn is None:
            return {"stored": False, "reason": self.error or "캐시 없음"}
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with self._lock:
                conn.execute(
                    "INSERT INTO cache(endpoint, payload, fetched_at) VALUES(?,?,?) "
                    "ON CONFLICT(endpoint) DO UPDATE SET "
                    "payload=excluded.payload, fetched_at=excluded.fetched_at",
                    (endpoint, body, now))
                conn.commit()
        except sqlite3.Error as e:
            return {"stored": False, "reason": f"적재 실패: {e}"}
        return {"stored": True, "at": now}

    def get_stale(self, endpoint: str) -> str | None:
        """마지막 정상 응답에 `_stale`·`_cached_at` 을 **주입해서** 돌려준다. 없으면 `None`.

        🔴 표기를 주입하는 것이 계약이다 — 소비자가 *"이건 낡은 값이다"* 를 알아야 한다.
        표기 없이 내주면 마스터가 죽은 것을 아무도 모른다.
        """
        conn = self._conn_or_none()
        if conn is None:
            return None
        try:
            with self._lock:
                row = conn.execute(
                    "SELECT payload, fetched_at FROM cache WHERE endpoint=?",
                    (endpoint,)).fetchone()
        except sqlite3.Error as e:
            self.error = f"조회 실패: {e}"
            return None
        if not row:
            return None
        payload, fetched_at = row
        try:
            obj = json.loads(payload)
        except ValueError:
            return None
        if isinstance(obj, dict):
            obj["_stale"] = True
            obj["_cached_at"] = fetched_at
            return json.dumps(obj, ensure_ascii=False, indent=2)
        return json.dumps({"_stale": True, "_cached_at": fetched_at, "data": obj},
                          ensure_ascii=False, indent=2)

    def entries(self) -> int:
        conn = self._conn_or_none()
        if conn is None:
            return 0
        try:
            with self._lock:
                return int(conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0])
        except sqlite3.Error:
            return 0

    # ── 오케스트레이션 ───────────────────────────────────────────────────────
    def serve(self, endpoint: str, fetch_fn, *, logf=None) -> tuple:
        """🔴 **3분기.** `fetch_fn(endpoint) → (body, outcome)`.
        `outcome ∈ {"ok","absent","unreachable"}`. 반환 `(body|None, 어떻게)`.

            ok           → 캐시 워밍 후 응답 그대로            → "server"
            absent       → 🔴 **그대로 넘긴다. 폴백·캐시 안 한다** → "absent"
                           (서버가 「없다」고 답한 것이다 — 폴백하면 지워진 개념이 되살아난다)
            unreachable  → stale 폴백. 없으면 `(None, "miss")`  → "stale" | "miss"

        ⚠️ 모르는 `outcome` 은 **`unreachable` 로 접지 않고 예외**다 — 조용히 폴백하면
        서버가 무슨 말을 했는지 모른 채 낡은 값을 내주게 된다.
        """
        def log(msg):
            if logf:
                logf(msg)

        body, outcome = fetch_fn(endpoint)
        if outcome == "ok":
            r = self.put(endpoint, body)
            log(f"[온톨로지/원격] {endpoint} → 서버 OK"
                + (" (캐시 워밍)" if r.get("stored") else f" (캐시 skip: {r.get('reason')})"))
            return body, "server"
        if outcome == "absent":
            log(f"[온톨로지/원격] {endpoint} → 서버 응답: 부재/오류 — 🔴 폴백하지 않는다")
            return body, "absent"
        if outcome != "unreachable":
            raise ValueError(f"모르는 outcome: {outcome!r} "
                             "(ok|absent|unreachable 중 하나여야 한다)")
        cached = self.get_stale(endpoint)
        if cached is None:
            log(f"[온톨로지/원격] {endpoint} → 서버 불통 · 캐시 미스")
            return None, "miss"
        try:
            at = json.loads(cached).get("_cached_at", "?")
        except ValueError:
            at = "?"
        log(f"[온톨로지/원격] {endpoint} → 서버 불통, stale 폴백 (cached_at={at})")
        return cached, "stale"
